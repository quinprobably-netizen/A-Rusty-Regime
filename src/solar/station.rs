//! What each base is for. A base lists its stations in `assets/bases.toml`; each is a spot in the
//! building where E does one job, paid for from the banked money in the save:
//!
//! - the Roost's quartermaster resupplies you (health and ammunition, free) and opens the counter
//!   where guns and attachments are bought (`menu.rs`); its locker opens the wardrobe;
//! - the Yard's tuning rig upgrades the Kestrel's engines, three levels, and its parts rack opens
//!   the parts menu (`Panel::Parts`), where scrap buys hull plating, a shield cell, a gun
//!   capacitor and a missile rack (`salvage`);
//! - every base has a job board just inside its door (`board`), and Site Vantage's courier desk
//!   is one too: E opens it (`Panel::Board`) to take courier, cull and supply jobs;
//! - the Reliquary's shrine sells a blessing: more health for a while.
//!
//! Your standing with a base's faction (`standing`) sets its prices, in money or scrap: 15% off to a friend, 15% on
//! below -40, and at -60 or below it will not serve you at all, but for the courier desk, which
//! always hands out work (contracts are the income you climb back with). A parcel delivered to a friend's
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
use crate::menu::{Counter, Rack, Screen};
use crate::tuning::Tuning;
use crate::vehicle::{Driving, VehicleSet};
use crate::wardrobe::Wardrobe;
use crate::weapon::Arsenal;

/// How close to a station E reaches it, metres.
pub const REACH: f32 = 2.8;
/// A parcel is delivered this close to the destination's doorway, metres.
pub const DELIVER_RADIUS: f32 = 12.0;
/// How long the shrine's blessing lasts and how much health it adds (its tithe and the tuning
/// rig's levels are in `[economy]`).
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
    Parts,
    Contracts,
    Shrine,
    /// A job board: every base has one inside its door (spawned in `base`, not in `bases.toml`).
    Board,
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

pub use super::board::Contract;

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
    pub fn say(&mut self, text: impl Into<String>) {
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
    counter: Option<(ResMut<Counter>, ResMut<Rack>, ResMut<NextState<Screen>>)>,
    board: Option<ResMut<crate::menu::Board>>,
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
    let at_board = matches!(station.kind, StationKind::Contracts | StationKind::Board);
    if standing::hunted(&save, faction, t) && !at_board {
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
            if let Some((mut counter, _, mut next)) = counter {
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
            match tuning.economy.tune.get(level).map(|c| standing::price(*c, faction, &save, t)) {
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
        // The parts menu, priced by this base's faction.
        StationKind::Parts => match counter {
            Some((_, mut rack, mut next)) => {
                rack.0 = Some(faction);
                next.set(Screen::Paused);
            }
            None => prompt.say("The parts rack is locked"),
        },
        StationKind::Contracts | StationKind::Board => match (board, counter) {
            (Some(mut board), Some((_, _, mut next))) => {
                board.0 = Some((bases.base[station.base].id.clone(), faction));
                next.set(Screen::Paused);
            }
            _ => prompt.say("The board is bare"),
        },
        StationKind::Shrine => {
            let tithe = standing::price(tuning.economy.tithe, faction, &save, t);
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
pub(super) fn deliver(
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
    if driving {
        return;
    }
    // At a door with a parcel for it: every parcel for this base is delivered.
    let Some((_, base)) = placed.iter().find(|(at, b)| {
        let door = at.translation() + at.rotation() * Vec3::from(bases.base[b.spec].door);
        door.distance(tf.translation) < DELIVER_RADIUS && save.contracts.iter().any(|c| c.parcel_for() == Some(bases.base[b.spec].id.as_str()))
    }) else {
        return;
    };
    let id = bases.base[base.spec].id.clone();
    let faction = faction_of(&bases, base.spec);
    let (here, kept): (Vec<Contract>, Vec<Contract>) = std::mem::take(&mut save.contracts).into_iter().partition(|c| c.parcel_for() == Some(id.as_str()));
    save.contracts = kept;
    let name = &bases.base[base.spec].name;
    for c in here {
        let extra = standing::bonus(c.pay, faction, &save, &tuning.ship_combat);
        save.banked += c.pay + extra;
        save.contracts_done += 1;
        prompt.say(if extra > 0 { format!("Delivered to {name}: +${} and ${extra} for your standing", c.pay) } else { format!("Delivered to {name}: +${}", c.pay) });
        delivered.write(Delivered { faction });
    }
    file.write(&save);
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
                kind if !matches!(kind, StationKind::Contracts | StationKind::Board) && standing::hunted(&save, faction, t) => format!("the {} will not serve you (Hostile)", faction.name()),
                StationKind::Resupply => "resupply free, buy guns and attachments".to_string(),
                StationKind::Locker => "change clothes".to_string(),
                StationKind::Workshop => match tuning.economy.tune.get(save.ship_level as usize) {
                    Some(cost) => format!("tune the Kestrel to Mk{}, ${}{note}", save.ship_level + 1, standing::price(*cost, faction, &save, t)),
                    None => "the Kestrel is fully tuned".to_string(),
                },
                StationKind::Parts => format!("fit parts to the Kestrel for scrap ({} scrap){note}", save.scrap),
                StationKind::Contracts | StationKind::Board => {
                    let offers = save.boards.get(&bases.base[s.base].id).map_or(0, |b| b.len());
                    format!("job board, {offers} offers, {} of {} jobs carried", save.contracts.len(), tuning.economy.jobs)
                }
                StationKind::Shrine if blessing.0 > 0.0 => format!("blessed, {:.0} s left", blessing.0),
                StationKind::Shrine => format!("tithe ${}{note} for a blessing", standing::price(tuning.economy.tithe, faction, &save, t)),
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
    fn each_tuning_level_is_a_little_faster() {
        assert_eq!(tune(0), (1.0, 1.0));
        assert!(tune(3).0 > tune(2).0 && tune(3).1 > tune(2).1);
    }
}
