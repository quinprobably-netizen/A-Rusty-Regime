//! What persists between sessions, in `save.toml` next to `tuning.toml`: banked money, the outfit, the
//! loadout, the weapons and parts you own, the ship's tune, the courier parcel, the ships you
//! have shot down and lost, where you stand with each faction, and your salvage.

use std::collections::BTreeMap;
use std::path::PathBuf;

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

pub struct SavePlugin;

impl Plugin for SavePlugin {
    fn build(&self, app: &mut App) {
        let file = app.world().get_resource::<SaveFile>().cloned().unwrap_or_default();
        let save = file.load();
        app.insert_resource(file).insert_resource(save);
    }
}

/// Where the save lives; `None` keeps everything in memory (tests).
#[derive(Resource, Clone, Debug)]
pub struct SaveFile(pub Option<PathBuf>);

impl Default for SaveFile {
    fn default() -> Self {
        SaveFile(Some(std::env::var_os("RUST_REGIME_SAVE").map_or_else(|| PathBuf::from("save.toml"), PathBuf::from)))
    }
}

impl SaveFile {
    pub fn load(&self) -> Save {
        let Some(path) = &self.0 else { return Save::default() };
        match std::fs::read_to_string(path) {
            Ok(text) => toml::from_str(&text).unwrap_or_else(|e| {
                warn!("{} is invalid, starting fresh: {e}", path.display());
                Save::default()
            }),
            Err(_) => Save::default(),
        }
    }

    pub fn write(&self, save: &Save) {
        let Some(path) = &self.0 else { return };
        match toml::to_string(save) {
            Ok(text) => {
                if let Err(e) = std::fs::write(path, text) {
                    warn!("could not write {}: {e}", path.display());
                }
            }
            Err(e) => warn!("could not serialize the save: {e}"),
        }
    }
}

/// What persists between sessions.
#[derive(Resource, Serialize, Deserialize, Clone, Debug, Default, PartialEq)]
#[serde(default)]
pub struct Save {
    pub banked: u32,
    /// Money earned in the field and not yet banked (bounties): it banks at a base's door and is
    /// lost when your ship is shot down (`solar::economy`).
    pub pocket: u32,
    /// Clothes picked at the camp wardrobe, over the class default.
    pub outfit: Option<crate::character::OutfitDef>,
    /// The wardrobe's saved looks and which one `outfit` is.
    pub presets: Vec<crate::character::OutfitDef>,
    pub preset: usize,
    /// Gunsmith parts fitted to each weapon.
    pub loadout: Option<crate::gunsmith::Loadout>,
    /// Weapons owned, by id: the starter kit, then whatever the quartermaster has sold. Empty on
    /// worlds with no quartermaster (and in an old save, until the solar system grants the kit),
    /// where every weapon is yours.
    pub weapons: Vec<String>,
    /// Attachments bought, a bit per part in each slot (part 0, the bare gun's own, is always yours).
    pub parts: [u8; 4],
    /// How far the Yard has tuned the Kestrel's engines.
    pub ship_level: u8,
    /// The courier parcel being carried, and how many have been delivered.
    pub contract: Option<crate::solar::station::Contract>,
    pub contracts_done: u32,
    /// Enemy ships you have shot down, in all and by faction id (`combat::Faction::id`), and how
    /// often your own ship has been shot down.
    pub kills: u32,
    pub faction_kills: BTreeMap<String, u32>,
    pub deaths: u32,
    /// Your standing with each faction that has moved from where a stranger starts, by faction id
    /// (`solar::standing::get` reads it, falling back to `[ship_combat] standing_start`), and the
    /// game time toward the next day's slow recovery, s.
    pub standing: BTreeMap<String, i32>,
    pub standing_clock: f32,
    /// Salvage (`solar::salvage`): scrap picked up from wrecks and not yet spent, the level of
    /// each ship part bought with it (hull plating, shield cell, gun capacitor, missile rack), the
    /// modules found, by id, and the ones fitted (at most two).
    pub scrap: u32,
    pub ship_parts: [u8; 4],
    pub modules: Vec<String>,
    pub fitted: Vec<String>,
    /// The posts you have come across (`solar::post`), as `<body>.<n>`: each has a waypoint.
    pub posts_found: Vec<String>,
}
