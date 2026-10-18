//! Targets: soldier dummies that get knocked over, flying drones that circle
//! and pop, and soldiers that patrol a route and shoot back. All take
//! `Damage` and respawn after a while.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::character::{Pose, Rig, RigPose};
use crate::controller::{ControllerSet, Player};
use crate::health::{PlayerHealth, PlayerHit};
use crate::terrain::Heightmap;
use crate::tuning::Tuning;
use crate::weapon::{self, Damage, FxAssets};

pub struct TargetsPlugin;

impl Plugin for TargetsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Score>()
            .add_systems(Startup, load_assets)
            .add_message::<PlayerHit>()
            .add_message::<Killed>()
            .add_message::<Shot>()
            .add_systems(FixedUpdate, (take_damage, respawn, patrol, hear, soldier_ai).chain().in_set(TargetSet).after(ControllerSet));
    }
}

#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct TargetSet;

/// Whose side a soldier is on. The player is team 0; the island's patrols are team 1.
#[derive(Component, Clone, Copy, Debug, PartialEq, Eq)]
pub struct Team(pub u8);

/// A soldier fired from `pos`, for the sound.
#[derive(Message, Debug, Clone, Copy)]
pub struct Shot {
    pub pos: Vec3,
    pub team: Team,
}

/// A target just died.
#[derive(Message, Debug, Clone, Copy)]
pub struct Killed {
    pub kind: TargetKind,
    pub team: Team,
    pub pos: Vec3,
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
    /// Seconds since the enemy was last seen, while alert.
    pub alert: Option<f32>,
    pub fire_cd: f32,
    /// Where the enemy was last seen (feet height).
    pub last_seen: Vec3,
    /// Hit since the last tick: look for cover.
    pub take_cover: bool,
    /// A cover spot (feet) and the seconds left there.
    pub cover: Option<(Vec3, f32)>,
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
    drone: Handle<bevy::world_serialization::WorldAsset>,
}

pub fn load_assets(mut commands: Commands, server: Res<AssetServer>, materials: Option<Res<Assets<StandardMaterial>>>) {
    if materials.is_none() {
        return;
    }
    commands.insert_resource(TargetAssets {
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
    if assets.is_some() {
        e.with_child(soldier_model(Team(1), Pose::Idle));
    }
}

/// A soldier walking `route` (feet positions, looped), starting at its first point.
pub fn spawn_soldier(commands: &mut Commands, tuning: &Tuning, assets: Option<&TargetAssets>, route: Vec<Vec3>) {
    spawn_soldier_team(commands, tuning, assets, route, Team(1));
}

/// A soldier on `team` walking `route`.
pub fn spawn_soldier_team(commands: &mut Commands, tuning: &Tuning, assets: Option<&TargetAssets>, route: Vec<Vec3>, team: Team) {
    let radius = 0.35;
    let feet = route[0];
    let home = feet + Vec3::Y * DUMMY_HEIGHT * 0.5;
    let mut e = commands.spawn((
        Name::new("Soldier"),
        Target { kind: TargetKind::Soldier, health: tuning.soldier.health, home, down: 0.0 },
        Soldier { next: 1 % route.len(), route, alert: None, fire_cd: 0.0, last_seen: feet, take_cover: false, cover: None },
        team,
        RigidBody::Kinematic,
        Collider::capsule(radius, DUMMY_HEIGHT - 2.0 * radius),
        Mass(70.0),
        Transform::from_translation(home),
        Visibility::default(),
    ));
    if assets.is_some() {
        e.with_child(soldier_model(team, Pose::Walk));
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

/// One of `team`'s characters with its loadout, feet at the bottom of the capsule, playing `pose`.
fn soldier_model(team: Team, pose: Pose) -> impl Bundle {
    (
        Rig::team(team.0),
        RigPose { pose, rate: 1.0 },
        Transform::from_xyz(0.0, -DUMMY_HEIGHT * 0.5, 0.0).with_scale(Vec3::splat(DUMMY_HEIGHT / crate::character::MODEL_HEIGHT)),
        Visibility::default(),
    )
}

#[allow(clippy::too_many_arguments)]
fn take_damage(
    mut commands: Commands,
    tuning: Res<Tuning>,
    mut damage: MessageReader<Damage>,
    mut score: ResMut<Score>,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut killed: MessageWriter<Killed>,
    mut targets: Query<(&mut Target, &Transform, Option<&Team>)>,
) {
    for hit in damage.read() {
        let Ok((mut target, tf, team)) = targets.get_mut(hit.entity) else { continue };
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
        killed.write(Killed { kind: target.kind, team: team.copied().unwrap_or(Team(1)), pos: tf.translation });
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

/// Something a soldier can shoot at: the player, or a live soldier of another team.
struct Enemy {
    entity: Entity,
    team: Team,
    eye: Vec3,
}

/// Soldiers react to what they hear: a gunshot within `hearing` sends them to look where it came
/// from, a soldier who has an enemy in sight calls it out to squad mates within `squad_radius`, and
/// one who is hit looks for cover.
#[allow(clippy::too_many_arguments)]
pub fn hear(
    tuning: Res<Tuning>,
    player: Single<&Transform, With<Player>>,
    mut fired: MessageReader<crate::weapon::WeaponFired>,
    mut shots: MessageReader<Shot>,
    mut damage: MessageReader<Damage>,
    mut soldiers: Query<(Entity, &Target, &Team, &mut Soldier, &Transform), Without<Player>>,
) {
    let t = &tuning.soldier;
    let mut noises: Vec<(Vec3, Team)> = shots.read().map(|s| (s.pos, s.team)).collect();
    if fired.read().count() > 0 {
        noises.push((player.translation, Team(0)));
    }
    let hit: Vec<Entity> = damage.read().map(|d| d.entity).collect();
    // Who has an enemy in sight right now, to call it out.
    let callouts: Vec<(Team, Vec3, Vec3)> = soldiers
        .iter()
        .filter(|(_, target, _, s, _)| target.alive() && s.alert == Some(0.0))
        .map(|(_, _, team, s, tf)| (*team, tf.translation, s.last_seen))
        .collect();
    for (entity, target, team, mut s, tf) in &mut soldiers {
        if !target.alive() {
            continue;
        }
        if hit.contains(&entity) {
            s.take_cover = true;
        }
        if s.alert.is_some_and(|a| a < 0.5) {
            continue;
        }
        let pos = tf.translation;
        let mut heard = None;
        // A shot from the other side is the enemy; one from our side is where the fight is.
        for (at, _) in &noises {
            let d = at.distance(pos);
            if d < t.hearing && d > 1.0 && heard.is_none_or(|(_, hd)| d < hd) {
                heard = Some((*at, d));
            }
        }
        for (from, at, target) in &callouts {
            if from == team && at.distance(pos) < t.squad_radius && at.distance(pos) > 0.01 {
                heard = Some((*target + Vec3::Y * SOLDIER_EYE, 0.0));
            }
        }
        if let Some((at, _)) = heard {
            s.alert = Some(0.0);
            s.last_seen = at - Vec3::Y * SOLDIER_EYE;
        }
    }
}

/// Patrol the route; on a clear line to an enemy within `sight`, face them and fire, closing in to `hold`
/// meters; chase the last place they were seen and give up after `forget` seconds. Soldiers hit by other
/// soldiers take `Damage`; the player takes `PlayerHit`.
#[allow(clippy::too_many_arguments)]
fn soldier_ai(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    heightmap: Option<Res<Heightmap>>,
    health: Res<PlayerHealth>,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    player: Single<(Entity, &Player, &Transform)>,
    mut soldiers: Query<(Entity, &Target, &Team, &mut Soldier, &mut Transform), Without<Player>>,
    mut shots: MessageWriter<Shot>,
    mut seed: Local<u64>,
) {
    let dt = time.delta_secs();
    let t = &tuning.soldier;
    let (player_entity, p, ptf) = *player;
    let mut enemies: Vec<Enemy> = Vec::new();
    if health.alive() {
        enemies.push(Enemy { entity: player_entity, team: Team(0), eye: ptf.translation + Vec3::Y * p.eye_offset(&tuning) });
    }
    for (entity, target, team, _, tf) in soldiers.iter() {
        if target.alive() {
            enemies.push(Enemy { entity, team: *team, eye: tf.translation + Vec3::Y * SOLDIER_EYE });
        }
    }
    let feet_y = |pos: Vec3| heightmap.as_ref().map_or(pos.y, |hm| hm.height_at(pos.x, pos.z));

    for (entity, target, team, mut soldier, mut tf) in &mut soldiers {
        if !target.alive() || soldier.route.is_empty() {
            continue;
        }
        let eye = tf.translation + Vec3::Y * SOLDIER_EYE;
        let filter = SpatialQueryFilter::from_excluded_entities([entity]);
        // The nearest enemy in sight.
        let mut seen: Option<(&Enemy, f32)> = None;
        for enemy in enemies.iter().filter(|e| e.team != *team && e.entity != entity) {
            let dist = enemy.eye.distance(eye);
            if dist > t.sight || dist < 0.01 || seen.is_some_and(|(_, d)| d <= dist) {
                continue;
            }
            let dir = (enemy.eye - eye) / dist;
            if spatial.cast_ray(eye, Dir3::new(dir).unwrap(), dist + 0.1, true, &filter).is_some_and(|hit| hit.entity == enemy.entity) {
                seen = Some((enemy, dist));
            }
        }
        soldier.fire_cd -= dt;
        let feet = tf.translation - Vec3::Y * DUMMY_HEIGHT * 0.5;
        // Hit: find the nearest spot within 10 m that the shooter can't see, and go there.
        if std::mem::take(&mut soldier.take_cover) && soldier.cover.is_none() {
            let threat = seen.map_or(soldier.last_seen + Vec3::Y * SOLDIER_EYE, |(e, _)| e.eye);
            let mut skip = vec![entity, player_entity];
            if let Some((e, _)) = seen {
                skip.push(e.entity);
            }
            let block = SpatialQueryFilter::from_excluded_entities(skip);
            let mut best: Option<(Vec3, f32)> = None;
            for k in 0..16 {
                let a = k as f32 * std::f32::consts::TAU / 16.0;
                for r in [3.0, 6.0, 9.0] {
                    let mut spot = feet + Vec3::new(a.cos() * r, 0.0, a.sin() * r);
                    spot.y = feet_y(spot);
                    let to = spot + Vec3::Y * SOLDIER_EYE - threat;
                    let len = to.length();
                    let Ok(dir) = Dir3::new(to / len.max(1e-3)) else { continue };
                    let hidden = spatial.cast_ray(threat, dir, len, true, &block).is_some_and(|h| h.distance < len - 0.6);
                    // Only spots it can walk to: nothing in the way at waist height.
                    let path = spot + Vec3::Y * 0.9 - (feet + Vec3::Y * 0.9);
                    let clear = Dir3::new(path / r).ok().is_some_and(|d| spatial.cast_ray(feet + Vec3::Y * 0.9, d, r, true, &block).is_none());
                    if hidden && clear && best.is_none_or(|(_, d)| r < d) {
                        best = Some((spot, r));
                    }
                }
            }
            if let Some((spot, _)) = best {
                soldier.cover = Some((spot, t.cover_time));
                soldier.alert = Some(0.0);
            }
        }
        if let Some((spot, left)) = soldier.cover.as_mut() {
            let delta = *spot - feet;
            let flat = Vec3::new(delta.x, 0.0, delta.z);
            if flat.length() > 0.3 {
                // Run for it, no shooting.
                let next = feet + flat.normalize() * (t.speed * 1.4 * dt).min(flat.length());
                tf.translation = Vec3::new(next.x, feet_y(next) + DUMMY_HEIGHT * 0.5, next.z);
                tf.rotation = Quat::from_rotation_y(flat.x.atan2(flat.z));
                continue;
            }
            *left -= dt;
            if *left > 0.0 {
                continue;
            }
            // Peek out: back to fighting from here.
            soldier.cover = None;
        }
        if let Some((enemy, dist)) = seen {
            soldier.alert = Some(0.0);
            soldier.last_seen = enemy.eye - Vec3::Y * SOLDIER_EYE;
            let to_enemy = enemy.eye - eye;
            tf.rotation = Quat::from_rotation_y(to_enemy.x.atan2(to_enemy.z));
            if soldier.fire_cd <= 0.0 {
                soldier.fire_cd = t.fire_interval;
                shots.write(Shot { pos: eye, team: *team });
                // Aim error: a random offset in a disc of `spread` radians.
                let a = next_unit(&mut seed) * std::f32::consts::TAU;
                let r = next_unit(&mut seed).sqrt() * t.spread;
                let dir = to_enemy / dist;
                let right = dir.cross(Vec3::Y).normalize_or(Vec3::X);
                let up = right.cross(dir);
                let aim = (dir + right * (r * a.cos()) + up * (r * a.sin())).normalize();
                let gun = crate::tuning::Gun { damage: t.damage, velocity: t.bullet_speed, drag: 0.0006, prop_impulse: 2.0, ..default() };
                weapon::spawn_bullet(&mut commands, fx.as_deref(), eye + aim * 0.6, aim, &gun, entity);
                if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                    weapon::spawn_blast(&mut commands, fx, materials, eye + aim * 0.6, 0.25);
                }
            }
            // Close in, but keep some distance.
            if dist > t.hold {
                let delta = soldier.last_seen - feet;
                let flat = Vec3::new(delta.x, 0.0, delta.z);
                if flat.length() > 0.1 {
                    let next = feet + flat.normalize() * t.speed * dt;
                    tf.translation = Vec3::new(next.x, feet_y(next) + DUMMY_HEIGHT * 0.5, next.z);
                }
            }
            continue;
        }
        if let Some(unseen) = soldier.alert.as_mut() {
            *unseen += dt;
            if *unseen < t.forget {
                // Head for where the enemy was last seen.
                let delta = soldier.last_seen - feet;
                let flat = Vec3::new(delta.x, 0.0, delta.z);
                if flat.length() > 1.0 {
                    let next = feet + flat.normalize() * t.speed * dt;
                    tf.translation = Vec3::new(next.x, feet_y(next) + DUMMY_HEIGHT * 0.5, next.z);
                    tf.rotation = Quat::from_rotation_y(flat.x.atan2(flat.z));
                }
                continue;
            }
            soldier.alert = None;
        }
        // Patrol: walk toward the next waypoint (feet positions).
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
