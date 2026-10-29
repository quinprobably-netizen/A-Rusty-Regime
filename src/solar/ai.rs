//! The enemy pilots (section 8 of `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`):
//! one state machine per enemy ship, which flies it the way the player does, by writing its own
//! `ShipControls` (stick, thrust, boost and trigger). `fly` then gives it the turn rates, boost
//! tank, speed caps and flight assist of its hull, so an enemy cannot do anything the player
//! cannot. `Patrol` follows a loop round its base (a raider with nothing to hunt flies on),
//! `Pursue` flies at a point ahead of the target, `Attack` aims the guns where the shots will meet
//! it and fires inside a cone, and `Break` is the hard turn after a pass, or the run home when
//! hurt. How each hull fights is its `ai` entry in `ships.toml`.
//!
//! Enemies hunt ships only: the target is the ship the player flies, never the player on foot,
//! and never a ship of their own side. Raiders and hunters always attack it; a patrol only while
//! its faction's standing with you is below 0, or once you have shot it (`standing::attacks`),
//! and it forgets that once it lets you go. Nothing here holds a position from one tick to the next,
//! so the origin rebase and a handoff to another world's frame have nothing to convert.

use avian3d::prelude::*;
use bevy::prelude::*;
use serde::Deserialize;

use super::base::Base;
use super::combat::{Faction, Hull};
use super::missile::Missiles;
use super::ship::{clearance, Ship, ShipControls, Ships};
use super::{standing, Solar};
use crate::save::Save;
use crate::surface::{Origin, Surface};
use crate::tuning::{ShipCombat, Tuning};

/// How one hull fights (`ai = { ... }` in `ships.toml`).
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct AiSpec {
    /// Inside this range (m) it attacks: aims at the lead and fires.
    pub attack_range: f32,
    /// It fires only while the lead is this close to its nose, degrees.
    pub cone: f32,
    /// The range it tries to keep while attacking (m); 0 rushes straight in.
    pub hold: f32,
    /// Closer than this (m) it breaks off the pass.
    pub break_range: f32,
    /// How long the break lasts (s), and how hard it pulls the stick, 0 to 1: a wide turn is a
    /// gentle one held for longer.
    pub break_time: f32,
    pub break_turn: f32,
    /// At or under this fraction of its hull it breaks off for good and runs; 0 never runs.
    pub flee_hull: f32,
    /// Further than this (m) from the target it boosts.
    pub boost_range: f32,
    /// How far its aim wanders across the lead, degrees: a perfect shot every time is no fun.
    pub wobble: f32,
    /// It flies with missiles: while it has one it points its nose at the target to lock it, and
    /// fires once locked, `[ship_combat] ai_missile_gap` seconds apart.
    pub missiles: bool,
}

impl Default for AiSpec {
    fn default() -> Self {
        Self { attack_range: 1200.0, cone: 3.0, hold: 0.0, break_range: 150.0, break_time: 2.5, break_turn: 1.0, flee_hull: 0.0, boost_range: 1500.0, wobble: 1.0, missiles: false }
    }
}

/// What an enemy pilot is doing.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum Mode {
    #[default]
    Patrol,
    Pursue,
    Attack,
    Break,
}

/// Why an enemy ship is there: a raider hunting whoever flies by, one of a base's patrols
/// (`base` indexes `Bases`, `slot` counts its patrols from 0), or one of a pack a faction that
/// hunts you sent (`standing`), which flies like a raider.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Raider,
    Patrol { base: usize, slot: usize },
    Hunter,
}

/// An enemy ship's pilot.
#[derive(Component, Debug)]
pub struct Enemy {
    pub role: Role,
    pub mode: Mode,
    /// Seconds left of a break.
    pub timer: f32,
    /// Which way the break turns, 1 or -1: alternates each pass.
    side: f32,
    /// Hurt past its `flee_hull`: it has broken off for good.
    pub fleeing: bool,
    /// You have shot it in this fight: a patrol comes for you whatever your standing, until it
    /// lets you go.
    pub provoked: bool,
    /// The steady pull `steer` holds near the mark, rad/s in pitch and yaw.
    trim: Vec2,
    /// 0 to 1, its own: which way it swings in from and breaks, how long, and where its aim
    /// wanders, so a pack does not fly as one.
    quirk: f32,
}

impl Enemy {
    pub fn new(role: Role, quirk: f32) -> Self {
        Self { role, mode: Mode::Patrol, timer: 0.0, side: if quirk < 0.5 { 1.0 } else { -1.0 }, fleeing: false, provoked: false, trim: Vec2::ZERO, quirk }
    }
}

pub fn build(app: &mut App) {
    app.add_systems(FixedUpdate, think.before(super::ship::fly));
}

/// Where to aim a shot that flies at `speed` relative to the shooter so it meets a target `rel`
/// away and moving at `rel_v` against the shooter: the shot carries the shooter's own velocity,
/// so only the relative motion counts. Relative to the shooter; straight at the target if no
/// shot can catch it.
pub fn lead(rel: Vec3, rel_v: Vec3, speed: f32) -> Vec3 {
    // |rel + rel_v t| = speed t, for the first t > 0.
    let (a, b, c) = (rel_v.length_squared() - speed * speed, 2.0 * rel.dot(rel_v), rel.length_squared());
    let t = if a.abs() < 1e-3 {
        (b < 0.0).then(|| -c / b)
    } else {
        let disc = b * b - 4.0 * a * c;
        (disc >= 0.0).then(|| {
            let (r1, r2) = ((-b - disc.sqrt()) / (2.0 * a), (-b + disc.sqrt()) / (2.0 * a));
            [r1, r2].into_iter().filter(|t| *t > 0.0).fold(f32::MAX, f32::min)
        })
    };
    match t.filter(|t| *t < f32::MAX) {
        Some(t) => rel + rel_v * t,
        None => rel,
    }
}

/// The stick that swings a ship turned `rot` toward world direction `dir`: well off the nose it
/// banks into the turn and pulls, as a pilot does, but never further than `bank` radians off
/// level, so it is never upside down; within a few degrees it yaws onto it and holds the wings
/// level with `up`. Each axis is a rate demand against the hull's `rates`,
/// so a slow hull is asked for no more than it can give. Near the mark `trim` builds up a steady
/// pull in pitch and yaw over `dt`: flight assist levels a nose held only a little off the
/// horizon, and a line of sight turns as the range closes, and without it either would hold the
/// guns a degree off.
#[allow(clippy::too_many_arguments)]
pub fn steer(rot: Quat, dir: Vec3, up: Vec3, rates: [f32; 3], bank: f32, trim: &mut Vec2, dt: f32) -> Vec3 {
    /// How fast an angle off is asked to close, 1/s, and how fast the trim builds, 1/s².
    const GAIN: f32 = 3.0;
    const TRIM: f32 = 4.0;
    let local = rot.inverse() * dir;
    let level = rot.inverse() * up;
    // Rolling by this much would level the wings.
    let to_level = (-level.x).atan2(level.y);
    let far = local.angle_between(Vec3::NEG_Z) > 0.25;
    // Behind, it pulls round (it is never upside down, so that is the sky side), never pushes
    // the nose down through a bunt.
    let pitch = local.y.atan2(-local.z);
    let pitch = if local.z > 0.0 { pitch.abs() } else { pitch };
    // Banked over, a yaw would swing the nose up or down instead of round: well off the mark it
    // yaws only as far as the wings are level.
    let yaw = (-local.x).atan2(-local.z) * if far { level.y.clamp(0.0, 1.0) } else { 1.0 };
    // Well off, it banks into the turn round `up` it has to make, the further the more, as far as
    // `bank` allows; it rolls there by way of level.
    let roll = if far {
        let fwd = rot * Vec3::NEG_Z;
        let flat = |v: Vec3| (v - up * v.dot(up)).try_normalize();
        let heading = flat(fwd).or_else(|| flat(rot * Vec3::Y * -fwd.dot(up).signum())).unwrap_or(Vec3::NEG_Z);
        let goal = flat(dir).unwrap_or(heading);
        let turn = heading.cross(goal).dot(up).atan2(heading.dot(goal));
        (turn * 1.5).clamp(-bank, bank) + to_level
    } else {
        to_level
    };
    let off = Vec2::new(pitch, yaw);
    *trim = if !far && off.length() < 0.1 { (*trim + off * TRIM * dt).clamp(Vec2::splat(-0.3), Vec2::splat(0.3)) } else { *trim * (-4.0 * dt).exp() };
    ((Vec3::new(pitch, yaw, roll) * GAIN + trim.extend(0.0)) / Vec3::from(rates)).clamp(Vec3::NEG_ONE, Vec3::ONE)
}

/// The least clearance an enemy ship will have over the next `ai_lookahead` seconds on its
/// present path (longer the faster it goes over 200 m/s, as it takes longer to turn), from
/// `clear` (how high a world point is over the ground): where it is, half way and at the end, so
/// a hillside ahead counts as well as a dive.
pub fn margin(p: Vec3, v: Vec3, t: &ShipCombat, clear: impl Fn(Vec3) -> f32) -> f32 {
    let ahead = t.ai_lookahead * (v.length() / 200.0).max(1.0);
    [0.0, 0.5, 1.0].into_iter().map(|k| clear(p + v * ahead * k)).fold(f32::MAX, f32::min)
}

/// Keeps a heading off the ground with `margin` to spare ahead: within three floors
/// (`ai_floor`) of it the heading dives less and less steeply, and under one it climbs, the
/// harder the lower. Also how much room there is, 0 (at the floor) to 1 (three floors up or
/// more), which `think` limits the bank by, and how far under the floor it is, 0 to 1, which it
/// lifts by; `fly`'s flight assist does the rest (it pulls out of a dive the engines could not
/// stop in time).
pub fn avoid_ground(dir: Vec3, up: Vec3, margin: f32, t: &ShipCombat) -> (Vec3, f32, f32) {
    let d = dir.normalize_or(up);
    let flat = (d - up * d.dot(up)).normalize_or(d.any_orthonormal_vector());
    let room = ((margin - t.ai_floor) / (2.0 * t.ai_floor)).clamp(0.0, 1.0);
    let low = ((t.ai_floor - margin) / t.ai_floor).clamp(0.0, 1.0);
    let d = if low > 0.0 {
        (flat + up * low * 1.5).normalize()
    } else if -d.dot(up) > room {
        flat * (1.0 - room * room).sqrt() - up * room
    } else {
        d
    };
    (d, room, low)
}

/// After a break an enemy pilot opens out to this many times its break range before turning
/// back in, for this many seconds at most.
const EXTEND: f32 = 3.0;
const EXTEND_TIME: f32 = 6.0;

/// The steepest bank an enemy pilot takes at its floor, and with room to spare, radians.
const MIN_BANK: f32 = 0.45;
const MAX_BANK: f32 = 1.45;

/// The ship an enemy hunts: where it is and how it moves.
#[derive(Clone, Copy)]
struct Quarry {
    entity: Entity,
    at: Vec3,
    velocity: Vec3,
    faction: Faction,
}

/// One tick of every enemy pilot: what the ship it flies does next, written into its stick.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub(super) fn think(
    time: Res<Time>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    save: Option<Res<Save>>,
    bases: Query<(&Transform, &Base)>,
    targets: Query<(Entity, &Ship, &Position, &LinearVelocity, &Faction), Without<Enemy>>,
    mut enemies: Query<(&mut Enemy, &Ship, &Hull, &Faction, &Position, &Rotation, &LinearVelocity, &mut ShipControls, Option<&Missiles>)>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    // Only a ship someone flies is hunted: on foot the player is left alone.
    let quarry = targets.iter().find(|(_, s, ..)| s.pilot.is_some()).map(|(e, _, p, v, f)| Quarry { entity: e, at: p.0, velocity: v.0, faction: *f });
    for (mut enemy, ship, hull, faction, pos, rot, vel, mut controls, missiles) in &mut enemies {
        let spec = &specs.ship[ship.spec];
        let ai = &spec.ai;
        let (p, rot, v) = (pos.0, rot.0, vel.0);
        let fwd = rot * Vec3::NEG_Z;
        let body = origin.body(p);
        let up = surface.up(body);
        let home = match enemy.role {
            Role::Patrol { base, .. } => bases.iter().find(|(_, b)| b.spec == base).map(|(tf, _)| *tf),
            Role::Raider | Role::Hunter => None,
        };
        // A patrol takes on a ship that comes near its base and lets it go once it is well away.
        let engaged = enemy.mode != Mode::Patrol;
        let attacks = standing::attacks(&enemy, *faction, save.as_deref(), t);
        let foe = quarry.filter(|q| q.faction != *faction && attacks).filter(|q| match home {
            Some(base) => q.at.distance(base.translation) < if engaged { t.patrol_give_up } else { t.patrol_engage },
            None => true,
        });
        if ai.flee_hull > 0.0 && hull.hp <= ai.flee_hull * spec.hull && !enemy.fleeing {
            enemy.fleeing = true;
            enemy.mode = Mode::Break;
        }
        enemy.timer -= dt;
        let rel = foe.map_or(Vec3::ZERO, |f| f.at - p);
        let dist = rel.length();
        // It only boosts at a target ahead of it, never away from one behind.
        let ahead = fwd.angle_between(rel) < 0.8;
        enemy.mode = match (enemy.mode, foe) {
            _ if enemy.fleeing => Mode::Break,
            (_, None) => Mode::Patrol,
            // The turn, then out to a few times its break range before it turns back in (a few
            // seconds at most, if the target keeps after it).
            (Mode::Break, _) if enemy.timer > 0.0 || (dist < ai.break_range * EXTEND && enemy.timer > -EXTEND_TIME) => Mode::Break,
            (Mode::Patrol | Mode::Break, _) => Mode::Pursue,
            (Mode::Pursue, _) if dist < ai.attack_range => Mode::Attack,
            (Mode::Attack, _) if dist < ai.break_range => {
                enemy.timer = ai.break_time * (0.8 + 0.4 * enemy.quirk);
                enemy.side = -enemy.side;
                Mode::Break
            }
            (Mode::Attack, _) if dist > ai.attack_range * 1.3 => Mode::Pursue,
            (mode, _) => mode,
        };
        // Let go, the fight is over: a shot next time is a new one.
        if engaged && enemy.mode == Mode::Patrol {
            enemy.provoked = false;
        }

        let mut fire = false;
        let mut missile = false;
        // With a missile to hand, a hull that flies with them points straight at the target to
        // lock it instead of at the guns' lead.
        let homing = ai.missiles && missiles.is_some_and(|m| m.count > 0);
        let mut boost = false;
        let mut thrust = 1.0;
        let mut pull = 1.0;
        let dir = match (enemy.mode, foe) {
            (Mode::Patrol, _) => {
                thrust = 0.6;
                match home {
                    // Round the base, a little ahead of where it is on the loop, at patrol height.
                    Some(base) => {
                        let bup = base.rotation * Vec3::Y;
                        let out = p - base.translation;
                        let flat = (out - bup * out.dot(bup)).normalize_or(base.rotation * Vec3::X);
                        let next = Quat::from_axis_angle(bup, 0.4) * flat;
                        base.translation + next * t.patrol_radius + bup * t.patrol_altitude - p
                    }
                    // A raider with no one to hunt flies on, level, until it is out of range.
                    None => (fwd - up * fwd.dot(up)).normalize_or(fwd),
                }
            }
            (Mode::Pursue, Some(f)) => {
                // At where the target will be by the time it is reached, a few seconds at most, and
                // swinging wide to one side so a pack comes in from several.
                let closing = (v - f.velocity).dot(rel / dist.max(1.0)).max(150.0);
                boost = dist > ai.boost_range && ahead;
                let wide = rel.cross(up).normalize_or_zero() * (enemy.quirk * 2.0 - 1.0) * dist.min(1500.0) * 0.3;
                rel + f.velocity * (dist / closing).min(4.0) + wide
            }
            (Mode::Attack, Some(f)) => {
                let aim = lead(rel, f.velocity - v, t.gun_speed);
                // The aim wanders across the lead and back, up to `wobble` off, the way it swings
                // turning slowly round.
                let round = time.elapsed_secs() * 0.5 + enemy.quirk * std::f32::consts::TAU;
                let across = aim.cross(up).normalize_or(rot * Vec3::X);
                let swing = across * round.cos() + across.cross(aim).normalize_or(up) * round.sin();
                let aim = aim + swing * (round * 3.7).sin() * aim.length() * ai.wobble.to_radians();
                fire = dist < ai.attack_range && fwd.angle_between(aim) < ai.cone.to_radians();
                // A rusher keeps the throttle open; the others close at a speed that brings them to
                // `hold` in a couple of seconds, backing off when nearer.
                let closing = -(f.velocity - v).dot(rel / dist.max(1.0));
                if ai.hold > 0.0 {
                    thrust = ((dist - ai.hold) * 0.5 - closing).clamp(-30.0, 30.0) / 30.0;
                }
                // Well short of its range and not gaining, it boosts to catch up.
                boost = closing < 30.0 && dist > ai.hold.max(ai.break_range) * 3.0 && ahead;
                if homing {
                    missile = missiles.is_some_and(|m| m.locked() == Some(f.entity) && m.since >= t.ai_missile_gap);
                    rel
                } else {
                    aim
                }
            }
            (Mode::Break, f) => {
                if enemy.fleeing {
                    boost = true;
                    f.map_or(fwd, |_| -rel) + up * dist.max(1.0) * 0.2
                } else if enemy.timer > 0.0 {
                    pull = ai.break_turn;
                    let side = rel.cross(up).normalize_or(rot * Vec3::X) * enemy.side;
                    fwd * 0.3 + side + up * 0.3
                } else {
                    -rel.normalize_or(fwd) + up * 0.1
                }
            }
            (_, None) => fwd,
        };
        // Near its floor the lift engines hold it up too, and under it they climb; it never backs
        // down onto the ground.
        // Less what it would sink while its lift engines stop the descent.
        let sink = (-v.dot(up)).max(0.0);
        let margin = margin(p, v, t, |w| clearance(&solar, &surface, origin.body(w))) - sink * sink / (2.0 * spec.lift);
        let (dir, room, low) = avoid_ground(dir, up, margin, t);
        let bank = MIN_BANK + (MAX_BANK - MIN_BANK) * room;
        controls.thrust = if low > 0.0 { thrust.max(0.0) } else { thrust };
        let sinking = (sink / 30.0).min(1.0) * (1.0 - room);
        controls.lift = ((low * 2.0 + sinking) * (rot * Vec3::Y).dot(up)).clamp(-1.0, 1.0);
        controls.turn = steer(rot, dir, up, spec.rates, bank, &mut enemy.trim, dt) * pull;
        // Near the ground it keeps its speed down: a heavy hull cannot pull out of a fast dive.
        controls.boost = boost && room >= 1.0;
        controls.fire = fire;
        controls.missile = missile;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_lead_meets_a_crossing_target() {
        let (rel, rel_v, speed) = (Vec3::new(0.0, 0.0, -1000.0), Vec3::new(200.0, 0.0, 0.0), 1200.0);
        let aim = lead(rel, rel_v, speed);
        let t = aim.length() / speed;
        assert!((rel + rel_v * t).distance(aim) < 0.5, "the shot and the target meet");
        assert!(aim.x > 100.0, "aimed ahead of it: {aim}");
        // Nothing to catch: straight at it.
        assert_eq!(lead(rel, Vec3::new(0.0, 0.0, -2000.0), speed), rel);
    }

    #[test]
    fn the_stick_turns_the_nose_toward_the_target() {
        let rates = [2.0, 1.5, 3.0];
        let mut trim = Vec2::ZERO;
        let s = steer(Quat::IDENTITY, Vec3::new(0.0, 0.05, -1.0), Vec3::Y, rates, MAX_BANK, &mut trim, 0.0);
        assert!(s.x > 0.0 && s.y.abs() < 1e-4 && s.z.abs() < 1e-4, "a little above: pitch up, {s}");
        let s = steer(Quat::IDENTITY, Vec3::new(-0.05, 0.0, -1.0), Vec3::Y, rates, MAX_BANK, &mut trim, 0.0);
        assert!(s.y > 0.0, "a little to the left: yaw left, {s}");
        let s = steer(Quat::IDENTITY, Vec3::new(-1.0, 0.0, -0.2), Vec3::Y, rates, MAX_BANK, &mut trim, 0.0);
        assert!(s.z > 0.5, "well off to the left: roll left to pull round, {s}");
        // Behind and a little below, near the ground: no rolling over into a split-S.
        let level = Quat::from_rotation_z(1.2);
        let s = steer(level, Vec3::new(0.0, -0.1, 1.0), Vec3::Y, rates, 1.3, &mut trim, 0.0);
        assert!(s.z <= 0.15 && s.x > 0.5, "banked 69 degrees it rolls no further than 75, and pulls round: {s}");
        // Never upside down: rolled over, it rolls back.
        let s = steer(Quat::from_rotation_z(2.8), Vec3::new(1.0, 0.0, 0.0), Vec3::Y, rates, MAX_BANK, &mut trim, 0.0);
        assert!(s.z < -0.5, "rolled over to the left, it rolls right: {s}");
        // Held a little off, the pull grows until it gets there.
        let first = steer(Quat::IDENTITY, Vec3::new(0.0, 0.02, -1.0), Vec3::Y, rates, MAX_BANK, &mut trim, 0.1).x;
        for _ in 0..10 {
            steer(Quat::IDENTITY, Vec3::new(0.0, 0.02, -1.0), Vec3::Y, rates, MAX_BANK, &mut trim, 0.1);
        }
        assert!(steer(Quat::IDENTITY, Vec3::new(0.0, 0.02, -1.0), Vec3::Y, rates, MAX_BANK, &mut trim, 0.1).x > first * 2.0, "the trim builds");
    }

    #[test]
    fn low_down_the_heading_never_points_at_the_ground() {
        let t = ShipCombat::default();
        let down = Vec3::new(0.0, -1.0, -1.0).normalize();
        // Over flat ground at 0 m: the lowest point ahead counts.
        let flat = |p: Vec3| p.y;
        assert_eq!(margin(Vec3::Y * 500.0, Vec3::new(0.0, -50.0, 100.0), &t, flat), 500.0 - 50.0 * t.ai_lookahead);
        assert_eq!(margin(Vec3::Y * 5000.0, Vec3::new(0.0, -100.0, 400.0), &t, flat), 5000.0 - 100.0 * t.ai_lookahead * 400.0f32.hypot(100.0) / 200.0, "faster, it looks further");
        let (d, room, low) = avoid_ground(down, Vec3::Y, 2000.0, &t);
        assert!(d.distance(down) < 1e-5 && room == 1.0 && low == 0.0, "high up it is left alone");
        let (d, _, low) = avoid_ground(down, Vec3::Y, t.ai_floor * 2.0, &t);
        assert!(d.y < 0.0 && d.y > down.y && low == 0.0, "nearer the floor it dives less steeply: {d}");
        assert!(avoid_ground(down, Vec3::Y, t.ai_floor, &t).0.y.abs() < 1e-5, "at the floor it holds level");
        let (d, _, low) = avoid_ground(down, Vec3::Y, 20.0, &t);
        assert!(d.y > 0.5 && low > 0.8, "near the ground: it climbs hard, {d} {low}");
    }
}
