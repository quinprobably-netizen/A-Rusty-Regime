//! Code-generated vegetation and rocks (hyper-realism stage R1): pines and scrub placed by
//! noise over the island, boulders on the steep ground, and grass blades built in cells
//! around the player as they move. No model files: every mesh is made here.

use avian3d::prelude::*;
use bevy::camera::visibility::VisibilityRange;
use bevy::mesh::VertexAttributeValues;
use bevy::prelude::*;

use crate::controller::Player;
use crate::island::{Placed, Sites};
use crate::look::Textures;
use crate::terrain::{splat_weights, value_noise, Heightmap};
use crate::tuning::{Island, Tuning};

pub struct VegPlugin;

impl Plugin for VegPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(crate::boot::Boot::Ready), spawn.after(crate::terrain::spawn_terrain))
            .add_systems(Update, grass.run_if(|t: Res<Tuning>| t.graphics.grass).run_if(resource_exists::<Heightmap>));
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Plant {
    Pine,
    Scrub,
    Rock,
}

#[derive(Clone, Debug)]
pub struct Placement {
    pub kind: Plant,
    pub pos: Vec3,
    pub yaw: f32,
    pub scale: f32,
    pub variant: usize,
}

fn hash(p: Vec2, salt: f32) -> f32 {
    let v = (p.dot(Vec2::new(269.5, 183.3)) + salt * 7.13).sin() * 24634.635;
    v - v.floor()
}

/// Where everything grows: one candidate per 18 m cell, kept by the forest noise, the slope,
/// the height, and distance from the sites' pads.
pub fn place(hm: &Heightmap, island: &Island, sites: &[Placed], density: f32) -> Vec<Placement> {
    let mut out = Vec::new();
    if density <= 0.0 {
        return out;
    }
    const CELL: f32 = 18.0;
    let cells = (island.size / CELL) as i32;
    let clear = |p: Vec2| sites.iter().any(|s| s.center.distance(p) < s.radius + 12.0);
    for cz in 1..cells - 1 {
        for cx in 1..cells - 1 {
            let cell = Vec2::new(cx as f32, cz as f32);
            let p = (cell + Vec2::new(hash(cell, 1.0), hash(cell, 2.0))) * CELL - island.size / 2.0;
            let h = hm.height_at(p.x, p.y);
            if h < island.water_level + 2.5 || clear(p) {
                continue;
            }
            let ny = hm.normal_at(p.x, p.y).y;
            let forest = value_noise(p * 0.0025) * 0.7 + value_noise(p * 0.009) * 0.3;
            let roll = hash(cell, 3.0);
            let variant = (hash(cell, 4.0) * 3.0) as usize;
            let yaw = hash(cell, 5.0) * std::f32::consts::TAU;
            let treeline = h < 0.7 * island.height;
            if treeline && ny > 0.78 && forest > 0.48 && roll < density * (forest - 0.48) * 3.0 {
                out.push(Placement { kind: Plant::Pine, pos: Vec3::new(p.x, h - 0.2, p.y), yaw, scale: 0.7 + hash(cell, 6.0) * 0.7, variant });
            } else if treeline && ny > 0.7 && roll < density * 0.22 {
                out.push(Placement { kind: Plant::Scrub, pos: Vec3::new(p.x, h - 0.1, p.y), yaw, scale: 0.6 + hash(cell, 6.0) * 1.0, variant });
            } else if (ny < 0.84 && roll < 0.35) || roll < 0.03 {
                out.push(Placement { kind: Plant::Rock, pos: Vec3::new(p.x, h - 0.3, p.y), yaw, scale: 0.6 + hash(cell, 6.0) * 2.2, variant });
            }
        }
    }
    out
}

fn colored(mut mesh: Mesh, color: [f32; 4]) -> Mesh {
    let n = mesh.count_vertices();
    mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, vec![color; n]);
    mesh
}

/// A pine: a trunk and three stacked cones, vertex colored. About 8 m tall at scale 1.
fn pine_mesh(variant: usize) -> Mesh {
    let bark = Color::srgb(0.3, 0.2, 0.12).to_linear().to_f32_array();
    let tint = [0.0, 0.04, -0.03][variant];
    let needles = Color::srgb(0.07 + tint, 0.19 + tint * 0.5, 0.07).to_linear().to_f32_array();
    let mut mesh = colored(Mesh::from(Cylinder::new(0.22, 2.4)).translated_by(Vec3::Y * 1.2), bark);
    for (r, h, y) in [(2.4, 2.6, 1.3), (2.0, 2.6, 2.7), (1.5, 2.6, 4.1), (1.0, 2.8, 5.5)] {
        let w = 1.0 + (variant as f32 - 1.0) * 0.12;
        let cone = colored(Mesh::from(Cone { radius: r * w, height: h }).translated_by(Vec3::Y * (y + h / 2.0)), needles);
        mesh.merge(&cone).expect("same attributes");
    }
    mesh
}

/// Scrub: a squashed ico-sphere.
fn scrub_mesh(variant: usize) -> Mesh {
    let tint = [0.0, 0.05, -0.04][variant];
    let leaf = Color::srgb(0.22 + tint, 0.3, 0.1).to_linear().to_f32_array();
    colored(Sphere::new(1.0).mesh().ico(1).expect("ico").scaled_by(Vec3::new(1.0, 0.6, 1.0)).translated_by(Vec3::Y * 0.4), leaf)
}

/// A boulder: an ico-sphere pushed in and out by noise, faceted.
fn rock_mesh(variant: usize) -> Mesh {
    let mut mesh = Sphere::new(1.0).mesh().ico(2).expect("ico");
    if let Some(VertexAttributeValues::Float32x3(pos)) = mesh.attribute_mut(Mesh::ATTRIBUTE_POSITION) {
        for p in pos.iter_mut() {
            let v = Vec3::from(*p);
            let k = value_noise(Vec2::new(v.x * 1.7 + v.z * 0.9 + variant as f32 * 3.1, v.y * 1.9 - v.x * 0.6)) - 0.5;
            let r = (1.0 + 0.5 * k) * Vec3::new(1.2, 0.75, 1.0);
            *p = (v * r).to_array();
        }
    }
    mesh.remove_attribute(Mesh::ATTRIBUTE_NORMAL);
    mesh.remove_attribute(Mesh::ATTRIBUTE_UV_0);
    let mesh = mesh.with_duplicated_vertices().with_computed_flat_normals();
    colored(mesh, Color::srgb(0.5, 0.48, 0.45).to_linear().to_f32_array())
}

fn spawn(
    mut commands: Commands,
    hm: Res<Heightmap>,
    sites: Res<Sites>,
    tuning: Res<Tuning>,
    textures: Option<Res<Textures>>,
    roads: Option<Res<crate::roads::Roads>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let g = &tuning.graphics;
    let start = std::time::Instant::now();
    let mut placed = place(&hm, &tuning.island, &sites.0, g.trees);
    if let Some(roads) = &roads {
        placed.retain(|p| roads.nearest(p.pos.xz()).is_none_or(|(d, _)| d > crate::roads::HALF_WIDTH + 4.0));
    }
    let pines: Vec<_> = (0..3).map(|v| meshes.add(pine_mesh(v))).collect();
    let scrubs: Vec<_> = (0..3).map(|v| meshes.add(scrub_mesh(v))).collect();
    let rocks: Vec<_> = (0..3).map(|v| meshes.add(rock_mesh(v))).collect();
    let plant = materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.95, ..default() });
    let gray = materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.9, ..default() });
    let range = |far: f32| VisibilityRange { start_margin: 0.0..0.0, end_margin: (far - 120.0).max(50.0)..far, use_aabb: false };
    let (mut trees, mut rocks_n) = (0, 0);
    for p in &placed {
        let tf = Transform::from_translation(p.pos).with_rotation(Quat::from_rotation_y(p.yaw)).with_scale(Vec3::splat(p.scale));
        match p.kind {
            Plant::Pine => {
                trees += 1;
                commands.spawn((
                    Mesh3d(pines[p.variant].clone()),
                    MeshMaterial3d(plant.clone()),
                    tf,
                    range(g.tree_range),
                    RigidBody::Static,
                    Collider::compound(vec![(Vec3::Y * 1.6, Quat::IDENTITY, Collider::cylinder(0.28, 3.2))]),
                ));
            }
            Plant::Scrub => {
                commands.spawn((Mesh3d(scrubs[p.variant].clone()), MeshMaterial3d(plant.clone()), tf, range(g.tree_range * 0.5)));
            }
            Plant::Rock => {
                rocks_n += 1;
                let mut e = commands.spawn((Mesh3d(rocks[p.variant].clone()), tf, range(g.tree_range), RigidBody::Static, Collider::sphere(0.85)));
                match &textures {
                    Some(t) => e.insert(MeshMaterial3d(t.rock.clone())),
                    None => e.insert(MeshMaterial3d(gray.clone())),
                };
            }
        }
    }
    info!("vegetation: {trees} pines, {} scrub, {rocks_n} rocks in {:.0} ms", placed.len() - trees - rocks_n, start.elapsed().as_secs_f32() * 1000.0);
}

/// One 24 m cell of grass blades.
#[derive(Component)]
struct GrassCell(IVec2);

const GRASS_CELL: f32 = 24.0;

fn grass_mesh(hm: &Heightmap, island: &Island, cell: IVec2, blades: u32) -> Mesh {
    use bevy::asset::RenderAssetUsages;
    use bevy::mesh::PrimitiveTopology;
    let o = cell.as_vec2() * GRASS_CELL;
    let dark = Color::srgb(0.09, 0.17, 0.04).to_linear().to_vec3();
    let light = Color::srgb(0.33, 0.47, 0.15).to_linear().to_vec3();
    let mut positions = Vec::with_capacity(blades as usize * 3);
    let mut normals = Vec::with_capacity(positions.capacity());
    let mut colors = Vec::with_capacity(positions.capacity());
    for i in 0..blades {
        let k = Vec2::new(i as f32, cell.x as f32 * 31.0 + cell.y as f32 * 17.0);
        let p = o + Vec2::new(hash(k, 1.0), hash(k, 2.0)) * GRASS_CELL;
        let h = hm.height_at(p.x, p.y);
        let n = hm.normal_at(p.x, p.y);
        let w = splat_weights(p, h, n.y, island);
        if hash(k, 3.0) > w[0] * w[0] * 1.1 {
            continue;
        }
        let yaw = hash(k, 4.0) * std::f32::consts::TAU;
        let right = Vec3::new(yaw.cos(), 0.0, yaw.sin()) * (0.012 + hash(k, 5.0) * 0.02);
        let height = 0.18 + hash(k, 6.0) * 0.32;
        let lean = Vec3::new(-right.z, 0.0, right.x).normalize_or_zero() * (hash(k, 7.0) - 0.5) * 0.9 * height;
        let base = Vec3::new(p.x, h, p.y);
        let tip = base + Vec3::Y * height + lean;
        let shade = 0.8 + hash(k, 8.0) * 0.4;
        positions.extend([(base - right).to_array(), (base + right).to_array(), tip.to_array()]);
        normals.extend([n.to_array(); 3]);
        colors.extend([(dark * shade).extend(1.0).to_array(), (dark * shade).extend(1.0).to_array(), (light * shade).extend(1.0).to_array()]);
    }
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, colors)
}

/// Keeps the 7 by 7 cells of blades around the player built (fading out past 55 m), and drops the ones left behind.
#[allow(clippy::too_many_arguments)]
fn grass(
    mut commands: Commands,
    hm: Res<Heightmap>,
    tuning: Res<Tuning>,
    player: Single<&Transform, With<Player>>,
    cells: Query<(Entity, &GrassCell)>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut material: Local<Option<Handle<StandardMaterial>>>,
) {
    let material = material
        .get_or_insert_with(|| materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 1.0, cull_mode: None, double_sided: true, ..default() }))
        .clone();
    let center = (player.translation.xz() / GRASS_CELL).floor().as_ivec2();
    let mut have = Vec::new();
    for (e, c) in &cells {
        let d = (c.0 - center).abs().max_element();
        if d > 4 {
            commands.entity(e).despawn();
        } else {
            have.push(c.0);
        }
    }
    let mut built = 0;
    for dz in -3..=3 {
        for dx in -3..=3 {
            let cell = center + IVec2::new(dx, dz);
            if have.contains(&cell) || built >= 4 {
                continue;
            }
            built += 1;
            let mesh = grass_mesh(&hm, &tuning.island, cell, tuning.graphics.grass_density);
            commands.spawn((
                Name::new("Grass"),
                GrassCell(cell),
                Mesh3d(meshes.add(mesh)),
                MeshMaterial3d(material.clone()),
                Transform::default(),
                bevy::light::NotShadowCaster,
                VisibilityRange { start_margin: 0.0..0.0, end_margin: 55.0..80.0, use_aabb: true },
            ));
        }
    }
}
