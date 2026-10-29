//! Who owns what. You start with one sidearm, bare (the Warden or the Smite, whichever your
//! character carries) and a knife; every other gun and every attachment is bought from the Roost's
//! quartermaster with banked money (`menu.rs` has the counter). Ownership lives in the save:
//! `Save.weapons` by id and `Save.parts` as a bit per part. An empty `weapons` list means there is
//! no quartermaster on this world, so everything is yours (the old levels, and the tests).

use bevy::prelude::*;

use crate::abilities::Class;
use crate::character::Characters;
use crate::gunsmith::{Loadout, PARTS, SLOTS};
use crate::save::{Save, SaveFile};
use crate::tuning::Economy;
use crate::weapon::{Arsenal, KNIFE, WEAPONS, WeaponKind};

/// What a weapon costs, banked money (`[economy] guns`). `None`: not for sale (the knife comes
/// with you).
pub fn price(kind: WeaponKind, e: &Economy) -> Option<u32> {
    if kind == WeaponKind::Knife {
        return None;
    }
    e.guns.get(kind.id()).copied()
}

/// Whether `kind` is yours. With no save, or an empty one, everything is.
pub fn owns_weapon(save: Option<&Save>, kind: WeaponKind) -> bool {
    save.is_none_or(|s| s.weapons.is_empty() || kind == WeaponKind::Knife || s.weapons.iter().any(|w| w == kind.id()))
}

/// Whether part `part` of slot `slot` is yours.
pub fn owns_part(save: Option<&Save>, slot: usize, part: usize) -> bool {
    part == 0 || save.is_none_or(|s| s.weapons.is_empty() || s.parts[slot] & (1 << part) != 0)
}

/// What a sale came to.
#[derive(Debug, PartialEq, Eq)]
pub enum Sale {
    Bought(u32),
    /// Short of money by this much.
    Poor(u32),
    Owned,
    NotForSale,
}

pub fn buy_weapon(save: &mut Save, kind: WeaponKind, e: &Economy) -> Sale {
    if owns_weapon(Some(save), kind) {
        return Sale::Owned;
    }
    let Some(cost) = price(kind, e) else { return Sale::NotForSale };
    if save.banked < cost {
        return Sale::Poor(cost - save.banked);
    }
    save.banked -= cost;
    save.weapons.push(kind.id().to_string());
    Sale::Bought(cost)
}

pub fn buy_part(save: &mut Save, slot: usize, part: usize, e: &Economy) -> Sale {
    if owns_part(Some(save), slot, part) {
        return Sale::Owned;
    }
    let cost = e.attachments[slot][part];
    if save.banked < cost {
        return Sale::Poor(cost - save.banked);
    }
    save.banked -= cost;
    save.parts[slot] |= 1 << part;
    Sale::Bought(cost)
}

/// The sidearm `class`'s character starts with.
pub fn starter(characters: Option<&Characters>, class: Option<&Class>) -> WeaponKind {
    let (Some(characters), Some(class)) = (characters, class) else { return WeaponKind::Pistol };
    characters.class.get(&class.0).map_or(WeaponKind::Pistol, |c| characters.start(&c.character))
}

fn slot_of(kind: WeaponKind) -> usize {
    WEAPONS.iter().position(|k| *k == kind).unwrap_or(0)
}

/// Gives a new save its starter kit. Nothing changes if it already has weapons.
pub fn grant(save: &mut Save, start: WeaponKind) -> bool {
    if !save.weapons.is_empty() {
        return false;
    }
    save.weapons = vec![start.id().to_string(), WeaponKind::Knife.id().to_string()];
    save.parts = [0; 4];
    save.loadout = None;
    true
}

/// Takes back what is not yours: unbought parts come off every gun, and a weapon in hand that you
/// do not own is swapped for one you do. Returns whether anything changed.
pub fn sanitize(save: &Save, loadout: &mut Loadout, arsenal: &mut Arsenal, start: WeaponKind) -> bool {
    let mut changed = false;
    for gun in 0..loadout.parts.len() {
        for slot in 0..SLOTS.len() {
            let part = loadout.parts[gun][slot] as usize;
            if part >= PARTS[slot].len() || !owns_part(Some(save), slot, part) {
                loadout.parts[gun][slot] = 0;
                changed = true;
            }
        }
    }
    if !owns_weapon(Some(save), arsenal.kind()) {
        let own = if owns_weapon(Some(save), start) { start } else { WeaponKind::Knife };
        arsenal.current = slot_of(own);
        arsenal.last = KNIFE;
        arsenal.switch_time = 0.0;
        changed = true;
    }
    changed
}

/// At the start of the solar system: hand a new save the kit and make sure the loadout is only
/// what you own.
pub fn start_kit(
    mut save: ResMut<Save>,
    file: Res<SaveFile>,
    mut loadout: ResMut<Loadout>,
    mut arsenal: ResMut<Arsenal>,
    characters: Option<Res<Characters>>,
    class: Option<Res<Class>>,
) {
    let start = starter(characters.as_deref(), class.as_deref());
    let new = grant(&mut save, start);
    if new {
        *loadout = Loadout::default();
        arsenal.current = slot_of(start);
        arsenal.last = KNIFE;
        arsenal.switch_time = 0.0;
    }
    let tidied = sanitize(&save, &mut loadout, &mut arsenal, start);
    if new || tidied {
        crate::gunsmith::persist(&loadout, &mut save, &file);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_new_save_gets_one_bare_sidearm_and_a_knife() {
        let mut save = Save::default();
        assert!(owns_weapon(Some(&save), WeaponKind::Rifle), "no quartermaster: everything is yours");
        assert!(grant(&mut save, WeaponKind::Revolver));
        assert!(owns_weapon(Some(&save), WeaponKind::Revolver) && owns_weapon(Some(&save), WeaponKind::Knife));
        assert!(!owns_weapon(Some(&save), WeaponKind::Pistol) && !owns_weapon(Some(&save), WeaponKind::Rifle));
        assert!(!owns_part(Some(&save), 0, 1) && owns_part(Some(&save), 0, 0), "only the bare parts");
        assert!(!grant(&mut save, WeaponKind::Pistol), "a save that has its kit keeps it");
    }

    #[test]
    fn buying_takes_banked_money_once() {
        let e = Economy::default();
        let mut save = Save::default();
        grant(&mut save, WeaponKind::Pistol);
        save.banked = 700;
        assert_eq!(buy_weapon(&mut save, WeaponKind::Smg, &e), Sale::Bought(600));
        assert_eq!((save.banked, owns_weapon(Some(&save), WeaponKind::Smg)), (100, true));
        assert_eq!(buy_weapon(&mut save, WeaponKind::Smg, &e), Sale::Owned);
        assert_eq!(buy_weapon(&mut save, WeaponKind::Dmr, &e), Sale::Poor(1000));
        assert_eq!(buy_weapon(&mut save, WeaponKind::Knife, &e), Sale::Owned);
        assert_eq!(buy_part(&mut save, 1, 2, &e), Sale::Poor(250));
        save.banked = 500;
        assert_eq!(buy_part(&mut save, 1, 2, &e), Sale::Bought(350));
        assert!(owns_part(Some(&save), 1, 2) && !owns_part(Some(&save), 1, 1) && !owns_part(Some(&save), 0, 2));
        assert_eq!(save.banked, 150);
    }

    #[test]
    fn everything_but_the_knife_has_a_price_and_every_part_too() {
        let e = Economy::default();
        for kind in WEAPONS {
            assert_eq!(price(kind, &e).is_none(), kind == WeaponKind::Knife, "{kind:?}");
        }
        for slot in 0..SLOTS.len() {
            assert_eq!(e.attachments[slot][0], 0);
            assert!(e.attachments[slot][1..].iter().all(|p| *p > 0));
        }
    }

    #[test]
    fn leaving_the_counter_hands_back_what_you_did_not_buy() {
        let mut save = Save::default();
        grant(&mut save, WeaponKind::Revolver);
        save.parts[0] = 0b010; // the red dot
        let mut loadout = Loadout::default();
        loadout.cycle(WeaponKind::Revolver, 0, 1); // red dot, bought
        loadout.cycle(WeaponKind::Revolver, 1, 2); // suppressor, not
        let mut arsenal = Arsenal::default(); // the rocket launcher, not yours
        assert!(sanitize(&save, &mut loadout, &mut arsenal, WeaponKind::Revolver));
        assert_eq!((loadout.part(WeaponKind::Revolver, 0), loadout.part(WeaponKind::Revolver, 1)), (1, 0));
        assert_eq!(arsenal.kind(), WeaponKind::Revolver);
        assert_eq!(arsenal.last, KNIFE);
        assert!(!sanitize(&save, &mut loadout, &mut arsenal, WeaponKind::Revolver), "nothing more to take");
    }

    #[test]
    fn saves_from_before_the_quartermaster_still_load() {
        let save: Save = toml::from_str("banked = 40\n").unwrap();
        assert!(save.weapons.is_empty() && save.parts == [0; 4]);
        let back: Save = toml::from_str(&toml::to_string(&Save { weapons: vec!["pistol".into()], parts: [2, 0, 6, 0], ..default() }).unwrap()).unwrap();
        assert_eq!((back.weapons, back.parts), (vec!["pistol".to_string()], [2, 0, 6, 0]));
    }
}
