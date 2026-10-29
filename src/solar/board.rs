//! Job boards (stage B of `docs/superpowers/specs/2026-10-29-economy-design.md`): every base has
//! a board just inside its door (and Site Vantage's courier desk is one too) with three offers a
//! game day, drawn from the save's seed so a day's board is the same however often you look.
//!
//! - **Courier:** carry a parcel to another base's door. Pays `courier_base` and `courier_per_km`
//!   for each km between the two worlds when the board went up, `danger_pay` times that if the
//!   destination's faction is hostile to you, into the bank on delivery (`station::deliver`).
//! - **Cull:** shoot down `need` raiders with the ship you fly. Pays `cull_per_kill` each, into
//!   the pocket on the last one, on top of each bounty.
//! - **Supply run:** bring `need` scrap back to this board. Pays a little over what the scrap
//!   sells for, into the bank. The Yard has its own stockpile (stage C) and offers none.
//!
//! You carry up to `[economy] jobs` at a time. A job taken today is due by the end of tomorrow;
//! after that it is gone, and a parcel never delivered costs `drop_standing` with whoever gave it
//! to you, as does a parcel lost with your ship (`loss`). A day is `[economy] day` seconds of
//! game time.

use std::collections::BTreeMap;

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

use super::base::Bases;
use super::combat::{Faction, ShipDestroyed};
use super::enemy::Rng;
use super::loss::BountyLine;
use super::ship::Ship;
use super::{standing, Solar};
use crate::save::{Save, SaveFile};
use crate::tuning::{Economy, ShipCombat, Tuning};

/// What a job asks of you.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Job {
    /// Carry a parcel to base `to`'s door.
    Courier { to: String },
    /// Shoot down `need` raiders; `got` so far.
    Cull { need: u32, got: u32 },
    /// Bring `need` scrap to the board that gave it.
    Supply { need: u32 },
}

/// A job on a board or in your hands, saved.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct Contract {
    pub job: Job,
    /// The base id whose board gave it.
    pub from: String,
    pub pay: u32,
    /// The last game day it can be done on; `None`, never due.
    pub due: Option<u32>,
}

impl Contract {
    /// The courier parcel's destination, if it is one.
    pub fn parcel_for(&self) -> Option<&str> {
        match &self.job {
            Job::Courier { to } => Some(to),
            _ => None,
        }
    }
}

/// Why a job was not taken.
#[derive(Debug, PartialEq, Eq)]
pub enum Refusal {
    /// You carry as many as you can.
    Full,
    /// Nothing in that slot.
    Gone,
}

pub fn build(app: &mut App) {
    // The boards go up even while paused (a board opened straight from the title, or a day that
    // turned under the menu); the clock and the culls run with the game.
    app.add_systems(FixedUpdate, (tick_day, cull.after(super::combat::wreck)).chain()).add_systems(Update, restock);
}

/// The faction of base `id`.
pub fn faction_of(bases: &Bases, id: &str) -> Faction {
    bases.base.iter().find(|b| b.id == id).and_then(|b| Faction::from_id(&b.faction)).unwrap_or_default()
}

/// The base's name for `id`, or the id.
pub fn name_of<'a>(bases: &'a Bases, id: &'a str) -> &'a str {
    bases.base.iter().find(|b| b.id == id).map_or(id, |b| b.name.as_str())
}

fn hash(seed: u64, day: u32, id: &str) -> u64 {
    let mut h = 0xcbf2_9ce4_8422_2325u64 ^ seed;
    for b in day.to_le_bytes().iter().chain(id.as_bytes()) {
        h = (h ^ *b as u64).wrapping_mul(0x0100_0000_01b3);
    }
    h | 1
}

/// The offers on base `base`'s board on game day `day`: a courier, a cull and, some days and
/// never at the Yard, a supply run. `km` is how far apart two bases' worlds are.
#[allow(clippy::too_many_arguments)]
pub fn offers(base: usize, bases: &Bases, day: u32, seed: u64, km: impl Fn(&str, &str) -> f32, save: &Save, e: &Economy, t: &ShipCombat) -> Vec<Contract> {
    let here = &bases.base[base];
    let mut rng = Rng(hash(seed, day, &here.id));
    let due = Some(day + 1);
    let mut out = Vec::new();
    let others: Vec<usize> = (0..bases.base.len()).filter(|i| *i != base).collect();
    if !others.is_empty() {
        let to = &bases.base[others[rng.range(0, others.len() - 1)]];
        let mut pay = e.courier_base as f32 + e.courier_per_km * km(&here.id, &to.id);
        if standing::hostile(save, faction_of(bases, &to.id), t) && standing::moves(faction_of(bases, &to.id)) {
            pay *= e.danger_pay;
        }
        let pay = ((pay / 10.0).round() * 10.0) as u32;
        out.push(Contract { job: Job::Courier { to: to.id.clone() }, from: here.id.clone(), pay, due });
    }
    let need = rng.range(e.cull_kills[0] as usize, e.cull_kills[1].max(e.cull_kills[0]) as usize) as u32;
    out.push(Contract { job: Job::Cull { need, got: 0 }, from: here.id.clone(), pay: e.cull_per_kill * need, due });
    let roll = rng.next();
    let stock = super::economy::yard_stock(save, e);
    if here.id == super::economy::YARD {
        // The Yard asks for scrap only when its stockpile runs low, and pays for the hurry.
        if stock < e.yard_shortage * e.yard_target {
            let need = rng.range(e.supply_scrap[0] as usize, e.supply_scrap[1].max(e.supply_scrap[0]) as usize) as u32;
            let pay = (super::economy::yard_price(stock, e) * e.supply_markup * e.shortage_pay * need as f32).round() as u32;
            out.push(Contract { job: Job::Supply { need }, from: here.id.clone(), pay, due });
        }
    } else if roll < e.supply_chance {
        let need = rng.range(e.supply_scrap[0] as usize, e.supply_scrap[1].max(e.supply_scrap[0]) as usize) as u32;
        let pay = (e.scrap_value as f32 * 0.7 * e.supply_markup * need as f32).round() as u32;
        out.push(Contract { job: Job::Supply { need }, from: here.id.clone(), pay, due });
    }
    out
}

/// Puts up every base's board for `save.day`.
pub fn restock_all(save: &mut Save, bases: &Bases, km: impl Fn(&str, &str) -> f32, e: &Economy, t: &ShipCombat) {
    let mut boards = BTreeMap::new();
    for (i, b) in bases.base.iter().enumerate() {
        boards.insert(b.id.clone(), offers(i, bases, save.day, save.seed, &km, save, e, t));
    }
    save.boards = boards;
    save.board_day = Some(save.day);
}

/// Takes offer `i` from base `base`'s board, if you have room for another job.
pub fn take(save: &mut Save, base: &str, i: usize, e: &Economy) -> Result<Contract, Refusal> {
    if save.contracts.len() >= e.jobs {
        return Err(Refusal::Full);
    }
    let Some(board) = save.boards.get_mut(base).filter(|b| i < b.len()) else { return Err(Refusal::Gone) };
    let c = board.remove(i);
    save.contracts.push(c.clone());
    Ok(c)
}

/// Hands in the first supply run given by base `base` if the hold has enough scrap: the scrap
/// goes, the pay is banked. Returns (scrap, pay).
pub fn hand_in(save: &mut Save, base: &str, e: &Economy) -> Option<(u32, u32)> {
    let i = save.contracts.iter().position(|c| c.from == base && matches!(c.job, Job::Supply { need } if save.scrap >= need))?;
    let c = save.contracts.remove(i);
    let Job::Supply { need } = c.job else { unreachable!() };
    save.scrap -= need;
    save.banked = save.banked.saturating_add(c.pay);
    // Scrap brought to the Yard goes on its stockpile.
    if base == super::economy::YARD {
        save.yard_stock = Some(super::economy::yard_stock(save, e) + need as f32);
    }
    Some((need, c.pay))
}

/// Drops `c`, a job you lost or let lapse: a parcel costs standing with whoever gave it.
pub fn dropped(save: &mut Save, c: &Contract, bases: &Bases, e: &Economy, t: &ShipCombat) -> i32 {
    if c.parcel_for().is_some() { standing::shift(save, faction_of(bases, &c.from), e.drop_standing, t) } else { 0 }
}

/// A job in a line, for the flight readout: `PARCEL for The Reliquary +$750`, `CULL 2/6 +$300`,
/// `SUPPLY 30 SCRAP to Site Vantage +$160`.
pub fn job_line(c: &Contract, bases: &Bases) -> String {
    match &c.job {
        Job::Courier { to } => format!("PARCEL for {} +${}", name_of(bases, to), c.pay),
        Job::Cull { need, got } => format!("CULL {got}/{need} +${}", c.pay),
        Job::Supply { need } => format!("SUPPLY {need} SCRAP to {} +${}", name_of(bases, &c.from), c.pay),
    }
}

/// What a base's marker adds for the jobs you carry: `DELIVER HERE +$750` for the parcels bound
/// for it, `HAND IN 30 SCRAP` for a supply run it gave you.
pub fn marker(save: &Save, base: &str) -> String {
    let mut out = String::new();
    let pay: u32 = save.contracts.iter().filter(|c| c.parcel_for() == Some(base)).map(|c| c.pay).sum();
    if pay > 0 {
        out.push_str(&format!("\nDELIVER HERE +${pay}"));
    }
    for c in save.contracts.iter().filter(|c| c.from == base) {
        if let Job::Supply { need } = c.job {
            out.push_str(&format!("\nHAND IN {need} SCRAP"));
        }
    }
    out
}

/// Jobs past their day are gone; returns them.
pub fn expire(save: &mut Save, bases: &Bases, e: &Economy, t: &ShipCombat) -> Vec<Contract> {
    let day = save.day;
    let (gone, kept): (Vec<Contract>, Vec<Contract>) = std::mem::take(&mut save.contracts).into_iter().partition(|c| c.due.is_some_and(|d| d < day));
    save.contracts = kept;
    for c in &gone {
        dropped(save, c, bases, e, t);
    }
    gone
}

/// A raider shot down by you: every cull counts it; the ones that are done pay into the pocket.
/// Returns what was paid.
pub fn raider_down(save: &mut Save) -> Vec<u32> {
    let mut paid = Vec::new();
    save.contracts.retain_mut(|c| {
        if let Job::Cull { need, got } = &mut c.job {
            *got += 1;
            if *got >= *need {
                paid.push(c.pay);
                return false;
            }
        }
        true
    });
    for p in &paid {
        save.pocket = save.pocket.saturating_add(*p);
    }
    paid
}

/// Game time moves the day on, and jobs past theirs lapse.
fn tick_day(time: Res<Time>, tuning: Res<Tuning>, bases: Res<Bases>, file: Res<SaveFile>, save: Option<ResMut<Save>>) {
    let Some(mut save) = save else { return };
    let e = &tuning.economy;
    save.day_clock += time.delta_secs();
    if save.day_clock < e.day.max(1.0) {
        return;
    }
    save.day_clock -= e.day.max(1.0);
    save.day += 1;
    let gone = expire(&mut save, &bases, e, &tuning.ship_combat);
    if !gone.is_empty() {
        info!("day {}: {} jobs lapsed", save.day, gone.len());
    }
    file.write(&save);
}

/// A new day puts up new boards, with the worlds where they are now.
fn restock(tuning: Res<Tuning>, bases: Res<Bases>, solar: Res<Solar>, file: Res<SaveFile>, save: Option<ResMut<Save>>) {
    let Some(mut save) = save else { return };
    if save.board_day == Some(save.day) {
        return;
    }
    if save.seed == 0 {
        save.seed = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(1, |d| d.as_nanos() as u64) | 1;
    }
    let km = |a: &str, b: &str| {
        let body = |id: &str| bases.base.iter().find(|x| x.id == id).map_or("home", |x| x.body.as_str()).to_string();
        let (pa, pb) = (solar.placement(&body(a)).0, solar.placement(&body(b)).0);
        pa.distance(pb) / 1000.0
    };
    restock_all(&mut save, &bases, km, &tuning.economy, &tuning.ship_combat);
    file.write(&save);
}

/// Raiders shot down by the ship you fly count toward your culls.
fn cull(mut destroyed: MessageReader<ShipDestroyed>, file: Res<SaveFile>, save: Option<ResMut<Save>>, mut line: ResMut<BountyLine>, tuning: Res<Tuning>, ships: Query<&Ship>) {
    let Some(mut save) = save else {
        destroyed.clear();
        return;
    };
    for kill in destroyed.read() {
        if kill.faction != Faction::Raiders || kill.killer.is_none_or(|k| k == kill.ship || !ships.get(k).is_ok_and(|s| s.pilot.is_some())) {
            continue;
        }
        if !save.contracts.iter().any(|c| matches!(c.job, Job::Cull { .. })) {
            continue;
        }
        let paid = raider_down(&mut save);
        file.write(&save);
        if let Some(total) = paid.iter().copied().reduce(|a, b| a + b) {
            line.text = format!("CULL DONE +${total}");
            line.left = tuning.ship_combat.bounty_line;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup() -> (Bases, Economy, ShipCombat) {
        (Bases::load(), Economy::default(), ShipCombat::default())
    }

    fn km(_: &str, _: &str) -> f32 {
        150.0
    }

    #[test]
    fn a_days_board_is_the_same_every_time_and_another_day_differs() {
        let (bases, e, t) = setup();
        let save = Save::default();
        let a = offers(0, &bases, 3, 77, km, &save, &e, &t);
        assert_eq!(a, offers(0, &bases, 3, 77, km, &save, &e, &t));
        let others: Vec<_> = (0..40).map(|d| offers(0, &bases, d, 77, km, &save, &e, &t)).collect();
        assert!(others.iter().any(|o| *o != a), "the days differ");
        assert!((0..40).any(|s| offers(0, &bases, 3, s, km, &save, &e, &t) != a), "and the seeds");
    }

    #[test]
    fn offers_follow_their_rules() {
        let (bases, e, t) = setup();
        let mut save = Save::default();
        let yard = bases.base.iter().position(|b| b.id == "yard").unwrap();
        let mut supplies = 0;
        for day in 0..60 {
            for base in 0..bases.base.len() {
                let o = offers(base, &bases, day, 5, km, &save, &e, &t);
                let id = &bases.base[base].id;
                assert!(o.iter().all(|c| c.from == *id && c.due == Some(day + 1)));
                let Job::Courier { to } = &o[0].job else { panic!("a courier first") };
                assert_ne!(to, id, "never to itself");
                let Job::Cull { need, got: 0 } = o[1].job else { panic!("a cull second") };
                assert!((4..=8).contains(&need) && o[1].pay == 50 * need);
                if let Some(c) = o.get(2) {
                    assert_ne!(base, yard, "the Yard, full, asks for none");
                    let Job::Supply { need } = c.job else { panic!() };
                    assert!((20..=40).contains(&need));
                    assert_eq!(c.pay, (6.0 * 0.7 * 1.3 * need as f32).round() as u32);
                    supplies += 1;
                }
            }
        }
        assert!(supplies > 40 && supplies < 140, "about half the days at three bases: {supplies}");
        // To a friendly or neutral faction a 150 km run pays 250 + 450; to a hostile one half again.
        save.standing.insert("regime".into(), 10);
        save.standing.insert("pmc".into(), 10);
        let calm = (0..20).flat_map(|d| offers(0, &bases, d, 9, km, &save, &e, &t)).find(|c| c.parcel_for().is_some()).unwrap();
        assert_eq!(calm.pay, 700);
        save.standing.insert("regime".into(), -10);
        save.standing.insert("pmc".into(), -10);
        save.standing.insert("scrappers".into(), -10);
        let hot = (0..20).flat_map(|d| offers(0, &bases, d, 9, km, &save, &e, &t)).find(|c| c.parcel_for().is_some_and(|to| to != "roost")).unwrap();
        assert_eq!(hot.pay, 1050);
    }

    #[test]
    fn two_jobs_at_most_and_a_taken_offer_leaves_the_board() {
        let (bases, e, t) = setup();
        let mut save = Save { seed: 3, ..default() };
        restock_all(&mut save, &bases, km, &e, &t);
        let n = save.boards["roost"].len();
        let first = save.boards["roost"][0].clone();
        assert_eq!(take(&mut save, "roost", 0, &e), Ok(first.clone()));
        assert_eq!((save.contracts.len(), save.boards["roost"].len()), (1, n - 1));
        assert!(take(&mut save, "outpost", 0, &e).is_ok());
        let left = save.boards["yard"].clone();
        assert_eq!(take(&mut save, "yard", 0, &e), Err(Refusal::Full));
        assert_eq!(save.boards["yard"], left, "still there");
        save.contracts.clear();
        assert_eq!(take(&mut save, "yard", 9, &e), Err(Refusal::Gone));
    }

    #[test]
    fn the_yard_asks_for_scrap_only_when_its_stock_runs_low() {
        let (bases, e, t) = setup();
        let yard = bases.base.iter().position(|b| b.id == "yard").unwrap();
        let full = Save::default();
        assert!((0..20).all(|d| offers(yard, &bases, d, 1, km, &full, &e, &t).len() == 2), "none at full stock");
        let low = Save { yard_stock: Some(100.0), ..default() };
        let o = offers(yard, &bases, 4, 1, km, &low, &e, &t);
        let Job::Supply { need } = o[2].job else { panic!("a supply run") };
        let price = crate::solar::economy::yard_price(100.0, &e);
        assert_eq!(o[2].pay, (price * 1.3 * 1.6 * need as f32).round() as u32, "at the premium");
        let mut save = Save { scrap: need, yard_stock: Some(100.0), contracts: vec![o[2].clone()], ..default() };
        assert!(hand_in(&mut save, "yard", &e).is_some());
        assert_eq!(save.yard_stock, Some(100.0 + need as f32), "the scrap goes on the stockpile");
    }

    #[test]
    fn a_supply_run_hands_in_only_with_the_scrap_aboard() {
        let mut save = Save { scrap: 20, banked: 1, ..default() };
        save.contracts.push(Contract { job: Job::Supply { need: 30 }, from: "outpost".into(), pay: 160, due: Some(1) });
        assert_eq!(hand_in(&mut save, "outpost", &Economy::default()), None);
        assert_eq!((save.scrap, save.contracts.len()), (20, 1), "nothing taken");
        save.scrap = 35;
        assert_eq!(hand_in(&mut save, "roost", &Economy::default()), None, "only at its own board");
        assert_eq!(hand_in(&mut save, "outpost", &Economy::default()), Some((30, 160)));
        assert_eq!((save.scrap, save.banked, save.contracts.len()), (5, 161, 0));
    }

    #[test]
    fn a_lapsed_parcel_costs_standing_with_whoever_gave_it_once() {
        let (bases, e, t) = setup();
        let mut save = Save { day: 2, ..default() };
        save.contracts = vec![
            Contract { job: Job::Courier { to: "roost".into() }, from: "outpost".into(), pay: 500, due: Some(1) },
            Contract { job: Job::Courier { to: "roost".into() }, from: "yard".into(), pay: 500, due: Some(2) },
            Contract { job: Job::Cull { need: 4, got: 1 }, from: "yard".into(), pay: 200, due: Some(1) },
            Contract { job: Job::Courier { to: "yard".into() }, from: "outpost".into(), pay: 400, due: None },
        ];
        let gone = expire(&mut save, &bases, &e, &t);
        assert_eq!(gone.len(), 2);
        assert_eq!(save.contracts.len(), 2, "due today and never due are kept");
        assert_eq!(standing::get(&save, Faction::Pmc, &t), -25, "-20 and -5 for the lost parcel");
        assert_eq!(standing::get(&save, Faction::Scrappers, &t), 0, "a lapsed cull costs nothing");
        assert!(expire(&mut save, &bases, &e, &t).is_empty(), "once");
    }

    #[test]
    fn a_cull_pays_once_on_its_last_raider() {
        let mut save = Save::default();
        save.contracts.push(Contract { job: Job::Cull { need: 2, got: 0 }, from: "roost".into(), pay: 100, due: Some(1) });
        assert!(raider_down(&mut save).is_empty());
        assert_eq!(save.contracts[0].job, Job::Cull { need: 2, got: 1 });
        assert_eq!(raider_down(&mut save), vec![100]);
        assert_eq!((save.pocket, save.contracts.len()), (100, 0));
        assert!(raider_down(&mut save).is_empty());
    }
}
