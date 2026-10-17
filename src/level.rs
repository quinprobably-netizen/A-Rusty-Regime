use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;

use crate::targets::{self, TargetAssets};
use crate::tuning::Tuning;

/// Test level: open arena with ramps, a wall-run wall, a parkour
/// course, and a physics playground of dynamic props.
pub struct LevelPlugin;

impl Plugin for LevelPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(ClearColor(Color::srgb(0.55, 0.7, 0.85)))
            .add_systems(Startup, (spawn_level, spawn_props, spawn_range.after(targets::load_assets)));
    }
}

fn spawn_level(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let floor_mat = materials.add(Color::srgb(0.35, 0.37, 0.4));
    let wall_mat = materials.add(Color::srgb(0.55, 0.5, 0.45));
    let ramp_mat = materials.add(Color::srgb(0.8, 0.45, 0.2));
    let box_mat = materials.add(Color::srgb(0.3, 0.55, 0.75));
    let goal_mat = materials.add(Color::srgb(0.3, 0.75, 0.4));
    let crate_mat = materials.add(Color::srgb(0.65, 0.48, 0.28));
    let barrel_mat = materials.add(Color::srgb(0.7, 0.2, 0.2));
    let ball_mat = materials.add(Color::srgb(0.9, 0.8, 0.2));

    let mut block = |size: Vec3, transform: Transform, mat: &Handle<StandardMaterial>| {
        commands.spawn((
            Mesh3d(meshes.add(Cuboid::from_size(size))),
            MeshMaterial3d(mat.clone()),
            transform,
            RigidBody::Static,
            Collider::cuboid(size.x, size.y, size.z),
        ));
    };
    let at = |x: f32, y: f32, z: f32| Transform::from_xyz(x, y, z);

    // Floor and perimeter walls
    block(Vec3::new(120.0, 1.0, 120.0), at(0.0, -0.5, 0.0), &floor_mat);
    for (pos, size) in [
        (Vec3::new(0.0, 5.0, -60.0), Vec3::new(120.0, 10.0, 1.0)),
        (Vec3::new(0.0, 5.0, 60.0), Vec3::new(120.0, 10.0, 1.0)),
        (Vec3::new(-60.0, 5.0, 0.0), Vec3::new(1.0, 10.0, 120.0)),
        (Vec3::new(60.0, 5.0, 0.0), Vec3::new(1.0, 10.0, 120.0)),
    ] {
        block(size, Transform::from_translation(pos), &wall_mat);
    }

    // Ramps of increasing steepness (ramp slides / launches)
    for (i, angle) in [15.0_f32, 30.0, 45.0].into_iter().enumerate() {
        block(
            Vec3::new(8.0, 0.5, 20.0),
            at(-30.0 + i as f32 * 15.0, 2.5, -30.0).with_rotation(Quat::from_rotation_x(angle.to_radians())),
            &ramp_mat,
        );
    }

    // Long wall for wall running
    block(Vec3::new(1.0, 8.0, 40.0), at(30.0, 4.0, 0.0), &wall_mat);

    // Box steps of increasing height (jump / crouch-jump / mantle targets)
    for i in 0..6 {
        let h = 0.5 + i as f32 * 0.5;
        block(Vec3::new(3.0, h, 3.0), at(-20.0 + i as f32 * 4.0, h / 2.0, 20.0), &box_mat);
    }

    // --- Parkour course ---

    // Wall-run gap: climb onto platform A, wall-run across to platform B.
    block(Vec3::new(4.0, 1.5, 4.0), at(34.0, 0.75, -50.0), &box_mat);
    block(Vec3::new(8.0, 3.0, 8.0), at(40.0, 1.5, -50.0), &box_mat);
    block(Vec3::new(1.0, 8.0, 24.0), at(45.0, 4.0, -38.0), &wall_mat);
    block(Vec3::new(8.0, 3.0, 8.0), at(40.0, 1.5, -28.0), &goal_mat);

    // Wall-jump chimney: alternate wall jumps up to the goal on top.
    block(Vec3::new(1.0, 12.0, 8.0), at(-47.5, 6.0, -48.0), &wall_mat);
    block(Vec3::new(1.0, 11.0, 8.0), at(-43.5, 5.5, -48.0), &wall_mat);
    block(Vec3::new(6.0, 1.0, 8.0), at(-40.5, 11.5, -48.0), &goal_mat);

    // Mantle tower: three 1.8 m ledges.
    for i in 0..3 {
        let h = 1.8 * (i + 1) as f32;
        block(Vec3::new(4.0, h, 4.0), at(-18.0 + i as f32 * 4.0, h / 2.0, -50.0), &box_mat);
    }

    // Slide tunnel: too low to walk through standing.
    block(Vec3::new(5.0, 0.5, 20.0), at(12.0, 1.75, 40.0), &wall_mat);
    block(Vec3::new(0.5, 2.0, 20.0), at(9.75, 1.0, 40.0), &wall_mat);
    block(Vec3::new(0.5, 2.0, 20.0), at(14.25, 1.0, 40.0), &wall_mat);

    // --- Physics playground ---
    let mut prop = |mesh: Mesh, collider: Collider, mass: f32, pos: Vec3, mat: &Handle<StandardMaterial>| {
        commands.spawn((
            Mesh3d(meshes.add(mesh)),
            MeshMaterial3d(mat.clone()),
            Transform::from_translation(pos),
            RigidBody::Dynamic,
            collider,
            Mass(mass),
        ));
    };

    // Crate pyramid
    for layer in 0..4 {
        let n = 4 - layer;
        for i in 0..n {
            for j in 0..n {
                let off = (n as f32 - 1.0) / 2.0;
                let pos = Vec3::new(16.0 + i as f32 - off, 0.5 + layer as f32, -6.0 + j as f32 - off);
                prop(Cuboid::from_length(1.0).into(), Collider::cuboid(1.0, 1.0, 1.0), 40.0, pos, &crate_mat);
            }
        }
    }
    // Heavy crates
    for i in 0..3 {
        let pos = Vec3::new(22.0, 1.0, 2.0 + i as f32 * 2.5);
        prop(Cuboid::from_length(2.0).into(), Collider::cuboid(2.0, 2.0, 2.0), 150.0, pos, &crate_mat);
    }
    // Barrels
    for i in 0..6 {
        let pos = Vec3::new(12.0, 0.6, -10.0 - i as f32 * 1.2);
        prop(Cylinder::new(0.4, 1.2).into(), Collider::cylinder(0.4, 1.2), 25.0, pos, &barrel_mat);
    }
    // Balls
    for i in 0..5 {
        let pos = Vec3::new(20.0 + i as f32 * 1.2, 0.5, -14.0);
        prop(Sphere::new(0.5).into(), Collider::sphere(0.5), 10.0, pos, &ball_mat);
    }
    // Dominoes
    for i in 0..12 {
        let pos = Vec3::new(-10.0, 1.0, -2.0 - i as f32 * 1.2);
        prop(Cuboid::new(1.2, 2.0, 0.3).into(), Collider::cuboid(1.2, 2.0, 0.3), 20.0, pos, &box_mat);
    }

    commands.spawn((
        DirectionalLight {
            illuminance: 10_000.0,
            shadow_maps_enabled: true,
            ..default()
        },
        // Also sees the shadow-only layer, so the player's hidden head still casts a shadow.
        bevy::camera::visibility::RenderLayers::from_layers(&[0, crate::body::SHADOW_ONLY_LAYER]),
        Transform::from_xyz(20.0, 40.0, 10.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
}

/// Kenney Mini Arena glTF props. Static ones get a simple collider;
/// dynamic ones are boxes you can shoot around.
fn spawn_props(mut commands: Commands, server: Res<AssetServer>) {
    let model = |name: &str| server.load(GltfAssetLabel::Scene(0).from_asset(format!("models/arena/{name}.glb")));
    let column = model("column");
    let column_damaged = model("column-damaged");
    let statue = model("statue");
    let tree = model("tree");
    let banner = model("banner");
    let rack = model("weapon-rack");
    let trophy = model("trophy");
    let block = model("block");
    let bricks = model("bricks");

    // A prop whose model origin is at its base, standing on the ground at `pos`.
    let mut standing = |asset: &Handle<_>, pos: Vec3, scale: f32, yaw: f32, collider: Collider, body: RigidBody, center_y: f32| {
        commands
            .spawn((
                body,
                collider,
                Transform::from_translation(pos + Vec3::Y * center_y).with_rotation(Quat::from_rotation_y(yaw)),
                Visibility::default(),
            ))
            .with_child((
                WorldAssetRoot(asset.clone()),
                Transform::from_xyz(0.0, -center_y, 0.0).with_scale(Vec3::splat(scale)),
            ));
    };

    // Colonnade around the spawn point (model is 1 m tall, scaled x2.5).
    for (x, z) in [(-7.0, 4.0), (7.0, 4.0), (-7.0, 16.0), (7.0, 16.0)] {
        standing(&column, Vec3::new(x, 0.0, z), 2.5, 0.0, Collider::cylinder(0.75, 2.5), RigidBody::Static, 1.25);
    }
    standing(&column_damaged, Vec3::new(-7.0, 0.0, 10.0), 2.5, 0.4, Collider::cylinder(0.75, 1.8), RigidBody::Static, 0.9);
    standing(&column_damaged, Vec3::new(7.0, 0.0, 10.0), 2.5, 2.1, Collider::cylinder(0.75, 1.8), RigidBody::Static, 0.9);
    // Statues flanking the way to the playground, on heavy blocks.
    for x in [-3.0, 3.0] {
        standing(&block, Vec3::new(x, 0.0, 0.0), 1.5, 0.0, Collider::cuboid(1.5, 0.75, 1.5), RigidBody::Static, 0.375);
        standing(&statue, Vec3::new(x, 0.75, 0.0), 1.5, if x < 0.0 { 0.6 } else { -0.6 }, Collider::cylinder(0.5, 2.0), RigidBody::Static, 1.0);
    }
    standing(&trophy, Vec3::new(0.0, 0.0, 14.0), 2.0, 0.0, Collider::cylinder(0.5, 0.96), RigidBody::Static, 0.48);
    standing(&rack, Vec3::new(-4.0, 0.0, 14.0), 2.0, 1.2, Collider::cuboid(1.6, 0.94, 0.6), RigidBody::Static, 0.47);
    standing(&rack, Vec3::new(4.0, 0.0, 14.0), 2.0, -1.2, Collider::cuboid(1.6, 0.94, 0.6), RigidBody::Static, 0.47);

    // Trees along the perimeter walls.
    for i in 0..10 {
        let z = -54.0 + i as f32 * 12.0;
        standing(&tree, Vec3::new(-57.0, 0.0, z), 3.5, i as f32, Collider::cylinder(0.5, 6.7), RigidBody::Static, 3.36);
        standing(&tree, Vec3::new(57.0, 0.0, z + 6.0), 3.5, i as f32 * 1.3, Collider::cylinder(0.5, 6.7), RigidBody::Static, 3.36);
    }
    // Banners on the wall-run wall.
    for i in 0..4 {
        standing(&banner, Vec3::new(29.4, 2.0, -15.0 + i as f32 * 10.0), 3.0, -std::f32::consts::FRAC_PI_2, Collider::cuboid(0.3, 3.0, 1.8), RigidBody::Static, 1.5);
    }

    // Dynamic blocks and brick piles to shoot around.
    for i in 0..5 {
        let pos = Vec3::new(-16.0 + i as f32 * 1.6, 0.0, 6.0);
        standing(&block, pos, 1.5, 0.0, Collider::cuboid(1.5, 0.75, 1.5), RigidBody::Dynamic, 0.375);
    }
    for i in 0..6 {
        let pos = Vec3::new(-14.0 + (i % 3) as f32 * 1.4, (i / 3) as f32 * 0.65, 9.0);
        standing(&bricks, pos, 1.5, 0.0, Collider::cuboid(1.17, 0.62, 1.26), RigidBody::Dynamic, 0.31);
    }
}

/// Shooting range along the south wall: a line of dummies and drones circling above.
fn spawn_range(mut commands: Commands, tuning: Res<Tuning>, assets: Option<Res<TargetAssets>>) {
    let assets = assets.as_deref();
    for i in 0..6 {
        let x = -20.0 + i as f32 * 8.0;
        targets::spawn_dummy(&mut commands, &tuning, assets, Vec3::new(x, 0.0, 30.0), std::f32::consts::PI);
    }
    for i in 0..3 {
        let x = -20.0 + i as f32 * 20.0;
        targets::spawn_drone(&mut commands, &tuning, assets, Vec3::new(x, 5.0, 36.0), 4.0, i as f32 * 2.1);
    }
    // A couple more guarding the parkour course.
    targets::spawn_drone(&mut commands, &tuning, assets, Vec3::new(40.0, 7.0, -40.0), 6.0, 0.0);
    targets::spawn_dummy(&mut commands, &tuning, assets, Vec3::new(-40.5, 12.0, -48.0), std::f32::consts::FRAC_PI_2);
}
