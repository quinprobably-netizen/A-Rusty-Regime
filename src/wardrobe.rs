//! The camp wardrobe: stand at the locker, press E, pick a character with left/right and cycle its
//! three colours with 1/2/3. The result is saved in `save.toml` as an outfit over the class default
//! and worn again next time; saves naming no known character fall back to the class default.

use bevy::prelude::*;

use crate::abilities::Class;
use crate::body::Body;
use crate::character::{ArmsOnly, CHARACTERS, Characters, OutfitDef, Rig};
use crate::controller::Player;
use crate::dressing::Mannequin;
use crate::input::PlayerInput;
use crate::loot::{Save, SaveFile};
use crate::vehicle::{Driving, VehicleSet};

/// Name of the outfit the wardrobe writes into `Characters`.
pub const CUSTOM: &str = "custom";
/// How close to the locker E opens it.
const REACH: f32 = 2.5;
pub const PALETTE: [&str; 14] = [
    "#141413", "#D97757", "#F0EEE6", "#D4A27F", "#2b2f33", "#4a5a48", "#d98b2b", "#8a2b2b", "#1f3a5f", "#5a4632", "#c9c2b4", "#3a3a3a", "#6d8a3a", "#7a3a7a",
];

#[derive(Component)]
pub struct Locker;

#[derive(Resource, Debug, Default)]
pub struct Wardrobe {
    pub open: bool,
    /// What the player wears over the class default; `None` until they change something.
    pub outfit: Option<OutfitDef>,
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

// --------------------------------------------------------------------------------------- logic

/// Step to the next (`dir` +1) or previous (-1) character in roster order, in its own colours.
pub fn cycle_character(characters: &Characters, outfit: &mut OutfitDef, dir: i32) {
    let at = CHARACTERS.iter().position(|c| *c == outfit.character).unwrap_or(0) as i32;
    let next = CHARACTERS[(at + dir).rem_euclid(CHARACTERS.len() as i32) as usize];
    if let Some(o) = characters.default_outfit(next) {
        *outfit = o;
    }
}

/// Step one of the three colours through the palette.
pub fn cycle_colour(outfit: &mut OutfitDef, which: usize) {
    let field = match which {
        0 => &mut outfit.primary,
        1 => &mut outfit.secondary,
        _ => &mut outfit.accent,
    };
    let at = PALETTE.iter().position(|c| *c == field.as_str()).map_or(0, |i| (i + 1) % PALETTE.len());
    *field = PALETTE[at].into();
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
        save.outfit = wardrobe.outfit.clone();
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
            wardrobe.outfit = Some(o.clone());
            wardrobe.applied = false;
        }
    }
}

fn edit(keys: Res<ButtonInput<KeyCode>>, characters: Res<Characters>, class: Res<Class>, mut wardrobe: ResMut<Wardrobe>) {
    if !wardrobe.open {
        return;
    }
    let mut outfit = wardrobe.outfit.clone().unwrap_or_else(|| class_outfit(&characters, &class));
    let mut changed = false;
    for (key, dir) in [(KeyCode::ArrowRight, 1), (KeyCode::ArrowLeft, -1)] {
        if keys.just_pressed(key) {
            cycle_character(&characters, &mut outfit, dir);
            changed = true;
        }
    }
    for (key, which) in [(KeyCode::Digit1, 0), (KeyCode::Digit2, 1), (KeyCode::Digit3, 2)] {
        if keys.just_pressed(key) {
            cycle_colour(&mut outfit, which);
            changed = true;
        }
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
        TextFont { font_size: FontSize::Px(18.0), ..default() },
        Node { position_type: PositionType::Absolute, bottom: Val::Px(120.0), left: Val::Percent(50.0), width: Val::Px(520.0), margin: UiRect::left(Val::Px(-260.0)), ..default() },
        BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.55)),
        Visibility::Hidden,
    ));
}

fn show_ui(wardrobe: Res<Wardrobe>, characters: Res<Characters>, class: Res<Class>, mut text: Single<(&mut Text, &mut Visibility), With<WardrobeText>>) {
    let (text, vis) = &mut *text;
    if !wardrobe.open {
        **vis = Visibility::Hidden;
        return;
    }
    **vis = Visibility::Inherited;
    let outfit = wardrobe.outfit.clone().unwrap_or_else(|| class_outfit(&characters, &class));
    let mut lines = vec!["WARDROBE   Left/Right: character   1/2/3: colours   E: done".to_string()];
    lines.push(format!("  character: {}", characters.label(&outfit.character)));
    lines.push(format!("  colours: {} {} {}", outfit.primary, outfit.secondary, outfit.accent));
    text.0 = lines.join("\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn characters_cycle_in_roster_order_with_their_colours() {
        let c = Characters::parse(include_str!("../assets/characters.toml")).unwrap();
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
    fn colours_walk_the_palette() {
        let mut o = OutfitDef { primary: PALETTE[0].into(), ..default() };
        cycle_colour(&mut o, 0);
        assert_eq!(o.primary, PALETTE[1]);
        o.accent = "#123456".into();
        cycle_colour(&mut o, 2);
        assert_eq!(o.accent, PALETTE[0], "unknown colours restart the palette");
    }
}
