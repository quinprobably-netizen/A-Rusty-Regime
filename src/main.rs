mod body;
mod camera;
mod controller;
mod hud;
mod input;
mod level;
mod targets;
mod tuning;
mod viewmodel;
mod weapon;
#[cfg(test)]
mod tests;

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
            viewmodel::ViewModelPlugin,
            targets::TargetsPlugin,
            hud::HudPlugin,
            level::LevelPlugin,
        ))
        .add_systems(Update, dev_screenshot.run_if(|| std::env::var_os("RUST_REGIME_SCREENSHOT").is_some()))
        .run();
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
) {
    use bevy::render::view::screenshot::{Screenshot, save_to_disk};
    *frames += 1;
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
            tf.translation = Vec3::new(x, 1.0, z);
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
