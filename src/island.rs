//! The island's six sites: where they go on the heightmap, the pads stamped
//! for them, and what stands on each. Everything is generated blocks plus
//! Kenney props, built with a small `Kit`.

use avian3d::prelude::*;
use bevy::ecs::system::EntityCommands;
use bevy::prelude::*;
use bevy::world_serialization::WorldAssetRoot;
use std::f32::consts::{FRAC_PI_2, PI, TAU};

use crate::look::{SurfaceMaterial, Textures};
use crate::targets::{self, TargetAssets};
use crate::terrain::Heightmap;
use crate::tuning::{Island, Tuning};

/// A site resolved onto the heightmap: `center` and the height of its flat
/// pad (`pad` meters across), with `radius` the whole site's footprint.
#[derive(Clone, Debug)]
#[allow(dead_code)] // `pad` and `radius` are read by the tests and later stages
pub struct Placed {
    pub name: &'static str,
    pub center: Vec2,
    pub height: f32,
    pub pad: f32,
    pub radius: f32,
}

impl Placed {
    pub fn origin(&self) -> Vec3 {
        Vec3::new(self.center.x, self.height, self.center.y)
    }
}

#[derive(Resource, Clone, Debug)]
pub struct Sites(pub Vec<Placed>);

const BASE_CAMP: usize = 0;
const TOWER: usize = 1;
const FORT: usize = 2;
const QUARRY: usize = 3;
const RUINS: usize = 4;
const LIGHTHOUSE: usize = 5;

/// Resolve the six sites and stamp their pads. Base camp is first (the
/// spawn), then the radio tower on the highest core sample, the fort east,
/// the quarry west, the ruins north and the lighthouse on the south coast.
pub fn place(hm: &mut Heightmap, island: &Island) -> Vec<Placed> {
    let min = island.water_level + 4.0;
    let mut sites = Vec::new();
    let flat = |hm: &mut Heightmap, name, center: Vec2, pad: f32, radius: f32, blend: f32| {
        let height = hm.height_at(center.x, center.y).max(min);
        hm.stamp_flat(center, pad, height, blend);
        Placed { name, center, height, pad, radius }
    };
    sites.push(flat(hm, "Base camp", Vec2::new(0.0, 350.0), 50.0, 55.0, 30.0));

    // Radio tower: highest sample inside the core, away from the camp.
    let mut best = (f32::MIN, Vec2::ZERO);
    for zi in 0..hm.n {
        for xi in 0..hm.n {
            let p = hm.sample_pos(xi, zi);
            if p.length() < island.core * 0.9 && p.distance(Vec2::new(0.0, 350.0)) > 250.0 {
                let h = hm.sample(xi, zi);
                if h > best.0 {
                    best = (h, p);
                }
            }
        }
    }
    sites.push(flat(hm, "Radio tower", best.1, 30.0, 35.0, 25.0));
    sites.push(flat(hm, "Fort", Vec2::new(900.0, 0.0), 60.0, 65.0, 30.0));

    // Quarry: four descending rings, the pit 18 m below the rim.
    let qc = Vec2::new(-900.0, 0.0);
    let rim = hm.height_at(qc.x, qc.y).max(min + 18.0);
    hm.stamp_flat(qc, 70.0, rim, 20.0);
    hm.stamp_flat(qc, 52.0, rim - 6.0, 10.0);
    hm.stamp_flat(qc, 36.0, rim - 12.0, 10.0);
    hm.stamp_flat(qc, 20.0, rim - 18.0, 10.0);
    sites.push(Placed { name: "Quarry", center: qc, height: rim - 18.0, pad: 20.0, radius: 90.0 });

    sites.push(flat(hm, "Ruins", Vec2::new(0.0, -900.0), 60.0, 65.0, 30.0));

    // Lighthouse: walk south from the core until the ground dips to the water, then step back inland.
    let mut z = island.core * 0.6;
    while z < island.size / 2.0 - 60.0 && hm.height_at(0.0, z) > island.water_level + 3.0 {
        z += 4.0;
    }
    sites.push(flat(hm, "Lighthouse", Vec2::new(0.0, z - 40.0), 30.0, 35.0, 20.0));

    // Extraction pads: three in the wilderness ring, each on the first dry, gentle ground inward from the coast.
    for (name, bearing) in [("Extract north", 1.95f32), ("Extract east", -0.35f32), ("Extract west", 3.8f32)] {
        let dir = Vec2::new(bearing.cos(), bearing.sin());
        let mut r = island.size / 2.0 - 250.0;
        let floor = island.core + 120.0;
        while r > floor {
            let c = dir * r;
            let h = hm.height_at(c.x, c.y);
            let gentle = [Vec2::X, Vec2::NEG_X, Vec2::Y, Vec2::NEG_Y].iter().all(|d| (hm.height_at(c.x + d.x * 20.0, c.y + d.y * 20.0) - h).abs() < 12.0);
            if h > island.water_level + 8.0 && gentle {
                break;
            }
            r -= 20.0;
        }
        sites.push(flat(hm, name, dir * r, 16.0, 18.0, 24.0));
    }
    sites
}

/// The site indices of the extraction pads.
pub fn extract_pads(sites: &[Placed]) -> impl Iterator<Item = &Placed> {
    sites.iter().filter(|p| p.name.starts_with("Extract"))
}

/// Materials for generated blocks.
#[derive(Clone, Copy)]
enum Mat {
    Stone,
    Wood,
    Metal,
    Goal,
    Crate,
    Barrel,
    Ball,
    Medkit,
}

/// Energy a bullet loses going through a block of `mat` that is `thickness` m thin, if it can.
fn cover(mat: Mat, thickness: f32) -> Option<f32> {
    match mat {
        Mat::Wood | Mat::Crate => Some((0.3 + thickness * 0.4).min(0.9)),
        Mat::Metal if thickness < 0.5 => Some(0.55),
        _ => None,
    }
}

/// Everything a site builder needs, with one shared cube mesh and material set.
struct Kit<'w, 's, 'a> {
    commands: &'a mut Commands<'w, 's>,
    meshes: &'a mut Assets<Mesh>,
    server: &'a AssetServer,
    tuning: &'a Tuning,
    targets: Option<&'a TargetAssets>,
    mats: [Handle<StandardMaterial>; 8],
    /// Textured concrete, wood and metal when the look is loaded.
    surfaces: Option<[Handle<SurfaceMaterial>; 3]>,
    hm: &'a Heightmap,
}

impl Kit<'_, '_, '_> {
    fn mat(&self, m: Mat) -> Handle<StandardMaterial> {
        self.mats[m as usize].clone()
    }

    /// A mesh with its material: the textured surface for stone, wood, crates and metal when
    /// available, else the flat color.
    fn surface(&mut self, mesh: Mesh, transform: Transform, mat: Mat) -> EntityCommands<'_> {
        let mesh = Mesh3d(self.meshes.add(mesh));
        let textured = self.surfaces.as_ref().and_then(|s| match mat {
            Mat::Stone => Some(s[0].clone()),
            Mat::Wood | Mat::Crate => Some(s[1].clone()),
            Mat::Metal => Some(s[2].clone()),
            _ => None,
        });
        match textured {
            Some(h) => self.commands.spawn((mesh, MeshMaterial3d(h), transform)),
            None => self.commands.spawn((mesh, MeshMaterial3d(self.mat(mat)), transform)),
        }
    }

    /// Static box centered at `center`, turned `yaw` around Y. Wood and thin metal can be shot through.
    fn block(&mut self, size: Vec3, center: Vec3, yaw: f32, mat: Mat) {
        let mut e = self.surface(Cuboid::from_size(size).into(), Transform::from_translation(center).with_rotation(Quat::from_rotation_y(yaw)), mat);
        e.insert((RigidBody::Static, Collider::cuboid(size.x, size.y, size.z)));
        if let Some(cost) = cover(mat, size.min_element()) {
            e.insert(crate::weapon::Penetrable { cost });
        }
    }

    /// Static cylinder standing on `base`.
    fn cylinder(&mut self, radius: f32, height: f32, base: Vec3, mat: Mat) {
        self.surface(Cylinder::new(radius, height).into(), Transform::from_translation(base + Vec3::Y * height / 2.0), mat)
            .insert((RigidBody::Static, Collider::cylinder(radius, height)));
    }

    /// Dynamic prop from a primitive mesh, centered at `center`.
    fn dynamic(&mut self, mesh: Mesh, collider: Collider, mass: f32, center: Vec3, mat: Mat) {
        let mut e = self.surface(mesh, Transform::from_translation(center), mat);
        e.insert((RigidBody::Dynamic, collider, Mass(mass)));
        if let Some(cost) = cover(mat, 0.5) {
            e.insert(crate::weapon::Penetrable { cost });
        }
    }

    /// A medkit (white box, red cross) on the ground at `pos`.
    fn medkit(&mut self, pos: Vec3) {
        let box_ = self.meshes.add(Cuboid::new(0.5, 0.3, 0.4));
        let bar = self.meshes.add(Cuboid::new(0.3, 0.02, 0.08));
        let bar2 = self.meshes.add(Cuboid::new(0.08, 0.02, 0.3));
        let (white, red) = (self.mat(Mat::Medkit), self.mat(Mat::Barrel));
        self.commands
            .spawn((Name::new("Medkit"), crate::loot::Medkit { down: 0.0 }, Mesh3d(box_), MeshMaterial3d(white), Transform::from_translation(pos + Vec3::Y * 0.15), Visibility::default()))
            .with_children(|k| {
                k.spawn((Mesh3d(bar), MeshMaterial3d(red.clone()), Transform::from_xyz(0.0, 0.16, 0.0)));
                k.spawn((Mesh3d(bar2), MeshMaterial3d(red), Transform::from_xyz(0.0, 0.16, 0.0)));
            });
    }

    /// Kenney arena prop whose origin is at its base, standing at `base`.
    #[allow(clippy::too_many_arguments)]
    fn prop(&mut self, name: &str, base: Vec3, scale: f32, yaw: f32, collider: Collider, center_y: f32, dynamic: bool) {
        let asset = self.server.load(GltfAssetLabel::Scene(0).from_asset(format!("models/arena/{name}.glb")));
        self.commands
            .spawn((
                if dynamic { RigidBody::Dynamic } else { RigidBody::Static },
                collider,
                Transform::from_translation(base + Vec3::Y * center_y).with_rotation(Quat::from_rotation_y(yaw)),
                Visibility::default(),
            ))
            .with_child((WorldAssetRoot(asset), Transform::from_xyz(0.0, -center_y, 0.0).with_scale(Vec3::splat(scale))));
    }

    fn column(&mut self, base: Vec3, damaged: bool) {
        if damaged {
            self.prop("column-damaged", base, 2.5, base.x * 0.3, Collider::cylinder(0.75, 1.8), 0.9, false);
        } else {
            self.prop("column", base, 2.5, 0.0, Collider::cylinder(0.75, 2.5), 1.25, false);
        }
    }

    fn tree(&mut self, base: Vec3, seed: f32) {
        self.prop("tree", base, 3.5, seed, Collider::cylinder(0.5, 6.7), 3.36, false);
    }

    fn soldier(&mut self, route: Vec<Vec3>) {
        targets::spawn_soldier(self.commands, self.tuning, self.targets, route);
    }

    fn drone(&mut self, center: Vec3, radius: f32, phase: f32) {
        targets::spawn_drone(self.commands, self.tuning, self.targets, center, radius, phase);
    }

    /// A cache worth `value` lying at `pos` (its base).
    fn loot(&mut self, pos: Vec3, value: u32, key: Option<usize>) {
        let mat = if key.is_some() { Mat::Goal } else { Mat::Crate };
        self.surface(Cuboid::new(0.7, 0.5, 0.5).into(), Transform::default(), mat).insert(crate::loot::bundle(pos, value, key));
    }

    /// A cache on the ground at island coordinates `(x, z)`.
    fn ground_loot(&mut self, x: f32, z: f32, value: u32) {
        let y = self.hm.height_at(x, z);
        self.loot(Vec3::new(x, y, z), value, None);
    }

    /// An extraction pad: a lit disc you stand on.
    fn extract_pad(&mut self, p: &Placed) {
        let o = p.origin();
        self.commands.spawn((
            Name::new(p.name),
            crate::loot::ExtractPad { radius: 10.0 },
            Mesh3d(self.meshes.add(Cylinder::new(10.0, 0.3))),
            MeshMaterial3d(self.mat(Mat::Goal)),
            Transform::from_translation(o + Vec3::Y * 0.15),
            RigidBody::Static,
            Collider::cylinder(10.0, 0.3),
        ));
        for (x, z) in [(-9.0, -9.0), (9.0, -9.0), (9.0, 9.0), (-9.0, 9.0)] {
            self.block(Vec3::new(0.4, 6.0, 0.4), o + Vec3::new(x, 3.0, z), 0.0, Mat::Metal);
            self.block(Vec3::new(0.8, 0.8, 0.8), o + Vec3::new(x, 6.4, z), 0.0, Mat::Goal);
        }
    }
}

/// Square loop of feet positions `half` meters from `o`, at `o.y`.
fn square(o: Vec3, half: f32) -> Vec<Vec3> {
    [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)].iter().map(|(x, z)| o + Vec3::new(x * half, 0.0, z * half)).collect()
}

pub fn spawn_sites(
    mut commands: Commands,
    sites: Res<Sites>,
    tuning: Res<Tuning>,
    server: Res<AssetServer>,
    targets: Option<Res<TargetAssets>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    vehicles: Option<Res<crate::vehicle::VehicleAssets>>,
    heightmap: Res<Heightmap>,
    textures: Option<Res<Textures>>,
) {
    let mats = [
        Color::srgb(0.55, 0.52, 0.48),
        Color::srgb(0.55, 0.38, 0.22),
        Color::srgb(0.6, 0.62, 0.66),
        Color::srgb(0.3, 0.75, 0.4),
        Color::srgb(0.65, 0.48, 0.28),
        Color::srgb(0.7, 0.2, 0.2),
        Color::srgb(0.9, 0.8, 0.2),
        Color::srgb(0.95, 0.95, 0.95),
    ]
    .map(|c| materials.add(StandardMaterial { base_color: c, perceptual_roughness: 0.9, ..default() }));
    let surfaces = textures.as_ref().map(|t| [t.concrete.clone(), t.wood.clone(), t.metal.clone()]);
    let mut kit = Kit { commands: &mut commands, meshes: &mut meshes, server: &server, tuning: &tuning, targets: targets.as_deref(), mats, surfaces, hm: &heightmap };
    let s = &sites.0;
    base_camp(&mut kit, &s[BASE_CAMP]);
    radio_tower(&mut kit, &s[TOWER]);
    fort(&mut kit, &s[FORT]);
    quarry(&mut kit, &s[QUARRY]);
    ruins(&mut kit, &s[RUINS]);
    lighthouse(&mut kit, &s[LIGHTHOUSE]);
    for pad in extract_pads(s) {
        kit.extract_pad(pad);
    }
    wilderness_loot(&mut kit, &tuning.island);
    spawn_vehicles(&mut commands, vehicles.as_deref(), &tuning, s, &heightmap);
}

/// Caches out in the ring between the core and the coast, worth the walk.
fn wilderness_loot(k: &mut Kit, island: &Island) {
    for i in 0..10 {
        let a = i as f32 * TAU / 10.0 + 0.3;
        let r = island.core + 150.0 + (i % 3) as f32 * 180.0;
        let (x, z) = (a.cos() * r, a.sin() * r);
        if k.hm.height_at(x, z) > island.water_level + 3.0 {
            k.ground_loot(x, z, 60);
        }
    }
}

/// The motor pool: a row south of base camp, a Humvee outside the fort gate, a jeep on the quarry rim and a bike at the lighthouse.
fn spawn_vehicles(commands: &mut Commands, assets: Option<&crate::vehicle::VehicleAssets>, tuning: &Tuning, s: &[Placed], hm: &Heightmap) {
    use crate::vehicle::{spawn, Kind};
    let at = |site: usize, dx: f32, dz: f32| {
        let c = s[site].center + Vec2::new(dx, dz);
        Vec3::new(c.x, hm.height_at(c.x, c.y), c.y)
    };
    spawn(commands, assets, tuning, Kind::Humvee, at(BASE_CAMP, -14.0, 30.0), 0.0);
    spawn(commands, assets, tuning, Kind::Jeep, at(BASE_CAMP, -6.0, 30.0), 0.0);
    spawn(commands, assets, tuning, Kind::DirtBike, at(BASE_CAMP, 1.0, 30.0), 0.0);
    spawn(commands, assets, tuning, Kind::DirtBike, at(BASE_CAMP, 4.0, 30.0), 0.0);
    spawn(commands, assets, tuning, Kind::Humvee, at(FORT, -48.0, 12.0), FRAC_PI_2);
    spawn(commands, assets, tuning, Kind::Jeep, at(QUARRY, 0.0, -66.0), -FRAC_PI_2);
    spawn(commands, assets, tuning, Kind::DirtBike, at(LIGHTHOUSE, 8.0, 4.0), 0.0);
}

/// Spawn: colonnade, racks, the physics playground from the arena, two
/// wall-run walls, box steps and a ring of trees. No enemies.
fn base_camp(k: &mut Kit, p: &Placed) {
    let o = p.origin();
    for i in 0..6 {
        let a = i as f32 * TAU / 6.0;
        k.column(o + Vec3::new(a.cos() * 12.0, 0.0, a.sin() * 12.0), i % 3 == 2);
    }
    k.prop("trophy", o, 2.0, 0.0, Collider::cylinder(0.5, 0.96), 0.48, false);
    // Wardrobe locker: stand next to it and press E.
    k.block(Vec3::new(1.2, 2.2, 0.7), o + Vec3::new(0.0, 1.1, -12.0), 0.0, Mat::Wood);
    k.commands.spawn((crate::wardrobe::Locker, Transform::from_translation(o + Vec3::new(0.0, 1.0, -12.0))));
    k.medkit(o + Vec3::new(3.0, 0.0, -5.0));
    k.medkit(o + Vec3::new(-3.0, 0.0, -5.0));
    k.prop("weapon-rack", o + Vec3::new(-5.0, 0.0, -8.0), 2.0, 0.3, Collider::cuboid(1.6, 0.94, 0.6), 0.47, false);
    k.prop("weapon-rack", o + Vec3::new(5.0, 0.0, -8.0), 2.0, -0.3, Collider::cuboid(1.6, 0.94, 0.6), 0.47, false);
    for i in 0..4 {
        let a = i as f32 * FRAC_PI_2 + 0.4;
        k.prop("banner", o + Vec3::new(a.cos() * 18.0, 0.0, a.sin() * 18.0), 3.0, -a, Collider::cuboid(0.3, 3.0, 1.8), 1.5, false);
    }
    // Playground: crate pyramid, barrels, balls, dominoes.
    for layer in 0..4 {
        let n = 4 - layer;
        for i in 0..n {
            for j in 0..n {
                let pos = o + Vec3::new(14.0 + (i as f32 - n as f32 / 2.0 + 0.5) * 1.02, 0.5 + layer as f32 * 1.0, 12.0 + (j as f32 - n as f32 / 2.0 + 0.5) * 1.02);
                k.dynamic(Cuboid::from_length(1.0).into(), Collider::cuboid(1.0, 1.0, 1.0), 40.0, pos, Mat::Crate);
            }
        }
    }
    for i in 0..5 {
        k.dynamic(Cylinder::new(0.4, 1.2).into(), Collider::cylinder(0.4, 1.2), 25.0, o + Vec3::new(-14.0 + i as f32 * 1.1, 0.6, 12.0), Mat::Barrel);
    }
    for i in 0..4 {
        k.dynamic(Sphere::new(0.5).into(), Collider::sphere(0.5), 10.0, o + Vec3::new(-16.0 + i as f32 * 1.3, 0.5, 16.0), Mat::Ball);
    }
    for i in 0..12 {
        k.dynamic(Cuboid::new(1.2, 2.0, 0.3).into(), Collider::cuboid(1.2, 2.0, 0.3), 20.0, o + Vec3::new(-6.0, 1.0, 14.0 + i as f32 * 1.2), Mat::Wood);
    }
    for i in 0..6 {
        let h = 0.5 + i as f32 * 0.5;
        k.block(Vec3::new(3.0, h, 3.0), o + Vec3::new(-20.0 + i as f32 * 4.0, h / 2.0, -22.0), 0.0, Mat::Stone);
    }
    k.block(Vec3::new(1.0, 6.0, 30.0), o + Vec3::new(30.0, 3.0, 0.0), 0.0, Mat::Stone);
    k.block(Vec3::new(1.0, 6.0, 30.0), o + Vec3::new(-30.0, 3.0, 0.0), 0.0, Mat::Stone);
    for i in 0..10 {
        let a = i as f32 * TAU / 10.0 + 0.2;
        k.tree(o + Vec3::new(a.cos() * 46.0, 0.0, a.sin() * 46.0), i as f32);
    }
}

/// A 40 m lattice: climb the spiral of ledges inside the four posts, with
/// crossbars to wall-jump between, drones circling the top.
fn radio_tower(k: &mut Kit, p: &Placed) {
    let o = p.origin();
    k.medkit(o + Vec3::new(2.5, 0.0, 3.5));
    k.block(Vec3::new(6.0, 3.0, 6.0), o + Vec3::new(0.0, 1.5, 9.0), 0.0, Mat::Metal);
    for (x, z) in [(-3.0, -3.0), (3.0, -3.0), (3.0, 3.0), (-3.0, 3.0)] {
        k.block(Vec3::new(0.6, 40.0, 0.6), o + Vec3::new(x, 20.0, z), 0.0, Mat::Metal);
    }
    for level in 1..=8 {
        let y = level as f32 * 5.0;
        k.block(Vec3::new(6.6, 0.3, 0.3), o + Vec3::new(0.0, y, -3.0), 0.0, Mat::Metal);
        k.block(Vec3::new(6.6, 0.3, 0.3), o + Vec3::new(0.0, y, 3.0), 0.0, Mat::Metal);
        k.block(Vec3::new(0.3, 0.3, 6.6), o + Vec3::new(-3.0, y, 0.0), 0.0, Mat::Metal);
        k.block(Vec3::new(0.3, 0.3, 6.6), o + Vec3::new(3.0, y, 0.0), 0.0, Mat::Metal);
    }
    // Spiral of ledges, 2.4 m apart: a jump plus a mantle each.
    for i in 0..16 {
        let a = i as f32 * FRAC_PI_2 + 0.785;
        let y = 2.4 * (i + 1) as f32;
        k.block(Vec3::new(1.8, 0.3, 1.8), o + Vec3::new(a.cos() * 2.4, y, a.sin() * 2.4), a, Mat::Wood);
    }
    k.block(Vec3::new(9.0, 0.5, 9.0), o + Vec3::new(0.0, 40.25, 0.0), 0.0, Mat::Goal);
    k.loot(o + Vec3::new(2.0, 40.5, 2.0), 80, None);
    k.loot(o + Vec3::new(-2.0, 0.0, 12.0), 20, None);
    for i in 0..3 {
        k.drone(o + Vec3::new(0.0, 26.0 + i as f32 * 9.0, 0.0), 10.0 + i as f32 * 3.0, i as f32 * 2.1);
    }
}

/// Walls to run along and climb, a gate to the west, towers at the corners,
/// the arena's mantle tower and wall-jump chimney inside, four soldiers.
fn fort(k: &mut Kit, p: &Placed) {
    let o = p.origin();
    k.medkit(o + Vec3::new(2.5, 0.0, 3.5));
    k.block(Vec3::new(72.0, 8.0, 1.0), o + Vec3::new(0.0, 4.0, -36.0), 0.0, Mat::Stone);
    k.block(Vec3::new(72.0, 8.0, 1.0), o + Vec3::new(0.0, 4.0, 36.0), 0.0, Mat::Stone);
    k.block(Vec3::new(1.0, 8.0, 72.0), o + Vec3::new(36.0, 4.0, 0.0), 0.0, Mat::Stone);
    k.block(Vec3::new(1.0, 8.0, 30.0), o + Vec3::new(-36.0, 4.0, -21.0), 0.0, Mat::Stone);
    k.block(Vec3::new(1.0, 8.0, 30.0), o + Vec3::new(-36.0, 4.0, 21.0), 0.0, Mat::Stone);
    for (x, z) in [(-36.0, -36.0), (36.0, -36.0), (36.0, 36.0), (-36.0, 36.0)] {
        k.block(Vec3::new(5.0, 14.0, 5.0), o + Vec3::new(x, 7.0, z), 0.0, Mat::Stone);
    }
    for (x, z) in [(-20.0, -25.0), (25.0, 20.0), (0.0, 0.0), (28.0, -28.0)] {
        k.loot(o + Vec3::new(x, 0.0, z), 30, None);
    }
    for i in 0..3 {
        let h = 1.8 * (i + 1) as f32;
        k.block(Vec3::new(4.0, h, 4.0), o + Vec3::new(14.0 + i as f32 * 4.0, h / 2.0, 16.0), 0.0, Mat::Wood);
    }
    k.block(Vec3::new(1.0, 12.0, 8.0), o + Vec3::new(-20.0, 6.0, -16.0), 0.0, Mat::Stone);
    k.block(Vec3::new(1.0, 11.0, 8.0), o + Vec3::new(-16.0, 5.5, -16.0), 0.0, Mat::Stone);
    k.block(Vec3::new(6.0, 1.0, 8.0), o + Vec3::new(-13.0, 11.5, -16.0), 0.0, Mat::Goal);
    for i in 0..6 {
        k.dynamic(Cuboid::from_length(1.0).into(), Collider::cuboid(1.0, 1.0, 1.0), 40.0, o + Vec3::new(-4.0 + (i % 3) as f32 * 1.1, 0.5 + (i / 3) as f32, 20.0), Mat::Crate);
    }
    k.prop("weapon-rack", o + Vec3::new(0.0, 0.0, -30.0), 2.0, 0.0, Collider::cuboid(1.6, 0.94, 0.6), 0.47, false);
    for i in 0..4 {
        let a = i as f32 * FRAC_PI_2 + 0.785;
        k.prop("banner", o + Vec3::new(a.cos() * 30.0, 0.0, a.sin() * 30.0), 3.0, -a, Collider::cuboid(0.3, 3.0, 1.8), 1.5, false);
    }
    // Two in the courtyard, two on the north and south walls.
    let mut loop1 = square(o, 24.0);
    k.soldier(loop1.clone());
    loop1.rotate_left(2);
    k.soldier(loop1);
    k.soldier(vec![o + Vec3::new(-30.0, 8.0, -36.0), o + Vec3::new(30.0, 8.0, -36.0)]);
    k.soldier(vec![o + Vec3::new(30.0, 8.0, 36.0), o + Vec3::new(-30.0, 8.0, 36.0)]);
}

/// Terraces stamped into the ground; blocks to shoot around and soldiers
/// walking each ring.
fn quarry(k: &mut Kit, p: &Placed) {
    let pit = p.origin();
    k.medkit(pit + Vec3::new(3.0, 0.0, 3.0));
    let rim = pit.y + 18.0;
    k.loot(pit, 100, Some(0));
    for (x, z, y) in [(40.0, 0.0, rim - 12.0), (-40.0, 10.0, rim - 12.0), (0.0, -58.0, rim - 6.0)] {
        k.loot(Vec3::new(pit.x + x, y, pit.z + z), 40, None);
    }
    for (i, (x, z)) in [(44.0, 20.0), (-30.0, 38.0), (10.0, -45.0)].iter().enumerate() {
        k.block(Vec3::new(3.0, 3.0, 3.0), Vec3::new(pit.x + x, rim - 6.0 + 1.5, pit.z + z), i as f32, Mat::Stone);
    }
    for i in 0..6 {
        let pos = Vec3::new(pit.x - 25.0 + (i % 3) as f32 * 1.4, rim - 12.0 + 0.31 + (i / 3) as f32 * 0.65, pit.z + 10.0);
        k.prop("bricks", pos, 1.5, 0.0, Collider::cuboid(1.17, 0.62, 1.26), 0.31, true);
    }
    for i in 0..4 {
        k.prop("block", Vec3::new(pit.x - 4.0 + i as f32 * 1.6, pit.y, pit.z + 4.0), 1.5, 0.0, Collider::cuboid(1.5, 0.75, 1.5), 0.375, true);
    }
    k.prop("weapon-rack", pit + Vec3::new(0.0, 0.0, -8.0), 2.0, 0.0, Collider::cuboid(1.6, 0.94, 0.6), 0.47, false);
    k.soldier(square(Vec3::new(pit.x, rim - 6.0, pit.z), 31.0));
    k.soldier(square(Vec3::new(pit.x, rim - 12.0, pit.z), 20.0));
    let mut inner = square(Vec3::new(pit.x, pit.y, pit.z), 8.0);
    inner.rotate_left(2);
    k.soldier(inner);
}

/// Broken colonnade, statues, and the wall-run gap between two platforms.
fn ruins(k: &mut Kit, p: &Placed) {
    let o = p.origin();
    k.medkit(o + Vec3::new(2.5, 0.0, 3.5));
    for (x, z) in [(-11.0, 0.0), (11.0, 0.0), (0.0, -24.0)] {
        k.loot(o + Vec3::new(x, if z == 0.0 { 3.0 } else { 0.0 }, z), 30, None);
    }
    for i in 0..4 {
        for j in 0..3 {
            k.column(o + Vec3::new(-12.0 + i as f32 * 8.0, 0.0, 18.0 + j as f32 * 8.0), (i + j) % 2 == 1);
        }
    }
    for (x, yaw) in [(-18.0, 0.6), (0.0, 0.0), (18.0, -0.6)] {
        k.prop("block", o + Vec3::new(x, 0.0, -20.0), 1.5, 0.0, Collider::cuboid(1.5, 0.75, 1.5), 0.375, false);
        k.prop("statue", o + Vec3::new(x, 0.75, -20.0), 1.5, yaw, Collider::cylinder(0.5, 2.0), 1.0, false);
    }
    // Wall-run gap: platform, a wall along one side, platform.
    k.block(Vec3::new(8.0, 3.0, 8.0), o + Vec3::new(-11.0, 1.5, 0.0), 0.0, Mat::Stone);
    k.block(Vec3::new(26.0, 8.0, 1.0), o + Vec3::new(0.0, 4.0, 5.0), 0.0, Mat::Stone);
    k.block(Vec3::new(8.0, 3.0, 8.0), o + Vec3::new(11.0, 1.5, 0.0), 0.0, Mat::Goal);
    k.block(Vec3::new(4.0, 1.5, 4.0), o + Vec3::new(-19.0, 0.75, 0.0), 0.0, Mat::Stone);
    for i in 0..6 {
        let a = i as f32 * TAU / 6.0;
        k.tree(o + Vec3::new(a.cos() * 50.0, 0.0, a.sin() * 50.0), i as f32 * 1.7);
    }
    k.soldier(square(o, 30.0));
    let mut other = square(o, 14.0);
    other.rotate_left(1);
    k.soldier(other);
}

/// A tower on the coast with a spiral of ledges to mantle up, drones around it.
fn lighthouse(k: &mut Kit, p: &Placed) {
    let o = p.origin();
    k.medkit(o + Vec3::new(2.5, 0.0, 3.5));
    k.cylinder(3.0, 24.0, o, Mat::Stone);
    k.cylinder(4.5, 0.5, o + Vec3::Y * 24.0, Mat::Goal);
    k.loot(o + Vec3::new(2.0, 24.5, 1.0), 80, None);
    k.loot(o + Vec3::new(9.0, 3.0, -2.0), 20, None);
    for i in 0..16 {
        let a = i as f32 * 0.5;
        let y = 1.5 * (i + 1) as f32;
        k.block(Vec3::new(2.2, 0.35, 2.0), o + Vec3::new(a.cos() * 4.3, y, a.sin() * 4.3), -a, Mat::Wood);
    }
    k.block(Vec3::new(6.0, 3.0, 6.0), o + Vec3::new(9.0, 1.5, 0.0), 0.0, Mat::Wood);
    k.prop("weapon-rack", o + Vec3::new(9.0, 3.0, 0.0), 2.0, PI, Collider::cuboid(1.6, 0.94, 0.6), 0.47, false);
    k.drone(o + Vec3::Y * 14.0, 9.0, 0.0);
    k.drone(o + Vec3::Y * 28.0, 7.0, 2.0);
}
