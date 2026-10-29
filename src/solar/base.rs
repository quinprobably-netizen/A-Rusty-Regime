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

use super::life::{self, CrewSpec};
use super::ship::ShipBox;
use super::station::{Station, StationSpec};
use super::{flat_site, lat_lon_dir, Fixture, Solar};
use crate::surface::{Origin, Sphere, Surface};

/// How far the foundation and pad slabs reach down: whatever the slope, they meet the ground.
pub(super) const SLAB_DEPTH: f32 = 14.0;
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
    /// Whose base it is; a faction that flies a fighter patrols it (`enemy`).
    pub faction: String,
    pub body: String,
    /// The faction's colour (rgb): its waypoint and the beam over the base.
    #[serde(default = "white")]
    pub color: [f32; 3],
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
    /// Where the foundation's centre is (x, z), when the building is not in the middle of it.
    #[serde(default)]
    pub footprint_at: [f32; 2],
    /// The landing pad's centre (x, z) in the base frame, if the base has its own.
    pub pad: Option<[f32; 2]>,
    /// A point in the front doorway, for the tests.
    #[cfg_attr(not(test), allow(dead_code))]
    pub door: [f32; 3],
    pub collider: Vec<ShipBox>,
    /// What the building is for: where E does what (see `station`).
    #[serde(default)]
    pub stations: Vec<StationSpec>,
    /// Who works here and walks its rounds (`life`).
    #[serde(default)]
    pub crew: Vec<CrewSpec>,
    /// The ship that visits its pad now and then, by `ships.toml` id.
    pub traffic: Option<String>,
}

fn white() -> [f32; 3] {
    [1.0; 3]
}

/// The light beam over each base: this wide, this tall, so it reads from kilometres off.
const BEAM_RADIUS: f32 = 3.0;
const BEAM_HEIGHT: f32 = 900.0;

impl BaseSpec {
    pub fn collider(&self) -> Collider {
        Collider::compound(self.collider.iter().map(|b| (Vec3::from(b.center), b.rotation(), Collider::cuboid(b.size[0], b.size[1], b.size[2]))).collect())
    }

    /// The top of the highest level box under `p` (base frame), or the foundation's, if one is
    /// within `reach` below.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn floor_under(&self, p: Vec3, reach: f32) -> Option<f32> {
        let foundation = ((p.x - self.footprint_at[0]).abs() <= self.footprint[0] / 2.0 && (p.z - self.footprint_at[1]).abs() <= self.footprint[1] / 2.0).then_some(0.0);
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

/// Where a base's job board stands from its doorway, in the base frame (the door faces +Z).
pub const BOARD_IN: Vec3 = Vec3::new(0.0, 0.0, -1.5);

/// A base standing on the anchor world: `spec` indexes `Bases`.
#[derive(Component)]
pub struct Base {
    pub spec: usize,
}

/// Holds a base's meshes under its body.
#[derive(Component)]
pub(super) struct BaseModel;

/// A model whose glb (this asset path) has not been loaded yet; bases and their visitors load
/// one at a time, after the ships.
#[derive(Component)]
pub struct Pending(pub String);

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
    let deck = deck_over(sphere, ground, frame, Vec3::new(spec.footprint_at[0], 0.0, spec.footprint_at[1]), spec.footprint[0] / 2.0, spec.footprint[1] / 2.0);
    (ground, frame, deck)
}

/// A deck over the ground around `ground + frame * at`, half `hx` by `hz`: `CLEARANCE` over the
/// highest of nine samples, measured from `ground`'s height.
pub(super) fn deck_over(sphere: &Sphere, ground: Vec3, frame: Quat, at: Vec3, hx: f32, hz: f32) -> f32 {
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

/// A base whose deck stands well over the ground in front of it (on a slope) gets a ramp down
/// from its front edge, in line with the door, no steeper than `RAMP_SLOPE`: its centre and turn
/// in the base frame and its size, or `None` when the ground is near enough the deck already.
pub fn approach(spec: &BaseSpec, sphere: &Sphere, ground: Vec3, frame: Quat, deck: f32) -> Option<(Vec3, Quat, Vec3)> {
    let here = sphere.height(ground.normalize());
    let front = spec.footprint_at[1] + spec.footprint[1] / 2.0;
    let rise = |d: f32| sphere.height((ground + frame * Vec3::new(spec.door[0], 0.0, front + d)).normalize()) - here;
    if deck - rise(1.0) < RAMP_MIN {
        return None;
    }
    // Run out until the ground meets the slope coming down from the deck.
    let run = (1..=RAMP_MAX as i32).map(|d| d as f32).find(|d| rise(*d) >= deck - d * RAMP_SLOPE)?;
    let (top, bottom) = (Vec3::new(spec.door[0], deck, front - 1.0), Vec3::new(spec.door[0], rise(run), front + run));
    let along = bottom - top;
    let tilt = Quat::from_rotation_x((-along.y).atan2(along.z));
    let size = Vec3::new(RAMP_WIDTH, RAMP_THICK, along.length() + 2.0);
    Some(((top + bottom) / 2.0 + tilt * Vec3::new(0.0, -RAMP_THICK / 2.0, 0.0), tilt, size))
}

/// The approach ramp: how far the deck must stand over the ground to get one, how steep it may
/// be (rise over run), how far it may reach, its width and thickness, metres.
const RAMP_MIN: f32 = 1.0;
const RAMP_SLOPE: f32 = 0.5;
const RAMP_MAX: f32 = 60.0;
const RAMP_WIDTH: f32 = 7.0;
const RAMP_THICK: f32 = 1.5;

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
        let mut slabs = vec![("Foundation", Vec3::new(spec.footprint_at[0], 0.0, spec.footprint_at[1]), Vec3::new(spec.footprint[0], SLAB_DEPTH, spec.footprint[1]), deck)];
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
        if let Some((center, rotation, size)) = approach(spec, &sphere, ground, frame, deck) {
            let transform = Transform::from_translation(origin.world(ground + frame * center)).with_rotation(frame * rotation);
            let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
            let mut e = world.spawn((Name::new("Approach"), Fixture, RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
            if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
                e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
            }
        }
        let transform = Transform::from_translation(origin.world(ground + frame * Vec3::Y * deck)).with_rotation(frame);
        let base = world.spawn((Name::new(spec.name.clone()), Base { spec: i }, Fixture, RigidBody::Static, spec.collider(), transform, Visibility::default())).id();
        for st in &spec.stations {
            let e = world.spawn((Name::new(format!("Station {}", st.label)), Station { base: i, faction: super::station::faction_of(&specs, i), kind: st.kind, label: st.label.clone() }, Transform::from_translation(Vec3::from(st.at)), Visibility::default())).id();
            world.entity_mut(base).add_child(e);
        }
        // Every base's job board, just inside its door.
        let board = world.spawn((Name::new("Station Job board"), Station { base: i, faction: super::station::faction_of(&specs, i), kind: super::station::StationKind::Board, label: "Job board".into() }, Transform::from_translation(Vec3::from(spec.door) + BOARD_IN), Visibility::default())).id();
        world.entity_mut(base).add_child(board);
                let model = world.spawn((BaseModel, Transform::default(), Visibility::default())).id();
        world.entity_mut(base).add_child(model);
        let pad_top = spec.pad.map(|[x, z]| Vec3::new(x, deck.max(deck_over(&sphere, ground, frame, Vec3::new(x, 0.0, z), PAD_SIZE / 2.0, PAD_SIZE / 2.0)) - deck, z));
        life::spawn(world, base, &spec.crew, spec.traffic.as_deref(), pad_top, 37.0 * i as f32);
        // The beam: additive and unlit, a column of the faction's colour straight up.
        let (mesh, material) = (
            world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cylinder::new(BEAM_RADIUS, BEAM_HEIGHT))),
            world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| {
                let c = Vec3::from(spec.color) * 2.5;
                m.add(StandardMaterial { base_color: Color::LinearRgba(LinearRgba::new(c.x, c.y, c.z, 0.5)), alpha_mode: AlphaMode::Add, unlit: true, ..default() })
            }),
        );
        if let (Some(mesh), Some(material)) = (mesh, material) {
            let beam = world.spawn((Name::new("Beam"), Mesh3d(mesh), MeshMaterial3d(material), Transform::from_xyz(0.0, BEAM_HEIGHT / 2.0, 0.0), bevy::light::NotShadowCaster)).id();
            world.entity_mut(base).add_child(beam);
        }
        if world.contains_resource::<AssetServer>() {
            world.entity_mut(model).insert(Pending(format!("models/bases/{}.glb", spec.id)));
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
    ships: Query<(), With<super::ship::Pending>>,
    waiting: Query<(Entity, &Pending), Without<WorldAssetRoot>>,
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
    // The buildings first, then the ships that visit them.
    if let Some((e, pending)) = waiting.iter().min_by_key(|(_, p)| !p.0.starts_with("models/bases/")) {
        commands.entity(e).insert(WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(pending.0.clone()))));
    }
}

/// Once a base's glb is in: a warm lamp on every `lamp.<n>` node, a cold floodlight on every
/// `flood.<n>`, and the life layer's nodes (`life::dress`). No shadows: the building is one mesh
/// and the lights are many. A visiting ship's glb needs nothing more.
fn dress(ready: On<WorldInstanceReady>, mut commands: Commands, models: Query<&BaseModel>, pending: Query<(), With<Pending>>, children: Query<&Children>, names: Query<&Name>) {
    if pending.contains(ready.entity) {
        commands.entity(ready.entity).remove::<Pending>();
    }
    if models.get(ready.entity).is_err() {
        return;
    }
    for e in children.iter_descendants(ready.entity) {
        let Ok(name) = names.get(e) else { continue };
        if name.starts_with("lamp.") {
            commands.entity(e).insert(PointLight { color: Color::srgb(1.0, 0.92, 0.8), intensity: 8.0e5, range: 11.0, radius: 0.15, shadow_maps_enabled: false, ..default() });
        } else if name.starts_with("flood.") {
            commands.entity(e).insert(PointLight { color: Color::srgb(0.9, 0.95, 1.0), intensity: 6.0e6, range: 40.0, radius: 0.2, shadow_maps_enabled: false, ..default() });
        } else {
            life::dress(&mut commands, e, name);
        }
    }
}
