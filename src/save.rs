//! What persists between sessions, in `save.toml` next to `tuning.toml`: banked money, the outfit, the
//! loadout, the weapons and parts you own, the ship's tune, the courier parcel, and the ships you
//! have shot down and lost.

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
#[derive(Resource, Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
#[serde(default)]
pub struct Save {
    pub banked: u32,
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
    /// Enemy ships you have shot down, in all and by faction id (`combat::Faction::id`), for
    /// faction standing later; and how often your own ship has been shot down.
    pub kills: u32,
    pub faction_kills: BTreeMap<String, u32>,
    pub deaths: u32,
}
