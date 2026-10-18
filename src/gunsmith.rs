//! Gun customization: four attachment slots per hitscan weapon, each part a multiplier on the
//! gun's tuning, drawn as simple shapes on the first-person model. The loadout lives in
//! `save.toml`; the menu in `menu.rs` edits it.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

use crate::loot::{Save, SaveFile};
use crate::tuning::Gun;
use crate::viewmodel::ViewModel;
use crate::weapon::{Arsenal, WEAPONS, WeaponKind};

pub const SLOTS: [&str; 4] = ["OPTIC", "MUZZLE", "GRIP", "STOCK"];

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
        part("3X SCOPE", "Aimed spread -55%, recoil +15%", |g| {
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

/// Which part sits in each slot of each weapon (`WEAPONS` order).
#[derive(Resource, Serialize, Deserialize, Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Loadout {
    pub parts: [[u8; 4]; 4],
    /// Per-slot tuning, -4..4, trading the slot's two stats (see `TUNES`); only a fitted part tunes.
    #[serde(default)]
    pub tune: [[i8; 4]; 4],
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
        self.parts[Self::weapon_index(kind)][slot] as usize % PARTS[slot].len()
    }
    /// Step a slot's part by `dir`, wrapping.
    pub fn cycle(&mut self, kind: WeaponKind, slot: usize, dir: i32) {
        let n = PARTS[slot].len() as i32;
        let at = self.part(kind, slot) as i32;
        self.parts[Self::weapon_index(kind)][slot] = (at + dir).rem_euclid(n) as u8;
    }
    pub fn tuning(&self, kind: WeaponKind, slot: usize) -> i8 {
        self.tune[Self::weapon_index(kind)][slot]
    }
    /// Nudge a slot's tuning by `dir`, within -4..4.
    pub fn cycle_tune(&mut self, kind: WeaponKind, slot: usize, dir: i32) {
        let t = &mut self.tune[Self::weapon_index(kind)][slot];
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

/// Whether the gunsmith can fit parts to this weapon (rockets are not a gun).
pub fn customizable(kind: WeaponKind) -> bool {
    kind != WeaponKind::RocketLauncher
}

pub struct GunsmithPlugin;

impl Plugin for GunsmithPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Loadout>().add_systems(Startup, restore).add_systems(Update, (spawn_parts, show_parts));
    }
}

/// A part's mesh on the viewmodel: shown when its weapon is out and the part is fitted.
#[derive(Component)]
struct PartMesh {
    weapon: usize,
    slot: usize,
    part: usize,
}

fn restore(save: Option<Res<Save>>, mut loadout: ResMut<Loadout>) {
    if let Some(l) = save.and_then(|s| s.loadout) {
        *loadout = l;
    }
}

/// Write the loadout into the save file.
pub fn persist(loadout: &Loadout, save: &mut Save, file: &SaveFile) {
    save.loadout = Some(*loadout);
    file.write(save);
}

/// Where parts sit on each weapon, in viewmodel space (guns point down -Z): the top rail,
/// the muzzle, under the barrel and the stock.
fn anchors(kind: WeaponKind) -> Option<[Vec3; 4]> {
    match kind {
        WeaponKind::Rifle => Some([Vec3::new(0.0, 0.085, 0.0), Vec3::new(0.0, 0.03, -0.17), Vec3::new(0.0, -0.06, -0.06), Vec3::new(0.0, -0.02, 0.19)]),
        WeaponKind::Shotgun => Some([Vec3::new(0.0, 0.1, 0.03), Vec3::new(0.0, 0.04, -0.16), Vec3::new(0.0, -0.06, -0.04), Vec3::new(0.0, -0.03, 0.24)]),
        WeaponKind::Pistol => Some([Vec3::new(0.0, 0.075, 0.03), Vec3::new(0.0, 0.035, -0.08), Vec3::new(0.0, -0.04, 0.0), Vec3::new(0.0, -0.03, 0.14)]),
        WeaponKind::RocketLauncher => None,
    }
}

fn spawn_parts(
    mut commands: Commands,
    mut done: Local<bool>,
    vm: Option<Single<Entity, With<ViewModel>>>,
    meshes: Option<ResMut<Assets<Mesh>>>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
) {
    if *done {
        return;
    }
    // Headless tests have no render assets, and no viewmodel to hang parts on.
    let (Some(vm), Some(mut meshes), Some(mut materials)) = (vm, meshes, materials) else { return };
    *done = true;
    let dark = materials.add(Color::srgb(0.12, 0.12, 0.13));
    let steel = materials.add(StandardMaterial { base_color: Color::srgb(0.3, 0.31, 0.33), metallic: 0.8, perceptual_roughness: 0.4, ..default() });
    let glass = materials.add(StandardMaterial { base_color: Color::srgb(0.2, 0.5, 0.9), emissive: LinearRgba::rgb(0.2, 0.6, 1.2), ..default() });
    let along_z = Quat::from_rotation_x(std::f32::consts::FRAC_PI_2);
    // Meshes per slot and part (part 0 is bare, so it has none).
    let dot_base = meshes.add(Cuboid::new(0.02, 0.012, 0.03));
    let dot_glass = meshes.add(Cuboid::new(0.016, 0.014, 0.003));
    let scope = meshes.add(Cylinder::new(0.012, 0.07));
    let scope_lens = meshes.add(Cylinder::new(0.011, 0.004));
    let comp = meshes.add(Cuboid::new(0.024, 0.024, 0.03));
    let supp = meshes.add(Cylinder::new(0.016, 0.075));
    let vgrip = meshes.add(Cuboid::new(0.02, 0.045, 0.02));
    let agrip = meshes.add(Cuboid::new(0.02, 0.028, 0.045));
    let light = meshes.add(Cuboid::new(0.02, 0.04, 0.02));
    let heavy = meshes.add(Cuboid::new(0.03, 0.06, 0.05));
    commands.entity(*vm).with_children(|p| {
        for (weapon, kind) in WEAPONS.iter().enumerate() {
            let Some([top, muzzle, under, stock]) = anchors(*kind) else { continue };
            let mut spawn = |slot: usize, part: usize, mesh: &Handle<Mesh>, mat: &Handle<StandardMaterial>, tf: Transform| {
                p.spawn((PartMesh { weapon, slot, part }, Mesh3d(mesh.clone()), MeshMaterial3d(mat.clone()), tf, Visibility::Hidden));
            };
            spawn(0, 1, &dot_base, &dark, Transform::from_translation(top));
            spawn(0, 1, &dot_glass, &glass, Transform::from_translation(top + Vec3::new(0.0, 0.013, -0.012)));
            spawn(0, 2, &scope, &dark, Transform::from_translation(top + Vec3::Y * 0.012).with_rotation(along_z));
            spawn(0, 2, &scope_lens, &glass, Transform::from_translation(top + Vec3::new(0.0, 0.012, -0.036)).with_rotation(along_z));
            spawn(1, 1, &comp, &steel, Transform::from_translation(muzzle + Vec3::Z * -0.01));
            spawn(1, 2, &supp, &dark, Transform::from_translation(muzzle + Vec3::Z * -0.035).with_rotation(along_z));
            spawn(2, 1, &vgrip, &dark, Transform::from_translation(under + Vec3::Y * -0.02));
            spawn(2, 2, &agrip, &dark, Transform::from_translation(under + Vec3::Y * -0.012));
            spawn(3, 1, &light, &steel, Transform::from_translation(stock));
            spawn(3, 2, &heavy, &dark, Transform::from_translation(stock));
        }
    });
}

fn show_parts(arsenal: Res<Arsenal>, loadout: Res<Loadout>, mut parts: Query<(&PartMesh, &mut Visibility)>) {
    for (p, mut vis) in &mut parts {
        let fitted = p.weapon == arsenal.current && loadout.parts[p.weapon][p.slot] as usize == p.part;
        let want = if fitted { Visibility::Inherited } else { Visibility::Hidden };
        if *vis != want {
            *vis = want;
        }
    }
}
