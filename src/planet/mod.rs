pub mod bubble;
pub mod chunk;
pub mod gravity;
pub mod origin;
pub mod quadtree;

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::tasks::{block_on, poll_once, AsyncComputeTaskPool, Task};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::{Duration, Instant};

use crate::controller::{ControllerSet, Player, WorldBounds};
use crate::surface::{Ground, Origin, Sphere, Surface};
use crate::tuning::Tuning;
use chunk::{build_chunk, leaves_near, ChunkMesh};
use gravity::gravitate;
use quadtree::{finest_depth, node_distance, select_leaves, NodeId};

/// Height of the course deck's top over the surface point it is built at.
pub const COURSE_DECK: f32 = 3.0;

/// A small parkour course (a step, a wall to run, a ledge to mantle and a roof to slide under)
/// on a flat deck floating over the ground at `at`, a body-coordinate surface point, built in
/// the surface frame there. Grey boxes when the renderer is present, colliders always.
pub fn spawn_course(world: &mut World, surface: &Surface, origin: &Origin, at: Vec3) -> Vec<Entity> {
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
    let mut spawned = Vec::new();
    for (size, centre) in boxes {
        let transform = Transform::from_translation(origin.world(at + frame * centre)).with_rotation(frame);
        let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
        let mut e = world.spawn((Name::new("Course"), RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
        if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
            e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
        }
        spawned.push(e.id());
    }
    spawned
}

/// Finished chunks spawned per frame at most, so a burst of builds does not stall a frame.
const APPLIED_PER_FRAME: usize = 2;

/// The streamed body: its shape, shared with the workers, and the depth of its finest chunks.
/// `streamed` is false while the anchor is the star, which has no ground to stream.
#[derive(Resource)]
pub struct Planet {
    pub sphere: Arc<Sphere>,
    pub max_depth: u8,
    pub streamed: bool,
}

impl Planet {
    pub fn new(sphere: Arc<Sphere>, cell: f32, streamed: bool) -> Planet {
        let max_depth = finest_depth(sphere.sea_radius(), cell);
        Planet { sphere, max_depth, streamed }
    }
}

/// Whether there is ground to stream.
pub fn streaming(planet: Res<Planet>) -> bool {
    planet.streamed
}

/// The streaming state. `wanted` is the tiling the player should see; `built` what is spawned,
/// which can briefly hold both a node and some of its descendants while one replaces the other;
/// `pending` the builds in flight; `loaded` the built nodes' data; `solid` the built nodes whose
/// chunk has a collider, which are those inside the physics bubble.
#[derive(Resource, Default)]
pub struct Chunks {
    pub wanted: HashSet<NodeId>,
    pub built: HashMap<NodeId, Entity>,
    /// Each build yields its chunk and how long the worker took over it.
    pub pending: HashMap<NodeId, Task<(ChunkMesh, Duration)>>,
    pub loaded: HashMap<NodeId, Arc<ChunkMesh>>,
    pub solid: HashSet<NodeId>,
}

impl Chunks {
    /// The ground under `p_body` on the finest loaded chunk holding its direction, or from the
    /// height function where nothing is loaded.
    #[allow(dead_code)] // only the tests read it so far
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
    /// whether there is built ground inside the physics bubble under it. `max_depth` is the
    /// planet's finest depth; the lookup walks the nodes holding the direction from there up.
    pub fn is_solid(&self, p_body: Vec3, max_depth: u8) -> bool {
        let dir = p_body.try_normalize().unwrap_or(Vec3::Y);
        (0..=max_depth).rev().map(|d| NodeId::leaf_at(dir, d)).find(|n| self.built.contains_key(n)).is_some_and(|n| self.solid.contains(&n))
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

/// Where `seed_ground` builds: the surface point under the course, in body coordinates.
#[derive(Resource)]
pub struct Seed {
    pub at: Vec3,
}

/// Builds the finest leaf under the seed point and every finest leaf within two of its sides on
/// the spot, and spawns them as `apply` would, so the player and the course have solid ground on
/// the first tick instead of hovering while the workers catch up.
#[allow(clippy::too_many_arguments)]
pub fn seed_ground(
    mut commands: Commands,
    mut chunks: ResMut<Chunks>,
    planet: Res<Planet>,
    tuning: Res<Tuning>,
    origin: Res<Origin>,
    bounds: Res<WorldBounds>,
    seed: Res<Seed>,
    look: Res<ChunkLook>,
    mut meshes: Option<ResMut<Assets<Mesh>>>,
) {
    let under = NodeId::leaf_at(seed.at.normalize(), planet.max_depth);
    let mut nodes = leaves_near(&planet.sphere, planet.max_depth, seed.at, 2.0 * under.arc(planet.sphere.sea_radius()));
    if !nodes.contains(&under) {
        nodes.push(under);
    }
    // The player is not spawned yet; the bubble is measured from where they will be.
    for node in nodes {
        spawn_chunk(&mut commands, &mut chunks, &planet, &tuning, &origin, Some(bounds.spawn), meshes.as_deref_mut(), &look, build_chunk(&planet.sphere, node));
    }
}

/// Streams terrain chunks over the `Surface::Sphere` already in the app; on a flat surface it
/// does nothing.
pub fn add_streaming(app: &mut App) {
    let Some(Surface::Sphere(sphere)) = app.world().get_resource::<Surface>().cloned() else { return };
    let planet = Planet::new(sphere, app.world().resource::<Tuning>().terrain.cell, true);
    origin::add_rebase(app);
    app.insert_resource(planet)
        .init_resource::<Chunks>()
        .init_resource::<ChunkLook>()
        .add_systems(Update, (plan, apply, bubble::solidify).chain().run_if(streaming))
        .add_systems(FixedUpdate, (bubble::freeze.before(gravitate), bubble::hold_player).before(ControllerSet).run_if(streaming));
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
        chunks.pending.insert(
            node,
            AsyncComputeTaskPool::get().spawn(async move {
                let start = Instant::now();
                let built = build_chunk(&sphere, node);
                (built, start.elapsed())
            }),
        );
    }
}

/// The material every chunk is drawn in, when there is a renderer: plain grey, or white under
/// vertex colours on a body with a palette.
#[derive(Resource)]
pub struct ChunkLook(pub Option<Handle<StandardMaterial>>);

impl ChunkLook {
    pub fn for_body(sphere: &Sphere, materials: Option<Mut<Assets<StandardMaterial>>>) -> ChunkLook {
        let base_color = if sphere.body.palette.is_some() { Color::WHITE } else { Color::srgb(0.5, 0.5, 0.52) };
        ChunkLook(materials.map(|mut m| m.add(StandardMaterial { base_color, perceptual_roughness: 1.0, ..default() })))
    }
}

impl FromWorld for ChunkLook {
    fn from_world(world: &mut World) -> Self {
        let sphere = world.resource::<Planet>().sphere.clone();
        ChunkLook::for_body(&sphere, world.get_resource_mut::<Assets<StandardMaterial>>())
    }
}

/// Spawns a built chunk and records it in `chunks`: a grey mesh when there is a renderer, and a
/// collider if it is inside the physics bubble around `player_body`. `apply` and `seed_ground`
/// both spawn through here, so a seeded chunk is indistinguishable from a streamed one.
#[allow(clippy::too_many_arguments)]
fn spawn_chunk(
    commands: &mut Commands,
    chunks: &mut Chunks,
    planet: &Planet,
    tuning: &Tuning,
    origin: &Origin,
    player_body: Option<Vec3>,
    meshes: Option<&mut Assets<Mesh>>,
    look: &ChunkLook,
    built: ChunkMesh,
) {
    let node = built.node;
    let built = Arc::new(built);
    let mut e = commands.spawn((Name::new("Chunk"), Chunk { node }, Transform::from_translation(origin.world(built.center)), RigidBody::Static));
    if let (Some(meshes), Some(grey)) = (meshes, look.0.as_ref()) {
        let mesh = match &planet.sphere.body.palette {
            Some(palette) => built.painted_mesh(&planet.sphere, palette),
            None => built.mesh(),
        };
        e.insert((Mesh3d(meshes.add(mesh)), MeshMaterial3d(grey.clone())));
    }
    if player_body.is_some_and(|p| node_distance(node, planet.sphere.sea_radius(), p) <= tuning.terrain.bubble) {
        e.insert(built.collider());
        chunks.solid.insert(node);
    }
    chunks.built.insert(node, e.id());
    chunks.loaded.insert(node, built);
}

/// Build times of the first `TIMED` streamed chunks, then the rate they are applied at.
#[derive(Default)]
struct ApplyStats {
    times: Vec<Duration>,
    window_start: Option<f32>,
    window_count: u32,
}

const TIMED: usize = 200;
/// Seconds over which the applied rate is averaged and logged.
const RATE_WINDOW: f32 = 10.0;

/// Spawns up to `APPLIED_PER_FRAME` finished builds: grey meshes when there is a renderer, with
/// colliders inside the physics bubble. Logs the mean and longest build time of the first
/// `TIMED` chunks once, then the chunks applied per second every `RATE_WINDOW` seconds while
/// any are.
#[allow(clippy::too_many_arguments)]
fn apply(
    mut commands: Commands,
    mut chunks: ResMut<Chunks>,
    planet: Res<Planet>,
    tuning: Res<Tuning>,
    origin: Res<Origin>,
    time: Res<Time<Real>>,
    players: Query<&Transform, With<Player>>,
    mut meshes: Option<ResMut<Assets<Mesh>>>,
    look: Res<ChunkLook>,
    mut stats: Local<ApplyStats>,
) {
    let player_body = players.single().ok().map(|tf| origin.body(tf.translation));
    let mut ready: Vec<NodeId> = chunks.pending.keys().copied().collect();
    ready.sort_by_key(|n| (n.face, n.depth, n.x, n.y));
    let mut applied = 0;
    for node in ready {
        if applied == APPLIED_PER_FRAME {
            break;
        }
        // A finished task must not be polled again, so it leaves `pending` as soon as it yields.
        let Some(task) = chunks.pending.get_mut(&node) else { continue };
        let Some((built, took)) = block_on(poll_once(task)) else { continue };
        chunks.pending.remove(&node);
        spawn_chunk(&mut commands, &mut chunks, &planet, &tuning, &origin, player_body, meshes.as_deref_mut(), &look, built);
        applied += 1;
        if stats.times.len() < TIMED {
            stats.times.push(took);
            if stats.times.len() == TIMED {
                let mean = stats.times.iter().sum::<Duration>() / TIMED as u32;
                let max = stats.times.iter().max().copied().unwrap_or_default();
                info!("chunk build at cell {} m: mean {:.2} ms, max {:.2} ms over the first {TIMED}", tuning.terrain.cell, mean.as_secs_f64() * 1e3, max.as_secs_f64() * 1e3);
            }
        }
    }
    let now = time.elapsed_secs();
    let start = *stats.window_start.get_or_insert(now);
    stats.window_count += applied as u32;
    if now - start >= RATE_WINDOW {
        if stats.window_count > 0 {
            info!("chunks applied at cell {} m: {:.1}/s over {:.0} s", tuning.terrain.cell, stats.window_count as f32 / (now - start), now - start);
        }
        stats.window_start = Some(now);
        stats.window_count = 0;
    }
}
