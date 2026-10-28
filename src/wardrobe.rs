//! The camp wardrobe: stand at the locker, press E, walk the slots with up/down and change them
//! with left/right (R rolls a random look, Tab switches preset). The result is saved in `save.toml`
//! as an outfit over the class default and worn again next time; saves naming no known character
//! fall back to the class default. The menu's wardrobe panel (`menu`) edits the same slots.

use bevy::prelude::*;

use crate::abilities::Class;
use crate::body::Body;
use crate::camo::PATTERNS;
use crate::character::{ArmsOnly, CHARACTERS, Characters, OutfitDef, Rig, WEAR_MAX};
use crate::controller::Player;
use crate::dressing::Mannequin;
use crate::input::PlayerInput;
use crate::save::{Save, SaveFile};
use crate::vehicle::{Driving, VehicleSet};

/// Name of the outfit the wardrobe writes into `Characters`.
pub const CUSTOM: &str = "custom";
/// How close to the locker E opens it.
const REACH: f32 = 2.5;
/// Cloth colours.
pub const PALETTE: [&str; 14] = [
    "#141413", "#D97757", "#F0EEE6", "#D4A27F", "#2b2f33", "#4a5a48", "#d98b2b", "#8a2b2b", "#1f3a5f", "#5a4632", "#c9c2b4", "#3a3a3a", "#6d8a3a", "#7a3a7a",
];
pub const SKIN_TONES: [&str; 8] = ["#f3d9c6", "#e7bfa1", "#d8a482", "#c48a64", "#a86f4c", "#8a5639", "#6a3f2a", "#47291c"];
pub const METALS: [&str; 7] = ["#2a2a2c", "#4a4f55", "#9aa0a6", "#b08d57", "#8c6a3f", "#a08a5c", "#5a6a3a"];
/// Glow colours; `off` puts the lights out.
pub const GLOWS: [&str; 7] = ["#ff8c1a", "#ff2a2a", "#2ae0ff", "#3aff6a", "#b04cff", "#ffffff", "off"];
pub const GLASSES: [&str; 5] = ["#404040", "#d0882a", "#4a7fbf", "#a03030", "#3a9a5a"];
pub const WEAR_NAMES: [&str; 4] = ["CLEAN", "USED", "WORN", "BATTERED"];
/// How many outfits the player keeps.
pub const PRESETS: usize = 3;

/// What the wardrobe lets you change, in display order.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Slot {
    Character,
    Head,
    Primary,
    Secondary,
    Accent,
    Camo,
    Skin,
    Gloves,
    Boots,
    Webbing,
    Metal,
    Glow,
    Glass,
    Wear,
}

pub const SLOTS: [Slot; 14] = [
    Slot::Character,
    Slot::Head,
    Slot::Primary,
    Slot::Secondary,
    Slot::Accent,
    Slot::Camo,
    Slot::Skin,
    Slot::Gloves,
    Slot::Boots,
    Slot::Webbing,
    Slot::Metal,
    Slot::Glow,
    Slot::Glass,
    Slot::Wear,
];

impl Slot {
    pub fn label(self) -> &'static str {
        match self {
            Slot::Character => "CHARACTER",
            Slot::Head => "HEAD",
            Slot::Primary => "PRIMARY",
            Slot::Secondary => "SECONDARY",
            Slot::Accent => "ACCENT",
            Slot::Camo => "CAMO",
            Slot::Skin => "SKIN",
            Slot::Gloves => "GLOVES",
            Slot::Boots => "BOOTS",
            Slot::Webbing => "WEBBING",
            Slot::Metal => "METAL",
            Slot::Glow => "LIGHTS",
            Slot::Glass => "VISOR",
            Slot::Wear => "WEAR",
        }
    }

    /// The palette an optional colour slot walks, if it is one.
    fn palette(self) -> Option<&'static [&'static str]> {
        Some(match self {
            Slot::Gloves | Slot::Boots | Slot::Webbing => &PALETTE,
            Slot::Skin => &SKIN_TONES,
            Slot::Metal => &METALS,
            Slot::Glow => &GLOWS,
            Slot::Glass => &GLASSES,
            _ => return None,
        })
    }

    /// The optional field behind an optional slot.
    fn field(self, o: &mut OutfitDef) -> Option<&mut Option<String>> {
        Some(match self {
            Slot::Head => &mut o.head,
            Slot::Camo => &mut o.camo,
            Slot::Skin => &mut o.skin,
            Slot::Gloves => &mut o.gloves,
            Slot::Boots => &mut o.boots,
            Slot::Webbing => &mut o.webbing,
            Slot::Metal => &mut o.metal,
            Slot::Glow => &mut o.glow,
            Slot::Glass => &mut o.glass,
            _ => return None,
        })
    }

    /// The slot's current value as text: a colour, a name, or `DEFAULT` for the character's own.
    pub fn value(self, o: &OutfitDef, characters: &Characters) -> String {
        let own = |v: &Option<String>| v.clone().unwrap_or_else(|| "DEFAULT".into());
        match self {
            Slot::Character => characters.label(&o.character).to_uppercase(),
            Slot::Head => o.head.as_deref().map_or("OWN".into(), |h| characters.label(h).to_uppercase()),
            Slot::Primary => o.primary.clone(),
            Slot::Secondary => o.secondary.clone(),
            Slot::Accent => o.accent.clone(),
            Slot::Camo => o.camo.as_deref().unwrap_or("none").to_uppercase(),
            Slot::Wear => WEAR_NAMES[o.wear.min(WEAR_MAX) as usize].into(),
            Slot::Glow if o.glow.as_deref() == Some("off") => "OFF".into(),
            Slot::Skin => own(&o.skin),
            Slot::Gloves => own(&o.gloves),
            Slot::Boots => own(&o.boots),
            Slot::Webbing => own(&o.webbing),
            Slot::Metal => own(&o.metal),
            Slot::Glow => own(&o.glow),
            Slot::Glass => own(&o.glass),
        }
    }

    /// The colour to show beside the value, when the value is one.
    pub fn swatch(self, o: &OutfitDef) -> Option<Color> {
        let hex = match self {
            Slot::Primary => o.primary.as_str(),
            Slot::Secondary => o.secondary.as_str(),
            Slot::Accent => o.accent.as_str(),
            Slot::Skin => o.skin.as_deref()?,
            Slot::Gloves => o.gloves.as_deref()?,
            Slot::Boots => o.boots.as_deref()?,
            Slot::Webbing => o.webbing.as_deref()?,
            Slot::Metal => o.metal.as_deref()?,
            Slot::Glow => o.glow.as_deref()?,
            Slot::Glass => o.glass.as_deref()?,
            _ => return None,
        };
        Srgba::hex(hex).ok().map(Color::from)
    }

    /// Step the slot forward (`dir` +1) or back (-1). Optional slots walk `DEFAULT`, then their
    /// list, then `DEFAULT` again.
    pub fn cycle(self, o: &mut OutfitDef, characters: &Characters, dir: i32) {
        match self {
            Slot::Character => cycle_character(characters, o, dir),
            Slot::Primary | Slot::Secondary | Slot::Accent => {
                let field = match self {
                    Slot::Primary => &mut o.primary,
                    Slot::Secondary => &mut o.secondary,
                    _ => &mut o.accent,
                };
                let at = PALETTE.iter().position(|c| *c == field.as_str()).map_or(0, |i| (i as i32 + dir).rem_euclid(PALETTE.len() as i32) as usize);
                *field = PALETTE[at].into();
            }
            Slot::Wear => o.wear = (o.wear as i32 + dir).rem_euclid(WEAR_MAX as i32 + 1) as u8,
            Slot::Head => {
                let others: Vec<&str> = CHARACTERS.iter().copied().filter(|c| *c != o.character).collect();
                cycle_optional(&mut o.head, &others, dir);
            }
            Slot::Camo => cycle_optional(&mut o.camo, &PATTERNS[1..], dir),
            _ => {
                let list = self.palette().unwrap_or(&[]);
                if let Some(field) = self.field(o) {
                    cycle_optional(field, list, dir);
                }
            }
        }
        o.tidy();
    }
}

/// Step an optional value through `list` with `None` as one more entry before its start.
fn cycle_optional(field: &mut Option<String>, list: &[&str], dir: i32) {
    let n = list.len() as i32 + 1;
    let at = field.as_deref().and_then(|v| list.iter().position(|c| *c == v)).map_or(0, |i| i as i32 + 1);
    let next = (at + dir).rem_euclid(n);
    *field = if next == 0 { None } else { Some(list[next as usize - 1].into()) };
}

/// Step to the next (`dir` +1) or previous (-1) character in roster order, in its own colours.
pub fn cycle_character(characters: &Characters, outfit: &mut OutfitDef, dir: i32) {
    let at = CHARACTERS.iter().position(|c| *c == outfit.character).unwrap_or(0) as i32;
    let next = CHARACTERS[(at + dir).rem_euclid(CHARACTERS.len() as i32) as usize];
    if let Some(o) = characters.default_outfit(next) {
        *outfit = o;
    }
}

/// A random look for the outfit's character: colours, camo and extras rolled from `seed`.
pub fn randomize(o: &mut OutfitDef, seed: u64) {
    let mut s = seed.max(1) ^ 0x9E37_79B9_7F4A_7C15;
    let mut roll = |n: usize| {
        s ^= s << 13;
        s ^= s >> 7;
        s ^= s << 17;
        (s % n as u64) as usize
    };
    let pick = |list: &[&str], i: usize| list[i].to_string();
    o.primary = pick(&PALETTE, roll(PALETTE.len()));
    o.secondary = pick(&PALETTE, roll(PALETTE.len()));
    o.accent = pick(&PALETTE, roll(PALETTE.len()));
    o.camo = (roll(5) < 3).then(|| pick(&PATTERNS[1..], roll(PATTERNS.len() - 1)));
    let others: Vec<&str> = CHARACTERS.iter().copied().filter(|c| *c != o.character).collect();
    o.head = (roll(3) == 0).then(|| pick(&others, roll(others.len())));
    o.skin = (roll(2) == 0).then(|| pick(&SKIN_TONES, roll(SKIN_TONES.len())));
    o.gloves = (roll(2) == 0).then(|| pick(&PALETTE, roll(PALETTE.len())));
    o.boots = (roll(2) == 0).then(|| pick(&PALETTE, roll(PALETTE.len())));
    o.webbing = (roll(2) == 0).then(|| pick(&PALETTE, roll(PALETTE.len())));
    o.metal = (roll(2) == 0).then(|| pick(&METALS, roll(METALS.len())));
    o.glow = (roll(2) == 0).then(|| pick(&GLOWS, roll(GLOWS.len())));
    o.glass = (roll(2) == 0).then(|| pick(&GLASSES, roll(GLASSES.len())));
    o.wear = roll(WEAR_MAX as usize + 1) as u8;
    o.tidy();
}

/// Park `current` in the save's active preset and move `dir` presets along, returning the outfit
/// kept there (an empty preset takes a copy of `current`).
pub fn switch_preset(save: &mut Save, current: OutfitDef, dir: i32) -> OutfitDef {
    save.presets.resize(PRESETS, OutfitDef::default());
    save.preset = save.preset.min(PRESETS - 1);
    save.presets[save.preset] = current.clone();
    save.preset = (save.preset as i32 + dir).rem_euclid(PRESETS as i32) as usize;
    let next = &mut save.presets[save.preset];
    if next.character.is_empty() {
        *next = current;
    }
    next.clone()
}

/// Remember `outfit` as what the player wears and as the active preset.
pub fn persist(save: &mut Save, outfit: &OutfitDef) {
    save.outfit = Some(outfit.clone());
    save.presets.resize(PRESETS, OutfitDef::default());
    save.preset = save.preset.min(PRESETS - 1);
    save.presets[save.preset] = outfit.clone();
}

#[derive(Component)]
pub struct Locker;

#[derive(Resource, Debug, Default)]
pub struct Wardrobe {
    pub open: bool,
    /// What the player wears over the class default; `None` until they change something.
    pub outfit: Option<OutfitDef>,
    /// The locker's highlighted slot.
    pub slot: usize,
    applied: bool,
}

impl Wardrobe {
    /// Wear `outfit` from now on (the menu's wardrobe edits it).
    pub fn set(&mut self, outfit: OutfitDef) {
        self.outfit = Some(outfit);
        self.applied = false;
    }
}

#[derive(Component)]
struct WardrobeText;

pub struct WardrobePlugin;

impl Plugin for WardrobePlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Wardrobe>()
            .add_systems(Startup, spawn_ui)
            .add_systems(FixedUpdate, toggle.before(VehicleSet))
            .add_systems(Update, (restore, edit.run_if(resource_exists::<ButtonInput<KeyCode>>), apply, show_ui).chain());
    }
}

/// The outfit the player's class wears by default.
pub fn class_outfit(characters: &Characters, class: &Class) -> OutfitDef {
    characters
        .class
        .get(&class.0)
        .and_then(|c| characters.default_outfit(&c.character))
        .or_else(|| characters.default_outfit("runner"))
        .unwrap_or_default()
}

// -------------------------------------------------------------------------------------- systems

/// E next to the locker opens or closes it; the press is used up so vehicles don't see it.
fn toggle(mut input: ResMut<PlayerInput>, mut wardrobe: ResMut<Wardrobe>, file: Res<SaveFile>, mut save: ResMut<Save>, player: Single<(&Transform, Has<Driving>), With<Player>>, lockers: Query<&Transform, With<Locker>>) {
    if !input.interact_pressed {
        return;
    }
    let (tf, driving) = *player;
    if driving {
        return;
    }
    if wardrobe.open {
        wardrobe.open = false;
        input.interact_pressed = false;
        if let Some(o) = &wardrobe.outfit {
            persist(&mut save, o);
        }
        file.write(&save);
    } else if lockers.iter().any(|l| l.translation.distance(tf.translation) < REACH) {
        wardrobe.open = true;
        input.interact_pressed = false;
    }
}

/// Pick up the saved outfit once the save has loaded.
fn restore(save: Option<Res<Save>>, characters: Res<Characters>, mut wardrobe: ResMut<Wardrobe>, mut done: Local<bool>) {
    let Some(save) = save else { return };
    if !*done {
        *done = true;
        if let Some(o) = save.outfit.as_ref().filter(|o| characters.character.contains_key(&o.character)) {
            let mut o = o.clone();
            o.tidy();
            wardrobe.outfit = Some(o);
            wardrobe.applied = false;
        }
    }
}

fn edit(keys: Res<ButtonInput<KeyCode>>, characters: Res<Characters>, class: Res<Class>, mut wardrobe: ResMut<Wardrobe>, save: Option<ResMut<Save>>, time: Res<Time<Real>>) {
    if !wardrobe.open {
        return;
    }
    let mut outfit = wardrobe.outfit.clone().unwrap_or_else(|| class_outfit(&characters, &class));
    let mut changed = false;
    for (key, step) in [(KeyCode::ArrowDown, 1), (KeyCode::ArrowUp, -1)] {
        if keys.just_pressed(key) {
            wardrobe.slot = (wardrobe.slot as i32 + step).rem_euclid(SLOTS.len() as i32) as usize;
        }
    }
    for (key, dir) in [(KeyCode::ArrowRight, 1), (KeyCode::ArrowLeft, -1)] {
        if keys.just_pressed(key) {
            SLOTS[wardrobe.slot].cycle(&mut outfit, &characters, dir);
            changed = true;
        }
    }
    if keys.just_pressed(KeyCode::KeyR) {
        randomize(&mut outfit, time.elapsed().as_millis() as u64);
        changed = true;
    }
    if keys.just_pressed(KeyCode::Tab)
        && let Some(mut save) = save
    {
        outfit = switch_preset(&mut save, outfit, 1);
        changed = true;
    }
    if changed {
        wardrobe.outfit = Some(outfit);
        wardrobe.applied = false;
    }
}

/// Write the custom outfit into `Characters` and put it on the player's body, first-person arms and
/// the dressing room's mannequin.
fn apply(mut characters: ResMut<Characters>, mut wardrobe: ResMut<Wardrobe>, mut body: Query<&mut Rig, Or<(With<Body>, With<ArmsOnly>, With<Mannequin>)>>) {
    // F5 reloads `Characters` without the custom entry: put it back.
    let missing = wardrobe.outfit.is_some() && !characters.custom.contains_key(CUSTOM);
    if wardrobe.applied && !missing {
        return;
    }
    wardrobe.applied = true;
    let Some(outfit) = wardrobe.outfit.clone() else { return };
    characters.custom.insert(CUSTOM.into(), outfit);
    for mut rig in &mut body {
        rig.wear(CUSTOM);
    }
}

fn spawn_ui(mut commands: Commands) {
    commands.spawn((
        WardrobeText,
        Text::new(""),
        TextFont { font_size: FontSize::Px(16.0), ..default() },
        Node { position_type: PositionType::Absolute, bottom: Val::Px(120.0), left: Val::Percent(50.0), width: Val::Px(520.0), margin: UiRect::left(Val::Px(-260.0)), padding: UiRect::all(Val::Px(8.0)), ..default() },
        BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.55)),
        Visibility::Hidden,
    ));
}

fn show_ui(wardrobe: Res<Wardrobe>, characters: Res<Characters>, class: Res<Class>, save: Option<Res<Save>>, mut text: Single<(&mut Text, &mut Visibility), With<WardrobeText>>) {
    let (text, vis) = &mut *text;
    if !wardrobe.open {
        **vis = Visibility::Hidden;
        return;
    }
    **vis = Visibility::Inherited;
    let outfit = wardrobe.outfit.clone().unwrap_or_else(|| class_outfit(&characters, &class));
    text.0 = locker_text(&outfit, &characters, wardrobe.slot, save.map_or(0, |s| s.preset));
}

/// The locker overlay: one line per slot, the highlighted one marked.
pub fn locker_text(outfit: &OutfitDef, characters: &Characters, slot: usize, preset: usize) -> String {
    let mut lines = vec![format!("WARDROBE  preset {}/{PRESETS}   Up/Down: slot   Left/Right: change   R: random   Tab: preset   E: done", preset + 1)];
    for (i, s) in SLOTS.iter().enumerate() {
        lines.push(format!("{} {:<10} {}", if i == slot { ">" } else { " " }, s.label(), s.value(outfit, characters)));
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn roster() -> Characters {
        Characters::parse(include_str!("../assets/characters.toml")).unwrap()
    }

    #[test]
    fn characters_cycle_in_roster_order_with_their_colours() {
        let c = roster();
        let mut o = c.default_outfit("runner").unwrap();
        o.primary = "#ff0000".into();
        cycle_character(&c, &mut o, 1);
        assert_eq!(o, c.default_outfit("breaker").unwrap());
        cycle_character(&c, &mut o, -1);
        cycle_character(&c, &mut o, -1);
        assert_eq!(o.character, "trapper");
        let mut o = c.default_outfit(CHARACTERS[CHARACTERS.len() - 1]).unwrap();
        cycle_character(&c, &mut o, 1);
        assert_eq!(o.character, CHARACTERS[0], "wraps");
    }

    #[test]
    fn colours_walk_the_palette_both_ways() {
        let c = roster();
        let mut o = OutfitDef { primary: PALETTE[0].into(), ..default() };
        Slot::Primary.cycle(&mut o, &c, 1);
        assert_eq!(o.primary, PALETTE[1]);
        Slot::Primary.cycle(&mut o, &c, -2);
        assert_eq!(o.primary, PALETTE[PALETTE.len() - 1], "backwards wraps");
        o.accent = "#123456".into();
        Slot::Accent.cycle(&mut o, &c, 1);
        assert_eq!(o.accent, PALETTE[0], "unknown colours restart the palette");
    }

    #[test]
    fn optional_slots_walk_default_then_their_list() {
        let c = roster();
        let mut o = c.default_outfit("runner").unwrap();
        Slot::Gloves.cycle(&mut o, &c, 1);
        assert_eq!(o.gloves.as_deref(), Some(PALETTE[0]), "unset gloves start the palette");
        for _ in 1..PALETTE.len() {
            Slot::Gloves.cycle(&mut o, &c, 1);
        }
        assert_eq!(o.gloves.as_deref(), Some(PALETTE[PALETTE.len() - 1]));
        Slot::Gloves.cycle(&mut o, &c, 1);
        assert_eq!(o.gloves, None, "past the palette the character keeps its own gloves");
        assert_eq!(o.boots, None, "other slots are untouched");
        Slot::Boots.cycle(&mut o, &c, -1);
        assert_eq!(o.boots.as_deref(), Some(PALETTE[PALETTE.len() - 1]), "backwards from default lands on the last");
        Slot::Camo.cycle(&mut o, &c, 1);
        assert_eq!(o.camo.as_deref(), Some("woodland"));
        assert_eq!(Slot::Camo.value(&o, &c), "WOODLAND");
        Slot::Head.cycle(&mut o, &c, 1);
        assert_eq!(o.head.as_deref(), Some("acolyte"), "the first other character");
        for _ in 0..CHARACTERS.len() - 1 {
            Slot::Head.cycle(&mut o, &c, 1);
        }
        assert_eq!(o.head, None, "never its own head");
        Slot::Wear.cycle(&mut o, &c, -1);
        assert_eq!((o.wear, Slot::Wear.value(&o, &c).as_str()), (WEAR_MAX, "BATTERED"));
        Slot::Glow.cycle(&mut o, &c, -1);
        assert_eq!(Slot::Glow.value(&o, &c), "OFF");
        assert_eq!(Slot::Glow.swatch(&o), None);
        assert!(Slot::Primary.swatch(&o).is_some());
        for s in SLOTS {
            assert!(!s.value(&o, &c).is_empty(), "{s:?} shows something");
        }
    }

    #[test]
    fn random_looks_differ_by_seed_and_stay_valid() {
        let c = roster();
        let mut a = c.default_outfit("ghost").unwrap();
        let mut b = a.clone();
        randomize(&mut a, 1);
        randomize(&mut b, 2);
        assert_ne!(a, b);
        assert_eq!(a.character, "ghost", "the character is kept");
        assert!(a.wear <= WEAR_MAX && a.head.as_deref() != Some("ghost"));
        let mut again = c.default_outfit("ghost").unwrap();
        randomize(&mut again, 1);
        assert_eq!(a, again, "seeded");
    }

    #[test]
    fn presets_keep_three_outfits() {
        let c = roster();
        let mut save = Save::default();
        let runner = c.default_outfit("runner").unwrap();
        let next = switch_preset(&mut save, runner.clone(), 1);
        assert_eq!((save.preset, &next), (1, &runner), "an empty preset copies the current look");
        let mut ghost = c.default_outfit("ghost").unwrap();
        ghost.wear = 2;
        persist(&mut save, &ghost);
        assert_eq!(save.presets[1], ghost);
        let back = switch_preset(&mut save, ghost.clone(), -1);
        assert_eq!((save.preset, back), (0, runner));
        let forward = switch_preset(&mut save, c.default_outfit("runner").unwrap(), 1);
        assert_eq!(forward, ghost, "preset 2 kept the ghost");
        assert_eq!(save.presets.len(), PRESETS);
    }

    #[test]
    fn locker_text_marks_the_slot() {
        let c = roster();
        let o = c.default_outfit("runner").unwrap();
        let t = locker_text(&o, &c, 2, 0);
        assert!(t.lines().nth(3).unwrap().starts_with("> PRIMARY"), "{t}");
        assert_eq!(t.lines().count(), SLOTS.len() + 1);
    }
}
