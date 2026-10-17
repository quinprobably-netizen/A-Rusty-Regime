mod body;
mod camera;
mod controller;
mod health;
mod hud;
mod input;
mod island;
mod level;
mod targets;
mod terrain;
mod tuning;
mod viewmodel;
mod weapon;
#[cfg(test)]
mod tests;
mod vehicle;
mod loot;
mod mission;
mod bots;
mod look;
mod veg;
mod sound;
mod roads;
mod world;

use avian3d::prelude::*;
use bevy::prelude::*;

fn main() {
    let tuning = tuning::load();
    App::new()
        .add_plugins((
            DefaultPlugins.set(WindowPlugin {
                primary_window: Some(Window {
                    title: "Rust Regime".into(),
                    ..default()
                }),
                ..default()
            }),
            PhysicsPlugins::default(),
        ))
        // TF2 simulates at 66 ticks per second.
        .insert_resource(Time::<Fixed>::from_hz(66.0))
        .insert_resource(Gravity(Vec3::NEG_Y * tuning.gravity))
        .add_plugins((
            tuning::TuningPlugin,
            input::InputPlugin,
            controller::ControllerPlugin,
            camera::CameraPlugin,
            body::BodyPlugin,
            weapon::WeaponPlugin,
            health::HealthPlugin,
            viewmodel::ViewModelPlugin,
            targets::TargetsPlugin,
            hud::HudPlugin,
            vehicle::VehiclePlugin,
            loot::LootPlugin,
            mission::MissionPlugin,
            sound::SoundPlugin,
        ))
        .add_plugins(level_plugin())
        .add_systems(Update, dev_screenshot.run_if(|| std::env::var_os("RUST_REGIME_SCREENSHOT").is_some()))
        .run();
}

/// `RUST_REGIME_LEVEL=arena` runs the old walled arena; anything else is the island.
fn level_plugin() -> bevy::app::PluginGroupBuilder {
    use bevy::app::PluginGroup;
    struct Level(bool);
    impl PluginGroup for Level {
        fn build(self) -> bevy::app::PluginGroupBuilder {
            let group = bevy::app::PluginGroupBuilder::start::<Self>();
            let group = if self.0 { group.add(level::LevelPlugin) } else { group.add(terrain::TerrainPlugin).add(look::LookPlugin).add(veg::VegPlugin).add(world::WorldPlugin) };
            if std::env::var("RUST_REGIME_MODE").is_ok_and(|m| m == "6v6") { group.add(bots::MatchPlugin) } else { group }
        }
    }
    Level(std::env::var("RUST_REGIME_LEVEL").is_ok_and(|v| v == "arena")).build()
}

/// Dev aid: `RUST_REGIME_SCREENSHOT=shot.png` saves a frame after a few
/// seconds and quits, so the level can be checked on a machine with no display.
fn dev_screenshot(
    mut commands: Commands,
    mut frames: Local<u32>,
    mut exit: MessageWriter<AppExit>,
    mut arsenal: ResMut<weapon::Arsenal>,
    mut view: ResMut<input::ViewAngles>,
    mut player: Single<(&mut controller::Player, &mut Transform)>,
    heightmap: Option<Res<terrain::Heightmap>>,
    vehicles: Query<(&Transform, &vehicle::Vehicle, Option<&Children>), Without<controller::Player>>,
) {
    use bevy::render::view::screenshot::{Screenshot, save_to_disk};
    *frames += 1;
    if *frames == 150 {
        for (tf, v, children) in &vehicles {
            info!("{} at {} up {} grounded {} parts {}", v.spec.name, tf.translation, tf.rotation * Vec3::Y, v.grounded_wheels(), children.map_or(0, |c| c.len()));
        }
    }
    // Optional "slot,yaw_degrees,x,z,pitch_degrees" to pick a weapon, spot and look direction.
    if *frames == 1 && let Ok(spec) = std::env::var("RUST_REGIME_SCREENSHOT_VIEW") {
        let mut parts = spec.split(',').filter_map(|v| v.trim().parse::<f32>().ok());
        if let Some(slot) = parts.next() {
            arsenal.select(slot as usize);
            arsenal.switch_time = 0.0;
        }
        if let Some(yaw) = parts.next() {
            view.yaw = yaw.to_radians();
        }
        if let (Some(x), Some(z)) = (parts.next(), parts.next()) {
            let (p, tf) = &mut *player;
            let y = heightmap.as_ref().map_or(0.0, |hm| hm.height_at(x, z)) + 1.0;
            tf.translation = Vec3::new(x, y, z);
            p.prev_pos = tf.translation;
        }
        if let Some(pitch) = parts.next() {
            view.pitch = pitch.to_radians();
        }
    }
    if *frames == 150 {
        let path = std::env::var("RUST_REGIME_SCREENSHOT").unwrap_or_default();
        commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
    }
    if *frames == 240 {
        exit.write(AppExit::Success);
    }
}
