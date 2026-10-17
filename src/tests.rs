//! Headless simulation tests: real Avian physics, scripted input, no window.

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::ecs::system::RunSystemOnce;
use bevy::time::TimeUpdateStrategy;
use std::time::Duration;

use crate::controller::{self, ControllerPlugin, MoveState, Player};
use crate::input::{PlayerInput, ViewAngles};
use crate::health::{HealthPlugin, PlayerHealth, PlayerHit};
use crate::targets::Soldier;
use crate::terrain;
use crate::tuning::{Island, Tuning};
use crate::targets::{self, Target, TargetsPlugin};
use crate::island::{Placed, Sites};
use crate::loot::{self, ExtractPad, Inventory, Loot, LootPlugin, Save, SaveFile};
use crate::mission::{MissionPlugin, Missions};
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
    app.add_plugins((MinimalPlugins, TransformPlugin, AssetPlugin::default(), bevy::world_serialization::WorldSerializationPlugin, bevy::mesh::MeshPlugin, PhysicsPlugins::default()))
        .insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_secs_f32(DT)))
        .insert_resource(Time::<Fixed>::from_seconds(DT as f64))
        .insert_resource(tuning)
        .insert_resource(SaveFile(None))
        .init_resource::<PlayerInput>()
        .init_resource::<ViewAngles>()
        .add_plugins((ControllerPlugin, WeaponPlugin, TargetsPlugin, HealthPlugin, VehiclePlugin, LootPlugin, MissionPlugin));
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
        MissionPlugin,
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
}

#[test]
fn site_pads_are_flat_and_above_water() {
    let island = Island::default();
    let mut hm = terrain::generate(&island);
    let sites = crate::island::place(&mut hm, &island);
    assert_eq!(sites.len(), 9, "six sites and three extraction pads");
    assert_eq!(crate::island::extract_pads(&sites).count(), 3);
    for site in &sites {
        assert!(site.height > island.water_level, "{} above water", site.name);
        assert!(site.pad <= site.radius);
        for (dx, dz) in [(0.0, 0.0), (0.7, 0.0), (0.0, -0.7), (0.5, 0.5), (-0.6, 0.3)] {
            let h = hm.height_at(site.center.x + dx * site.pad, site.center.y + dz * site.pad);
            assert!((h - site.height).abs() < 0.05, "{} pad flat at {dx},{dz}: {h} vs {}", site.name, site.height);
        }
    }
    assert_eq!(sites[0].name, "Base camp");
    assert!(sites[5].center.y > island.core * 0.6, "lighthouse is on the south coast");
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
    app.insert_resource(controller::WorldBounds { spawn: Vec3::new(5.0, 1.0, -5.0), kill_y: -30.0 });
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
    let e = spawn_vehicle(&mut app, Kind::Jeep, Vec3::new(300.0, 0.0, 300.0), 0.0);
    run(&mut app, 1.6);
    let (pos, _, _, _) = vehicle_state(&mut app, e);
    assert!(pos.y < -15.0, "fell off the floor, got {pos}");
    run(&mut app, 0.8);
    let (pos, _, _, _) = vehicle_state(&mut app, e);
    assert!(pos.y > -15.0 && (pos.xz() - Vec2::new(300.0, 300.0)).length() < 0.5, "back home, got {pos}");
}

#[test]
fn vehicles_park_on_the_island() {
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
        MissionPlugin,
        terrain::TerrainPlugin,
    ));
    app.finish();
    app.cleanup();
    run(&mut app, 10.0);
    let mut q = app.world_mut().query::<(&Transform, &Vehicle)>();
    let mut n = 0;
    let mut bad = Vec::new();
    for (tf, v) in q.iter(app.world()) {
        n += 1;
        let home = v.home.translation;
        let up = tf.rotation * Vec3::Y;
        if tf.translation.distance(home) > 1.0 || up.y < 0.95 {
            bad.push(format!("{} from {home} to {} up {up} grounded {}", v.spec.name, tf.translation, v.grounded_wheels()));
        }
    }
    assert_eq!(n, 7);
    assert!(bad.is_empty(), "every vehicle stays parked and upright:\n{}", bad.join("\n"));
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

/// Six fake sites on the test floor, in `island::place` order, plus one extraction pad.
fn fake_sites(app: &mut App) {
    let site = |name, x: f32, z: f32| Placed { name, center: Vec2::new(x, z), height: 0.0, pad: 10.0, radius: 20.0 };
    app.insert_resource(Sites(vec![
        site("Base camp", 0.0, 60.0),
        site("Radio tower", 60.0, -60.0),
        site("Fort", 80.0, 0.0),
        site("Quarry", -80.0, 0.0),
        site("Ruins", 0.0, -80.0),
        site("Lighthouse", 0.0, 90.0),
        site("Extract north", -60.0, 60.0),
    ]));
    spawn_pad(app, Vec3::new(-60.0, 0.0, 60.0));
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
    let s = Save { banked: 1234, runs: 7, deaths: 2, missions_done: 3 };
    file.write(&s);
    assert_eq!(file.load(), s);
    std::fs::remove_file(&path).ok();
    assert_eq!(file.load(), Save::default(), "missing file is a fresh save");
}

fn mission(app: &mut App) -> usize {
    app.world().resource::<Missions>().current
}

#[test]
fn missions_progress_in_order() {
    let mut app = make_app(Tuning::default());
    fake_sites(&mut app);
    assert_eq!(mission(&mut app), 0);

    // 0: reach the tower top.
    set_player(&mut app, Vec3::new(60.0, 41.4, -60.0), Vec3::ZERO);
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 1, "reached the tower");
    set_player(&mut app, Vec3::new(0.0, 1.0, 0.0), Vec3::ZERO);

    // 1: kill four soldiers at the fort (and one elsewhere that must not count).
    for i in 0..4 {
        soldier(&mut app, vec![Vec3::new(80.0 + i as f32 * 2.0, 0.0, 10.0)]);
    }
    soldier(&mut app, vec![Vec3::new(-20.0, 0.0, -60.0)]);
    let mut q = app.world_mut().query_filtered::<(Entity, &Transform), With<Soldier>>();
    let soldiers: Vec<(Entity, Vec3)> = q.iter(app.world()).map(|(e, tf)| (e, tf.translation)).collect();
    for (e, pos) in &soldiers {
        if pos.x < 0.0 {
            app.world_mut().resource_mut::<Messages<Damage>>().write(Damage { entity: *e, amount: 1000.0, impulse: Vec3::ZERO });
        }
    }
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 1, "a kill away from the fort does not count");
    for (e, pos) in &soldiers {
        if pos.x > 0.0 {
            app.world_mut().resource_mut::<Messages<Damage>>().write(Damage { entity: *e, amount: 1000.0, impulse: Vec3::ZERO });
        }
    }
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 2, "fort cleared");

    // 2 and 3: the quarry cache, carried to the pad; dying with it sends you back a step.
    let cache = spawn_loot(&mut app, Vec3::new(-80.0, 0.0, 0.0), 100, Some(0));
    set_player(&mut app, Vec3::new(-80.0, 1.0, 0.0), Vec3::ZERO);
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 3, "cache collected");
    hit_player(&mut app, 500.0);
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 2, "lost the cache with your life");
    run(&mut app, 2.5);
    assert!(app.world().get::<Loot>(cache).unwrap().available(), "the cache is back quickly");
    set_player(&mut app, Vec3::new(-80.0, 1.0, 0.0), Vec3::ZERO);
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 3);
    set_player(&mut app, Vec3::new(-60.0, 1.0, 60.0), Vec3::ZERO);
    run(&mut app, 8.5);
    assert_eq!(mission(&mut app), 4, "extracted with the cache");
    assert_eq!(save(&mut app).missions_done, 4);

    // 4: drive a Humvee to the ruins.
    app.insert_resource(Gravity(Vec3::NEG_Y * 17.6));
    let humvee = spawn_vehicle(&mut app, Kind::Humvee, Vec3::new(0.0, 0.0, -50.0), 0.0);
    run(&mut app, 1.0);
    set_player(&mut app, Vec3::new(3.0, 1.0, -50.0), Vec3::ZERO);
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(driving(&mut app), Some(humvee));
    assert_eq!(mission(&mut app), 5, "drove to the ruins");
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);

    // 5: the lighthouse top, and then there is nothing left.
    set_player(&mut app, Vec3::new(0.0, 25.3, 90.0), Vec3::ZERO);
    run(&mut app, 0.1);
    assert_eq!(mission(&mut app), 6, "all done");
    run(&mut app, 1.0);
    assert_eq!(mission(&mut app), 6);
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

#[test]
fn match_mode_spawns_two_teams_and_scores() {
    let mut app = build_app(Tuning::default());
    fake_sites(&mut app);
    app.add_plugins(crate::bots::MatchPlugin);
    app.finish();
    run(&mut app, 0.1);
    let mut q = app.world_mut().query::<&Team>();
    let (mut blue, mut red) = (0, 0);
    for team in q.iter(app.world()) {
        if team.0 == 0 { blue += 1 } else { red += 1 }
    }
    assert_eq!((blue, red), (5, 6));
    assert_eq!(app.world().resource::<controller::WorldBounds>().spawn.x, 28.0, "spawn moved to the fort gate");
    let mut q = app.world_mut().query::<(Entity, &Team)>();
    let red_bot = q.iter(app.world()).find(|(_, t)| t.0 == 1).map(|(e, _)| e).unwrap();
    app.world_mut().resource_mut::<Messages<Damage>>().write(Damage { entity: red_bot, amount: 1000.0, impulse: Vec3::ZERO });
    run(&mut app, 0.1);
    assert_eq!(app.world().resource::<crate::bots::MatchState>().score, [1, 0]);
}

#[test]
fn splat_weights_sum_to_one_and_follow_the_ground() {
    let island = Island::default();
    let sum = |w: [f32; 4]| w.iter().sum::<f32>();
    for (p, h, ny) in [(Vec2::ZERO, 40.0, 1.0), (Vec2::new(300.0, -200.0), 2.0, 0.95), (Vec2::new(-50.0, 90.0), 120.0, 0.5), (Vec2::new(17.0, 400.0), 240.0, 0.9)] {
        let w = terrain::splat_weights(p, h, ny, &island);
        assert!((sum(w) - 1.0).abs() < 1e-4, "weights {w:?} sum to one");
        assert!(w.iter().all(|x| *x >= -1e-6), "no negative weight in {w:?}");
    }
    let cliff = terrain::splat_weights(Vec2::ZERO, 60.0, 0.5, &island);
    assert!(cliff[2] > 0.9, "a cliff is rock: {cliff:?}");
    let beach = terrain::splat_weights(Vec2::ZERO, island.water_level + 1.0, 1.0, &island);
    assert!(beach[3] > 0.9, "the shore is sand: {beach:?}");
    let meadow = terrain::splat_weights(Vec2::new(500.0, 500.0), 40.0, 1.0, &island);
    assert!(meadow[0] + meadow[1] > 0.95, "flat land is grass or dirt: {meadow:?}");
}

#[test]
fn vegetation_keeps_off_the_pads_the_water_and_the_cliffs() {
    use crate::veg::{self, Plant};
    let island = Island::default();
    let mut hm = terrain::generate(&island);
    let sites = crate::island::place(&mut hm, &island);
    let placed = veg::place(&hm, &island, &sites, 1.0);
    let pines = placed.iter().filter(|p| p.kind == Plant::Pine).count();
    let rocks = placed.iter().filter(|p| p.kind == Plant::Rock).count();
    assert!(pines > 2000 && rocks > 200, "{pines} pines, {rocks} rocks");
    for p in &placed {
        let q = p.pos.xz();
        assert!(hm.height_at(q.x, q.y) > island.water_level + 2.0, "{:?} at {q} is on land", p.kind);
        for s in &sites {
            assert!(s.center.distance(q) > s.radius + 10.0, "{:?} at {q} is clear of {}", p.kind, s.name);
        }
        if p.kind == Plant::Pine {
            assert!(hm.normal_at(q.x, q.y).y > 0.75, "pines stand on gentle ground");
        }
    }
    assert!(veg::place(&hm, &island, &sites, 0.0).is_empty(), "density 0 grows nothing");
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
fn roads_join_camp_to_every_site_and_leave_the_pads_alone() {
    let island = Island::default();
    let mut hm = terrain::generate(&island);
    let sites = crate::island::place(&mut hm, &island);
    let pads = hm.clone();
    let roads = crate::roads::carve(&mut hm, &sites, &island);
    assert!(roads.segments.len() > 40, "{} segments", roads.segments.len());
    for site in sites.iter().take(6) {
        // The pads are where they were.
        for (dx, dz) in [(0.0, 0.0), (0.5, 0.5), (-0.6, 0.3)] {
            let (x, z) = (site.center.x + dx * site.pad, site.center.y + dz * site.pad);
            assert_eq!(hm.height_at(x, z), pads.height_at(x, z), "{} pad untouched", site.name);
        }
        // A road reaches each site's edge.
        let near = roads.segments.iter().flat_map(|(a, b)| [a.xz(), b.xz()]).map(|p| p.distance(site.center)).fold(f32::MAX, f32::min);
        assert!(near < site.radius + 10.0, "{} is {near} m from the nearest road", site.name);
    }
    // Driveable: the carved surface along every road is gentle and above the sea.
    for (a, b) in &roads.segments {
        let grade = (b.y - a.y).abs() / a.xz().distance(b.xz()).max(1.0);
        assert!(grade < 0.16, "grade {grade} between {a} and {b}");
        let mid = (a.xz() + b.xz()) / 2.0;
        assert!(hm.height_at(mid.x, mid.y) > island.water_level, "road above water at {mid}");
        assert!(roads.on_road(mid));
    }
    assert!(!roads.on_road(Vec2::new(5000.0, 5000.0)));
}

#[test]
fn roads_grip_better_than_grass() {
    // The same hard brake from 15 m/s stops shorter on a road.
    let stop = |road: bool| {
        let mut app = vehicle_app();
        if road {
            app.insert_resource(crate::roads::Roads { segments: vec![(Vec3::new(40.0, 0.0, 100.0), Vec3::new(40.0, 0.0, -200.0))] });
        }
        let e = spawn_vehicle(&mut app, Kind::Jeep, Vec3::new(40.0, 0.0, 40.0), 0.0);
        run(&mut app, 1.0);
        set_player(&mut app, Vec3::new(42.0, 1.0, 40.0), Vec3::ZERO);
        input(&mut app).interact_pressed = true;
        run(&mut app, 0.1);
        app.world_mut().entity_mut(e).insert(LinearVelocity(Vec3::new(0.0, 0.0, -15.0)));
        input(&mut app).movement = Vec2::new(0.0, -1.0);
        run(&mut app, 0.05);
        let (start, _, _, _) = vehicle_state(&mut app, e);
        for _ in 0..100 {
            run(&mut app, 0.05);
            let (end, _, vel, _) = vehicle_state(&mut app, e);
            if vel.length() < 1.0 {
                return start.z - end.z;
            }
        }
        panic!("never stopped");
    };
    let (road, grass) = (stop(true), stop(false));
    assert!(road < grass * 0.9, "road {road} m vs grass {grass} m");
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
    app.world_mut().get_mut::<Vehicle>(e).unwrap().fuel = 0.0;
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

#[test]
fn the_sun_rises_sets_and_the_night_is_dark() {
    use crate::world::Clock;
    let noon = Clock { hour: 12.0 };
    let midnight = Clock { hour: 0.0 };
    assert!(noon.sun_dir().y > 0.7 && noon.daylight() == 1.0);
    assert!(midnight.sun_dir().y < -0.7 && midnight.daylight() == 0.0);
    assert!(Clock { hour: 7.0 }.sun_dir().x > 0.5, "rises in the east");
    assert!(Clock { hour: 17.0 }.sun_dir().x < -0.5, "sets in the west");
    let dusk = Clock { hour: 18.2 }.daylight();
    assert!(dusk > 0.0 && dusk < 1.0, "dusk is a ramp: {dusk}");
}

#[test]
fn weather_changes_smoothly_and_rain_wets_the_ground() {
    use crate::world::{Sky, Weather};
    let mut w = Weather::default();
    let mut seen = std::collections::HashSet::new();
    let mut prev = w.clone();
    for _ in 0..(4 * 3600) {
        w.step(1.0, 6.0);
        assert!((w.rain - prev.rain).abs() < 0.03 && (w.fog - prev.fog).abs() < 0.03, "no jumps");
        seen.insert(format!("{:?}", w.sky));
        if w.sky == Sky::Rain && w.rain > 0.8 {
            assert!(w.wet > 0.0);
        }
        prev = w.clone();
    }
    assert!(seen.len() == 4, "every sky turns up in four hours: {seen:?}");
}

#[test]
fn a_crosswind_pushes_bullets_sideways() {
    use crate::weapon::Bullet;
    let mut app = make_app(Tuning::default());
    app.insert_resource(crate::world::Wind(Vec3::new(10.0, 0.0, 0.0)));
    select_weapon(&mut app, WeaponKind::Pistol);
    input(&mut app).fire_pressed = true;
    run(&mut app, 0.5);
    let mut q = app.world_mut().query::<&Bullet>();
    let b = q.single(app.world()).expect("a bullet in the air");
    assert!(b.velocity.x > 0.3, "drifting downwind: {}", b.velocity);
}
