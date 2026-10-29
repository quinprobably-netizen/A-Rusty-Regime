//! Headless simulation tests: real Avian physics, scripted input, no window.

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::ecs::system::RunSystemOnce;
use bevy::time::TimeUpdateStrategy;
use std::collections::HashSet;
use std::sync::Arc;
use std::time::Duration;

use crate::controller::{self, ControllerPlugin, MoveState, Player};
use crate::input::{PlayerInput, ViewAngles};
use crate::health::{HealthPlugin, PlayerHealth, PlayerHit};
use crate::tuning::Tuning;
use crate::planet::{self, chunk::{self, ChunkMesh}, quadtree::{self, NodeId}};
use crate::planet::gravity::gravitate;
use crate::surface::testing::random_dirs;
use crate::surface::{Origin, Sphere, Surface, QUANTUM};
use crate::system::Body;
use crate::save::{Save, SaveFile, SavePlugin};
use crate::vehicle::{Driving, VehiclePlugin};
use crate::weapon::{Arsenal, WeaponKind, WeaponPlugin};

const DT: f32 = 1.0 / 66.0;

fn make_app(tuning: Tuning) -> App {
    let mut app = build_app(tuning);
    app.finish();
    app.update(); // run Startup so the player exists
    app
}

/// `make_app` before `finish`, for tests that add a plugin or resources first.
fn build_app(tuning: Tuning) -> App {
    let mut app = App::new();
    app.add_plugins((MinimalPlugins, bevy::state::app::StatesPlugin, TransformPlugin, AssetPlugin::default(), bevy::world_serialization::WorldSerializationPlugin, bevy::mesh::MeshPlugin, PhysicsPlugins::default()))
        .insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_secs_f32(DT)))
        .insert_resource(Time::<Fixed>::from_seconds(DT as f64))
        .insert_resource(tuning)
        .insert_resource(SaveFile(None))
        .init_resource::<PlayerInput>()
        .init_resource::<ViewAngles>()
        .add_plugins(crate::boot::BootPlugin)
        .insert_resource(crate::character::Characters::load())
        .add_plugins((ControllerPlugin, WeaponPlugin, HealthPlugin, VehiclePlugin, SavePlugin, crate::abilities::AbilitiesPlugin));
    app.world_mut().spawn((RigidBody::Static, Collider::cuboid(200.0, 1.0, 200.0), Transform::from_xyz(0.0, -0.5, 0.0)));
    app
}

fn wall(app: &mut App, size: Vec3, pos: Vec3) {
    app.world_mut().spawn((RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), Transform::from_translation(pos)));
}

fn run(app: &mut App, seconds: f32) {
    for _ in 0..(seconds / DT).round() as usize {
        app.update();
    }
}

fn player(app: &mut App) -> (Vec3, Vec3, MoveState) {
    let mut q = app.world_mut().query::<(&Player, &Transform)>();
    let (p, tf) = q.single(app.world()).unwrap();
    (tf.translation, p.velocity, p.state)
}

fn player_state(app: &mut App) -> MoveState {
    player(app).2
}

fn set_player(app: &mut App, pos: Vec3, vel: Vec3) {
    let mut q = app.world_mut().query::<(&mut Player, &mut Transform)>();
    let (mut p, mut tf) = q.single_mut(app.world_mut()).unwrap();
    tf.translation = pos;
    p.velocity = vel;
    p.state = MoveState::Air;
}

fn input(app: &mut App) -> Mut<'_, PlayerInput> {
    app.world_mut().resource_mut::<PlayerInput>()
}

/// Presses jump and returns the highest the player rises over the next 100 ticks, measured by `altitude`.
fn jump_apex(app: &mut App, altitude: impl Fn(&mut App) -> f32) -> f32 {
    let start = altitude(app);
    input(app).jump_pressed = true;
    let mut apex = 0.0_f32;
    for _ in 0..100 {
        app.update();
        apex = apex.max(altitude(app) - start);
    }
    apex
}

#[test]
fn source_math() {
    // Friction below stop speed uses stop speed as the control value.
    let mut v = Vec3::new(1.0, 0.0, 0.0);
    controller::friction(&mut v, 4.0, 2.2, DT);
    assert!((v.x - (1.0 - 2.2 * 4.0 * DT)).abs() < 1e-5);
    // Ground accel never exceeds wish speed along the wish dir.
    let mut v = Vec3::new(7.4, 0.0, 0.0);
    controller::accelerate(&mut v, Vec3::X, 7.5, 10.0, DT);
    assert!((v.x - 7.5).abs() < 1e-5);
    // Air accel: perpendicular wish adds up to the cap, raising total speed.
    let mut v = Vec3::new(10.0, 0.0, 0.0);
    controller::air_accelerate(&mut v, Vec3::Z, 7.5, 10.0, 0.66, DT);
    assert!(v.length() > 10.0 && (v.z - 0.66).abs() < 1e-5);
}

#[test]
fn walks_to_max_speed_on_ground() {
    let mut app = make_app(Tuning::default());
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 2.0);
    let (pos, vel, state) = player(&mut app);
    assert_eq!(state, MoveState::Ground);
    assert!((vel.xz().length() - 7.5).abs() < 0.05, "speed {}", vel.xz().length());
    assert!((pos.y - 0.9).abs() < 0.05, "height {}", pos.y);
    assert!(pos.z < 0.0, "moved forward (-Z)");
}

#[test]
fn jump_apex_is_unchanged_by_the_retune() {
    let mut app = make_app(Tuning::default());
    run(&mut app, 0.5);
    let apex = jump_apex(&mut app, |a| player(a).0.y);
    // v²/2g for 4.74 m/s at 9.8 is 1.146 m; the tick integrator lands a few cm under it.
    assert!((1.08..1.18).contains(&apex), "apex {apex}");
    assert_eq!(Tuning::default().gravity, 9.8);
}

#[test]
fn air_strafing_gains_speed() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 80.0, 0.0), Vec3::new(7.5, 0.0, 0.0));
    input(&mut app).movement = Vec2::X; // strafe right
    for _ in 0..66 {
        // Turn so "right" stays just ahead of perpendicular to velocity.
        let (_, vel, _) = player(&mut app);
        let d = vel.with_y(0.0).normalize();
        let wish = Quat::from_rotation_y(-1.55) * d;
        app.world_mut().resource_mut::<ViewAngles>().yaw = (-wish.z).atan2(wish.x);
        app.update();
    }
    let (_, vel, _) = player(&mut app);
    assert!(vel.xz().length() > 9.0, "speed {}", vel.xz().length());
}

#[test]
fn bunny_hopping_keeps_speed() {
    let mut t = Tuning::default();
    t.auto_bhop = true;
    let mut app = make_app(t);
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::new(10.0, 0.0, 0.0));
    input(&mut app).jump_held = true;
    run(&mut app, 3.0);
    let (_, hop, _) = player(&mut app);

    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::new(10.0, 0.0, 0.0));
    run(&mut app, 3.0);
    let (_, walk, _) = player(&mut app);
    assert!(hop.xz().length() > 9.5, "bhop speed {}", hop.xz().length());
    assert!(walk.xz().length() < 0.5, "friction stops a grounded player");
}

#[test]
fn ramp_slide_launches_off_ramp() {
    let mut app = make_app(Tuning::default());
    // 30 degree ramp rising toward -Z
    app.world_mut().spawn((
        RigidBody::Static,
        Collider::cuboid(8.0, 0.5, 20.0),
        Transform::from_xyz(0.0, 2.5, -15.0).with_rotation(Quat::from_rotation_x(30f32.to_radians())),
    ));
    set_player(&mut app, Vec3::new(0.0, 1.0, -9.0), Vec3::new(0.0, 0.0, -16.0));
    let mut max_y = 0.0f32;
    for _ in 0..90 {
        app.update();
        max_y = max_y.max(player(&mut app).0.y);
    }
    assert!(max_y > 3.0, "fast player slid up the ramp, max height {max_y}");
}

#[test]
fn wall_runs_along_wall() {
    let mut app = make_app(Tuning::default());
    wall(&mut app, Vec3::new(1.0, 8.0, 40.0), Vec3::new(1.0, 4.0, -10.0));
    set_player(&mut app, Vec3::new(0.2, 2.5, 0.0), Vec3::new(0.0, 2.0, -9.0));
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 0.2);
    assert_eq!(player(&mut app).2, MoveState::WallRun);
    run(&mut app, 0.8);
    let (pos, _, state) = player(&mut app);
    assert_eq!(state, MoveState::WallRun);
    assert!(pos.y > 1.5, "low gravity while wall running, y {}", pos.y);
    // Jump off the wall
    input(&mut app).jump_pressed = true;
    app.update();
    let (_, vel, state) = player(&mut app);
    assert_eq!(state, MoveState::Air);
    assert!(vel.x < -3.0 && vel.y > 3.0, "wall jump pushes away and up {vel}");
}

#[test]
fn mantles_onto_ledge() {
    let mut app = make_app(Tuning::default());
    wall(&mut app, Vec3::new(4.0, 1.8, 4.0), Vec3::new(0.0, 0.9, -3.0));
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::ZERO);
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 0.3);
    input(&mut app).jump_pressed = true;
    run(&mut app, 0.6); // long enough to climb, short enough not to walk off the far side
    let (pos, _, _) = player(&mut app);
    assert!(pos.y > 1.8 + 0.8, "on top of the ledge, y {}", pos.y);
}

#[test]
fn slides_under_low_ceiling() {
    let mut app = make_app(Tuning::default());
    wall(&mut app, Vec3::new(6.0, 0.5, 10.0), Vec3::new(0.0, 1.75, -10.0));
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::new(0.0, 0.0, -8.0));
    {
        let mut i = input(&mut app);
        i.movement = Vec2::Y;
        i.crouch_held = true;
    }
    run(&mut app, 0.4);
    assert_eq!(player(&mut app).2, MoveState::Slide);
    run(&mut app, 2.5);
    let (pos, _, _) = player(&mut app);
    assert!(pos.z < -15.0, "got through the tunnel, z {}", pos.z);
    // Can't stand up under the ceiling
    input(&mut app).crouch_held = false;
    set_player(&mut app, Vec3::new(0.0, 0.73, -10.0), Vec3::ZERO);
    run(&mut app, 0.2);
    let crouched = app.world_mut().query::<&Player>().single(app.world()).unwrap().crouched;
    assert!(crouched);
}

#[test]
fn rocket_jump() {
    let mut app = make_app(Tuning::default());
    run(&mut app, 0.3);
    app.world_mut().resource_mut::<ViewAngles>().pitch = -1.5;
    input(&mut app).fire_held = true;
    let mut best = 0.0f32;
    for _ in 0..20 {
        app.update();
        best = best.max(player(&mut app).1.y);
    }
    assert!(best > 5.0, "launched upward, vy {best}");
}

#[test]
fn rocket_knocks_props() {
    let mut app = make_app(Tuning::default());
    let crate_id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_xyz(0.0, 0.5, -6.0))).id();
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::ZERO);
    run(&mut app, 0.3);
    app.world_mut().resource_mut::<ViewAngles>().pitch = -0.15;
    input(&mut app).fire_held = true;
    run(&mut app, 0.5);
    let pos = app.world().get::<Transform>(crate_id).unwrap().translation;
    assert!(pos.z < -6.5 || pos.y > 1.0, "crate moved: {pos}");
}

#[test]
fn pushes_props_by_walking() {
    let mut app = make_app(Tuning::default());
    let crate_id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_xyz(0.0, 0.5, -2.0))).id();
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 2.0);
    let pos = app.world().get::<Transform>(crate_id).unwrap().translation;
    assert!(pos.z < -4.0, "crate pushed: {pos}");
}


/// Boots the full game (all plugins, no window or GPU) to catch system
/// conflicts and missing resources that only show up at runtime.
#[test]
fn full_game_boots_headless() {
    use bevy::render::{RenderPlugin, settings::WgpuSettings};
    let mut app = App::new();
    app.add_plugins((
        DefaultPlugins
            .build()
            .disable::<bevy::winit::WinitPlugin>()
            .set(RenderPlugin { render_creation: WgpuSettings { backends: None, ..default() }.into(), ..default() }),
        PhysicsPlugins::default(),
    ))
    .insert_resource(Time::<Fixed>::from_hz(66.0))
    .insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_secs_f32(DT)))
    .insert_resource(SaveFile(None))
    .add_plugins((
        crate::tuning::TuningPlugin,
        crate::input::InputPlugin,
        ControllerPlugin,
        crate::camera::CameraPlugin,
        WeaponPlugin,
        crate::viewmodel::ViewModelPlugin,
        HealthPlugin,
        crate::hud::HudPlugin,
        VehiclePlugin,
        SavePlugin,
        crate::boot::BootPlugin,
        solar::SolarPlugin,
    ));
    app.finish();
    app.cleanup();
    for _ in 0..30 {
        app.update();
    }
    let (pos, _, state) = player(&mut app);
    assert_eq!(state, MoveState::Ground, "spawned and landed at {pos}");
}

fn select_weapon(app: &mut App, kind: WeaponKind) {
    let slot = crate::weapon::WEAPONS.iter().position(|k| *k == kind).unwrap();
    app.world_mut().resource_mut::<Arsenal>().select(slot);
    run(app, 0.3); // raise animation
}

fn prop(app: &mut App, pos: Vec3) -> Entity {
    app.world_mut()
        .spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(pos)))
        .id()
}

#[test]
fn weapon_switching() {
    let mut app = make_app(Tuning::default());
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::RocketLauncher);
    input(&mut app).weapon_select = Some(2);
    app.update();
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Shotgun);
    input(&mut app).weapon_step = 9; // wraps around past the knife
    app.update();
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::RocketLauncher);
    input(&mut app).weapon_last = true;
    app.update();
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Shotgun);
    // Can't fire while the new weapon comes up.
    input(&mut app).fire_pressed = true;
    app.update();
    assert_eq!(app.world().resource::<Arsenal>().shots, 0);
}

#[test]
fn rifle_is_automatic_pistol_is_not() {
    let mut app = make_app(Tuning::default());
    select_weapon(&mut app, WeaponKind::Pistol);
    input(&mut app).fire_held = true;
    input(&mut app).fire_pressed = true;
    run(&mut app, 1.0);
    assert_eq!(app.world().resource::<Arsenal>().shots, 1, "pistol fires once per press");
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.5);
    assert_eq!(app.world().resource::<Arsenal>().shots, 2);

    select_weapon(&mut app, WeaponKind::Rifle);
    run(&mut app, 1.0);
    let shots = app.world().resource::<Arsenal>().shots;
    assert!(shots > 8, "rifle keeps firing while held: {shots}");
}

#[test]
fn hitscan_knocks_props() {
    let mut app = make_app(Tuning::default());
    // Player at z=10 looks down -Z; a crate on the floor 6 m ahead, aim a bit down.
    let crate_ = prop(&mut app, controller::SPAWN + Vec3::new(0.0, -0.5, -6.0));
    select_weapon(&mut app, WeaponKind::Shotgun);
    app.world_mut().resource_mut::<ViewAngles>().pitch = -0.2;
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.2);
    let v = app.world().get::<LinearVelocity>(crate_).unwrap().0;
    assert!(v.z < -2.0, "crate pushed away from the player: {v}");
    assert_eq!(app.world().resource::<Arsenal>().shots, 1);
}

#[test]
fn body_pose_follows_movement() {
    use crate::body::{Pose, playback_rate, pose_for};
    let max = 7.5;
    assert_eq!(pose_for(MoveState::Ground, false, 0.0, 0.0, max, 0.0, false, false), Pose::Idle);
    assert_eq!(pose_for(MoveState::Ground, false, 2.0, 0.0, max, 0.0, false, false), Pose::Walk);
    assert_eq!(pose_for(MoveState::Ground, false, 5.0, 0.0, max, 0.0, false, false), Pose::Run);
    assert_eq!(pose_for(MoveState::Ground, false, 7.0, 0.0, max, 0.0, false, false), Pose::Sprint);
    assert_eq!(pose_for(MoveState::Ground, true, 0.0, 0.0, max, 0.0, false, false), Pose::Crouch);
    assert_eq!(pose_for(MoveState::Ground, true, 2.0, 0.0, max, 0.0, false, false), Pose::CrouchWalk);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, 4.0, max, 0.0, false, true), Pose::DoubleJump);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, -4.0, max, 0.0, true, true), Pose::Grapple);
    assert_eq!(pose_for(MoveState::Slide, true, 8.0, 0.0, max, 0.0, false, false), Pose::Slide);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, 4.0, max, 0.0, false, false), Pose::Jump);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, -4.0, max, 0.0, false, false), Pose::Fall);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, -4.0, max, 0.0, true, false), Pose::Grapple);
    assert_eq!(pose_for(MoveState::WallRun, false, 8.0, 1.0, max, 1.0, false, false), Pose::WallRunL);
    assert_eq!(pose_for(MoveState::WallRun, false, 8.0, 1.0, max, -1.0, false, false), Pose::WallRunR);
    assert_eq!(pose_for(MoveState::Mantle, false, 0.0, 0.0, max, 0.0, false, false), Pose::Mantle);
    // Feet speed up with the run and never stall.
    assert!(playback_rate(Pose::Sprint, 7.5, max) > playback_rate(Pose::Sprint, 5.5, max));
    assert!(playback_rate(Pose::Walk, 0.3, max) >= 0.7);
    assert_eq!(playback_rate(Pose::Idle, 3.0, max), 1.0);
}

// --- Island terrain ---

/// Drops make_app's flat floor so only the terrain under test can be hit.
fn drop_flat_floor(app: &mut App) {
    let floor: Vec<Entity> = app.world_mut().query_filtered::<Entity, (With<Collider>, Without<Player>)>().iter(app.world()).collect();
    for e in floor {
        app.world_mut().despawn(e);
    }
}

/// A headless app on the test moon: the player spawns 1 m above the ground in `spawn_dir`,
/// dynamic bodies fall toward the centre, and terrain chunks of `cell` metres cover
/// `ground_radius` around the spawn (none when it is 0).
fn sphere_app(cell: f32, spawn_dir: Vec3, ground_radius: f32) -> (App, Arc<Sphere>, Origin, Vec<Arc<ChunkMesh>>) {
    sphere_app_on(Body::test_moon(), cell, spawn_dir, ground_radius)
}

/// `sphere_app` on `body` in place of the test moon.
fn sphere_app_on(body: Body, cell: f32, spawn_dir: Vec3, ground_radius: f32) -> (App, Arc<Sphere>, Origin, Vec<Arc<ChunkMesh>>) {
    let mut tuning = Tuning::default();
    tuning.terrain.cell = cell;
    let mut app = build_app(tuning);
    drop_flat_floor(&mut app);
    let sphere = Arc::new(Sphere::new(body));
    let spawn = sphere.surface_point(spawn_dir) + spawn_dir * 1.0;
    let origin = Origin::at(spawn, QUANTUM);
    app.insert_resource(Surface::Sphere(sphere.clone()))
        .insert_resource(origin)
        .insert_resource(controller::WorldBounds { spawn, kill_altitude: -50.0 })
        .insert_resource(Gravity(Vec3::ZERO))
        .add_systems(FixedUpdate, gravitate.before(controller::ControllerSet));
    app.finish();
    app.update();
    let meshes = if ground_radius > 0.0 { chunk::spawn_ground(app.world_mut(), &sphere, &origin, cell, spawn, ground_radius) } else { Vec::new() };
    (app, sphere, origin, meshes)
}

#[test]
fn chunk_colliders_match_their_meshes() {
    let sphere = Sphere::new(Body::test_moon());
    let origin = Origin::at(sphere.surface_point(Vec3::X), QUANTUM);
    let mut app = make_app(Tuning::default());
    drop_flat_floor(&mut app);
    let meshes = chunk::spawn_ground(app.world_mut(), &sphere, &origin, 4.0, sphere.surface_point(Vec3::X), 60.0);
    app.update();
    for dir in random_dirs(20).into_iter().map(|d| (Vec3::X * 40.0 + d).normalize()) {
        let Some(g) = meshes.iter().find_map(|m| m.ground_on(dir)) else { continue };
        let from = origin.world(sphere.surface_point(dir) + dir * 100.0);
        let hit = app.world_mut().run_system_once(move |q: SpatialQuery| q.cast_ray(from, Dir3::new(-dir).unwrap(), 300.0, true, &SpatialQueryFilter::default())).unwrap().expect("ray hits the chunk");
        assert!(origin.body(from - dir * hit.distance).distance(g.point) < 1e-2);
    }
}

#[test]
fn crates_fall_toward_the_centre_and_rest() {
    let (mut app, sphere, origin, meshes) = sphere_app(4.0, Vec3::X, 80.0);
    // About 3 m from the player, who now stands upright at the spawn.
    let dir = (Vec3::X + Vec3::Z * 0.003).normalize();
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(sphere.surface_point(dir) + dir * 50.0)))).id();
    run(&mut app, 6.0);
    let pos = origin.body(app.world().get::<Transform>(id).unwrap().translation);
    let ground = meshes.iter().find_map(|m| m.ground_on(pos.normalize())).unwrap().point;
    assert!(pos.normalize().dot(dir) > 0.99996, "fell radially: {pos}");
    assert!((pos.length() - ground.length() - 0.5).abs() < 0.1, "rests on the ground, {} over it", pos.length() - ground.length());
    assert!(app.world().get::<LinearVelocity>(id).unwrap().0.length() < 0.05);
}

#[test]
fn resting_bodies_stay_asleep_under_gravity() {
    let (mut app, sphere, origin, _) = sphere_app(4.0, Vec3::X, 80.0);
    // About 3 m from the player, who stands upright at the spawn.
    let dir = (Vec3::X + Vec3::Z * 0.003).normalize();
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(sphere.surface_point(dir) + dir * 3.0)))).id();
    run(&mut app, 5.0);
    assert!(app.world().get::<Sleeping>(id).is_some(), "asleep after settling");
    run(&mut app, 1.0);
    assert!(app.world().get::<Sleeping>(id).is_some(), "gravity does not keep waking it");
}

/// Fires `kind` level at +X on the test moon given `gravity`, with no ground to hit, and
/// returns how fast the shot then gains speed sideways to its flight (m/s²) and how closely
/// that points at the centre (1 is straight at it). `probe` reads the shot's position and velocity.
fn projectile_fall(gravity: f32, kind: WeaponKind, probe: fn(&mut App) -> (Vec3, Vec3)) -> (f32, f32) {
    let (mut app, _, origin, _) = sphere_app_on(Body { gravity, ..Body::test_moon() }, 4.0, Vec3::X, 0.0);
    select_weapon(&mut app, kind);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.05);
    let (_, v0) = probe(&mut app);
    let flight = 16.0 * DT;
    run(&mut app, flight);
    let (pos, v1) = probe(&mut app);
    // Drag and the fall's own direction both act along the flight: only the rest is the pull.
    let (dv, along) = (v1 - v0, v0.normalize());
    let side = dv - along * dv.dot(along);
    let down = -origin.body(pos).normalize();
    (side.dot(down) / flight, side.normalize_or_zero().dot(down))
}

#[test]
fn bullets_and_grenades_fall_toward_the_centre_with_the_worlds_gravity() {
    use crate::weapon::{Bullet, GrenadeShell};
    fn bullet(app: &mut App) -> (Vec3, Vec3) {
        let mut q = app.world_mut().query::<(&Bullet, &Transform)>();
        q.single(app.world()).map(|(b, tf)| (tf.translation, b.velocity)).expect("one bullet in the air")
    }
    fn grenade(app: &mut App) -> (Vec3, Vec3) {
        let mut q = app.world_mut().query::<(&GrenadeShell, &Transform)>();
        q.single(app.world()).map(|(g, tf)| (tf.translation, g.velocity)).expect("one grenade in the air")
    }
    // Haven's 9.8 and Ash's 1.9. Level at +X is north, world +Y: the old fixed -Y pull acted
    // along the flight and none of it toward the centre.
    let grenade_g = Tuning::default().grenade.gravity;
    for (g, kind, probe, expect) in [(9.8, WeaponKind::Pistol, bullet as fn(&mut App) -> _, 9.8), (1.9, WeaponKind::Pistol, bullet, 1.9), (9.8, WeaponKind::Grenade, grenade, grenade_g), (1.9, WeaponKind::Grenade, grenade, grenade_g * 1.9 / 9.8)] {
        let (fall, aim) = projectile_fall(g, kind, probe);
        assert!(aim > 0.99, "{kind:?} on a {g} world falls toward the centre: {aim}");
        assert!((fall - expect).abs() < 0.05 * expect, "{kind:?} on a {g} world falls at {fall}, not {expect}");
    }
}

/// The surface point under `at_dir` and the local frame there.
fn course_frame(sphere: &Arc<Sphere>, at_dir: Vec3) -> (Vec3, Quat) {
    let at = sphere.surface_point(at_dir);
    (at, Surface::Sphere(sphere.clone()).frame(at))
}

/// `set_player` in the course frame at `at_dir`, with local y measured from the deck top.
fn set_player_local(app: &mut App, origin: &Origin, sphere: &Arc<Sphere>, at_dir: Vec3, local_pos: Vec3, local_vel: Vec3) {
    let (at, frame) = course_frame(sphere, at_dir);
    set_player(app, origin.world(at + frame * (local_pos + Vec3::Y * planet::COURSE_DECK)), frame * local_vel);
}

/// `player` in the course frame at `at_dir`: position over the deck top, velocity in the frame.
fn player_local(app: &mut App, origin: &Origin, sphere: &Arc<Sphere>, at_dir: Vec3) -> (Vec3, Vec3, MoveState) {
    let (at, frame) = course_frame(sphere, at_dir);
    let (pos, vel, state) = player(app);
    (frame.inverse() * (origin.body(pos) - at) - Vec3::Y * planet::COURSE_DECK, frame.inverse() * vel, state)
}

#[test]
fn runs_along_the_surface_for_a_minute() {
    // On the equator 150 m short of the +X/+Z face seam; local -X is west, toward +Z and across it.
    let theta = std::f32::consts::FRAC_PI_4 - 150.0 / 2000.0;
    let start = Vec3::new(theta.cos(), 0.0, theta.sin());
    let (mut app, _, origin, meshes) = sphere_app(4.0, start, 650.0);
    app.world_mut().resource_mut::<ViewAngles>().yaw = std::f32::consts::FRAC_PI_2;
    input(&mut app).movement = Vec2::Y;
    // Within 5 cm of standing height over the mesh every tick, once landed from the 1 m spawn.
    run(&mut app, 0.5);
    for i in 0..(59.5 / DT).round() as usize {
        app.update();
        let body = origin.body(player(&mut app).0);
        let ground = meshes.iter().find_map(|m| m.ground_on(body.normalize())).expect("on built ground").point;
        let off = (body.length() - ground.length() - 0.9).abs();
        assert!(off < 0.05, "tick {i}: feet {} m over the mesh", body.length() - ground.length());
    }
    let (pos, _, state) = player(&mut app);
    let body = origin.body(pos);
    let dir = body.normalize();
    assert_eq!(state, MoveState::Ground);
    assert!(dir.angle_between(start) * 2000.0 > 380.0, "travelled {} m", dir.angle_between(start) * 2000.0);
    assert!(dir.z > start.z + 0.1, "went toward +Z, across the seam");
    let ground = meshes.iter().find_map(|m| m.ground_on(dir)).expect("still on built ground").point;
    assert!((body.length() - ground.length() - 0.9).abs() < 0.05, "feet {} m over the mesh", body.length() - ground.length());
}

#[test]
fn jump_height_on_the_sphere_matches_the_flat_world() {
    let flat = {
        let mut app = make_app(Tuning::default());
        run(&mut app, 0.5);
        jump_apex(&mut app, |a| player(a).0.y)
    };
    for dir in [Vec3::Y, Vec3::X] {
        let (mut app, _, origin, _) = sphere_app(4.0, dir, 60.0);
        run(&mut app, 0.5);
        let apex = jump_apex(&mut app, |a| origin.body(player(a).0).length());
        assert!((apex - flat).abs() < 0.02 * flat, "apex {apex} vs flat {flat} at {dir}");
    }
}

#[test]
fn stairs_wall_runs_mantles_and_slides_on_the_sphere() {
    let at = Vec3::new(0.2, 0.7, 0.68).normalize();
    let (mut app, sphere, origin, _) = sphere_app(4.0, at, 40.0);
    let surface = Surface::Sphere(sphere.clone());
    planet::spawn_course(app.world_mut(), &surface, &origin, sphere.surface_point(at));
    // Wall run and wall jump, as in wall_runs_along_wall.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(0.2, 2.5, -18.0), Vec3::new(0.0, 2.0, -9.0));
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 1.0);
    assert_eq!(player(&mut app).2, MoveState::WallRun);
    input(&mut app).jump_pressed = true;
    app.update();
    let (_, vel, state) = player_local(&mut app, &origin, &sphere, at);
    assert!(state == MoveState::Air && vel.x < -3.0 && vel.y > 3.0, "wall jump {vel}");
    // Mantle, as in mantles_onto_ledge.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(-8.0, 0.95, 0.0), Vec3::ZERO);
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 0.3);
    input(&mut app).jump_pressed = true;
    run(&mut app, 0.6);
    assert!(player_local(&mut app, &origin, &sphere, at).0.y > 2.6, "mantled");
    // Stair step onto the 0.3 m block and keep walking on it.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(8.0, 0.95, -2.0), Vec3::ZERO);
    run(&mut app, 1.2);
    let (p, _, state) = player_local(&mut app, &origin, &sphere, at);
    assert!(state == MoveState::Ground && p.y > 1.1 && p.z < -6.0, "stepped up: {p}");
    // Slide under the tunnel roof, as in slides_under_low_ceiling.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(16.0, 0.95, 0.0), Vec3::new(0.0, 0.0, -8.0));
    {
        let mut i = input(&mut app);
        i.movement = Vec2::Y;
        i.crouch_held = true;
    }
    run(&mut app, 0.4);
    assert_eq!(player(&mut app).2, MoveState::Slide);
    run(&mut app, 2.5);
    assert!(player_local(&mut app, &origin, &sphere, at).0.z < -15.0, "slid through the tunnel");
}

#[test]
fn falling_under_the_sea_respawns_on_the_sphere() {
    let (mut app, sphere, origin, _) = sphere_app(4.0, Vec3::X, 60.0);
    set_player(&mut app, origin.world(sphere.point(Vec3::Z, -60.0)), Vec3::ZERO); // 60 m under sea level, deep inside the test moon
    run(&mut app, 0.1);
    let (pos, _, _) = player(&mut app);
    assert!(origin.body(pos).distance(sphere.surface_point(Vec3::X) + Vec3::X) < 1.0);
    let frame = app.world_mut().query::<&Player>().single(app.world()).unwrap().frame;
    assert!((frame * Vec3::Y).dot(Vec3::X) > 0.9999);
}

#[test]
fn falling_in_water_respawns_at_world_bounds() {
    let mut app = make_app(Tuning::default());
    app.insert_resource(controller::WorldBounds { spawn: Vec3::new(5.0, 30.0, -5.0), kill_altitude: 10.0 });
    set_player(&mut app, Vec3::new(50.0, 9.0, 50.0), Vec3::new(3.0, -5.0, 0.0));
    run(&mut app, 0.1);
    let (pos, vel, state) = player(&mut app);
    assert!((pos.xz() - Vec2::new(5.0, -5.0)).length() < 0.5 && pos.y > 25.0, "respawned at spawn, got {pos}");
    // Reset to zero, then a few ticks of gravity at the spawn point.
    assert!(vel.xz().length() < 0.01 && vel.y <= 0.0 && vel.y > -3.0, "velocity reset, got {vel}");
    assert_eq!(state, MoveState::Air);
}

// --- Terrain streaming ---

fn streaming_app(workers: usize) -> (App, Arc<Sphere>, Origin) {
    let (mut app, sphere, origin, _) = sphere_app(4.0, Vec3::X, 0.0);
    app.world_mut().resource_mut::<Tuning>().terrain.workers = workers;
    planet::add_streaming(&mut app);
    (app, sphere, origin)
}

/// Updates until every wanted chunk is built and nothing else remains, then one more frame.
fn settle(app: &mut App) {
    for _ in 0..600 {
        app.update();
        let c = app.world().resource::<planet::Chunks>();
        if c.pending.is_empty() && c.built.keys().copied().collect::<HashSet<_>>() == c.wanted { app.update(); return; }
    }
    panic!("streaming did not converge");
}

fn covered(app: &mut App, dir: Vec3) -> usize { app.world().resource::<planet::Chunks>().built.keys().filter(|n| n.contains(dir)).count() }

#[test]
fn streaming_converges_to_a_tiling_and_never_leaves_holes() {
    let (mut app, sphere, origin) = streaming_app(4);
    settle(&mut app);
    let dirs = random_dirs(500);
    for d in &dirs { assert_eq!(covered(&mut app, *d), 1, "{d}"); }
    assert!(app.world().resource::<planet::Chunks>().built.contains_key(&NodeId::leaf_at(Vec3::X, 5)), "finest under the player");
    for step in 1..=10 {
        let dir = Vec3::new(1.0, 0.0, 0.15 * step as f32).normalize();
        set_player(&mut app, origin.world(sphere.surface_point(dir) + dir), Vec3::ZERO);
        for _ in 0..30 { app.update(); for d in &dirs { assert!(covered(&mut app, *d) >= 1, "hole at {d} during step {step}"); } }
    }
    settle(&mut app);
    for d in &dirs { assert_eq!(covered(&mut app, *d), 1); }
}

#[test]
fn builder_respects_the_worker_cap() {
    for workers in [0usize, 2] {
        let (mut app, _, _) = streaming_app(workers);
        for _ in 0..200 { app.update(); assert!(app.world().resource::<planet::Chunks>().pending.len() <= workers.max(1)); }
    }
}

#[test]
fn rebase_keeps_the_world_together() {
    use crate::abilities::{GrappleState, Hook};
    let (mut app, sphere, origin0) = streaming_app(4);
    settle(&mut app);
    let body_of = |app: &App, id: Entity| app.world().resource::<Origin>().body(app.world().get::<Transform>(id).unwrap().translation);
    // Beside the player, not on their head, so it is at rest before the walk.
    let crate_id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin0.world(sphere.surface_point(Vec3::X) + Vec3::X * 3.0 - Vec3::Z * 6.0)))).id();
    let block_id = app.world_mut().spawn((RigidBody::Static, Collider::cuboid(2.0, 2.0, 2.0), Transform::from_translation(origin0.world(sphere.surface_point(Vec3::X) + Vec3::Z * 6.0)))).id();
    run(&mut app, 2.0);
    let (crate_before, block_before) = (body_of(&app, crate_id), body_of(&app, block_id));
    // Teleport-walk 2.5 km in 100 m hops; the crate and block fall out of the bubble and freeze where they are.
    // The grapple lets go past 1.5x its 30 m range, so each hop hooks afresh 11 m over the player's head.
    let (mut target, mut anchor) = (Vec3::ZERO, Vec3::ZERO);
    for i in 1..=25 {
        let dir = Quat::from_rotation_y(-(i as f32) * 100.0 / 2000.0) * Vec3::X;
        target = sphere.surface_point(dir) + dir;
        let o = *app.world().resource::<Origin>();
        set_player(&mut app, o.world(target), Vec3::ZERO);
        anchor = target + dir * 12.0;
        app.world_mut().resource_mut::<GrappleState>().hook = Some(Hook { anchor, rope: 12.0 });
        app.update();
        assert_eq!(app.world().resource::<GrappleState>().hook.map(|h| h.anchor), Some(anchor), "hop {i}: hook held, body-coordinate anchor untouched");
        // The rebase lands after the controller has set `prev_pos`, so `Player::shift` must move it too.
        let p = app.world_mut().query::<(&Player, &Transform)>().single(app.world()).unwrap();
        assert!(p.0.prev_pos.distance(p.1.translation) < 2.0, "hop {i}: no camera jump");
    }
    let o = *app.world().resource::<Origin>();
    assert_ne!(o.offset, origin0.offset, "a rebase happened");
    let (pos, _, _) = player(&mut app);
    assert!(pos.length() < 2100.0, "the player is near the new origin");
    assert!(o.body(pos).distance(target) < 0.5, "player body coordinates survived the shift");
    assert!(body_of(&app, crate_id).distance(crate_before) < 1e-3 && body_of(&app, block_id).distance(block_before) < 1e-3);
    assert_eq!(app.world().resource::<GrappleState>().hook.map(|h| h.anchor), Some(anchor), "body-coordinate anchor untouched");
    let p = app.world_mut().query::<(&Player, &Transform)>().single(app.world()).unwrap();
    assert!(p.0.prev_pos.distance(p.1.translation) < 2.0, "no camera jump");

    // Mid-swing: no more teleports, the same hook, the player moving at 6 m/s along the ground,
    // and a rebase forced on the first of three ticks (any step under their distance from the
    // origin will do; the next ticks go back to the default).
    let pos = player(&mut app).0;
    assert!(pos.abs().max_element() > 36.0, "far enough from the origin for the forced rebase to move it");
    let frame = app.world_mut().query::<&Player>().single(app.world()).unwrap().frame;
    app.world_mut().query::<&mut Player>().single_mut(app.world_mut()).unwrap().velocity = frame * Vec3::NEG_Z * 6.0;
    let default_step = app.world().resource::<Tuning>().terrain.origin_step;
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = 1.0;
    let mut moved = 0.0;
    for i in 0..3 {
        let (before, o_before) = (player(&mut app), *app.world().resource::<Origin>());
        app.update();
        app.world_mut().resource_mut::<Tuning>().terrain.origin_step = default_step;
        let o_after = *app.world().resource::<Origin>();
        assert_eq!(o_after.offset != o_before.offset, i == 0, "tick {i}: the rebase lands on the first tick only");
        let after = player(&mut app);
        assert_eq!(app.world().resource::<GrappleState>().hook.map(|h| h.anchor), Some(anchor), "tick {i}: hook held, body-coordinate anchor untouched");
        // Continuous in body coordinates: no further than the faster of the two speeds carries it.
        let step = o_before.body(before.0).distance(o_after.body(after.0));
        let reach = before.1.length().max(after.1.length()) * DT + 0.01;
        assert!(step <= reach, "tick {i}: moved {step} m, at most {reach} m expected");
        let p = app.world_mut().query::<(&Player, &Transform)>().single(app.world()).unwrap();
        assert!(p.0.prev_pos.distance(p.1.translation) <= reach, "tick {i}: no camera jump");
        moved += step;
    }
    assert!(moved > 0.1, "the swing went on: {moved} m");
}

/// Puts the player about 1 km from the world origin on settled streamed ground, then walks them
/// straight away from the origin for 2 s with `terrain.origin_step` set to rebase (or not) about
/// 5 m into the walk. Returns each tick's body position and state, and the ticks that rebased.
fn walk_on_streamed_ground(rebase: bool) -> (Vec<(Vec3, MoveState)>, Vec<usize>) {
    let (mut app, sphere, _) = streaming_app(4);
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = f32::INFINITY;
    settle(&mut app);
    let dir = Quat::from_rotation_y(-0.5) * Vec3::X;
    let o = *app.world().resource::<Origin>();
    set_player(&mut app, o.world(sphere.surface_point(dir) + dir), Vec3::ZERO);
    settle(&mut app);
    run(&mut app, 1.0);
    let (pos, _, state) = player(&mut app);
    assert_eq!(state, MoveState::Ground, "landed before the walk");
    // Face straight away from the world origin, in the player's frame.
    let frame = app.world_mut().query::<&Player>().single(app.world()).unwrap().frame;
    let away = frame.inverse() * pos.normalize();
    app.world_mut().resource_mut::<ViewAngles>().yaw = (-away.x).atan2(-away.z);
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = if rebase { pos.length() + 5.0 } else { f32::INFINITY };
    input(&mut app).movement = Vec2::Y;
    let (mut ticks, mut rebases) = (Vec::new(), Vec::new());
    for i in 0..(2.0 / DT).round() as usize {
        let before = app.world().resource::<Origin>().offset;
        app.update();
        let o = *app.world().resource::<Origin>();
        if o.offset != before { rebases.push(i); }
        let (pos, _, state) = player(&mut app);
        ticks.push((o.body(pos), state));
    }
    (ticks, rebases)
}

#[test]
fn an_idle_player_far_from_the_origin_stays_put() {
    // Rotating the position into the frame and back each tick is not exact in f32, and the error
    // is biased: 1.5 km out, a player standing still crept tens of centimetres in 10 s.
    let (mut app, sphere, _) = streaming_app(4);
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = f32::INFINITY;
    settle(&mut app);
    // 43 degrees north, about 1.47 km from the world origin at the moon's centre.
    let dir = Quat::from_rotation_z(0.75) * Vec3::X;
    let o = *app.world().resource::<Origin>();
    set_player(&mut app, o.world(sphere.surface_point(dir) + dir), Vec3::ZERO);
    settle(&mut app);
    run(&mut app, 1.0);
    let (start, _, state) = player(&mut app);
    assert_eq!(state, MoveState::Ground, "landed");
    assert!((1400.0..1600.0).contains(&start.length()), "{} m from the origin", start.length());
    let mut worst = 0.0_f32;
    for _ in 0..(10.0 / DT).round() as usize {
        app.update();
        let (pos, _, state) = player(&mut app);
        assert_eq!(state, MoveState::Ground);
        worst = worst.max(pos.distance(start));
    }
    assert!(worst < 1e-3, "an idle player crept {worst} m in 10 s");
}

#[test]
fn walking_across_a_rebase_stays_grounded() {
    // A ~1 km rebase mid-walk: stale collider trees would miss the ground entirely for a tick.
    let (with, rebases) = walk_on_streamed_ground(true);
    let (without, none) = walk_on_streamed_ground(false);
    assert!(rebases.len() == 1 && none.is_empty(), "rebased on ticks {rebases:?}, and {none:?} in the other walk");
    for (i, (_, state)) in with.iter().enumerate() {
        assert_eq!(*state, MoveState::Ground, "tick {i} of the walk");
    }
    // The distance covered over the 21 ticks centred on the rebase. Compared over a window, not
    // the whole walk: after the rebase the other walk stays at 1 km coordinates, where f32
    // rounding alone drifts it about 0.1 mm a tick. A lost tick of motion is 11 cm.
    let r = rebases[0];
    assert!(r > 10 && r + 10 < with.len(), "rebase on tick {r}, mid-walk");
    let covered = |t: &[(Vec3, MoveState)]| t[r - 11].0.distance(t[r + 10].0);
    let (d, d_ref) = (covered(&with), covered(&without));
    assert!(d > 2.0, "walked {d} m around the rebase");
    assert!((d - d_ref).abs() < 0.01, "walked {d} m across the rebase, {d_ref} m without one");
}

#[test]
fn a_teleport_on_the_rebase_tick_survives() {
    let (mut app, sphere, _) = streaming_app(4);
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = 40.0;
    settle(&mut app);
    // A 100 m hop written to the Transform before the frame, past the step: the same frame rebases.
    let dir = Quat::from_rotation_y(-100.0 / 2000.0) * Vec3::X;
    let target = sphere.surface_point(dir) + dir;
    let o = *app.world().resource::<Origin>();
    set_player(&mut app, o.world(target), Vec3::ZERO);
    app.update();
    let o2 = *app.world().resource::<Origin>();
    assert_ne!(o2.offset, o.offset, "the teleport frame rebased");
    let (pos, _, _) = player(&mut app);
    assert!(o2.body(pos).distance(target) < 0.5, "teleport survived the rebase, {} m off", o2.body(pos).distance(target));
}

#[test]
fn only_chunks_inside_the_bubble_are_solid() {
    let (mut app, _, origin) = streaming_app(4);
    settle(&mut app);
    let bubble = app.world().resource::<Tuning>().terrain.bubble;
    let player_body = origin.body(player(&mut app).0);
    let mut q = app.world_mut().query::<(&planet::Chunk, Has<Collider>)>();
    let with_colliders: HashSet<NodeId> = q.iter(app.world()).filter(|(_, solid)| *solid).map(|(c, _)| c.node).collect();
    for (c, solid) in q.iter(app.world()) {
        assert_eq!(solid, quadtree::node_distance(c.node, 2000.0, player_body) <= bubble, "{:?}", c.node);
    }
    assert!(!with_colliders.is_empty());
    assert_eq!(app.world().resource::<planet::Chunks>().solid, with_colliders, "Chunks::solid is exactly the chunks with colliders");
}

#[test]
fn bodies_outside_the_bubble_freeze_and_wake_on_solid_ground() {
    let (mut app, sphere, origin) = streaming_app(4);
    settle(&mut app);
    let far = Vec3::new(1.0, 0.0, 0.35).normalize(); // about 680 m from the player
    let start = sphere.surface_point(far) + far * 20.0;
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(start)))).id();
    run(&mut app, 2.0);
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_some() && app.world().get::<RigidBodyDisabled>(id).is_some());
    assert!(origin.body(app.world().get::<Transform>(id).unwrap().translation).distance(start) < 1e-3, "did not move");
    set_player(&mut app, origin.world(sphere.surface_point(far) + far), Vec3::ZERO);
    settle(&mut app);
    run(&mut app, 6.0);
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_none());
    let height = origin.body(app.world().get::<Transform>(id).unwrap().translation).length() - sphere.surface_point(far).length();
    assert!(height < 15.0, "fell once woken, {height} m up");
}

#[test]
fn a_body_inside_the_bubble_stays_frozen_until_its_ground_is_built() {
    let (mut app, sphere, origin) = streaming_app(4);
    let start = sphere.surface_point(Vec3::X) + Vec3::X * 5.0;
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(start)))).id();
    app.update();
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_some(), "no ground yet");
    settle(&mut app);
    run(&mut app, 4.0);
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_none());
    assert!(origin.body(app.world().get::<Transform>(id).unwrap().translation).length() < start.length() - 2.0, "fell onto the built ground");
}

fn is_held(app: &mut App) -> bool {
    app.world_mut().query_filtered::<(), (With<Player>, With<planet::bubble::Held>)>().iter(app.world()).count() == 1
}

fn is_solid(app: &App, p_body: Vec3) -> bool {
    app.world().resource::<planet::Chunks>().is_solid(p_body, app.world().resource::<planet::Planet>().max_depth)
}

#[test]
fn the_player_hovers_until_the_ground_under_them_is_built() {
    let (mut app, sphere, origin) = streaming_app(4);
    let spawn = origin.body(player(&mut app).0);
    let frames = |app: &mut App| (app.world().resource::<ViewAngles>().frame, app.world_mut().query::<&Player>().single(app.world()).unwrap().frame);
    let (view, frame) = frames(&mut app);
    assert!(view == frame && (frame * Vec3::Y).dot(Vec3::X) > 0.9999, "the view turns with the spawn frame from the start");
    let mut held = 0;
    for _ in 0..600 {
        if is_solid(&app, spawn) { break; }
        app.update();
        assert!(is_held(&mut app), "update {held}: Held while the ground is not solid");
        let (view, frame) = frames(&mut app);
        assert_eq!(view, frame, "update {held}: the view keeps the frame while held");
        assert!(origin.body(player(&mut app).0).distance(spawn) < 0.01, "held in place with no ground");
        held += 1;
    }
    assert!(held >= 1, "the ground was solid before the first update");
    settle(&mut app);
    run(&mut app, 1.0);
    let body = origin.body(player(&mut app).0);
    let ground = app.world().resource::<planet::Chunks>().ground(&sphere, body).point;
    assert!((body.length() - ground.length() - 0.9).abs() < 0.05, "standing on the built ground");
}

#[test]
fn a_held_player_still_resets_and_respawns_after_a_fall() {
    let (mut app, sphere, origin) = streaming_app(4);
    let spawn = app.world().resource::<controller::WorldBounds>().spawn;
    app.update();
    assert!(is_held(&mut app), "no ground under the spawn yet");
    // Moved 50 m while held, over ground that is not built either: still held, and the reset
    // pressed now must bring them back.
    let aside = Quat::from_rotation_y(-50.0 / 2000.0) * Vec3::X;
    set_player(&mut app, origin.world(sphere.surface_point(aside) + aside), Vec3::ZERO);
    app.update();
    assert!(is_held(&mut app) && !is_solid(&app, spawn), "still held, nothing built under the spawn");
    input(&mut app).reset_pressed = true;
    app.update();
    assert!(origin.body(player(&mut app).0).distance(spawn) < 0.01, "a reset while held respawns");
    // Under the kill altitude while held: respawned too.
    set_player(&mut app, origin.world(sphere.point(aside, -60.0)), Vec3::ZERO);
    app.update();
    assert!(origin.body(player(&mut app).0).distance(spawn) < 0.01, "a fall while held respawns");
}

#[test]
fn a_player_high_over_the_ground_is_not_held_and_falls() {
    // 600 m up, the ground under them is outside the 400 m bubble and will never be solid.
    let (mut app, sphere, origin) = streaming_app(4);
    let start = sphere.surface_point(Vec3::X) + Vec3::X * 600.0;
    set_player(&mut app, origin.world(start), Vec3::ZERO);
    for i in 0..(2.0 / DT).round() as usize {
        app.update();
        assert!(!is_held(&mut app), "update {i}: not held");
    }
    // Gravity is 5.8 m/s² that far out: 11.6 m in 2 s.
    let fell = start.length() - origin.body(player(&mut app).0).length();
    assert!(fell > 10.0, "fell {fell} m in 2 s");
}

// --- Health and soldiers ---

fn hit_player(app: &mut App, amount: f32) {
    app.world_mut().resource_mut::<Messages<PlayerHit>>().write(PlayerHit { amount });
}

#[test]
fn player_dies_and_respawns_with_full_health() {
    let mut app = make_app(Tuning::default());
    app.insert_resource(controller::WorldBounds { spawn: Vec3::new(5.0, 1.0, -5.0), kill_altitude: -30.0 });
    set_player(&mut app, Vec3::new(40.0, 1.0, 40.0), Vec3::ZERO);
    hit_player(&mut app, 30.0);
    run(&mut app, 0.1);
    let hp = app.world().resource::<PlayerHealth>().hp;
    assert!((hp - 70.0).abs() < 0.5, "30 damage (and a little bleeding): {hp}");
    hit_player(&mut app, 100.0);
    run(&mut app, 0.1);
    let h = app.world().resource::<PlayerHealth>();
    assert!(!h.alive() && h.hp == 0.0, "dead: {h:?}");
    run(&mut app, 2.2);
    let h = app.world().resource::<PlayerHealth>().clone();
    assert!(h.alive() && h.hp == 100.0, "respawned: {h:?}");
    let (pos, _, _) = player(&mut app);
    assert!((pos.xz() - Vec2::new(5.0, -5.0)).length() < 0.5, "back at spawn, got {pos}");
}

#[test]
fn health_regenerates_to_the_cap_after_a_quiet_spell() {
    let mut app = make_app(Tuning::default());
    // Three small hits: no bleeding, 58 hp.
    for _ in 0..3 {
        hit_player(&mut app, 14.0);
        run(&mut app, 0.1);
    }
    run(&mut app, 3.5);
    let h = app.world().resource::<PlayerHealth>().clone();
    assert!((h.hp - 58.0).abs() < 0.01 && h.bleeding <= 0.0, "no regen yet, no bleeding: {h:?}");
    run(&mut app, 2.0);
    let hp = app.world().resource::<PlayerHealth>().hp;
    assert!((hp - 60.0).abs() < 0.01, "regenerated to the 60% cap, got {hp}");
}

#[test]
fn big_hits_bleed_until_healed() {
    let mut app = make_app(Tuning::default());
    hit_player(&mut app, 30.0);
    run(&mut app, 2.0);
    let h = app.world().resource::<PlayerHealth>().clone();
    assert!(h.bleeding > 0.0 && h.hp < 67.0 && h.hp > 64.0, "bleeding 2 hp/s: {h:?}");
    app.world_mut().resource_mut::<PlayerHealth>().heal();
    let h = app.world().resource::<PlayerHealth>().clone();
    assert!(h.hp == 100.0 && h.bleeding <= 0.0, "healed: {h:?}");
}

// ---------------------------------------------------------------------------
// Vehicles

/// The solar system as `main` runs it, headless: the world, the ship and the player.
fn solar_app() -> App {
    use bevy::render::{RenderPlugin, settings::WgpuSettings};
    let mut app = App::new();
    app.add_plugins((
        DefaultPlugins
            .build()
            .disable::<bevy::winit::WinitPlugin>()
            .set(RenderPlugin { render_creation: WgpuSettings { backends: None, ..default() }.into(), ..default() }),
        PhysicsPlugins::default(),
    ))
    .insert_resource(Time::<Fixed>::from_hz(66.0))
    .insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_secs_f32(DT)))
    .insert_resource(Gravity(Vec3::NEG_Y * Tuning::default().gravity))
    .insert_resource(SaveFile(None))
    .add_plugins((
        crate::boot::BootPlugin,
        crate::tuning::TuningPlugin,
        crate::input::InputPlugin,
        ControllerPlugin,
        crate::camera::CameraPlugin,
        WeaponPlugin,
        crate::viewmodel::ViewModelPlugin,
        HealthPlugin,
        crate::hud::HudPlugin,
        VehiclePlugin,
        SavePlugin,
        solar::SolarPlugin,
    ));
    app.finish();
    app.cleanup();
    app
}

/// The first-person guns must stay hidden for the whole time the player is in a vehicle.
#[test]
fn viewmodel_stays_hidden_while_driving() {
    let mut app = solar_app();
    run(&mut app, 0.5);
    let visible = |app: &mut App| app.world_mut().query_filtered::<&Visibility, With<crate::viewmodel::ViewModel>>().single(app.world()).map(|v| *v != Visibility::Hidden).unwrap();
    assert!(visible(&mut app), "the guns show on foot");
    let vehicle = ship_entity(&mut app);
    let player = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    app.world_mut().entity_mut(player).insert(Driving(vehicle));
    for _ in 0..30 {
        app.update();
        assert!(!visible(&mut app), "the guns showed while driving");
    }
}

// ---------------------------------------------------------------------------
// Saves

#[test]
fn save_round_trips_through_a_file() {
    let path = std::env::temp_dir().join(format!("rust-regime-save-{}.toml", std::process::id()));
    let file = SaveFile(Some(path.clone()));
    let s = Save { banked: 1234, ..default() };
    file.write(&s);
    assert_eq!(file.load(), s);
    std::fs::remove_file(&path).ok();
    assert_eq!(file.load(), Save::default(), "missing file is a fresh save");
}

// ---------------------------------------------------------------------------
// Double jump and grapple

#[test]
fn double_jump_once_per_flight() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::ZERO);
    run(&mut app, 0.3); // land
    input(&mut app).jump_pressed = true;
    run(&mut app, 0.25);
    let (_, v1, state) = player(&mut app);
    assert_eq!(state, MoveState::Air);
    // Second press in the air: a fresh hop.
    input(&mut app).jump_pressed = true;
    app.update();
    let (_, v2, _) = player(&mut app);
    assert!(v2.y > v1.y + 2.0, "air jump adds height {v1} -> {v2}");
    // Third press does nothing until we land again.
    run(&mut app, 0.2);
    let (_, before, _) = player(&mut app);
    input(&mut app).jump_pressed = true;
    app.update();
    let (_, after, _) = player(&mut app);
    assert!(after.y < before.y, "no third jump {before} -> {after}");
    run(&mut app, 1.5);
    assert_eq!(player(&mut app).2, MoveState::Ground);
    input(&mut app).jump_pressed = true;
    run(&mut app, 0.2);
    input(&mut app).jump_pressed = true;
    app.update();
    assert!(player(&mut app).1.y > 5.0, "air jump is back after landing");
}

#[test]
fn air_jump_redirects_momentum() {
    let t = Tuning::default();
    let v = controller::air_jump_velocity(Vec3::new(0.0, -2.0, -8.0), Vec3::X, &t);
    assert!((v.y - t.air_jump_speed).abs() < 1e-5);
    assert!(v.x > 4.0 && v.z > -5.0, "bent toward +x: {v}");
    assert!((v.xz().length() - 8.0).abs() < 1e-4, "speed kept: {v}");
}

#[test]
fn grapple_pulls_toward_the_anchor_and_lets_go() {
    use crate::abilities::GrappleState;
    let mut app = make_app(Tuning::default());
    // A tall wall 15 m ahead; look up at it so the pull lifts us off the ground.
    wall(&mut app, Vec3::new(10.0, 20.0, 1.0), Vec3::new(0.0, 10.0, -15.0));
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::ZERO);
    app.world_mut().resource_mut::<ViewAngles>().pitch = 0.45;
    run(&mut app, 0.3);
    input(&mut app).ability_pressed = true;
    app.update();
    let state = app.world().resource::<GrappleState>();
    assert!(state.enabled, "pilot class has the grapple");
    let hook = state.hook.expect("hooked the wall");
    assert!((hook.anchor.z - -14.5).abs() < 0.2, "anchor on the wall face {}", hook.anchor);
    run(&mut app, 0.6);
    let (pos, vel, _) = player(&mut app);
    assert!(pos.z < -3.0 && vel.z < -8.0 && pos.y > 2.0, "pulled up toward the wall: {pos} {vel}");
    let power = app.world().resource::<GrappleState>().power;
    assert!(power < Tuning::default().grapple.power_max, "pulling uses power");
    // Press again: let go, keep the speed.
    input(&mut app).ability_pressed = true;
    app.update();
    assert!(app.world().resource::<GrappleState>().hook.is_none());
    let (_, after, state) = player(&mut app);
    assert_eq!(state, MoveState::Air);
    assert!(after.z < -8.0, "speed kept after release {after}");
    run(&mut app, 2.0);
    assert!(app.world().resource::<GrappleState>().power > power, "power refills");
}

#[test]
fn grapple_needs_the_class_and_a_target_in_range() {
    use crate::abilities::{Class, GrappleState};
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 0.95, 0.0), Vec3::ZERO);
    run(&mut app, 0.3);
    // Nothing within range straight ahead: no hook.
    input(&mut app).ability_pressed = true;
    app.update();
    assert!(app.world().resource::<GrappleState>().hook.is_none());
    // A grunt has no grapple.
    let mut app = build_app(Tuning::default());
    app.insert_resource(Class("grunt".into()));
    app.finish();
    app.update();
    assert!(!app.world().resource::<GrappleState>().enabled);
}

#[test]
fn bullets_fly_drop_and_slow_then_vanish() {
    use crate::weapon::Bullet;
    let mut app = make_app(Tuning::default());
    select_weapon(&mut app, WeaponKind::Pistol);
    let (pos, _, _) = player(&mut app);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.3);
    let mut q = app.world_mut().query::<(&Bullet, &Transform)>();
    let (b, tf) = q.single(app.world()).expect("one bullet in the air");
    let speed = b.velocity.length();
    assert!(speed < 360.0 && speed > 300.0, "drag slowed it: {speed}");
    assert!(b.velocity.y < -2.0, "gravity pulls it down: {}", b.velocity);
    assert!(tf.translation.z < pos.z - 80.0, "it has travelled: {}", tf.translation);
    run(&mut app, 3.0);
    let mut q = app.world_mut().query::<&Bullet>();
    assert_eq!(q.iter(app.world()).count(), 0, "gone after three seconds");
}

#[test]
fn recoil_kicks_the_view_up_then_settles_back() {
    let mut app = make_app(Tuning::default());
    select_weapon(&mut app, WeaponKind::Pistol);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.06);
    let peak = app.world().resource::<ViewAngles>().pitch;
    assert!(peak > 0.01, "kicked up: {peak}");
    run(&mut app, 1.5);
    let rest = app.world().resource::<ViewAngles>().pitch;
    assert!(rest < peak * 0.5 && rest > 0.0, "most of it came back: {rest} of {peak}");
}

#[test]
fn aiming_down_sights_settles_and_tightens() {
    let mut app = make_app(Tuning::default());
    select_weapon(&mut app, WeaponKind::Rifle);
    input(&mut app).aim_held = true;
    run(&mut app, 0.6);
    assert!(app.world().resource::<crate::weapon::Aim>().level > 0.95);
    input(&mut app).aim_held = false;
    run(&mut app, 0.6);
    assert!(app.world().resource::<crate::weapon::Aim>().level < 0.05);
}

// ------------------------------------------------------------------------------------ menus

/// The game's input plugin on bare devices (Bevy's own input plugin would clear a button the test
/// pressed by hand), so taps and pad presses reach `input::gather` and the menu.
fn with_input_devices(app: &mut App) {
    app.add_plugins(crate::input::InputPlugin)
        .init_resource::<ButtonInput<KeyCode>>()
        .init_resource::<ButtonInput<MouseButton>>()
        .init_resource::<bevy::input::mouse::AccumulatedMouseMotion>()
        .init_resource::<bevy::input::mouse::AccumulatedMouseScroll>()
        .add_message::<bevy::input::gamepad::GamepadRumbleRequest>();
}

/// Press and release a key over two frames, like a real tap.
fn tap(app: &mut App, key: KeyCode) {
    app.world_mut().resource_mut::<ButtonInput<KeyCode>>().press(key);
    app.update();
    let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
    keys.release(key);
    keys.clear();
    app.update();
}

#[test]
fn menus_stop_time_and_esc_pauses() {
    use crate::menu::{MenuPlugin, Screen};
    let mut app = build_app(Tuning::default());
    app.add_plugins((crate::gunsmith::GunsmithPlugin, MenuPlugin));
    with_input_devices(&mut app);
    app.finish();
    app.update();
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Title);
    run(&mut app, 1.0);
    assert!(app.world().resource::<Time<Virtual>>().is_paused(), "the title screen holds the clock");
    let (_, _, state) = player(&mut app);
    assert_ne!(state, MoveState::Ground, "nothing moved: the player has not even landed");

    // Enter: PLAY is the first row.
    tap(&mut app, KeyCode::Enter);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    run(&mut app, 1.0);
    assert!(!app.world().resource::<Time<Virtual>>().is_paused());
    assert_eq!(player(&mut app).2, MoveState::Ground, "time runs again and the player lands");

    // Esc pauses, Esc again resumes.
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Paused);
    assert!(app.world().resource::<Time<Virtual>>().is_paused());
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
}

/// Press and release a gamepad button over two frames.
fn pad_tap(app: &mut App, pad: Entity, button: GamepadButton) {
    app.world_mut().get_mut::<Gamepad>(pad).unwrap().digital_mut().press(button);
    app.update();
    let mut g = app.world_mut().get_mut::<Gamepad>(pad).unwrap();
    g.digital_mut().release(button);
    g.digital_mut().clear();
    app.update();
}

#[test]
fn pad_mappings_join_the_users_sdl_config() {
    // SAFETY: the only test that touches this variable.
    unsafe { std::env::set_var("SDL_GAMECONTROLLERCONFIG", "deadbeef,Test Pad,a:b0,platform:Linux,") };
    crate::input::install_pad_mappings();
    let all = std::env::var("SDL_GAMECONTROLLERCONFIG").unwrap();
    assert!(all.starts_with("deadbeef,Test Pad"), "the user's mapping comes first");
    assert!(all.contains("\n05000000c82d00001260000001000000,8BitDo Ultimate 2,"), "Ultimate 2 over Bluetooth is listed on its own line");
    assert!(all.lines().all(|l| l.is_empty() || l.ends_with("platform:Linux,") || l.ends_with("platform:Windows,")), "every line names a platform");
}

#[test]
fn gamepad_b_crouches_in_game_and_only_start_pauses() {
    use crate::menu::{MenuPlugin, Screen};
    let mut app = build_app(Tuning::default());
    app.add_plugins((crate::gunsmith::GunsmithPlugin, MenuPlugin));
    with_input_devices(&mut app);
    app.finish();
    app.update();
    let pad = app.world_mut().spawn(Gamepad::default()).id();

    // A picks PLAY on the title screen.
    pad_tap(&mut app, pad, GamepadButton::South);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    run(&mut app, 1.0);

    // B in the game crouches and leaves the menu closed.
    app.world_mut().get_mut::<Gamepad>(pad).unwrap().digital_mut().press(GamepadButton::East);
    app.update();
    assert!(input(&mut app).crouch_held, "B crouches");
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing, "B must not pause the game");
    let mut g = app.world_mut().get_mut::<Gamepad>(pad).unwrap();
    g.digital_mut().release(GamepadButton::East);
    g.digital_mut().clear();
    app.update();

    // Start pauses, B backs out of the pause menu.
    pad_tap(&mut app, pad, GamepadButton::Start);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Paused);
    pad_tap(&mut app, pad, GamepadButton::East);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
}

#[test]
fn gunsmith_parts_change_the_gun_and_persist() {
    use crate::gunsmith::{Loadout, PARTS, SLOTS};
    let t = Tuning::default();
    let mut loadout = Loadout::default();
    assert_eq!(loadout.gun(WeaponKind::Rifle, &t.rifle).spread_degrees, t.rifle.spread_degrees, "bare gun is the tuning");
    loadout.cycle(WeaponKind::Rifle, 1, 2); // suppressor
    let gun = loadout.gun(WeaponKind::Rifle, &t.rifle);
    assert!(gun.velocity < t.rifle.velocity && gun.recoil_up < t.rifle.recoil_up);
    assert_eq!(loadout.gun(WeaponKind::Pistol, &t.pistol).velocity, t.pistol.velocity, "other guns untouched");
    loadout.cycle_tune(WeaponKind::Rifle, 1, 9);
    assert_eq!(loadout.tuning(WeaponKind::Rifle, 1), 4, "tuning clamps");
    let tuned = loadout.gun(WeaponKind::Rifle, &t.rifle);
    assert!(tuned.recoil_up < gun.recoil_up && tuned.velocity < gun.velocity, "muzzle tuned toward control trades velocity");
    loadout.cycle(WeaponKind::Rifle, 1, 1);
    assert_eq!(loadout.part(WeaponKind::Rifle, 1), 0, "wraps back to bare");
    assert_eq!(loadout.gun(WeaponKind::Rifle, &t.rifle).velocity, t.rifle.velocity, "a bare slot ignores its tuning");
    for slot in 0..SLOTS.len() {
        assert_eq!(PARTS[slot].len(), 3);
    }
    let save = Save { loadout: Some(loadout.clone()), ..default() };
    let text = toml::to_string(&save).unwrap();
    let back: Save = toml::from_str(&text).unwrap();
    assert_eq!(back.loadout, Some(loadout));
}

/// A save with the starter kit, as the solar system hands out: the Warden, bare, and the knife.
fn starter_kit(app: &mut App) {
    let slot = |k: WeaponKind| crate::weapon::WEAPONS.iter().position(|w| *w == k).unwrap();
    crate::quartermaster::grant(&mut app.world_mut().resource_mut::<Save>(), WeaponKind::Revolver);
    let mut a = app.world_mut().resource_mut::<Arsenal>();
    a.current = slot(WeaponKind::Revolver);
    a.last = crate::weapon::KNIFE;
}

#[test]
fn only_owned_weapons_can_be_drawn_and_x_toggles_the_knife() {
    let slot = |k: WeaponKind| crate::weapon::WEAPONS.iter().position(|w| *w == k).unwrap();
    let mut app = make_app(Tuning::default());
    starter_kit(&mut app);
    for number in [slot(WeaponKind::Rifle), slot(WeaponKind::RocketLauncher), slot(WeaponKind::Pistol)] {
        input(&mut app).weapon_select = Some(number);
        run(&mut app, 0.1);
        assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Revolver, "slot {number} was never sold to you");
    }
    input(&mut app).weapon_select = Some(crate::weapon::KNIFE);
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Knife);
    input(&mut app).weapon_select = Some(crate::weapon::KNIFE);
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Revolver, "the same key puts it away");
    // Scrolling passes over the rest: the Warden, the knife, round again.
    input(&mut app).weapon_step = 1;
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Knife);
    input(&mut app).weapon_step = 1;
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Revolver);
    // Bought, it can be drawn.
    app.world_mut().resource_mut::<Save>().weapons.push("rifle".into());
    input(&mut app).weapon_select = Some(slot(WeaponKind::Rifle));
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Rifle);
}

#[test]
fn recoil_follows_a_fixed_pattern_that_climbs_then_resets() {
    use crate::weapon::recoil_pattern;
    let first = recoil_pattern(1, 0);
    assert_eq!(first, (1.0, 0.0), "a burst starts straight up");
    assert_eq!(recoil_pattern(1, 7), recoil_pattern(1, 7), "same every burst");
    let ceiling = recoil_pattern(1, 60).0;
    assert!(ceiling > 1.5 && ceiling < 1.7, "climb settles near 1.6: {ceiling}");
    assert!((1..12).map(|n| recoil_pattern(1, n).0).collect::<Vec<_>>().windows(2).all(|w| w[1] >= w[0]), "climb never falls");
    assert_ne!(recoil_pattern(1, 6).1, recoil_pattern(2, 6).1, "each gun drifts differently");
    // In the game a rifle burst kicks harder at the end than at the start, and rests after a pause.
    let mut app = make_app(Tuning::default());
    select_weapon(&mut app, WeaponKind::Rifle);
    input(&mut app).fire_held = true;
    run(&mut app, 0.5);
    assert!(app.world().resource::<crate::weapon::Recoil>().streak > 3);
    input(&mut app).fire_held = false;
    run(&mut app, 0.6);
    input(&mut app).fire_held = true;
    run(&mut app, 0.03);
    assert!(app.world().resource::<crate::weapon::Recoil>().streak <= 2, "the pattern restarts after a pause");
}

#[test]
fn magazines_run_dry_and_reload() {
    let mut app = make_app(Tuning::default());
    let t = Tuning::default();
    select_weapon(&mut app, WeaponKind::Revolver);
    for _ in 0..t.revolver.mag {
        input(&mut app).fire_pressed = true;
        run(&mut app, t.revolver.cooldown + 0.05);
    }
    let a = app.world().resource::<Arsenal>();
    assert_eq!(a.shots, t.revolver.mag, "six shots from a six-shooter");
    assert!(a.reload > 0.0, "an empty gun reloads itself");
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<Arsenal>().shots, t.revolver.mag, "no shots while reloading");
    run(&mut app, t.revolver.reload);
    assert_eq!(app.world().resource::<Arsenal>().rounds(&t), Some((t.revolver.mag, t.revolver.mag)));
    // R tops up a part-used magazine; swapping away cancels a reload.
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.6);
    input(&mut app).reload_pressed = true;
    run(&mut app, 0.1);
    assert!(app.world().resource::<Arsenal>().reload > 0.0, "R starts a reload");
    select_weapon(&mut app, WeaponKind::Fist);
    assert_eq!(app.world().resource::<Arsenal>().reload, 0.0);
    assert_eq!(app.world().resource::<Arsenal>().rounds(&t), None, "the fist has no magazine");
}

#[test]
fn power_fist_launches_off_a_wall() {
    let mut app = make_app(Tuning::default());
    wall(&mut app, Vec3::new(6.0, 4.0, 0.5), controller::SPAWN + Vec3::new(0.0, 0.0, -1.8));
    run(&mut app, 0.5);
    select_weapon(&mut app, WeaponKind::Fist);
    input(&mut app).fire_held = true;
    run(&mut app, 0.05);
    input(&mut app).fire_held = false;
    let (_, vel, _) = player(&mut app);
    assert!(vel.z > 6.0, "punching the wall throws you back: {vel}");
}

#[test]
fn harpoon_yanks_you_to_a_wall() {
    let mut app = make_app(Tuning::default());
    wall(&mut app, Vec3::new(10.0, 10.0, 0.5), controller::SPAWN + Vec3::new(0.0, 0.0, -20.0));
    run(&mut app, 0.5);
    select_weapon(&mut app, WeaponKind::Harpoon);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.4);
    let (_, vel, _) = player(&mut app);
    assert!(vel.z < -8.0, "the spear sticks and pulls you toward it: {vel}");
    run(&mut app, 0.2);
    assert!(app.world().resource::<Arsenal>().reload > 0.0, "one spear, then a reload");
}

#[test]
fn grenades_bounce_then_burst_and_knock_you_up() {
    let mut app = make_app(Tuning::default());
    run(&mut app, 0.5);
    select_weapon(&mut app, WeaponKind::Grenade);
    // Straight down at your feet: it bounces about, then bursts on the fuse close by.
    app.world_mut().resource_mut::<ViewAngles>().pitch = -1.5;
    input(&mut app).fire_pressed = true;
    let fuse = Tuning::default().grenade.fuse;
    run(&mut app, fuse - 0.3);
    let (_, vel, _) = player(&mut app);
    assert!(vel.y.abs() < 1.0, "no burst before the fuse: {vel}");
    run(&mut app, 0.4);
    let (_, vel, _) = player(&mut app);
    assert!(vel.y > 1.5 && vel.length() > 4.0, "the burst throws you: {vel}");
}

#[test]
fn old_saves_keep_their_gunsmith_parts() {
    use crate::gunsmith::Loadout;
    // A save from before the new weapons: four weapons' worth of parts.
    let text = "parts = [[0, 0, 0, 0], [2, 1, 0, 0], [0, 0, 0, 0], [1, 0, 0, 0]]\ntune = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]\n";
    let mut l: Loadout = toml::from_str(text).unwrap();
    assert_eq!(l.part(WeaponKind::Rifle, 0), 2);
    assert_eq!(l.part(WeaponKind::Pistol, 0), 1);
    assert_eq!(l.part(WeaponKind::Dmr, 0), 0, "new guns start bare");
    l.cycle(WeaponKind::Dmr, 0, 2);
    assert_eq!(l.part(WeaponKind::Dmr, 0), 2);
    assert_eq!(l.part(WeaponKind::Rifle, 0), 2, "growing the list keeps the old parts");
}

/// Every weapon's model is in the assets with the rig the viewmodel drives: the five clips, a
/// muzzle on everything that shoots, and the gunsmith part meshes on the guns.
#[test]
fn weapon_models_carry_their_rigs() {
    for kind in crate::weapon::WEAPONS {
        let path = format!("assets/models/weapons/{}.glb", kind.id());
        let Ok(bytes) = std::fs::read(&path) else { panic!("missing {path}") };
        let len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let json = std::str::from_utf8(&bytes[20..20 + len]).unwrap();
        let has = |name: &str| json.contains(&format!("\"name\":\"{name}\""));
        for clip in ["idle", "fire", "reload", "draw", "inspect"] {
            assert!(has(clip), "{path} has no {clip} clip");
        }
        assert!(has("root"), "{path} has no root bone");
        assert!(has("muzzle"), "{path} has no muzzle socket");
        if crate::gunsmith::customizable(kind) {
            for slot in crate::gunsmith::MESHES {
                for part in &slot[1..] {
                    assert!(has(part), "{path} has no {part}");
                }
            }
            assert!(has("optic"), "{path} has no optic socket for aiming");
        }
    }
}

fn camera_and_eye(app: &mut App) -> (Vec3, Vec3) {
    let tuning = app.world().resource::<Tuning>().clone();
    let mut q = app.world_mut().query::<(&Player, &Transform)>();
    let (p, tf) = q.single(app.world()).unwrap();
    let eye = tf.translation + Vec3::Y * p.eye_offset(&tuning);
    let mut q = app.world_mut().query_filtered::<&Transform, With<crate::camera::PlayerCamera>>();
    (q.single(app.world()).unwrap().translation, eye)
}

#[test]
fn third_person_camera_sits_over_the_shoulder_and_stops_at_walls() {
    let mut tuning = Tuning::default();
    tuning.third_person = true;
    let mut app = build_app(tuning.clone());
    app.add_plugins(crate::camera::CameraPlugin);
    app.finish();
    app.update();
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    run(&mut app, 1.0);
    // Yaw 0 looks down -Z: behind is +Z, the right shoulder +X.
    let (cam, eye) = camera_and_eye(&mut app);
    let off = cam - eye;
    assert!((off.z - tuning.third_person_distance).abs() < 0.1, "camera {off} behind the eyes");
    assert!((off.x - tuning.third_person_shoulder).abs() < 0.1, "camera {off} over the right shoulder");

    // A wall a metre behind: the camera stays in front of it.
    wall(&mut app, Vec3::new(10.0, 10.0, 0.4), Vec3::new(0.0, 2.0, eye.z + 1.2));
    run(&mut app, 0.2);
    let (cam, eye) = camera_and_eye(&mut app);
    assert!(cam.z < eye.z + 1.0 - 0.15, "camera at {cam} went into the wall behind {eye}");

    // First person again: the camera is in the head.
    app.world_mut().resource_mut::<Tuning>().third_person = false;
    run(&mut app, 0.1);
    let (cam, eye) = camera_and_eye(&mut app);
    assert!(cam.distance(eye) < 0.2, "first person camera at {cam}, eyes at {eye}");
}

#[test]
fn t_switches_to_third_person_in_game() {
    use crate::menu::{MenuPlugin, Screen};
    let mut app = build_app(Tuning::default());
    app.add_plugins((crate::gunsmith::GunsmithPlugin, MenuPlugin, crate::camera::CameraPlugin));
    with_input_devices(&mut app);
    app.finish();
    app.update();
    tap(&mut app, KeyCode::Enter);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    run(&mut app, 1.0);
    tap(&mut app, KeyCode::KeyT);
    assert!(app.world().resource::<Tuning>().third_person, "T turns third person on");
    run(&mut app, 1.0);
    let (cam, eye) = camera_and_eye(&mut app);
    assert!(cam.distance(eye) > 2.0, "camera {cam} pulled back from the eyes {eye}");
}

// --- The solar system ---

use crate::solar::{self, orbit::STAR, ship::{Ship, ShipControls}, Solar};

fn system_app() -> App {
    let mut app = build_app(Tuning::default());
    drop_flat_floor(&mut app);
    app.add_plugins(solar::SolarPlugin);
    app.finish();
    app.update();
    app
}

/// The player's ship, the first in `ships.toml`.
fn ship_entity(app: &mut App) -> Entity {
    app.world_mut().query::<(Entity, &Ship)>().iter(app.world()).find(|(_, s)| s.spec == 0).map(|(e, _)| e).unwrap()
}

/// Boards the ship, which must be in reach.
fn board(app: &mut App) {
    input(app).interact_pressed = true;
    run(app, 0.1);
    let ship = ship_entity(app);
    let id = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    assert_eq!(app.world().get::<Driving>(id).map(|d| d.0), Some(ship), "flying the ship");
}

/// The ship's body coordinates on the anchor, and its velocity there.
fn ship_state(app: &mut App) -> (Vec3, Vec3) {
    let ship = ship_entity(app);
    let origin = *app.world().resource::<Origin>();
    let (tf, v) = (app.world().get::<Transform>(ship).unwrap(), app.world().get::<LinearVelocity>(ship).unwrap());
    (origin.body(tf.translation), v.0)
}

/// Puts the ship at body coordinates `p` on the anchor, moving at `v`, with the pilot aboard.
fn put_ship(app: &mut App, p: Vec3, v: Vec3) {
    let ship = ship_entity(app);
    let at = app.world().resource::<Origin>().world(p);
    // Nose along the velocity, so flight assist has no drift to bleed off.
    let rotation = match v.try_normalize() {
        Some(dir) => Transform::default().looking_to(dir, p.normalize().any_orthonormal_vector()).rotation,
        None => app.world().get::<Transform>(ship).unwrap().rotation,
    };
    app.world_mut().entity_mut(ship).insert((Transform::from_translation(at).with_rotation(rotation), Position(at), Rotation(rotation), LinearVelocity(v)));
}

fn inertial(app: &App, p: Vec3, v: Vec3) -> (bevy::math::DVec3, bevy::math::DVec3) {
    let solar = app.world().resource::<Solar>();
    solar.bodies.pose(&solar.anchor, solar.epoch).to_inertial(p.as_dvec3(), v.as_dvec3())
}

#[test]
fn the_system_starts_on_havens_pad_beside_the_ship() {
    let mut app = system_app();
    run(&mut app, 1.5);
    assert_eq!(app.world().resource::<Solar>().anchor, "home");
    let (pos, _, state) = player(&mut app);
    assert_eq!(state, MoveState::Ground, "standing on the pad");
    let ship = ship_entity(&mut app);
    let ship_at = app.world().get::<Transform>(ship).unwrap().translation;
    assert!(pos.distance(ship_at) < solar::ship::BOARD_RADIUS, "in reach of the ship, {} m", pos.distance(ship_at));
    let (p, v) = ship_state(&mut app);
    let sphere = app.world().resource::<Solar>().spheres["home"].clone();
    let surface = Surface::Sphere(sphere.clone());
    assert!(v.length() < 0.2, "the ship rests on the pad, moving {v}");
    assert!(surface.altitude(p) > sphere.height(p.normalize()), "above the ground");
}

#[test]
fn the_ship_takes_its_stick_from_the_input() {
    let mut app = build_app(Tuning::default());
    drop_flat_floor(&mut app);
    app.add_plugins(solar::SolarPlugin).init_resource::<ButtonInput<KeyCode>>();
    app.finish();
    app.update();
    run(&mut app, 1.0);
    board(&mut app);
    // What `input::gather` reads from the bindings (see `controls`): thrust, lift, roll left, boost.
    let mut i = input(&mut app);
    i.thrust = 0.6;
    i.lift = 1.0;
    i.roll = -0.5;
    i.boost = true;
    app.update();
    let ship = ship_entity(&mut app);
    let c = app.world().get::<ShipControls>(ship).unwrap();
    assert!((c.thrust - 0.6).abs() < 1e-5, "thrust: {}", c.thrust);
    assert!((c.lift - 1.0).abs() < 1e-5, "lift: {}", c.lift);
    assert!((c.turn.z + 0.5).abs() < 1e-5, "roll: {}", c.turn.z);
    assert!(c.boost, "A boosts");
}

#[test]
fn the_pilot_cannot_leave_a_ship_at_flying_speed() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    let ship = ship_entity(&mut app);
    app.world_mut().entity_mut(ship).insert(LinearVelocity(Vec3::new(0.0, 0.0, -110.0)));
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    let id = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    assert!(app.world().get::<Driving>(id).is_some(), "still flying at 110 m/s");
}

#[test]
fn the_ship_lifts_off_hovers_and_lands() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    let surface = app.world().resource::<Surface>().clone();
    let start = surface.altitude(ship_state(&mut app).0);
    input(&mut app).lift = 1.0;
    run(&mut app, 2.0);
    let lifted = surface.altitude(ship_state(&mut app).0);
    assert!(lifted - start > 15.0, "lifted {} m in 2 s", lifted - start);
    input(&mut app).lift = 0.0;
    run(&mut app, 2.0);
    let settled = surface.altitude(ship_state(&mut app).0);
    run(&mut app, 2.0);
    let held = surface.altitude(ship_state(&mut app).0);
    assert!((held - settled).abs() < 0.5, "hovers in place with no lift: {settled} then {held}");
    // Sinking brings it back down onto the pad, the last metres slowed to a soft touchdown, and it
    // stays there once the pilot leaves.
    input(&mut app).lift = -1.0;
    let mut touchdown = 0.0f32;
    for _ in 0..120 {
        run(&mut app, 0.1);
        let (p, v) = ship_state(&mut app);
        if surface.altitude(p) - start < 3.0 {
            touchdown = touchdown.max(-v.dot(p.normalize()));
        }
    }
    assert!(touchdown < 4.0, "touched down at {touchdown} m/s");
    input(&mut app).lift = 0.0;
    input(&mut app).interact_pressed = true;
    run(&mut app, 2.0);
    let (p, v) = ship_state(&mut app);
    assert!((surface.altitude(p) - start).abs() < 0.3 && v.length() < 0.3, "back on the pad: {} m off, {v}", surface.altitude(p) - start);
    let id = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    assert!(app.world().get::<Driving>(id).is_none(), "left the ship");
    assert_eq!(player(&mut app).2, MoveState::Ground, "standing beside it");
}

#[test]
fn leaving_havens_sphere_of_influence_hands_off_to_the_star_on_the_same_path() {
    let mut app = system_app();
    run(&mut app, 0.5);
    board(&mut app);
    let soi = app.world().resource::<Solar>().bodies.get("home").soi;
    let (p, v) = (Vec3::new(0.3, 0.8, 0.5).normalize() * (soi - 300.0), Vec3::new(0.3, 0.8, 0.5).normalize() * 600.0);
    put_ship(&mut app, p, v);
    let (before, epoch) = (inertial(&app, p, v), app.world().resource::<Solar>().epoch);
    run(&mut app, 1.0);
    assert_eq!(app.world().resource::<Solar>().anchor, STAR, "out in deep space");
    let (q, w) = ship_state(&mut app);
    let (after, now) = (inertial(&app, q, w), app.world().resource::<Solar>().epoch);
    let expected = before.0 + before.1 * (now - epoch);
    assert!(after.0.distance(expected) < 3.0, "kept to its path: {} m off", after.0.distance(expected));
    assert!(after.1.distance(before.1) < 2.0, "kept its speed: {} m/s off", after.1.distance(before.1));
    assert!(app.world().resource::<planet::Chunks>().built.is_empty(), "no ground streams around the star");
    // The pilot came along, in the seat.
    let (pos, _, _) = player(&mut app);
    let ship = ship_entity(&mut app);
    assert!(pos.distance(app.world().get::<Transform>(ship).unwrap().translation) < 3.0);
}

#[test]
fn flying_down_to_ash_hands_off_to_the_moon_and_streams_its_ground() {
    let mut app = system_app();
    run(&mut app, 0.5);
    board(&mut app);
    // Five kilometres from Ash's centre, at rest over its ground.
    let (radius, over) = (app.world().resource::<Solar>().bodies.get("ash").radius, Vec3::Y * 5000.0);
    let (p, v) = {
        let solar = app.world().resource::<Solar>();
        let (p, v) = solar.bodies.convert("ash", "home", solar.epoch, over.as_dvec3(), bevy::math::DVec3::ZERO);
        (p.as_vec3(), v.as_vec3())
    };
    put_ship(&mut app, p, v);
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Solar>().anchor, "ash");
    let (q, w) = ship_state(&mut app);
    assert!(q.distance(over) < 2.0 && w.length() < 2.0, "still over the same spot, {} m off, moving {w}", q.distance(over));
    run(&mut app, 3.0);
    let chunks = app.world().resource::<planet::Chunks>();
    assert!(!chunks.built.is_empty(), "Ash's ground streams in");
    assert_eq!(app.world().resource::<planet::Planet>().sphere.body.radius, radius);
    let g = app.world().resource::<Surface>().gravity(q, 9.8).length();
    assert!((g - 0.475).abs() < 0.01, "Ash's 1.9 m/s² a quarter as strong at twice its radius: {g}");
}

#[test]
fn a_part_push_on_the_lift_climbs_instead_of_sinking() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    let surface = app.world().resource::<Surface>().clone();
    input(&mut app).lift = 1.0;
    run(&mut app, 1.5);
    input(&mut app).lift = 0.0;
    run(&mut app, 2.0);
    let before = surface.altitude(ship_state(&mut app).0);
    input(&mut app).lift = 0.3;
    run(&mut app, 2.0);
    let after = surface.altitude(ship_state(&mut app).0);
    assert!(after > before + 1.0, "a third of the lift climbs: {before} then {after}");
}

#[test]
fn stop_brings_a_flying_ship_to_a_hover() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    let (p, _) = ship_state(&mut app);
    let up = p.normalize();
    let east = up.any_orthonormal_vector();
    put_ship(&mut app, p + up * 600.0, east * 120.0);
    input(&mut app).stop = true;
    run(&mut app, 5.0);
    let (_, v) = ship_state(&mut app);
    assert!(v.length() < 3.0, "stopped: still {} m/s", v.length());
}

#[test]
fn boost_burns_from_a_tank_that_refills() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    let ship = ship_entity(&mut app);
    input(&mut app).boost = true;
    run(&mut app, 2.0);
    let used = app.world().get::<Ship>(ship).unwrap().boost_used;
    assert!(used > 0.05, "boosting burns the tank: {used}");
    input(&mut app).boost = false;
    run(&mut app, 4.0);
    assert!(app.world().get::<Ship>(ship).unwrap().boost_used < used, "and it refills once let go");
}

#[test]
fn flight_assist_and_the_speed_cap_fade_out_smoothly_with_height() {
    use solar::ship::assist;
    let k = &solar::ship::Ships::load().ship[0];
    assert_eq!(assist(1000.0), 1.0);
    assert_eq!(assist(4000.0), 0.0);
    assert!((assist(3000.0) - 0.5).abs() < 1e-4);
    for h in [2500.0, 3000.0, 3500.0, 5000.0] {
        let (below, above) = (k.speed_cap(h - 1.0, false), k.speed_cap(h + 1.0, false));
        assert!(above >= below && above / below < 1.01, "no jump in the cap at {h} m: {below} to {above}");
    }
}

#[test]
fn boosting_is_capped_by_height_over_the_ground() {
    let ships = solar::ship::Ships::load();
    let speed_cap = |clearance: f32, boost: bool| ships.ship[0].speed_cap(clearance, boost);
    assert_eq!(speed_cap(50.0, false), speed_cap(2000.0, false), "cruising speed near the ground");
    assert!(speed_cap(100_000.0, false).is_infinite(), "coasting in space");
    assert!(speed_cap(100.0, true) < speed_cap(1000.0, true) && speed_cap(1000.0, true) < speed_cap(1.0e6, true));
    assert_eq!(speed_cap(1.0e9, true), 6000.0);
}

// --------------------------------------------------------------------------- the faction ships

#[test]
fn ships_toml_lists_four_ships_with_models_and_matching_rest_heights() {
    let ships = solar::ship::Ships::load();
    assert_eq!(ships.ship.iter().filter(|s| s.boardable()).map(|s| s.id.as_str()).collect::<Vec<_>>(), ["kestrel", "litany", "mule", "vantage"]);
    for s in &ships.ship {
        assert!(std::path::Path::new(&format!("assets/models/ships/{}.glb", s.id)).exists(), "{} has a model", s.id);
        assert!((s.bottom() + s.rest).abs() < 0.05, "{}: collider bottom {} vs rest {}", s.id, s.bottom(), s.rest);
        assert!(s.mass > 0.0 && s.thrust > 0.0 && s.lift > 0.0 && s.cruise > 0.0 && s.boost_max > s.cruise);
    }
    let k = &ships.ship[0];
    assert_eq!((k.mass, k.thrust, k.lift, k.cruise, k.boost_max, k.rest), (6000.0, 30.0, 20.0, 160.0, 6000.0, 1.6));
}

#[test]
fn each_ship_caps_speed_by_its_own_numbers() {
    let ships = solar::ship::Ships::load();
    let (k, v) = (&ships.ship[0], &ships.ship[3]);
    assert_eq!(k.speed_cap(100.0, false), 160.0);
    assert_eq!(v.speed_cap(100.0, false), 190.0);
    assert_eq!(k.speed_cap(1.0e9, true), 6000.0);
    assert_eq!(v.speed_cap(1.0e9, true), 6500.0);
    assert_eq!(k.speed_cap(1.0e5, false), f32::INFINITY);
}

#[test]
fn a_ship_without_assets_still_flies() {
    // Headless apps have no renderer or materials: the Kestrel must still board and move.
    let mut app = system_app();
    board(&mut app);
    let (p0, _) = ship_state(&mut app);
    input(&mut app).thrust = 1.0;
    run(&mut app, 2.0);
    let (p1, _) = ship_state(&mut app);
    // Sitting on its skids the pad holds it back, so this checks the thrust is plumbed through, not the number.
    assert!(p0.distance(p1) > 10.0, "moved {} m", p0.distance(p1));
    let ship = ship_entity(&mut app);
    assert_eq!(app.world().get::<Ship>(ship).unwrap().spec, 0);
    assert_eq!(app.world().get::<Mass>(ship).unwrap().0, 6000.0);
}

#[test]
fn leaving_the_ship_uses_its_exit_point() {
    let mut app = system_app();
    board(&mut app);
    run(&mut app, 0.5);
    let ship = ship_entity(&mut app);
    let tf = *app.world().get::<Transform>(ship).unwrap();
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    let stood = app.world_mut().query_filtered::<&Transform, With<Player>>().single(app.world()).unwrap().translation;
    let spec = app.world().resource::<solar::ship::Ships>().ship[0].clone();
    let exit = Vec3::from(spec.exit);
    let expect = tf.translation + tf.rotation * exit;
    assert!(stood.distance(expect) < 1.5, "stood up {} m from the cabin spot", stood.distance(expect));
    run(&mut app, 1.0);
    assert_eq!(player_state(&mut app), MoveState::Ground, "standing on the cabin floor");
    // Walking backwards from the seat's heading goes aft, down the ramp and onto the apron.
    input(&mut app).movement = Vec2::new(0.0, -1.0);
    run(&mut app, 4.0);
    input(&mut app).movement = Vec2::ZERO;
    run(&mut app, 0.5);
    let (pos, _, state) = player(&mut app);
    let local = tf.rotation.inverse() * (pos - tf.translation);
    assert!(local.z > spec.ramp_foot().z + 1.0, "walked out the back: {local}");
    assert!(local.y < spec.cabin[0], "down on the apron, below the cabin floor: {local}");
    assert_eq!(state, MoveState::Ground, "standing on the apron");
}

#[test]
fn four_ships_rest_in_a_row_on_the_apron_without_touching() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let ships = app.world().resource::<solar::ship::Ships>().clone();
    let mut parked: Vec<(usize, Vec3)> = app.world_mut().query::<(&Ship, &Transform)>().iter(app.world()).filter(|(s, _)| ships.ship[s.spec].boardable()).map(|(s, tf)| (s.spec, tf.translation)).collect();
    parked.sort_by_key(|p| p.0);
    assert_eq!(parked.len(), 4);
    let origin = *app.world().resource::<Origin>();
    let pad = app.world().resource::<Solar>().pad;
    let frame = app.world().resource::<Surface>().frame(pad);
    let Surface::Sphere(sphere) = app.world().resource::<Surface>().clone() else { panic!("round world") };
    for (spec, at) in &parked {
        let local = frame.inverse() * (origin.body(*at) - pad);
        let deck = if *spec == 0 { crate::planet::COURSE_DECK } else { solar::berth_deck(&sphere, pad, solar::ship::BERTHS[*spec]) };
        let rest = deck + ships.ship[*spec].rest;
        assert!((local.y - rest).abs() < 2.0, "{} rests at {} (want {})", ships.ship[*spec].id, local.y, rest);
    }
    // Berths along the row never overlap, and no ship's door opens into a neighbour.
    for a in 0..4 {
        for b in 0..4 {
            if a == b {
                continue;
            }
            let (sa, sb) = (&ships.ship[a], &ships.ship[b]);
            let dx = (parked[a].1 - parked[b].1).length();
            assert!(dx > sa.half_width() + sb.half_width(), "{} and {} touch", sa.id, sb.id);
            let foot = (parked[a].1 + frame * sa.ramp_foot()).distance(parked[b].1);
            assert!(foot > sb.half_width() + 2.0, "{}'s ramp lands beside {}", sa.id, sb.id);
        }
    }
}

#[test]
fn respawn_follows_the_last_flown_ship() {
    let mut app = system_app();
    // Walk to the Litany, board it, leave it: the respawn moves to its door.
    let litany = app.world_mut().query::<(Entity, &Ship, &Transform)>().iter(app.world()).find(|(_, s, _)| s.spec == 1).map(|(e, _, tf)| (e, *tf)).unwrap();
    let player = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    let near = litany.1.translation + litany.1.rotation * Vec3::new(-4.0, 0.0, 0.0);
    set_player(&mut app, near, Vec3::ZERO);
    run(&mut app, 0.5);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(app.world().get::<Driving>(player).map(|d| d.0), Some(litany.0), "flying the Litany");
    input(&mut app).interact_pressed = true;
    run(&mut app, 1.0);
    let spawn = app.world().resource::<controller::WorldBounds>().spawn;
    let origin = *app.world().resource::<Origin>();
    let exit = Vec3::from(app.world().resource::<solar::ship::Ships>().ship[1].exit);
    let expect = origin.body(litany.1.translation + litany.1.rotation * exit);
    assert!(spawn.distance(expect) < 3.0, "respawn {} m from the Litany's cabin spot", spawn.distance(expect));
}


#[test]
fn every_cabin_fits_a_standing_player_and_its_ramp_reaches_the_ground() {
    let ships = solar::ship::Ships::load();
    for spec in ships.ship.iter().filter(|s| s.boardable()) {
        let exit = Vec3::from(spec.exit);
        // A 1.8 m, 0.4 m radius capsule standing on the cabin floor: bottom and top sphere centres.
        for p in [exit + Vec3::Y * -0.45, exit, exit + Vec3::Y * 0.45] {
            for b in &spec.collider {
                assert!(!b.touches(p, 0.4), "{}: a standing player at {exit} hits the box at {:?}", spec.id, b.center);
            }
        }
        assert!(exit.y - 0.95 > spec.cabin[0] - 0.05 && exit.y + 0.95 < spec.cabin[1], "{}: exit stands on the floor under the ceiling", spec.id);
        assert!(spec.cabin[1] - spec.cabin[0] >= 2.2, "{}: cabin {} m tall", spec.id, spec.cabin[1] - spec.cabin[0]);
        let foot = spec.ramp_foot();
        assert!((foot.y + spec.rest).abs() < 0.3, "{}: ramp foot at {} vs ground {}", spec.id, foot.y, -spec.rest);
        // The doorway over the hinge is clear for a standing player.
        let door = Vec3::from(spec.ramp) + Vec3::new(0.0, 0.95, -0.5);
        for b in &spec.collider {
            assert!(!b.touches(door, 0.35), "{}: the doorway is blocked by the box at {:?}", spec.id, b.center);
        }
    }
}

#[test]
fn the_four_fighters_are_solid_hulls_with_their_glbs_nodes() {
    use solar::ship::ShipKind;
    let ships = solar::ship::Ships::load();
    let fighters: Vec<_> = ships.ship.iter().filter(|s| s.kind == ShipKind::Fighter).collect();
    assert_eq!(fighters.iter().map(|s| s.id.as_str()).collect::<Vec<_>>(), ["jackal", "sentry", "censer", "welder"]);
    for s in &fighters {
        assert!(!s.boardable(), "{} cannot be boarded", s.id);
        assert_eq!(s.collider.len(), 1, "{}: one box round the hull", s.id);
        assert_eq!((s.ramp_len, s.cabin), (0.0, [0.0; 2]), "{}: no ramp or cabin", s.id);
        // The glb's own nodes: an exhaust for the glow discs and the heat glow at the nose.
        let glb = std::fs::read(format!("assets/models/ships/{}.glb", s.id)).unwrap();
        let text = String::from_utf8_lossy(&glb);
        for node in ["\"exhaust.0\"", "\"heat\"", "\"light.0\""] {
            assert!(text.contains(node), "{} has a {node} node", s.id);
        }
    }
    // `kind` defaults to a cabin ship, and a fighter needs none of the cabin's fields.
    let parsed = solar::ship::Ships::parse(
        "[[ship]]\nid = \"a\"\nname = \"A\"\nmass = 1\nthrust = 1\nlift = 1\nrates = [1, 1, 1]\ncruise = 1\nboost_max = 2\nrest = 1\nseat = [0, 0, 0]\nexit = [0, 0, 0]\ncam = [1, 1]\nengine_r = 1\ncabin = [0, 2]\nramp = [0, 0, 0]\nramp_len = 1\nramp_slope = 1\ncollider = []\n\
         [[ship]]\nid = \"b\"\nname = \"B\"\nkind = \"fighter\"\nmass = 1\nthrust = 1\nlift = 1\nrates = [1, 1, 1]\ncruise = 1\nboost_max = 2\nrest = 1\ncam = [1, 1]\nengine_r = 1\ncollider = [{ center = [0, 0, 0], size = [1, 2, 1] }]\n",
    )
    .unwrap();
    assert_eq!(parsed.ship.iter().map(|s| s.kind).collect::<Vec<_>>(), [ShipKind::Cabin, ShipKind::Fighter]);
}

#[test]
fn a_jackal_is_parked_off_the_apron_and_cannot_be_boarded() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let specs = app.world().resource::<solar::ship::Ships>().clone();
    let fighters: Vec<(Entity, usize, Transform)> = app.world_mut().query::<(Entity, &Ship, &Transform)>().iter(app.world()).filter(|(_, s, _)| !specs.ship[s.spec].boardable()).map(|(e, s, tf)| (e, s.spec, *tf)).collect();
    assert_eq!(fighters.len(), 1, "one parked fighter");
    let (jackal, spec, tf) = fighters[0];
    assert_eq!(specs.ship[spec].id, "jackal");
    assert_eq!(*app.world().get::<RigidBody>(jackal).unwrap(), RigidBody::Static, "parked");
    // Standing on its slab south of the apron, toward the Roost, above the ground.
    let origin = *app.world().resource::<Origin>();
    let Surface::Sphere(sphere) = app.world().resource::<Surface>().clone() else { panic!("round world") };
    let p = origin.body(tf.translation);
    let pad = app.world().resource::<Solar>().pad;
    let local = app.world().resource::<Surface>().frame(pad).inverse() * (p - pad);
    let deck = solar::fighter_deck(&sphere, pad) + specs.ship[spec].rest;
    assert!((local.y - deck).abs() < 0.3, "rests on its slab at {} (want {deck})", local.y);
    assert!(p.length() - sphere.sea_radius() - sphere.height(p.normalize()) > specs.ship[spec].rest, "above the ground");
    assert!(local.z > 40.0, "south of the apron, toward the Roost: {local}");
    // E beside it does nothing: a fighter has no cabin.
    let player = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    set_player(&mut app, tf.translation + tf.rotation * Vec3::new(0.0, 0.0, 4.5), Vec3::ZERO);
    run(&mut app, 0.5);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.2);
    assert!(app.world().get::<Driving>(player).is_none(), "not boarded");
}

#[test]
fn a_parked_ship_is_static_until_boarded() {
    let mut app = system_app();
    run(&mut app, 2.0);
    let ship = ship_entity(&mut app);
    assert_eq!(*app.world().get::<RigidBody>(ship).unwrap(), RigidBody::Static, "parked");
    board(&mut app);
    run(&mut app, 0.2);
    assert_eq!(*app.world().get::<RigidBody>(ship).unwrap(), RigidBody::Dynamic, "woken by its pilot");
    input(&mut app).lift = 1.0;
    run(&mut app, 1.0);
    input(&mut app).lift = -1.0;
    run(&mut app, 4.0);
    input(&mut app).lift = 0.0;
    input(&mut app).interact_pressed = true;
    run(&mut app, 3.0);
    assert_eq!(*app.world().get::<RigidBody>(ship).unwrap(), RigidBody::Static, "parked again after landing");
}

// --------------------------------------------------------------------------- ship combat

use crate::solar::combat::{Faction, Gun, Hull};

#[test]
fn the_shield_takes_damage_first_and_comes_back_after_five_quiet_seconds() {
    let t = crate::tuning::ShipCombat::default();
    let mut hull = Hull::new(100.0, 60.0);
    for _ in 0..5 {
        hull.hit(t.gun_damage, &t);
    }
    assert_eq!((hull.shield, hull.hp), (0.0, 100.0), "five shots take the shield and leave the hull");
    hull.hit(t.gun_damage, &t);
    assert_eq!(hull.hp, 88.0, "the sixth reaches the hull");
    // A hit bigger than the shield left: the shield holds what it can, the hull takes the rest.
    let mut part = Hull::new(40.0, 30.0);
    part.hit(25.0, &t);
    part.hit(25.0, &t);
    assert_eq!((part.shield, part.hp), (0.0, 20.0));
    // Nothing comes back for five seconds after a hit, then it does, up to full and no more.
    for _ in 0..49 {
        hull.tick(0.1, &t);
    }
    assert_eq!(hull.shield, 0.0, "still down 4.9 s after the hit");
    for _ in 0..11 {
        hull.tick(0.1, &t);
    }
    assert!(hull.shield > 0.0 && hull.shield < 60.0, "coming back at 6 s: {}", hull.shield);
    hull.hit(t.gun_damage, &t);
    hull.tick(1.0, &t);
    assert_eq!(hull.shield, 0.0, "a new hit starts the wait again");
    let hp = hull.hp;
    for _ in 0..200 {
        hull.tick(0.1, &t);
    }
    assert_eq!((hull.shield, hull.hp), (60.0, hp), "the shield refills; the hull does not");
}

#[test]
fn every_ship_carries_its_shield_hull_and_faction_from_the_spec_table() {
    let ships = solar::ship::Ships::load();
    let get = |id: &str| ships.ship.iter().find(|s| s.id == id).unwrap();
    for (id, shield, hull, faction) in [("kestrel", 60.0, 100.0, Faction::Deserters), ("jackal", 30.0, 40.0, Faction::Raiders), ("sentry", 50.0, 70.0, Faction::Pmc), ("censer", 50.0, 90.0, Faction::Regime), ("welder", 60.0, 200.0, Faction::Scrappers)] {
        let s = get(id);
        assert_eq!((s.shield, s.hull, s.faction), (shield, hull, faction), "{id}");
        assert_eq!(s.guns.len(), 2, "{id} has two barrels");
    }
    let mut app = system_app();
    run(&mut app, 0.2);
    let kestrel = ship_entity(&mut app);
    let h = *app.world().get::<Hull>(kestrel).unwrap();
    assert_eq!((h.hp, h.shield), (100.0, 60.0));
    assert!(app.world().get::<Gun>(kestrel).is_some(), "the Kestrel has nose guns");
}

/// The parked fighter, and the Kestrel boarded and hanging 600 m over the pad with that fighter
/// `range` metres ahead of its nose.
fn gunnery_range(range: f32) -> (App, Entity) {
    let mut app = system_app();
    run(&mut app, 0.5);
    board(&mut app);
    let (p, _) = ship_state(&mut app);
    put_ship(&mut app, p + p.normalize() * 600.0, Vec3::ZERO);
    run(&mut app, 0.2);
    let specs = app.world().resource::<solar::ship::Ships>().clone();
    let jackal = app.world_mut().query::<(Entity, &Ship)>().iter(app.world()).find(|(_, s)| !specs.ship[s.spec].boardable()).map(|(e, _)| e).unwrap();
    let ship = ship_entity(&mut app);
    let tf = *app.world().get::<Transform>(ship).unwrap();
    let at = tf.translation + tf.rotation * Vec3::NEG_Z * range;
    app.world_mut().entity_mut(jackal).insert((Transform::from_translation(at).with_rotation(tf.rotation), Position(at), Rotation(tf.rotation), RigidBody::Static));
    (app, jackal)
}

/// Holds the left mouse button for `seconds`: the input is read afresh every frame, as in game.
fn hold_fire(app: &mut App, seconds: f32) {
    for _ in 0..(seconds / DT).round() as usize {
        input(app).fire_held = true;
        app.update();
    }
}

#[test]
fn the_fire_button_pulls_the_ships_trigger_not_the_hand_gun() {
    let mut app = system_app();
    run(&mut app, 0.5);
    board(&mut app);
    let shots = app.world().resource::<Arsenal>().shots;
    hold_fire(&mut app, 0.3);
    let ship = ship_entity(&mut app);
    assert!(app.world().get::<ShipControls>(ship).unwrap().fire, "the ship's trigger is held");
    assert_eq!(app.world().resource::<Arsenal>().shots, shots, "the gun in the pilot's hands stays quiet");
    assert!(app.world().get::<Gun>(ship).unwrap().heat > 0.0, "the nose guns fired");
    run(&mut app, 0.1);
    assert!(!app.world().get::<ShipControls>(ship).unwrap().fire, "let go");
}

#[test]
fn nose_guns_wear_down_a_ship_in_range_and_destroy_it() {
    let (mut app, jackal) = gunnery_range(300.0);
    hold_fire(&mut app, 1.0);
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert!(h.shield < 30.0, "hit: shield {} hull {}", h.shield, h.hp);
    hold_fire(&mut app, 3.0);
    run(&mut app, 0.2);
    assert!(app.world().get_entity(jackal).is_err(), "the Jackal is destroyed");
    // Its last shots fly on and are gone past their range.
    run(&mut app, 2.0);
    assert_eq!(app.world_mut().query::<&solar::combat::Projectile>().iter(app.world()).count(), 0);
}

#[test]
fn nose_guns_spare_their_own_side_and_fall_short_past_their_range() {
    let (mut app, jackal) = gunnery_range(300.0);
    app.world_mut().entity_mut(jackal).insert(Faction::Deserters);
    hold_fire(&mut app, 1.0);
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp), (30.0, 40.0), "no friendly fire");
    let (mut app, jackal) = gunnery_range(2300.0);
    hold_fire(&mut app, 1.0);
    run(&mut app, 2.0);
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp), (30.0, 40.0), "2.3 km is out of range");
}

#[test]
fn a_ship_whose_hull_is_gone_is_destroyed() {
    let mut app = system_app();
    run(&mut app, 0.5);
    let specs = app.world().resource::<solar::ship::Ships>().clone();
    let jackal = app.world_mut().query::<(Entity, &Ship)>().iter(app.world()).find(|(_, s)| !specs.ship[s.spec].boardable()).map(|(e, _)| e).unwrap();
    app.world_mut().get_mut::<Hull>(jackal).unwrap().hp = 0.0;
    run(&mut app, 0.1);
    assert!(app.world().get_entity(jackal).is_err(), "gone");
}

// --------------------------------------------------------------------------- the faction bases

#[test]
fn bases_toml_lists_four_bases_on_four_worlds_with_models_and_clear_doorways() {
    let bases = solar::base::Bases::load();
    assert_eq!(bases.base.iter().map(|b| b.id.as_str()).collect::<Vec<_>>(), ["roost", "reliquary", "yard", "outpost"]);
    assert_eq!(bases.base.iter().map(|b| b.body.as_str()).collect::<Vec<_>>(), ["home", "bastion", "cinder", "frost"]);
    let bodies = solar::orbit::Bodies::new(&crate::system::System::load());
    assert_eq!(bases.base.iter().map(|b| b.faction.as_str()).collect::<Vec<_>>(), ["deserters", "regime", "scrappers", "pmc"]);
    for b in &bases.base {
        assert!(bodies.bodies.contains_key(&b.body), "{}: {} is a world", b.id, b.body);
        assert!(std::path::Path::new(&format!("assets/models/bases/{}.glb", b.id)).exists(), "{} has a model", b.id);
        assert!(!b.collider.is_empty() && b.footprint.iter().all(|f| *f > 0.0));
        assert!(b.near_pad.is_some() || b.pad.is_some(), "{}: a pad to land on", b.id);
        // A standing player fits through the door and a metre inside it, with a floor under them.
        let door = Vec3::from(b.door);
        for p in [door, door + Vec3::NEG_Z] {
            for bx in &b.collider {
                assert!(!bx.touches(p, 0.35), "{}: the doorway at {p} is blocked by the box at {:?}", b.id, bx.center);
            }
            assert!(b.floor_under(p, 2.0).is_some(), "{}: no floor under {p}", b.id);
        }
    }
}

#[test]
fn every_base_is_staffed_by_its_own_faction_standing_on_floors_and_has_a_visitor() {
    let bases = solar::base::Bases::load();
    let characters = crate::character::Characters::load();
    let ships = solar::ship::Ships::load();
    for b in &bases.base {
        let own = &characters.faction[&b.faction].characters;
        assert!(b.crew.len() > b.stations.len(), "{}: a keeper per station and someone walking rounds", b.id);
        assert!(b.crew.iter().any(|c| !c.path.is_empty()), "{}: someone walks a round", b.id);
        for c in &b.crew {
            assert!(own.contains(&c.character), "{}: {} is one of the {}", b.id, c.character, b.faction);
            for p in std::iter::once(c.at).chain(c.path.iter().copied()).map(Vec3::from) {
                assert!(b.floor_under(p + Vec3::Y * 0.01, 0.6).is_some(), "{}: {} has no floor under {p}", b.id, c.character);
                for bx in b.collider.iter().filter(|bx| bx.rot == [0.0; 3]) {
                    assert!(!bx.touches(p + Vec3::Y, 0.3), "{}: {} at {p} stands in the box at {:?}", b.id, c.character, bx.center);
                }
            }
        }
        let visitor = b.traffic.as_deref().unwrap_or_else(|| panic!("{}: a ship visits", b.id));
        assert!(ships.ship.iter().any(|s| s.id == visitor), "{}: {visitor} is a ship", b.id);
    }
}

#[test]
fn the_roost_has_its_crew_and_its_visitor_at_start() {
    let mut app = system_app();
    run(&mut app, 0.5);
    let roost = app.world().resource::<solar::base::Bases>().base.iter().find(|b| b.id == "roost").unwrap().clone();
    let crew = app.world_mut().query_filtered::<&ChildOf, With<solar::life::Crew>>().iter(app.world()).map(|c| c.parent()).collect::<Vec<_>>();
    let at_base = crew.iter().filter(|p| app.world().get::<solar::base::Base>(**p).is_some()).count();
    assert_eq!(at_base, roost.crew.len());
    let visitors = app.world_mut().query::<&solar::life::Traffic>().iter(app.world()).count();
    assert_eq!(visitors, 1);
}

#[test]
fn every_world_has_its_own_factions_post_with_a_cache_and_crew_on_floors() {
    let bases = solar::base::Bases::load();
    let posts = solar::post::Posts::load();
    let characters = crate::character::Characters::load();
    assert_eq!(posts.post.iter().map(|p| p.body.as_str()).collect::<Vec<_>>(), ["home", "bastion", "cinder", "frost"]);
    for p in &posts.post {
        let base = bases.base.iter().find(|b| b.body == p.body).unwrap();
        assert_eq!(p.faction, base.faction, "{}: the world's own faction", p.id);
        assert!(std::path::Path::new(&format!("assets/models/posts/{}.glb", p.id)).exists(), "{} has a model", p.id);
        assert_eq!(p.stations.iter().map(|s| s.kind).collect::<Vec<_>>(), [StationKind::Cache]);
        let cache = Vec3::from(p.stations[0].at);
        assert!(p.floor_under(cache, 2.0).is_some(), "{}: a floor under the cache", p.id);
        let own = &characters.faction[&p.faction].characters;
        for c in &p.crew {
            assert!(own.contains(&c.character), "{}: {} is one of the {}", p.id, c.character, p.faction);
            assert!(p.floor_under(Vec3::from(c.at) + Vec3::Y * 0.01, 0.6).is_some(), "{}: {} has a floor", p.id, c.character);
        }
    }
}

#[test]
fn posts_are_scattered_clear_of_the_bases_and_each_other_on_every_world() {
    let app = system_app();
    let solar = app.world().resource::<Solar>();
    let bases = app.world().resource::<solar::base::Bases>();
    for body in ["home", "bastion", "cinder", "frost"] {
        let sphere = solar.spheres[body].clone();
        let clear: Vec<Vec3> = bases.base.iter().filter(|b| b.body == body).map(|b| solar::base::site(b, &sphere, solar.pad).0).collect();
        let sites = solar::post::sites(&sphere, &clear);
        assert!(sites.len() >= 4, "{body}: {} posts", sites.len());
        assert_eq!(sites.iter().map(|s| s.0).collect::<Vec<_>>(), solar::post::sites(&sphere, &clear).iter().map(|s| s.0).collect::<Vec<_>>(), "{body}: the same every time");
        let r = sphere.sea_radius();
        for (i, (a, _)) in sites.iter().enumerate() {
            for c in &clear {
                assert!(a.angle_between(*c) * r >= 399.0, "{body}: post {i} is clear of the base");
            }
            for (b, _) in &sites[i + 1..] {
                assert!(a.angle_between(*b) * r >= 599.0, "{body}: posts apart");
            }
        }
    }
}

#[test]
fn havens_posts_stand_at_start_with_their_crew_and_a_found_one_gets_a_waypoint() {
    let mut app = system_app();
    run(&mut app, 0.5);
    let posts: Vec<solar::post::Post> = app.world_mut().query::<&solar::post::Post>().iter(app.world()).cloned().collect();
    assert!(posts.len() >= 4, "{} posts on Haven", posts.len());
    assert!(posts.iter().all(|p| p.key.starts_with("home.")));
    let crew = app.world_mut().query::<&solar::life::Crew>().iter(app.world()).count();
    let roost = app.world().resource::<solar::base::Bases>().base[0].crew.len();
    let per_post = app.world().resource::<solar::post::Posts>().post[0].crew.len();
    assert_eq!(crew, roost + per_post * posts.len());
}

#[test]
fn a_base_standing_high_over_a_slope_has_a_ramp_down_from_its_door() {
    let app = system_app();
    let solar = app.world().resource::<Solar>();
    let bases = app.world().resource::<solar::base::Bases>();
    let roost = bases.base.iter().find(|b| b.id == "roost").unwrap();
    let sphere = solar.spheres["home"].clone();
    let (ground, frame, deck) = solar::base::site(roost, &sphere, solar.pad);
    let (center, tilt, size) = solar::base::approach(roost, &sphere, ground, frame, deck).expect("the Roost stands over a slope");
    let slope = tilt * Vec3::Z;
    assert!(slope.y < 0.0 && -slope.y / slope.z <= 0.51, "down and walkable: {slope}");
    assert!(size.x >= 6.0, "wide enough to walk up");
    // Its top surface starts at the deck and ends on the ground.
    let top_end = center + tilt * Vec3::new(0.0, size.y / 2.0, -size.z / 2.0);
    let low_end = center + tilt * Vec3::new(0.0, size.y / 2.0, size.z / 2.0);
    assert!(top_end.y >= deck - 0.6, "it meets the deck: {} vs {deck}", top_end.y);
    let here = sphere.height(ground.normalize());
    let under = sphere.height((ground + frame * low_end.with_y(0.0)).normalize()) - here;
    assert!(low_end.y <= under + 1.0, "it reaches the ground: {} vs {under}", low_end.y);
    // And so it stands in the world: from the deck's height down to the ground.
    let mut app = app;
    run(&mut app, 0.2);
    let origin = *app.world().resource::<Origin>();
    let surface = app.world().resource::<Surface>().clone();
    let (ramp, len) = app.world_mut().query::<(&Name, &Transform, &Collider)>().iter(app.world()).find(|(n, _, _)| n.as_str() == "Approach").map(|(_, tf, c)| (*tf, c.shape_scaled().as_cuboid().unwrap().half_extents.z)).expect("the ramp stands");
    let base = app.world_mut().query::<(&Transform, &solar::base::Base)>().iter(app.world()).find(|(_, b)| b.spec == 0).map(|(tf, _)| *tf).unwrap();
    let alt = |p: Vec3| surface.altitude(origin.body(p));
    let near = ramp.translation + ramp.rotation * Vec3::NEG_Z * len;
    let far = ramp.translation + ramp.rotation * Vec3::Z * len;
    assert!(near.distance(base.translation) < far.distance(base.translation), "it runs away from the base");
    assert!(alt(near) > alt(far) + 5.0, "it runs down: {} to {}", alt(near), alt(far));
    assert!((alt(near) - alt(base.translation)).abs() < 2.5, "it starts at the deck: {} vs {}", alt(near), alt(base.translation));
}

/// The base and foundation fixtures standing on the anchor: (base id, how many slabs).
fn standing(app: &mut App) -> (Vec<String>, usize) {
    let specs = app.world().resource::<solar::base::Bases>().clone();
    let ids: Vec<String> = app.world_mut().query::<&solar::base::Base>().iter(app.world()).map(|b| specs.base[b.spec].id.clone()).collect();
    let slabs = app.world_mut().query_filtered::<&Name, With<solar::Fixture>>().iter(app.world()).filter(|n| n.as_str() == "Foundation" || n.as_str() == "Pad").count();
    (ids, slabs)
}

#[test]
fn the_roost_stands_north_of_the_apron_and_bastions_base_replaces_it_after_a_handoff() {
    let mut app = system_app();
    run(&mut app, 0.5);
    let (ids, slabs) = standing(&mut app);
    assert_eq!(ids, ["roost"], "Haven's base");
    assert_eq!(slabs, 2, "Haven's pad and the Roost's foundation");
    let origin = *app.world().resource::<Origin>();
    let pad = app.world().resource::<Solar>().pad;
    let frame = app.world().resource::<Surface>().frame(pad);
    let at = app.world_mut().query::<(&Transform, &solar::base::Base)>().single(app.world()).map(|(tf, _)| tf.translation).unwrap();
    let local = frame.inverse() * (origin.body(at) - pad);
    assert!((local.x - 70.0).abs() < 0.5 && (local.z - 85.0).abs() < 0.5, "south-east of the pad, at {local}");
    assert!(local.y.abs() < 30.0, "on the ground near the pad's height, {}", local.y);
    let (_, base) = app.world_mut().query::<(&Transform, &solar::base::Base)>().single(app.world()).map(|(tf, b)| (*tf, b.spec)).unwrap();
    let door = app.world().resource::<solar::base::Bases>().base[base].door;
    let base_tf = app.world_mut().query::<(&Transform, &solar::base::Base)>().single(app.world()).map(|(tf, _)| *tf).unwrap();
    let door_local = frame.inverse() * (origin.body(base_tf.translation + base_tf.rotation * Vec3::from(door)) - pad);
    assert!(door_local.z < local.z - 3.0, "the door faces the pad: door at z {} vs centre {}", door_local.z, local.z);
    let Surface::Sphere(sphere) = app.world().resource::<Surface>().clone() else { panic!("round world") };
    let ground = sphere.height(origin.body(at).normalize());
    let altitude = app.world().resource::<Surface>().altitude(origin.body(at));
    assert!(altitude > ground && altitude - ground < 15.0, "the deck sits just over the ground: {altitude} vs {ground}");
    // Fly to Bastion: the Roost and the apron go, the Reliquary and its pad stand there.
    board(&mut app);
    let over = Vec3::Y * 8000.0;
    let (p, v) = {
        let solar = app.world().resource::<Solar>();
        let (p, v) = solar.bodies.convert("bastion", "home", solar.epoch, over.as_dvec3(), bevy::math::DVec3::ZERO);
        (p.as_vec3(), v.as_vec3())
    };
    put_ship(&mut app, p, v);
    run(&mut app, 0.3);
    assert_eq!(app.world().resource::<Solar>().anchor, "bastion");
    let (ids, slabs) = standing(&mut app);
    assert_eq!(ids, ["reliquary"], "Bastion's base");
    assert_eq!(slabs, 2, "the Reliquary's foundation and pad");
    assert!(app.world_mut().query_filtered::<&Name, With<solar::Fixture>>().iter(app.world()).all(|n| n.as_str() != "Berth"), "Haven's berths went");
    let base = app.world_mut().query::<(&Transform, &solar::base::Base)>().single(app.world()).map(|(tf, _)| *tf).unwrap();
    let origin = *app.world().resource::<Origin>();
    let Surface::Sphere(sphere) = app.world().resource::<Surface>().clone() else { panic!("round world") };
    let here = origin.body(base.translation);
    let ground = sphere.height(here.normalize());
    let altitude = app.world().resource::<Surface>().altitude(here);
    assert!(altitude > ground && altitude - ground < 20.0, "on Bastion's ground: {altitude} vs {ground}");
    assert!((base.rotation * Vec3::Y).dot(here.normalize()) > 0.999, "stands upright");
}


// ------------------------------------------------------------------------------- waypoints

#[test]
fn every_base_and_the_ship_get_a_waypoint_in_the_faction_colour() {
    let mut app = system_app();
    run(&mut app, 0.2);
    let bases = app.world().resource::<solar::base::Bases>().clone();
    let mut pins: Vec<String> = Vec::new();
    for (target, text) in app.world_mut().query::<(&solar::waypoint::Target, &Children)>().iter(app.world()).map(|(t, c)| (t.clone(), c.to_vec())) {
        match target {
            solar::waypoint::Target::Base(i) => pins.push(bases.base[i].id.clone()),
            solar::waypoint::Target::Ship => pins.push("ship".into()),
            solar::waypoint::Target::Post(_) => pins.push("post".into()),
        }
        assert_eq!(text.len(), 2, "a diamond and a label");
    }
    pins.sort();
    assert_eq!(pins, ["outpost", "reliquary", "roost", "ship", "yard"]);
    // Four factions, four different colours, none of them white (that is the ship's).
    let mut colours: Vec<[u32; 3]> = bases.base.iter().map(|b| b.color.map(|c| (c * 100.0) as u32)).collect();
    colours.sort();
    colours.dedup();
    assert_eq!(colours.len(), 4);
    assert!(bases.base.iter().all(|b| b.color != [1.0; 3]));
}

// ---------------------------------------------------------------------------- base stations

use solar::station::{Blessing, Contract, Station, StationKind, BLESSING_HP};

const UPGRADE_COST: [u32; 3] = [300, 700, 1400];
const TITHE: u32 = 150;

#[test]
fn the_economy_section_in_tuning_toml_matches_the_defaults() {
    let text = std::fs::read_to_string("tuning.toml").unwrap();
    let parsed: Tuning = toml::from_str(&text).unwrap();
    let e = Tuning::default().economy;
    assert_eq!(parsed.economy, e);
    assert_eq!((e.guns["rocket"], e.tune, e.tithe), (1500, UPGRADE_COST, TITHE));
}

#[test]
fn every_base_has_its_station_on_a_floor_clear_of_the_furniture() {
    let bases = solar::base::Bases::load();
    let roles: Vec<(&str, Vec<StationKind>)> = vec![
        ("roost", vec![StationKind::Resupply, StationKind::Locker]),
        ("reliquary", vec![StationKind::Shrine]),
        ("yard", vec![StationKind::Workshop, StationKind::Parts]),
        ("outpost", vec![StationKind::Contracts]),
    ];
    for (id, kinds) in roles {
        let b = bases.base.iter().find(|b| b.id == id).unwrap();
        assert_eq!(b.stations.iter().map(|s| s.kind).collect::<Vec<_>>(), kinds, "{id}'s stations");
        for s in &b.stations {
            let at = Vec3::from(s.at);
            let floor = b.floor_under(at, 2.0).unwrap_or_else(|| panic!("{id}: no floor under {}", s.label));
            assert!((0.8..1.6).contains(&(at.y - floor)), "{id}: {} is {} m over the floor", s.label, at.y - floor);
            // Someone can stand a metre from it, at chest height, in the open.
            let stand = Vec3::new(at.x, floor + 1.0, at.z);
            assert!(b.collider.iter().all(|bx| !bx.touches(stand, 0.2)), "{id}: {} is inside a wall or a counter", s.label);
        }
    }
}

/// Stands the player beside a station of `kind` that the test puts there (so it works on any world).
fn stand_at_station(app: &mut App, kind: StationKind, base: usize) {
    let at = player(app).0;
    let faction = solar::station::faction_of(app.world().resource::<solar::base::Bases>(), base);
    app.world_mut().spawn((Station { base, faction, kind, label: "Test".into() }, GlobalTransform::from_translation(at)));
}

fn press_use(app: &mut App) {
    input(app).interact_pressed = true;
    run(app, 0.1);
}

#[test]
fn the_quartermaster_tops_you_up_for_free_and_uses_the_press_up() {
    let mut app = system_app();
    run(&mut app, 1.0);
    // The real one in the Roost's depot, wherever the base ended up on Haven.
    let at = app.world_mut().query::<(&Station, &GlobalTransform)>().iter(app.world()).find(|(s, _)| s.kind == StationKind::Resupply).map(|(_, g)| g.translation()).expect("the Roost's quartermaster");
    set_player(&mut app, at, Vec3::ZERO);
    app.world_mut().resource_mut::<PlayerHealth>().hp = 20.0;
    app.world_mut().resource_mut::<Arsenal>().spent[0] = 7;
    press_use(&mut app);
    assert_eq!(app.world().resource::<PlayerHealth>().hp, app.world().resource::<PlayerHealth>().max);
    assert_eq!(app.world().resource::<Arsenal>().spent[0], 0, "magazines refilled");
    assert!(app.world().resource::<solar::station::Prompt>().text().contains("Resupplied"));
    let id = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    assert!(app.world().get::<Driving>(id).is_none(), "the same press did not board the ship");
}

#[test]
fn the_tuning_rig_sells_three_levels_for_banked_money() {
    let mut app = system_app();
    run(&mut app, 1.0);
    stand_at_station(&mut app, StationKind::Workshop, 2);
    app.world_mut().resource_mut::<Save>().banked = UPGRADE_COST[0] - 1;
    press_use(&mut app);
    assert_eq!((app.world().resource::<Save>().ship_level, app.world().resource::<Save>().banked), (0, UPGRADE_COST[0] - 1), "too poor");
    let total: u32 = UPGRADE_COST.iter().sum();
    app.world_mut().resource_mut::<Save>().banked = total + 10;
    for level in 1..=3 {
        press_use(&mut app);
        assert_eq!(app.world().resource::<Save>().ship_level, level);
    }
    press_use(&mut app);
    let save = app.world().resource::<Save>();
    assert_eq!((save.ship_level, save.banked), (3, 10), "three levels and no more");
}

#[test]
fn a_tuned_ship_climbs_faster() {
    fn lifted(level: u8) -> f32 {
        let mut app = system_app();
        run(&mut app, 1.0);
        app.world_mut().resource_mut::<Save>().ship_level = level;
        board(&mut app);
        let surface = app.world().resource::<Surface>().clone();
        let start = surface.altitude(ship_state(&mut app).0);
        input(&mut app).lift = 1.0;
        run(&mut app, 2.0);
        surface.altitude(ship_state(&mut app).0) - start
    }
    let (stock, tuned) = (lifted(0), lifted(3));
    assert!(tuned > stock * 1.2, "Mk3 climbs {tuned} m, stock {stock} m in 2 s");
}

/// A courier job for base `to`, from Site Vantage, never due.
fn parcel(to: &str, pay: u32) -> Contract {
    Contract { job: solar::board::Job::Courier { to: to.into() }, from: "outpost".into(), pay, due: None }
}

#[test]
fn a_parcel_taken_from_the_board_pays_at_the_other_bases_door() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let bases = app.world().resource::<solar::base::Bases>().clone();
    // The day's boards are up, one for each base, each with a courier first.
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.board_day, save.boards.len()), (Some(0), 4));
    assert!(save.seed != 0, "the save got its seed");
    let job = save.boards["outpost"][0].clone();
    assert!(job.parcel_for().is_some_and(|to| to != "outpost"));
    let e = Tuning::default().economy;
    assert_eq!(solar::board::take(&mut app.world_mut().resource_mut::<Save>(), "outpost", 0, &e), Ok(job));
    // Carry one to the Roost, the only base on this world, and stand in its doorway: it and any
    // other parcel for the Roost pay; the rest stay aboard.
    {
        let mut save = app.world_mut().resource_mut::<Save>();
        save.contracts = vec![parcel("roost", 250), parcel("yard", 400)];
    }
    let (at, base) = app.world_mut().query::<(&GlobalTransform, &solar::base::Base)>().single(app.world()).map(|(g, b)| (*g, b.spec)).unwrap();
    let door = at.translation() + at.rotation() * Vec3::from(bases.base[base].door);
    set_player(&mut app, door, Vec3::ZERO);
    run(&mut app, 0.2);
    let save = app.world().resource::<Save>();
    assert_eq!((save.banked, save.contracts_done, save.contracts.clone()), (250, 1, vec![parcel("yard", 400)]), "paid on arrival");
}

#[test]
fn the_board_stands_inside_every_bases_door_and_a_day_puts_up_new_boards() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let bases = app.world().resource::<solar::base::Bases>().clone();
    for (i, b) in bases.base.iter().enumerate() {
        let at = Vec3::from(b.door) + solar::base::BOARD_IN;
        assert!(at.distance(Vec3::from(b.door)) < 3.0, "{} board by its door", b.id);
        let _ = i;
    }
    // The Roost is the base on this world: its board station is there.
    let boards = app.world_mut().query::<&Station>().iter(app.world()).filter(|s| s.kind == StationKind::Board).count();
    assert_eq!(boards, 1, "one board on Haven, at the Roost");
    let e = Tuning::default().economy;
    let before = app.world().resource::<Save>().boards.clone();
    {
        let mut save = app.world_mut().resource_mut::<Save>();
        save.contracts = vec![Contract { job: solar::board::Job::Courier { to: "yard".into() }, from: "outpost".into(), pay: 500, due: Some(1) }];
        save.day_clock = e.day - 0.5;
    }
    run(&mut app, 1.0);
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.day, save.board_day), (1, Some(1)), "a new day, new boards");
    assert_ne!(save.boards, before);
    assert_eq!(save.contracts.len(), 1, "due by the end of day 1, still in hand on it");
    app.world_mut().resource_mut::<Save>().day_clock = e.day - 0.5;
    run(&mut app, 1.0);
    let save = app.world().resource::<Save>().clone();
    assert!(save.contracts.is_empty(), "lapsed on day 2");
    assert_eq!(standing_of(&app, Faction::Pmc), -25, "and the PMC, who gave it, think 5 worse of you");
}

/// The solar system with the menu and input devices, played from the title screen on.
fn counter_app() -> App {
    use crate::menu::{MenuPlugin, Screen};
    let mut app = build_app(Tuning::default());
    drop_flat_floor(&mut app);
    app.add_plugins((solar::SolarPlugin, crate::gunsmith::GunsmithPlugin, MenuPlugin));
    with_input_devices(&mut app);
    app.finish();
    app.update();
    tap(&mut app, KeyCode::Enter);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    run(&mut app, 1.0);
    app
}

#[test]
fn the_board_opens_from_its_station_takes_two_jobs_and_no_more() {
    use crate::menu::{Menu, Panel, Screen};
    let mut app = counter_app();
    stand_at_station(&mut app, StationKind::Board, 0);
    let offers = app.world().resource::<Save>().boards["roost"].clone();
    assert!(offers.len() >= 2);
    press_use(&mut app);
    run(&mut app, 0.2);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Paused);
    let menu = app.world().resource::<Menu>();
    assert_eq!((menu.panel, menu.board.as_str(), menu.board_faction, menu.from_station), (Panel::Board, "roost", Faction::Deserters, true));
    // Enter takes the first offer, then the next one up; a third is refused and stays.
    tap(&mut app, KeyCode::Enter);
    tap(&mut app, KeyCode::Enter);
    let save = app.world().resource::<Save>().clone();
    assert_eq!(save.contracts, offers[..2].to_vec());
    assert_eq!(save.boards["roost"], offers[2..].to_vec());
    tap(&mut app, KeyCode::Enter);
    assert_eq!(app.world().resource::<Save>().contracts.len(), 2);
    assert!(app.world().resource::<Menu>().note.contains("2 jobs already"), "{}", app.world().resource::<Menu>().note);
    // The Roost buys no scrap: three offers, two jobs, then the sell row.
    app.world_mut().resource_mut::<Save>().scrap = 10;
    for _ in 0..5 {
        tap(&mut app, KeyCode::KeyS);
    }
    tap(&mut app, KeyCode::Enter);
    assert_eq!(app.world().resource::<Menu>().note, "This board buys no scrap");
    assert_eq!(app.world().resource::<Save>().scrap, 10);
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing, "back to the game");
    // Vantage's board buys it at 70%: $4 a scrap to a neutral.
    set_standing(&mut app, Faction::Pmc, 0);
    only_station(&mut app, StationKind::Contracts, 3);
    press_use(&mut app);
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Menu>().board, "outpost");
    let banked = app.world().resource::<Save>().banked;
    for _ in 0..5 {
        tap(&mut app, KeyCode::KeyS);
    }
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().scrap, app.world().resource::<Save>().banked), (0, banked + 40));
}

#[test]
fn a_raider_shot_down_by_your_ship_counts_toward_a_cull() {
    let (mut app, jackal) = gunnery_range(300.0);
    app.world_mut().resource_mut::<Save>().contracts = vec![
        Contract { job: solar::board::Job::Cull { need: 2, got: 0 }, from: "roost".into(), pay: 100, due: None },
        Contract { job: solar::board::Job::Cull { need: 1, got: 0 }, from: "yard".into(), pay: 50, due: None },
    ];
    hold_fire(&mut app, 4.0);
    run(&mut app, 0.2);
    assert!(app.world().get_entity(jackal).is_err(), "the Jackal is destroyed");
    let save = app.world().resource::<Save>().clone();
    assert_eq!(save.contracts.len(), 1, "the one-raider cull is done");
    assert_eq!(save.contracts[0].job, solar::board::Job::Cull { need: 2, got: 1 });
    assert_eq!(save.pocket, 60 + 50, "the bounty and the cull's pay, both unbanked");
    assert_eq!(app.world().resource::<BountyLine>().text, "CULL DONE +$50");
}

#[test]
fn the_space_screens_draw_with_and_without_the_solar_system() {
    use crate::menu::{Menu, MenuPlugin, Panel, Screen};
    let mut solar = counter_app();
    let mut plain = build_app(Tuning::default());
    plain.add_plugins((crate::gunsmith::GunsmithPlugin, MenuPlugin));
    with_input_devices(&mut plain);
    plain.finish();
    plain.update();
    for app in [&mut solar, &mut plain] {
        app.world_mut().resource_mut::<NextState<Screen>>().set(Screen::Paused);
        app.update();
        for panel in [Panel::Starmap, Panel::Ship, Panel::Contracts] {
            app.world_mut().resource_mut::<Menu>().panel = panel;
            app.update();
            app.update();
            assert_eq!(app.world().resource::<Menu>().panel, panel);
        }
    }
}

#[test]
fn the_solar_system_starts_you_with_the_warden_a_knife_and_nothing_else() {
    let mut app = counter_app();
    // The pilot class wears Runner, who starts with the Warden.
    assert_eq!(app.world().resource::<Save>().weapons, ["revolver", "knife"]);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Revolver);
    for slot in 0..4 {
        assert_eq!(app.world().resource::<crate::gunsmith::Loadout>().part(WeaponKind::Revolver, slot), 0, "no attachments");
    }
    let c = app.world().resource::<crate::character::Characters>();
    assert_eq!((c.start("zealot"), c.start("acolyte"), c.start("nobody")), (WeaponKind::Pistol, WeaponKind::Revolver, WeaponKind::Pistol));
    assert!(c.problems().is_empty(), "{:?}", c.problems());
    run(&mut app, 0.1);
}

#[test]
fn the_counter_opens_at_the_quartermaster_sells_for_banked_money_and_hands_back_the_game() {
    use crate::menu::{Menu, Panel, Screen};
    let mut app = counter_app();
    app.world_mut().resource_mut::<Save>().banked = 1500;
    let at = app.world_mut().query::<(&Station, &GlobalTransform)>().iter(app.world()).find(|(s, _)| s.kind == StationKind::Resupply).map(|(_, g)| g.translation()).expect("the Roost's quartermaster");
    set_player(&mut app, at, Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.3);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Paused);
    let menu = app.world().resource::<Menu>();
    assert_eq!((menu.panel, menu.from_station), (Panel::Quartermaster, true));

    // E steps the picker on from the Warden to the Thumper (1000); Enter buys it, then steps on to the Harpoon.
    tap(&mut app, KeyCode::KeyE);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Grenade);
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().banked, app.world().resource::<Save>().weapons.contains(&"grenade".to_string())), (500, true));
    tap(&mut app, KeyCode::Enter);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Harpoon, "Enter on a gun you own just steps on");
    assert_eq!(app.world().resource::<Save>().banked, 500);
    // The Power fist is 600: short, nothing sold.
    tap(&mut app, KeyCode::KeyE);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Fist);
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().banked, app.world().resource::<Save>().weapons.len()), (500, 3));
    assert!(app.world().resource::<Menu>().note.contains("$100 short"), "{}", app.world().resource::<Menu>().note);

    // Back to the game: the gun on the counter was not yours, so you hold the Warden again.
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    assert_eq!(app.world().resource::<Arsenal>().kind(), WeaponKind::Revolver);
}

#[test]
fn attachments_are_bought_once_and_tried_on_for_free() {
    use crate::menu::Screen;
    let mut app = counter_app();
    app.world_mut().resource_mut::<Save>().banked = 250;
    let at = app.world_mut().query::<(&Station, &GlobalTransform)>().iter(app.world()).find(|(s, _)| s.kind == StationKind::Resupply).map(|(_, g)| g.translation()).unwrap();
    set_player(&mut app, at, Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.3);
    // Down to the optic row, right to the red dot (200), Enter buys it.
    tap(&mut app, KeyCode::KeyS);
    tap(&mut app, KeyCode::KeyD);
    assert_eq!(app.world().resource::<crate::gunsmith::Loadout>().part(WeaponKind::Revolver, 0), 1);
    assert_eq!(app.world().resource::<Save>().banked, 250, "trying it on is free");
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().banked, app.world().resource::<Save>().parts[0]), (50, 0b10));
    // The scope (400) is out of reach; leaving takes it off again and keeps the red dot's slot bare, as the dot is gone with it.
    tap(&mut app, KeyCode::KeyD);
    assert_eq!(app.world().resource::<crate::gunsmith::Loadout>().part(WeaponKind::Revolver, 0), 2);
    tap(&mut app, KeyCode::Enter);
    assert_eq!(app.world().resource::<Save>().banked, 50, "too poor for the scope");
    tap(&mut app, KeyCode::KeyA);
    assert_eq!(app.world().resource::<crate::gunsmith::Loadout>().part(WeaponKind::Revolver, 0), 1);
    tap(&mut app, KeyCode::KeyD);
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    assert_eq!(app.world().resource::<crate::gunsmith::Loadout>().part(WeaponKind::Revolver, 0), 0, "the unbought scope came off");
}

#[test]
fn the_shrine_sells_a_blessing_that_lengthens_the_health_bar_for_a_while() {
    let mut app = system_app();
    run(&mut app, 1.0);
    stand_at_station(&mut app, StationKind::Shrine, 1);
    app.world_mut().resource_mut::<Save>().banked = TITHE - 1;
    press_use(&mut app);
    assert_eq!(app.world().resource::<Blessing>().0, 0.0, "the tithe is not met");
    app.world_mut().resource_mut::<Save>().banked = TITHE + 5;
    let plain = app.world().resource::<PlayerHealth>().max;
    press_use(&mut app);
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Save>().banked, 5);
    let health = app.world().resource::<PlayerHealth>().clone();
    assert!(app.world().resource::<Blessing>().0 > 0.0 && (health.max - (plain + BLESSING_HP)).abs() < 0.01, "blessed, max {}", health.max);
    assert!(health.hp > plain, "and healed past the usual maximum, {}", health.hp);
    // It wears off.
    app.world_mut().resource_mut::<Blessing>().0 = 0.05;
    run(&mut app, 0.3);
    let health = app.world().resource::<PlayerHealth>().clone();
    assert!((health.max - plain).abs() < 0.01 && health.hp <= health.max, "back to normal: {} / {}", health.hp, health.max);
}


// ------------------------------------------------------------------- raiders, patrols and the AI

use solar::ai::{Enemy, Mode, Role};
use solar::enemy::{spawn_enemy, Patrols, Raids};

/// Every enemy ship: its entity, why it is there and what it is doing.
fn enemies(app: &mut App) -> Vec<(Entity, Role, Mode)> {
    app.world_mut().query::<(Entity, &Enemy)>().iter(app.world()).map(|(e, en)| (e, en.role, en.mode)).collect()
}

/// The Kestrel boarded and hanging `height` metres straight over the pad, at rest.
fn aloft(height: f32) -> App {
    let mut app = system_app();
    run(&mut app, 0.5);
    board(&mut app);
    let (p, _) = ship_state(&mut app);
    put_ship(&mut app, p + p.normalize() * height, Vec3::ZERO);
    run(&mut app, 0.1);
    app
}

/// Where a ship is, its nose and its velocity, in the world frame.
fn pose(app: &App, e: Entity) -> (Vec3, Vec3, Vec3) {
    let (p, r, v) = (app.world().get::<Position>(e).unwrap().0, app.world().get::<Rotation>(e).unwrap().0, app.world().get::<LinearVelocity>(e).unwrap().0);
    (p, r * Vec3::NEG_Z, v)
}

/// The ship spec index of `id`.
fn spec_of(app: &App, id: &str) -> usize {
    app.world().resource::<solar::ship::Ships>().ship.iter().position(|s| s.id == id).unwrap()
}

/// An enemy `id` at `offset` (world frame) from the Kestrel, nose toward it, at rest.
fn enemy_near(app: &mut App, id: &str, offset: Vec3, role: Role) -> Entity {
    let spec = spec_of(app, id);
    let ship = ship_entity(app);
    let (p, _, _) = pose(app, ship);
    let at = p + offset;
    let up = app.world().resource::<Surface>().up(app.world().resource::<Origin>().body(at));
    let facing = Transform::from_translation(at).looking_at(p, up).rotation;
    let e = spawn_enemy(app.world_mut(), spec, at, facing, Vec3::ZERO, role);
    run(app, 1.0 / 66.0);
    e
}

#[test]
fn a_raid_comes_in_off_to_one_side_inside_the_band_and_never_over_the_cap() {
    let mut app = aloft(3400.0);
    let t = Tuning::default().ship_combat;
    let ship = ship_entity(&mut app);
    let mut packs = Vec::new();
    for _ in 0..5 {
        let (from, nose, _) = pose(&app, ship);
        let before: HashSet<Entity> = enemies(&mut app).iter().map(|e| e.0).collect();
        app.world_mut().resource_mut::<Raids>().force = true;
        run(&mut app, 2.0 / 66.0);
        let new: Vec<Entity> = enemies(&mut app).iter().map(|e| e.0).filter(|e| !before.contains(e)).collect();
        for &e in &new {
            let (p, _, _) = pose(&app, e);
            let d = p.distance(from);
            assert!((t.spawn_near..=t.spawn_far).contains(&d), "came in {d:.0} m off");
            assert!((p - from).normalize().dot(nose) <= 0.0, "never ahead of the nose: {:.0} degrees off it", (p - from).angle_between(nose).to_degrees());
            assert_eq!(app.world().get::<Ship>(e).map(|s| s.spec), Some(spec_of(&app, "jackal")), "raiders fly Jackals");
        }
        packs.push(new.len());
    }
    let alive = enemies(&mut app).len();
    assert!(packs[0] >= 2 && packs[0] <= 4, "a pack of two to four: {packs:?}");
    assert_eq!(alive, t.enemy_cap, "packs fill up to the cap and no further: {packs:?}");
    assert_eq!(*packs.last().unwrap(), 0, "a full sky takes no more: {packs:?}");
    assert!(enemies(&mut app).iter().all(|e| e.1 == Role::Raider));
}

#[test]
fn a_raider_past_six_km_is_gone() {
    let mut app = aloft(3400.0);
    let ship = ship_entity(&mut app);
    let side = app.world().get::<Rotation>(ship).unwrap().0 * Vec3::X;
    let near = enemy_near(&mut app, "jackal", side * 5500.0, Role::Raider);
    let far = enemy_near(&mut app, "jackal", -side * 6300.0, Role::Raider);
    run(&mut app, 0.1);
    assert!(app.world().get_entity(far).is_err(), "6.3 km off: gone");
    assert!(app.world().get_entity(near).is_ok(), "5.5 km off: still coming");
}

#[test]
fn no_raiders_on_foot_near_a_base_or_in_the_first_minute_after_boarding() {
    let t = Tuning::default().ship_combat;
    let due = |app: &mut App, aboard: f32| {
        let mut r = app.world_mut().resource_mut::<Raids>();
        r.clock = t.raid_delay + 1.0;
        r.aboard = aboard;
    };
    // On foot, beside the ship: whatever the clock says.
    let mut app = system_app();
    run(&mut app, 0.5);
    due(&mut app, 1000.0);
    run(&mut app, 1.0);
    assert!(enemies(&mut app).is_empty(), "nothing hunts you on foot");
    // On the pad, a hundred metres from the Roost: none, however long you have been aboard.
    board(&mut app);
    due(&mut app, 1000.0);
    run(&mut app, 1.0);
    assert!(enemies(&mut app).is_empty(), "none within 3 km of a base");
    // Away from it, but only just aboard: none until the minute is up.
    let (p, _) = ship_state(&mut app);
    put_ship(&mut app, p + p.normalize() * 3400.0, Vec3::ZERO);
    due(&mut app, 0.0);
    run(&mut app, 2.0);
    assert!(enemies(&mut app).is_empty(), "none in the first minute");
    due(&mut app, t.raid_grace + 0.5);
    run(&mut app, 0.1);
    assert!(enemies(&mut app).len() >= 2, "then the pack comes");
    assert_eq!(app.world().resource::<Raids>().clock, 0.0, "and the clock starts again");
}

#[test]
fn the_raid_clock_runs_faster_the_longer_the_flight_goes_without_a_fight() {
    let mut app = aloft(3400.0);
    run(&mut app, 2.0);
    let early = app.world().resource::<Raids>().clock;
    app.world_mut().resource_mut::<Raids>().quiet = 240.0;
    let before = app.world().resource::<Raids>().clock;
    run(&mut app, 2.0);
    let late = app.world().resource::<Raids>().clock - before;
    assert!(late > early * 2.5, "four quiet minutes in, it runs about three times as fast: {early:.2} then {late:.2}");
}

/// Hands the flight over to `body` with the Kestrel at `p` (that body's coordinates), at rest
/// over its ground, then lets its fixtures stand.
fn fly_to(app: &mut App, body: &str, p: Vec3) {
    let (q, v) = {
        let solar = app.world().resource::<Solar>();
        let (q, v) = solar.bodies.convert(body, &solar.anchor, solar.epoch, p.as_dvec3(), bevy::math::DVec3::ZERO);
        (q.as_vec3(), v.as_vec3())
    };
    put_ship(app, q, v);
    run(app, 0.3);
    assert_eq!(app.world().resource::<Solar>().anchor, body);
}

/// The Reliquary's ground point and up on Bastion, body coordinates.
fn reliquary(app: &App) -> (Vec3, Vec3) {
    let bases = app.world().resource::<solar::base::Bases>().clone();
    let solar = app.world().resource::<Solar>();
    let spec = bases.base.iter().find(|b| b.id == "reliquary").unwrap();
    let (ground, frame, deck) = solar::base::site(spec, &solar.spheres["bastion"], solar.pad);
    (ground + frame * Vec3::Y * deck, frame * Vec3::Y)
}

/// The patrols in the sky: what each is doing.
fn patrol_modes(app: &mut App) -> Vec<Mode> {
    enemies(app).into_iter().filter(|e| matches!(e.1, Role::Patrol { .. })).map(|e| e.2).collect()
}

#[test]
fn patrols_guard_a_base_inside_eight_km_attack_inside_two_and_a_half_and_come_back_after_ten_minutes() {
    let t = Tuning::default().ship_combat;
    let mut app = system_app();
    run(&mut app, 0.5);
    run(&mut app, 0.5);
    assert!(enemies(&mut app).is_empty(), "the Roost has no patrols");
    board(&mut app);
    let (base, up) = reliquary(&app);
    fly_to(&mut app, "bastion", base + up * 9000.0);
    run(&mut app, 0.5);
    assert!(patrol_modes(&mut app).is_empty(), "9 km off: none up");
    put_ship(&mut app, base + up * 7500.0, Vec3::ZERO);
    run(&mut app, 0.5);
    assert_eq!(patrol_modes(&mut app), [Mode::Patrol, Mode::Patrol], "7.5 km off: two up, flying their loop");
    let censer = spec_of(&app, "censer");
    let origin = *app.world().resource::<Origin>();
    for (e, _, _) in enemies(&mut app) {
        assert_eq!(app.world().get::<Ship>(e).unwrap().spec, censer, "the Regime flies Censers");
        let (p, _, _) = pose(&app, e);
        let height = (origin.body(p) - base).dot(up);
        assert!((height - t.patrol_altitude).abs() < 20.0, "at patrol height: {height:.0} m");
        assert!(app.world().get::<crate::planet::bubble::KeepAwake>(e).is_some(), "kept awake so far from you");
    }
    put_ship(&mut app, base + up * 3000.0, Vec3::ZERO);
    run(&mut app, 0.5);
    assert!(patrol_modes(&mut app).iter().all(|m| *m == Mode::Patrol), "3 km off: left alone");
    put_ship(&mut app, base + up * 2000.0, Vec3::ZERO);
    run(&mut app, 0.3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m != Mode::Patrol), "2 km off: they come for you, {:?}", patrol_modes(&mut app));
    put_ship(&mut app, base + up * 3500.0, Vec3::ZERO);
    run(&mut app, 0.3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m != Mode::Patrol), "3.5 km off: they keep after you");
    put_ship(&mut app, base + up * 4500.0, Vec3::ZERO);
    run(&mut app, 0.3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m == Mode::Patrol), "4.5 km off: they give up, {:?}", patrol_modes(&mut app));
    // One shot down: back only after ten minutes of game time.
    let (shot, _, _) = enemies(&mut app)[0];
    app.world_mut().get_mut::<Hull>(shot).unwrap().hp = 0.0;
    run(&mut app, 0.5);
    assert!(app.world().get_entity(shot).is_err(), "shot down");
    assert_eq!(patrol_modes(&mut app).len(), 1, "one left");
    app.world_mut().resource_mut::<Patrols>().clock += t.patrol_respawn as f64 - 5.0;
    run(&mut app, 0.5);
    assert_eq!(patrol_modes(&mut app).len(), 1, "not yet");
    app.world_mut().resource_mut::<Patrols>().clock += 5.0;
    run(&mut app, 0.5);
    assert_eq!(patrol_modes(&mut app).len(), 2, "back after ten minutes");
    // Leaving: they go.
    put_ship(&mut app, base + up * 9000.0, Vec3::ZERO);
    run(&mut app, 0.2);
    assert!(patrol_modes(&mut app).is_empty(), "gone once you are well away");
}

#[test]
fn a_raider_closes_on_the_kestrel_and_fires_only_with_it_in_the_cone() {
    let mut app = aloft(2000.0);
    let t = Tuning::default().ship_combat;
    let ship = ship_entity(&mut app);
    let side = app.world().get::<Rotation>(ship).unwrap().0 * Vec3::X;
    // A steady hand, so every pass that should land does.
    let spec = spec_of(&app, "jackal");
    app.world_mut().resource_mut::<solar::ship::Ships>().ship[spec].ai.wobble = 0.0;
    let jackal = enemy_near(&mut app, "jackal", side * 2000.0, Role::Raider);
    let ai = app.world().resource::<solar::ship::Ships>().ship[spec].ai.clone();
    let (mut nearest, mut fired, mut modes) = (f32::MAX, 0, HashSet::new());
    for _ in 0..(10.0 / DT) as usize {
        let ((p, nose, v), (q, _, w)) = (pose(&app, jackal), pose(&app, ship));
        nearest = nearest.min(p.distance(q));
        app.update();
        let Some(enemy) = app.world().get::<Enemy>(jackal) else { break };
        modes.insert(format!("{:?}", enemy.mode));
        if app.world().get::<ShipControls>(jackal).unwrap().fire {
            fired += 1;
            let aim = solar::ai::lead(q - p, w - v, t.gun_speed);
            let off = nose.angle_between(aim).to_degrees();
            assert!(off < ai.cone + 1.0, "fired {off:.1} degrees off the lead");
        }
    }
    assert!(nearest < 800.0, "closed from 2 km to {nearest:.0} m");
    assert!(fired > 0, "and fired: {modes:?}");
    let hull = *app.world().get::<Hull>(ship).unwrap();
    assert!(hull.shield < 60.0, "and hit: shield {} hull {}", hull.shield, hull.hp);
    assert!(modes.contains("Break"), "and broke off after a pass: {modes:?}");
}

#[test]
fn an_enemy_pilot_diving_on_a_low_target_never_flies_into_the_ground() {
    let mut app = aloft(60.0);
    let ship = ship_entity(&mut app);
    // The target outlasts the 40 s: shot down, it would be back at the Roost, and the raiders
    // left 6 km behind would be gone.
    app.world_mut().entity_mut(ship).insert(Hull::new(1e6, 0.0));
    let rot = app.world().get::<Rotation>(ship).unwrap().0;
    let mut ships = Vec::new();
    for id in ["jackal", "censer", "welder", "sentry"] {
        let e = enemy_near(&mut app, id, rot * Vec3::new(400.0 * ships.len() as f32 - 600.0, 300.0, -1200.0), Role::Raider);
        // One side, so none is shot down by another's stray fire.
        app.world_mut().entity_mut(e).insert(Faction::Raiders);
        app.world_mut().get_mut::<LinearVelocity>(e).unwrap().0 = (pose(&app, ship).0 - pose(&app, e).0).normalize() * 150.0;
        ships.push((id, e, f32::MAX));
    }
    for _ in 0..(40.0 / DT) as usize {
        app.update();
        let solar = app.world().resource::<Solar>();
        let (surface, origin) = (app.world().resource::<Surface>(), app.world().resource::<Origin>());
        for (_, e, low) in &mut ships {
            let Some(p) = app.world().get::<Position>(*e) else { continue };
            *low = low.min(solar::ship::clearance(solar, surface, origin.body(p.0)));
        }
    }
    for (id, e, low) in ships {
        assert!(app.world().get_entity(e).is_ok(), "{id} still flying");
        assert!(low > 25.0, "{id} came down to {low:.0} m over the ground");
    }
}

#[test]
fn a_dogfight_across_an_origin_rebase_keeps_every_ship_on_its_path() {
    let mut app = aloft(2000.0);
    let ship = ship_entity(&mut app);
    let (_, nose, _) = pose(&app, ship);
    let side = app.world().get::<Rotation>(ship).unwrap().0 * Vec3::X;
    let raiders = [enemy_near(&mut app, "jackal", side * 900.0 - nose * 300.0, Role::Raider), enemy_near(&mut app, "jackal", -side * 1200.0, Role::Raider)];
    // Full throttle, level: the Kestrel runs and the raiders chase it, the world re-centring on
    // it every 400 m.
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = 400.0;
    input(&mut app).thrust = 1.0;
    let start = app.world().resource::<Origin>().offset;
    let mut rebased = 0;
    for tick in 0..(10.0 / DT) as usize {
        let origin = *app.world().resource::<Origin>();
        let last: Vec<(Vec3, Vec3)> = raiders.iter().map(|&e| (origin.body(app.world().get::<Position>(e).unwrap().0), app.world().get::<LinearVelocity>(e).unwrap().0)).collect();
        app.update();
        let now = *app.world().resource::<Origin>();
        rebased += (now.offset != origin.offset) as i32;
        for (k, &e) in raiders.iter().enumerate() {
            let (pos, tf, v) = (app.world().get::<Position>(e).unwrap().0, app.world().get::<Transform>(e).unwrap().translation, app.world().get::<LinearVelocity>(e).unwrap().0);
            assert!(pos.distance(tf) < 0.01, "tick {tick}: transform and body agree");
            let step = now.body(pos) - last[k].0;
            let expected = (last[k].1 + v) / 2.0 * DT;
            assert!(step.distance(expected) < 1.0, "tick {tick}: raider {k} jumped {:.2} m off its path", step.distance(expected));
        }
    }
    assert!(rebased > 0 && app.world().resource::<Origin>().offset != start, "the origin moved under the fight");
}

// --------------------------------------------------------------------------- homing missiles

use solar::missile::{Missile, Missiles};

/// The ship's missiles and lock.
fn missiles(app: &App, ship: Entity) -> Missiles {
    app.world().get::<Missiles>(ship).unwrap().clone()
}

/// Every missile in flight: its entity and the ship that fired it.
fn in_flight(app: &mut App) -> Vec<(Entity, Entity)> {
    app.world_mut().query::<(Entity, &Missile)>().iter(app.world()).map(|(e, m)| (e, m.owner)).collect()
}

/// One click of the right mouse button: held for a frame, then let go.
fn click_missile(app: &mut App) {
    input(app).aim_held = true;
    app.update();
    app.update();
}

/// The fighter of `gunnery_range` given a Welder's 60 shield and 200 hull, so one missile's 80
/// shows where it went.
fn tough(app: &mut App, target: Entity) {
    app.world_mut().entity_mut(target).insert(Hull::new(200.0, 60.0));
}

/// Sets `target` flying on whatever velocity it is given, like an enemy pilot's ship: kept awake
/// (a kilometre off is outside the physics bubble), and woken if the bubble froze it while it
/// stood parked.
fn under_way(app: &mut App, target: Entity, velocity: Vec3) {
    app.world_mut().entity_mut(target).remove::<(RigidBodyDisabled, crate::planet::bubble::Frozen)>().insert((RigidBody::Kinematic, LinearVelocity(velocity), crate::planet::bubble::KeepAwake));
}

/// Moves `target` to `range` metres off the ship's nose, `degrees` to its right.
fn off_nose(app: &mut App, target: Entity, range: f32, degrees: f32) {
    let ship = ship_entity(app);
    let tf = *app.world().get::<Transform>(ship).unwrap();
    let at = tf.translation + tf.rotation * (Quat::from_rotation_y(-degrees.to_radians()) * Vec3::NEG_Z * range);
    app.world_mut().entity_mut(target).insert((Transform::from_translation(at).with_rotation(tf.rotation), Position(at)));
}

#[test]
fn a_lock_needs_a_ship_held_in_the_cone_for_1_2_s_and_drops_when_it_leaves() {
    let (mut app, jackal) = gunnery_range(800.0);
    let ship = ship_entity(&mut app);
    run(&mut app, 2.0 / 66.0);
    assert_eq!(missiles(&app, ship).target, Some(jackal), "dead ahead: the lock starts");
    run(&mut app, 1.0);
    let m = missiles(&app, ship);
    assert!(m.locked().is_none() && m.lock > 0.75 && m.lock < 1.0, "a second in: not yet, {}", m.lock);
    run(&mut app, 0.25);
    assert_eq!(missiles(&app, ship).locked(), Some(jackal), "1.2 s: locked");
    off_nose(&mut app, jackal, 800.0, 4.5);
    run(&mut app, 0.5);
    assert_eq!(missiles(&app, ship).locked(), Some(jackal), "4.5 degrees off the nose is inside the cone");
    off_nose(&mut app, jackal, 800.0, 8.0);
    run(&mut app, 2.0 / 66.0);
    let m = missiles(&app, ship);
    assert_eq!((m.target, m.lock), (None, 0.0), "8 degrees off: the lock is gone");
    off_nose(&mut app, jackal, 800.0, 0.0);
    run(&mut app, 0.5);
    let m = missiles(&app, ship);
    assert!(m.target == Some(jackal) && m.lock < 0.5, "back in the cone it starts from nothing: {}", m.lock);
    // Its own side, or too far, is never locked.
    app.world_mut().entity_mut(jackal).insert(Faction::Deserters);
    run(&mut app, 2.0);
    assert_eq!(missiles(&app, ship).target, None, "not the player's own side");
    app.world_mut().entity_mut(jackal).insert(Faction::Raiders);
    off_nose(&mut app, jackal, 3200.0, 0.0);
    run(&mut app, 2.0);
    assert_eq!(missiles(&app, ship).target, None, "not past 3 km");
}

#[test]
fn a_locked_missile_hits_a_steady_target_for_80_damage_shield_first() {
    let (mut app, jackal) = gunnery_range(1200.0);
    tough(&mut app, jackal);
    let ship = ship_entity(&mut app);
    run(&mut app, 1.3);
    assert_eq!(missiles(&app, ship).locked(), Some(jackal));
    click_missile(&mut app);
    let flying = in_flight(&mut app);
    assert_eq!(flying.len(), 1, "one missile away");
    assert_eq!(app.world().get::<Missile>(flying[0].0).unwrap().target, Some(jackal), "at the locked ship");
    // It flies on across the nose at 100 m/s, steady.
    let side = app.world().get::<Rotation>(ship).unwrap().0 * Vec3::X;
    under_way(&mut app, jackal, side * 100.0);
    let mut took = 0.0;
    while !in_flight(&mut app).is_empty() && took < 6.0 {
        app.update();
        took += DT;
    }
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp), (0.0, 180.0), "80 damage: the 60 shield, then 20 off the hull ({took:.1} s)");
    assert!(took < 3.5, "hit in {took:.1} s");
}

/// A missile locked on the gunnery range's fighter 1 km ahead, which flies off across the nose at
/// 250 m/s as it is fired, heading `phase` radians round from straight across, and once the
/// missile is within `break_at` metres breaks into a turn at `rate` rad/s: how close the missile
/// came, and the shield and hull left.
fn chase(rate: f32, phase: f32, break_at: f32) -> (f32, f32) {
    let (mut app, jackal) = gunnery_range(1000.0);
    tough(&mut app, jackal);
    let ship = ship_entity(&mut app);
    run(&mut app, 1.3);
    click_missile(&mut app);
    let missile = in_flight(&mut app)[0].0;
    let rot = app.world().get::<Rotation>(ship).unwrap().0;
    let up = rot * Vec3::Y;
    let mut heading = Quat::from_axis_angle(up, phase) * (rot * Vec3::X);
    under_way(&mut app, jackal, heading * 250.0);
    let mut closest = f32::MAX;
    for _ in 0..(8.0 / DT) as usize {
        let (Some(m), Some(j)) = (app.world().get::<Transform>(missile), app.world().get::<Position>(jackal)) else { break };
        let d = m.translation.distance(j.0);
        closest = closest.min(d);
        if d < break_at || closest < break_at {
            heading = Quat::from_axis_angle(up, rate * DT) * heading;
        }
        app.world_mut().get_mut::<LinearVelocity>(jackal).unwrap().0 = heading * 250.0;
        app.update();
    }
    let h = *app.world().get::<Hull>(jackal).unwrap();
    (closest, h.hp + h.shield)
}

#[test]
fn a_missile_is_outturned_by_a_target_breaking_harder_than_it_can_turn() {
    let t = Tuning::default().ship_combat;
    // From five headings across and away, the target breaks into a turn once the missile is
    // 600 m off. Steady, or a gentle 1 rad/s under the missile's 1.4: hit every time.
    let headings = [0.0, 0.8, 1.6, 2.4, -0.8];
    for rate in [0.0, 1.0] {
        for phase in headings {
            let (closest, left) = chase(rate, phase, 600.0);
            assert_eq!(left, 180.0, "{rate} rad/s from {phase}: hit, closest {closest:.1} m");
        }
    }
    // A hard 2.5 rad/s break, well over its 1.4: it gets away from most of them.
    assert!(t.missile_turn < 2.5);
    let missed: Vec<f32> = headings.iter().map(|&phase| chase(2.5, phase, 600.0)).filter(|(_, left)| *left == 260.0).map(|(c, _)| c).collect();
    assert!(missed.len() >= 3, "a hard break gets away: missed {} of 5 ({missed:?} m)", missed.len());
}

#[test]
fn a_missile_bursts_on_the_ground_and_after_eight_seconds() {
    let t = Tuning::default().ship_combat;
    let mut app = aloft(120.0);
    let ship = ship_entity(&mut app);
    let (p, _, _) = pose(&app, ship);
    let up = app.world().resource::<Surface>().up(app.world().resource::<Origin>().body(p));
    let side = up.any_orthonormal_vector();
    // Straight down from 90 m over the ground, off to one side of the ship.
    let at = |offset: Vec3, dir: Vec3| Transform::from_translation(p + offset).looking_to(dir, dir.any_orthonormal_vector());
    let down = solar::missile::spawn(app.world_mut(), Missile::new(100.0, 600.0, ship, Faction::Deserters, None, &t), at(side * 20.0 - up * 30.0, -up));
    let mut low = f32::MAX;
    for _ in 0..(1.5 / DT) as usize {
        let Some(tf) = app.world().get::<Transform>(down) else { break };
        let solar = app.world().resource::<Solar>();
        low = low.min(solar::ship::clearance(solar, app.world().resource::<Surface>(), app.world().resource::<Origin>().body(tf.translation)));
        app.update();
    }
    assert!(app.world().get_entity(down).is_err(), "burst on the ground within 1.5 s");
    assert!(low < 15.0, "at the ground: it got down to {low:.1} m");
    // Straight up into an empty sky: it bursts on its own at 8 s.
    let climb = solar::missile::spawn(app.world_mut(), Missile::new(600.0, 600.0, ship, Faction::Deserters, None, &t), at(up * 30.0, up));
    run(&mut app, t.missile_life - 0.15);
    assert!(app.world().get_entity(climb).is_ok(), "still flying at 7.85 s");
    run(&mut app, 0.3);
    assert!(app.world().get_entity(climb).is_err(), "gone at 8 s");
}

#[test]
fn a_missile_never_hurts_its_own_side() {
    let (mut app, jackal) = gunnery_range(500.0);
    app.world_mut().entity_mut(jackal).insert(Faction::Deserters);
    let ship = ship_entity(&mut app);
    run(&mut app, 1.5);
    assert_eq!(missiles(&app, ship).target, None, "no lock on its own side");
    // Fired straight ahead with no lock, it flies into the fighter and bursts there, harmlessly.
    click_missile(&mut app);
    let missile = in_flight(&mut app)[0].0;
    assert_eq!(app.world().get::<Missile>(missile).unwrap().target, None);
    run(&mut app, 2.0);
    assert!(app.world().get_entity(missile).is_err(), "burst on the hull");
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp), (30.0, 40.0), "no friendly fire");
}

#[test]
fn four_missiles_and_one_back_every_ten_seconds() {
    let t = Tuning::default().ship_combat;
    let mut app = aloft(600.0);
    let ship = ship_entity(&mut app);
    assert_eq!(missiles(&app, ship).count, 4, "four aboard");
    click_missile(&mut app);
    assert_eq!(missiles(&app, ship).count, 3);
    run(&mut app, t.missile_reload - 0.2);
    assert_eq!(missiles(&app, ship).count, 3, "not back at 9.8 s");
    run(&mut app, 0.3);
    assert_eq!(missiles(&app, ship).count, 4, "back at 10 s");
    run(&mut app, 15.0);
    assert_eq!(missiles(&app, ship).count, 4, "never more than four");
    // Five clicks: four go, the fifth finds the rails empty.
    for _ in 0..5 {
        click_missile(&mut app);
    }
    assert_eq!(missiles(&app, ship).count, 0);
    assert_eq!(in_flight(&mut app).len(), 4, "four in the air");
    run(&mut app, t.missile_reload + 0.1);
    assert_eq!(missiles(&app, ship).count, 1, "one back after ten seconds");
}

#[test]
fn right_mouse_fires_a_missile_not_the_hand_guns_sights() {
    let mut app = system_app();
    run(&mut app, 0.5);
    // On foot it aims the gun in hand and fires no missile.
    for _ in 0..10 {
        input(&mut app).aim_held = true;
        app.update();
    }
    assert!(app.world().resource::<crate::weapon::Aim>().level > 0.0, "on foot: down the sights");
    assert!(in_flight(&mut app).is_empty(), "no missile on foot");
    input(&mut app).aim_held = false;
    run(&mut app, 0.5);
    board(&mut app);
    let shots = app.world().resource::<Arsenal>().shots;
    let ship = ship_entity(&mut app);
    input(&mut app).aim_held = true;
    app.update();
    // With no lock it goes straight off the nose.
    let (missile, _) = in_flight(&mut app)[0];
    let (nose, heading) = (app.world().get::<Rotation>(ship).unwrap().0 * Vec3::NEG_Z, app.world().get::<Transform>(missile).unwrap().rotation * Vec3::NEG_Z);
    assert!(nose.angle_between(heading) < 0.01 && app.world().get::<Missile>(missile).unwrap().target.is_none(), "straight ahead");
    // Held for a while: one missile, not one a tick.
    for _ in 0..20 {
        input(&mut app).aim_held = true;
        app.update();
    }
    assert!(app.world().get::<ShipControls>(ship).unwrap().missile, "the missile trigger is held");
    assert_eq!(missiles(&app, ship).count, 3, "one missile per press");
    assert!(app.world().resource::<crate::weapon::Aim>().level < 0.01, "flying: no aiming down the sights");
    assert_eq!(app.world().resource::<Arsenal>().shots, shots, "and the gun in hand stays quiet");
    app.update();
    assert!(!app.world().get::<ShipControls>(ship).unwrap().missile, "let go");
}

#[test]
fn a_sentry_fires_a_missile_once_it_has_a_lock_and_a_jackal_never_does() {
    let mut app = aloft(2000.0);
    let ship = ship_entity(&mut app);
    let rot = app.world().get::<Rotation>(ship).unwrap().0;
    let sentry = enemy_near(&mut app, "sentry", rot * Vec3::new(0.0, 100.0, 700.0), Role::Raider);
    let jackal = enemy_near(&mut app, "jackal", rot * Vec3::new(900.0, 100.0, 0.0), Role::Raider);
    // One side, so neither is shot down by the other's stray fire.
    app.world_mut().entity_mut(jackal).insert(Faction::Pmc);
    let mut fired = None;
    for tick in 0..(10.0 / DT) as usize {
        let before = missiles(&app, sentry);
        app.update();
        assert!(in_flight(&mut app).iter().all(|(_, owner)| *owner != jackal), "a Jackal flies with guns only");
        if let Some((m, _)) = in_flight(&mut app).into_iter().find(|(_, owner)| *owner == sentry) {
            assert_eq!(before.locked(), Some(ship), "tick {tick}: fired with a lock on the Kestrel");
            assert_eq!(app.world().get::<Missile>(m).unwrap().target, Some(ship), "and at it");
            fired = Some(tick as f32 * DT);
            break;
        }
    }
    assert!(fired.is_some(), "the Sentry fired a missile within 10 s");
    assert_eq!(missiles(&app, sentry).count, 3);
}

#[test]
fn a_missile_flies_on_across_an_origin_rebase_and_hits() {
    let (mut app, jackal) = gunnery_range(1500.0);
    tough(&mut app, jackal);
    let ship = ship_entity(&mut app);
    run(&mut app, 1.3);
    assert_eq!(missiles(&app, ship).locked(), Some(jackal));
    // The Kestrel runs at the target at 150 m/s, the world re-centring on it every 100 m.
    app.world_mut().resource_mut::<Tuning>().terrain.origin_step = 100.0;
    let nose = app.world().get::<Rotation>(ship).unwrap().0 * Vec3::NEG_Z;
    app.world_mut().get_mut::<LinearVelocity>(ship).unwrap().0 = nose * 150.0;
    input(&mut app).thrust = 1.0;
    click_missile(&mut app);
    let start = app.world().resource::<Origin>().offset;
    let mut rebased = 0;
    for _ in 0..(5.0 / DT) as usize {
        if in_flight(&mut app).is_empty() {
            break;
        }
        let before = app.world().resource::<Origin>().offset;
        app.update();
        rebased += (app.world().resource::<Origin>().offset != before) as i32;
    }
    assert!(rebased > 1 && app.world().resource::<Origin>().offset != start, "the origin moved under it {rebased} times");
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp), (0.0, 180.0), "and it hit");
}

#[test]
fn a_missile_is_carried_into_the_new_frame_at_a_handoff() {
    let mut app = aloft(600.0);
    click_missile(&mut app);
    let (missile, _) = in_flight(&mut app)[0];
    run(&mut app, 0.2);
    // The Kestrel jumps to 9 km over the Reliquary, on Bastion; the missile stays where it is.
    let (base, up) = reliquary(&app);
    let p = {
        let solar = app.world().resource::<Solar>();
        solar.bodies.convert("bastion", &solar.anchor, solar.epoch, (base + up * 9000.0).as_dvec3(), bevy::math::DVec3::ZERO).0.as_vec3()
    };
    put_ship(&mut app, p, Vec3::ZERO);
    for _ in 0..30 {
        let (old, epoch, origin) = {
            let solar = app.world().resource::<Solar>();
            (solar.anchor.clone(), solar.epoch, *app.world().resource::<Origin>())
        };
        let (tf, m) = (*app.world().get::<Transform>(missile).unwrap(), app.world().get::<Missile>(missile).unwrap());
        // As it flies this tick, burning on, before the handoff converts it.
        let v = tf.rotation * Vec3::NEG_Z * (m.speed + Tuning::default().ship_combat.missile_accel * DT).min(m.top);
        app.update();
        let solar = app.world().resource::<Solar>();
        if solar.anchor == old {
            continue;
        }
        assert_eq!(solar.anchor, "bastion");
        let (q, w) = solar.bodies.convert(&old, &solar.anchor, epoch, (origin.body(tf.translation) + v * DT).as_dvec3(), v.as_dvec3());
        let (q, w) = (q.as_vec3(), w.as_vec3());
        let now = app.world().resource::<Origin>().body(app.world().get::<Transform>(missile).expect("the missile survives the handoff").translation);
        assert!(now.distance(q) < 100.0f32.max(q.length() * 1e-6), "where it was, in Bastion's frame: {:.0} m off", now.distance(q));
        let m = app.world().get::<Missile>(missile).unwrap();
        let heading = app.world().get::<Transform>(missile).unwrap().rotation * Vec3::NEG_Z;
        assert!(heading.angle_between(w) < 1e-3 && (m.speed - w.length()).abs() < 10.0, "moving as it was: {} vs {}, {} rad off", m.speed, w.length(), heading.angle_between(w));
        return;
    }
    panic!("no handoff");
}

// ------------------------------------------------------------------ the loss rule and the bounty

use solar::loss::{BountyLine, Downed, Loss};

/// Empties the hull of the ship the player flies, as a last hit from nobody in particular.
fn shoot_down(app: &mut App) -> Entity {
    let ship = app.world_mut().query::<(Entity, &Ship)>().iter(app.world()).find(|(_, s)| s.pilot.is_some()).map(|(e, _)| e).expect("a ship being flown");
    let mut hull = app.world_mut().get_mut::<Hull>(ship).unwrap();
    (hull.shield, hull.hp) = (0.0, 0.0);
    ship
}

/// After the pause: the wreck gone, the player on foot on the cabin floor of one fresh Kestrel
/// standing on its berth on Haven's pad, the Roost's apron.
fn back_at_the_roost(app: &mut App, wreck: Entity) {
    let t = Tuning::default().ship_combat;
    run(app, t.downed + 0.5);
    assert!(app.world().get_entity(wreck).is_err(), "the wreck is gone");
    assert_eq!(app.world().resource::<Solar>().anchor, "home", "back on Haven");
    let kestrels: Vec<Entity> = app.world_mut().query::<(Entity, &Ship)>().iter(app.world()).filter(|(_, s)| s.spec == 0).map(|(e, _)| e).collect();
    assert_eq!(kestrels.len(), 1, "one Kestrel, never none");
    let kestrel = kestrels[0];
    let (berth, _) = solar::ship::berth(app.world(), 0).unwrap();
    let origin = *app.world().resource::<Origin>();
    let at = app.world().get::<Transform>(kestrel).unwrap().translation;
    assert!(origin.body(at).distance(berth) < 0.5, "on the pad, {} m off its berth", origin.body(at).distance(berth));
    let spec = app.world().resource::<solar::ship::Ships>().ship[0].clone();
    let hull = *app.world().get::<Hull>(kestrel).unwrap();
    let refit = solar::salvage::Refit::of(app.world().resource::<Save>(), &t);
    assert_eq!((hull.hp, hull.shield), (refit.max_hull(spec.hull), refit.max_shield(spec.shield)), "a fresh hull, with whatever parts are bought");
    let player = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    assert!(app.world().get::<Driving>(player).is_none(), "on foot");
    let (pos, _, _) = self::player(app);
    assert!(pos.distance(at) < solar::ship::BOARD_RADIUS, "in the Kestrel, {} m from its centre", pos.distance(at));
    assert!(app.world().resource::<Downed>().wreck.is_none());
}

#[test]
fn shot_down_you_lose_the_pocket_the_hold_and_the_parcel_and_pay_the_rebuy() {
    let mut app = aloft(600.0);
    {
        let mut save = app.world_mut().resource_mut::<Save>();
        save.banked = 1003;
        save.pocket = 120;
        save.scrap = 30;
        save.contracts = vec![parcel("reliquary", 400), Contract { job: solar::board::Job::Cull { need: 4, got: 1 }, from: "roost".into(), pay: 200, due: Some(3) }];
        save.ship_level = 2;
        save.parts = [3, 1, 0, 2];
    }
    let before = app.world().resource::<Save>().clone();
    assert!(!before.weapons.is_empty(), "the starter kit is owned");
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    // The camera hangs on the blast: the wreck is out of sight and out of the physics.
    let downed = app.world().resource::<Downed>();
    assert_eq!(downed.wreck, Some(wreck), "watching the wreck");
    assert_eq!(downed.lost, Loss { pocket: 120, scrap: 30, parcels: vec![parcel("reliquary", 400)], fee: 100 }, "a tenth of a $1000 tune is the $100 floor");
    assert_eq!(*app.world().get::<Visibility>(wreck).unwrap(), Visibility::Hidden);
    let bases = app.world().resource::<solar::base::Bases>().clone();
    assert_eq!(solar::loss::card_text(&app.world().resource::<Downed>().lost, &bases), "Lost $120 unbanked, 30 scrap and the parcel for The Reliquary. Rebuy $100");
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.banked, save.pocket, save.scrap, save.contracts.len(), save.deaths), (903, 0, 0, 1, 1), "the bank only pays the rebuy; the cull is kept");
    assert_eq!(standing_of(&app, Faction::Pmc), -25, "the parcel's issuer thinks 5 worse of you");
    assert_eq!((&save.weapons, save.parts, save.ship_level, &save.loadout), (&before.weapons, before.parts, before.ship_level, &before.loadout), "guns, parts and tune kept");
    back_at_the_roost(&mut app, wreck);
    assert_eq!(app.world().resource::<Save>().banked, 903, "paid once");
    assert!(app.world().resource::<Downed>().showing(), "the card is still up");
}

#[test]
fn shot_down_with_a_poor_bank_rebuys_for_what_is_there() {
    let (e, t) = (Tuning::default().economy, Tuning::default().ship_combat);
    let bases = solar::base::Bases::load();
    let mut save = Save { banked: 40, ..default() };
    let lost = solar::loss::lose(&mut save, &e, &t);
    assert_eq!((lost.clone(), save.banked, save.deaths), (Loss { fee: 40, ..default() }, 0, 1), "never more than the bank holds");
    assert_eq!(solar::loss::card_text(&lost, &bases), "Nothing aboard lost. Rebuy $40");
    let lost = solar::loss::lose(&mut save, &e, &t);
    assert_eq!((lost.clone(), save.banked), (Loss::default(), 0));
    assert_eq!(solar::loss::card_text(&lost, &bases), "Nothing aboard lost. Rebuy free: the bank is empty");
    let mut app = aloft(600.0);
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Downed>().lost, Loss::default(), "a new save has nothing to lose");
    assert_eq!(app.world().resource::<Save>().banked, 0);
    back_at_the_roost(&mut app, wreck);
}

#[test]
fn shot_down_over_bastion_you_are_back_at_the_roost_on_haven_in_a_fresh_kestrel() {
    let mut app = aloft(600.0);
    let (ground, up) = reliquary(&app);
    fly_to(&mut app, "bastion", ground + up * 3000.0);
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Solar>().anchor, "bastion", "the wreck burns where it fell");
    back_at_the_roost(&mut app, wreck);
    // Haven's ground streams in under the pad, and the player stands in the cabin.
    run(&mut app, 2.0);
    assert_eq!(player_state(&mut app), MoveState::Ground, "standing");
}

#[test]
fn shooting_down_an_enemy_pays_its_bounty_and_counts_the_kill_by_faction() {
    let t = Tuning::default().ship_combat;
    assert_eq!(["jackal", "sentry", "censer", "welder"].map(|id| t.bounty[id]), [60, 120, 150, 200]);
    let mut save = Save::default();
    assert_eq!(solar::loss::pay(&mut save, "welder", Faction::Scrappers, &t), 200);
    assert_eq!(solar::loss::pay(&mut save, "kestrel", Faction::Deserters, &t), 0, "no bounty on a hull not listed");
    let mut hull = Hull::new(10.0, 0.0);
    hull.hit_by(4.0, Entity::PLACEHOLDER, &t);
    assert_eq!(hull.last_hit_by, Some(Entity::PLACEHOLDER), "the shooter is remembered");
    hull.hit(4.0, &t);
    assert_eq!(hull.last_hit_by, None, "and forgotten after a hit from nobody");
    // The Kestrel's guns on the parked Jackal.
    let (mut app, jackal) = gunnery_range(300.0);
    hold_fire(&mut app, 4.0);
    run(&mut app, 0.2);
    assert!(app.world().get_entity(jackal).is_err(), "the Jackal is destroyed");
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.pocket, save.banked, save.kills), (60, 0, 1), "into the pocket, not the bank");
    assert_eq!(save.faction_kills, [("raiders".to_string(), 1)].into_iter().collect());
    let line = app.world().resource::<BountyLine>();
    assert_eq!(line.text, "+$60 BOUNTY  JACKAL");
    assert!(line.left > 0.0, "the line is up");
    run(&mut app, t.bounty_line);
    assert_eq!(app.world().resource::<BountyLine>().left, 0.0, "and gone a few seconds later");
}

#[test]
fn a_kill_by_another_ship_pays_nothing() {
    // The player flies, but it is the parked Jackal's guns that bring a Censer down.
    let (mut app, jackal) = gunnery_range(300.0);
    let censer = spec_of(&app, "censer");
    let tf = *app.world().get::<Transform>(jackal).unwrap();
    let at = tf.translation + tf.rotation * Vec3::NEG_Z * 300.0;
    let target = solar::ship::spawn(app.world_mut(), censer, Transform::from_translation(at).with_rotation(tf.rotation));
    app.world_mut().entity_mut(target).insert((RigidBody::Static, Position(at), Rotation(tf.rotation)));
    run(&mut app, 0.1);
    let mut hull = app.world_mut().get_mut::<Hull>(target).unwrap();
    (hull.shield, hull.hp) = (0.0, 20.0);
    for _ in 0..(3.0 / DT) as usize {
        app.world_mut().get_mut::<ShipControls>(jackal).unwrap().fire = true;
        app.update();
    }
    assert!(app.world().get_entity(target).is_err(), "the Jackal shot the Censer down");
    let save = app.world().resource::<Save>();
    assert_eq!((save.banked, save.kills, save.faction_kills.len()), (0, 0, 0), "no bounty, no kill on your tally");
    assert_eq!(app.world().resource::<BountyLine>().left, 0.0);
}

#[test]
fn an_old_save_without_kills_or_deaths_still_loads() {
    let path = std::env::temp_dir().join(format!("rust-regime-old-save-{}.toml", std::process::id()));
    std::fs::write(&path, "banked = 500\nweapons = [\"warden\", \"knife\"]\nparts = [1, 0, 0, 0]\nship_level = 2\ncontracts_done = 3\n\n[contract]\nto = \"yard\"\npay = 400\n").unwrap();
    let file = SaveFile(Some(path.clone()));
    let save = file.load();
    assert_eq!((save.banked, save.ship_level, save.contracts_done), (500, 2, 3), "the old fields are kept");
    assert_eq!((save.contracts.clone(), save.contract.clone()), (vec![Contract { job: solar::board::Job::Courier { to: "yard".into() }, from: "outpost".into(), pay: 400, due: None }], None), "the old parcel is a courier job");
    assert!(!toml::to_string(&save).unwrap().contains("[contract]"), "and is not written back the old way");
    assert_eq!((save.kills, save.deaths, save.faction_kills.len()), (0, 0, 0), "the new ones start at zero");
    // And the new fields round-trip.
    let tallied = Save { kills: 3, deaths: 1, faction_kills: [("raiders".to_string(), 2), ("pmc".to_string(), 1)].into_iter().collect(), ..save };
    file.write(&tallied);
    assert_eq!(file.load(), tallied);
    std::fs::remove_file(&path).ok();
}

// ------------------------------------------------------------------ the cockpit: HUD and sounds

use crate::hud::{FlightHud, Threat};
use solar::cockpit::{Cue, Sfx};

/// `aloft` with the HUD on: the Kestrel boarded and hanging `height` metres up.
fn aloft_with_hud(height: f32) -> App {
    let mut app = build_app(Tuning::default());
    drop_flat_floor(&mut app);
    app.add_plugins((solar::SolarPlugin, crate::hud::HudPlugin));
    app.finish();
    app.update();
    run(&mut app, 0.5);
    board(&mut app);
    let (p, _) = ship_state(&mut app);
    put_ship(&mut app, p + p.normalize() * height, Vec3::ZERO);
    run(&mut app, 0.1);
    app
}

/// Whether the on-foot health card, weapon card and crosshair show, and whether the ship card does.
fn cards(app: &mut App) -> (bool, bool, bool, bool) {
    use crate::hud::{CrosshairDot, HealthCard, ShipCard, WeaponPlate};
    let w = app.world_mut();
    let shown = |n: &Node| n.display != Display::None;
    let health = shown(w.query_filtered::<&Node, With<HealthCard>>().single(w).unwrap());
    let weapon = shown(w.query_filtered::<&Node, With<WeaponPlate>>().single(w).unwrap());
    let crosshair = w.query_filtered::<&BackgroundColor, With<CrosshairDot>>().single(w).unwrap().0.alpha() > 0.0;
    let ship = shown(w.query_filtered::<&Node, With<ShipCard>>().single(w).unwrap());
    (health, weapon, crosshair, ship)
}

#[test]
fn flying_and_the_whole_shot_down_card_hide_the_on_foot_cards() {
    let mut app = aloft_with_hud(600.0);
    let t = Tuning::default().ship_combat;
    assert_eq!(cards(&mut app), (false, false, false, true), "flying: the ship card, none of the on-foot cards");
    let fight = app.world().resource::<FlightHud>().fight.clone();
    assert_eq!((fight.hull, fight.max_hull, fight.shield, fight.missiles), (100.0, 100.0, 60.0, 4), "the Kestrel's hull, shield and rails");
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    assert_eq!(cards(&mut app), (false, false, false, false), "the wreck burning: nobody flies, and still nothing on foot");
    back_at_the_roost(&mut app, wreck);
    assert!(app.world().resource::<Downed>().showing());
    assert_eq!(cards(&mut app), (false, false, false, false), "on foot in the fresh Kestrel, the card still up");
    run(&mut app, t.loss_card);
    assert!(!app.world().resource::<Downed>().showing());
    assert_eq!(cards(&mut app), (true, true, true, false), "the card gone: on foot again");
}

#[test]
fn a_landed_shot_flashes_the_hit_marker_and_a_kill_the_kill_marker() {
    let (mut app, jackal) = gunnery_range(300.0);
    let fight = |app: &App| app.world().resource::<FlightHud>().fight.clone();
    assert_eq!(fight(&app).hit, 0.0);
    let mut ticks = 0;
    while fight(&app).hit == 0.0 && ticks < 66 {
        input(&mut app).fire_held = true;
        app.update();
        ticks += 1;
    }
    let f = fight(&app);
    assert!(f.hit > 0.0 && !f.kill, "a shot landed within a second: the hit marker, not a kill");
    // The last shots take a quarter of a second to reach it.
    run(&mut app, 0.3 + solar::cockpit::HIT_MARK + 0.1);
    assert_eq!(fight(&app).hit, 0.0, "it clears once the guns stop");
    while app.world().get_entity(jackal).is_ok() && ticks < 66 * 8 {
        input(&mut app).fire_held = true;
        app.update();
        ticks += 1;
    }
    assert!(app.world().get_entity(jackal).is_err(), "shot down");
    let f = fight(&app);
    assert!(f.kill && f.hit > solar::cockpit::HIT_MARK, "the kill marker, longer than a hit's");
    run(&mut app, solar::cockpit::KILL_MARK);
    assert_eq!(fight(&app).hit, 0.0);
}

#[test]
fn the_lock_ring_fills_as_the_lock_comes_on() {
    use solar::contacts::{lit, TICKS};
    let (mut app, _) = gunnery_range(800.0);
    let ship = ship_entity(&mut app);
    let mut seen = Vec::new();
    for _ in 0..(1.4 / DT) as usize {
        app.update();
        let lock = app.world().resource::<FlightHud>().fight.lock;
        assert_eq!(lock, missiles(&app, ship).lock, "the HUD reads the ship's own lock");
        seen.push(lit(lock));
    }
    assert!(seen.windows(2).all(|w| w[0] <= w[1]), "it only fills");
    assert!(seen.contains(&(TICKS / 2)) && seen.contains(&(TICKS - 1)), "through every stage: {seen:?}");
    assert_eq!(*seen.last().unwrap(), TICKS, "and whole once locked");
}

/// Runs `seconds`, doing `each` before every frame, and gathers every cue for the fight's sounds.
fn listen(app: &mut App, seconds: f32, mut each: impl FnMut(&mut App)) -> Vec<Cue> {
    let mut cursor = app.world().resource::<Messages<Cue>>().get_cursor_current();
    let mut heard = Vec::new();
    for _ in 0..(seconds / DT).round() as usize {
        each(app);
        app.update();
        heard.extend(cursor.read(app.world().resource::<Messages<Cue>>()).copied());
    }
    heard
}

fn of(cues: &[Cue], sfx: Sfx) -> Vec<Cue> {
    cues.iter().filter(|c| c.sfx == sfx).copied().collect()
}

#[test]
fn the_fights_sounds_are_cued_on_their_triggers_and_nothing_outside_carries_in_vacuum() {
    let (mut app, jackal) = gunnery_range(300.0);
    let ship = ship_entity(&mut app);
    // The lock comes on: beeps climbing in pitch, then none once it is locked.
    let heard = listen(&mut app, 1.4, |_| {});
    let beeps = of(&heard, Sfx::LockBeep);
    assert!(beeps.len() >= 4 && beeps.windows(2).all(|w| w[0].pitch < w[1].pitch), "rising beeps: {beeps:?}");
    assert!(of(&listen(&mut app, 0.5, |_| {}), Sfx::LockBeep).is_empty(), "locked: the steady tone, no beeps");
    // Your own guns and missile, in the cockpit at full level.
    let heard = listen(&mut app, 0.5, |app| input(app).fire_held = true);
    let guns = of(&heard, Sfx::Gun);
    assert!(guns.len() >= 2 && guns.iter().all(|c| c.volume == 1.0), "own guns: {guns:?}");
    let mut heard = listen(&mut app, DT, |app| input(app).aim_held = true);
    heard.extend(listen(&mut app, 0.1, |_| {}));
    assert!(of(&heard, Sfx::Launch).iter().any(|c| c.volume == 1.0), "own launch");
    // The Jackal's guns 300 m off, through Haven's air: heard, but quieter.
    let heard = listen(&mut app, 0.5, |app| app.world_mut().get_mut::<ShipControls>(jackal).unwrap().fire = true);
    let theirs: Vec<Cue> = of(&heard, Sfx::Gun).into_iter().filter(|c| c.volume < 1.0).collect();
    assert!(!theirs.is_empty() && theirs.iter().all(|c| c.volume > 0.2 && c.volume < 0.5), "another ship's guns at 300 m: {theirs:?}");
    // Hits on your own hull: the shield's sound, then the hull's once through it.
    let t = Tuning::default().ship_combat;
    app.world_mut().get_mut::<Hull>(ship).unwrap().hit(10.0, &t);
    let heard = listen(&mut app, 0.1, |_| {});
    assert_eq!((of(&heard, Sfx::ShieldHit).len(), of(&heard, Sfx::HullHit).len()), (1, 0), "shield hit");
    app.world_mut().get_mut::<Hull>(ship).unwrap().hit(60.0, &t);
    let heard = listen(&mut app, 0.1, |_| {});
    assert_eq!(of(&heard, Sfx::HullHit).len(), 1, "through the shield: the hull's clang");
    // The Jackal blown apart 300 m off: the wreck's deeper explosion, at less than full level.
    app.world_mut().get_mut::<Hull>(jackal).unwrap().hp = 0.0;
    let heard = listen(&mut app, 0.1, |_| {});
    let wreck = of(&heard, Sfx::Wreck);
    assert!(wreck.len() == 1 && wreck[0].volume > 0.3 && wreck[0].volume < 1.0 && wreck[0].pitch < 1.0, "{wreck:?}");

    // High above Haven's air the same guns are not heard at all, and your own still are.
    let (mut app, jackal) = gunnery_range(300.0);
    let (p, _) = ship_state(&mut app);
    put_ship(&mut app, p + p.normalize() * 150_000.0, Vec3::ZERO);
    run(&mut app, 0.1);
    let ship = ship_entity(&mut app);
    let tf = *app.world().get::<Transform>(ship).unwrap();
    let at = tf.translation + tf.rotation * Vec3::NEG_Z * 300.0;
    app.world_mut().entity_mut(jackal).insert((Transform::from_translation(at).with_rotation(tf.rotation), Position(at), Rotation(tf.rotation)));
    let heard = listen(&mut app, 0.5, |app| {
        input(app).fire_held = true;
        app.world_mut().get_mut::<ShipControls>(jackal).unwrap().fire = true;
    });
    let guns = of(&heard, Sfx::Gun);
    assert!(!guns.is_empty() && guns.iter().all(|c| c.volume == 1.0), "only your own guns in vacuum: {guns:?}");
}

#[test]
fn a_sentrys_lock_and_its_missile_set_off_the_warning() {
    let mut app = aloft(2000.0);
    let ship = ship_entity(&mut app);
    let rot = app.world().get::<Rotation>(ship).unwrap().0;
    enemy_near(&mut app, "sentry", rot * Vec3::new(0.0, 100.0, 700.0), Role::Raider);
    let mut threats = Vec::new();
    let heard = listen(&mut app, 10.0, |app| threats.push(app.world().resource::<FlightHud>().fight.threat));
    assert!(threats.contains(&Threat::Locked) && threats.contains(&Threat::Missile), "locked, then a missile in the air");
    let warnings = of(&heard, Sfx::Warning);
    assert!(warnings.len() >= 3, "it chirps: {}", warnings.len());
    // A Jackal holding you in its nose sets nothing off: it carries no missiles to fire.
    let mut app = aloft(2000.0);
    let ship = ship_entity(&mut app);
    let rot = app.world().get::<Rotation>(ship).unwrap().0;
    let jackal = enemy_near(&mut app, "jackal", rot * Vec3::new(0.0, 100.0, 700.0), Role::Raider);
    let heard = listen(&mut app, 3.0, |app| {
        app.world_mut().entity_mut(jackal).insert(Hull::new(1000.0, 1000.0));
    });
    assert!(of(&heard, Sfx::Warning).is_empty() && app.world().resource::<FlightHud>().fight.threat == Threat::None);
}

// ------------------------------------------------------------------------ faction standing

use solar::standing::{self as standing, StandingLine};

/// Your standing with `faction` in the running app's save.
fn standing_of(app: &App, faction: Faction) -> i32 {
    standing::get(app.world().resource::<Save>(), faction, &Tuning::default().ship_combat)
}

fn set_standing(app: &mut App, faction: Faction, v: i32) {
    app.world_mut().resource_mut::<Save>().standing.insert(faction.id().to_string(), v);
}

#[test]
fn a_new_save_starts_a_stranger_and_an_old_save_without_standing_still_loads() {
    let t = Tuning::default().ship_combat;
    let fresh = Save::default();
    assert_eq!(standing::FACTIONS.map(|f| standing::get(&fresh, f, &t)), [-20, 0, -20], "a stranger to the Regime and the PMC, neutral with the Scrappers");
    assert_eq!(standing::get(&fresh, Faction::Deserters, &t), 50);
    let path = std::env::temp_dir().join(format!("rust-regime-old-standing-{}.toml", std::process::id()));
    std::fs::write(&path, "banked = 500\nkills = 2\ndeaths = 1\n\n[faction_kills]\nraiders = 2\n").unwrap();
    let file = SaveFile(Some(path.clone()));
    let save = file.load();
    assert_eq!((save.banked, save.kills), (500, 2), "the old fields are kept");
    assert_eq!(standing::FACTIONS.map(|f| standing::get(&save, f, &t)), [-20, 0, -20], "and it starts where a new one does");
    let mut moved = save.clone();
    standing::shift(&mut moved, Faction::Scrappers, 35, &t);
    moved.standing_clock = 12.5;
    file.write(&moved);
    assert_eq!(file.load(), moved, "standing round-trips");
    std::fs::remove_file(&path).ok();
}

#[test]
fn shooting_down_a_raider_pleases_all_three_and_the_line_says_so() {
    let (mut app, jackal) = gunnery_range(300.0);
    hold_fire(&mut app, 4.0);
    run(&mut app, 0.2);
    assert!(app.world().get_entity(jackal).is_err(), "the Jackal is destroyed");
    assert_eq!(standing::FACTIONS.map(|f| standing_of(&app, f)), [-18, 2, -18]);
    let line = app.world().resource::<StandingLine>();
    assert_eq!(line.text(), "REGIME +2  SCRAPPERS +2  PMC +2");
    assert!(line.left > 0.0, "the line is up");
    run(&mut app, Tuning::default().ship_combat.standing_line);
    assert_eq!(app.world().resource::<StandingLine>().left, 0.0, "and gone a few seconds later");
}

/// The Kestrel 600 m up with a Censer patrol (for the Roost, so it is not culled) parked 300 m
/// off its nose, held still: the guns' target.
fn patrol_on_the_range() -> (App, Entity) {
    let (mut app, jackal) = gunnery_range(300.0);
    let tf = *app.world().get::<Transform>(jackal).unwrap();
    app.world_mut().despawn(jackal);
    let censer = spec_of(&app, "censer");
    let patrol = spawn_enemy(app.world_mut(), censer, tf.translation, tf.rotation, Vec3::ZERO, Role::Patrol { base: 0, slot: 9 });
    app.world_mut().entity_mut(patrol).insert((RigidBody::Static, Hull::new(10_000.0, 0.0)));
    run(&mut app, 0.1);
    (app, patrol)
}

#[test]
fn a_hit_on_a_patrol_costs_3_once_a_fight_and_its_kill_25_in_all_with_5_from_its_rival() {
    let (mut app, patrol) = patrol_on_the_range();
    let ship = ship_entity(&mut app);
    hold_fire(&mut app, 1.5);
    run(&mut app, 0.5);
    let hull = *app.world().get::<Hull>(patrol).unwrap();
    assert!(hull.hp < 10_000.0 - 3.0 * Tuning::default().ship_combat.gun_damage, "several hits landed: {}", hull.hp);
    assert_eq!(standing_of(&app, Faction::Regime), -23, "-3 for the first hit, and no more for the rest");
    assert!(app.world().get::<Enemy>(patrol).unwrap().provoked);
    assert_eq!(app.world().resource::<StandingLine>().text(), "REGIME -3");
    // Shot down by you: 25 in all, and the Scrappers, who hold a grudge against the Regime, like it.
    let mut hull = app.world_mut().get_mut::<Hull>(patrol).unwrap();
    (hull.hp, hull.last_hit_by) = (0.0, Some(ship));
    run(&mut app, 0.2);
    assert!(app.world().get_entity(patrol).is_err(), "shot down");
    assert_eq!((standing_of(&app, Faction::Regime), standing_of(&app, Faction::Scrappers), standing_of(&app, Faction::Pmc)), (-45, 5, -20));
    assert_eq!(app.world().resource::<StandingLine>().text(), "REGIME -25  SCRAPPERS +5", "the hit and the kill add up on the line");
    // A kill with no hit first costs the 25 on its own, and it clamps at -100.
    let (mut app, patrol) = patrol_on_the_range();
    set_standing(&mut app, Faction::Regime, -90);
    let ship = ship_entity(&mut app);
    let mut hull = app.world_mut().get_mut::<Hull>(patrol).unwrap();
    (hull.hp, hull.last_hit_by) = (0.0, Some(ship));
    run(&mut app, 0.2);
    assert_eq!(standing_of(&app, Faction::Regime), -100);
    assert_eq!(app.world().resource::<Save>().standing["regime"], -100);
}

#[test]
fn a_patrol_attacks_at_minus_20_leaves_you_be_at_0_and_comes_for_you_once_shot() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    let (base, up) = reliquary(&app);
    fly_to(&mut app, "bastion", base + up * 7500.0);
    run(&mut app, 0.5);
    put_ship(&mut app, base + up * 2000.0, Vec3::ZERO);
    run(&mut app, 0.3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m != Mode::Patrol), "at -20 they come for you, {:?}", patrol_modes(&mut app));
    put_ship(&mut app, base + up * 4500.0, Vec3::ZERO);
    run(&mut app, 0.3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m == Mode::Patrol), "and let you go");
    // At 10 they fly past.
    set_standing(&mut app, Faction::Regime, 10);
    put_ship(&mut app, base + up * 2000.0, Vec3::ZERO);
    run(&mut app, 1.0);
    assert_eq!(patrol_modes(&mut app), [Mode::Patrol, Mode::Patrol], "at 10 they leave you be");
    // Shoot one: it comes for you, and only it, since 7 is still friendly enough for the other.
    let ship = ship_entity(&mut app);
    let patrols: Vec<Entity> = enemies(&mut app).into_iter().filter(|e| matches!(e.1, Role::Patrol { .. })).map(|e| e.0).collect();
    app.world_mut().write_message(solar::combat::ShotLanded { by: ship, on: patrols[0] });
    run(&mut app, 0.3);
    assert_eq!(standing_of(&app, Faction::Regime), 7);
    let mode = |app: &App, e: Entity| app.world().get::<Enemy>(e).unwrap().mode;
    assert_ne!(mode(&app, patrols[0]), Mode::Patrol, "the one you shot comes for you");
    assert_eq!(mode(&app, patrols[1]), Mode::Patrol, "the other does not");
    // Once you are well away it lets you go and forgets; at 0 they both leave you be again.
    put_ship(&mut app, base + up * 4500.0, Vec3::ZERO);
    run(&mut app, 0.3);
    assert!(!app.world().get::<Enemy>(patrols[0]).unwrap().provoked, "the fight is over");
    set_standing(&mut app, Faction::Regime, 0);
    put_ship(&mut app, base + up * 2000.0, Vec3::ZERO);
    run(&mut app, 1.0);
    assert_eq!(patrol_modes(&mut app), [Mode::Patrol, Mode::Patrol], "at 0 they leave you be");
    // At 0 one hit makes the Regime hostile: both come for you.
    app.world_mut().write_message(solar::combat::ShotLanded { by: ship, on: patrols[1] });
    run(&mut app, 0.3);
    assert_eq!(standing_of(&app, Faction::Regime), -3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m != Mode::Patrol), "below 0 they all come for you, {:?}", patrol_modes(&mut app));
}

#[test]
fn the_scrappers_patrols_let_you_pass_at_the_start_until_you_shoot_one() {
    let mut app = system_app();
    run(&mut app, 1.0);
    board(&mut app);
    // The Yard's ground point and up on Cinder.
    let (base, up) = {
        let bases = app.world().resource::<solar::base::Bases>().clone();
        let solar = app.world().resource::<Solar>();
        let spec = bases.base.iter().find(|b| b.id == "yard").unwrap();
        let (ground, frame, deck) = solar::base::site(spec, &solar.spheres["cinder"], solar.pad);
        (ground + frame * Vec3::Y * deck, frame * Vec3::Y)
    };
    fly_to(&mut app, "cinder", base + up * 7500.0);
    run(&mut app, 0.5);
    assert_eq!(standing_of(&app, Faction::Scrappers), 0, "a new save is neutral with the Scrappers");
    put_ship(&mut app, base + up * 2000.0, Vec3::ZERO);
    run(&mut app, 1.0);
    assert_eq!(patrol_modes(&mut app), [Mode::Patrol, Mode::Patrol], "their Welders let you pass");
    let welder = spec_of(&app, "welder");
    let patrols: Vec<Entity> = enemies(&mut app).into_iter().filter(|e| matches!(e.1, Role::Patrol { .. })).map(|e| e.0).collect();
    assert!(patrols.iter().all(|e| app.world().get::<Ship>(*e).unwrap().spec == welder));
    let ship = ship_entity(&mut app);
    app.world_mut().write_message(solar::combat::ShotLanded { by: ship, on: patrols[0] });
    run(&mut app, 0.3);
    assert_eq!(standing_of(&app, Faction::Scrappers), -3);
    assert!(patrol_modes(&mut app).iter().all(|m| *m != Mode::Patrol), "shot at, they come for you: {:?}", patrol_modes(&mut app));
}

#[test]
fn at_minus_60_a_faction_sends_hunters_flying_its_patrol_hull() {
    let t = Tuning::default().ship_combat;
    let hunters = |app: &mut App| -> Vec<Entity> { enemies(app).into_iter().filter(|e| e.1 == Role::Hunter).map(|e| e.0).collect() };
    let mut app = aloft(3400.0);
    app.world_mut().resource_mut::<Raids>().aboard = t.raid_grace + 1.0;
    set_standing(&mut app, Faction::Pmc, -59);
    run(&mut app, 0.2);
    assert!(app.world().resource::<Raids>().hunts.is_empty(), "at -59 nobody hunts you");
    set_standing(&mut app, Faction::Pmc, -60);
    run(&mut app, 0.2);
    assert!(hunters(&mut app).is_empty(), "the hunters' clock has only just started");
    app.world_mut().resource_mut::<Raids>().hunts.insert("pmc".into(), t.raid_delay - 0.01);
    run(&mut app, 0.2);
    let pack = hunters(&mut app);
    assert!((t.hunt_pack[0]..=t.hunt_pack[1]).contains(&pack.len()), "a pack of two or three: {}", pack.len());
    let (sentry, ship) = (spec_of(&app, "sentry"), ship_entity(&mut app));
    let (from, _, _) = pose(&app, ship);
    for &e in &pack {
        assert_eq!(app.world().get::<Ship>(e).unwrap().spec, sentry, "the PMC hunts in Sentries");
        assert_eq!(*app.world().get::<Faction>(e).unwrap(), Faction::Pmc);
        let d = pose(&app, e).0.distance(from);
        assert!((t.spawn_near..=t.spawn_far).contains(&d), "came in {d:.0} m off, as raiders do");
    }
    assert!(enemies(&mut app).iter().all(|e| e.1 != Role::Raider), "the raiders keep their own clock");
    assert_eq!(app.world().resource::<Raids>().hunts["pmc"], 0.0, "and its clock starts again");
    // Back above -60, the hunt is off.
    set_standing(&mut app, Faction::Pmc, -50);
    run(&mut app, 0.1);
    assert!(app.world().resource::<Raids>().hunts.is_empty());
}

/// `stand_at_station`, with any station a test put there before taken away first.
fn only_station(app: &mut App, kind: StationKind, base: usize) {
    let old: Vec<Entity> = app.world_mut().query::<(Entity, &Station)>().iter(app.world()).filter(|(_, s)| s.label == "Test").map(|(e, _)| e).collect();
    for e in old {
        app.world_mut().despawn(e);
    }
    stand_at_station(app, kind, base);
}

#[test]
fn a_friendly_base_sells_for_less_a_wary_one_for_more_and_a_hostile_one_not_at_all() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let yard = 2;
    stand_at_station(&mut app, StationKind::Workshop, yard);
    let prompt = |app: &App| app.world().resource::<solar::station::Prompt>().text();
    // Friendly at 40: Mk1 for 15% off.
    set_standing(&mut app, Faction::Scrappers, 40);
    run(&mut app, 0.1);
    assert!(prompt(&app).contains("$255 (15% off)"), "{}", prompt(&app));
    app.world_mut().resource_mut::<Save>().banked = 255;
    press_use(&mut app);
    assert_eq!((app.world().resource::<Save>().ship_level, app.world().resource::<Save>().banked), (1, 0), "Mk1 for $255");
    // Below -40: Mk2 for 15% more.
    set_standing(&mut app, Faction::Scrappers, -41);
    app.world_mut().resource_mut::<Save>().banked = UPGRADE_COST[1];
    press_use(&mut app);
    assert_eq!(app.world().resource::<Save>().ship_level, 1, "too poor at the marked-up price");
    assert!(prompt(&app).contains(&format!("${}", (UPGRADE_COST[1] as f32 * 1.15).round() as u32)), "{}", prompt(&app));
    // At -60 it will not deal with you at all.
    set_standing(&mut app, Faction::Scrappers, -60);
    app.world_mut().resource_mut::<Save>().banked = 10_000;
    press_use(&mut app);
    assert_eq!((app.world().resource::<Save>().ship_level, app.world().resource::<Save>().banked), (1, 10_000), "refused");
    assert!(prompt(&app).contains("The Scrappers will not serve you"), "{}", prompt(&app));
    // Hated by the PMC, its courier desk still opens its board, while any other station of
    // Site Vantage's would refuse you.
    let vantage = 3;
    set_standing(&mut app, Faction::Pmc, -80);
    only_station(&mut app, StationKind::Contracts, vantage);
    press_use(&mut app);
    assert!(!prompt(&app).contains("will not serve"), "the board at -80: {}", prompt(&app));
    only_station(&mut app, StationKind::Workshop, vantage);
    app.world_mut().resource_mut::<Save>().ship_level = 1;
    press_use(&mut app);
    assert_eq!(app.world().resource::<Save>().ship_level, 1, "refused");
    assert!(prompt(&app).contains("The PMC will not serve you"), "{}", prompt(&app));
    // The shrine at the Reliquary, to a friend of the Regime: the tithe for 15% off.
    set_standing(&mut app, Faction::Regime, 40);
    only_station(&mut app, StationKind::Shrine, 1);
    app.world_mut().resource_mut::<Save>().banked = TITHE;
    press_use(&mut app);
    assert_eq!(app.world().resource::<Save>().banked, TITHE - (TITHE as f32 * 0.85).round() as u32, "blessed for less");
}

#[test]
fn a_parcel_to_a_friends_base_pays_a_fifth_more_and_raises_your_standing_there() {
    let deliver = |standing: i32| -> (u32, i32, String) {
        let mut app = system_app();
        run(&mut app, 1.0);
        set_standing(&mut app, Faction::Scrappers, standing);
        app.world_mut().resource_mut::<Save>().contracts = vec![parcel("yard", 250)];
        // A stand-in for the Yard (on Cinder) with its doorway where the player stands.
        let bases = app.world().resource::<solar::base::Bases>().clone();
        let yard = bases.base.iter().position(|b| b.id == "yard").unwrap();
        let at = player(&mut app).0 - Vec3::from(bases.base[yard].door);
        app.world_mut().spawn((solar::base::Base { spec: yard }, GlobalTransform::from_translation(at)));
        run(&mut app, 0.2);
        let save = app.world().resource::<Save>();
        assert!(save.contracts.is_empty(), "delivered");
        (save.banked, standing_of(&app, Faction::Scrappers), app.world().resource::<solar::station::Prompt>().text())
    };
    let (paid, after, _) = deliver(-20);
    assert_eq!((paid, after), (250, -10), "a stranger is paid the usual, and stands 10 better for it");
    let (paid, after, said) = deliver(40);
    assert_eq!((paid, after), (300, 50), "a friend is paid 20% more");
    assert!(said.contains("$50 for your standing"), "{said}");
}

// ------------------------------------------------------------------------------------ salvage

use solar::salvage::{self as salvage, Loot, Module, Pickup, SalvageLine};

/// Every pickup: its entity, what it holds and where it is in the world frame.
fn pickups(app: &mut App) -> Vec<(Entity, Loot, Vec3)> {
    app.world_mut().query::<(Entity, &Pickup, &Transform)>().iter(app.world()).map(|(e, p, tf)| (e, p.loot, tf.translation)).collect()
}

/// Puts salvage holding `loot` at `offset` (world frame) from the player, at rest.
fn salvage_near(app: &mut App, loot: Loot, offset: Vec3) -> Entity {
    let at = player(app).0 + offset;
    let pickup = Pickup::new(loot, Vec3::ZERO, &Tuning::default().ship_combat);
    app.world_mut().spawn((pickup, Transform::from_translation(at))).id()
}

#[test]
fn a_wreck_drops_its_scrap_where_it_died_drifting_with_it_until_it_times_out() {
    let t = Tuning::default().ship_combat;
    let (mut app, jackal) = gunnery_range(300.0);
    // Modules come later: here every wreck drops only its scrap.
    app.world_mut().resource_mut::<Tuning>().ship_combat.module_chance = 0.0;
    let at = app.world().get::<Transform>(jackal).unwrap().translation;
    app.world_mut().get_mut::<Hull>(jackal).unwrap().hp = 0.0;
    run(&mut app, 0.1);
    assert!(app.world().get_entity(jackal).is_err(), "shot down");
    let dropped = pickups(&mut app);
    assert_eq!(dropped.len(), 1, "a Jackal's scrap");
    assert_eq!(dropped[0].1, Loot::Scrap(2));
    assert!(dropped[0].2.distance(at) < 0.5, "where it blew apart: {} m off", dropped[0].2.distance(at));
    // 300 m off is out of the Kestrel's reach: it hangs there.
    run(&mut app, 1.0);
    assert_eq!((pickups(&mut app).len(), app.world().resource::<Save>().scrap), (1, 0));
    // A wreck that was moving (a Welder another ship shot down, 300 m off) carries its scrap on,
    // slowing in the air.
    let welder = spec_of(&app, "welder");
    let v = Vec3::new(0.0, 0.0, -50.0);
    app.world_mut().write_message(solar::combat::ShipDestroyed { ship: Entity::PLACEHOLDER, spec: welder, faction: Faction::Scrappers, killer: None, at: at + Vec3::X * 40.0, velocity: v });
    run(&mut app, 1.0);
    let (moving, loot, p) = pickups(&mut app).into_iter().find(|(_, l, _)| *l == Loot::Scrap(8)).expect("the Welder's scrap");
    let gone = (p - (at + Vec3::X * 40.0)).dot(v.normalize());
    assert!(loot == Loot::Scrap(8) && gone > 40.0 && gone < 50.0, "drifted {gone} m on in a second");
    let speed = app.world().get::<Pickup>(moving).unwrap().velocity.length();
    assert!(speed < 50.0 && speed > 40.0, "slowed by the air: {speed}");
    assert_eq!(app.world().get::<Pickup>(moving).unwrap().life.round(), t.scrap_life - 1.0, "90 s to live");
    // And once that is up it is gone.
    app.world_mut().get_mut::<Pickup>(moving).unwrap().life = 0.5;
    run(&mut app, 1.0);
    assert!(app.world().get_entity(moving).is_err(), "timed out");
    assert_eq!(pickups(&mut app).len(), 1, "the Jackal's scrap is still there");
}

#[test]
fn salvage_is_pulled_in_from_40_m_by_the_ship_you_fly_and_never_on_foot() {
    let mut app = aloft(600.0);
    let near = salvage_near(&mut app, Loot::Scrap(4), Vec3::X * 30.0);
    let far = salvage_near(&mut app, Loot::Scrap(5), Vec3::X * -50.0);
    let cues = listen(&mut app, 1.0, |_| {});
    assert!(app.world().get_entity(near).is_err(), "30 m off: pulled in and aboard");
    assert!(app.world().get_entity(far).is_ok(), "50 m off: out of reach");
    assert_eq!(app.world().resource::<Save>().scrap, 4);
    let line = app.world().resource::<SalvageLine>();
    assert_eq!(line.text(), "+4 SCRAP");
    assert!(line.left > 0.0, "the line is up");
    assert_eq!(of(&cues, Sfx::Scrap).len(), 1, "a clink as it comes aboard");
    run(&mut app, Tuning::default().ship_combat.scrap_line);
    assert_eq!(app.world().resource::<SalvageLine>().left, 0.0, "and gone a few seconds later");
    // On foot beside the parked Kestrel nothing pulls it in, the ship included.
    let mut app = system_app();
    run(&mut app, 1.0);
    let ship = ship_entity(&mut app);
    let beside = (app.world().get::<Transform>(ship).unwrap().translation - player(&mut app).0) * 0.5;
    let lying = salvage_near(&mut app, Loot::Scrap(4), beside + Vec3::Y * 3.0);
    run(&mut app, 1.0);
    assert!(app.world().get_entity(lying).is_ok(), "on foot it stays where it is");
    assert_eq!(app.world().resource::<Save>().scrap, 0);
}

#[test]
fn a_full_hold_leaves_scrap_floating() {
    let mut app = aloft(600.0);
    app.world_mut().resource_mut::<Save>().scrap = 60;
    let near = salvage_near(&mut app, Loot::Scrap(4), Vec3::X * 30.0);
    run(&mut app, 1.0);
    assert!(app.world().get_entity(near).is_ok(), "no room: it stays out there");
    assert_eq!(app.world().resource::<Save>().scrap, 60);
    assert_eq!(app.world().resource::<SalvageLine>().text(), "HOLD FULL");
    // A level of plating makes room for it.
    app.world_mut().resource_mut::<Save>().ship_parts[0] = 1;
    run(&mut app, 1.0);
    assert!(app.world().get_entity(near).is_err(), "aboard once there is room");
    assert_eq!(app.world().resource::<Save>().scrap, 64);
}

/// Stands the player on foot in the Roost's doorway.
fn at_the_roost_door(app: &mut App) {
    let bases = app.world().resource::<solar::base::Bases>().clone();
    let (at, base) = app.world_mut().query::<(&GlobalTransform, &solar::base::Base)>().single(app.world()).map(|(g, b)| (*g, b.spec)).unwrap();
    let door = at.translation() + at.rotation() * Vec3::from(bases.base[base].door);
    set_player(app, door, Vec3::ZERO);
}

#[test]
fn the_pocket_banks_and_the_landed_ship_is_repaired_at_a_bases_door() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let ship = ship_entity(&mut app);
    let max = app.world().get::<Hull>(ship).unwrap().max_hp;
    app.world_mut().get_mut::<Hull>(ship).unwrap().hp = max - 30.0;
    {
        let mut save = app.world_mut().resource_mut::<Save>();
        save.pocket = 200;
        save.banked = 100;
    }
    at_the_roost_door(&mut app);
    run(&mut app, 0.2);
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.banked, save.pocket), (270, 0), "+200 banked, -30 for the repair");
    assert_eq!(app.world().get::<Hull>(ship).unwrap().hp, max, "repaired");
    let prompt = app.world().resource::<solar::station::Prompt>().text();
    assert!(prompt.contains("Banked $200") && prompt.contains("Repaired 30 hull: -$30"), "{prompt}");
    // Standing there does it once.
    app.world_mut().get_mut::<Hull>(ship).unwrap().hp = max - 10.0;
    run(&mut app, 1.0);
    assert_eq!(app.world().resource::<Save>().banked, 270, "once per arrival");
    // A new bounty banks while you stand there.
    app.world_mut().resource_mut::<Save>().pocket = 60;
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Save>().banked, 330);
}

#[test]
fn a_wreck_of_your_own_ship_drops_nothing() {
    let mut app = aloft(600.0);
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    assert_eq!(app.world().resource::<Downed>().wreck, Some(wreck), "shot down");
    assert!(pickups(&mut app).is_empty(), "no scrap from your own ship");
}

#[test]
fn salvage_left_behind_at_a_handoff_is_gone() {
    let mut app = aloft(600.0);
    let left = salvage_near(&mut app, Loot::Scrap(4), Vec3::X * 2000.0);
    run(&mut app, 0.2);
    assert!(app.world().get_entity(left).is_ok());
    let (ground, up) = reliquary(&app);
    fly_to(&mut app, "bastion", ground + up * 3000.0);
    assert!(app.world().get_entity(left).is_err(), "dropped with the old world's frame");
}

#[test]
fn an_old_save_without_salvage_still_loads() {
    let path = std::env::temp_dir().join(format!("rust-regime-old-salvage-{}.toml", std::process::id()));
    std::fs::write(&path, "banked = 500\nship_level = 2\nkills = 2\n\n[standing]\nregime = 10\n").unwrap();
    let file = SaveFile(Some(path.clone()));
    let save = file.load();
    assert_eq!((save.banked, save.ship_level, save.kills, save.standing["regime"]), (500, 2, 2, 10), "the old fields are kept");
    assert_eq!((save.scrap, save.ship_parts, save.modules.len(), save.fitted.len()), (0, [0; 4], 0, 0), "and it starts with no salvage");
    let salvaged = Save { scrap: 37, ship_parts: [1, 0, 3, 2], modules: vec!["ram".into(), "spire".into()], fitted: vec!["spire".into()], ..save };
    file.write(&salvaged);
    assert_eq!(file.load(), salvaged, "salvage round-trips");
    std::fs::remove_file(&path).ok();
}

#[test]
fn the_yards_parts_rack_opens_its_menu_and_sells_for_scrap_at_the_scrappers_prices() {
    use crate::menu::{Menu, Panel, Screen};
    let mut app = counter_app();
    let yard = 2;
    stand_at_station(&mut app, StationKind::Parts, yard);
    app.world_mut().resource_mut::<Save>().scrap = 30;
    run(&mut app, 0.1);
    let prompt = |app: &App| app.world().resource::<solar::station::Prompt>().text();
    assert!(prompt(&app).contains("fit parts to the Kestrel for scrap (30 scrap)"), "{}", prompt(&app));
    press_use(&mut app);
    run(&mut app, 0.2);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Paused);
    let menu = app.world().resource::<Menu>();
    assert_eq!((menu.panel, menu.from_station, menu.rack), (Panel::Parts, true, Faction::Scrappers));
    // Enter buys hull plating Mk1 (12); down a row, the shield cell Mk1 (12); then Mk2 is short.
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().scrap, app.world().resource::<Save>().ship_parts), (18, [1, 0, 0, 0]));
    assert!(app.world().resource::<Menu>().note.contains("-12 scrap"), "{}", app.world().resource::<Menu>().note);
    tap(&mut app, KeyCode::KeyS);
    tap(&mut app, KeyCode::Enter);
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().scrap, app.world().resource::<Save>().ship_parts), (6, [1, 1, 0, 0]));
    assert!(app.world().resource::<Menu>().note.contains("18 scrap short"), "{}", app.world().resource::<Menu>().note);
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing, "back to the game");
    // A friend of the Scrappers pays 15% less: the missile rack's 15 for 13.
    set_standing(&mut app, Faction::Scrappers, 40);
    app.world_mut().resource_mut::<Save>().scrap = 100;
    press_use(&mut app);
    run(&mut app, 0.2);
    for _ in 0..3 {
        tap(&mut app, KeyCode::KeyS);
    }
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().scrap, app.world().resource::<Save>().ship_parts[3]), (87, 1), "Mk1 rack for 13");
    tap(&mut app, KeyCode::Escape);
    // The row under the parts sells the hold: 87 scrap from a friend's $7, a little less as the
    // Yard's stock fills.
    press_use(&mut app);
    run(&mut app, 0.2);
    let banked = app.world().resource::<Save>().banked;
    let (_, worth) = solar::economy::sale(app.world().resource::<Save>(), "yard", Faction::Scrappers, &Tuning::default().economy, &Tuning::default().ship_combat);
    assert!(worth < 87 * 7 && worth > 87 * 6, "{worth}");
    for _ in 0..4 {
        tap(&mut app, KeyCode::KeyS);
    }
    tap(&mut app, KeyCode::Enter);
    assert_eq!((app.world().resource::<Save>().scrap, app.world().resource::<Save>().banked), (0, banked + worth), "sold to a friend");
    assert_eq!(app.world().resource::<Menu>().note, format!("Sold 87 scrap: +${worth}"));
    assert_eq!(app.world().resource::<Save>().yard_stock.map(|s| s.round()), Some(387.0), "on the Yard's stockpile");
    // The row under that buys a lot back at half again over the Yard's price.
    let banked = app.world().resource::<Save>().banked;
    tap(&mut app, KeyCode::KeyS);
    tap(&mut app, KeyCode::Enter);
    let save = app.world().resource::<Save>().clone();
    assert_eq!(save.scrap, 10);
    assert!(banked - save.banked >= 10 * 5, "{} for 10", banked - save.banked);
    tap(&mut app, KeyCode::KeyW);
    app.world_mut().resource_mut::<Save>().scrap = 0;
    tap(&mut app, KeyCode::Enter);
    assert_eq!(app.world().resource::<Menu>().note, "The hold is empty");
    tap(&mut app, KeyCode::Escape);
    app.world_mut().resource_mut::<Save>().scrap = 87;
    // At -60 the Yard will not sell to you: the menu does not open.
    set_standing(&mut app, Faction::Scrappers, -60);
    press_use(&mut app);
    run(&mut app, 0.2);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    assert!(prompt(&app).contains("The Scrappers will not serve you"), "{}", prompt(&app));
    assert_eq!(app.world().resource::<Save>().scrap, 87);
}

#[test]
fn parts_land_on_a_fresh_kestrel_and_are_kept_after_being_shot_down() {
    let t = Tuning::default().ship_combat;
    let mut app = aloft(600.0);
    let ship = ship_entity(&mut app);
    app.world_mut().resource_mut::<Save>().ship_parts = [3, 2, 0, 1];
    run(&mut app, 0.1);
    let h = *app.world().get::<Hull>(ship).unwrap();
    assert_eq!((h.hp, h.max_hp, h.shield, h.max_shield), (175.0, 175.0, 90.0, 90.0), "+75 hull and +30 shield");
    assert!((h.regen - 1.4).abs() < 1e-5, "the shield comes back 40% faster: {}", h.regen);
    assert_eq!(missiles(&app, ship).count, t.missiles + 1, "one more missile on the rack");
    assert_eq!(app.world().resource::<crate::hud::FlightHud>().fight.max_hull, 175.0, "the HUD's hull bar runs to the new top");
    // The gun capacitor: three levels heat the guns well under half as fast.
    let heat = |level: u8| -> f32 {
        let mut app = aloft(600.0);
        app.world_mut().resource_mut::<Save>().ship_parts[2] = level;
        run(&mut app, 0.1);
        hold_fire(&mut app, 2.0);
        let ship = ship_entity(&mut app);
        app.world().get::<Gun>(ship).unwrap().heat
    };
    let (stock, cooled) = (heat(0), heat(3));
    assert!(stock > 0.2 && cooled < stock * 0.5, "two seconds of fire: stock {stock}, capacitor Mk3 {cooled}");
    // Shot down, the fresh Kestrel on the pad has them all.
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    back_at_the_roost(&mut app, wreck);
    assert_eq!(app.world().resource::<Save>().ship_parts, [3, 2, 0, 1], "kept");
    let kestrel = ship_entity(&mut app);
    let h = *app.world().get::<Hull>(kestrel).unwrap();
    assert_eq!((h.hp, h.shield), (175.0, 90.0));
    assert_eq!(missiles(&app, kestrel).count, t.missiles + 1);
}

#[test]
fn a_wreck_drops_its_module_beside_its_scrap_and_a_spare_turns_into_scrap() {
    let (mut app, jackal) = gunnery_range(30.0);
    // Every wreck drops its module here (the rate itself is the seeded roll's, in `salvage`).
    app.world_mut().resource_mut::<Tuning>().ship_combat.module_chance = 1.0;
    let at = app.world().get::<Transform>(jackal).unwrap();
    let (at, facing) = (at.translation, at.rotation);
    let kill = |app: &mut App, target: Entity| -> Vec<Cue> {
        app.world_mut().get_mut::<Hull>(target).unwrap().hp = 0.0;
        listen(app, 1.0, |_| {})
    };
    let heard = kill(&mut app, jackal);
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.scrap, save.modules.clone()), (2, vec!["afterburner".to_string()]), "a Jackal's two scrap and its afterburner, both pulled in from 30 m");
    assert!(pickups(&mut app).is_empty());
    assert_eq!(app.world().resource::<SalvageLine>().text(), "+2 SCRAP  MODULE FOUND  AFTERBURNER");
    assert_eq!(of(&heard, Sfx::Module).len(), 1, "the module's chime");
    // A second Jackal's afterburner, once the line has gone, is a spare: ten scrap instead.
    run(&mut app, Tuning::default().ship_combat.scrap_line);
    let spec = spec_of(&app, "jackal");
    let again = solar::ship::spawn(app.world_mut(), spec, Transform::from_translation(at).with_rotation(facing));
    app.world_mut().entity_mut(again).insert((RigidBody::Static, Position(at), Rotation(facing)));
    run(&mut app, 0.1);
    kill(&mut app, again);
    let save = app.world().resource::<Save>().clone();
    assert_eq!((save.scrap, save.modules.len()), (2 + 2 + 10, 1), "a spare turns into scrap");
    assert_eq!(app.world().resource::<SalvageLine>().text(), "+12 SCRAP  SPARE AFTERBURNER");
}

#[test]
fn modules_fit_two_at_a_time_from_the_ship_screen() {
    use crate::menu::{Menu, Panel, Screen};
    let mut app = counter_app();
    app.world_mut().resource_mut::<Save>().modules = ["afterburner", "spire", "ram"].map(String::from).to_vec();
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Paused);
    app.world_mut().resource_mut::<Menu>().panel = Panel::Ship;
    app.update();
    let fitted = |app: &App| salvage::fitted(app.world().resource::<Save>());
    // Slot 1: right fits the first you own. Slot 2 steps past it, then round to empty.
    tap(&mut app, KeyCode::KeyD);
    assert_eq!(fitted(&app), [Module::Afterburner]);
    tap(&mut app, KeyCode::KeyS);
    for want in [vec![Module::Afterburner, Module::Spire], vec![Module::Afterburner, Module::Ram], vec![Module::Afterburner]] {
        tap(&mut app, KeyCode::KeyD);
        assert_eq!(fitted(&app), want);
    }
    tap(&mut app, KeyCode::KeyA);
    assert_eq!(fitted(&app), [Module::Afterburner, Module::Ram]);
    assert_eq!(app.world().resource::<Save>().fitted.len(), 2, "never more than two");
    // On the Kestrel at once.
    let ship = ship_entity(&mut app);
    tap(&mut app, KeyCode::Escape);
    tap(&mut app, KeyCode::Escape);
    assert_eq!(*app.world().resource::<State<Screen>>().get(), Screen::Playing);
    run(&mut app, 0.1);
    let refit = *app.world().get::<salvage::Refit>(ship).unwrap();
    assert_eq!((refit.boost_refill > 1.0, refit.ram), (true, 30.0), "the afterburner and the ram plate are on");
}

/// The Kestrel 600 m up with `modules` fitted.
fn fitted_aloft(modules: &[&str]) -> App {
    let mut app = aloft(600.0);
    {
        let mut save = app.world_mut().resource_mut::<Save>();
        save.modules = modules.iter().map(|m| m.to_string()).collect();
        save.fitted = save.modules.clone();
    }
    run(&mut app, 0.1);
    app
}

#[test]
fn the_afterburner_refills_the_boost_faster_for_less_shield() {
    let refilled = |modules: &[&str]| -> (f32, f32) {
        let mut app = fitted_aloft(modules);
        let ship = ship_entity(&mut app);
        let mut s = app.world_mut().get_mut::<Ship>(ship).unwrap();
        (s.boost_used, s.boost_idle) = (1.0, 2.0);
        run(&mut app, 1.0);
        (1.0 - app.world().get::<Ship>(ship).unwrap().boost_used, app.world().get::<Hull>(ship).unwrap().max_shield)
    };
    let ((stock, shield), (burner, less)) = (refilled(&[]), refilled(&["afterburner"]));
    assert!((burner / stock - 1.4).abs() < 0.05, "refills {burner} a second against {stock}");
    assert_eq!((shield, less), (60.0, 54.0), "for a tenth of the shield");
}

#[test]
fn the_targeting_array_locks_in_0_8_s_in_a_tighter_cone() {
    let lock = |modules: &[&str], degrees: f32| -> (bool, bool) {
        let (mut app, jackal) = gunnery_range(800.0);
        {
            let mut save = app.world_mut().resource_mut::<Save>();
            save.modules = modules.iter().map(|m| m.to_string()).collect();
            save.fitted = save.modules.clone();
        }
        off_nose(&mut app, jackal, 800.0, degrees);
        let ship = ship_entity(&mut app);
        run(&mut app, 0.85);
        let early = missiles(&app, ship).locked() == Some(jackal);
        run(&mut app, 0.5);
        (early, missiles(&app, ship).locked() == Some(jackal))
    };
    assert_eq!(lock(&[], 1.0), (false, true), "stock: not at 0.85 s, locked by 1.35");
    assert_eq!(lock(&["targeting"], 1.0), (true, true), "the array locks by 0.85 s");
    assert_eq!(lock(&[], 3.0), (false, true), "3 degrees off is inside the stock cone");
    assert_eq!(lock(&["targeting"], 3.0), (false, false), "and outside the array's, 4 degrees tighter");
}

#[test]
fn the_spire_coil_fires_faster_harder_shots_that_heat_the_guns_faster() {
    let t = Tuning::default().ship_combat;
    let shoot = |modules: &[&str]| -> (f32, f32, f32) {
        let (mut app, jackal) = gunnery_range(300.0);
        app.world_mut().entity_mut(jackal).insert(Hull::new(10_000.0, 0.0));
        {
            let mut save = app.world_mut().resource_mut::<Save>();
            save.modules = modules.iter().map(|m| m.to_string()).collect();
            save.fitted = save.modules.clone();
        }
        run(&mut app, 0.1);
        hold_fire(&mut app, 1.0 / 66.0);
        let ship = ship_entity(&mut app);
        let heat = app.world().get::<Gun>(ship).unwrap().heat;
        let speed = app.world_mut().query::<&solar::combat::Projectile>().iter(app.world()).map(|p| p.velocity.length()).fold(0.0, f32::max);
        hold_fire(&mut app, 0.3);
        run(&mut app, 0.5);
        (heat, speed, 10_000.0 - app.world().get::<Hull>(jackal).unwrap().hp)
    };
    let ((heat, speed, hurt), (hot, fast, harder)) = (shoot(&[]), shoot(&["spire"]));
    assert!((heat - t.heat_per_shot).abs() < 1e-5 && (hot - t.heat_per_shot * 1.2).abs() < 1e-5, "a shot's heat: {heat}, with the coil {hot}");
    // A shot loses a little to the air in its first tick.
    assert!((speed / t.gun_speed - 1.0).abs() < 0.01 && (fast / speed - 1.25).abs() < 0.01, "muzzle speed {speed}, with the coil {fast}");
    let hits = |hurt: f32, each: f32| (hurt / each).round();
    assert!(hurt > 0.0 && (hurt / t.gun_damage - hits(hurt, t.gun_damage)).abs() < 1e-3, "12 a hit: {hurt}");
    assert!(harder > 0.0 && (harder / (t.gun_damage * 1.15) - hits(harder, t.gun_damage * 1.15)).abs() < 1e-3, "13.8 a hit: {harder}");
}

#[test]
fn the_ram_plate_hurts_what_you_ram_for_30_and_costs_a_tenth_of_the_thrust() {
    let pushed = |modules: &[&str]| -> f32 {
        let mut app = fitted_aloft(modules);
        input(&mut app).thrust = 1.0;
        run(&mut app, 0.5);
        ship_state(&mut app).1.length()
    };
    let (stock, rammer) = (pushed(&[]), pushed(&["ram"]));
    assert!((rammer / stock - 0.9).abs() < 0.03, "half a second of thrust: {rammer} m/s against {stock}");
    // Fly into a parked Jackal 25 m ahead.
    let (mut app, jackal) = gunnery_range(25.0);
    {
        let mut save = app.world_mut().resource_mut::<Save>();
        save.modules = vec!["ram".into()];
        save.fitted = vec!["ram".into()];
    }
    run(&mut app, 0.1);
    app.world_mut().entity_mut(jackal).insert(Hull::new(1000.0, 30.0));
    for _ in 0..(2.0 / DT) as usize {
        input(&mut app).thrust = 1.0;
        app.update();
    }
    let ship = ship_entity(&mut app);
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp, h.last_hit_by), (0.0, 1000.0, Some(ship)), "rammed once for 30, the shield first");
    // Without the plate a bump does nothing.
    let (mut app, jackal) = gunnery_range(25.0);
    app.world_mut().entity_mut(jackal).insert(Hull::new(1000.0, 30.0));
    for _ in 0..(2.0 / DT) as usize {
        input(&mut app).thrust = 1.0;
        app.update();
    }
    let h = *app.world().get::<Hull>(jackal).unwrap();
    assert_eq!((h.shield, h.hp), (30.0, 1000.0), "no plate, no harm");
}

#[test]
fn fitted_modules_are_kept_through_being_shot_down() {
    let mut app = fitted_aloft(&["spire", "afterburner"]);
    let wreck = shoot_down(&mut app);
    run(&mut app, 0.2);
    back_at_the_roost(&mut app, wreck);
    let save = app.world().resource::<Save>().clone();
    assert_eq!(salvage::fitted(&save), [Module::Spire, Module::Afterburner], "kept");
    let kestrel = ship_entity(&mut app);
    assert_eq!(*app.world().get::<salvage::Refit>(kestrel).unwrap(), salvage::Refit::of(&save, &Tuning::default().ship_combat), "on the fresh Kestrel");
    assert_eq!(app.world().get::<Hull>(kestrel).unwrap().max_shield, 54.0, "the afterburner's cost too");
}

#[test]
fn the_hud_shows_your_scrap_beside_the_bank() {
    let e = Tuning::default().economy;
    assert_eq!(crate::hud::haul(&Save { banked: 750, scrap: 12, ..default() }, &e), "BANK 750   SCRAP 12/60");
    assert_eq!(crate::hud::haul(&Save { banked: 750, pocket: 120, scrap: 12, ship_parts: [1, 0, 0, 0], ..default() }, &e), "BANK 750 +120   SCRAP 12/80");
}

