//! Faction standing (stage 2 of ship combat, `docs/superpowers/specs/2026-10-29-ship-combat-stages-2-3-design.md`):
//! where you stand with the Regime, the Scrappers and the PMC, -100 to 100, saved in
//! `Save::standing`. You start as a stranger at `[ship_combat] standing_start` (-20) with each;
//! the Deserters are your own side and stay at `standing_deserters`; raiders have no standing and
//! always attack.
//!
//! **What moves it:** a parcel delivered to a faction's base (`station` writes `Delivered`), a
//! raider shot down by the ship you fly (with each of the three), one of a faction's ships shot
//! down (with it, and with each faction holding a grudge against it, `[ship_combat.grudges]`),
//! and your first damaging hit on one of its ships in a fight (`ShotLanded`). A kill after a hit
//! costs the kill in all, not the kill and the hit. Below the start it creeps back a point a
//! day of game time, no further than the start.
//!
//! **What it changes:** a patrol attacks you only while its faction is below 0, or once you have
//! shot it, until it lets you go (`attacks`, which `ai` asks); at `standing_hunted` or below the
//! faction hunts you (`enemy` sends the packs) and its base will not serve you; below
//! `standing_wary` the base charges more, and at `standing_friendly` or above it charges less
//! and a parcel to it pays more. The Roost is your own side's and is never affected.
//!
//! A short line over the HUD says what changed (`REGIME -25  SCRAPPERS +5`).

use std::collections::HashSet;

use bevy::prelude::*;

use super::ai::{Enemy, Role};
use super::combat::{wreck, Faction, ShipDestroyed, ShotLanded};
use super::ship::Ship;
use crate::comic::{display_text, ComicTheme};
use crate::save::{Save, SaveFile};
use crate::tuning::{ShipCombat, Tuning};

/// The factions whose standing moves, in the order they are listed.
pub const FACTIONS: [Faction; 3] = [Faction::Regime, Faction::Scrappers, Faction::Pmc];
/// Standing runs between these.
pub const MIN: i32 = -100;
pub const MAX: i32 = 100;
/// At or above this the word for it is Allied (it gives what Friendly does).
pub const ALLIED: i32 = 80;

/// A parcel was delivered to a base of `faction`.
#[derive(Message, Debug, Clone, Copy)]
pub struct Delivered {
    pub faction: Faction,
}

/// What standing last changed by, for the line over the HUD: each faction's change while the
/// line is up adds together.
#[derive(Resource, Debug, Default)]
pub struct StandingLine {
    pub shifts: Vec<(Faction, i32)>,
    /// Seconds it stays up.
    pub left: f32,
}

impl StandingLine {
    fn add(&mut self, shifts: &[(Faction, i32)], t: &ShipCombat) {
        if shifts.is_empty() {
            return;
        }
        if self.left <= 0.0 {
            self.shifts.clear();
        }
        for &(f, by) in shifts {
            match self.shifts.iter_mut().find(|(g, _)| *g == f) {
                Some((_, sum)) => *sum += by,
                None => self.shifts.push((f, by)),
            }
        }
        self.shifts.sort_by_key(|(f, _)| FACTIONS.iter().position(|g| g == f));
        self.left = t.standing_line;
    }

    /// `REGIME -25  SCRAPPERS +5`.
    pub fn text(&self) -> String {
        self.shifts.iter().filter(|(_, by)| *by != 0).map(|(f, by)| format!("{} {by:+}", f.name().to_uppercase())).collect::<Vec<_>>().join("  ")
    }
}

/// The ships whose first hit in a fight has been charged, so their kill is charged the rest.
#[derive(Resource, Debug, Default)]
struct Charged(HashSet<Entity>);

/// The words for how a faction sees you.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Level {
    Hostile,
    Wary,
    Neutral,
    Friendly,
    Allied,
}

impl Level {
    pub const ALL: [Level; 5] = [Level::Hostile, Level::Wary, Level::Neutral, Level::Friendly, Level::Allied];

    pub fn of(value: i32, t: &ShipCombat) -> Level {
        match value {
            v if v <= t.standing_hunted => Level::Hostile,
            v if v < 0 => Level::Wary,
            v if v < t.standing_friendly => Level::Neutral,
            v if v < ALLIED => Level::Friendly,
            _ => Level::Allied,
        }
    }

    pub fn word(self) -> &'static str {
        match self {
            Level::Hostile => "Hostile",
            Level::Wary => "Wary",
            Level::Neutral => "Neutral",
            Level::Friendly => "Friendly",
            Level::Allied => "Allied",
        }
    }

    /// The range of standing it covers, as the Standing screen's key shows it.
    pub fn range(self, t: &ShipCombat) -> String {
        match self {
            Level::Hostile => format!("{} or below", t.standing_hunted),
            Level::Wary => format!("{} to -1", t.standing_hunted + 1),
            Level::Neutral => format!("0 to {}", t.standing_friendly - 1),
            Level::Friendly => format!("{} to {}", t.standing_friendly, ALLIED - 1),
            Level::Allied => format!("{ALLIED} or above"),
        }
    }

    /// What it gives you.
    pub fn gives(self, t: &ShipCombat) -> String {
        let pct = |f: f32| (f * 100.0).round() as i32;
        match self {
            Level::Hostile => "Patrols shoot on sight, hunters come after you, and its base will not serve you (its courier desk still will)".into(),
            Level::Wary => format!("Patrols shoot on sight; below {} its base charges {}% more", t.standing_wary, pct(t.standing_markup)),
            Level::Neutral => "Patrols let you pass; the usual prices".into(),
            Level::Friendly | Level::Allied => format!("Patrols let you pass; {}% off at its base, and parcels to it pay {}% more", pct(t.standing_discount), pct(t.standing_bonus)),
        }
    }
}

/// Whether `faction`'s standing moves: the Deserters' and the raiders' never does.
pub fn moves(faction: Faction) -> bool {
    FACTIONS.contains(&faction)
}

/// Your standing with `faction`. The raiders have none: they are always at the bottom.
pub fn get(save: &Save, faction: Faction, t: &ShipCombat) -> i32 {
    match faction {
        Faction::Deserters => t.standing_deserters,
        Faction::Raiders => MIN,
        f => save.standing.get(f.id()).copied().unwrap_or(t.standing_start).clamp(MIN, MAX),
    }
}

/// Moves your standing with `faction` by `by`, clamped; returns how far it actually moved.
pub fn shift(save: &mut Save, faction: Faction, by: i32, t: &ShipCombat) -> i32 {
    if !moves(faction) {
        return 0;
    }
    let was = get(save, faction, t);
    let now = (was + by).clamp(MIN, MAX);
    save.standing.insert(faction.id().to_string(), now);
    now - was
}

/// Its patrols shoot you on sight.
pub fn hostile(save: &Save, faction: Faction, t: &ShipCombat) -> bool {
    get(save, faction, t) < 0
}

/// It hunts you, and its base will not serve you (but for a courier desk).
pub fn hunted(save: &Save, faction: Faction, t: &ShipCombat) -> bool {
    moves(faction) && get(save, faction, t) <= t.standing_hunted
}

/// Whether enemy pilot `enemy`, flying for `faction`, comes for you: raiders and hunters always,
/// a patrol only while its faction is hostile or since you shot it. With no save (some tests),
/// everyone does.
pub fn attacks(enemy: &Enemy, faction: Faction, save: Option<&Save>, t: &ShipCombat) -> bool {
    match enemy.role {
        Role::Patrol { .. } => enemy.provoked || save.is_none_or(|s| hostile(s, faction, t)),
        Role::Raider | Role::Hunter => true,
    }
}

/// What a base of `faction` charges for something that costs `cost`: less to a friend, more to
/// someone it is wary of. Rounded to the dollar.
pub fn price(cost: u32, faction: Faction, save: &Save, t: &ShipCombat) -> u32 {
    if !moves(faction) {
        return cost;
    }
    let v = get(save, faction, t);
    let k = if v >= t.standing_friendly {
        1.0 - t.standing_discount
    } else if v < t.standing_wary {
        1.0 + t.standing_markup
    } else {
        1.0
    };
    (cost as f32 * k).round() as u32
}

/// What a price at a base of `faction` has on it, for the prompt: ` (15% off)`, ` (15% on)` or
/// nothing.
pub fn price_note(faction: Faction, save: &Save, t: &ShipCombat) -> String {
    let v = get(save, faction, t);
    match moves(faction) {
        true if v >= t.standing_friendly => format!(" ({:.0}% off)", t.standing_discount * 100.0),
        true if v < t.standing_wary => format!(" ({:.0}% on)", t.standing_markup * 100.0),
        _ => String::new(),
    }
}

/// What the base of a faction that hunts you says instead of serving you.
pub fn refusal(faction: Faction) -> String {
    format!("The {} will not serve you: you are Hostile to them", faction.name())
}

/// The extra a parcel paying `pay` earns delivered to a base of `faction` you stand well with.
pub fn bonus(pay: u32, faction: Faction, save: &Save, t: &ShipCombat) -> u32 {
    if moves(faction) && get(save, faction, t) >= t.standing_friendly { (pay as f32 * t.standing_bonus).round() as u32 } else { 0 }
}

/// A parcel delivered to a base of `faction`.
pub fn delivered(save: &mut Save, faction: Faction, t: &ShipCombat) -> Vec<(Faction, i32)> {
    changes(save, &[(faction, t.standing_delivery)], t)
}

/// A ship of `faction` shot down by you; `charged` if its first hit already cost a little, which
/// the kill makes up to its whole price.
pub fn shot_down(save: &mut Save, faction: Faction, charged: bool, t: &ShipCombat) -> Vec<(Faction, i32)> {
    if faction == Faction::Raiders {
        return changes(save, &FACTIONS.map(|f| (f, t.standing_raider_kill)), t);
    }
    if !moves(faction) {
        return Vec::new();
    }
    let kill = if charged { t.standing_kill - t.standing_hit } else { t.standing_kill };
    let mut by = vec![(faction, kill)];
    for f in FACTIONS.into_iter().filter(|f| t.grudges.get(f.id()).is_some_and(|foes| foes.iter().any(|g| g == faction.id()))) {
        by.push((f, t.standing_rival_kill));
    }
    changes(save, &by, t)
}

/// Your first damaging hit on a ship of `faction` in a fight.
pub fn hit(save: &mut Save, faction: Faction, t: &ShipCombat) -> Vec<(Faction, i32)> {
    changes(save, &[(faction, t.standing_hit)], t)
}

/// `dt` seconds of game time: each standing below the start creeps back a point a day.
pub fn recover(save: &mut Save, dt: f32, t: &ShipCombat) -> bool {
    save.standing_clock += dt;
    if save.standing_clock < t.standing_day {
        return false;
    }
    save.standing_clock -= t.standing_day;
    let mut moved = false;
    for f in FACTIONS {
        let v = get(save, f, t);
        if v < t.standing_start {
            save.standing.insert(f.id().to_string(), (v + t.standing_recovery).min(t.standing_start));
            moved = true;
        }
    }
    moved
}

/// Applies each shift, and returns the ones that moved anything.
fn changes(save: &mut Save, by: &[(Faction, i32)], t: &ShipCombat) -> Vec<(Faction, i32)> {
    by.iter().map(|&(f, d)| (f, shift(save, f, d, t))).filter(|(_, d)| *d != 0).collect()
}

/// `RUST_REGIME_STANDING=regime:50,pmc:-70`: a dev aid that sets standing at startup, for
/// screenshots.
pub fn from_env(spec: &str) -> Vec<(Faction, i32)> {
    spec.split(',').filter_map(|pair| {
        let (id, v) = pair.split_once(':')?;
        Some((Faction::from_id(id.trim()).filter(|f| moves(*f))?, v.trim().parse().ok()?))
    }).collect()
}

#[derive(Component)]
struct StandingText;

pub fn build(app: &mut App) {
    app.add_message::<Delivered>()
        .init_resource::<StandingLine>()
        .init_resource::<Charged>()
        .add_systems(Startup, (spawn_line, dev_standing))
        .add_systems(Update, show)
        .add_systems(FixedUpdate, (judge.after(wreck), tick));
}

fn dev_standing(save: Option<ResMut<Save>>) {
    let (Some(mut save), Ok(spec)) = (save, std::env::var("RUST_REGIME_STANDING")) else { return };
    for (f, v) in from_env(&spec) {
        save.standing.insert(f.id().to_string(), v.clamp(MIN, MAX));
    }
}

/// What the ship you fly did this tick, and the parcels delivered: each moves standing by the
/// table, saved, with the line over the HUD.
#[allow(clippy::too_many_arguments)]
fn judge(
    tuning: Res<Tuning>,
    file: Res<SaveFile>,
    save: Option<ResMut<Save>>,
    mut line: ResMut<StandingLine>,
    mut charged: ResMut<Charged>,
    mut landed: MessageReader<ShotLanded>,
    mut destroyed: MessageReader<ShipDestroyed>,
    mut delivered: MessageReader<Delivered>,
    ships: Query<(Entity, &Ship)>,
    mut enemies: Query<(&mut Enemy, &super::combat::Faction)>,
) {
    let Some(mut save) = save else {
        landed.clear();
        destroyed.clear();
        delivered.clear();
        return;
    };
    let t = &tuning.ship_combat;
    let flown = ships.iter().find(|(_, s)| s.pilot.is_some()).map(|(e, _)| e);
    let mut moved = Vec::new();
    for shot in landed.read() {
        if Some(shot.by) != flown {
            continue;
        }
        let Ok((mut enemy, faction)) = enemies.get_mut(shot.on) else { continue };
        if moves(*faction) && !enemy.provoked {
            enemy.provoked = true;
            charged.0.insert(shot.on);
            moved.extend(self::hit(&mut save, *faction, t));
        }
    }
    for kill in destroyed.read() {
        let Some(killer) = kill.killer.filter(|k| *k != kill.ship) else { continue };
        if !ships.get(killer).is_ok_and(|(_, s)| s.pilot.is_some()) {
            continue;
        }
        let was_charged = charged.0.remove(&kill.ship);
        moved.extend(shot_down(&mut save, kill.faction, was_charged, t));
    }
    for d in delivered.read() {
        moved.extend(self::delivered(&mut save, d.faction, t));
    }
    // Ships gone without a kill (left behind, another world) are forgotten.
    charged.0.retain(|e| enemies.contains(*e));
    if !moved.is_empty() {
        info!("standing: {:?}", save.standing);
        file.write(&save);
        line.add(&moved, t);
    }
}

/// Runs the recovery clock and the line's.
fn tick(time: Res<Time>, tuning: Res<Tuning>, file: Res<SaveFile>, save: Option<ResMut<Save>>, mut line: ResMut<StandingLine>) {
    line.left = (line.left - time.delta_secs()).max(0.0);
    let Some(mut save) = save else { return };
    if recover(&mut save, time.delta_secs(), &tuning.ship_combat) {
        file.write(&save);
    }
}

/// The line, under the bounty line over the crosshair, in the comic HUD's ink. It hides with the
/// rest of the HUD under the menus.
fn spawn_line(mut commands: Commands, theme: Res<ComicTheme>) {
    let t = theme.clone();
    let full = Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), justify_content: JustifyContent::Center, ..default() };
    commands.spawn((crate::hud::HudRoot, full, GlobalZIndex(5))).with_children(|p| {
        p.spawn((StandingText, display_text("", 26.0, t.paper, &t), TextShadow { offset: Vec2::splat(3.0), color: t.ink }, Node { position_type: PositionType::Absolute, top: Val::Percent(38.5), ..default() }, Visibility::Hidden));
    });
}

fn show(line: Res<StandingLine>, theme: Res<ComicTheme>, mut text: Query<(&mut Text, &mut TextColor, &mut Visibility), With<StandingText>>) {
    let s = line.text();
    // Red when anyone thinks less of you, paper when it is all good news.
    let color = if line.shifts.iter().any(|(_, by)| *by < 0) { theme.red } else { theme.paper };
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
    fn a_stranger_starts_hostile_and_the_deserters_stay_put() {
        let t = ShipCombat::default();
        let mut save = Save::default();
        assert!(FACTIONS.iter().all(|f| get(&save, *f, &t) == -20 && hostile(&save, *f, &t)));
        assert_eq!(get(&save, Faction::Deserters, &t), 50);
        assert_eq!(shift(&mut save, Faction::Deserters, -40, &t), 0, "your own side never moves");
        assert_eq!(get(&save, Faction::Deserters, &t), 50);
        assert_eq!(shift(&mut save, Faction::Raiders, 40, &t), 0, "raiders have no standing");
        assert!(hostile(&save, Faction::Raiders, &t));
    }

    #[test]
    fn standing_clamps_to_a_hundred_either_way() {
        let t = ShipCombat::default();
        let mut save = Save::default();
        assert_eq!(shift(&mut save, Faction::Pmc, 500, &t), 120);
        assert_eq!(get(&save, Faction::Pmc, &t), 100);
        assert_eq!(shift(&mut save, Faction::Pmc, 1, &t), 0);
        assert_eq!(shift(&mut save, Faction::Regime, -500, &t), -80);
        assert_eq!(get(&save, Faction::Regime, &t), -100);
    }

    #[test]
    fn the_movers_go_by_the_table() {
        let t = ShipCombat::default();
        let mut save = Save::default();
        assert_eq!(delivered(&mut save, Faction::Scrappers, &t), [(Faction::Scrappers, 10)]);
        assert!(delivered(&mut save, Faction::Deserters, &t).is_empty(), "the Roost's parcels move nothing");
        assert_eq!(shot_down(&mut save, Faction::Raiders, false, &t), [(Faction::Regime, 2), (Faction::Scrappers, 2), (Faction::Pmc, 2)]);
        // The Scrappers hold a grudge against the Regime, and the Regime against the Scrappers.
        assert_eq!(shot_down(&mut save, Faction::Regime, false, &t), [(Faction::Regime, -25), (Faction::Scrappers, 5)]);
        assert_eq!(shot_down(&mut save, Faction::Scrappers, false, &t), [(Faction::Scrappers, -25), (Faction::Regime, 5)]);
        // The Scrappers distrust the PMC; the PMC holds no grudge.
        assert_eq!(shot_down(&mut save, Faction::Pmc, false, &t), [(Faction::Pmc, -25), (Faction::Scrappers, 5)]);
        assert_eq!(hit(&mut save, Faction::Pmc, &t), [(Faction::Pmc, -3)]);
        assert_eq!(shot_down(&mut save, Faction::Pmc, true, &t)[0], (Faction::Pmc, -22), "after its hit, the kill costs the rest of the 25");
        assert_eq!(get(&save, Faction::Pmc, &t), -20 + 2 - 25 - 3 - 22);
    }

    #[test]
    fn below_the_start_it_creeps_back_a_point_a_day_and_no_further() {
        let t = ShipCombat::default();
        let mut save = Save::default();
        shift(&mut save, Faction::Regime, -2, &t);
        shift(&mut save, Faction::Pmc, 30, &t);
        assert!(!recover(&mut save, t.standing_day - 1.0, &t), "not a day yet");
        assert!(recover(&mut save, 1.0, &t));
        assert_eq!((get(&save, Faction::Regime, &t), get(&save, Faction::Scrappers, &t), get(&save, Faction::Pmc, &t)), (-21, -20, 10), "only what was pushed below the start");
        recover(&mut save, t.standing_day, &t);
        recover(&mut save, t.standing_day, &t);
        assert_eq!(get(&save, Faction::Regime, &t), -20, "back to the start and no further");
    }

    #[test]
    fn prices_and_pay_follow_standing() {
        let t = ShipCombat::default();
        let mut save = Save::default();
        assert_eq!(price(300, Faction::Scrappers, &save, &t), 300, "a stranger pays the usual");
        save.standing.insert("scrappers".into(), 40);
        assert_eq!((price(300, Faction::Scrappers, &save, &t), bonus(250, Faction::Scrappers, &save, &t)), (255, 50), "friendly at 40: 15% off, 20% more pay");
        save.standing.insert("scrappers".into(), -40);
        assert_eq!(price(300, Faction::Scrappers, &save, &t), 300, "at -40 still the usual");
        save.standing.insert("scrappers".into(), -41);
        assert_eq!((price(300, Faction::Scrappers, &save, &t), bonus(250, Faction::Scrappers, &save, &t)), (345, 0), "below -40: 15% on");
        assert!(!hunted(&save, Faction::Scrappers, &t));
        save.standing.insert("scrappers".into(), -60);
        assert!(hunted(&save, Faction::Scrappers, &t), "refused and hunted at -60");
        assert_eq!((price(400, Faction::Deserters, &save, &t), bonus(250, Faction::Deserters, &save, &t)), (400, 0), "the Roost is unaffected");
        assert!(!hunted(&save, Faction::Deserters, &t) && !hunted(&save, Faction::Raiders, &t));
    }

    #[test]
    fn each_level_has_its_word() {
        let t = ShipCombat::default();
        let words: Vec<&str> = [-100, -60, -59, -1, 0, 39, 40, 79, 80, 100].map(|v| Level::of(v, &t).word()).to_vec();
        assert_eq!(words, ["Hostile", "Hostile", "Wary", "Wary", "Neutral", "Neutral", "Friendly", "Friendly", "Allied", "Allied"]);
        assert!(Level::ALL.iter().all(|l| !l.gives(&t).is_empty()));
    }

    #[test]
    fn the_line_adds_up_while_it_shows() {
        let t = ShipCombat::default();
        let mut line = StandingLine::default();
        line.add(&[(Faction::Pmc, 2), (Faction::Regime, 2)], &t);
        line.add(&[(Faction::Regime, -25), (Faction::Scrappers, 5)], &t);
        assert_eq!(line.text(), "REGIME -23  SCRAPPERS +5  PMC +2");
        line.left = 0.0;
        line.add(&[(Faction::Regime, -3)], &t);
        assert_eq!(line.text(), "REGIME -3", "a new line once the last has gone");
    }

    #[test]
    fn the_dev_switch_reads_faction_and_value_pairs() {
        assert_eq!(from_env("regime:50, pmc:-70,deserters:0,nobody:3,scrappers:x"), [(Faction::Regime, 50), (Faction::Pmc, -70)]);
    }
}
