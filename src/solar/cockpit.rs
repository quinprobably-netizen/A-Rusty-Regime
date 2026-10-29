//! What the cockpit tells the pilot of a fight (section 11 of
//! `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`). Each tick it fills
//! `FlightHud::fight` from the ship the player flies (hull, shield, gun heat, missiles, the lock,
//! the hit marker and an enemy missile coming for it), and writes a `Cue` for each sound of the
//! fight for `sound` to play.
//!
//! Sound does not carry in vacuum: what happens outside the ship (other ships' guns and
//! launches, wrecks, missile bursts) is heard as loud as the air at the listener lets it, and
//! quieter with distance. What happens in the cockpit (your own guns and launches, hits on your
//! hull, the lock tone and the missile warning) is always heard.

use std::collections::HashMap;

use bevy::prelude::*;

use super::combat::{wreck, Faction, Gun, Hull, Projectile, ShipDestroyed, ShotLanded};
use super::missile::{Missile, Missiles};
use super::salvage::Refit;
use super::ship::{Autopilot, Ship, Ships};
use super::Solar;
use crate::controller::Player;
use crate::hud::{FlightHud, Threat};
use crate::surface::{Origin, Surface};
use crate::tuning::Tuning;

/// How long the hit marker shows, and the kill marker, seconds.
pub const HIT_MARK: f32 = 0.25;
pub const KILL_MARK: f32 = 0.6;
/// How far off each sound is still half as loud as close by, metres, and past where it is not
/// heard at all.
const GUN_NEAR: f32 = 150.0;
const GUN_FAR: f32 = 2500.0;
const BOOM_NEAR: f32 = 400.0;
const BOOM_FAR: f32 = 6000.0;
/// A missile bursting this close to your ship is felt through the hull, air or not.
const ON_HULL: f32 = 30.0;
/// Seconds between missile warning chirps: an enemy holding a lock on you, a missile in the air.
const WARN_LOCKED: f32 = 0.6;
const WARN_MISSILE: f32 = 0.22;

/// A sound of the fight, for `sound` to play. `volume` is 0 to 1 of its full level, distance and
/// air already counted; `pitch` is a playback speed.
#[derive(Message, Debug, Clone, Copy, PartialEq)]
pub struct Cue {
    pub sfx: Sfx,
    pub volume: f32,
    pub pitch: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Sfx {
    /// A nose gun's shot.
    Gun,
    /// A missile leaving its rail.
    Launch,
    /// A ship blown apart, and a missile bursting.
    Wreck,
    Burst,
    /// A hit on your own ship's shield, and one through to its hull.
    ShieldHit,
    HullHit,
    /// One beep of the lock coming on; it rises in pitch and quickens as the lock fills.
    LockBeep,
    /// An enemy's lock or missile on your ship.
    Warning,
    /// Salvage taken aboard (`salvage`): scrap, and a module new to you.
    Scrap,
    Module,
}

pub fn build(app: &mut App) {
    app.add_message::<Cue>().add_systems(FixedUpdate, (gauges, cues).chain().after(wreck));
}

/// How loud a sound `distance` metres off is, against close by: half at `near`, and `carry` of
/// that for the air it crosses.
pub fn heard(distance: f32, near: f32, carry: f32) -> f32 {
    carry * near / (near + distance.max(0.0))
}

/// How much of a sound the air at `at` (the anchor's frame) carries: all of it at sea level,
/// thinning with the air, none in vacuum.
pub fn carry(solar: &Solar, surface: &Surface, origin: &Origin, at: Vec3) -> f32 {
    let air = solar.anchor_body().air.as_ref().filter(|_| solar.anchor != super::orbit::STAR);
    air.map_or(0.0, |a| (a.density_at(surface.altitude(origin.body(at))) / 1.225).clamp(0.0, 1.0).sqrt())
}

/// Reads the ship the player flies into the HUD: hull, guns, missiles and lock, a marker for a
/// shot of its that lands (a bigger one for a kill), and whether an enemy's missile is on it.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn gauges(
    time: Res<Time>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    mut hud: ResMut<FlightHud>,
    mut landed: MessageReader<ShotLanded>,
    mut destroyed: MessageReader<ShipDestroyed>,
    ships: Query<(Entity, &Ship, &Hull, &Faction, Option<&Gun>, Option<&Missiles>, Option<&Refit>)>,
    hunters: Query<(&Ship, &Faction, &Missiles), With<Autopilot>>,
    in_flight: Query<&Missile>,
) {
    let fight = &mut hud.fight;
    fight.hit = (fight.hit - time.delta_secs()).max(0.0);
    let Some((me, _, hull, faction, gun, missiles, refit)) = ships.iter().find(|(_, s, ..)| s.pilot.is_some()) else {
        landed.clear();
        destroyed.clear();
        *fight = Default::default();
        return;
    };
    (fight.hull, fight.max_hull, fight.shield, fight.max_shield) = (hull.hp, hull.max_hp, hull.shield, hull.max_shield);
    (fight.heat, fight.overheated) = gun.map_or((0.0, false), |g| (g.heat.clamp(0.0, 1.0), g.overheated));
    let t = &tuning.ship_combat;
    let r = refit.copied().unwrap_or_default();
    match missiles {
        Some(m) => {
            (fight.missiles, fight.max_missiles) = (m.count, r.missiles(t));
            fight.reload = if m.count < r.missiles(t) { (m.reload / r.reload(t).max(1e-3)).clamp(0.0, 1.0) } else { 0.0 };
            fight.lock = if m.target.is_some() { m.lock } else { 0.0 };
        }
        None => (fight.missiles, fight.max_missiles, fight.reload, fight.lock) = (0, 0, 0.0, 0.0),
    }
    // A hit never replaces the kill marker while it shows.
    for shot in landed.read() {
        if shot.by == me && !(fight.kill && fight.hit > 0.0) {
            (fight.hit, fight.kill) = (HIT_MARK, false);
        }
    }
    for kill in destroyed.read() {
        if kill.killer == Some(me) && kill.ship != me {
            (fight.hit, fight.kill) = (KILL_MARK, true);
        }
    }
    // Only a hull that flies with missiles locking on counts: every pilot's nose "locks", but
    // only a Sentry ever fires.
    let incoming = in_flight.iter().any(|m| m.target == Some(me) && m.faction != *faction);
    let locked = hunters.iter().any(|(s, f, m)| f != faction && specs.ship[s.spec].ai.missiles && m.locked() == Some(me));
    fight.threat = if incoming { Threat::Missile } else if locked { Threat::Locked } else { Threat::None };
}

/// What `cues` remembers between ticks.
#[derive(Default)]
struct Heard {
    /// Where every ship and missile was last tick, for the ones gone this tick.
    ships: HashMap<Entity, Vec3>,
    missiles: HashMap<Entity, (Vec3, Entity)>,
    /// The flown ship's hull and shield last tick.
    hull: Option<(Entity, f32, f32)>,
    /// Seconds to the next lock beep and the next warning chirp.
    beep: f32,
    warn: f32,
}

/// Writes a `Cue` for each sound of the fight this tick, heard from where the player is.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn cues(
    time: Res<Time>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    hud: Res<FlightHud>,
    mut out: MessageWriter<Cue>,
    mut destroyed: MessageReader<ShipDestroyed>,
    player: Query<&Transform, With<Player>>,
    ships: Query<(Entity, &Ship, &Hull, &Transform)>,
    shots: Query<(&Projectile, &Transform), Added<Projectile>>,
    missiles: Query<(Entity, &Missile, &Transform)>,
    mut st: Local<Heard>,
) {
    let dt = time.delta_secs();
    let Ok(ear) = player.single().map(|tf| tf.translation) else { return };
    let air = carry(&solar, &surface, &origin, ear);
    let me = ships.iter().find(|(_, s, ..)| s.pilot.is_some());
    let mine = me.map(|(e, ..)| e);
    let mut cue = |sfx: Sfx, volume: f32, pitch: f32| {
        if volume > 0.005 {
            out.write(Cue { sfx, volume: volume.min(1.0), pitch });
        }
    };
    // Out there, as loud as the air and the distance let it be; from your own ship, always.
    let outside = |at: Vec3, near: f32, far: f32| {
        let d = at.distance(ear);
        if d > far { 0.0 } else { heard(d, near, air) }
    };

    for (shot, tf) in &shots {
        let own = Some(shot.owner) == mine;
        cue(Sfx::Gun, if own { 1.0 } else { outside(tf.translation, GUN_NEAR, GUN_FAR) }, if own { 1.0 } else { 0.92 });
    }
    for (e, m, tf) in &missiles {
        if st.missiles.insert(e, (tf.translation, m.owner)).is_none() {
            let own = Some(m.owner) == mine;
            cue(Sfx::Launch, if own { 1.0 } else { outside(tf.translation, GUN_NEAR, BOOM_FAR) }, 1.0);
        }
    }
    let gone: Vec<Entity> = st.missiles.keys().filter(|e| !missiles.contains(**e)).copied().collect();
    let hull_at = me.map(|(_, _, _, tf)| tf.translation);
    for e in gone {
        let Some((at, _)) = st.missiles.remove(&e) else { continue };
        let felt = hull_at.is_some_and(|h| h.distance(at) < ON_HULL);
        cue(Sfx::Burst, if felt { 0.8 } else { outside(at, BOOM_NEAR, BOOM_FAR) }, 1.0);
    }
    for kill in destroyed.read() {
        let volume = if Some(kill.ship) == mine || st.hull.is_some_and(|(e, ..)| e == kill.ship) { 1.0 } else { st.ships.get(&kill.ship).map_or(0.0, |at| outside(*at, BOOM_NEAR, BOOM_FAR)) };
        cue(Sfx::Wreck, volume, 0.7);
    }
    st.ships = ships.iter().map(|(e, _, _, tf)| (e, tf.translation)).collect();

    // Hits on your own ship: the shield's crackle, or the hull's clang once through it.
    match me {
        Some((e, _, hull, _)) => {
            if let Some((_, hp, shield)) = st.hull.filter(|(was, ..)| *was == e) {
                if hull.hp < hp {
                    cue(Sfx::HullHit, 1.0, 1.0);
                } else if hull.shield < shield - 0.01 {
                    cue(Sfx::ShieldHit, 1.0, 1.0);
                }
            }
            st.hull = Some((e, hull.hp, hull.shield));
        }
        None => st.hull = None,
    }

    // The lock tone: beeps that climb and quicken as the lock fills (once locked, `sound` holds
    // a steady tone); and the warning while an enemy's missile is on you.
    let fight = &hud.fight;
    let locking = me.is_some() && fight.lock > 0.0 && fight.lock < 1.0;
    st.beep = if locking { st.beep - dt } else { 0.0 };
    if locking && st.beep <= 0.0 {
        cue(Sfx::LockBeep, 1.0, 0.8 + 0.7 * fight.lock);
        st.beep = 0.24 - 0.14 * fight.lock;
    }
    let every = match fight.threat {
        _ if me.is_none() => 0.0,
        Threat::None => 0.0,
        Threat::Locked => WARN_LOCKED,
        Threat::Missile => WARN_MISSILE,
    };
    st.warn = if every > 0.0 { st.warn - dt } else { 0.0 };
    if every > 0.0 && st.warn <= 0.0 {
        cue(Sfx::Warning, 1.0, if fight.threat == Threat::Missile { 1.15 } else { 1.0 });
        st.warn = every;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sounds_fade_with_distance_and_thin_air() {
        assert_eq!(heard(0.0, 150.0, 1.0), 1.0);
        assert!((heard(150.0, 150.0, 1.0) - 0.5).abs() < 1e-6, "half as loud at `near`");
        assert!(heard(1000.0, 150.0, 1.0) < heard(500.0, 150.0, 1.0));
        assert_eq!(heard(10.0, 150.0, 0.0), 0.0, "nothing carries in vacuum");
    }
}
