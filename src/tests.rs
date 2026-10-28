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
use crate::targets::Soldier;
use crate::tuning::Tuning;
use crate::targets::{self, Target, TargetsPlugin};
use crate::planet::{self, chunk::{self, ChunkMesh}, quadtree::{self, NodeId}};
use crate::planet::gravity::gravitate;
use crate::surface::testing::random_dirs;
use crate::surface::{Origin, Sphere, Surface, QUANTUM};
use crate::system::Body;
use crate::loot::{self, ExtractPad, Inventory, Loot, LootPlugin, Save, SaveFile};
use crate::targets::{Killed, Team};
use crate::weapon::Damage;
use crate::vehicle::{self, Driving, Kind, Vehicle, VehiclePlugin};
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
        .add_plugins((ControllerPlugin, WeaponPlugin, TargetsPlugin, HealthPlugin, VehiclePlugin, LootPlugin, crate::abilities::AbilitiesPlugin));
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
        TargetsPlugin,
        HealthPlugin,
        crate::hud::HudPlugin,
        VehiclePlugin,
        LootPlugin,
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
fn dummy_dies_falls_and_respawns() {
    let tuning = Tuning::default();
    let mut app = make_app(tuning.clone());
    let feet = controller::SPAWN + Vec3::new(0.0, -1.0, -8.0);
    let t = app.world().resource::<Tuning>().clone();
    targets::spawn_dummy(&mut app.world_mut().commands(), &t, None, feet, 0.0);
    app.update();
    let mut q = app.world_mut().query_filtered::<Entity, With<Target>>();
    let dummy = q.single(app.world()).unwrap();

    select_weapon(&mut app, WeaponKind::Rifle);
    input(&mut app).fire_held = true;
    run(&mut app, 1.0);
    input(&mut app).fire_held = false;
    let target = app.world().get::<Target>(dummy).unwrap();
    let home = target.home;
    assert!(!target.alive(), "rifle fire for a second kills a {} hp dummy", tuning.target_health);
    assert_eq!(*app.world().get::<RigidBody>(dummy).unwrap(), RigidBody::Dynamic);
    let score = app.world().resource::<targets::Score>();
    assert!(score.kills == 1 && score.hits >= 2, "{score:?}");

    run(&mut app, 0.5);
    let fallen = app.world().get::<Transform>(dummy).unwrap().translation;
    assert!(fallen.y < home.y - 0.2 || fallen.z < feet.z - 0.3, "dummy was knocked over: {fallen}");

    run(&mut app, tuning.target_respawn + 0.2);
    let target = app.world().get::<Target>(dummy).unwrap();
    assert!(target.alive());
    assert_eq!(*app.world().get::<RigidBody>(dummy).unwrap(), RigidBody::Static);
    let pos = app.world().get::<Transform>(dummy).unwrap().translation;
    assert!(pos.distance(home) < 0.05, "back home: {pos}");
}

#[test]
fn rocket_damages_targets() {
    let mut app = make_app(Tuning::default());
    let feet = controller::SPAWN + Vec3::new(0.0, -1.0, -8.0);
    let t = app.world().resource::<Tuning>().clone();
    targets::spawn_dummy(&mut app.world_mut().commands(), &t, None, feet, 0.0);
    app.update();
    input(&mut app).fire_held = true;
    run(&mut app, 0.6);
    let mut q = app.world_mut().query::<&Target>();
    let target = q.single(app.world()).unwrap();
    assert!(target.health < Tuning::default().target_health, "rocket splash hurt the dummy: {}", target.health);
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
    let mut tuning = Tuning::default();
    tuning.terrain.cell = cell;
    let mut app = build_app(tuning);
    drop_flat_floor(&mut app);
    let sphere = Arc::new(Sphere::new(Body::test_moon()));
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

fn soldier(app: &mut App, route: Vec<Vec3>) {
    app.world_mut()
        .run_system_once(move |mut commands: Commands, tuning: Res<Tuning>| targets::spawn_soldier(&mut commands, &tuning, None, route.clone()))
        .unwrap();
    app.update();
}

fn soldier_state(app: &mut App) -> (Vec3, Option<f32>) {
    let mut q = app.world_mut().query::<(&Soldier, &Transform)>();
    let (s, tf) = q.single(app.world()).unwrap();
    (tf.translation, s.alert)
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
fn big_hits_bleed_until_a_medkit() {
    let mut app = make_app(Tuning::default());
    hit_player(&mut app, 30.0);
    run(&mut app, 2.0);
    let h = app.world().resource::<PlayerHealth>().clone();
    assert!(h.bleeding > 0.0 && h.hp < 67.0 && h.hp > 64.0, "bleeding 2 hp/s: {h:?}");
    let (pos, _, _) = player(&mut app);
    app.world_mut().spawn((loot::Medkit { down: 0.0 }, Transform::from_translation(pos), Visibility::default()));
    run(&mut app, 0.1);
    let h = app.world().resource::<PlayerHealth>().clone();
    assert!(h.hp == 100.0 && h.bleeding <= 0.0, "healed: {h:?}");
    let mut q = app.world_mut().query::<(&loot::Medkit, &Visibility)>();
    let (kit, vis) = q.single(app.world()).unwrap();
    assert!(kit.down > 0.0 && *vis == Visibility::Hidden, "the medkit is used up for a while");
}

#[test]
fn soldier_shoots_player_in_sight() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    soldier(&mut app, vec![Vec3::new(10.0, 0.0, 0.0), Vec3::new(10.0, 0.0, 6.0)]);
    run(&mut app, 1.5);
    let (_, alert) = soldier_state(&mut app);
    assert!(alert.is_some(), "soldier is alert");
    let hp = app.world().resource::<PlayerHealth>().hp;
    assert!(hp < 100.0 - 10.0, "player was shot, hp {hp}");
}

#[test]
fn soldier_ignores_player_behind_wall_and_patrols() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    wall(&mut app, Vec3::new(1.0, 6.0, 30.0), Vec3::new(5.0, 3.0, 0.0));
    soldier(&mut app, vec![Vec3::new(10.0, 0.0, 0.0), Vec3::new(10.0, 0.0, 6.0)]);
    let (start, _) = soldier_state(&mut app);
    run(&mut app, 1.5);
    let (pos, alert) = soldier_state(&mut app);
    assert!(alert.is_none(), "not alert");
    assert!((pos - start).length() > 2.0, "kept walking its route, moved {}", (pos - start).length());
    assert_eq!(app.world().resource::<PlayerHealth>().hp, 100.0);
}

#[test]
fn soldier_forgets_hidden_player() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    soldier(&mut app, vec![Vec3::new(10.0, 0.0, 0.0), Vec3::new(10.0, 0.0, 6.0)]);
    run(&mut app, 0.5);
    assert!(soldier_state(&mut app).1.is_some());
    // Out of sight range but still on the floor (off the floor you fall and respawn in view).
    set_player(&mut app, Vec3::new(0.0, 1.0, -80.0), Vec3::ZERO);
    run(&mut app, 2.0);
    assert!(soldier_state(&mut app).1.is_some(), "still alert before forget");
    run(&mut app, 2.5);
    assert!(soldier_state(&mut app).1.is_none(), "forgot the player");
}

// ---------------------------------------------------------------------------
// Vehicles

/// An app whose world gravity matches the controller's, as in the game.
fn vehicle_app() -> App {
    let mut app = make_app(Tuning::default());
    let g = app.world().resource::<Tuning>().gravity;
    app.insert_resource(Gravity(Vec3::NEG_Y * g));
    app
}

fn spawn_vehicle(app: &mut App, kind: Kind, ground: Vec3, yaw: f32) -> Entity {
    let tuning = app.world().resource::<Tuning>().clone();
    app.world_mut().run_system_once(move |mut commands: Commands| vehicle::spawn(&mut commands, None, &tuning, kind, ground, yaw)).unwrap()
}

fn vehicle_state(app: &mut App, e: Entity) -> (Vec3, Quat, Vec3, usize) {
    let mut q = app.world_mut().query::<(&Transform, &LinearVelocity, &Vehicle)>();
    let (tf, vel, v) = q.get(app.world(), e).unwrap();
    (tf.translation, tf.rotation, vel.0, v.grounded_wheels())
}

fn driving(app: &mut App) -> Option<Entity> {
    let mut q = app.world_mut().query_filtered::<&Driving, With<Player>>();
    q.single(app.world()).ok().map(|d| d.0)
}

#[test]
fn vehicle_physics_curves() {
    use crate::vehicle::physics::*;
    let c = TyreCurve::GRAVEL;
    // The tyre's force rises to a peak near the curve's peak slip and falls past it.
    let f = |kappa: f32| tyre_force(&c, 1000.0, kappa, 0.0).fx;
    assert!(f(0.03) < f(0.1) && f(0.1) < f(0.16), "rising to the peak: {} {} {}", f(0.03), f(0.1), f(0.16));
    assert!(f(0.16) > f(1.0), "falling past it: {} {}", f(0.16), f(1.0));
    assert!(f(0.16) > 900.0 && f(0.16) <= 1000.0);
    // Sliding left pushes right; the combined slip shares the peak.
    let side = tyre_force(&c, 1000.0, 0.0, 0.1);
    assert!(side.fy < -500.0 && side.fx == 0.0, "{side:?}");
    let both = tyre_force(&c, 1000.0, 0.16, 0.19);
    assert!(both.fx.hypot(both.fy) <= 1000.0 + 1e-3);
    // The coil-over: stiffer in bump than rebound, and a wall at the end of the stroke.
    let k = |x, v| coilover(&SUSP, x, v, 40_000.0, 3000.0, 4000.0, 3500.0, 500.0, 0.1, 0.25);
    assert!(k(0.1, 0.0) > 3900.0 && k(0.1, 0.0) < 4100.0);
    assert!(k(0.1, 0.5) > k(0.1, 0.0) && k(0.1, -0.5) < k(0.1, 0.0));
    assert!(k(0.27, 0.0) > 10.0 * k(0.1, 0.0), "hard stop: {}", k(0.27, 0.0));
    // Engine: interpolated torque, and braking off the throttle.
    let curve = [(1000.0, 100.0), (2000.0, 200.0), (3000.0, 150.0)];
    assert_eq!(engine_torque(&curve, 1500.0), 150.0);
    assert_eq!(engine_torque(&curve, 500.0), 100.0);
    assert_eq!(engine_torque(&curve, 9000.0), 150.0);
    assert!(engine_net(&curve, 2000.0, 1.0, 2.0, 3000.0, 0.9) > 150.0);
    assert!(engine_net(&curve, 2000.0, 0.0, 2.0, 3000.0, 0.9) < 0.0);
}

#[test]
fn humvee_settles_at_ride_height() {
    let mut app = vehicle_app();
    let e = spawn_vehicle(&mut app, Kind::Humvee, Vec3::new(30.0, 0.0, 30.0), 0.0);
    run(&mut app, 3.0);
    let (pos, rot, vel, grounded) = vehicle_state(&mut app, e);
    assert_eq!(grounded, 4);
    assert!(vel.length() < 0.2, "at rest, got {vel}");
    assert!((pos.y - 0.95).abs() < 0.15, "centre of mass at ride height, got {}", pos.y);
    assert!((rot * Vec3::Y).y > 0.995, "level, got {rot:?}");
    assert!((pos.xz() - Vec2::new(30.0, 30.0)).length() < 0.2, "stayed put, got {pos}");
}

#[test]
fn humvee_drives_steers_and_the_player_gets_out() {
    let mut app = vehicle_app();
    let e = spawn_vehicle(&mut app, Kind::Humvee, Vec3::new(40.0, 0.0, 40.0), 0.0);
    run(&mut app, 1.0);
    set_player(&mut app, Vec3::new(43.0, 1.0, 40.0), Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(driving(&mut app), Some(e), "pressed E next to it");

    input(&mut app).movement = Vec2::new(0.0, 1.0);
    run(&mut app, 4.0);
    let (pos, rot, vel, _) = vehicle_state(&mut app, e);
    let heading = rot * Vec3::NEG_Z;
    assert!(vel.dot(heading) > 8.0, "accelerated forward, got {vel} heading {heading}");
    assert!(pos.z < 30.0, "moved along -Z, got {pos}");
    let (ppos, _, _) = player(&mut app);
    assert!(ppos.distance(pos) < 3.0, "the driver rides along, player at {ppos}, vehicle at {pos}");

    input(&mut app).movement = Vec2::new(-1.0, 1.0);
    run(&mut app, 2.0);
    let (_, rot, vel, _) = vehicle_state(&mut app, e);
    let heading = rot * Vec3::NEG_Z;
    assert!(heading.x < -0.3, "turned left, heading {heading}");
    assert!((rot * Vec3::Y).y > 0.9, "and stayed on its wheels");
    assert!(vel.length() > 3.0);

    // Holding back brakes to a stop (then it would start reversing).
    input(&mut app).movement = Vec2::new(0.0, -1.0);
    let mut slowest = f32::MAX;
    for _ in 0..50 {
        run(&mut app, 0.05);
        slowest = slowest.min(vehicle_state(&mut app, e).2.length());
    }
    assert!(slowest < 1.0, "braked, got down to {slowest}");

    input(&mut app).movement = Vec2::ZERO;
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.5);
    assert_eq!(driving(&mut app), None, "got out");
    let (vpos, _, _, _) = vehicle_state(&mut app, e);
    let (ppos, _, state) = player(&mut app);
    assert!(ppos.distance(vpos) > 1.0 && ppos.distance(vpos) < 5.0, "standing beside it: {ppos} vs {vpos}");
    assert_eq!(state, MoveState::Ground);
}

#[test]
fn bike_stays_upright_and_rides() {
    let mut app = vehicle_app();
    let e = spawn_vehicle(&mut app, Kind::DirtBike, Vec3::new(-40.0, 0.0, 40.0), 0.0);
    run(&mut app, 3.0);
    let (pos, rot, vel, grounded) = vehicle_state(&mut app, e);
    assert_eq!(grounded, 2);
    assert!((rot * Vec3::Y).y > 0.98 && vel.length() < 0.2, "parked upright: {rot:?} {vel}");
    assert!((pos.y - 0.62).abs() < 0.15, "at ride height, got {}", pos.y);
    set_player(&mut app, Vec3::new(-38.0, 1.0, 40.0), Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(driving(&mut app), Some(e));
    input(&mut app).movement = Vec2::new(0.0, 1.0);
    run(&mut app, 3.0);
    let (_, rot, vel, _) = vehicle_state(&mut app, e);
    assert!(vel.dot(rot * Vec3::NEG_Z) > 5.0, "rode off, got {vel}");
    input(&mut app).movement = Vec2::new(-0.6, 1.0);
    run(&mut app, 1.5);
    let (_, rot, _, _) = vehicle_state(&mut app, e);
    let up = rot * Vec3::Y;
    let heading = rot * Vec3::NEG_Z;
    let right = Vec3::new(heading.x, 0.0, heading.z).normalize().cross(Vec3::Y);
    assert!(up.y > 0.7, "leaning but up, got {up}");
    assert!(up.dot(right) < -0.2, "leaning into the left turn, got {up} with right {right}");
    assert!(heading.x < -0.2, "turning left, heading {heading}");
}

#[test]
fn vehicle_respawns_after_falling_off_the_world() {
    let mut app = vehicle_app();
    // Seconds to drop `m` metres from rest; the kill plane is at -30.
    let g = app.world().resource::<Tuning>().gravity;
    let fall = |m: f32| (2.0 * m / g).sqrt();
    let e = spawn_vehicle(&mut app, Kind::Jeep, Vec3::new(300.0, 0.0, 300.0), 0.0);
    run(&mut app, fall(20.0));
    let (pos, _, _, _) = vehicle_state(&mut app, e);
    assert!(pos.y < -15.0, "fell off the floor, got {pos}");
    run(&mut app, fall(35.0) - fall(20.0));
    let (pos, _, _, _) = vehicle_state(&mut app, e);
    assert!(pos.y > -15.0 && (pos.xz() - Vec2::new(300.0, 300.0)).length() < 0.5, "back home, got {pos}");
}

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
        TargetsPlugin,
        HealthPlugin,
        crate::hud::HudPlugin,
        VehiclePlugin,
        LootPlugin,
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
// Extraction loop, missions, teams

fn spawn_loot(app: &mut App, pos: Vec3, value: u32, key: Option<usize>) -> Entity {
    app.world_mut().spawn(loot::bundle(pos, value, key)).id()
}

fn spawn_pad(app: &mut App, pos: Vec3) {
    app.world_mut().spawn((ExtractPad { radius: 6.0 }, Transform::from_translation(pos)));
}

fn inventory(app: &mut App) -> (u32, Vec<usize>) {
    let inv = app.world().resource::<Inventory>();
    (inv.carried, inv.keys.clone())
}

fn save(app: &mut App) -> Save {
    app.world().resource::<Save>().clone()
}

#[test]
fn loot_is_carried_banked_on_extraction_and_lost_on_death() {
    let mut app = make_app(Tuning::default());
    spawn_loot(&mut app, Vec3::new(20.0, 0.0, 20.0), 40, None);
    spawn_pad(&mut app, Vec3::new(-40.0, 0.0, -40.0));
    set_player(&mut app, Vec3::new(20.0, 1.0, 20.0), Vec3::ZERO);
    run(&mut app, 0.2);
    assert_eq!(inventory(&mut app), (40, vec![]), "picked up");
    set_player(&mut app, Vec3::new(-40.0, 1.0, -40.0), Vec3::ZERO);
    run(&mut app, 4.0);
    assert_eq!(inventory(&mut app).0, 40, "still extracting");
    assert!(app.world().resource::<Inventory>().extracting > 3.0);
    run(&mut app, 4.5);
    let s = save(&mut app);
    assert_eq!((s.banked, s.runs, inventory(&mut app).0), (40, 1, 0), "banked: {s:?}");
    let (pos, _, _) = player(&mut app);
    assert!(pos.distance(Vec3::new(-40.0, 1.0, -40.0)) > 10.0, "sent back to spawn, got {pos}");

    // The cache comes back later; pick it up again and die with it.
    let mut q = app.world_mut().query::<&mut Loot>();
    q.single_mut(app.world_mut()).unwrap().down = 0.1;
    run(&mut app, 0.2);
    set_player(&mut app, Vec3::new(20.0, 1.0, 20.0), Vec3::ZERO);
    run(&mut app, 0.2);
    assert_eq!(inventory(&mut app).0, 40);
    hit_player(&mut app, 500.0);
    run(&mut app, 0.2);
    let s = save(&mut app);
    assert_eq!((inventory(&mut app).0, s.deaths, s.banked), (0, 1, 40), "lost the haul: {s:?}");
}

#[test]
fn save_round_trips_through_a_file() {
    let path = std::env::temp_dir().join(format!("rust-regime-save-{}.toml", std::process::id()));
    let file = SaveFile(Some(path.clone()));
    let s = Save { banked: 1234, runs: 7, deaths: 2, ..default() };
    file.write(&s);
    assert_eq!(file.load(), s);
    std::fs::remove_file(&path).ok();
    assert_eq!(file.load(), Save::default(), "missing file is a fresh save");
}

#[test]
fn soldiers_of_different_teams_fight_each_other() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(90.0, 1.0, 90.0), Vec3::ZERO);
    let spawn = |app: &mut App, pos: Vec3, team: Team| {
        app.world_mut()
            .run_system_once(move |mut commands: Commands, tuning: Res<Tuning>| targets::spawn_soldier_team(&mut commands, &tuning, None, vec![pos], team))
            .unwrap();
    };
    spawn(&mut app, Vec3::new(0.0, 0.0, 0.0), Team(0));
    spawn(&mut app, Vec3::new(0.0, 0.0, 20.0), Team(1));
    spawn(&mut app, Vec3::new(-30.0, 0.0, 0.0), Team(1));
    run(&mut app, 6.0);
    let mut killed = 0;
    let mut q = app.world_mut().query::<(&Target, &Team)>();
    for (t, _) in q.iter(app.world()) {
        if !t.alive() {
            killed += 1;
        }
    }
    assert!(killed >= 1, "someone died in the crossfire");
    let hp = app.world().resource::<PlayerHealth>().hp;
    assert_eq!(hp, 100.0, "nobody shot the far-off player");
    let mut kills = app.world_mut().resource_mut::<Messages<Killed>>();
    kills.clear();
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

fn dummy_at(app: &mut App, feet: Vec3) -> Entity {
    let t = app.world().resource::<Tuning>().clone();
    targets::spawn_dummy(&mut app.world_mut().commands(), &t, None, feet, 0.0);
    app.update();
    let mut q = app.world_mut().query_filtered::<Entity, With<Target>>();
    q.single(app.world()).unwrap()
}

fn target_health(app: &mut App, e: Entity) -> f32 {
    app.world().get::<Target>(e).unwrap().health
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
fn bullets_go_through_wood_but_not_stone() {
    let mut app = make_app(Tuning::default());
    let dummy = dummy_at(&mut app, controller::SPAWN + Vec3::new(0.0, -1.0, -8.0));
    // A thin wooden fence halfway, shoulder high.
    let fence = app.world_mut().spawn((RigidBody::Static, Collider::cuboid(4.0, 3.0, 0.1), crate::weapon::Penetrable { cost: 0.35 }, Transform::from_translation(controller::SPAWN + Vec3::new(0.0, 0.5, -4.0)))).id();
    select_weapon(&mut app, WeaponKind::Rifle);
    input(&mut app).fire_pressed = true;
    input(&mut app).fire_held = true;
    run(&mut app, 0.12);
    input(&mut app).fire_held = false;
    let hp = target_health(&mut app, dummy);
    assert!(hp < 100.0 && hp > 40.0, "hit through the fence with less energy: {hp}");
    // Make it stone: no way through.
    app.world_mut().entity_mut(fence).remove::<crate::weapon::Penetrable>();
    let before = target_health(&mut app, dummy);
    input(&mut app).fire_held = true;
    run(&mut app, 0.3);
    assert_eq!(target_health(&mut app, dummy), before, "stone stops bullets");
}

#[test]
fn headshots_hurt_more_than_legshots() {
    let t = Tuning::default();
    let mut app = make_app(t.clone());
    let feet = controller::SPAWN + Vec3::new(0.0, -1.0, -8.0);
    let dummy = dummy_at(&mut app, feet);
    select_weapon(&mut app, WeaponKind::Pistol);
    let mut q = app.world_mut().query::<(&Player, &Transform)>();
    let (p, tf) = q.single(app.world()).unwrap();
    let eye = tf.translation + Vec3::Y * p.eye_offset(&t);
    let aim_at = |y: f32| ((feet.y + y) - eye.y).atan2(8.0);
    app.world_mut().resource_mut::<ViewAngles>().pitch = aim_at(1.65);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.2);
    let head = 100.0 - target_health(&mut app, dummy);
    app.world_mut().resource_mut::<ViewAngles>().pitch = aim_at(0.4);
    app.world_mut().resource_mut::<crate::weapon::Recoil>().pending = Vec2::ZERO;
    let before = target_health(&mut app, dummy);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.2);
    let legs = before - target_health(&mut app, dummy);
    assert!(head > 50.0 && legs > 5.0 && legs < 20.0, "head {head} vs legs {legs}");
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

fn soldiers(app: &mut App) -> Vec<(Entity, Vec3, Option<f32>)> {
    let mut q = app.world_mut().query::<(Entity, &Soldier, &Transform)>();
    q.iter(app.world()).map(|(e, s, tf)| (e, tf.translation, s.alert)).collect()
}

#[test]
fn soldier_hears_a_shot_and_goes_to_look() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    // Out of sight behind a long wall, 40 m off.
    wall(&mut app, Vec3::new(1.0, 6.0, 60.0), Vec3::new(20.0, 3.0, 0.0));
    soldier(&mut app, vec![Vec3::new(40.0, 0.0, 0.0), Vec3::new(40.0, 0.0, 1.0)]);
    run(&mut app, 0.3);
    assert!(soldier_state(&mut app).1.is_none(), "quiet: not alert");
    select_weapon(&mut app, WeaponKind::Pistol);
    app.world_mut().resource_mut::<ViewAngles>().yaw = std::f32::consts::FRAC_PI_2;
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.1);
    let (start, alert) = soldier_state(&mut app);
    assert!(alert.is_some(), "heard the shot");
    run(&mut app, 1.0);
    let (pos, _) = soldier_state(&mut app);
    assert!(pos.distance(Vec3::new(0.0, pos.y, 0.0)) < start.distance(Vec3::new(0.0, start.y, 0.0)) - 2.0, "walking toward the shot: {start} to {pos}");
}

#[test]
fn a_soldier_who_sees_you_calls_his_squad() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    // The second soldier is round a corner, 30 m from the first.
    wall(&mut app, Vec3::new(30.0, 6.0, 1.0), Vec3::new(10.0, 3.0, -8.0));
    soldier(&mut app, vec![Vec3::new(15.0, 0.0, 0.0), Vec3::new(15.0, 0.0, 1.0)]);
    soldier(&mut app, vec![Vec3::new(10.0, 0.0, -25.0), Vec3::new(11.0, 0.0, -25.0)]);
    run(&mut app, 0.5);
    let s = soldiers(&mut app);
    assert!(s.iter().all(|(_, _, a)| a.is_some()), "both alert: {s:?}");
}

#[test]
fn a_hit_soldier_runs_for_cover() {
    let mut app = make_app(Tuning::default());
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);
    // A crate-height wall just beside the soldier, side-on to the player.
    wall(&mut app, Vec3::new(0.6, 2.0, 3.0), Vec3::new(17.0, 1.0, 0.0));
    soldier(&mut app, vec![Vec3::new(15.0, 0.0, 3.0), Vec3::new(15.0, 0.0, 4.0)]);
    run(&mut app, 0.2);
    let e = soldiers(&mut app)[0].0;
    app.world_mut().resource_mut::<Messages<Damage>>().write(Damage { entity: e, amount: 10.0, impulse: Vec3::ZERO });
    run(&mut app, 2.0);
    let (_, pos, _) = soldiers(&mut app)[0];
    let eye = Vec3::new(0.0, 1.0, 0.0) + Vec3::Y * 0.6;
    let to = pos + Vec3::Y * 0.6 - eye;
    let mut q = app.world_mut().query_filtered::<Entity, With<Player>>();
    let player_e = q.single(app.world()).unwrap();
    let blocked = app
        .world_mut()
        .run_system_once(move |spatial: SpatialQuery| {
            spatial
                .cast_ray(eye, Dir3::new(to.normalize()).unwrap(), to.length(), true, &SpatialQueryFilter::from_excluded_entities([player_e, e]))
                .is_some()
        })
        .unwrap();
    assert!(blocked, "the wall is between them now, soldier at {pos}");
}


#[test]
fn fuel_burns_and_an_empty_tank_stops_the_engine() {
    let mut app = vehicle_app();
    let e = spawn_vehicle(&mut app, Kind::Jeep, Vec3::new(40.0, 0.0, 40.0), 0.0);
    run(&mut app, 1.0);
    set_player(&mut app, Vec3::new(42.0, 1.0, 40.0), Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 2.0);
    let fuel = app.world().get::<Vehicle>(e).unwrap().fuel;
    assert!(fuel < 57.0 && fuel > 56.9, "a little burned: {fuel}");
    // Stopped dead, wheels and all, so any motion from here on would have to come from the engine.
    let mut v = app.world_mut().get_mut::<Vehicle>(e).unwrap();
    v.fuel = 0.0;
    for w in &mut v.wheels {
        w.om = 0.0;
    }
    app.world_mut().entity_mut(e).insert(LinearVelocity::ZERO);
    run(&mut app, 0.3);
    let (start, _, _, _) = vehicle_state(&mut app, e);
    run(&mut app, 2.0);
    let (end, _, vel, _) = vehicle_state(&mut app, e);
    assert!(vel.length() < 0.5 && start.distance(end) < 0.5, "no power: {vel}");
}

#[test]
fn shot_up_vehicles_wreck_throw_the_driver_and_come_back() {
    let mut app = vehicle_app();
    let e = spawn_vehicle(&mut app, Kind::Jeep, Vec3::new(40.0, 0.0, 40.0), 0.0);
    run(&mut app, 1.0);
    set_player(&mut app, Vec3::new(42.0, 1.0, 40.0), Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    for _ in 0..3 {
        app.world_mut().resource_mut::<Messages<Damage>>().write(Damage { entity: e, amount: 150.0, impulse: Vec3::ZERO });
        run(&mut app, 0.05);
    }
    let v = app.world().get::<Vehicle>(e).unwrap();
    assert!(v.wreck.is_some() && v.health == 0.0, "wrecked: {} hp", v.health);
    assert_eq!(driving(&mut app), None, "the driver was thrown out");
    assert!(app.world().resource::<PlayerHealth>().hp < 70.0, "and hurt");
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(driving(&mut app), None, "a wreck can't be driven");
    run(&mut app, Tuning::default().vehicle.wreck_time);
    let v = app.world().get::<Vehicle>(e).unwrap();
    assert!(v.wreck.is_none() && v.health == v.spec.hp && v.fuel == v.spec.tank, "replaced with a fresh one");
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
fn the_knife_cuts_what_is_in_reach_and_nothing_beyond() {
    let t = Tuning::default();
    let mut app = make_app(t.clone());
    run(&mut app, 0.5);
    let near = dummy_at(&mut app, controller::SPAWN + Vec3::new(0.0, -1.0, -1.6));
    select_weapon(&mut app, WeaponKind::Knife);
    input(&mut app).fire_held = true;
    run(&mut app, 0.1);
    let one = t.target_health - t.knife.damage;
    assert!((target_health(&mut app, near) - one).abs() < 0.01, "one slash: {}", target_health(&mut app, near));
    // Held, the next slash waits out the cooldown.
    run(&mut app, t.knife.cooldown * 0.5);
    assert!((target_health(&mut app, near) - one).abs() < 0.01, "too soon");
    run(&mut app, t.knife.cooldown);
    assert!(!app.world().get::<Target>(near).unwrap().alive(), "two slashes of {} kill a {} hp dummy", t.knife.damage, t.target_health);

    let mut far = make_app(t.clone());
    run(&mut far, 0.5);
    let dummy = dummy_at(&mut far, controller::SPAWN + Vec3::new(0.0, -1.0, -(t.knife.range + 2.0)));
    select_weapon(&mut far, WeaponKind::Knife);
    input(&mut far).fire_held = true;
    run(&mut far, 0.1);
    assert_eq!(target_health(&mut far, dummy), t.target_health, "out of arm's reach");
}

#[test]
fn a_melee_hit_freezes_the_world_for_a_moment_then_lets_go() {
    let t = Tuning::default();
    let mut app = make_app(t.clone());
    run(&mut app, 0.5);
    dummy_at(&mut app, controller::SPAWN + Vec3::new(0.0, -1.0, -1.6));
    select_weapon(&mut app, WeaponKind::Knife);
    input(&mut app).fire_held = true;
    let mut slowest: f32 = 1.0;
    for _ in 0..10 {
        app.update();
        slowest = slowest.min(app.world().resource::<Time<Virtual>>().relative_speed());
    }
    input(&mut app).fire_held = false;
    assert!(slowest < 0.5, "slowed on the hit: {slowest}");
    run(&mut app, 0.3);
    assert_eq!(app.world().resource::<Time<Virtual>>().relative_speed(), 1.0, "back to full speed");
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
fn a_hit_on_a_target_is_confirmed_and_throws_sparks() {
    let mut app = make_app(Tuning::default());
    app.add_systems(Update, |mut r: MessageReader<crate::weapon::HitConfirm>, mut n: Local<u32>, mut out: ResMut<Confirmed>| {
        *n += r.read().count() as u32;
        out.0 = *n;
    });
    app.init_resource::<Confirmed>();
    let dummy = dummy_at(&mut app, controller::SPAWN + Vec3::new(0.0, -1.0, -8.0));
    select_weapon(&mut app, WeaponKind::Pistol);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.2);
    assert!(target_health(&mut app, dummy) < 100.0);
    assert!(app.world().resource::<Confirmed>().0 >= 1, "the hit was confirmed");
}

#[derive(Resource, Default)]
struct Confirmed(u32);

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
    let c = app.world().resource::<ShipControls>();
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
    assert_eq!(ships.ship.iter().map(|s| s.id.as_str()).collect::<Vec<_>>(), ["kestrel", "litany", "mule", "vantage"]);
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
    let mut parked: Vec<(usize, Vec3)> = app.world_mut().query::<(&Ship, &Transform)>().iter(app.world()).map(|(s, tf)| (s.spec, tf.translation)).collect();
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
    for spec in &ships.ship {
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

use solar::station::{Blessing, Contract, Station, StationKind, BLESSING_HP, TITHE, UPGRADE_COST};

#[test]
fn every_base_has_its_station_on_a_floor_clear_of_the_furniture() {
    let bases = solar::base::Bases::load();
    let roles: Vec<(&str, Vec<StationKind>)> = vec![
        ("roost", vec![StationKind::Resupply, StationKind::Locker]),
        ("reliquary", vec![StationKind::Shrine]),
        ("yard", vec![StationKind::Workshop]),
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
    app.world_mut().spawn((Station { base, kind, label: "Test".into() }, GlobalTransform::from_translation(at)));
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

#[test]
fn a_parcel_is_taken_at_the_desk_and_pays_at_the_other_bases_door() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let bases = app.world().resource::<solar::base::Bases>().clone();
    let vantage = bases.base.iter().position(|b| b.id == "outpost").unwrap();
    stand_at_station(&mut app, StationKind::Contracts, vantage);
    press_use(&mut app);
    let contract = app.world().resource::<Save>().contract.clone().expect("a contract was handed out");
    assert_ne!(contract.to, "outpost");
    // A second press while carrying one gives nothing new.
    press_use(&mut app);
    assert_eq!(app.world().resource::<Save>().contract, Some(contract.clone()));
    // Carry it to the Roost, the only base on this world, and stand in its doorway.
    app.world_mut().resource_mut::<Save>().contract = Some(Contract { to: "roost".into(), pay: 250 });
    let (at, base) = app.world_mut().query::<(&GlobalTransform, &solar::base::Base)>().single(app.world()).map(|(g, b)| (*g, b.spec)).unwrap();
    let door = at.translation() + at.rotation() * Vec3::from(bases.base[base].door);
    set_player(&mut app, door, Vec3::ZERO);
    run(&mut app, 0.2);
    let save = app.world().resource::<Save>();
    assert_eq!((save.banked, save.contracts_done, save.contract.clone()), (250, 1, None), "paid on arrival");
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
