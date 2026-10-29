//! Where enemy ships exist (sections 5 to 7 of
//! `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`): only near the player, at
//! most `enemy_cap` at once. **Raiders** come in packs of Jackals while the player flies a ship:
//! a clock runs while no raiders are about, faster the longer the flight has gone without a fight,
//! and a pack comes in 1.5 to 3 km off to one side, never ahead of the nose, but never in the
//! first minute after boarding or within 3 km of a base. A raider past 6 km is gone. **Patrols**
//! circle every base whose faction flies a fighter, two each while the player is within 8 km; one
//! shot down comes back after ten minutes of game time, and the rest go when the player leaves or
//! the world changes, so nothing about them needs saving. The numbers are in `[ship_combat]`.
//!
//! Every enemy ship is kept awake (`KeepAwake`): the bubble would freeze a body this far from the
//! player, and they all fly, so none ever rests on ground for the bubble to wake it on.

use avian3d::prelude::*;
use bevy::prelude::*;
use std::collections::HashMap;

use super::ai::{Enemy, Mode, Role};
use super::base::{Base, Bases};
use super::combat::Hull;
use super::ship::{clearance, Autopilot, Ship, ShipKind, Ships};
use super::Solar;
use crate::controller::Player;
use crate::planet::bubble::KeepAwake;
use crate::surface::{Origin, Surface};
use crate::tuning::{ShipCombat, Tuning};

/// A base's patrols stay this much past `patrol_range` before they go, so flying along the edge
/// does not spawn and drop them over and over.
const LEAVE_MARGIN: f32 = 500.0;

/// The raid clock.
#[derive(Resource)]
pub struct Raids {
    /// Counts up to `raid_delay` while no raiders are about.
    pub clock: f32,
    /// Seconds flown without a fight: the clock runs faster the longer it gets.
    pub quiet: f32,
    /// Seconds since the player last boarded.
    pub aboard: f32,
    /// A pack comes now, whatever the clock says (`RUST_REGIME_RAIDERS=1`, and the tests).
    pub force: bool,
    rng: Rng,
}

impl Default for Raids {
    fn default() -> Self {
        Self { clock: 0.0, quiet: 0.0, aboard: 0.0, force: std::env::var_os("RUST_REGIME_RAIDERS").is_some(), rng: Rng(0x2545_f491_4f6c_dd1d) }
    }
}

/// When each base's patrols were shot down, by `(base, slot)`, on a clock of game time.
#[derive(Resource, Default)]
pub struct Patrols {
    pub clock: f64,
    pub lost: HashMap<(usize, usize), f64>,
}

/// A small generator for where packs come in and how many.
pub struct Rng(pub u64);

impl Rng {
    /// 0 to 1.
    pub fn next(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
        (self.0 >> 40) as f32 / (1u64 << 24) as f32
    }

    /// `lo` to `hi`, both included.
    pub fn range(&mut self, lo: usize, hi: usize) -> usize {
        lo + ((self.next() * (hi + 1 - lo) as f32) as usize).min(hi - lo)
    }
}

pub fn build(app: &mut App) {
    app.init_resource::<Raids>()
        .init_resource::<Patrols>()
        .add_observer(lost)
        .add_systems(FixedUpdate, (cull, raid, guard).chain().after(super::ship::board).before(super::ai::think));
}

/// An enemy ship of spec `spec` at `at`, turned `rotation` and moving at `velocity`, flown by its
/// own pilot.
pub fn spawn_enemy(world: &mut World, spec: usize, at: Vec3, rotation: Quat, velocity: Vec3, role: Role) -> Entity {
    let ship = super::ship::spawn(world, spec, Transform::from_translation(at).with_rotation(rotation));
    // Spread evenly however many come.
    let quirk = (ship.index().index() as f32 * 0.618_034).fract();
    world.entity_mut(ship).insert((Enemy::new(role, quirk), Autopilot, KeepAwake, Position(at), Rotation(rotation), LinearVelocity(velocity)));
    ship
}

/// Where a pack of `n` comes in on a ship at `from` with its nose along `nose`: round one spot
/// 100 to 150 degrees off the nose to either side, a little above or below, between
/// `spawn_near` and `spawn_far` away, the pack abreast across the line to it. Every ship of it
/// keeps twice `ai_floor` over the ground (`clear` measures it); none if no spot does.
pub fn pack_spots(rng: &mut Rng, from: Vec3, nose: Vec3, up: Vec3, n: usize, t: &ShipCombat, clear: impl Fn(Vec3) -> f32) -> Vec<Vec3> {
    let nose = nose.normalize_or(Vec3::NEG_Z);
    let lift = (up - nose * up.dot(nose)).normalize_or(nose.any_orthonormal_vector());
    let side = nose.cross(lift);
    let fits = |p: &Vec3| (*p - from).dot(nose) <= 0.0 && (t.spawn_near..=t.spawn_far).contains(&p.distance(from)) && clear(*p) >= t.ai_floor * 2.0;
    for _ in 0..16 {
        let off = (100.0 + 50.0 * rng.next()).to_radians();
        let around = if rng.next() < 0.5 { 1.0 } else { -1.0 };
        let tilt = (rng.next() * 30.0 - 10.0).to_radians();
        let dir = (nose * off.cos() + side * off.sin() * around) * tilt.cos() + lift * tilt.sin();
        let centre = from + dir * (t.spawn_near + 100.0 + rng.next() * (t.spawn_far - t.spawn_near - 200.0));
        // Abreast: 50 m apart across the line, every other one a little higher.
        let across = dir.cross(lift).normalize_or(side);
        let spots: Vec<Vec3> = (0..n).map(|i| centre + across * (i as f32 - (n as f32 - 1.0) / 2.0) * 50.0 + lift * (i % 2) as f32 * 20.0).collect();
        if spots.iter().all(fits) {
            return spots;
        }
    }
    Vec::new()
}

/// The fighter a faction patrols its base with: the first fighter of its side in `ships.toml`.
pub fn patrol_ship(specs: &Ships, faction: &str) -> Option<usize> {
    specs.ship.iter().position(|s| s.kind == ShipKind::Fighter && s.faction.id() == faction)
}

/// Raiders past `despawn`, and patrols whose base is gone (another world) or far behind, go
/// without a trace; the next spawn replaces them.
fn cull(mut commands: Commands, tuning: Res<Tuning>, players: Query<&Transform, With<Player>>, bases: Query<(&Transform, &Base)>, enemies: Query<(Entity, &Enemy, &Transform)>) {
    let t = &tuning.ship_combat;
    let Ok(player) = players.single() else { return };
    for (e, enemy, tf) in &enemies {
        let gone = match enemy.role {
            Role::Raider => tf.translation.distance(player.translation) > t.despawn,
            Role::Patrol { base, .. } => bases.iter().find(|(_, b)| b.spec == base).is_none_or(|(at, _)| at.translation.distance(player.translation) > t.patrol_range + LEAVE_MARGIN),
        };
        if gone {
            commands.entity(e).despawn();
        }
    }
}

/// Runs the raid clock while the player flies, and sends a pack in when it is due.
#[allow(clippy::too_many_arguments)]
fn raid(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    mut raids: ResMut<Raids>,
    bases: Query<&Transform, With<Base>>,
    flown: Query<(&Ship, &Position, &Rotation, &LinearVelocity), Without<Enemy>>,
    enemies: Query<&Enemy>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    let Some((_, pos, rot, vel)) = flown.iter().find(|(s, ..)| s.pilot.is_some()) else {
        // On foot nothing comes, and boarding starts the quiet minute again.
        raids.aboard = 0.0;
        return;
    };
    raids.aboard += dt;
    if enemies.iter().any(|e| e.mode != Mode::Patrol && !e.fleeing) {
        raids.quiet = 0.0;
    } else {
        raids.quiet += dt;
    }
    if !enemies.iter().any(|e| e.role == Role::Raider) {
        raids.clock += dt * (1.0 + raids.quiet / t.raid_hurry);
    }
    let near_base = bases.iter().any(|b| b.translation.distance(pos.0) < t.raid_clear);
    let due = raids.clock >= t.raid_delay && raids.aboard >= t.raid_grace && !near_base;
    let Some(raider) = specs.ship.iter().position(|s| s.id == t.raider) else { return };
    if !(due || raids.force) {
        return;
    }
    let room = t.enemy_cap.saturating_sub(enemies.iter().count());
    let n = raids.rng.range(t.raid_pack[0], t.raid_pack[1]).min(room);
    let up = surface.up(origin.body(pos.0));
    let spots = if n == 0 { Vec::new() } else { pack_spots(&mut raids.rng, pos.0, rot.0 * Vec3::NEG_Z, up, n, t, |p| clearance(&solar, &surface, origin.body(p))) };
    if spots.is_empty() {
        return;
    }
    raids.clock = 0.0;
    raids.force = false;
    info!("{} raiders inbound", spots.len());
    let (from, velocity) = (pos.0, vel.0);
    commands.queue(move |world: &mut World| {
        for at in spots {
            let facing = Transform::from_translation(at).looking_at(from, up).rotation;
            spawn_enemy(world, raider, at, facing, velocity, Role::Raider);
        }
    });
}

/// Puts up each base's patrols while the player is within `patrol_range` of it: evenly round the
/// loop at patrol height, flying it. A slot shot down waits out `patrol_respawn`.
#[allow(clippy::too_many_arguments)]
fn guard(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    base_specs: Res<Bases>,
    mut patrols: ResMut<Patrols>,
    players: Query<&Transform, With<Player>>,
    bases: Query<(&Transform, &Base)>,
    enemies: Query<&Enemy>,
) {
    let t = &tuning.ship_combat;
    patrols.clock += time.delta_secs_f64();
    let Ok(player) = players.single() else { return };
    let mut alive = enemies.iter().count();
    for (tf, base) in &bases {
        if tf.translation.distance(player.translation) > t.patrol_range {
            continue;
        }
        let Some(ship) = patrol_ship(&specs, &base_specs.base[base.spec].faction) else { continue };
        for slot in 0..t.patrols {
            let role = Role::Patrol { base: base.spec, slot };
            if enemies.iter().any(|e| e.role == role) || alive >= t.enemy_cap {
                continue;
            }
            if patrols.lost.get(&(base.spec, slot)).is_some_and(|at| patrols.clock < at + t.patrol_respawn as f64) {
                continue;
            }
            patrols.lost.remove(&(base.spec, slot));
            alive += 1;
            let up = tf.rotation * Vec3::Y;
            let out = Quat::from_axis_angle(up, slot as f32 / t.patrols as f32 * std::f32::consts::TAU) * (tf.rotation * Vec3::X);
            let at = tf.translation + out * t.patrol_radius + up * t.patrol_altitude;
            // Round the loop the way `ai` flies it.
            let along = up.cross(out);
            let rotation = Transform::default().looking_to(along, up).rotation;
            let velocity = along * specs.ship[ship].cruise * 0.5;
            commands.queue(move |world: &mut World| {
                spawn_enemy(world, ship, at, rotation, velocity, role);
            });
        }
    }
}

/// A patrol shot down starts its slot's wait.
fn lost(remove: On<Remove, Enemy>, enemies: Query<(&Enemy, &Hull)>, mut patrols: ResMut<Patrols>) {
    let Ok((enemy, hull)) = enemies.get(remove.entity) else { return };
    if let Role::Patrol { base, slot } = enemy.role
        && hull.hp <= 0.0
    {
        let now = patrols.clock;
        patrols.lost.insert((base, slot), now);
    }
}
