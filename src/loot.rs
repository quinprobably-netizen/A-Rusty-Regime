//! The extraction loop: caches scattered over the island are carried until you stand on an extraction pad
//! long enough to bank them, or die and lose them. Banked value, runs, deaths and mission progress persist
//! in `save.toml` next to `tuning.toml`.

use std::path::PathBuf;

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

use crate::controller::{ControllerSet, Player};
use crate::health::PlayerHealth;
use crate::input::PlayerInput;
use crate::tuning::Tuning;

pub struct LootPlugin;

impl Plugin for LootPlugin {
    fn build(&self, app: &mut App) {
        let file = app.world().get_resource::<SaveFile>().cloned().unwrap_or_default();
        let save = file.load();
        app.insert_resource(file)
            .insert_resource(save)
            .init_resource::<Inventory>()
            .add_systems(FixedUpdate, (pickup, medkits, extract, lose_on_death).chain().in_set(LootSet).after(ControllerSet));
    }
}

#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct LootSet;

/// A cache worth `value`; `key` marks a mission item. Hidden for `down` seconds after being taken.
#[derive(Component, Debug)]
pub struct Loot {
    pub value: u32,
    pub key: Option<usize>,
    pub down: f32,
}

impl Loot {
    pub fn available(&self) -> bool {
        self.down <= 0.0
    }
}

/// A medkit: full health and no more bleeding, then gone for `down` seconds.
#[derive(Component, Debug)]
pub struct Medkit {
    pub down: f32,
}

/// Stand inside `radius` of it to extract.
#[derive(Component, Debug)]
pub struct ExtractPad {
    pub radius: f32,
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
    pub runs: u32,
    pub deaths: u32,
    pub missions_done: usize,
    /// Clothes picked at the camp wardrobe, over the class default.
    pub outfit: Option<crate::character::OutfitDef>,
    /// The wardrobe's saved looks and which one `outfit` is.
    pub presets: Vec<crate::character::OutfitDef>,
    pub preset: usize,
    /// Gunsmith parts fitted to each weapon.
    pub loadout: Option<crate::gunsmith::Loadout>,
    /// How far the Yard has tuned the Kestrel's engines.
    pub ship_level: u8,
    /// The courier parcel being carried, and how many have been delivered.
    pub contract: Option<crate::solar::station::Contract>,
    pub contracts_done: u32,
}

/// What you carry right now.
#[derive(Resource, Debug, Default)]
pub struct Inventory {
    pub carried: u32,
    pub keys: Vec<usize>,
    /// Seconds spent on a pad so far.
    pub extracting: f32,
    /// True for the tick an extraction lands, with the keys it carried out.
    pub just_extracted: bool,
    pub extracted_keys: Vec<usize>,
    /// Set for the tick you die, so missions can react.
    pub just_died: bool,
    was_alive: bool,
}

/// A cache lying on the ground at `pos`.
pub fn bundle(pos: Vec3, value: u32, key: Option<usize>) -> impl Bundle {
    (Name::new("Loot"), Loot { value, key, down: 0.0 }, Transform::from_translation(pos + Vec3::Y * 0.4), Visibility::default())
}

fn pickup(time: Res<Time>, tuning: Res<Tuning>, health: Res<PlayerHealth>, player: Single<&Transform, With<Player>>, mut inv: ResMut<Inventory>, mut loots: Query<(&mut Loot, &Transform, &mut Visibility)>) {
    let dt = time.delta_secs();
    for (mut loot, tf, mut vis) in &mut loots {
        if !loot.available() {
            loot.down -= dt;
            if loot.available() {
                loot.down = 0.0;
                *vis = Visibility::Inherited;
            }
            continue;
        }
        if health.alive() && tf.translation.distance(player.translation) < tuning.loot.pickup_radius {
            inv.carried += loot.value;
            if let Some(key) = loot.key {
                inv.keys.push(key);
            }
            loot.down = tuning.loot.respawn;
            *vis = Visibility::Hidden;
        }
    }
}

fn medkits(time: Res<Time>, tuning: Res<Tuning>, mut health: ResMut<PlayerHealth>, player: Single<&Transform, With<Player>>, mut kits: Query<(&mut Medkit, &Transform, &mut Visibility)>) {
    let dt = time.delta_secs();
    for (mut kit, tf, mut vis) in &mut kits {
        if kit.down > 0.0 {
            kit.down -= dt;
            if kit.down <= 0.0 {
                *vis = Visibility::Inherited;
            }
            continue;
        }
        let needs = health.hp < health.max || health.bleeding > 0.0;
        if needs && health.alive() && tf.translation.distance(player.translation) < tuning.loot.pickup_radius {
            health.heal();
            kit.down = tuning.loot.respawn * 0.5;
            *vis = Visibility::Hidden;
        }
    }
}

fn extract(
    time: Res<Time>,
    tuning: Res<Tuning>,
    health: Res<PlayerHealth>,
    file: Res<SaveFile>,
    player: Single<&Transform, With<Player>>,
    pads: Query<(&ExtractPad, &Transform), Without<Player>>,
    mut inv: ResMut<Inventory>,
    mut save: ResMut<Save>,
    mut input: ResMut<PlayerInput>,
) {
    inv.just_extracted = false;
    inv.extracted_keys.clear();
    let on_pad = pads.iter().any(|(pad, tf)| tf.translation.xz().distance(player.translation.xz()) < pad.radius);
    let has_haul = inv.carried > 0 || !inv.keys.is_empty();
    if !(on_pad && has_haul && health.alive()) {
        inv.extracting = 0.0;
        return;
    }
    inv.extracting += time.delta_secs();
    if inv.extracting < tuning.loot.extract_time {
        return;
    }
    save.banked += inv.carried;
    save.runs += 1;
    inv.carried = 0;
    inv.extracting = 0.0;
    inv.extracted_keys = std::mem::take(&mut inv.keys);
    inv.just_extracted = true;
    file.write(&save);
    // The run is over: back to base camp.
    input.reset_pressed = true;
}

fn lose_on_death(health: Res<PlayerHealth>, file: Res<SaveFile>, mut inv: ResMut<Inventory>, mut save: ResMut<Save>, mut loots: Query<&mut Loot>) {
    inv.just_died = false;
    let alive = health.alive();
    if inv.was_alive && !alive {
        inv.just_died = true;
        inv.carried = 0;
        // Mission caches come back quickly so the mission can be retried.
        for key in inv.keys.drain(..) {
            for mut loot in &mut loots {
                if loot.key == Some(key) {
                    loot.down = loot.down.min(2.0);
                }
            }
        }
        save.deaths += 1;
        file.write(&save);
    }
    inv.was_alive = alive;
}
