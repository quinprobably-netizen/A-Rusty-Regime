//! Gun customization: four attachment slots per hitscan weapon, each part a multiplier on the
//! gun's tuning and a real mesh on the weapon model (`att.<slot>.<part>`, shown by `viewmodel.rs`).
//! The loadout lives in `save.toml`; the menu in `menu.rs` edits it.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

use crate::loot::{Save, SaveFile};
use crate::tuning::Gun;
use crate::weapon::{WEAPONS, WeaponKind};

pub const SLOTS: [&str; 4] = ["OPTIC", "MUZZLE", "GRIP", "STOCK"];

/// The model mesh for each slot's parts (`att.<slot>.<part>`), in `PARTS` order. Index 0 is the
/// bare gun's own piece (flip-up irons, flash hider, standard stock), which a fitted part replaces.
pub const MESHES: [[&str; 3]; 4] = [
    ["att.optic.irons", "att.optic.reddot", "att.optic.scope"],
    ["att.muzzle.bare", "att.muzzle.comp", "att.muzzle.supp"],
    ["att.grip.standard", "att.grip.vertical", "att.grip.angled"],
    ["att.stock.standard", "att.stock.light", "att.stock.heavy"],
];

/// One attachment: what it is called, what it does, and how it changes the gun.
pub struct Part {
    pub name: &'static str,
    pub desc: &'static str,
    pub apply: fn(&mut Gun),
}

const fn part(name: &'static str, desc: &'static str, apply: fn(&mut Gun)) -> Part {
    Part { name, desc, apply }
}

/// Parts per slot; index 0 is always the bare gun.
pub const PARTS: [[Part; 3]; 4] = [
    [
        part("IRON SIGHTS", "Stock sights", |_| {}),
        part("RED DOT", "Aimed spread -25%", |g| g.ads_spread *= 0.75),
        part("SCOPE", "Magnifies, aimed spread -55%, recoil +15%", |g| {
            g.ads_spread *= 0.45;
            g.recoil_up *= 1.15;
            g.recoil_side *= 1.15;
        }),
    ],
    [
        part("BARE", "Nothing on the barrel", |_| {}),
        part("COMPENSATOR", "Vertical recoil -30%, spread +10%", |g| {
            g.recoil_up *= 0.7;
            g.spread_degrees *= 1.1;
        }),
        part("SUPPRESSOR", "Recoil -15%, velocity -15%, damage -10%", |g| {
            g.recoil_up *= 0.85;
            g.recoil_side *= 0.85;
            g.velocity *= 0.85;
            g.damage *= 0.9;
        }),
    ],
    [
        part("STANDARD", "Plain grip", |_| {}),
        part("VERTICAL", "Side recoil -50%, heat spread -20%", |g| {
            g.recoil_side *= 0.5;
            g.heat_spread *= 0.8;
        }),
        part("ANGLED", "Spread -15%, vertical recoil +10%", |g| {
            g.spread_degrees *= 0.85;
            g.recoil_up *= 1.1;
        }),
    ],
    [
        part("STANDARD", "Plain stock", |_| {}),
        part("LIGHT", "Fires 10% faster, recoil +10%", |g| {
            g.cooldown *= 0.9;
            g.recoil_up *= 1.1;
            g.recoil_side *= 1.1;
        }),
        part("HEAVY", "Recoil -25%, fires 10% slower", |g| {
            g.cooldown *= 1.1;
            g.recoil_up *= 0.75;
            g.recoil_side *= 0.75;
        }),
    ],
];

/// Which part sits in each slot of each weapon (`WEAPONS` order). Lists grow as weapons are
/// added, so a save from before the new guns still loads.
#[derive(Resource, Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
pub struct Loadout {
    pub parts: Vec<[u8; 4]>,
    /// Per-slot tuning, -4..4, trading the slot's two stats (see `TUNES`); only a fitted part tunes.
    #[serde(default)]
    pub tune: Vec<[i8; 4]>,
}

/// What each slot's tuning slider trades: left stat (negative) against right stat (positive).
pub const TUNES: [(&str, &str); 4] = [("HIP FIRE", "AIMED FIRE"), ("VELOCITY", "CONTROL"), ("RATE", "STABILITY"), ("RANGE", "CONTROL")];
pub const TUNE_MAX: i8 = 4;

/// Apply a slot's tuning `t` (-4..4) to the gun.
fn tune(slot: usize, t: i8, g: &mut Gun) {
    let t = t as f32 / TUNE_MAX as f32;
    let (up, down) = (1.0 + 0.15 * t.abs(), 1.0 - 0.15 * t.abs());
    match (slot, t > 0.0) {
        (0, true) => { g.ads_spread *= down; g.spread_degrees *= up; }
        (0, false) => { g.spread_degrees *= down; g.ads_spread *= up; }
        (1, true) => { g.recoil_up *= down; g.recoil_side *= down; g.velocity *= down; }
        (1, false) => { g.velocity *= up; g.recoil_up *= up; g.recoil_side *= up; }
        (2, true) => { g.heat_spread *= down; g.cooldown *= up; }
        (2, false) => { g.cooldown *= down; g.heat_spread *= up; }
        (3, true) => { g.recoil_up *= down; g.recoil_side *= down; g.range *= down; }
        _ => { g.range *= up; g.recoil_up *= up; g.recoil_side *= up; }
    }
}

impl Loadout {
    pub fn weapon_index(kind: WeaponKind) -> usize {
        WEAPONS.iter().position(|k| *k == kind).unwrap_or(0)
    }
    pub fn part(&self, kind: WeaponKind, slot: usize) -> usize {
        self.parts.get(Self::weapon_index(kind)).map_or(0, |p| p[slot] as usize % PARTS[slot].len())
    }
    /// Step a slot's part by `dir`, wrapping.
    pub fn cycle(&mut self, kind: WeaponKind, slot: usize, dir: i32) {
        let n = PARTS[slot].len() as i32;
        let at = self.part(kind, slot) as i32;
        let i = Self::weapon_index(kind);
        if self.parts.len() <= i {
            self.parts.resize(WEAPONS.len(), [0; 4]);
        }
        self.parts[i][slot] = (at + dir).rem_euclid(n) as u8;
    }
    pub fn tuning(&self, kind: WeaponKind, slot: usize) -> i8 {
        self.tune.get(Self::weapon_index(kind)).map_or(0, |t| t[slot])
    }
    /// Nudge a slot's tuning by `dir`, within -4..4.
    pub fn cycle_tune(&mut self, kind: WeaponKind, slot: usize, dir: i32) {
        let i = Self::weapon_index(kind);
        if self.tune.len() <= i {
            self.tune.resize(WEAPONS.len(), [0; 4]);
        }
        let t = &mut self.tune[i][slot];
        *t = (*t as i32 + dir).clamp(-(TUNE_MAX as i32), TUNE_MAX as i32) as i8;
    }
    /// The gun's tuning with every fitted part and its tuning applied.
    pub fn gun(&self, kind: WeaponKind, base: &Gun) -> Gun {
        let mut gun = base.clone();
        for slot in 0..SLOTS.len() {
            let part = self.part(kind, slot);
            (PARTS[slot][part].apply)(&mut gun);
            if part != 0 && self.tuning(kind, slot) != 0 {
                tune(slot, self.tuning(kind, slot), &mut gun);
            }
        }
        gun
    }
}

/// Five bars, 0..1, for the stat panel: damage per shot, rate of fire, accuracy, control, range.
pub fn stats(gun: &Gun) -> [(&'static str, f32); 5] {
    let damage = gun.damage * gun.pellets.max(1) as f32;
    [
        ("DAMAGE", (damage / 100.0).clamp(0.0, 1.0)),
        ("RATE", (0.08 / gun.cooldown.max(0.01)).clamp(0.0, 1.0)),
        ("ACCURACY", (1.0 - gun.spread_degrees / 6.0).clamp(0.0, 1.0)),
        ("CONTROL", (1.0 - (gun.recoil_up + gun.recoil_side) / 4.0).clamp(0.0, 1.0)),
        ("RANGE", (gun.range / 250.0).clamp(0.0, 1.0)),
    ]
}

/// Whether the gunsmith can fit parts to this weapon: the hitscan guns.
pub fn customizable(kind: WeaponKind) -> bool {
    matches!(kind, WeaponKind::Rifle | WeaponKind::Shotgun | WeaponKind::Pistol | WeaponKind::Smg | WeaponKind::Dmr | WeaponKind::Revolver)
}

pub struct GunsmithPlugin;

impl Plugin for GunsmithPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Loadout>().add_systems(Startup, restore);
    }
}

fn restore(save: Option<Res<Save>>, mut loadout: ResMut<Loadout>) {
    if let Some(l) = save.and_then(|s| s.loadout.clone()) {
        *loadout = l;
    }
}

/// Write the loadout into the save file.
pub fn persist(loadout: &Loadout, save: &mut Save, file: &SaveFile) {
    save.loadout = Some(loadout.clone());
    file.write(save);
}
