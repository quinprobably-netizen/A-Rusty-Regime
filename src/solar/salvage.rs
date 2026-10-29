//! Salvage (stage 3 of ship combat, `docs/superpowers/specs/2026-10-29-ship-combat-stages-2-3-design.md`):
//! wrecks drop scrap you fly into, scrap buys four permanent parts for the Kestrel at the Yard,
//! and now and then a wreck drops a module, two of which fit at a time.
//!
//! **Scrap:** an enemy hull shot down (by anyone: a fight between raiders and a patrol leaves
//! some for you) drops its `[ship_combat] scrap` where it blew apart. It drifts on with the
//! wreck's velocity, slowed by air as a shot is and coming to rest on the ground, for
//! `scrap_life` seconds. The ship you fly pulls it in from `scrap_pull` metres (on foot nothing
//! does), with a `+4 SCRAP` line and a clink. A wreck of your own side, your own ship included,
//! drops nothing. Pickups are plain roots in the anchor's frame, so the origin rebase moves them;
//! they are dropped at a handoff to another world, as shots are.
//!
//! **Parts:** the Yard's parts rack (`station`, `Panel::Parts` in `menu`) sells hull plating,
//! shield cell, gun capacitor and missile rack, three levels each, for scrap at `part_costs`,
//! priced by your standing with the Scrappers like everything else the Yard sells
//! (`standing::price`), and not at all to someone they hunt. Bought levels are in
//! `Save::ship_parts` and kept through being shot down.
//!
//! **Modules:** each enemy hull has its own (`module_from`), dropped `module_chance` of the time
//! beside its scrap; one you already own turns into `module_scrap` scrap. Two fit at a time
//! (`Save::fitted`, from Pause > Ship), and each has an effect and a cost.
//!
//! What the parts and modules do lands on the Kestrel as a `Refit`, worked out from the save on
//! top of the hull's own numbers in `ships.toml` and the Yard's engine tune: its hull and shield
//! here, its guns in `combat`, its missiles and lock in `missile`, its boost and thrust in
//! `ship::fly`. A Kestrel fresh off the pad gets it on its first tick.

use std::collections::HashMap;

use avian3d::prelude::*;
use bevy::prelude::*;

use super::cockpit::{Cue, Sfx};
use super::combat::{wreck, Faction, Hull, ShipDestroyed, ShotLanded};
use super::enemy::Rng;
use super::missile::Missiles;
use super::orbit::STAR;
use super::ship::{clearance, Ship, Ships};
use super::standing;
use super::Solar;
use crate::comic::{display_text, ComicTheme};
use crate::controller::ControllerSet;
use crate::save::{Save, SaveFile};
use crate::surface::{Origin, Surface};
use crate::tuning::{ShipCombat, Tuning};

/// The ship parts and modules are fitted to, by id in `ships.toml`.
pub const KESTREL: &str = "kestrel";
/// How many modules fit at once.
pub const SLOTS: usize = 2;
/// A pickup pulled this close to the ship is aboard, metres, and the slowest it is pulled in, m/s.
const ABOARD: f32 = 5.0;
const PULL_SPEED: f32 = 40.0;
/// A ramming hit on the same ship counts once in this many seconds, however often they bump.
const RAM_GAP: f64 = 1.0;
/// A pickup this close over the ground rests on it, metres.
const REST: f32 = 1.0;

/// The four ship parts, in the order of `Save::ship_parts` and `[ship_combat] part_costs`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Part {
    Plating,
    Cell,
    Capacitor,
    Rack,
}

impl Part {
    pub const ALL: [Part; 4] = [Part::Plating, Part::Cell, Part::Capacitor, Part::Rack];

    pub fn name(self) -> &'static str {
        match self {
            Part::Plating => "Hull plating",
            Part::Cell => "Shield cell",
            Part::Capacitor => "Gun capacitor",
            Part::Rack => "Missile rack",
        }
    }

    /// What a level of it gives.
    pub fn gives(self, t: &ShipCombat) -> String {
        let pct = |f: f32| (f * 100.0).round() as i32;
        match self {
            Part::Plating => format!("+{:.0} hull", t.plating_hull),
            Part::Cell => format!("+{:.0} shield, back {}% faster", t.cell_shield, pct(t.cell_regen)),
            Part::Capacitor => format!("Guns heat {}% slower, cool {}% faster", pct(t.capacitor_heat), pct(t.capacitor_cool)),
            Part::Rack => format!("+{} missile, back {} s sooner", t.rack_missiles, t.rack_reload),
        }
    }
}

/// The rare drops, one per enemy hull (`[ship_combat] module_from`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Module {
    Afterburner,
    Targeting,
    Spire,
    Ram,
}

impl Module {
    pub const ALL: [Module; 4] = [Module::Afterburner, Module::Targeting, Module::Spire, Module::Ram];

    /// Its name in the save and the data files.
    pub fn id(self) -> &'static str {
        match self {
            Module::Afterburner => "afterburner",
            Module::Targeting => "targeting",
            Module::Spire => "spire",
            Module::Ram => "ram",
        }
    }

    pub fn from_id(id: &str) -> Option<Module> {
        Module::ALL.into_iter().find(|m| m.id() == id)
    }

    /// Its name on screen.
    pub fn name(self) -> &'static str {
        match self {
            Module::Afterburner => "Afterburner",
            Module::Targeting => "Targeting array",
            Module::Spire => "Spire coil",
            Module::Ram => "Ram plate",
        }
    }

    /// What it gives.
    pub fn effect(self, t: &ShipCombat) -> String {
        let pct = |f: f32| (f * 100.0).round() as i32;
        match self {
            Module::Afterburner => format!("The boost tank refills {}% faster", pct(t.afterburner_refill)),
            Module::Targeting => format!("Locks in {} s instead of {} s", t.targeting_lock, t.lock_time),
            Module::Spire => format!("Shots fly {}% faster and hit {}% harder", pct(t.spire_speed), pct(t.spire_damage)),
            Module::Ram => format!("A ramming hit on an enemy hurts it for {:.0}", t.ram_damage),
        }
    }

    /// What it costs.
    pub fn cost(self, t: &ShipCombat) -> String {
        let pct = |f: f32| (f * 100.0).round() as i32;
        match self {
            Module::Afterburner => format!("{}% less shield", pct(t.afterburner_shield)),
            Module::Targeting => format!("The lock cone is {:.0} degrees tighter", t.targeting_cone),
            Module::Spire => format!("Guns heat {}% faster", pct(t.spire_heat)),
            Module::Ram => format!("{}% less thrust", pct(t.ram_thrust)),
        }
    }
}

/// What the Kestrel's parts and fitted modules change, against its stock numbers. The default
/// changes nothing, and is what every other ship flies with.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct Refit {
    /// Hull and shield added, and the share of the shield then taken off again.
    pub hull: f32,
    pub shield: f32,
    pub shield_cut: f32,
    /// Times the stock rate: shield regeneration, gun heat a shot, gun cooling, shot speed and
    /// damage, boost refill and thrust.
    pub regen: f32,
    pub heat: f32,
    pub cool: f32,
    pub shot_speed: f32,
    pub shot_damage: f32,
    pub boost_refill: f32,
    pub thrust: f32,
    /// Missiles added, and seconds off their reload.
    pub extra_missiles: u32,
    pub reload_cut: f32,
    /// The lock's time, if a module sets it, and degrees off its cone.
    pub lock: Option<f32>,
    pub cone_cut: f32,
    /// What a ramming hit does to an enemy (none at 0).
    pub ram: f32,
}

impl Default for Refit {
    fn default() -> Self {
        Self { hull: 0.0, shield: 0.0, shield_cut: 0.0, regen: 1.0, heat: 1.0, cool: 1.0, shot_speed: 1.0, shot_damage: 1.0, boost_refill: 1.0, thrust: 1.0, extra_missiles: 0, reload_cut: 0.0, lock: None, cone_cut: 0.0, ram: 0.0 }
    }
}

impl Refit {
    /// The Kestrel as the save has it: each part's level, then each fitted module.
    pub fn of(save: &Save, t: &ShipCombat) -> Self {
        let level = |p: Part| save.ship_parts[p as usize].min(3) as f32;
        let mut r = Refit {
            hull: t.plating_hull * level(Part::Plating),
            shield: t.cell_shield * level(Part::Cell),
            regen: 1.0 + t.cell_regen * level(Part::Cell),
            heat: (1.0 - t.capacitor_heat * level(Part::Capacitor)).max(0.1),
            cool: 1.0 + t.capacitor_cool * level(Part::Capacitor),
            extra_missiles: t.rack_missiles * level(Part::Rack) as u32,
            reload_cut: t.rack_reload * level(Part::Rack),
            ..default()
        };
        for m in fitted(save) {
            match m {
                Module::Afterburner => (r.boost_refill, r.shield_cut) = (1.0 + t.afterburner_refill, t.afterburner_shield),
                Module::Targeting => (r.lock, r.cone_cut) = (Some(t.targeting_lock), t.targeting_cone),
                Module::Spire => {
                    (r.shot_speed, r.shot_damage) = (1.0 + t.spire_speed, 1.0 + t.spire_damage);
                    r.heat *= 1.0 + t.spire_heat;
                }
                Module::Ram => (r.ram, r.thrust) = (t.ram_damage, 1.0 - t.ram_thrust),
            }
        }
        r
    }

    /// The most hull and shield on a hull that has `hull` and `shield` stock.
    pub fn max_hull(&self, hull: f32) -> f32 {
        hull + self.hull
    }
    pub fn max_shield(&self, shield: f32) -> f32 {
        (shield + self.shield) * (1.0 - self.shield_cut)
    }

    /// Missiles carried, and seconds for one to come back.
    pub fn missiles(&self, t: &ShipCombat) -> u32 {
        t.missiles + self.extra_missiles
    }
    pub fn reload(&self, t: &ShipCombat) -> f32 {
        (t.missile_reload - self.reload_cut).max(1.0)
    }

    /// The lock's cone, degrees off the nose, and how long it takes.
    pub fn lock_cone(&self, t: &ShipCombat) -> f32 {
        (t.lock_cone - self.cone_cut).max(0.5)
    }
    pub fn lock_time(&self, t: &ShipCombat) -> f32 {
        self.lock.unwrap_or(t.lock_time)
    }
}

/// What a pickup holds.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Loot {
    Scrap(u32),
    Module(Module),
}

/// Salvage drifting where a ship was shot down, in the anchor's frame.
#[derive(Component, Debug)]
pub struct Pickup {
    pub loot: Loot,
    pub velocity: Vec3,
    /// Seconds before it is gone.
    pub life: f32,
    /// The ship you fly has it and is pulling it in.
    pub pulled: bool,
    spin: Vec3,
}

/// What picking something up added: scrap, and a module (`true` if it was new to you; a spare
/// is in the scrap).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Gain {
    pub scrap: u32,
    pub module: Option<(Module, bool)>,
}

/// What was last picked up, for the line over the HUD: everything picked up while it shows adds
/// together.
#[derive(Resource, Debug, Default)]
pub struct SalvageLine {
    pub scrap: u32,
    pub module: Option<(Module, bool)>,
    /// Seconds it stays up.
    pub left: f32,
}

impl SalvageLine {
    fn add(&mut self, gain: Gain, t: &ShipCombat) {
        if self.left <= 0.0 {
            (self.scrap, self.module) = (0, None);
        }
        self.scrap += gain.scrap;
        self.module = gain.module.or(self.module);
        self.left = t.scrap_line;
    }

    /// `+4 SCRAP`, `MODULE FOUND  AFTERBURNER`, `+10 SCRAP  SPARE AFTERBURNER`.
    pub fn text(&self) -> String {
        let mut out: Vec<String> = Vec::new();
        if self.scrap > 0 {
            out.push(format!("+{} SCRAP", self.scrap));
        }
        match self.module {
            Some((m, true)) => out.push(format!("MODULE FOUND  {}", m.name().to_uppercase())),
            Some((m, false)) => out.push(format!("SPARE {}", m.name().to_uppercase())),
            None => {}
        }
        out.join("  ")
    }
}

/// The roll for module drops: seeded, so a run is repeatable, and a test can set it.
#[derive(Resource)]
pub struct Luck(pub Rng);

impl Default for Luck {
    fn default() -> Self {
        Luck(Rng(0x9e37_79b9_7f4a_7c15))
    }
}

/// What a shot-down hull `id` drops, for a module roll `roll` (0 to 1): its scrap, and its module
/// when the roll comes in under `module_chance`.
pub fn loot(id: &str, roll: f32, t: &ShipCombat) -> Vec<Loot> {
    let mut out = Vec::new();
    if let Some(&n) = t.scrap.get(id).filter(|n| **n > 0) {
        out.push(Loot::Scrap(n));
    }
    if roll < t.module_chance
        && let Some(m) = t.module_from.get(id).and_then(|m| Module::from_id(m))
    {
        out.push(Loot::Module(m));
    }
    out
}

/// Takes `loot` aboard into `save`: scrap adds up, a new module is yours, a spare is scrap.
pub fn collect(save: &mut Save, loot: Loot, t: &ShipCombat) -> Gain {
    match loot {
        Loot::Scrap(n) => {
            save.scrap = save.scrap.saturating_add(n);
            Gain { scrap: n, module: None }
        }
        Loot::Module(m) if owns(save, m) => {
            save.scrap = save.scrap.saturating_add(t.module_scrap);
            Gain { scrap: t.module_scrap, module: Some((m, false)) }
        }
        Loot::Module(m) => {
            save.modules.push(m.id().to_string());
            Gain { scrap: 0, module: Some((m, true)) }
        }
    }
}

/// What buying a part came to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Sale {
    /// Bought, for this much scrap.
    Bought(u32),
    /// This much scrap short.
    Short(u32),
    /// Already at the top level.
    Top,
    /// The faction hunts you and will not sell.
    Refused,
}

/// What the next level of part `part` costs at a base of `faction`, in scrap, priced by your
/// standing as everything else there is; `None` once it is at the top.
pub fn price(save: &Save, part: Part, faction: Faction, t: &ShipCombat) -> Option<u32> {
    let cost = t.part_costs[part as usize].get(save.ship_parts[part as usize] as usize)?;
    Some(standing::price(*cost, faction, save, t))
}

/// Buys the next level of `part` from a base of `faction` with scrap from `save`.
pub fn buy(save: &mut Save, part: Part, faction: Faction, t: &ShipCombat) -> Sale {
    if standing::hunted(save, faction, t) {
        return Sale::Refused;
    }
    let Some(cost) = price(save, part, faction, t) else { return Sale::Top };
    if save.scrap < cost {
        return Sale::Short(cost - save.scrap);
    }
    save.scrap -= cost;
    save.ship_parts[part as usize] += 1;
    Sale::Bought(cost)
}

/// Whether module `m` is yours.
pub fn owns(save: &Save, m: Module) -> bool {
    save.modules.iter().any(|id| id == m.id())
}

/// The modules you own, in the order they are listed.
pub fn owned(save: &Save) -> Vec<Module> {
    Module::ALL.into_iter().filter(|m| owns(save, *m)).collect()
}

/// The modules fitted, in slot order: ones you own, each once, at most `SLOTS`, whatever the
/// save file says.
pub fn fitted(save: &Save) -> Vec<Module> {
    let mut out: Vec<Module> = Vec::new();
    for m in save.fitted.iter().filter_map(|id| Module::from_id(id)) {
        if owns(save, m) && !out.contains(&m) && out.len() < SLOTS {
            out.push(m);
        }
    }
    out
}

/// Fits module `m` in the first free slot; false if it is not yours, already in, or both slots
/// are taken.
pub fn fit(save: &mut Save, m: Module) -> bool {
    let now = fitted(save);
    if !owns(save, m) || now.contains(&m) || now.len() >= SLOTS {
        return false;
    }
    save.fitted = now.iter().chain([&m]).map(|m| m.id().to_string()).collect();
    true
}

/// Steps slot `slot` to the next module in `dir` that is yours and not in the other slot, or to
/// empty. Emptying the first slot moves the second up into it.
pub fn cycle(save: &mut Save, slot: usize, dir: i32) {
    let mut now = fitted(save);
    let here = now.get(slot).copied();
    let choices: Vec<Option<Module>> = std::iter::once(None).chain(owned(save).into_iter().filter(|m| !now.contains(m) || Some(*m) == here).map(Some)).collect();
    let at = choices.iter().position(|c| *c == here).unwrap_or(0) as i32;
    let next = choices[(at + dir.signum()).rem_euclid(choices.len() as i32) as usize];
    match (next, slot < now.len()) {
        (Some(m), true) => now[slot] = m,
        (Some(m), false) => now.push(m),
        (None, true) => {
            now.remove(slot);
        }
        (None, false) => {}
    }
    save.fitted = now.iter().map(|m| m.id().to_string()).collect();
}

/// `RUST_REGIME_MODULES=afterburner,spire`: the modules a dev aid gives you (the first two
/// fitted), for screenshots.
pub fn modules_from_env(spec: &str) -> Vec<Module> {
    spec.split(',').filter_map(|id| Module::from_id(id.trim())).collect()
}

/// `RUST_REGIME_PARTS=1,2,0,3`: the part levels a dev aid sets, each up to 3.
pub fn parts_from_env(spec: &str) -> [u8; 4] {
    let mut out = [0; 4];
    for (slot, v) in spec.split(',').take(4).enumerate() {
        out[slot] = v.trim().parse::<u8>().unwrap_or(0).min(3);
    }
    out
}

/// What scrap and modules look like: a few glowing chunks of hull, and a cyan box.
#[derive(Resource)]
struct SalvageLook {
    chunk: Handle<Mesh>,
    scrap: Handle<StandardMaterial>,
    module: Handle<StandardMaterial>,
}

#[derive(Component)]
struct SalvageText;

pub fn build(app: &mut App) {
    app.init_resource::<Luck>()
        .init_resource::<SalvageLine>()
        .add_systems(Startup, (load_look, spawn_line, dev_salvage))
        .add_systems(Update, show)
        .add_systems(
            FixedUpdate,
            (refit.before(super::ship::fly), ram.after(ControllerSet).before(wreck), (drop_salvage, gather).chain().after(wreck), tick),
        );
}

fn load_look(mut commands: Commands, meshes: Option<ResMut<Assets<Mesh>>>, materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    commands.insert_resource(SalvageLook {
        chunk: meshes.add(Cuboid::from_length(1.0)),
        scrap: materials.add(StandardMaterial { base_color: Color::srgb(0.55, 0.36, 0.2), emissive: LinearRgba::rgb(6.0, 2.6, 0.5), metallic: 0.7, perceptual_roughness: 0.5, ..default() }),
        module: materials.add(StandardMaterial { base_color: Color::srgb(0.2, 0.8, 0.9), emissive: LinearRgba::rgb(1.0, 8.0, 10.0), metallic: 0.4, perceptual_roughness: 0.3, ..default() }),
    });
}

/// Dev aids for screenshots: `RUST_REGIME_SCRAP=<n>` sets your scrap, `RUST_REGIME_PARTS=1,2,0,3`
/// the part levels and `RUST_REGIME_MODULES=afterburner,spire` the modules you own (the first two
/// fitted). Like `RUST_REGIME_STANDING` it is saved with the next save, so pair it with
/// `RUST_REGIME_SAVE`.
fn dev_salvage(save: Option<ResMut<Save>>) {
    let Some(mut save) = save else { return };
    if let Some(n) = std::env::var("RUST_REGIME_SCRAP").ok().and_then(|v| v.trim().parse().ok()) {
        save.scrap = n;
    }
    if let Ok(spec) = std::env::var("RUST_REGIME_PARTS") {
        save.ship_parts = parts_from_env(&spec);
    }
    if let Ok(spec) = std::env::var("RUST_REGIME_MODULES") {
        let found = modules_from_env(&spec);
        save.modules = found.iter().map(|m| m.id().to_string()).collect();
        save.fitted = found.iter().take(SLOTS).map(|m| m.id().to_string()).collect();
    }
}

/// Keeps the Kestrel's `Refit` in step with the save: its hull and shield move by what changed
/// (a part bought, a module fitted or taken out), and its missiles by the rack. A Kestrel fresh
/// off the pad has none yet, so it gets everything at once.
fn refit(mut commands: Commands, tuning: Res<Tuning>, specs: Res<Ships>, save: Option<Res<Save>>, mut ships: Query<(Entity, &Ship, &mut Hull, Option<&mut Missiles>, Option<&Refit>)>) {
    let t = &tuning.ship_combat;
    let want = save.as_deref().map_or_else(Refit::default, |s| Refit::of(s, t));
    for (e, ship, mut hull, missiles, had) in &mut ships {
        let spec = &specs.ship[ship.spec];
        if spec.id != KESTREL || had == Some(&want) {
            continue;
        }
        let was = had.copied().unwrap_or_default();
        hull.max_hp = want.max_hull(spec.hull);
        if hull.hp > 0.0 {
            hull.hp = (hull.hp + want.hull - was.hull).clamp(1.0, hull.max_hp);
        }
        let (old, new) = (was.max_shield(spec.shield), want.max_shield(spec.shield));
        hull.max_shield = new;
        hull.shield = (hull.shield + (new - old).max(0.0)).min(new);
        hull.regen = want.regen;
        if let Some(mut m) = missiles {
            m.count = (m.count + want.extra_missiles.saturating_sub(was.extra_missiles)).min(want.missiles(t));
        }
        // It hears its own collisions, for the ram plate.
        commands.entity(e).insert((want, CollisionEventsEnabled));
    }
}

/// A ship with a ram plate that runs into a ship of another side hurts it, once a bump.
#[allow(clippy::type_complexity)]
fn ram(
    time: Res<Time>,
    tuning: Res<Tuning>,
    mut bumps: MessageReader<CollisionStart>,
    mut landed: MessageWriter<ShotLanded>,
    rams: Query<(&Refit, &Faction)>,
    mut hulls: Query<(&mut Hull, &Faction)>,
    mut last: Local<HashMap<(Entity, Entity), f64>>,
) {
    let now = time.elapsed_secs_f64();
    last.retain(|_, at| now - *at < RAM_GAP);
    for bump in bumps.read() {
        let (Some(a), Some(b)) = (bump.body1, bump.body2) else { continue };
        for (me, other) in [(a, b), (b, a)] {
            let Ok((r, mine)) = rams.get(me).map(|(r, f)| (*r, *f)) else { continue };
            if r.ram <= 0.0 || me == other || last.contains_key(&(me, other)) {
                continue;
            }
            let Ok((mut hull, theirs)) = hulls.get_mut(other) else { continue };
            if *theirs == mine {
                continue;
            }
            hull.hit_by(r.ram, me, &tuning.ship_combat);
            landed.write(ShotLanded { by: me, on: other });
            last.insert((me, other), now);
        }
    }
}

/// Each wreck of an enemy hull drops its scrap where it blew apart, moving as it was, and now and
/// then its module beside it.
fn drop_salvage(mut commands: Commands, tuning: Res<Tuning>, specs: Res<Ships>, look: Option<Res<SalvageLook>>, mut luck: ResMut<Luck>, mut destroyed: MessageReader<ShipDestroyed>) {
    let t = &tuning.ship_combat;
    for kill in destroyed.read() {
        if kill.faction == Faction::Deserters {
            continue;
        }
        let roll = luck.0.next();
        let side = kill.velocity.normalize_or(Vec3::Y).any_orthonormal_vector();
        for (n, loot) in loot(&specs.ship[kill.spec].id, roll, t).into_iter().enumerate() {
            let at = kill.at + side * 3.0 * n as f32;
            spawn(&mut commands, look.as_deref(), loot, at, kill.velocity, t);
        }
    }
}

impl Pickup {
    /// Fresh salvage holding `loot`, moving at `velocity`, with all its life ahead of it.
    pub fn new(loot: Loot, velocity: Vec3, t: &ShipCombat) -> Self {
        // Scrap tumbles; a module turns slowly.
        let spin = Vec3::new(0.7, 1.1, -0.5) * if matches!(loot, Loot::Module(_)) { 0.6 } else { 1.0 };
        Self { loot, velocity, life: t.scrap_life, pulled: false, spin }
    }
}

/// Puts a pickup holding `loot` at `at` (the anchor's frame), moving at `velocity`.
fn spawn(commands: &mut Commands, look: Option<&SalvageLook>, loot: Loot, at: Vec3, velocity: Vec3, t: &ShipCombat) -> Entity {
    let mut e = commands.spawn((Name::new("Salvage"), Pickup::new(loot, velocity, t), Transform::from_translation(at), Visibility::default()));
    if let Some(look) = look {
        let piece = |material: &Handle<StandardMaterial>, at: Vec3, size: Vec3| (Mesh3d(look.chunk.clone()), MeshMaterial3d(material.clone()), Transform::from_translation(at).with_scale(size), bevy::light::NotShadowCaster);
        e.with_children(|c| match loot {
            Loot::Scrap(_) => {
                c.spawn(piece(&look.scrap, Vec3::ZERO, Vec3::new(1.6, 0.7, 1.0)));
                c.spawn(piece(&look.scrap, Vec3::new(0.9, 0.5, -0.4), Vec3::new(0.8, 0.8, 1.3)));
                c.spawn(piece(&look.scrap, Vec3::new(-0.7, -0.4, 0.6), Vec3::new(1.1, 0.4, 0.6)));
            }
            Loot::Module(_) => {
                c.spawn(piece(&look.module, Vec3::ZERO, Vec3::splat(1.3)));
            }
        });
    }
    e.id()
}

/// Drifts every pickup, pulls in the ones near the ship you fly and takes them aboard, and lets
/// the old ones go. They are dropped at a handoff to another world, which only ever cuts one
/// short of its 90 seconds.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn gather(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    file: Res<SaveFile>,
    mut save: Option<ResMut<Save>>,
    mut line: ResMut<SalvageLine>,
    mut cues: MessageWriter<Cue>,
    ships: Query<(&Ship, &Transform, &LinearVelocity), Without<Pickup>>,
    mut pickups: Query<(Entity, &mut Pickup, &mut Transform)>,
    mut anchor: Local<String>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    let handoff = *anchor != solar.anchor;
    anchor.clone_from(&solar.anchor);
    // Only the ship someone sits in pulls: on foot, nothing does.
    let flown = ships.iter().find(|(s, ..)| s.pilot.is_some()).map(|(_, tf, v)| (tf.translation, v.0));
    let air = solar.anchor_body().air.as_ref().filter(|_| solar.anchor != STAR);
    for (e, mut p, mut tf) in &mut pickups {
        p.life -= dt;
        if handoff || p.life <= 0.0 {
            commands.entity(e).despawn();
            continue;
        }
        if flown.is_some_and(|(at, _)| at.distance(tf.translation) < t.scrap_pull) {
            p.pulled = true;
        }
        match flown.filter(|_| p.pulled) {
            Some((at, v)) => {
                // Pulled in faster the further it has to come, carried along with the ship.
                let rel = at - tf.translation;
                let d = rel.length();
                let closing = (d * 4.0).max(PULL_SPEED);
                if d - closing * dt <= ABOARD {
                    if let Some(save) = save.as_deref_mut() {
                        let gain = collect(save, p.loot, t);
                        file.write(save);
                        info!("salvage aboard: {gain:?}, {} scrap", save.scrap);
                        line.add(gain, t);
                        let sfx = if matches!(gain.module, Some((_, true))) { Sfx::Module } else { Sfx::Scrap };
                        cues.write(Cue { sfx, volume: 1.0, pitch: 1.0 });
                    }
                    commands.entity(e).despawn();
                    continue;
                }
                p.velocity = v + rel / d * closing;
                tf.translation += p.velocity * dt;
            }
            None => {
                p.pulled = false;
                if let Some(air) = air {
                    let density = air.density_at(surface.altitude(origin.body(tf.translation)));
                    p.velocity *= (-t.air_drag * density / 1.225 * dt).exp();
                }
                let next = tf.translation + p.velocity * dt;
                // It comes to rest on the ground, not through it.
                if solar.anchor != STAR && clearance(&solar, &surface, origin.body(next)) <= REST {
                    p.velocity = Vec3::ZERO;
                } else {
                    tf.translation = next;
                }
            }
        }
        let spin = p.spin * dt;
        tf.rotation = (Quat::from_scaled_axis(spin) * tf.rotation).normalize();
    }
}

fn tick(time: Res<Time>, mut line: ResMut<SalvageLine>) {
    line.left = (line.left - time.delta_secs()).max(0.0);
}

/// The line, under the standing line over the crosshair. It hides with the rest of the HUD
/// under the menus.
fn spawn_line(mut commands: Commands, theme: Res<ComicTheme>) {
    let t = theme.clone();
    let full = Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), justify_content: JustifyContent::Center, ..default() };
    commands.spawn((crate::hud::HudRoot, full, GlobalZIndex(5))).with_children(|p| {
        p.spawn((SalvageText, display_text("", 26.0, t.paper, &t), TextShadow { offset: Vec2::splat(3.0), color: t.ink }, Node { position_type: PositionType::Absolute, top: Val::Percent(42.5), ..default() }, Visibility::Hidden));
    });
}

fn show(line: Res<SalvageLine>, theme: Res<ComicTheme>, mut text: Query<(&mut Text, &mut TextColor, &mut Visibility), With<SalvageText>>) {
    let s = line.text();
    // Yellow for a new module, paper for scrap.
    let color = if matches!(line.module, Some((_, true))) { theme.yellow } else { theme.paper };
    for (mut text, mut c, mut v) in &mut text {
        v.set_if_neq(if line.left > 0.0 && !s.is_empty() { Visibility::Inherited } else { Visibility::Hidden });
        if text.0 != s {
            text.0.clone_from(&s);
        }
        c.0 = color;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_hull_drops_its_scrap_and_a_quarter_of_the_time_its_module() {
        let t = ShipCombat::default();
        assert_eq!(["jackal", "sentry", "censer", "welder"].map(|id| loot(id, 0.99, &t)), [[Loot::Scrap(2)], [Loot::Scrap(4)], [Loot::Scrap(5)], [Loot::Scrap(8)]]);
        assert_eq!(loot("welder", 0.1, &t), [Loot::Scrap(8), Loot::Module(Module::Ram)]);
        assert_eq!(loot("jackal", 0.24, &t)[1], Loot::Module(Module::Afterburner));
        assert_eq!(loot("sentry", 0.0, &t)[1], Loot::Module(Module::Targeting));
        assert_eq!(loot("censer", 0.0, &t)[1], Loot::Module(Module::Spire));
        assert!(loot("kestrel", 0.0, &t).is_empty(), "your own ship drops nothing");
        // The seeded roll comes in under a quarter about a quarter of the time.
        let mut luck = Luck::default();
        let n = 20_000;
        let modules = (0..n).filter(|_| loot("jackal", luck.0.next(), &t).len() == 2).count();
        let rate = modules as f32 / n as f32;
        assert!((rate - 0.25).abs() < 0.015, "modules drop {rate:.3} of the time");
    }

    #[test]
    fn a_spare_module_turns_into_scrap() {
        let t = ShipCombat::default();
        let mut save = Save::default();
        assert_eq!(collect(&mut save, Loot::Scrap(4), &t), Gain { scrap: 4, module: None });
        assert_eq!(collect(&mut save, Loot::Module(Module::Spire), &t), Gain { scrap: 0, module: Some((Module::Spire, true)) });
        assert_eq!((save.scrap, save.modules.clone()), (4, vec!["spire".to_string()]));
        assert_eq!(collect(&mut save, Loot::Module(Module::Spire), &t), Gain { scrap: 10, module: Some((Module::Spire, false)) });
        assert_eq!((save.scrap, save.modules.len()), (14, 1), "a spare is scrap, not a second one");
    }

    #[test]
    fn parts_cost_their_table_stop_at_the_third_level_and_follow_standing() {
        let t = ShipCombat::default();
        let yard = Faction::Scrappers;
        let mut save = Save { scrap: 12 + 24 + 40 + 5, ..default() };
        for (n, cost) in [12, 24, 40].into_iter().enumerate() {
            assert_eq!(buy(&mut save, Part::Plating, yard, &t), Sale::Bought(cost), "level {}", n + 1);
        }
        assert_eq!((buy(&mut save, Part::Plating, yard, &t), save.ship_parts, save.scrap), (Sale::Top, [3, 0, 0, 0], 5), "three levels and no more");
        assert_eq!(buy(&mut save, Part::Rack, yard, &t), Sale::Short(10));
        assert_eq!([Part::Cell, Part::Capacitor, Part::Rack].map(|p| price(&save, p, yard, &t)), [Some(12), Some(10), Some(15)]);
        // The Yard's standing rule: 15% off at 40, 15% on below -40, nothing at all at -60.
        save.standing.insert("scrappers".into(), 40);
        assert_eq!(price(&save, Part::Rack, yard, &t), Some(13));
        save.standing.insert("scrappers".into(), -41);
        assert_eq!(price(&save, Part::Rack, yard, &t), Some(17));
        save.standing.insert("scrappers".into(), -60);
        save.scrap = 500;
        assert_eq!((buy(&mut save, Part::Rack, yard, &t), save.scrap), (Sale::Refused, 500));
    }

    #[test]
    fn two_modules_fit_and_the_slots_step_through_what_you_own() {
        let mut save = Save::default();
        assert!(!fit(&mut save, Module::Ram), "not yours");
        save.modules = ["ram", "spire", "afterburner"].map(String::from).to_vec();
        assert!(fit(&mut save, Module::Ram) && fit(&mut save, Module::Spire));
        assert!(!fit(&mut save, Module::Afterburner), "two slots");
        assert!(!fit(&mut save, Module::Ram), "and one of each");
        assert_eq!(fitted(&save), [Module::Ram, Module::Spire]);
        // A save that says more is cut down to what it may hold.
        save.fitted = ["spire", "spire", "targeting", "ram", "afterburner"].map(String::from).to_vec();
        assert_eq!(fitted(&save), [Module::Spire, Module::Ram]);
        // Slot 2 steps past Spire (in slot 1) to the next one you own, then to empty.
        let mut save = Save { modules: ["afterburner", "spire", "ram"].map(String::from).to_vec(), fitted: vec!["spire".into()], ..default() };
        cycle(&mut save, 1, 1);
        assert_eq!(fitted(&save), [Module::Spire, Module::Afterburner]);
        cycle(&mut save, 1, 1);
        assert_eq!(fitted(&save), [Module::Spire, Module::Ram]);
        cycle(&mut save, 1, 1);
        assert_eq!(fitted(&save), [Module::Spire], "round to empty");
        cycle(&mut save, 0, -1);
        assert_eq!(fitted(&save), [Module::Afterburner], "back a step from Spire");
        cycle(&mut save, 0, -1);
        assert!(fitted(&save).is_empty(), "and back to empty");
    }

    #[test]
    fn the_refit_adds_each_parts_levels_and_each_modules_effect_and_cost() {
        let t = ShipCombat::default();
        let stock = Refit::of(&Save::default(), &t);
        assert_eq!(stock, Refit::default(), "nothing bought, nothing changes");
        let save = Save { ship_parts: [2, 1, 3, 2], ..default() };
        let r = Refit::of(&save, &t);
        assert_eq!((r.max_hull(100.0), r.max_shield(60.0), r.missiles(&t), r.reload(&t)), (150.0, 75.0, 6, 7.0));
        assert!((r.regen - 1.2).abs() < 1e-6 && (r.heat - 0.4).abs() < 1e-6 && (r.cool - 1.6).abs() < 1e-6, "{r:?}");
        let fitted = |ids: &[&str]| Refit::of(&Save { modules: ids.iter().map(|s| s.to_string()).collect(), fitted: ids.iter().map(|s| s.to_string()).collect(), ..default() }, &t);
        let near = |a: &[f32], b: &[f32]| a.iter().zip(b).all(|(a, b)| (a - b).abs() < 1e-4);
        let r = fitted(&["afterburner", "targeting"]);
        assert!(near(&[r.boost_refill, r.max_shield(60.0), r.lock_time(&t), r.lock_cone(&t)], &[1.4, 54.0, 0.8, 2.0]), "{r:?}");
        let r = fitted(&["spire", "ram"]);
        assert!(near(&[r.shot_speed, r.shot_damage, r.heat, r.ram, r.thrust], &[1.25, 1.15, 1.2, 30.0, 0.9]), "{r:?}");
    }

    #[test]
    fn the_line_adds_up_while_it_shows() {
        let t = ShipCombat::default();
        let mut line = SalvageLine::default();
        line.add(Gain { scrap: 4, module: None }, &t);
        line.add(Gain { scrap: 2, module: None }, &t);
        assert_eq!(line.text(), "+6 SCRAP");
        line.add(Gain { scrap: 0, module: Some((Module::Ram, true)) }, &t);
        assert_eq!(line.text(), "+6 SCRAP  MODULE FOUND  RAM PLATE");
        line.left = 0.0;
        line.add(Gain { scrap: 10, module: Some((Module::Ram, false)) }, &t);
        assert_eq!(line.text(), "+10 SCRAP  SPARE RAM PLATE", "a new line once the last has gone");
    }

    #[test]
    fn the_dev_switches_read_modules_and_part_levels() {
        assert_eq!(modules_from_env("afterburner, spire,nothing"), [Module::Afterburner, Module::Spire]);
        assert_eq!(parts_from_env("1,2,x,9,3"), [1, 2, 0, 3]);
    }
}
