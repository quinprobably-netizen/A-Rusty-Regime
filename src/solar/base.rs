//! The faction bases: one building per faction on its world, from `assets/bases.toml` and
//! `models/bases/<id>.glb` (built by `tools/bases`). Each stands on a buried foundation slab
//! whose top is its ground, with a landing pad of its own beside it unless it shares Haven's
//! apron, and is hollow: the spec's boxes are its floors, walls, roofs and stairs, and the
//! player walks between them. The anchor world's bases are spawned with its other fixtures and
//! go with them at a handoff.

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};
use serde::Deserialize;
use std::sync::Arc;

use super::ship::ShipBox;
use super::{flat_site, lat_lon_dir, Fixture, Solar};
use crate::surface::{Origin, Sphere, Surface};

/// How far the foundation and pad slabs reach down: whatever the slope, they meet the ground.
const SLAB_DEPTH: f32 = 14.0;
/// The deck stands this far over the highest ground under it.
const CLEARANCE: f32 = 0.6;
/// A base's own landing pad, square.
pub const PAD_SIZE: f32 = 26.0;

/// One base's numbers from `assets/bases.toml`, in the base frame: +X right, +Y up, the front
/// door on +Z, the origin at ground level under the building's centre.
#[derive(Deserialize, Clone, Debug)]
pub struct BaseSpec {
    pub id: String,
    pub name: String,
    #[cfg_attr(not(test), allow(dead_code))]
    pub faction: String,
    pub body: String,
    /// Where it stands in Haven's pad frame (x, z), for a base beside the apron.
    pub near_pad: Option<[f32; 2]>,
    /// Otherwise: snapped to the flattest ground near this latitude and longitude, degrees.
    #[serde(default)]
    pub lat: f32,
    #[serde(default)]
    pub lon: f32,
    /// How the base is turned on its site, degrees about up: 0 puts the door on the south side.
    #[serde(default)]
    pub yaw: f32,
    /// The foundation slab (x, z).
    pub footprint: [f32; 2],
    /// The landing pad's centre (x, z) in the base frame, if the base has its own.
    pub pad: Option<[f32; 2]>,
    /// A point in the front doorway, for the tests.
    #[cfg_attr(not(test), allow(dead_code))]
    pub door: [f32; 3],
    pub collider: Vec<ShipBox>,
}

impl BaseSpec {
    pub fn collider(&self) -> Collider {
        Collider::compound(self.collider.iter().map(|b| (Vec3::from(b.center), b.rotation(), Collider::cuboid(b.size[0], b.size[1], b.size[2]))).collect())
    }

    /// The top of the highest level box under `p` (base frame), or the foundation's, if one is
    /// within `reach` below.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn floor_under(&self, p: Vec3, reach: f32) -> Option<f32> {
        let foundation = (p.x.abs() <= self.footprint[0] / 2.0 && p.z.abs() <= self.footprint[1] / 2.0).then_some(0.0);
        self.collider
            .iter()
            .filter(|b| b.rot == [0.0; 3])
            .filter(|b| (p.x - b.center[0]).abs() <= b.size[0] / 2.0 && (p.z - b.center[2]).abs() <= b.size[2] / 2.0)
            .map(|b| b.center[1] + b.size[1] / 2.0)
            .chain(foundation)
            .filter(|top| *top <= p.y && p.y - top <= reach)
            .max_by(|a, b| a.total_cmp(b))
    }
}

/// Every base in the game.
#[derive(Resource, Deserialize, Clone, Debug)]
pub struct Bases {
    pub base: Vec<BaseSpec>,
}

impl Bases {
    pub fn parse(text: &str) -> Result<Self, toml::de::Error> {
        toml::from_str(text)
    }

    /// The bases compiled in from `assets/bases.toml`.
    pub fn load() -> Self {
        Self::parse(include_str!("../../assets/bases.toml")).expect("assets/bases.toml")
    }
}

/// A base standing on the anchor world: `spec` indexes `Bases`.
#[derive(Component)]
pub struct Base {
    pub spec: usize,
}

/// Holds a base's meshes under its body.
#[derive(Component)]
struct BaseModel {
    spec: usize,
}

/// A model whose glb has not been loaded yet; bases load one at a time, after the ships.
#[derive(Component)]
struct Pending;

pub fn build(app: &mut App) {
    app.insert_resource(Bases::load()).add_systems(Update, stream).add_observer(dress);
}

/// Where a base stands: its ground point (body coordinates, on the terrain), its frame, and
/// its deck height over that point.
pub fn site(spec: &BaseSpec, sphere: &Arc<Sphere>, pad: Vec3) -> (Vec3, Quat, f32) {
    let surface = Surface::Sphere(sphere.clone());
    let (ground, frame) = match spec.near_pad {
        Some([x, z]) => {
            let frame = surface.frame(pad);
            (sphere.surface_point((pad + frame * Vec3::new(x, 0.0, z)).normalize()), frame)
        }
        None => {
            let p = flat_site(sphere, lat_lon_dir(spec.lat, spec.lon));
            (p, surface.frame(p))
        }
    };
    let frame = frame * Quat::from_rotation_y(spec.yaw.to_radians());
    let deck = deck_over(sphere, ground, frame, Vec3::ZERO, spec.footprint[0] / 2.0, spec.footprint[1] / 2.0);
    (ground, frame, deck)
}

/// A deck over the ground around `ground + frame * at`, half `hx` by `hz`: `CLEARANCE` over the
/// highest of nine samples, measured from `ground`'s height.
fn deck_over(sphere: &Sphere, ground: Vec3, frame: Quat, at: Vec3, hx: f32, hz: f32) -> f32 {
    let here = sphere.height(ground.normalize());
    let mut rise = 0.0_f32;
    for dx in [-hx, 0.0, hx] {
        for dz in [-hz, 0.0, hz] {
            let p = ground + frame * (at + Vec3::new(dx, 0.0, dz));
            rise = rise.max(sphere.height(p.normalize()) - here);
        }
    }
    rise + CLEARANCE
}

/// The anchor world's bases: a foundation slab, a landing pad, the building's collider, and
/// its model streamed in behind the ships.
pub fn spawn_bases(world: &mut World) {
    let solar = world.resource::<Solar>();
    let (anchor, pad) = (solar.anchor.clone(), solar.pad);
    let Some(sphere) = solar.spheres.get(&anchor).cloned() else { return };
    let origin = *world.resource::<Origin>();
    let specs = world.resource::<Bases>().clone();
    let material = world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| m.add(StandardMaterial { base_color: Color::srgb(0.32, 0.33, 0.35), perceptual_roughness: 0.8, ..default() }));
    for (i, spec) in specs.base.iter().enumerate().filter(|(_, s)| s.body == anchor) {
        let (ground, frame, deck) = site(spec, &sphere, pad);
        let mut slabs = vec![("Foundation", Vec3::ZERO, Vec3::new(spec.footprint[0], SLAB_DEPTH, spec.footprint[1]), deck)];
        if let Some([x, z]) = spec.pad {
            let at = Vec3::new(x, 0.0, z);
            let pad_deck = deck.max(deck_over(&sphere, ground, frame, at, PAD_SIZE / 2.0, PAD_SIZE / 2.0));
            slabs.push(("Pad", at, Vec3::splat(PAD_SIZE).with_y(SLAB_DEPTH), pad_deck));
        }
        for (name, at, size, top) in slabs {
            let transform = Transform::from_translation(origin.world(ground + frame * (at + Vec3::Y * (top - size.y / 2.0)))).with_rotation(frame);
            let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
            let mut e = world.spawn((Name::new(name), Fixture, RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
            if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
                e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
            }
        }
        let transform = Transform::from_translation(origin.world(ground + frame * Vec3::Y * deck)).with_rotation(frame);
        let base = world.spawn((Name::new(spec.name.clone()), Base { spec: i }, Fixture, RigidBody::Static, spec.collider(), transform, Visibility::default())).id();
        let model = world.spawn((BaseModel { spec: i }, Transform::default(), Visibility::default())).id();
        world.entity_mut(base).add_child(model);
        if world.contains_resource::<AssetServer>() {
            world.entity_mut(model).insert(Pending);
        }
    }
}

/// Loads the next pending base's glb once every ship hull and the previous base are in, so the
/// boot never decodes two models at once. A model that fails to load leaves an invisible base
/// that still has its walls.
#[allow(clippy::type_complexity)]
fn stream(
    mut commands: Commands,
    server: Res<AssetServer>,
    bases: Res<Bases>,
    ships: Query<(), With<super::ship::Pending>>,
    waiting: Query<(Entity, &BaseModel), (With<Pending>, Without<WorldAssetRoot>)>,
    loading: Query<(Entity, &WorldAssetRoot), With<Pending>>,
) {
    for (e, root) in &loading {
        if let Some(bevy::asset::LoadState::Failed(err)) = server.get_load_state(root.0.id()) {
            warn!("base model failed to load: {err}");
            commands.entity(e).remove::<Pending>();
            return;
        }
    }
    if !loading.is_empty() || !ships.is_empty() {
        return;
    }
    if let Some((e, model)) = waiting.iter().next() {
        let path = format!("models/bases/{}.glb", bases.base[model.spec].id);
        commands.entity(e).insert(WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(path))));
    }
}

/// Once a base's glb is in: a warm lamp on every `lamp.<n>` node, a cold floodlight on every
/// `flood.<n>`. No shadows: the building is one mesh and the lights are many.
fn dress(ready: On<WorldInstanceReady>, mut commands: Commands, models: Query<&BaseModel>, children: Query<&Children>, names: Query<&Name>) {
    if models.get(ready.entity).is_err() {
        return;
    }
    commands.entity(ready.entity).remove::<Pending>();
    for e in children.iter_descendants(ready.entity) {
        let Ok(name) = names.get(e) else { continue };
        if name.starts_with("lamp.") {
            commands.entity(e).insert(PointLight { color: Color::srgb(1.0, 0.92, 0.8), intensity: 8.0e5, range: 11.0, radius: 0.15, shadow_maps_enabled: false, ..default() });
        } else if name.starts_with("flood.") {
            commands.entity(e).insert(PointLight { color: Color::srgb(0.9, 0.95, 1.0), intensity: 6.0e6, range: 40.0, radius: 0.2, shadow_maps_enabled: false, ..default() });
        }
    }
}
