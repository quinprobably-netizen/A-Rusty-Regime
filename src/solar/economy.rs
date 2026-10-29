//! The ledger (stage A of `docs/superpowers/specs/2026-10-29-economy-design.md`): what you earn
//! in the field is at risk until you walk it into a base, and being shot down costs what is
//! aboard, not the bank.
//!
//! **The pocket:** bounties go into `Save::pocket`, not the bank. Walk up to the door of any base
//! that will serve you (one whose faction does not hunt you) and the pocket banks (`Banked
//! $120`). A parcel pays into the bank as before, since you are at a door when it does.
//!
//! **The hold:** scrap rides in the ship, `[economy] hold_base` of it and `hold_per_plating` more
//! a level of hull plating (`salvage` stops pulling scrap in once it is full). The Yard's parts
//! rack buys it at `scrap_value` each, priced by your standing (`standing::buys`).
//!
//! **Shot down** (`loss`): the pocket, the hold and the parcel are lost; the bank is not. A fresh
//! Kestrel costs a rebuy fee, `rebuy_share` of what the engine tune and the parts on it are worth
//! (`ship_value`), between `rebuy_min` and `rebuy_max`, and never more than the bank holds.
//!
//! **Repair:** reaching a base's door also repairs the hull of the ship you last landed, if it is
//! parked within `repair_reach`, at `repair_per_hp` a point priced by the base's faction, as far
//! as the bank goes.

use bevy::prelude::*;

use super::base::{Base, Bases};
use super::combat::{Faction, Hull};
use super::ship::Ship;
use super::standing;
use super::station::{Prompt, DELIVER_RADIUS};
use crate::controller::Player;
use crate::save::{Save, SaveFile};
use crate::tuning::{Economy, ShipCombat, Tuning};
use crate::vehicle::Driving;

pub fn build(app: &mut App) {
    app.add_systems(FixedUpdate, at_the_door.after(super::station::deliver));
}

/// Moves the pocket into the bank; returns how much.
pub fn bank(save: &mut Save) -> u32 {
    let p = std::mem::take(&mut save.pocket);
    save.banked = save.banked.saturating_add(p);
    p
}

/// Whether a base of `faction` banks, repairs and trades for you: any base but one whose faction
/// hunts you.
pub fn serves(save: &Save, faction: Faction, t: &ShipCombat) -> bool {
    !standing::hunted(save, faction, t)
}

/// How much scrap the hold carries.
pub fn hold_cap(save: &Save, e: &Economy) -> u32 {
    e.hold_base + e.hold_per_plating * save.ship_parts[0] as u32
}

/// What the engine tune and the parts on the Kestrel are worth, in money: the tune's levels at
/// their price, and the parts' scrap at `scrap_value`.
pub fn ship_value(save: &Save, e: &Economy, t: &ShipCombat) -> u32 {
    let tune: u32 = e.tune.iter().take(save.ship_level as usize).sum();
    let scrap: u32 = t.part_costs.iter().zip(save.ship_parts).map(|(costs, level)| costs.iter().take(level as usize).sum::<u32>()).sum();
    tune + scrap * e.scrap_value
}

/// What a fresh Kestrel costs when yours is shot down (before the bank caps it).
pub fn rebuy_fee(save: &Save, e: &Economy, t: &ShipCombat) -> u32 {
    ((ship_value(save, e, t) as f32 * e.rebuy_share).round() as u32).clamp(e.rebuy_min, e.rebuy_max.max(e.rebuy_min))
}

/// What a base of `faction` charges to repair `missing` points of hull.
pub fn repair_cost(missing: f32, faction: Faction, save: &Save, e: &Economy, t: &ShipCombat) -> u32 {
    standing::price((missing.max(0.0) * e.repair_per_hp).ceil() as u32, faction, save, t)
}

/// Repairs as much of `hull` as the bank affords at a base of `faction`, whole points, and takes
/// the money: the points repaired and what they cost, or `None` if there is nothing to repair or
/// nothing to pay with.
pub fn repair(hull: &mut Hull, faction: Faction, save: &mut Save, e: &Economy, t: &ShipCombat) -> Option<(f32, u32)> {
    let missing = (hull.max_hp - hull.hp).max(0.0);
    if missing <= 0.0 || save.banked == 0 {
        return None;
    }
    let full = repair_cost(missing, faction, save, e, t);
    let (points, cost) = if full <= save.banked {
        (missing, full)
    } else {
        // Whole points at what one costs here, as many as the bank pays for.
        let each = (full as f32 / missing.ceil()).max(f32::EPSILON);
        let points = (save.banked as f32 / each).floor().min(missing);
        if points < 1.0 {
            return None;
        }
        (points, repair_cost(points, faction, save, e, t).min(save.banked))
    };
    save.banked -= cost;
    hull.hp = (hull.hp + points).min(hull.max_hp);
    Some((points, cost))
}

/// Sells the whole hold to a base of `faction` that pays `share` of `scrap_value` into the bank;
/// returns the money.
pub fn sell_scrap(save: &mut Save, faction: Faction, share: f32, e: &Economy, t: &ShipCombat) -> u32 {
    let each = standing::buys((e.scrap_value as f32 * share).round() as u32, faction, save, t);
    let money = std::mem::take(&mut save.scrap).saturating_mul(each);
    save.banked = save.banked.saturating_add(money);
    money
}

/// On foot in the doorway of a base that serves you: the pocket banks, and on the way in, the
/// ship you last landed nearby is repaired.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn at_the_door(
    tuning: Res<Tuning>,
    bases: Res<Bases>,
    file: Res<SaveFile>,
    save: Option<ResMut<Save>>,
    mut prompt: ResMut<Prompt>,
    player: Single<(&Transform, Has<Driving>), With<Player>>,
    placed: Query<(&GlobalTransform, &Base)>,
    mut ships: Query<(&Ship, &Transform, &mut Hull)>,
    mut was_there: Local<bool>,
) {
    let Some(mut save) = save else { return };
    let (tf, driving) = *player;
    let (t, e) = (&tuning.ship_combat, &tuning.economy);
    let door = placed.iter().find_map(|(at, base)| {
        let spec = &bases.base[base.spec];
        let door = at.translation() + at.rotation() * Vec3::from(spec.door);
        let faction = Faction::from_id(&spec.faction).unwrap_or_default();
        (door.distance(tf.translation) < DELIVER_RADIUS && serves(&save, faction, t)).then_some((door, faction))
    });
    let Some((door, faction)) = door.filter(|_| !driving) else {
        *was_there = false;
        return;
    };
    let arrived = !std::mem::replace(&mut *was_there, true);
    let mut said = Vec::new();
    if save.pocket > 0 {
        said.push(format!("Banked ${}", bank(&mut save)));
    }
    if arrived {
        // The last landed; before any landing, your own Kestrel rather than whichever ship the
        // query meets last.
        let landed = ships
            .iter_mut()
            .filter(|(s, tf, _)| s.pilot.is_none() && tf.translation.distance(door) < e.repair_reach)
            .max_by(|a, b| a.0.landed_at.total_cmp(&b.0.landed_at).then((a.0.spec == 0).cmp(&(b.0.spec == 0))));
        if let Some((_, _, mut hull)) = landed
            && let Some((points, cost)) = repair(&mut hull, faction, &mut save, e, t)
        {
            said.push(format!("Repaired {points:.0} hull: -${cost}"));
        }
    }
    if !said.is_empty() {
        file.write(&save);
        info!("at the door: {}", said.join(", "));
        prompt.say(said.join("   "));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tuned() -> (Economy, ShipCombat) {
        (Economy::default(), ShipCombat::default())
    }

    #[test]
    fn bank_moves_the_pocket_into_the_bank() {
        let mut save = Save { banked: 10, pocket: 120, ..default() };
        assert_eq!(bank(&mut save), 120);
        assert_eq!((save.banked, save.pocket), (130, 0));
        assert_eq!(bank(&mut save), 0, "once");
    }

    #[test]
    fn a_base_that_hunts_you_does_not_serve_you() {
        let (_, t) = tuned();
        let mut save = Save::default();
        save.standing.insert("scrappers".into(), -60);
        assert!(!serves(&save, Faction::Scrappers, &t));
        save.standing.insert("scrappers".into(), -59);
        assert!(serves(&save, Faction::Scrappers, &t));
        assert!(serves(&save, Faction::Deserters, &t), "the Roost always does");
    }

    #[test]
    fn the_hold_holds_sixty_and_twenty_more_a_plating_level() {
        let (e, _) = tuned();
        assert_eq!(hold_cap(&Save::default(), &e), 60);
        assert_eq!(hold_cap(&Save { ship_parts: [3, 0, 0, 0], ..default() }, &e), 120);
    }

    #[test]
    fn a_bare_kestrel_is_worth_nothing_and_rebuys_at_the_floor() {
        let (e, t) = tuned();
        assert_eq!((ship_value(&Save::default(), &e, &t), rebuy_fee(&Save::default(), &e, &t)), (0, 100));
    }

    #[test]
    fn the_rebuy_fee_is_a_tenth_of_the_kit_up_to_the_cap() {
        let (mut e, t) = tuned();
        let save = Save { ship_level: 3, ship_parts: [3, 3, 3, 3], ..default() };
        assert_eq!(ship_value(&save, &e, &t), 2400 + 6 * (76 + 76 + 62 + 95));
        assert_eq!(rebuy_fee(&save, &e, &t), 425);
        e.rebuy_share = 1.0;
        assert_eq!(rebuy_fee(&save, &e, &t), 1500);
        assert_eq!(ship_value(&Save { ship_level: 2, ..default() }, &e, &t), 1000);
    }

    #[test]
    fn repair_costs_a_credit_a_point_at_list_price_and_less_to_a_friend() {
        let (e, t) = tuned();
        let mut save = Save::default();
        assert_eq!(repair_cost(40.0, Faction::Deserters, &save, &e, &t), 40);
        save.standing.insert("scrappers".into(), 40);
        assert_eq!(repair_cost(40.0, Faction::Scrappers, &save, &e, &t), 34);
    }

    #[test]
    fn repair_stops_at_what_the_bank_affords() {
        let (e, t) = tuned();
        let mut save = Save { banked: 25, ..default() };
        let mut hull = Hull::new(100.0, 0.0);
        hull.hp = 60.0;
        assert_eq!(repair(&mut hull, Faction::Deserters, &mut save, &e, &t), Some((25.0, 25)));
        assert_eq!((hull.hp, save.banked), (85.0, 0));
        assert_eq!(repair(&mut hull, Faction::Deserters, &mut save, &e, &t), None, "nothing to pay with");
        save.banked = 100;
        assert_eq!(repair(&mut hull, Faction::Deserters, &mut save, &e, &t), Some((15.0, 15)));
        assert_eq!((hull.hp, save.banked), (100.0, 85));
        assert_eq!(repair(&mut hull, Faction::Deserters, &mut save, &e, &t), None, "nothing to repair");
    }

    #[test]
    fn selling_empties_the_hold_into_the_bank_and_a_friend_pays_more() {
        let (e, t) = tuned();
        let mut save = Save { scrap: 12, banked: 5, ..default() };
        assert_eq!(sell_scrap(&mut save, Faction::Scrappers, 1.0, &e, &t), 72);
        assert_eq!((save.scrap, save.banked), (0, 77));
        assert_eq!(sell_scrap(&mut save, Faction::Scrappers, 1.0, &e, &t), 0, "nothing left");
        for (v, each) in [(0, 6), (40, 7), (-41, 5)] {
            save.standing.insert("scrappers".into(), v);
            assert_eq!(standing::buys(6, Faction::Scrappers, &save, &t), each, "at {v}");
        }
    }
}
