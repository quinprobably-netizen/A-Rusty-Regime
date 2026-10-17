//! Headless simulation tests: real Avian physics, scripted input, no window.

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::ecs::system::RunSystemOnce;
use bevy::time::TimeUpdateStrategy;
use std::time::Duration;

use crate::controller::{self, ControllerPlugin, MoveState, Player};
use crate::input::{PlayerInput, ViewAngles};
use crate::terrain;
use crate::tuning::{Island, Tuning};
use crate::targets::{self, Target, TargetsPlugin};
use crate::weapon::{Arsenal, WeaponKind, WeaponPlugin};

const DT: f32 = 1.0 / 66.0;

fn make_app(tuning: Tuning) -> App {
    let mut app = App::new();
    app.add_plugins((MinimalPlugins, TransformPlugin, AssetPlugin::default(), bevy::world_serialization::WorldSerializationPlugin, bevy::mesh::MeshPlugin, PhysicsPlugins::default()))
        .insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_secs_f32(DT)))
        .insert_resource(Time::<Fixed>::from_seconds(DT as f64))
        .insert_resource(tuning)
        .init_resource::<PlayerInput>()
        .init_resource::<ViewAngles>()
        .add_plugins((ControllerPlugin, WeaponPlugin, TargetsPlugin));
    app.world_mut().spawn((RigidBody::Static, Collider::cuboid(200.0, 1.0, 200.0), Transform::from_xyz(0.0, -0.5, 0.0)));
    app.finish();
    app.update(); // run Startup so the player exists
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
    .add_plugins((
        crate::tuning::TuningPlugin,
        crate::input::InputPlugin,
        ControllerPlugin,
        crate::camera::CameraPlugin,
        WeaponPlugin,
        crate::viewmodel::ViewModelPlugin,
        TargetsPlugin,
        crate::hud::HudPlugin,
        crate::level::LevelPlugin,
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
    input(&mut app).weapon_step = 2; // wraps around past the pistol
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
    assert!(score.kills == 1 && score.hits >= 6, "{score:?}");

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
    assert_eq!(pose_for(MoveState::Ground, false, 0.0, 0.0, max), Pose::Idle);
    assert_eq!(pose_for(MoveState::Ground, false, 2.0, 0.0, max), Pose::Walk);
    assert_eq!(pose_for(MoveState::Ground, false, 7.0, 0.0, max), Pose::Sprint);
    assert_eq!(pose_for(MoveState::Ground, true, 2.0, 0.0, max), Pose::Crouch);
    assert_eq!(pose_for(MoveState::Slide, true, 8.0, 0.0, max), Pose::Crouch);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, 4.0, max), Pose::Jump);
    assert_eq!(pose_for(MoveState::Air, false, 5.0, -4.0, max), Pose::Fall);
    assert_eq!(pose_for(MoveState::WallRun, false, 8.0, 1.0, max), Pose::Sprint);
    assert_eq!(pose_for(MoveState::Mantle, false, 0.0, 0.0, max), Pose::Jump);
    // Feet speed up with the run and never stall.
    assert!(playback_rate(Pose::Sprint, 7.5, max) > playback_rate(Pose::Sprint, 5.5, max));
    assert!(playback_rate(Pose::Walk, 0.3, max) >= 0.7);
    assert_eq!(playback_rate(Pose::Idle, 3.0, max), 1.0);
}

// --- Island terrain ---

#[test]
fn heightmap_is_deterministic_and_island_shaped() {
    let island = Island::default();
    let a = terrain::generate(&island);
    let b = terrain::generate(&island);
    assert_eq!(a.heights, b.heights);
    let other = terrain::generate(&Island { seed: 8, ..island.clone() });
    assert_ne!(a.heights, other.heights);
    assert_eq!(a.n, 1025);
    assert!(a.height_at(0.0, 0.0) > island.water_level + 5.0, "center is land");
    let half = island.size / 2.0;
    for (x, z) in [(-half, -half), (half, -half), (-half, half), (half, half), (0.0, half), (half, 0.0)] {
        assert!(a.height_at(x, z) < island.water_level - 1.0, "coast is under water at {x},{z}");
    }
    let peak = a.heights.iter().cloned().fold(f32::MIN, f32::max);
    assert!(peak > 0.6 * island.height && peak <= island.height, "peak {peak}");
}

#[test]
fn heightmap_handles_odd_sizes_and_out_of_range() {
    let hm = terrain::generate(&Island { size: 100.0, cell: 3.0, ..Island::default() });
    assert_eq!(hm.n, 100 / 3 + 1);
    assert_eq!(hm.height_at(1e6, -1e6), hm.height_at(hm.size / 2.0, -hm.size / 2.0));
    let n = hm.normal_at(0.0, 0.0);
    assert!((n.length() - 1.0).abs() < 1e-3 && n.y > 0.0);
}

#[test]
fn stamp_flattens_a_pad() {
    let mut hm = terrain::generate(&Island::default());
    hm.stamp_flat(Vec2::new(200.0, -300.0), 30.0, 50.0, 20.0);
    for (dx, dz) in [(0.0, 0.0), (29.0, 0.0), (0.0, -29.0), (20.0, 20.0)] {
        assert!((hm.height_at(200.0 + dx, -300.0 + dz) - 50.0).abs() < 0.05);
    }
    let untouched = terrain::generate(&Island::default());
    assert_eq!(hm.height_at(200.0 + 60.0, -300.0), untouched.height_at(200.0 + 60.0, -300.0), "unaffected beyond radius + blend");
    assert!((hm.height_at(0.0, 0.0) - hm.height_at(20.0, 20.0)).abs() < 0.05, "spawn pad is flat");
}

#[test]
fn colliders_match_heightmap() {
    // 500 m at 4 m cells is 125 cells: three full chunks and a short one per side.
    let island = Island { size: 500.0, ..Island::default() };
    let hm = terrain::generate(&island);
    let mut app = make_app(Tuning::default());
    // Drop make_app's flat floor so only the terrain can be hit.
    let floor: Vec<Entity> = app.world_mut().query_filtered::<Entity, (With<Collider>, Without<Player>)>().iter(app.world()).collect();
    for e in floor {
        app.world_mut().despawn(e);
    }
    terrain::spawn_colliders(app.world_mut(), &hm);
    app.update();
    for (x, z) in [(0.0, 0.0), (100.0, -37.0), (-211.0, 180.0), (245.0, 3.0), (-3.0, -245.0), (130.0, 130.0), (240.0, -240.0)] {
        let got = app
            .world_mut()
            .run_system_once(move |q: SpatialQuery| {
                q.cast_ray(Vec3::new(x, 400.0, z), Dir3::NEG_Y, 800.0, true, &SpatialQueryFilter::default()).map(|hit| 400.0 - hit.distance)
            })
            .unwrap()
            .expect("ray hits terrain");
        let want = hm.height_at(x, z);
        assert!((got - want).abs() < 0.1, "at {x},{z}: collider {got} vs heightmap {want}");
    }
}

#[test]
fn falling_in_water_respawns_at_world_bounds() {
    let mut app = make_app(Tuning::default());
    app.insert_resource(controller::WorldBounds { spawn: Vec3::new(5.0, 30.0, -5.0), kill_y: 10.0 });
    set_player(&mut app, Vec3::new(50.0, 9.0, 50.0), Vec3::new(3.0, -5.0, 0.0));
    run(&mut app, 0.1);
    let (pos, vel, state) = player(&mut app);
    assert!((pos.xz() - Vec2::new(5.0, -5.0)).length() < 0.5 && pos.y > 25.0, "respawned at spawn, got {pos}");
    // Reset to zero, then a few ticks of gravity at the spawn point.
    assert!(vel.xz().length() < 0.01 && vel.y <= 0.0 && vel.y > -3.0, "velocity reset, got {vel}");
    assert_eq!(state, MoveState::Air);
}
