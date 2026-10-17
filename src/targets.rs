//! Targets: soldier dummies that get knocked over, flying drones that circle
//! and pop, and soldiers that patrol a route and shoot back. All take
//! `Damage` and respawn after a while.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::{ControllerSet, Player};
use crate::health::PlayerHit;
use crate::tuning::Tuning;
use crate::weapon::{self, Damage, FxAssets};

pub struct TargetsPlugin;

impl Plugin for TargetsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Score>()
            .add_systems(Startup, load_assets)
            .add_message::<PlayerHit>()
            .add_systems(FixedUpdate, (take_damage, respawn, patrol, soldier_ai).chain().after(ControllerSet))
            .add_observer(start_animation);
    }
}

#[derive(Resource, Default, Debug)]
pub struct Score {
    pub hits: u32,
    pub kills: u32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TargetKind {
    /// Static capsule; falls over as a ragdoll-ish rigid body when killed.
    Dummy,
    /// Kinematic; circles `center` at `radius`, bobbing. Hidden while dead.
    Drone { center: Vec3, radius: f32, phase: f32 },
    /// Kinematic; walks a `Soldier` route and shoots the player on sight.
    Soldier,
}

/// Route and state of a patrolling soldier.
#[derive(Component, Debug)]
pub struct Soldier {
    pub route: Vec<Vec3>,
    pub next: usize,
    /// Seconds since the player was last seen, while alert.
    pub alert: Option<f32>,
    pub fire_cd: f32,
}

#[derive(Component, Debug)]
pub struct Target {
    pub kind: TargetKind,
    pub health: f32,
    pub home: Vec3,
    /// Seconds until respawn; 0 while alive.
    pub down: f32,
}

impl Target {
    pub fn alive(&self) -> bool {
        self.down <= 0.0
    }
}

/// glTF handles for target models; absent in headless tests.
#[derive(Resource)]
pub struct TargetAssets {
    soldier: Handle<bevy::world_serialization::WorldAsset>,
    soldier_idle: Handle<AnimationClip>,
    soldier_walk: Handle<AnimationClip>,
    drone: Handle<bevy::world_serialization::WorldAsset>,
}

/// Put on a `WorldAssetRoot`: once the glTF is spawned, loop this clip.
#[derive(Component)]
pub struct PlayAnimation(pub Handle<AnimationClip>);

pub fn load_assets(mut commands: Commands, server: Res<AssetServer>, materials: Option<Res<Assets<StandardMaterial>>>) {
    if materials.is_none() {
        return;
    }
    let soldier = "models/arena/character-soldier.glb";
    commands.insert_resource(TargetAssets {
        soldier: server.load(GltfAssetLabel::Scene(0).from_asset(soldier)),
        // Animation 1 is "idle" (0 is "static").
        soldier_idle: server.load(GltfAssetLabel::Animation(1).from_asset(soldier)),
        soldier_walk: server.load(GltfAssetLabel::Animation(2).from_asset(soldier)),
        drone: server.load(GltfAssetLabel::Scene(0).from_asset("models/fps/enemy-flying.glb")),
    });
}

pub const DUMMY_HEIGHT: f32 = 1.8;

/// A soldier dummy standing at `feet`. The model faces +Z at `yaw` 0.
pub fn spawn_dummy(commands: &mut Commands, tuning: &Tuning, assets: Option<&TargetAssets>, feet: Vec3, yaw: f32) {
    let radius = 0.35;
    let home = feet + Vec3::Y * DUMMY_HEIGHT * 0.5;
    let mut e = commands.spawn((
        Name::new("Dummy"),
        Target { kind: TargetKind::Dummy, health: tuning.target_health, home, down: 0.0 },
        RigidBody::Static,
        Collider::capsule(radius, DUMMY_HEIGHT - 2.0 * radius),
        Mass(70.0),
        Transform::from_translation(home).with_rotation(Quat::from_rotation_y(yaw)),
        Visibility::default(),
    ));
    if let Some(assets) = assets {
        // Kenney's soldier is 0.84 units tall; the model's origin is at its feet.
        let scale = DUMMY_HEIGHT / 0.84;
        e.with_child((
            bevy::world_serialization::WorldAssetRoot(assets.soldier.clone()),
            PlayAnimation(assets.soldier_idle.clone()),
            Transform::from_xyz(0.0, -DUMMY_HEIGHT * 0.5, 0.0).with_scale(Vec3::splat(scale)),
        ));
    }
}

/// A soldier walking `route` (feet positions, looped), starting at its first point.
pub fn spawn_soldier(commands: &mut Commands, tuning: &Tuning, assets: Option<&TargetAssets>, route: Vec<Vec3>) {
    let radius = 0.35;
    let feet = route[0];
    let home = feet + Vec3::Y * DUMMY_HEIGHT * 0.5;
    let mut e = commands.spawn((
        Name::new("Soldier"),
        Target { kind: TargetKind::Soldier, health: tuning.soldier.health, home, down: 0.0 },
        Soldier { route, next: 1, alert: None, fire_cd: 0.0 },
        RigidBody::Kinematic,
        Collider::capsule(radius, DUMMY_HEIGHT - 2.0 * radius),
        Mass(70.0),
        Transform::from_translation(home),
        Visibility::default(),
    ));
    if let Some(assets) = assets {
        let scale = DUMMY_HEIGHT / 0.84;
        e.with_child((
            bevy::world_serialization::WorldAssetRoot(assets.soldier.clone()),
            PlayAnimation(assets.soldier_walk.clone()),
            Transform::from_xyz(0.0, -DUMMY_HEIGHT * 0.5, 0.0).with_scale(Vec3::splat(scale)),
        ));
    }
}

/// A drone circling `center` horizontally at `radius`.
pub fn spawn_drone(commands: &mut Commands, tuning: &Tuning, assets: Option<&TargetAssets>, center: Vec3, radius: f32, phase: f32) {
    let home = center + Vec3::new(phase.cos(), 0.0, phase.sin()) * radius;
    let mut e = commands.spawn((
        Name::new("Drone"),
        Target { kind: TargetKind::Drone { center, radius, phase }, health: tuning.drone_health, home, down: 0.0 },
        RigidBody::Kinematic,
        Collider::sphere(0.5),
        Transform::from_translation(home),
        Visibility::default(),
    ));
    if let Some(assets) = assets {
        e.with_child((
            bevy::world_serialization::WorldAssetRoot(assets.drone.clone()),
            Transform::from_xyz(0.0, -0.45, 0.0).with_scale(Vec3::splat(1.3)),
        ));
    }
}

/// Find the glTF's `AnimationPlayer` once the model is spawned and loop the clip.
fn start_animation(
    ready: On<bevy::world_serialization::WorldInstanceReady>,
    mut commands: Commands,
    requests: Query<&PlayAnimation>,
    children: Query<&Children>,
    mut players: Query<&mut AnimationPlayer>,
    graphs: Option<ResMut<Assets<AnimationGraph>>>,
) {
    let (Ok(request), Some(mut graphs)) = (requests.get(ready.entity), graphs) else { return };
    let (graph, node) = AnimationGraph::from_clip(request.0.clone());
    let graph = graphs.add(graph);
    for e in children.iter_descendants(ready.entity) {
        if let Ok(mut player) = players.get_mut(e) {
            player.play(node).repeat();
            commands.entity(e).insert(AnimationGraphHandle(graph.clone()));
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn take_damage(
    mut commands: Commands,
    tuning: Res<Tuning>,
    mut damage: MessageReader<Damage>,
    mut score: ResMut<Score>,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut targets: Query<(&mut Target, &Transform)>,
) {
    for hit in damage.read() {
        let Ok((mut target, tf)) = targets.get_mut(hit.entity) else { continue };
        if !target.alive() {
            continue;
        }
        score.hits += 1;
        target.health -= hit.amount;
        if target.health > 0.0 {
            continue;
        }
        score.kills += 1;
        target.down = tuning.target_respawn;
        match target.kind {
            TargetKind::Dummy | TargetKind::Soldier => {
                // Let it fall: becomes a dynamic body with the hit's momentum.
                let spin = Vec3::Y.cross(hit.impulse) * 2.0;
                commands.entity(hit.entity).insert((
                    RigidBody::Dynamic,
                    LinearVelocity(hit.impulse + Vec3::Y * 1.5),
                    AngularVelocity(spin),
                ));
            }
            TargetKind::Drone { .. } => {
                commands.entity(hit.entity).insert(Visibility::Hidden);
                if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                    weapon::spawn_blast(&mut commands, fx, materials, tf.translation, 1.2);
                }
            }
        }
    }
}

fn respawn(mut commands: Commands, time: Res<Time>, tuning: Res<Tuning>, mut targets: Query<(Entity, &mut Target, Option<&mut Soldier>)>) {
    for (e, mut target, soldier) in &mut targets {
        if target.alive() {
            continue;
        }
        target.down -= time.delta_secs();
        if target.alive() {
            target.down = 0.0;
            let health = match target.kind {
                TargetKind::Dummy => tuning.target_health,
                TargetKind::Drone { .. } => tuning.drone_health,
                TargetKind::Soldier => tuning.soldier.health,
            };
            target.health = health;
            if let Some(mut soldier) = soldier {
                soldier.next = 1 % soldier.route.len();
                soldier.alert = None;
                soldier.fire_cd = 0.0;
            }
            let body = match target.kind {
                TargetKind::Dummy => RigidBody::Static,
                TargetKind::Drone { .. } | TargetKind::Soldier => RigidBody::Kinematic,
            };
            commands.entity(e).insert((
                body,
                Position(target.home),
                Rotation::default(),
                Transform::from_translation(target.home),
                LinearVelocity::ZERO,
                AngularVelocity::ZERO,
                Visibility::Inherited,
            ));
        }
    }
}

fn patrol(time: Res<Time>, tuning: Res<Tuning>, mut drones: Query<(&Target, &mut Transform)>) {
    let elapsed = time.elapsed_secs();
    for (target, mut tf) in &mut drones {
        let TargetKind::Drone { center, radius, phase } = target.kind else { continue };
        if !target.alive() {
            continue;
        }
        let a = phase + elapsed * tuning.drone_speed / radius.max(0.1);
        tf.translation = center + Vec3::new(a.cos() * radius, (elapsed * 1.7 + phase).sin() * 0.5, a.sin() * radius);
        // Face along the circle.
        tf.rotation = Quat::from_rotation_y(-a);
    }
}

/// Tiny deterministic random source for aim error (no `rand` dependency).
fn next_unit(seed: &mut u64) -> f32 {
    *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    ((*seed >> 40) as f32) / (1u64 << 24) as f32
}

const SOLDIER_EYE: f32 = 0.6;

/// Patrol the route; on a clear line to the player within `sight`, stop,
/// face them and fire; lose interest after `forget` seconds unseen.
#[allow(clippy::too_many_arguments)]
fn soldier_ai(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    player: Single<(Entity, &Player, &Transform)>,
    mut soldiers: Query<(Entity, &Target, &mut Soldier, &mut Transform), Without<Player>>,
    mut hits: MessageWriter<PlayerHit>,
    mut seed: Local<u64>,
) {
    let dt = time.delta_secs();
    let t = &tuning.soldier;
    let (player_entity, p, ptf) = *player;
    let player_eye = ptf.translation + Vec3::Y * p.eye_offset(&tuning);
    for (entity, target, mut soldier, mut tf) in &mut soldiers {
        if !target.alive() || soldier.route.is_empty() {
            continue;
        }
        let eye = tf.translation + Vec3::Y * SOLDIER_EYE;
        let to_player = player_eye - eye;
        let dist = to_player.length();
        let filter = SpatialQueryFilter::from_excluded_entities([entity]);
        let sees = dist <= t.sight
            && dist > 0.01
            && spatial
                .cast_ray(eye, Dir3::new(to_player).unwrap(), dist + 0.1, true, &filter)
                .is_some_and(|hit| hit.entity == player_entity);
        soldier.fire_cd -= dt;
        if sees {
            soldier.alert = Some(0.0);
            tf.rotation = Quat::from_rotation_y(to_player.x.atan2(to_player.z));
            if soldier.fire_cd <= 0.0 {
                soldier.fire_cd = t.fire_interval;
                // Aim error: a random offset in a disc of `spread` radians.
                let a = next_unit(&mut seed) * std::f32::consts::TAU;
                let r = next_unit(&mut seed).sqrt() * t.spread;
                let dir = to_player / dist;
                let right = dir.cross(Vec3::Y).normalize_or(Vec3::X);
                let up = right.cross(dir);
                let aim = (dir + right * (r * a.cos()) + up * (r * a.sin())).normalize();
                if let Some(hit) = spatial.cast_ray(eye, Dir3::new(aim).unwrap(), t.sight * 1.5, true, &filter)
                    && hit.entity == player_entity
                {
                    hits.write(PlayerHit { amount: t.damage });
                }
                if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                    weapon::spawn_blast(&mut commands, fx, materials, eye + aim * 0.6, 0.25);
                }
            }
            continue;
        }
        if let Some(unseen) = soldier.alert.as_mut() {
            *unseen += dt;
            if *unseen < t.forget {
                continue;
            }
            soldier.alert = None;
        }
        // Patrol: walk toward the next waypoint (feet positions).
        let feet = tf.translation - Vec3::Y * DUMMY_HEIGHT * 0.5;
        let goal = soldier.route[soldier.next];
        let delta = goal - feet;
        let step = t.speed * dt;
        if delta.length() <= step.max(0.05) {
            tf.translation = goal + Vec3::Y * DUMMY_HEIGHT * 0.5;
            soldier.next = (soldier.next + 1) % soldier.route.len();
        } else {
            let dir = delta / delta.length();
            tf.translation += dir * step;
            tf.rotation = Quat::from_rotation_y(dir.x.atan2(dir.z));
        }
    }
}
