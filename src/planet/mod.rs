pub mod bubble;
pub mod chunk;
pub mod gravity;
pub mod quadtree;

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::tasks::{block_on, poll_once, AsyncComputeTaskPool, Task};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use crate::controller::{ControllerSet, Player};
use crate::surface::{Ground, Origin, Sphere, Surface};
use crate::tuning::Tuning;
use chunk::{build_chunk, ChunkMesh};
use gravity::gravitate;
use quadtree::{finest_depth, node_distance, select_leaves, NodeId};

/// Height of the course deck's top over the surface point it is built at.
pub const COURSE_DECK: f32 = 3.0;

/// A small parkour course (a step, a wall to run, a ledge to mantle and a roof to slide under)
/// on a flat deck floating over the ground at `at`, a body-coordinate surface point, built in
/// the surface frame there. Grey boxes when the renderer is present, colliders always.
// Only the tests build it until the planet level does.
#[allow(dead_code)]
pub fn spawn_course(world: &mut World, surface: &Surface, origin: &Origin, at: Vec3) {
    let frame = surface.frame(at);
    let deck = Vec3::Y * COURSE_DECK;
    // (size, centre) in the frame; everything but the deck stands on the deck top.
    let boxes = [
        (Vec3::new(40.0, 0.5, 50.0), Vec3::new(4.0, 2.75, -22.0)),
        (Vec3::new(3.0, 0.3, 12.0), deck + Vec3::new(8.0, 0.15, -10.5)),
        (Vec3::new(1.0, 8.0, 40.0), deck + Vec3::new(1.0, 4.0, -40.0)),
        (Vec3::new(4.0, 1.8, 4.0), deck + Vec3::new(-8.0, 0.9, -3.0)),
        (Vec3::new(6.0, 0.5, 10.0), deck + Vec3::new(16.0, 1.75, -10.0)),
    ];
    let material = world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| m.add(Color::srgb(0.5, 0.5, 0.52)));
    for (size, centre) in boxes {
        let transform = Transform::from_translation(origin.world(at + frame * centre)).with_rotation(frame);
        let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
        let mut e = world.spawn((Name::new("Course"), RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
        if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
            e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
        }
    }
}

/// Finished chunks spawned per frame at most, so a burst of builds does not stall a frame.
const APPLIED_PER_FRAME: usize = 2;

/// The streamed body: its shape, shared with the workers, and the depth of its finest chunks.
#[derive(Resource)]
pub struct Planet {
    pub sphere: Arc<Sphere>,
    pub max_depth: u8,
}

/// The streaming state. `wanted` is the tiling the player should see; `built` what is spawned,
/// which can briefly hold both a node and some of its descendants while one replaces the other;
/// `pending` the builds in flight; `loaded` the built nodes' data; `solid` the built nodes whose
/// chunk has a collider, which are those inside the physics bubble.
#[derive(Resource, Default)]
pub struct Chunks {
    pub wanted: HashSet<NodeId>,
    pub built: HashMap<NodeId, Entity>,
    pub pending: HashMap<NodeId, Task<ChunkMesh>>,
    pub loaded: HashMap<NodeId, Arc<ChunkMesh>>,
    pub solid: HashSet<NodeId>,
}

impl Chunks {
    /// The ground under `p_body` on the finest loaded chunk holding its direction, or from the
    /// height function where nothing is loaded.
    #[allow(dead_code)] // the level reads it next; the tests already do
    pub fn ground(&self, sphere: &Sphere, p_body: Vec3) -> Ground {
        let dir = p_body.try_normalize().unwrap_or(Vec3::Y);
        self.loaded
            .values()
            .filter(|c| c.node.contains(dir))
            .max_by_key(|c| c.node.depth)
            .and_then(|c| c.ground_on(dir))
            .unwrap_or_else(|| sphere.ground(p_body))
    }

    /// Whether the finest built chunk holding the direction of `p_body` has a collider, that is,
    /// whether there is built ground inside the physics bubble under it.
    pub fn is_solid(&self, p_body: Vec3) -> bool {
        let dir = p_body.try_normalize().unwrap_or(Vec3::Y);
        self.built.keys().filter(|n| n.contains(dir)).max_by_key(|n| n.depth).is_some_and(|n| self.solid.contains(n))
    }
}

/// A spawned terrain chunk.
#[derive(Component)]
pub struct Chunk {
    pub node: NodeId,
}

/// Where the player will be in a second, in body coordinates: the quadtree refines around it.
pub fn focus(player_world: Vec3, velocity: Vec3, origin: &Origin) -> Vec3 {
    origin.body(player_world + velocity)
}

/// A round body to stand on, streamed around the player.
// The moon level builds it; until then only the tests stream.
#[allow(dead_code)]
pub struct PlanetPlugin {
    pub body: String,
}

impl Plugin for PlanetPlugin {
    fn build(&self, app: &mut App) {
        add_streaming(app);
    }
}

/// Streams terrain chunks over the `Surface::Sphere` already in the app; on a flat surface it
/// does nothing.
#[allow(dead_code)] // called by `PlanetPlugin` and the tests
pub fn add_streaming(app: &mut App) {
    let Some(Surface::Sphere(sphere)) = app.world().get_resource::<Surface>().cloned() else { return };
    let max_depth = finest_depth(sphere.sea_radius(), app.world().resource::<Tuning>().terrain.cell);
    app.insert_resource(Planet { sphere, max_depth })
        .init_resource::<Chunks>()
        .add_systems(Update, (plan, apply, bubble::solidify).chain())
        .add_systems(FixedUpdate, (bubble::freeze.before(gravitate), bubble::hold_player).before(ControllerSet));
}

/// Nearest the focus first; ties in a fixed order, so the same state always plans the same way.
fn by_nearness(nodes: &mut [NodeId], radius: f32, focus: Vec3) {
    nodes.sort_by(|a, b| {
        node_distance(*a, radius, focus).total_cmp(&node_distance(*b, radius, focus)).then_with(|| (a.face, a.depth, a.x, a.y).cmp(&(b.face, b.depth, b.x, b.y)))
    });
}

/// Picks the leaves around the player, retires chunks whose replacements are built, and starts
/// builds for missing leaves up to the worker cap.
fn plan(mut commands: Commands, planet: Res<Planet>, mut chunks: ResMut<Chunks>, tuning: Res<Tuning>, origin: Res<Origin>, players: Query<(&Transform, &Player)>) {
    let Ok((tf, player)) = players.single() else { return };
    let terrain = &tuning.terrain;
    let radius = planet.sphere.sea_radius();
    let focus = focus(tf.translation, player.velocity, &origin);
    let chunks = &mut *chunks;
    chunks.wanted = select_leaves(radius, planet.max_depth, focus, terrain.split, terrain.merge(), &chunks.wanted);
    // Dropping a task cancels its build.
    chunks.pending.retain(|node, _| chunks.wanted.contains(node));

    // A built node that is no longer wanted goes once what replaces it is built: all its wanted
    // descendants, or its wanted ancestor. With neither it covers nothing wanted and goes now.
    // Wanted nodes are never retired, so a direction covered stays covered.
    let mut stale: HashMap<NodeId, (bool, bool)> = chunks.built.keys().filter(|n| !chunks.wanted.contains(n)).map(|n| (*n, (false, true))).collect();
    for leaf in &chunks.wanted {
        let mut up = leaf.parent();
        while let Some(node) = up {
            if let Some((has_descendant, all_built)) = stale.get_mut(&node) {
                *has_descendant = true;
                *all_built &= chunks.built.contains_key(leaf);
            }
            up = node.parent();
        }
    }
    for (node, (has_descendant, all_built)) in stale {
        let ancestor = std::iter::successors(node.parent(), |n| n.parent()).find(|n| chunks.wanted.contains(n));
        let retire = (has_descendant && all_built) || ancestor.is_some_and(|a| chunks.built.contains_key(&a)) || (!has_descendant && ancestor.is_none());
        if retire {
            if let Some(entity) = chunks.built.remove(&node) {
                commands.entity(entity).despawn();
            }
            chunks.loaded.remove(&node);
            chunks.solid.remove(&node);
        }
    }

    let cap = terrain.workers.max(1);
    if chunks.pending.len() >= cap {
        return;
    }
    let mut missing: Vec<NodeId> = chunks.wanted.iter().filter(|n| !chunks.built.contains_key(n) && !chunks.pending.contains_key(n)).copied().collect();
    by_nearness(&mut missing, radius, focus);
    for node in missing.into_iter().take(cap - chunks.pending.len()) {
        let sphere = planet.sphere.clone();
        chunks.pending.insert(node, AsyncComputeTaskPool::get().spawn(async move { build_chunk(&sphere, node) }));
    }
}

/// Spawns up to `APPLIED_PER_FRAME` finished builds: grey meshes when there is a renderer, with
/// colliders inside the physics bubble.
#[allow(clippy::too_many_arguments)]
fn apply(
    mut commands: Commands,
    mut chunks: ResMut<Chunks>,
    planet: Res<Planet>,
    tuning: Res<Tuning>,
    origin: Res<Origin>,
    players: Query<&Transform, With<Player>>,
    mut meshes: Option<ResMut<Assets<Mesh>>>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut grey: Local<Option<Handle<StandardMaterial>>>,
) {
    let player_body = players.single().ok().map(|tf| origin.body(tf.translation));
    if grey.is_none() {
        *grey = materials.map(|mut m| m.add(StandardMaterial { base_color: Color::srgb(0.5, 0.5, 0.52), perceptual_roughness: 1.0, ..default() }));
    }
    let mut ready: Vec<NodeId> = chunks.pending.keys().copied().collect();
    ready.sort_by_key(|n| (n.face, n.depth, n.x, n.y));
    let mut applied = 0;
    for node in ready {
        if applied == APPLIED_PER_FRAME {
            break;
        }
        // A finished task must not be polled again, so it leaves `pending` as soon as it yields.
        let Some(task) = chunks.pending.get_mut(&node) else { continue };
        let Some(built) = block_on(poll_once(task)) else { continue };
        chunks.pending.remove(&node);
        let built = Arc::new(built);
        let mut e = commands.spawn((Name::new("Chunk"), Chunk { node }, Transform::from_translation(origin.world(built.center)), RigidBody::Static));
        if let (Some(meshes), Some(grey)) = (meshes.as_mut(), grey.as_ref()) {
            e.insert((Mesh3d(meshes.add(built.mesh())), MeshMaterial3d(grey.clone())));
        }
        if player_body.is_some_and(|p| node_distance(node, planet.sphere.sea_radius(), p) <= tuning.terrain.bubble) {
            e.insert(built.collider());
            chunks.solid.insert(node);
        }
        chunks.built.insert(node, e.id());
        chunks.loaded.insert(node, built);
        applied += 1;
    }
}
