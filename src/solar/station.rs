//! What each base is for. A base lists its stations in `assets/bases.toml`; each is a spot in the
//! building where E does one job, paid for from the banked money in the save:
//!
//! - the Roost's quartermaster resupplies you (health and ammunition, free) and opens the counter
//!   where guns and attachments are bought (`menu.rs`); its locker opens the wardrobe;
//! - the Yard's tuning rig upgrades the Kestrel's engines, three levels;
//! - Site Vantage's courier desk hands out contracts: carry the parcel to another base's door and
//!   it pays out (the only income in the system, so everything else is paid for with it);
//! - the Reliquary's shrine sells a blessing: more health for a while.
//!
//! Your standing with a base's faction (`standing`) sets its prices: 15% off to a friend, 15% on
//! below -40, and at -60 or below it will not serve you at all. A parcel delivered to a friend's
//! base pays 20% more, and every delivery raises your standing there. The Roost is your own
//! side's and is never affected.

use bevy::prelude::*;
use serde::Deserialize;

use super::base::{Base, Bases};
use super::combat::Faction;
use super::ship;
use super::standing::{self, Delivered};
use crate::controller::Player;
use crate::health::PlayerHealth;
use crate::input::PlayerInput;
use crate::save::{Save, SaveFile};
use crate::menu::{Counter, Screen};
use crate::tuning::Tuning;
use crate::vehicle::{Driving, VehicleSet};
use crate::wardrobe::Wardrobe;
use crate::weapon::Arsenal;

/// How close to a station E reaches it, metres.
pub const REACH: f32 = 2.8;
/// A parcel is delivered this close to the destination's doorway, metres.
pub const DELIVER_RADIUS: f32 = 12.0;
/// What the tuning rig charges for each level, banked money.
pub const UPGRADE_COST: [u32; 3] = [300, 700, 1400];
/// What the shrine charges, how long the blessing lasts and how much health it adds.
pub const TITHE: u32 = 150;
pub const BLESSING_SECS: f32 = 300.0;
pub const BLESSING_HP: f32 = 50.0;
/// How long a message from a station stays on screen.
const NOTE_SECS: f32 = 4.0;

#[derive(Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum StationKind {
    Resupply,
    Locker,
    Workshop,
    Contracts,
    Shrine,
}

/// One station's place in the base frame, from `assets/bases.toml`.
#[derive(Deserialize, Clone, Debug)]
pub struct StationSpec {
    pub kind: StationKind,
    pub at: [f32; 3],
    pub label: String,
}

/// A station standing in a base: a child of the base entity, so it goes with it.
#[derive(Component)]
pub struct Station {
    pub base: usize,
    pub kind: StationKind,
    pub label: String,
}

/// The courier job you carry, saved: the destination's base id and what it pays.
#[derive(serde::Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct Contract {
    pub to: String,
    pub pay: u32,
}

/// Seconds of blessing left.
#[derive(Resource, Default)]
pub struct Blessing(pub f32);

/// What to show over the HUD: the station in reach, and the last thing a station said.
#[derive(Resource, Default)]
pub struct Prompt {
    pub line: String,
    note: String,
    note_left: f32,
}

impl Prompt {
    fn say(&mut self, text: impl Into<String>) {
        self.note = text.into();
        self.note_left = NOTE_SECS;
    }

    /// The lines the flight HUD adds.
    pub fn text(&self) -> String {
        let mut out = String::new();
        for l in [self.line.as_str(), if self.note_left > 0.0 { self.note.as_str() } else { "" }] {
            if !l.is_empty() {
                out.push('\n');
                out.push_str(l);
            }
        }
        out
    }
}

/// Engine boost for a tuning level: thrust and speed, and a little sharper turning.
pub fn tune(level: u8) -> (f32, f32) {
    (1.0 + 0.12 * level as f32, 1.0 + 0.05 * level as f32)
}

/// The contract the courier desk at base `from` offers after `done` deliveries: another base, a
/// different one each time round, paying more the longer the trip.
pub fn offer(bases: &Bases, from: usize, done: u32) -> Option<Contract> {
    let others: Vec<&str> = bases.base.iter().enumerate().filter(|(i, _)| *i != from).map(|(_, b)| b.id.as_str()).collect();
    let to = others.get(done as usize % others.len().max(1))?;
    Some(Contract { to: to.to_string(), pay: 250 + 150 * (done % 3) })
}

pub fn build(app: &mut App) {
    app.init_resource::<Blessing>()
        .init_resource::<Prompt>()
        .add_systems(FixedUpdate, (use_station.before(ship::board).before(VehicleSet), deliver, bless.after(crate::health::tick)).chain())
        .add_systems(Update, nearby);
}

/// The faction whose base `base` (an index into `Bases`) is.
fn faction_of(bases: &Bases, base: usize) -> Faction {
    bases.base.get(base).and_then(|b| Faction::from_id(&b.faction)).unwrap_or_default()
}

fn nearest<'a>(at: Vec3, stations: &'a Query<(&Station, &GlobalTransform)>) -> Option<&'a Station> {
    stations.iter().map(|(s, tf)| (s, tf.translation().distance(at))).filter(|(_, d)| *d < REACH).min_by(|a, b| a.1.total_cmp(&b.1)).map(|(s, _)| s)
}

/// E at a station does its job and uses the press up, so the ship and the wardrobe do not also see it.
#[allow(clippy::too_many_arguments)]
fn use_station(
    mut input: ResMut<PlayerInput>,
    bases: Res<Bases>,
    tuning: Res<Tuning>,
    file: Res<SaveFile>,
    mut save: ResMut<Save>,
    mut health: ResMut<PlayerHealth>,
    mut arsenal: ResMut<Arsenal>,
    mut blessing: ResMut<Blessing>,
    wardrobe: Option<ResMut<Wardrobe>>,
    mut prompt: ResMut<Prompt>,
    counter: Option<(ResMut<Counter>, ResMut<NextState<Screen>>)>,
    player: Single<(&Transform, Has<Driving>), With<Player>>,
    stations: Query<(&Station, &GlobalTransform)>,
) {
    if !input.interact_pressed {
        return;
    }
    let (tf, driving) = *player;
    if driving || !health.alive() || wardrobe.as_ref().is_some_and(|w| w.open) {
        return;
    }
    let Some(station) = nearest(tf.translation, &stations) else { return };
    input.interact_pressed = false;
    let t = &tuning.ship_combat;
    let faction = faction_of(&bases, station.base);
    if standing::hunted(&save, faction, t) {
        prompt.say(standing::refusal(faction));
        return;
    }
    match station.kind {
        StationKind::Resupply => {
            let topped = health.hp >= health.max && health.bleeding <= 0.0 && arsenal.spent.iter().all(|s| *s == 0);
            health.heal();
            arsenal.spent = Default::default();
            arsenal.reload = 0.0;
            prompt.say(if topped { "Nothing needed: you are topped off" } else { "Resupplied: health and ammunition" });
            if let Some((mut counter, mut next)) = counter {
                counter.0 = true;
                next.set(Screen::Paused);
            }
        }
        StationKind::Locker => match wardrobe {
            Some(mut w) => w.open = true,
            None => prompt.say("The locker is stuck"),
        },
        StationKind::Workshop => {
            let level = save.ship_level as usize;
            match UPGRADE_COST.get(level).map(|c| standing::price(*c, faction, &save, t)) {
                None => prompt.say("The Kestrel is tuned as far as it goes"),
                Some(cost) if save.banked < cost => prompt.say(format!("Engine tune Mk{} costs ${cost}: you have ${}", level + 1, save.banked)),
                Some(cost) => {
                    save.banked -= cost;
                    save.ship_level += 1;
                    file.write(&save);
                    prompt.say(format!("Engines tuned to Mk{}", save.ship_level));
                }
            }
        }
        StationKind::Contracts => {
            if let Some(c) = &save.contract {
                let to = bases.base.iter().find(|b| b.id == c.to).map_or("its destination", |b| b.name.as_str());
                prompt.say(format!("You are already carrying a parcel for {to}"));
            } else if let Some(c) = offer(&bases, station.base, save.contracts_done) {
                let to = bases.base.iter().find(|b| b.id == c.to).map_or("?", |b| b.name.as_str()).to_string();
                prompt.say(format!("Parcel for {to}: it pays ${} on delivery", c.pay));
                save.contract = Some(c);
                file.write(&save);
            }
        }
        StationKind::Shrine => {
            let tithe = standing::price(TITHE, faction, &save, t);
            if save.banked < tithe {
                prompt.say(format!("The tithe is ${tithe}: you have ${}", save.banked));
            } else {
                save.banked -= tithe;
                file.write(&save);
                blessing.0 = BLESSING_SECS;
                health.bleeding = 0.0;
                health.hp = health.max + BLESSING_HP;
                prompt.say(format!("Blessed: +{BLESSING_HP:.0} health for {:.0} minutes", BLESSING_SECS / 60.0));
            }
        }
    }
}

/// Walk up to the destination's doorway with the parcel and it pays out, more to a friend.
#[allow(clippy::too_many_arguments)]
fn deliver(
    time: Res<Time>,
    bases: Res<Bases>,
    tuning: Res<Tuning>,
    file: Res<SaveFile>,
    mut save: ResMut<Save>,
    mut prompt: ResMut<Prompt>,
    mut delivered: MessageWriter<Delivered>,
    player: Single<(&Transform, Has<Driving>), With<Player>>,
    placed: Query<(&GlobalTransform, &Base)>,
) {
    prompt.note_left -= time.delta_secs();
    let (tf, driving) = *player;
    let Some(c) = save.contract.clone().filter(|_| !driving) else { return };
    let Some((at, base)) = placed.iter().find(|(_, b)| bases.base[b.spec].id == c.to) else { return };
    let door = at.translation() + at.rotation() * Vec3::from(bases.base[base.spec].door);
    if door.distance(tf.translation) < DELIVER_RADIUS {
        let faction = faction_of(&bases, base.spec);
        let extra = standing::bonus(c.pay, faction, &save, &tuning.ship_combat);
        save.banked += c.pay + extra;
        save.contracts_done += 1;
        save.contract = None;
        file.write(&save);
        let name = &bases.base[base.spec].name;
        prompt.say(if extra > 0 { format!("Delivered to {name}: +${} and ${extra} for your standing", c.pay) } else { format!("Delivered to {name}: +${}", c.pay) });
        delivered.write(Delivered { faction });
    }
}

/// Runs the blessing down; while it lasts the health bar is that much longer.
fn bless(time: Res<Time>, mut blessing: ResMut<Blessing>, mut health: ResMut<PlayerHealth>) {
    if blessing.0 > 0.0 {
        blessing.0 = (blessing.0 - time.delta_secs()).max(0.0);
        health.max += BLESSING_HP;
    } else {
        health.hp = health.hp.min(health.max);
    }
}

/// The prompt for the station in reach.
#[allow(clippy::too_many_arguments)]
fn nearby(
    bases: Res<Bases>,
    tuning: Res<Tuning>,
    save: Res<Save>,
    blessing: Res<Blessing>,
    mut prompt: ResMut<Prompt>,
    player: Single<(&Transform, Has<Driving>), With<Player>>,
    stations: Query<(&Station, &GlobalTransform)>,
    actions: Option<Res<crate::controls::ActionState>>,
) {
    let (tf, driving) = *player;
    let pad = actions.is_some_and(|a| a.pad_last);
    let line = match nearest(tf.translation, &stations).filter(|_| !driving) {
        None => String::new(),
        Some(s) => {
            let t = &tuning.ship_combat;
            let faction = faction_of(&bases, s.base);
            let note = standing::price_note(faction, &save, t);
            let what = match s.kind {
                _ if standing::hunted(&save, faction, t) => format!("the {} will not serve you (Hostile)", faction.name()),
                StationKind::Resupply => "resupply free, buy guns and attachments".to_string(),
                StationKind::Locker => "change clothes".to_string(),
                StationKind::Workshop => match UPGRADE_COST.get(save.ship_level as usize) {
                    Some(cost) => format!("tune the Kestrel to Mk{}, ${}{note}", save.ship_level + 1, standing::price(*cost, faction, &save, t)),
                    None => "the Kestrel is fully tuned".to_string(),
                },
                StationKind::Contracts => match &save.contract {
                    Some(c) => format!("carrying a parcel for {}", bases.base.iter().find(|b| b.id == c.to).map_or("?", |b| b.name.as_str())),
                    None => "take a courier contract".to_string(),
                },
                StationKind::Shrine if blessing.0 > 0.0 => format!("blessed, {:.0} s left", blessing.0),
                StationKind::Shrine => format!("tithe ${}{note} for a blessing", standing::price(TITHE, faction, &save, t)),
            };
            format!("[{}] {}: {what}", crate::controls::hint(crate::controls::Ctx::Foot, crate::controls::Action::Use, pad), s.label)
        }
    };
    if prompt.line != line {
        prompt.line = line;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contracts_visit_every_other_base_in_turn_and_pay_more_for_the_far_ones() {
        let bases = Bases::load();
        let vantage = bases.base.iter().position(|b| b.id == "outpost").unwrap();
        let trips: Vec<Contract> = (0..3).map(|n| offer(&bases, vantage, n).unwrap()).collect();
        let mut to: Vec<&str> = trips.iter().map(|c| c.to.as_str()).collect();
        to.sort();
        assert_eq!(to, ["reliquary", "roost", "yard"]);
        assert!(trips.windows(2).all(|w| w[1].pay > w[0].pay));
        assert_eq!(offer(&bases, vantage, 3).unwrap().to, trips[0].to, "round again");
    }

    #[test]
    fn each_tuning_level_is_a_little_faster() {
        assert_eq!(tune(0), (1.0, 1.0));
        assert!(tune(3).0 > tune(2).0 && tune(3).1 > tune(2).1);
    }
}
