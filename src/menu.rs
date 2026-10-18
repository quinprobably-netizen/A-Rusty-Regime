//! The front end: title screen, pause menu, settings, controls sheet, gunsmith and wardrobe, all
//! Bevy UI over the live world. Titanfall-style: a tall uppercase list on the left, the island
//! behind it, button hints along the bottom. Time stands still while a menu is up.
//!
//! `RUST_REGIME_MENU=title|pause|settings|controls|gunsmith|wardrobe` opens straight into a
//! screen (handy with `RUST_REGIME_SCREENSHOT`).

use bevy::app::AppExit;
use bevy::audio::{GlobalVolume, Volume};
use bevy::camera::visibility::RenderLayers;
use bevy::light::CascadeShadowConfigBuilder;
use bevy::prelude::*;
use bevy::ui::{ColorStop, LinearGradient, BackgroundGradient};
use bevy::window::{CursorGrabMode, CursorOptions};
use serde::{Deserialize, Serialize};

use crate::abilities::Class;
use crate::camera::PlayerCamera;
use crate::character::{Characters, OutfitDef, SHADOW_ONLY_LAYER};
use crate::gunsmith::{self, Loadout, PARTS, SLOTS, TUNE_MAX, TUNES};
use crate::hud::HudRoot;
use crate::loot::{Save, SaveFile};
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
    Settings,
    Controls,
    Gunsmith,
    Wardrobe,
}

/// What the camera presents while a panel is open.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Showcase {
    None,
    /// The first-person weapon turned to the camera (gunsmith).
    Gun,
    /// The player's body from the front (wardrobe).
    Body,
}

#[derive(Resource, Debug, Default)]
pub struct Menu {
    pub panel: Panel,
    /// Highlighted row, counting only selectable rows.
    pub cursor: usize,
    pub playing: bool,
}

impl Menu {
    pub fn showcase(&self) -> Showcase {
        match self.panel {
            _ if self.playing => Showcase::None,
            Panel::Gunsmith => Showcase::Gun,
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
    Gunsmith,
    Wardrobe,
    Settings,
    Controls,
    Quit,
    Back,
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum Row {
    Section(&'static str),
    Action(&'static str, Action),
    Field(usize),
    /// The gunsmith's weapon picker.
    Weapon,
    /// A gunsmith attachment slot.
    Slot(usize),
    /// The tuning slider under a fitted part.
    Tune(usize),
    /// The wardrobe's character picker.
    Character,
    /// A wardrobe colour (primary, secondary, accent).
    Colour(usize),
}

/// `tuned[slot]` says whether that gunsmith slot has a part to tune.
fn rows(panel: Panel, screen: Screen, tuned: [bool; 4]) -> Vec<Row> {
    let mut rows = vec![];
    match panel {
        Panel::Main => {
            rows.push(if screen == Screen::Paused { Row::Action("RESUME", Action::Resume) } else { Row::Action("PLAY", Action::Play) });
            rows.push(Row::Action("GUNSMITH", Action::Gunsmith));
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
        Panel::Gunsmith => {
            rows.push(Row::Weapon);
            for slot in 0..SLOTS.len() {
                rows.push(Row::Slot(slot));
                if tuned[slot] {
                    rows.push(Row::Tune(slot));
                }
            }
            rows.push(Row::Action("BACK", Action::Back));
        }
        Panel::Wardrobe => {
            rows.push(Row::Character);
            rows.extend((0..3).map(Row::Colour));
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
        Panel::Gunsmith => 1,
        Panel::Wardrobe => 2,
        Panel::Settings => 3,
        Panel::Controls => 4,
        Panel::Main => 0,
    }
}

const CONTROLS: &[(&str, &str, &str)] = &[
    ("Move", "W A S D", "Left stick"),
    ("Look", "Mouse", "Right stick"),
    ("Jump / wall jump / double jump", "Space", "A"),
    ("Crouch / slide", "Ctrl, Shift or C", "B, L3 or LT"),
    ("Fire", "Left mouse", "RT"),
    ("Aim down sights", "Right mouse", "LT"),
    ("Grapple", "G or mouse 4", "L3"),
    ("Flashlight", "F", ""),
    ("Weapon 1-10", "1 - 9, 0", "D-pad (1-4)"),
    ("Reload", "R", "R3"),
    ("Inspect weapon", "V", ""),
    ("Next / previous weapon", "Wheel", "RB / LB"),
    ("Last weapon", "Q", "Y"),
    ("Enter / leave a vehicle", "E", "X"),
    ("Drive, handbrake", "W A S D, Space", "Left stick, A"),
    ("Respawn", "Backspace", "Select"),
    ("Menu", "Esc", "Start"),
    ("Reload tuning.toml", "F5", ""),
];

// -------------------------------------------------------------------------------------- plugin

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        let settings = Settings::load().unwrap_or_else(|| app.world().get_resource::<Tuning>().map_or_else(Settings::default, Settings::from_tuning));
        app.insert_state(initial())
            .insert_resource(settings)
            .init_resource::<Menu>()
            .init_resource::<Nav>()
            .add_systems(OnEnter(Screen::Playing), enter_play)
            .add_systems(OnEnter(Screen::Paused), enter_menu)
            .add_systems(OnEnter(Screen::Title), enter_menu)
            .add_systems(Update, (read_input.run_if(resource_exists::<ButtonInput<KeyCode>>), act, sync, apply_live, showcase_layers, rebuild).chain());
    }
}

/// Boot to the title, unless a screenshot run asks for the game or a particular screen.
fn initial() -> Screen {
    match std::env::var("RUST_REGIME_MENU").as_deref() {
        Ok("pause" | "settings" | "controls" | "gunsmith" | "wardrobe") => Screen::Paused,
        Ok(_) => Screen::Title,
        Err(_) if std::env::var_os("RUST_REGIME_SCREENSHOT").is_some() => Screen::Playing,
        Err(_) => Screen::Title,
    }
}

fn enter_play(mut menu: ResMut<Menu>, cursor: Option<Single<&mut CursorOptions>>) {
    menu.panel = Panel::Main;
    menu.cursor = 0;
    menu.playing = true;
    if let Some(mut cursor) = cursor {
        cursor.grab_mode = CursorGrabMode::Locked;
        cursor.visible = false;
    }
}

fn enter_menu(mut menu: ResMut<Menu>, cursor: Option<Single<&mut CursorOptions>>, mut first: Local<bool>) {
    menu.playing = false;
    menu.panel = Panel::Main;
    menu.cursor = 0;
    if !*first {
        *first = true;
        menu.panel = match std::env::var("RUST_REGIME_MENU").as_deref() {
            Ok("settings") => Panel::Settings,
            Ok("controls") => Panel::Controls,
            Ok("gunsmith") => Panel::Gunsmith,
            Ok("wardrobe") => Panel::Wardrobe,
            _ => Panel::Main,
        };
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
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    pads: Query<&Gamepad>,
    rows: Query<(&Interaction, &RowId), Changed<Interaction>>,
    arrows: Query<(&Interaction, &Arrow), Changed<Interaction>>,
    mut nav: ResMut<Nav>,
) {
    let mut n = Nav::default();
    let down = |n: &mut Nav, k: KeyCode, d: i32| if keys.just_pressed(k) { n.moved += d };
    down(&mut n, KeyCode::ArrowDown, 1);
    down(&mut n, KeyCode::KeyS, 1);
    down(&mut n, KeyCode::ArrowUp, -1);
    down(&mut n, KeyCode::KeyW, -1);
    if keys.any_just_pressed([KeyCode::ArrowRight, KeyCode::KeyD]) {
        n.adjust += 1;
    }
    if keys.any_just_pressed([KeyCode::ArrowLeft, KeyCode::KeyA]) {
        n.adjust -= 1;
    }
    n.select = keys.any_just_pressed([KeyCode::Enter, KeyCode::Space]);
    n.back = keys.just_pressed(KeyCode::Escape);
    if keys.just_pressed(KeyCode::KeyE) {
        n.weapon += 1;
    }
    if keys.just_pressed(KeyCode::KeyQ) {
        n.weapon -= 1;
    }
    for pad in &pads {
        if pad.just_pressed(GamepadButton::DPadDown) {
            n.moved += 1;
        }
        if pad.just_pressed(GamepadButton::DPadUp) {
            n.moved -= 1;
        }
        if pad.just_pressed(GamepadButton::DPadRight) {
            n.adjust += 1;
        }
        if pad.just_pressed(GamepadButton::DPadLeft) {
            n.adjust -= 1;
        }
        n.select |= pad.just_pressed(GamepadButton::South);
        n.back |= pad.any_just_pressed([GamepadButton::East, GamepadButton::Start]);
        if pad.just_pressed(GamepadButton::RightTrigger) {
            n.weapon += 1;
        }
        if pad.just_pressed(GamepadButton::LeftTrigger) {
            n.weapon -= 1;
        }
    }
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
    let rows = rows(menu.panel, screen, tuned(&loadout, arsenal.kind()));
    let count = selectable(&rows).count();
    if nav.back {
        match menu.panel {
            Panel::Main => {
                if screen == Screen::Paused {
                    next.set(Screen::Playing);
                }
            }
            p => {
                menu.cursor = main_cursor(p);
                menu.panel = Panel::Main;
            }
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
    if nav.weapon != 0 && menu.panel == Panel::Gunsmith {
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
                        menu.cursor = main_cursor(menu.panel);
                        menu.panel = Panel::Main;
                    }
                    Action::Gunsmith => {
                        open(&mut menu, Panel::Gunsmith);
                        if !gunsmith::customizable(arsenal.kind()) {
                            switch_weapon(&mut arsenal, 1);
                        }
                    }
                    Action::Wardrobe => open(&mut menu, Panel::Wardrobe),
                    Action::Settings => open(&mut menu, Panel::Settings),
                    Action::Controls => open(&mut menu, Panel::Controls),
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
            if step != 0 {
                switch_weapon(&mut arsenal, step);
            }
        }
        Row::Slot(slot) | Row::Tune(slot) => {
            if step != 0 {
                if row == Row::Slot(slot) {
                    loadout.cycle(arsenal.kind(), slot, step);
                } else {
                    loadout.cycle_tune(arsenal.kind(), slot, step);
                }
                if let (Some(mut save), Some(file)) = (save, file) {
                    gunsmith::persist(&loadout, &mut save, &file);
                }
            }
        }
        Row::Character | Row::Colour(_) => {
            if step != 0
                && let Some(mut outfit) = closet.outfit()
                && let Some(characters) = closet.characters.as_deref()
                && let Some(w) = closet.wardrobe.as_mut()
            {
                match row {
                    Row::Colour(c) => wardrobe::cycle_colour(&mut outfit, c),
                    _ => wardrobe::cycle_character(characters, &mut outfit, step),
                }
                w.set(outfit.clone());
                if let (Some(mut save), Some(file)) = (save, file) {
                    save.outfit = Some(outfit);
                    file.write(&save);
                }
            }
        }
    }
}

fn tuned(loadout: &Loadout, kind: crate::weapon::WeaponKind) -> [bool; 4] {
    std::array::from_fn(|slot| loadout.part(kind, slot) != 0)
}

fn open(menu: &mut Menu, panel: Panel) {
    menu.panel = panel;
    menu.cursor = 0;
}

/// Next customizable weapon in `dir`, raised at once for the gunsmith.
fn switch_weapon(arsenal: &mut Arsenal, dir: i32) {
    let mut i = arsenal.current as i32;
    for _ in 0..WEAPONS.len() {
        i = (i + dir).rem_euclid(WEAPONS.len() as i32);
        if gunsmith::customizable(WEAPONS[i as usize]) {
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

/// The wardrobe looks at the player from the front, so the camera must draw the head too.
fn showcase_layers(mut commands: Commands, menu: Res<Menu>, camera: Option<Single<Entity, With<PlayerCamera>>>) {
    if !menu.is_changed() {
        return;
    }
    let Some(camera) = camera else { return };
    if menu.showcase() == Showcase::Body {
        commands.entity(*camera).insert(RenderLayers::from_layers(&[0, SHADOW_ONLY_LAYER]));
    } else {
        commands.entity(*camera).remove::<RenderLayers>();
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
) {
    let wardrobe_changed = closet.wardrobe.as_ref().is_some_and(|w| w.is_changed());
    let gun_changed = menu.panel == Panel::Gunsmith && arsenal.is_changed();
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
    let rows = rows(menu.panel, screen, tuned(&loadout, kind));
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
                (Panel::Gunsmith, _) => ("RUST REGIME", "GUNSMITH"),
                (Panel::Wardrobe, _) => ("RUST REGIME", "WARDROBE"),
            };
            h.spawn(text(small, 14.0, AMBER));
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
                list.spawn(Node { display: Display::Grid, grid_template_columns: RepeatedGridTrack::px(3, 196.0), row_gap: Val::Px(8.0), column_gap: Val::Px(8.0), ..default() }).with_children(|grid| {
                    let mut index = 0;
                    for row in &rows {
                        if let Row::Character | Row::Colour(_) = row {
                            tile(grid, *row, index, index == menu.cursor, outfit.as_ref(), closet.characters.as_deref());
                            index += 1;
                        }
                    }
                });
                list.spawn(Node { height: Val::Px(12.0), ..default() });
                action_row(list, "BACK", rows.len() - 1, menu.cursor == rows.len() - 1, 22.0);
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
                        value_row(list, &label, &value, fill, None, index, index == menu.cursor);
                        index += 1;
                    }
                    Row::Weapon => {
                        value_row(list, "WEAPON", kind.name(), None, None, index, index == menu.cursor);
                        list.spawn(Node { height: Val::Px(10.0), ..default() });
                        index += 1;
                    }
                    Row::Slot(slot) => {
                        let part = &PARTS[slot][loadout.part(kind, slot)];
                        value_row(list, SLOTS[slot], part.name, None, Some(part.desc), index, index == menu.cursor);
                        index += 1;
                    }
                    Row::Tune(slot) => {
                        let t = loadout.tuning(kind, slot);
                        let (l, r) = TUNES[slot];
                        value_row(list, &format!("  TUNE  {l} / {r}"), &format!("{t:+}"), Some((t + TUNE_MAX) as f32 / (2 * TUNE_MAX) as f32), None, index, index == menu.cursor);
                        index += 1;
                    }
                    Row::Character | Row::Colour(_) => {}
                }
            }
            if menu.panel == Panel::Settings {
                list.spawn((text("* takes effect after a restart.  Saved to settings.toml.", 12.0, DIM), Node { margin: UiRect::top(Val::Px(4.0)), ..default() }));
            }
            if menu.panel == Panel::Controls {
                let lines: Vec<String> = CONTROLS.iter().map(|(a, k, g)| format!("{a:<32}{k:<20}{g}")).collect();
                list.spawn((text(format!("{:<32}{:<20}{}\n\n{}", "ACTION", "KEYBOARD / MOUSE", "GAMEPAD", lines.join("\n")), 15.0, WHITE), Node { margin: UiRect::vertical(Val::Px(8.0)), ..default() }));
            }
        });

        // Gunsmith stat bars, bottom right.
        if let (Panel::Gunsmith, Some(base), Some(fitted)) = (menu.panel, &base, &fitted) {
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
                Panel::Gunsmith => &[("Q E / LB RB", "WEAPON"), ("A D", "PART / TUNE"), ("ESC / B", "BACK")],
                Panel::Wardrobe => &[("A D", "STYLE"), ("ENTER / A", "NEXT"), ("ESC / B", "BACK")],
                Panel::Controls => &[("ESC / B", "BACK")],
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
fn value_row(p: &mut ChildSpawnerCommands, label: &str, value: &str, fill: Option<f32>, note: Option<&str>, index: usize, selected: bool) {
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
                arrow(v, index, -1, selected);
                if let Some(fill) = fill {
                    v.spawn((Node { width: Val::Px(130.0), height: Val::Px(6.0), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.12))))
                        .with_child((Node { width: Val::Percent(fill.clamp(0.0, 1.0) * 100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(if selected { AMBER } else { Color::srgba(1.0, 0.72, 0.25, 0.6) })));
                    v.spawn((text(value, 18.0, WHITE), Node { width: Val::Px(52.0), justify_content: JustifyContent::FlexEnd, ..default() }, TextLayout { justify: Justify::Right, ..default() }));
                } else {
                    v.spawn((text(value, 18.0, if selected { AMBER } else { WHITE }), Node { width: Val::Px(190.0), justify_content: JustifyContent::Center, ..default() }, TextLayout { justify: Justify::Center, ..default() }));
                }
                arrow(v, index, 1, selected);
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

/// A wardrobe tile: the character worn, or a colour swatch.
fn tile(p: &mut ChildSpawnerCommands, row: Row, index: usize, selected: bool, outfit: Option<&OutfitDef>, characters: Option<&Characters>) {
    let (name, worn, swatch) = match row {
        Row::Character => {
            let worn = match (outfit, characters) {
                (Some(o), Some(c)) => c.label(&o.character),
                _ => "none".into(),
            };
            ("CHARACTER".to_string(), worn.to_uppercase(), None)
        }
        Row::Colour(c) => {
            let hex = outfit.map(|o| [&o.primary, &o.secondary, &o.accent][c].clone()).unwrap_or_default();
            (["PRIMARY", "SECONDARY", "ACCENT"][c].to_string(), hex.clone(), Srgba::hex(&hex).ok().map(Color::from))
        }
        _ => return,
    };
    p.spawn((
        Button,
        RowId(index),
        Node { height: Val::Px(74.0), padding: UiRect::all(Val::Px(10.0)), flex_direction: FlexDirection::Column, justify_content: JustifyContent::SpaceBetween, border: UiRect::all(Val::Px(1.0)), ..default() },
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
        for panel in [Panel::Main, Panel::Settings, Panel::Controls, Panel::Gunsmith, Panel::Wardrobe] {
            let panel_rows = rows(panel, Screen::Paused, [true; 4]);
            assert!(selectable(&panel_rows).count() > 0, "{panel:?}");
            if panel != Panel::Main {
                let main = rows(Panel::Main, Screen::Paused, [false; 4]);
                let opener = selectable(&main).nth(main_cursor(panel)).unwrap();
                assert!(matches!(opener, Row::Action(name, _) if name == format!("{panel:?}").to_uppercase()), "{panel:?} -> {opener:?}");
            }
        }
        assert_eq!(rows(Panel::Main, Screen::Title, [false; 4])[0], Row::Action("PLAY", Action::Play));
        assert_eq!(rows(Panel::Main, Screen::Paused, [false; 4])[0], Row::Action("RESUME", Action::Resume));
        assert_eq!(selectable(&rows(Panel::Gunsmith, Screen::Paused, [true, false, false, false])).count(), 1 + 4 + 1 + 1, "a tune row under the fitted optic");
    }
}
