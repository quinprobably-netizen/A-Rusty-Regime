//! The front end: title screen, pause menu, settings, controls sheet, quartermaster and wardrobe, all
//! Bevy UI over the live world. Titanfall-style: a tall uppercase list on the left, the island
//! behind it, button hints along the bottom. Time stands still while a menu is up.
//!
//! `RUST_REGIME_MENU=title|pause|settings|controls|maps|quartermaster|wardrobe` opens straight into a
//! screen (handy with `RUST_REGIME_SCREENSHOT`).

use bevy::app::AppExit;
use bevy::audio::{GlobalVolume, Volume};
use bevy::light::CascadeShadowConfigBuilder;
use bevy::prelude::*;
use bevy::ui::{ColorStop, LinearGradient, BackgroundGradient};
use bevy::window::{CursorGrabMode, CursorOptions};
use serde::{Deserialize, Serialize};

use crate::abilities::Class;
use crate::camera::PlayerCamera;
use crate::character::{Characters, OutfitDef};
use crate::gunsmith::{self, Loadout, PARTS, SLOTS, TUNE_MAX, TUNES};
use crate::hud::HudRoot;
use crate::loot::{Save, SaveFile};
use crate::quartermaster::{self, Sale};
use crate::tuning::Tuning;
use crate::wardrobe::{self, Wardrobe};
use crate::weapon::{Arsenal, WEAPONS};

/// Title at boot, then playing or paused. Time runs only while playing.
#[derive(States, Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum Screen {
    #[default]
    Title,
    Playing,
    Paused,
}

/// What the menu shows on top of the title or pause screen.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Panel {
    #[default]
    Main,
    Maps,
    Settings,
    Controls,
    /// The Roost's counter: guns and attachments, bought with banked money.
    Quartermaster,
    Wardrobe,
}

/// What the camera presents while a panel is open.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Showcase {
    None,
    /// The first-person weapon turned to the camera (quartermaster).
    Gun,
    /// The worn character in the dressing room (wardrobe).
    Body,
}

#[derive(Resource, Debug, Default)]
pub struct Menu {
    pub panel: Panel,
    /// Highlighted row, counting only selectable rows.
    pub cursor: usize,
    pub playing: bool,
    /// The counter was opened by walking up to it in the world: Back returns to the game.
    pub from_station: bool,
    /// The last thing the counter said: a sale, or why there was none.
    pub note: String,
}

/// Set by the quartermaster's station: open the counter when the pause screen comes up.
#[derive(Resource, Default)]
pub struct Counter(pub bool);

impl Menu {
    pub fn showcase(&self) -> Showcase {
        match self.panel {
            _ if self.playing => Showcase::None,
            Panel::Quartermaster => Showcase::Gun,
            Panel::Wardrobe => Showcase::Body,
            _ => Showcase::None,
        }
    }
}

// ------------------------------------------------------------------------------------ settings

const SETTINGS_PATH: &str = "settings.toml";

/// What the settings screen edits, saved to `settings.toml` and laid over `tuning.toml`.
#[derive(Resource, Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Settings {
    pub mouse_sensitivity: f32,
    pub invert_y: bool,
    pub fov_degrees: f32,
    pub third_person: bool,
    pub master: f32,
    pub guns: f32,
    pub effects: f32,
    pub engine: f32,
    pub ambience: f32,
    pub atmosphere: bool,
    pub bloom: bool,
    pub ssao: bool,
    pub taa: bool,
    pub shadow_distance: f32,
    pub grass: bool,
    pub trees: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Self::from_tuning(&Tuning::default())
    }
}

impl Settings {
    pub fn from_tuning(t: &Tuning) -> Self {
        let g = &t.graphics;
        let s = &t.sound;
        Self {
            mouse_sensitivity: t.mouse_sensitivity,
            invert_y: t.invert_y,
            fov_degrees: t.fov_degrees,
            third_person: t.third_person,
            master: s.master,
            guns: s.guns,
            effects: s.effects,
            engine: s.engine,
            ambience: s.ambience,
            atmosphere: g.atmosphere,
            bloom: g.bloom,
            ssao: g.ssao,
            taa: g.taa,
            shadow_distance: g.shadow_distance,
            grass: g.grass,
            trees: g.trees,
        }
    }

    pub fn apply(&self, t: &mut Tuning) {
        t.mouse_sensitivity = self.mouse_sensitivity;
        t.invert_y = self.invert_y;
        t.fov_degrees = self.fov_degrees;
        t.third_person = self.third_person;
        t.sound.master = self.master;
        t.sound.guns = self.guns;
        t.sound.effects = self.effects;
        t.sound.engine = self.engine;
        t.sound.ambience = self.ambience;
        t.graphics.atmosphere = self.atmosphere;
        t.graphics.bloom = self.bloom;
        t.graphics.ssao = self.ssao;
        t.graphics.taa = self.taa;
        t.graphics.shadow_distance = self.shadow_distance;
        t.graphics.grass = self.grass;
        t.graphics.trees = self.trees;
    }

    /// The saved settings, if the player changed any.
    pub fn load() -> Option<Self> {
        let text = std::fs::read_to_string(SETTINGS_PATH).ok()?;
        toml::from_str(&text).map_err(|e| warn!("{SETTINGS_PATH} is invalid, ignoring it: {e}")).ok()
    }

    pub fn save(&self) {
        // Tests must not leave a settings.toml behind for the next run to load.
        if cfg!(test) {
            return;
        }
        if let Ok(text) = toml::to_string(self)
            && let Err(e) = std::fs::write(SETTINGS_PATH, text)
        {
            warn!("could not write {SETTINGS_PATH}: {e}");
        }
    }
}

#[derive(Clone, Copy)]
enum Kind {
    Slider { min: f32, max: f32, step: f32, fmt: fn(f32) -> String },
    Toggle,
    Choice(&'static [(&'static str, f32)]),
}

/// One adjustable row of the settings screen.
struct Field {
    label: &'static str,
    kind: Kind,
    /// Shown as a footnote when set.
    restart: bool,
    get: fn(&Settings) -> f32,
    set: fn(&mut Settings, f32),
}

const fn field(label: &'static str, kind: Kind, restart: bool, get: fn(&Settings) -> f32, set: fn(&mut Settings, f32)) -> Field {
    Field { label, kind, restart, get, set }
}

fn pct(v: f32) -> String {
    format!("{:.0}%", v * 100.0)
}
fn int(v: f32) -> String {
    format!("{v:.0}")
}
fn sens(v: f32) -> String {
    format!("{:.1}", v * 1000.0)
}
fn bool_f(b: bool) -> f32 {
    if b { 1.0 } else { 0.0 }
}

const VOLUME: Kind = Kind::Slider { min: 0.0, max: 1.0, step: 0.1, fmt: pct };
const SHADOWS: &[(&str, f32)] = &[("NEAR", 250.0), ("NORMAL", 500.0), ("FAR", 1000.0), ("VERY FAR", 2000.0)];
const TREES: &[(&str, f32)] = &[("NONE", 0.0), ("SPARSE", 0.5), ("NORMAL", 1.0), ("DENSE", 1.5)];

/// Section headings and the fields under them.
const SECTIONS: &[(&str, &[Field])] = &[
    (
        "LOOK",
        &[
            field("MOUSE SENSITIVITY", Kind::Slider { min: 0.0005, max: 0.01, step: 0.0005, fmt: sens }, false, |s| s.mouse_sensitivity, |s, v| s.mouse_sensitivity = v),
            field("INVERT Y", Kind::Toggle, false, |s| bool_f(s.invert_y), |s, v| s.invert_y = v > 0.5),
            field("FIELD OF VIEW", Kind::Slider { min: 60.0, max: 110.0, step: 5.0, fmt: int }, false, |s| s.fov_degrees, |s, v| s.fov_degrees = v),
            field("THIRD PERSON", Kind::Toggle, false, |s| bool_f(s.third_person), |s, v| s.third_person = v > 0.5),
        ],
    ),
    (
        "SOUND",
        &[
            field("MASTER", VOLUME, false, |s| s.master, |s, v| s.master = v),
            field("GUNS", VOLUME, false, |s| s.guns, |s, v| s.guns = v),
            field("EFFECTS", VOLUME, false, |s| s.effects, |s, v| s.effects = v),
            field("ENGINES", VOLUME, false, |s| s.engine, |s, v| s.engine = v),
            field("AMBIENCE", VOLUME, false, |s| s.ambience, |s, v| s.ambience = v),
        ],
    ),
    (
        "GRAPHICS",
        &[
            field("PHYSICAL SKY", Kind::Toggle, true, |s| bool_f(s.atmosphere), |s, v| s.atmosphere = v > 0.5),
            field("BLOOM", Kind::Toggle, false, |s| bool_f(s.bloom), |s, v| s.bloom = v > 0.5),
            field("AMBIENT OCCLUSION", Kind::Toggle, false, |s| bool_f(s.ssao), |s, v| s.ssao = v > 0.5),
            field("ANTI-ALIASING", Kind::Toggle, false, |s| bool_f(s.taa), |s, v| s.taa = v > 0.5),
            field("SHADOW DISTANCE", Kind::Choice(SHADOWS), false, |s| s.shadow_distance, |s, v| s.shadow_distance = v),
            field("GRASS", Kind::Toggle, false, |s| bool_f(s.grass), |s, v| s.grass = v > 0.5),
            field("TREES", Kind::Choice(TREES), true, |s| s.trees, |s, v| s.trees = v),
        ],
    ),
];

fn fields() -> impl Iterator<Item = &'static Field> {
    SECTIONS.iter().flat_map(|(_, f)| f.iter())
}

/// Step a field by `dir` (+1 / -1): sliders clamp, toggles flip, choices wrap.
pub fn step_field(index: usize, dir: i32, settings: &mut Settings) {
    let Some(f) = fields().nth(index) else { return };
    let v = (f.get)(settings);
    let new = match f.kind {
        Kind::Slider { min, max, step, .. } => (v + step * dir as f32).clamp(min, max),
        Kind::Toggle => 1.0 - v.round(),
        Kind::Choice(opts) => {
            let at = opts.iter().position(|(_, o)| (*o - v).abs() < 1e-3).unwrap_or(0) as i32;
            opts[(at + dir).rem_euclid(opts.len() as i32) as usize].1
        }
    };
    (f.set)(settings, new);
}

/// The text shown for a field's value and, for sliders, how full its bar is.
fn field_value(f: &Field, settings: &Settings) -> (String, Option<f32>) {
    let v = (f.get)(settings);
    match f.kind {
        Kind::Slider { min, max, fmt, .. } => (fmt(v), Some((v - min) / (max - min))),
        Kind::Toggle => (if v > 0.5 { "ON" } else { "OFF" }.into(), None),
        Kind::Choice(opts) => (opts.iter().find(|(_, o)| (*o - v).abs() < 1e-3).map_or("?", |(n, _)| n).into(), None),
    }
}

// -------------------------------------------------------------------------------------- rows

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Action {
    Play,
    Resume,
    Maps,
    Wardrobe,
    Settings,
    Controls,
    Quit,
    Back,
    /// A random look in the wardrobe.
    Randomize,
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum Row {
    Section(&'static str),
    Action(&'static str, Action),
    Field(usize),
    /// The quartermaster's weapon picker: every gun for sale, owned or not.
    Weapon,
    /// An attachment slot of the gun on the counter.
    Slot(usize),
    /// The tuning slider under a fitted part.
    Tune(usize),
    /// The wardrobe's preset picker.
    Preset,
    /// A wardrobe slot (an entry of `wardrobe::SLOTS`).
    Look(usize),
    /// An entry of [`MAPS`].
    Map(usize),
}

/// A level to launch: its `RUST_REGIME_LEVEL` and `RUST_REGIME_MODE`, then name and blurb.
struct MapDef {
    level: &'static str,
    mode: &'static str,
    name: &'static str,
    desc: &'static str,
}

/// The island, arena and moon are still reachable with `RUST_REGIME_LEVEL`, just not from the menu.
const MAPS: &[MapDef] = &[
    MapDef { level: "system", mode: "", name: "SOLAR SYSTEM", desc: "Haven, its moon Ash and your ship: fly between worlds" },
];

/// The [`MAPS`] entry this run was started with. An unknown level is the solar system, as in `main`.
fn current_map() -> usize {
    let level = std::env::var("RUST_REGIME_LEVEL").ok();
    let level = match level.as_deref() {
        Some(l @ ("island" | "arena" | "moon")) => l,
        _ => "system",
    };
    let mode = if std::env::var("RUST_REGIME_MODE").is_ok_and(|m| m == "6v6") { "6v6" } else { "" };
    MAPS.iter().position(|m| m.level == level && m.mode == mode).unwrap_or(0)
}

/// Levels are wired in when the app is built, so another map is a fresh run of the game that
/// goes straight into play. The settings, save and loadout carry over through their files.
fn launch(map: &MapDef) -> std::io::Result<()> {
    let mut cmd = std::process::Command::new(std::env::current_exe()?);
    cmd.args(std::env::args_os().skip(1)).env("RUST_REGIME_LEVEL", map.level).env("RUST_REGIME_MENU", "play");
    if map.mode.is_empty() {
        cmd.env_remove("RUST_REGIME_MODE");
    } else {
        cmd.env("RUST_REGIME_MODE", map.mode);
    }
    *RELAUNCHED.lock().unwrap_or_else(|e| e.into_inner()) = Some(cmd.spawn()?);
    Ok(())
}

/// The run [`launch`] started, which this process waits on once its own window has closed.
static RELAUNCHED: std::sync::Mutex<Option<std::process::Child>> = std::sync::Mutex::new(None);

/// Waits for the map started from the menu, if there is one, and returns its exit code. The old
/// run must outlive it: once it exits, `cargo run` and the play script finish and the terminal
/// closes, and that hangs up on the new run and kills it without a word.
pub fn wait_for_relaunch() -> Option<i32> {
    let mut child = RELAUNCHED.lock().unwrap_or_else(|e| e.into_inner()).take()?;
    Some(child.wait().ok()?.code().unwrap_or(1))
}

/// `tuned[slot]` says whether that slot has a part to tune; `fits` whether the gun on the counter takes parts.
fn rows(panel: Panel, screen: Screen, tuned: [bool; 4], fits: bool) -> Vec<Row> {
    let mut rows = vec![];
    match panel {
        Panel::Main => {
            rows.push(if screen == Screen::Paused { Row::Action("RESUME", Action::Resume) } else { Row::Action("PLAY", Action::Play) });
            rows.push(Row::Action("MAPS", Action::Maps));
            rows.push(Row::Action("WARDROBE", Action::Wardrobe));
            rows.push(Row::Action("SETTINGS", Action::Settings));
            rows.push(Row::Action("CONTROLS", Action::Controls));
            rows.push(Row::Action("QUIT", Action::Quit));
        }
        Panel::Settings => {
            let mut i = 0;
            for (name, fields) in SECTIONS {
                rows.push(Row::Section(name));
                for _ in fields.iter() {
                    rows.push(Row::Field(i));
                    i += 1;
                }
            }
            rows.push(Row::Action("BACK", Action::Back));
        }
        Panel::Controls => rows.push(Row::Action("BACK", Action::Back)),
        Panel::Maps => {
            rows.extend((0..MAPS.len()).map(Row::Map));
            rows.push(Row::Action("BACK", Action::Back));
        }
        Panel::Quartermaster => {
            rows.push(Row::Weapon);
            for slot in (0..SLOTS.len()).filter(|_| fits) {
                rows.push(Row::Slot(slot));
                if tuned[slot] {
                    rows.push(Row::Tune(slot));
                }
            }
            rows.push(Row::Action("BACK", Action::Back));
        }
        Panel::Wardrobe => {
            rows.push(Row::Preset);
            rows.extend((0..wardrobe::SLOTS.len()).map(Row::Look));
            rows.push(Row::Action("RANDOMISE", Action::Randomize));
            rows.push(Row::Action("BACK", Action::Back));
        }
    }
    rows
}

fn selectable(rows: &[Row]) -> impl Iterator<Item = Row> + '_ {
    rows.iter().copied().filter(|r| !matches!(r, Row::Section(_)))
}

/// The main-list row that opens `panel`, so Back lands on it.
fn main_cursor(panel: Panel) -> usize {
    match panel {
        Panel::Maps => 1,
        Panel::Wardrobe => 2,
        Panel::Settings => 3,
        Panel::Controls => 4,
        Panel::Main | Panel::Quartermaster => 0,
    }
}

/// The Controls screen: every binding, by context, from `controls::BINDINGS`, with F5 on the end.
fn controls_sheet() -> String {
    let mut out = format!("{:<34}{:<30}{}\n", "ACTION", "KEYBOARD / MOUSE", "GAMEPAD");
    // Driving and flying only list what differs from walking: the rest is the same buttons.
    let foot = crate::controls::rows(crate::controls::Ctx::Foot);
    for ctx in crate::controls::Ctx::GAME {
        out.push_str(&format!("\n{}\n", ctx.label().to_uppercase()));
        for row in crate::controls::rows(ctx) {
            if ctx == crate::controls::Ctx::Foot || !foot.contains(&row) {
                out.push_str(&format!("{:<34}{:<30}{}\n", row.0, row.1, row.2));
            }
        }
    }
    out.push_str(&format!("\n{:<34}{:<30}\n", "Reload tuning.toml", "F5"));
    out
}

// -------------------------------------------------------------------------------------- plugin

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        let settings = Settings::load().unwrap_or_else(|| app.world().get_resource::<Tuning>().map_or_else(Settings::default, Settings::from_tuning));
        app.insert_state(initial())
            .insert_resource(settings)
            .init_resource::<Menu>()
            .init_resource::<Counter>()
            .init_resource::<Nav>()
            .add_systems(OnEnter(Screen::Playing), enter_play)
            .add_systems(OnEnter(Screen::Paused), enter_menu)
            .add_systems(OnEnter(Screen::Title), enter_menu)
            // Nothing to pick from until the world is in: the loading screen covers the title.
            .add_systems(Update, (read_input.run_if(resource_exists::<ButtonInput<KeyCode>>), act, sync, apply_live, rebuild).chain().run_if(in_state(crate::boot::Boot::Ready)));
    }
}

/// Boot to the title, unless a screenshot run asks for the game or a particular screen.
fn initial() -> Screen {
    match std::env::var("RUST_REGIME_MENU").as_deref() {
        Ok("pause" | "settings" | "controls" | "maps" | "quartermaster" | "wardrobe") => Screen::Paused,
        Ok("play") => Screen::Playing,
        Ok(_) => Screen::Title,
        Err(_) if std::env::var_os("RUST_REGIME_SCREENSHOT").is_some() => Screen::Playing,
        Err(_) => Screen::Title,
    }
}

fn enter_play(mut menu: ResMut<Menu>, cursor: Option<Single<&mut CursorOptions>>) {
    menu.panel = Panel::Main;
    menu.cursor = 0;
    menu.playing = true;
    menu.from_station = false;
    if let Some(mut cursor) = cursor {
        cursor.grab_mode = CursorGrabMode::Locked;
        cursor.visible = false;
    }
}

fn enter_menu(mut menu: ResMut<Menu>, mut counter: ResMut<Counter>, cursor: Option<Single<&mut CursorOptions>>, mut first: Local<bool>) {
    menu.playing = false;
    menu.panel = Panel::Main;
    menu.cursor = 0;
    menu.from_station = false;
    menu.note.clear();
    let counter = std::mem::take(&mut counter.0);
    if counter {
        menu.panel = Panel::Quartermaster;
        menu.from_station = true;
    }
    if !*first {
        *first = true;
        menu.panel = if counter { Panel::Quartermaster } else { match std::env::var("RUST_REGIME_MENU").as_deref() {
            Ok("settings") => Panel::Settings,
            Ok("controls") => Panel::Controls,
            Ok("maps") => Panel::Maps,
            Ok("quartermaster") => Panel::Quartermaster,
            Ok("wardrobe") => Panel::Wardrobe,
            _ => Panel::Main,
        } };
    }
    if let Some(mut cursor) = cursor {
        cursor.grab_mode = CursorGrabMode::None;
        cursor.visible = true;
    }
}

/// Stop the clock and hide the HUD while a menu is up.
fn sync(screen: Res<State<Screen>>, mut time: ResMut<Time<Virtual>>, mut hud: Query<&mut Visibility, With<HudRoot>>) {
    let playing = *screen.get() == Screen::Playing;
    if playing == time.is_paused() {
        if playing { time.unpause() } else { time.pause() }
    }
    for mut vis in &mut hud {
        let want = if playing { Visibility::Inherited } else { Visibility::Hidden };
        if *vis != want {
            *vis = want;
        }
    }
}

// -------------------------------------------------------------------------------------- input

/// What the player asked of the menu this frame, from keys, pad or mouse.
#[derive(Resource, Default, Debug)]
struct Nav {
    moved: i32,
    adjust: i32,
    select: bool,
    back: bool,
    weapon: i32,
    hover: Option<usize>,
    /// A clicked row and the direction clicked (0 = the row itself).
    click: Option<(usize, i32)>,
}

/// Which selectable row a UI node stands for.
#[derive(Component)]
struct RowId(usize);

/// A `<` or `>` button on a row.
#[derive(Component)]
struct Arrow(usize, i32);

fn read_input(
    mouse: Res<ButtonInput<MouseButton>>,
    actions: Res<crate::controls::ActionState>,
    rows: Query<(&Interaction, &RowId), Changed<Interaction>>,
    arrows: Query<(&Interaction, &Arrow), Changed<Interaction>>,
    mut nav: ResMut<Nav>,
) {
    use crate::controls::Action::*;
    let mut n = Nav::default();
    // Keys and pad come from the bindings (`controls::BINDINGS`): the same buttons the game uses
    // pause the game and back out of a menu.
    let step = |plus, minus| actions.pressed(plus) as i32 - actions.pressed(minus) as i32;
    n.moved = step(Down, Up);
    n.adjust = step(Right, Left);
    n.weapon = step(TabNext, TabPrev);
    n.select = actions.pressed(Select);
    n.back = actions.pressed(Back) || actions.pressed(Pause);
    for (i, row) in &rows {
        match i {
            Interaction::Hovered => n.hover = Some(row.0),
            Interaction::Pressed if mouse.just_pressed(MouseButton::Left) => n.click = Some((row.0, 0)),
            _ => {}
        }
    }
    for (i, arrow) in &arrows {
        if *i == Interaction::Pressed && mouse.just_pressed(MouseButton::Left) {
            n.click = Some((arrow.0, arrow.1));
        }
    }
    if n.moved != 0 || n.adjust != 0 || n.select || n.back || n.weapon != 0 || n.hover.is_some() || n.click.is_some() {
        *nav = n;
    }
}

/// The wardrobe's pieces, all optional so headless tests without a character still run.
#[derive(bevy::ecs::system::SystemParam)]
struct Closet<'w> {
    wardrobe: Option<ResMut<'w, Wardrobe>>,
    characters: Option<Res<'w, Characters>>,
    class: Option<Res<'w, Class>>,
}

impl Closet<'_> {
    fn outfit(&self) -> Option<OutfitDef> {
        let w = self.wardrobe.as_ref()?;
        if let Some(o) = &w.outfit {
            return Some(o.clone());
        }
        Some(wardrobe::class_outfit(self.characters.as_deref()?, self.class.as_deref()?))
    }
}

#[allow(clippy::too_many_arguments)]
fn act(
    mut nav: ResMut<Nav>,
    mut menu: ResMut<Menu>,
    screen: Res<State<Screen>>,
    mut next: ResMut<NextState<Screen>>,
    mut settings: ResMut<Settings>,
    mut tuning: ResMut<Tuning>,
    mut loadout: ResMut<Loadout>,
    mut arsenal: ResMut<Arsenal>,
    save: Option<ResMut<Save>>,
    file: Option<Res<SaveFile>>,
    mut exit: MessageWriter<AppExit>,
    mut closet: Closet,
) {
    let nav = std::mem::take(&mut *nav);
    let screen = *screen.get();
    if screen == Screen::Playing {
        if nav.back {
            next.set(Screen::Paused);
        }
        return;
    }
    let rows = rows(menu.panel, screen, tuned(&loadout, arsenal.kind()), gunsmith::customizable(arsenal.kind()));
    let count = selectable(&rows).count();
    if nav.back {
        match menu.panel {
            Panel::Main => {
                if screen == Screen::Paused {
                    next.set(Screen::Playing);
                }
            }
            p => leave(&mut menu, &mut next, p, save.as_deref(), &mut loadout, &mut arsenal, &closet),
        }
        return;
    }
    if let Some(h) = nav.hover
        && menu.cursor != h
    {
        menu.cursor = h;
    }
    if nav.moved != 0 && count > 0 {
        menu.cursor = (menu.cursor as i32 + nav.moved).rem_euclid(count as i32) as usize;
    }
    if nav.weapon != 0 && menu.panel == Panel::Quartermaster {
        switch_weapon(&mut arsenal, nav.weapon);
    }
    let (cursor, dir, select) = match nav.click {
        Some((i, d)) => (i, d, d == 0),
        None => (menu.cursor, nav.adjust, nav.select),
    };
    if nav.click.is_some() && menu.cursor != cursor {
        menu.cursor = cursor;
    }
    let Some(row) = selectable(&rows).nth(cursor) else { return };
    // Rows that only have a value: Enter steps them forward.
    let step = if dir != 0 { dir } else if select { 1 } else { 0 };
    match row {
        Row::Section(_) => {}
        Row::Action(_, action) => {
            if select {
                match action {
                    Action::Play | Action::Resume => next.set(Screen::Playing),
                    Action::Quit => {
                        exit.write(AppExit::Success);
                    }
                    Action::Back => {
                        let panel = menu.panel;
                        leave(&mut menu, &mut next, panel, save.as_deref(), &mut loadout, &mut arsenal, &closet);
                    }
                    Action::Maps => {
                        open(&mut menu, Panel::Maps);
                        menu.cursor = current_map();
                    }
                    Action::Wardrobe => open(&mut menu, Panel::Wardrobe),
                    Action::Randomize => {
                        if let Some(mut outfit) = closet.outfit()
                            && let Some(w) = closet.wardrobe.as_mut()
                        {
                            let seed = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(1, |d| d.as_millis() as u64);
                            wardrobe::randomize(&mut outfit, seed);
                            w.set(outfit.clone());
                            if let (Some(mut save), Some(file)) = (save, file) {
                                wardrobe::persist(&mut save, &outfit);
                                file.write(&save);
                            }
                        }
                    }
                    Action::Settings => open(&mut menu, Panel::Settings),
                    Action::Controls => open(&mut menu, Panel::Controls),
                }
            }
        }
        Row::Map(i) => {
            if select {
                if i == current_map() {
                    next.set(Screen::Playing);
                } else {
                    match launch(&MAPS[i]) {
                        Ok(()) => {
                            exit.write(AppExit::Success);
                        }
                        Err(e) => warn!("could not start {}: {e}", MAPS[i].name),
                    }
                }
            }
        }
        Row::Field(i) => {
            if step != 0 {
                step_field(i, step, &mut settings);
                settings.apply(&mut tuning);
                settings.save();
            }
        }
        Row::Weapon => {
            let kind = arsenal.kind();
            if select && !quartermaster::owns_weapon(save.as_deref(), kind) {
                if let (Some(mut save), Some(file)) = (save, file) {
                    let sale = quartermaster::buy_weapon(&mut save, kind);
                    menu.note = sold(sale, kind.name());
                    file.write(&save);
                }
            } else if step != 0 {
                switch_weapon(&mut arsenal, step);
            }
        }
        Row::Slot(slot) | Row::Tune(slot) => {
            let kind = arsenal.kind();
            let part = loadout.part(kind, slot);
            if row == Row::Slot(slot) && select && !quartermaster::owns_part(save.as_deref(), slot, part) {
                if let (Some(mut save), Some(file)) = (save, file) {
                    let sale = quartermaster::buy_part(&mut save, slot, part);
                    menu.note = sold(sale, PARTS[slot][part].name);
                    gunsmith::persist(&loadout, &mut save, &file);
                }
            } else if step != 0 {
                if row == Row::Slot(slot) {
                    loadout.cycle(kind, slot, step);
                } else {
                    loadout.cycle_tune(kind, slot, step);
                }
                if let (Some(mut save), Some(file)) = (save, file) {
                    gunsmith::persist(&loadout, &mut save, &file);
                }
            }
        }
        Row::Preset | Row::Look(_) => {
            if step != 0
                && let Some(mut outfit) = closet.outfit()
                && let Some(characters) = closet.characters.as_deref()
                && let Some(w) = closet.wardrobe.as_mut()
            {
                let mut save = save;
                match row {
                    Row::Look(i) => wardrobe::SLOTS[i].cycle(&mut outfit, characters, step),
                    _ => {
                        if let Some(save) = save.as_mut() {
                            outfit = wardrobe::switch_preset(save, outfit, step);
                        }
                    }
                }
                w.set(outfit.clone());
                if let (Some(mut save), Some(file)) = (save, file) {
                    wardrobe::persist(&mut save, &outfit);
                    file.write(&save);
                }
            }
        }
    }
}

/// Close the counter, or any other panel: the counter takes back what was only tried on and hands
/// you the game again if you walked up to it.
#[allow(clippy::too_many_arguments)]
fn leave(menu: &mut Menu, next: &mut NextState<Screen>, panel: Panel, save: Option<&Save>, loadout: &mut Loadout, arsenal: &mut Arsenal, closet: &Closet) {
    menu.note.clear();
    if panel == Panel::Quartermaster {
        if let Some(save) = save {
            let start = quartermaster::starter(closet.characters.as_deref(), closet.class.as_deref());
            quartermaster::sanitize(save, loadout, arsenal, start);
        }
        if menu.from_station {
            menu.from_station = false;
            next.set(Screen::Playing);
            return;
        }
    }
    menu.cursor = main_cursor(panel);
    menu.panel = Panel::Main;
}

/// What the counter says about a sale.
fn sold(sale: Sale, what: &str) -> String {
    match sale {
        Sale::Bought(cost) => format!("Bought {what}: -${cost}"),
        Sale::Poor(short) => format!("{what}: ${short} short"),
        Sale::Owned => format!("{what} is already yours"),
        Sale::NotForSale => format!("{what} is not for sale"),
    }
}

fn tuned(loadout: &Loadout, kind: crate::weapon::WeaponKind) -> [bool; 4] {
    std::array::from_fn(|slot| loadout.part(kind, slot) != 0)
}

fn open(menu: &mut Menu, panel: Panel) {
    menu.panel = panel;
    menu.cursor = 0;
}

/// Next weapon on the counter in `dir` (the knife is not for sale), raised at once.
fn switch_weapon(arsenal: &mut Arsenal, dir: i32) {
    let mut i = arsenal.current as i32;
    for _ in 0..WEAPONS.len() {
        i = (i + dir.signum()).rem_euclid(WEAPONS.len() as i32);
        if quartermaster::price(WEAPONS[i as usize]).is_some() {
            break;
        }
    }
    arsenal.select(i as usize);
    arsenal.switch_time = 0.0;
}

/// Settings that change something already spawned: volumes, post effects, shadows.
fn apply_live(
    mut commands: Commands,
    settings: Res<Settings>,
    mut first: Local<bool>,
    volume: Option<ResMut<GlobalVolume>>,
    camera: Option<Single<Entity, With<PlayerCamera>>>,
    suns: Query<Entity, With<DirectionalLight>>,
) {
    if !settings.is_changed() {
        return;
    }
    // The first change is the resource being inserted; startup already read tuning.
    if !*first {
        *first = true;
        return;
    }
    if let Some(mut v) = volume {
        v.volume = Volume::Linear(settings.master);
    }
    if let Some(camera) = camera {
        use bevy::anti_alias::taa::TemporalAntiAliasing;
        use bevy::pbr::ScreenSpaceAmbientOcclusion;
        use bevy::post_process::bloom::Bloom;
        let mut e = commands.entity(*camera);
        if settings.bloom { e.insert(Bloom::NATURAL); } else { e.remove::<Bloom>(); }
        if settings.ssao { e.insert((ScreenSpaceAmbientOcclusion::default(), Msaa::Off)); } else { e.remove::<ScreenSpaceAmbientOcclusion>(); }
        if settings.taa { e.insert((TemporalAntiAliasing::default(), Msaa::Off)); } else { e.remove::<TemporalAntiAliasing>(); }
    }
    for sun in &suns {
        commands.entity(sun).insert(CascadeShadowConfigBuilder { num_cascades: 4, maximum_distance: settings.shadow_distance, first_cascade_far_bound: 20.0, ..default() }.build());
    }
}

// ----------------------------------------------------------------------------------------- ui

const AMBER: Color = Color::srgb(1.0, 0.72, 0.25);
const WHITE: Color = Color::WHITE;
const DIM: Color = Color::srgba(1.0, 1.0, 1.0, 0.55);
const FAINT: Color = Color::srgba(1.0, 1.0, 1.0, 0.18);
const PANEL: Color = Color::srgba(0.02, 0.03, 0.04, 0.72);
const LEFT: f32 = 72.0;

#[derive(Component)]
struct MenuRoot;

fn text(s: impl Into<String>, px: f32, color: Color) -> (Text, TextFont, TextColor) {
    (Text::new(s), TextFont { font_size: FontSize::Px(px), ..default() }, TextColor(color))
}

fn abs(left: Option<f32>, right: Option<f32>, top: Option<f32>, bottom: Option<f32>) -> Node {
    let v = |o: Option<f32>| o.map_or(Val::Auto, Val::Px);
    Node { position_type: PositionType::Absolute, left: v(left), right: v(right), top: v(top), bottom: v(bottom), flex_direction: FlexDirection::Column, ..default() }
}

#[allow(clippy::too_many_arguments)]
fn rebuild(
    mut commands: Commands,
    roots: Query<Entity, With<MenuRoot>>,
    menu: Res<Menu>,
    screen: Res<State<Screen>>,
    settings: Res<Settings>,
    loadout: Res<Loadout>,
    arsenal: Res<Arsenal>,
    tuning: Res<Tuning>,
    closet: Closet,
    save: Option<Res<Save>>,
) {
    let wardrobe_changed = closet.wardrobe.as_ref().is_some_and(|w| w.is_changed());
    let gun_changed = menu.panel == Panel::Quartermaster && (arsenal.is_changed() || save.as_ref().is_some_and(|s| s.is_changed()));
    if !(menu.is_changed() || screen.is_changed() || settings.is_changed() || loadout.is_changed() || gun_changed || wardrobe_changed) {
        return;
    }
    for e in &roots {
        commands.entity(e).despawn();
    }
    let screen = *screen.get();
    if screen == Screen::Playing {
        return;
    }
    let kind = arsenal.kind();
    let rows = rows(menu.panel, screen, tuned(&loadout, kind), gunsmith::customizable(kind));
    let outfit = closet.outfit();
    let base = tuning.gun(kind).cloned();
    let fitted = base.as_ref().map(|g| loadout.gun(kind, g));

    // Dark from the left so the list reads over the island, like a vignette.
    let shade = |a: f32| ColorStop::auto(Color::srgba(0.0, 0.0, 0.0, a));
    let gradient = BackgroundGradient(vec![LinearGradient::to_right(vec![shade(0.88), shade(0.7), shade(0.25), shade(0.15)]).into()]);
    let mut root = commands.spawn((MenuRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() }, gradient, ZIndex(10)));
    root.with_children(|p| {
        // Header.
        p.spawn(abs(Some(LEFT), None, Some(48.0), None)).with_children(|h| {
            let (small, big) = match (menu.panel, screen) {
                (Panel::Main, Screen::Title) => ("ISLAND HUB  /  EXTRACTION", "RUST REGIME"),
                (Panel::Main, _) => ("RUST REGIME", "PAUSED"),
                (Panel::Settings, _) => ("RUST REGIME", "SETTINGS"),
                (Panel::Controls, _) => ("RUST REGIME", "CONTROLS"),
                (Panel::Maps, _) => ("RUST REGIME", "MAPS"),
                (Panel::Quartermaster, _) => ("BANKED", "QUARTERMASTER"),
                (Panel::Wardrobe, _) => ("RUST REGIME", "WARDROBE"),
            };
            if menu.panel == Panel::Quartermaster {
                h.spawn(text(format!("BANKED  ${}", save.as_ref().map_or(0, |s| s.banked)), 14.0, AMBER));
            } else {
                h.spawn(text(small, 14.0, AMBER));
            }
            h.spawn(text(big, if big == "RUST REGIME" { 64.0 } else { 44.0 }, WHITE));
            h.spawn((Node { width: Val::Px(320.0), height: Val::Px(2.0), margin: UiRect::top(Val::Px(6.0)), ..default() }, BackgroundColor(AMBER)));
        });

        // Rows.
        let top = if menu.panel == Panel::Main && screen == Screen::Title { 190.0 } else { 140.0 };
        let width = match menu.panel {
            Panel::Main => 360.0,
            Panel::Wardrobe => 620.0,
            _ => 560.0,
        };
        p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT), top: Val::Px(top), bottom: Val::Px(44.0), width: Val::Px(width), flex_direction: FlexDirection::Column, row_gap: Val::Px(2.0), overflow: Overflow::clip_y(), ..default() }).with_children(|list| {
            if menu.panel == Panel::Wardrobe {
                let preset = save.as_ref().map_or(0, |s| s.preset);
                list.spawn(Node { display: Display::Grid, grid_template_columns: RepeatedGridTrack::px(4, 146.0), row_gap: Val::Px(6.0), column_gap: Val::Px(6.0), ..default() }).with_children(|grid| {
                    let mut index = 0;
                    for row in &rows {
                        if let Row::Preset | Row::Look(_) = row {
                            tile(grid, *row, index, index == menu.cursor, outfit.as_ref(), closet.characters.as_deref(), preset);
                            index += 1;
                        }
                    }
                });
                list.spawn(Node { height: Val::Px(10.0), ..default() });
                let mut index = selectable(&rows).filter(|r| matches!(r, Row::Preset | Row::Look(_))).count();
                for row in &rows {
                    if let Row::Action(label, _) = row {
                        action_row(list, label, index, menu.cursor == index, 22.0);
                        index += 1;
                    }
                }
                return;
            }
            let mut index = 0;
            for row in &rows {
                match *row {
                    Row::Section(name) => {
                        list.spawn((text(name, 13.0, AMBER), Node { margin: UiRect::top(Val::Px(8.0)), ..default() }));
                    }
                    Row::Action(label, _) => {
                        let big = menu.panel == Panel::Main;
                        if !big {
                            list.spawn(Node { height: Val::Px(6.0), ..default() });
                        }
                        action_row(list, label, index, index == menu.cursor, if big { 40.0 } else { 22.0 });
                        index += 1;
                    }
                    Row::Field(i) => {
                        let f = fields().nth(i).unwrap();
                        let (value, fill) = field_value(f, &settings);
                        let label = if f.restart { format!("{} *", f.label) } else { f.label.to_string() };
                        value_row(list, &label, &value, fill, None, index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Weapon => {
                        let value = match (quartermaster::owns_weapon(save.as_deref(), kind), quartermaster::price(kind)) {
                            (false, Some(cost)) => format!("{}  ${cost}", kind.name()),
                            _ => format!("{}  OWNED", kind.name()),
                        };
                        let note = (!quartermaster::owns_weapon(save.as_deref(), kind)).then_some("ENTER buys it");
                        value_row(list, "WEAPON", &value, None, note, index, index == menu.cursor, true);
                        list.spawn(Node { height: Val::Px(10.0), ..default() });
                        index += 1;
                    }
                    Row::Slot(slot) => {
                        let at = loadout.part(kind, slot);
                        let part = &PARTS[slot][at];
                        let owned = quartermaster::owns_part(save.as_deref(), slot, at);
                        let value = if owned { part.name.to_string() } else { format!("{}  ${}", part.name, quartermaster::PART_PRICES[slot][at]) };
                        let note = if owned { part.desc.to_string() } else { format!("{}.  ENTER buys it", part.desc) };
                        value_row(list, SLOTS[slot], &value, None, Some(&note), index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Tune(slot) => {
                        let t = loadout.tuning(kind, slot);
                        let (l, r) = TUNES[slot];
                        value_row(list, &format!("  TUNE  {l} / {r}"), &format!("{t:+}"), Some((t + TUNE_MAX) as f32 / (2 * TUNE_MAX) as f32), None, index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Map(i) => {
                        let m = &MAPS[i];
                        value_row(list, m.name, if i == current_map() { "LOADED" } else { "" }, None, Some(m.desc), index, index == menu.cursor, false);
                        index += 1;
                    }
                    Row::Preset | Row::Look(_) => {}
                }
            }
            if menu.panel == Panel::Quartermaster && !menu.note.is_empty() {
                list.spawn((text(menu.note.clone(), 15.0, AMBER), Node { margin: UiRect::top(Val::Px(10.0)), ..default() }));
            }
            if menu.panel == Panel::Settings {
                list.spawn((text("* takes effect after a restart.  Saved to settings.toml.", 12.0, DIM), Node { margin: UiRect::top(Val::Px(4.0)), ..default() }));
            }
            if menu.panel == Panel::Controls {
                list.spawn((text(controls_sheet(), 14.0, WHITE), Node { margin: UiRect::vertical(Val::Px(8.0)), ..default() }));
            }
        });

        // The gun's stat bars, bottom right.
        if let (Panel::Quartermaster, Some(base), Some(fitted)) = (menu.panel, &base, &fitted) {
            p.spawn((Node { width: Val::Px(360.0), padding: UiRect::all(Val::Px(16.0)), row_gap: Val::Px(8.0), border: UiRect::all(Val::Px(1.0)), ..abs(None, Some(LEFT), Some(56.0), None) }, BackgroundColor(PANEL), BorderColor::all(FAINT))).with_children(|s| {
                s.spawn(text(format!("{}  STATS", kind.name()), 14.0, AMBER));
                for ((name, b), (_, f)) in gunsmith::stats(base).into_iter().zip(gunsmith::stats(fitted)) {
                    s.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: Val::Px(12.0), ..default() }).with_children(|r| {
                        r.spawn((text(name, 13.0, DIM), Node { width: Val::Px(90.0), ..default() }));
                        r.spawn((Node { width: Val::Px(200.0), height: Val::Px(8.0), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.08)))).with_children(|bar| {
                            bar.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), height: Val::Percent(100.0), width: Val::Percent(b * 100.0), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.3))));
                            bar.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), height: Val::Percent(100.0), width: Val::Percent(f * 100.0), ..default() }, BackgroundColor(if f + 0.001 < b { Color::srgb(0.9, 0.35, 0.25) } else { AMBER })));
                        });
                    });
                }
                s.spawn(text("grey: bare gun   amber: with parts   red: worse", 12.0, DIM));
            });
        }

        // Version, then the hint bar along the bottom.
        p.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(0.0), right: Val::Px(0.0), bottom: Val::Px(0.0), height: Val::Px(40.0), padding: UiRect::left(Val::Px(LEFT)), flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: Val::Px(28.0), ..default() }, BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.55)))).with_children(|bar| {
            let hints: &[(&str, &str)] = match menu.panel {
                Panel::Main if screen == Screen::Paused => &[("ENTER / A", "SELECT"), ("ESC / B", "RESUME")],
                Panel::Main => &[("ENTER / A", "SELECT"), ("W S", "MOVE")],
                Panel::Settings => &[("A D", "ADJUST"), ("ENTER / A", "TOGGLE"), ("ESC / B", "BACK")],
                Panel::Quartermaster => &[("Q E / LB RB", "WEAPON"), ("A D", "PART / TUNE"), ("ENTER / A", "BUY"), ("ESC / B", "BACK")],
                Panel::Wardrobe => &[("W S", "SLOT"), ("A D", "CHANGE"), ("ESC / B", "BACK")],
                Panel::Controls => &[("ESC / B", "BACK")],
                Panel::Maps => &[("ENTER / A", "PLAY"), ("ESC / B", "BACK")],
            };
            for (key, what) in hints {
                bar.spawn(Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(8.0), ..default() }).with_children(|c| {
                    c.spawn(text(format!("[{key}]"), 13.0, AMBER));
                    c.spawn(text(*what, 13.0, DIM));
                });
            }
            bar.spawn((text("v0.1  ISLAND HUB", 12.0, DIM), Node { margin: UiRect::left(Val::Auto).with_right(Val::Px(LEFT)), ..default() }));
        });
    });
}

fn action_row(p: &mut ChildSpawnerCommands, label: &str, index: usize, selected: bool, px: f32) {
    p.spawn((
        Button,
        RowId(index),
        Node { padding: UiRect::axes(Val::Px(14.0), Val::Px(4.0)), border: UiRect::left(Val::Px(4.0)), ..default() },
        BorderColor::all(if selected { AMBER } else { Color::NONE }),
        BackgroundColor(if selected { Color::srgba(1.0, 1.0, 1.0, 0.06) } else { Color::NONE }),
    ))
    .with_child(text(label, px, if selected { WHITE } else { DIM }));
}

/// A label on the left, `<` value `>` on the right, an optional bar and a note underneath.
/// `arrows` shows the < > steppers; a row that only launches something leaves them off.
fn value_row(p: &mut ChildSpawnerCommands, label: &str, value: &str, fill: Option<f32>, note: Option<&str>, index: usize, selected: bool, arrows: bool) {
    p.spawn((
        Button,
        RowId(index),
        Node { flex_direction: FlexDirection::Column, padding: UiRect::axes(Val::Px(14.0), Val::Px(2.0)), border: UiRect::left(Val::Px(4.0)), ..default() },
        BorderColor::all(if selected { AMBER } else { Color::NONE }),
        BackgroundColor(if selected { Color::srgba(1.0, 1.0, 1.0, 0.06) } else { Color::NONE }),
    ))
    .with_children(|row| {
        row.spawn(Node { flex_direction: FlexDirection::Row, justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, width: Val::Percent(100.0), ..default() }).with_children(|r| {
            r.spawn(text(label, 17.0, if selected { WHITE } else { DIM }));
            r.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: Val::Px(10.0), ..default() }).with_children(|v| {
                if arrows {
                    arrow(v, index, -1, selected);
                }
                if let Some(fill) = fill {
                    v.spawn((Node { width: Val::Px(130.0), height: Val::Px(6.0), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.12))))
                        .with_child((Node { width: Val::Percent(fill.clamp(0.0, 1.0) * 100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(if selected { AMBER } else { Color::srgba(1.0, 0.72, 0.25, 0.6) })));
                    v.spawn((text(value, 18.0, WHITE), Node { width: Val::Px(52.0), justify_content: JustifyContent::FlexEnd, ..default() }, TextLayout { justify: Justify::Right, ..default() }));
                } else {
                    v.spawn((text(value, 18.0, if selected { AMBER } else { WHITE }), Node { width: Val::Px(190.0), justify_content: JustifyContent::Center, ..default() }, TextLayout { justify: Justify::Center, ..default() }));
                }
                if arrows {
                    arrow(v, index, 1, selected);
                }
            });
        });
        if let Some(note) = note {
            row.spawn(text(note, 13.0, DIM));
        }
    });
}

fn arrow(p: &mut ChildSpawnerCommands, index: usize, dir: i32, selected: bool) {
    p.spawn((Button, Arrow(index, dir), Node { width: Val::Px(24.0), height: Val::Px(24.0), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.08))))
        .with_child(text(if dir < 0 { "<" } else { ">" }, 16.0, if selected { AMBER } else { DIM }));
}

/// A wardrobe tile: the preset in use, or one slot's value (with a swatch when it is a colour).
fn tile(p: &mut ChildSpawnerCommands, row: Row, index: usize, selected: bool, outfit: Option<&OutfitDef>, characters: Option<&Characters>, preset: usize) {
    let (name, worn, swatch) = match row {
        Row::Preset => ("PRESET".to_string(), format!("{} / {}", preset + 1, wardrobe::PRESETS), None),
        Row::Look(i) => {
            let slot = wardrobe::SLOTS[i];
            let (worn, swatch) = match (outfit, characters) {
                (Some(o), Some(c)) => (slot.value(o, c), slot.swatch(o)),
                _ => ("none".into(), None),
            };
            (slot.label().to_string(), worn, swatch)
        }
        _ => return,
    };
    p.spawn((
        Button,
        RowId(index),
        Node { height: Val::Px(64.0), padding: UiRect::all(Val::Px(8.0)), flex_direction: FlexDirection::Column, justify_content: JustifyContent::SpaceBetween, border: UiRect::all(Val::Px(1.0)), overflow: Overflow::clip(), ..default() },
        BorderColor::all(if selected { AMBER } else { FAINT }),
        BackgroundColor(if selected { Color::srgba(1.0, 0.72, 0.25, 0.12) } else { PANEL }),
    ))
    .with_children(|t| {
        t.spawn(text(name, 12.0, if selected { AMBER } else { DIM }));
        t.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: Val::Px(8.0), ..default() }).with_children(|r| {
            if let Some(c) = swatch {
                r.spawn((Node { width: Val::Px(18.0), height: Val::Px(18.0), ..default() }, BackgroundColor(c)));
            }
            r.spawn(text(worn, 16.0, WHITE));
        });
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn settings_round_trip_through_tuning_and_toml() {
        let mut t = Tuning::default();
        let mut s = Settings::from_tuning(&t);
        s.fov_degrees = 95.0;
        s.master = 0.3;
        s.taa = false;
        s.apply(&mut t);
        assert_eq!((t.fov_degrees, t.sound.master, t.graphics.taa), (95.0, 0.3, false));
        let text = toml::to_string(&s).unwrap();
        let back: Settings = toml::from_str(&text).unwrap();
        assert_eq!(back, s);
    }

    #[test]
    fn fields_step_clamp_flip_and_wrap() {
        let mut s = Settings::default();
        let fov = fields().position(|f| f.label == "FIELD OF VIEW").unwrap();
        for _ in 0..20 {
            step_field(fov, 1, &mut s);
        }
        assert_eq!(s.fov_degrees, 110.0, "sliders clamp at the top");
        let invert = fields().position(|f| f.label == "INVERT Y").unwrap();
        step_field(invert, 1, &mut s);
        assert!(s.invert_y, "toggles flip");
        let trees = fields().position(|f| f.label == "TREES").unwrap();
        step_field(trees, -1, &mut s);
        assert_eq!(s.trees, 0.5, "choices step through the list");
        step_field(trees, -2, &mut s);
        assert_eq!(s.trees, 1.5, "and wrap");
        let f = fields().nth(fov).unwrap();
        assert_eq!(field_value(f, &s), ("110".into(), Some(1.0)));
    }

    #[test]
    fn every_panel_has_rows_and_back_lands_on_its_opener() {
        for panel in [Panel::Main, Panel::Maps, Panel::Settings, Panel::Controls, Panel::Quartermaster, Panel::Wardrobe] {
            let panel_rows = rows(panel, Screen::Paused, [true; 4], true);
            assert!(selectable(&panel_rows).count() > 0, "{panel:?}");
            if !matches!(panel, Panel::Main | Panel::Quartermaster) {
                let main = rows(Panel::Main, Screen::Paused, [false; 4], false);
                let opener = selectable(&main).nth(main_cursor(panel)).unwrap();
                assert!(matches!(opener, Row::Action(name, _) if name == format!("{panel:?}").to_uppercase()), "{panel:?} -> {opener:?}");
            }
        }
        assert_eq!(rows(Panel::Main, Screen::Title, [false; 4], false)[0], Row::Action("PLAY", Action::Play));
        assert_eq!(rows(Panel::Main, Screen::Paused, [false; 4], false)[0], Row::Action("RESUME", Action::Resume));
        assert_eq!(selectable(&rows(Panel::Maps, Screen::Title, [false; 4], false)).count(), MAPS.len() + 1);
        assert!(MAPS.iter().any(|m| m.level == "system" && m.mode.is_empty()) && MAPS[0].mode.is_empty(), "the solar system leads");
        assert_eq!(selectable(&rows(Panel::Quartermaster, Screen::Paused, [true, false, false, false], true)).count(), 1 + 4 + 1 + 1, "a tune row under the fitted optic");
        assert_eq!(selectable(&rows(Panel::Quartermaster, Screen::Paused, [false; 4], false)).count(), 2, "a rocket launcher has the picker and Back");
        let main = rows(Panel::Main, Screen::Paused, [false; 4], false);
        assert!(!main.iter().any(|r| matches!(r, Row::Action(name, _) if name.contains("GUNSMITH"))), "the quartermaster replaced the gunsmith");
    }
}
