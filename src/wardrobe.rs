//! The camp wardrobe: stand at the locker, press E, and change clothes slot by slot. Tab picks the
//! slot, left/right cycle its style (including nothing, for slots that allow it), 1/2/3 cycle the
//! three colours. The result is saved in `save.toml` as an outfit over the class default and worn
//! again next time.

use bevy::prelude::*;

use crate::abilities::Class;
use crate::body::Body;
use crate::character::{Characters, OutfitDef, Rig, Styles, WEARABLE, styles_for};
use crate::controller::Player;
use crate::input::PlayerInput;
use crate::loot::{Save, SaveFile};
use crate::vehicle::{Driving, VehicleSet};

/// Name of the outfit the wardrobe writes into `Characters`.
pub const CUSTOM: &str = "custom";
/// How close to the locker E opens it.
const REACH: f32 = 2.5;
/// Slots that may be left empty.
const OPTIONAL: [&str; 4] = ["face", "back", "gear", "hands"];
pub const PALETTE: [&str; 10] = ["#2b2f33", "#4a5a48", "#d98b2b", "#8a2b2b", "#1f3a5f", "#5a4632", "#c9c2b4", "#3a3a3a", "#6d8a3a", "#7a3a7a"];

#[derive(Component)]
pub struct Locker;

#[derive(Resource, Debug, Default)]
pub struct Wardrobe {
    pub open: bool,
    pub slot: usize,
    /// What the player wears over the class default; `None` until they change something.
    pub outfit: Option<OutfitDef>,
    applied: bool,
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

/// The style list for `slot`, with `None` first when the slot may be empty.
pub fn options(slot: &str) -> Vec<Option<Styles>> {
    let mut out: Vec<Option<Styles>> = vec![];
    if OPTIONAL.contains(&slot) {
        out.push(None);
    }
    out.extend(styles_for(slot).into_iter().map(|s| Some(Styles::One(s.into()))));
    out
}

/// Step the slot's style by `dir` (+1 / -1) through `options`. A stacked style (jacket + carrier)
/// counts as its base style.
pub fn cycle_style(outfit: &mut OutfitDef, slot: &str, dir: i32) {
    let opts = options(slot);
    let current = outfit.slot(slot).and_then(|s| s.list().first().map(|b| b.to_string()));
    let at = opts.iter().position(|o| o.as_ref().and_then(|s| s.list().first().map(|b| b.to_string())) == current).unwrap_or(0) as i32;
    let next = (at + dir).rem_euclid(opts.len() as i32) as usize;
    outfit.set_slot(slot, opts[next].clone());
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

fn class_outfit(characters: &Characters, class: &Class) -> OutfitDef {
    characters
        .class
        .get(&class.0)
        .and_then(|c| characters.outfit.get(&c.outfit))
        .or_else(|| characters.outfit.get("runner"))
        .cloned()
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
fn restore(save: Option<Res<Save>>, mut wardrobe: ResMut<Wardrobe>, mut done: Local<bool>) {
    let Some(save) = save else { return };
    if !*done {
        *done = true;
        if let Some(o) = &save.outfit {
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
    let slot = WEARABLE[wardrobe.slot];
    let mut changed = false;
    if keys.just_pressed(KeyCode::Tab) {
        wardrobe.slot = (wardrobe.slot + 1) % WEARABLE.len();
    }
    for (key, dir) in [(KeyCode::ArrowRight, 1), (KeyCode::ArrowLeft, -1)] {
        if keys.just_pressed(key) {
            cycle_style(&mut outfit, slot, dir);
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

/// Write the custom outfit into `Characters` and put it on the player's body.
fn apply(mut characters: ResMut<Characters>, mut wardrobe: ResMut<Wardrobe>, mut body: Query<&mut Rig, With<Body>>) {
    // F5 reloads `Characters` without the custom entry: put it back.
    let missing = wardrobe.outfit.is_some() && !characters.outfit.contains_key(CUSTOM);
    if wardrobe.applied && !missing {
        return;
    }
    wardrobe.applied = true;
    let Some(outfit) = wardrobe.outfit.clone() else { return };
    characters.outfit.insert(CUSTOM.into(), outfit);
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
    let mut lines = vec!["WARDROBE   Tab: next slot   Left/Right: style   1/2/3: colours   E: done".to_string()];
    for (i, slot) in WEARABLE.iter().enumerate() {
        let worn = outfit.slot(slot).map_or("none".to_string(), |s| s.list().join(" + "));
        lines.push(format!("{} {slot}: {worn}", if i == wardrobe.slot { ">" } else { " " }));
    }
    lines.push(format!("  colours: {} {} {}", outfit.primary, outfit.secondary, outfit.accent));
    text.0 = lines.join("\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn styles_cycle_through_every_option_and_back() {
        let mut o = OutfitDef::default();
        o.set_slot("torso", Some(Styles::Many(vec!["jacket".into(), "carrier".into()])));
        cycle_style(&mut o, "torso", 1);
        assert_eq!(o.torso, Some(Styles::One("shirt".into())));
        cycle_style(&mut o, "torso", 1);
        assert_eq!(o.torso, Some(Styles::One("carrier".into())));
        cycle_style(&mut o, "torso", 1);
        assert_eq!(o.torso, Some(Styles::One("jacket".into())), "wraps; torso can't be empty");
        o.set_slot("face", Some(Styles::One("mask".into())));
        cycle_style(&mut o, "face", -1);
        assert_eq!(o.face, None, "face can be bare");
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
