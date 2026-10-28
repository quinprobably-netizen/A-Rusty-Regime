mod abilities;
mod arms;
mod body;
mod camo;
mod character;
mod dressing;
mod aim_assist;
mod camera;
mod controller;
mod health;
mod hud;
mod controls;
mod input;
mod targets;
mod tuning;
mod viewmodel;
mod wardrobe;
mod weapon;
#[cfg(test)]
mod tests;
mod vehicle;
mod loot;
mod boot;
mod sound;
mod menu;
mod near;
mod gunsmith;
mod quartermaster;
mod scope;
mod fingers;
mod system;
mod surface;
mod planet;
mod solar;
mod comic;

use avian3d::prelude::*;
use bevy::prelude::*;

fn main() {
    input::install_pad_mappings();
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
        .add_plugins(boot::BootPlugin)
        .add_plugins((
            tuning::TuningPlugin,
            input::InputPlugin,
            controller::ControllerPlugin,
            camera::CameraPlugin,
            character::CharacterPlugin,
            body::BodyPlugin,
            weapon::WeaponPlugin,
            health::HealthPlugin,
            viewmodel::ViewModelPlugin,
            targets::TargetsPlugin,
            hud::HudPlugin,
            vehicle::VehiclePlugin,
            loot::LootPlugin,
            sound::SoundPlugin,
        ))
        .add_plugins((abilities::AbilitiesPlugin, arms::ArmsPlugin, wardrobe::WardrobePlugin, dressing::DressingPlugin, gunsmith::GunsmithPlugin, menu::MenuPlugin, scope::ScopePlugin, fingers::FingersPlugin, aim_assist::AimAssistPlugin, comic::ComicPlugin, near::NearPlugin))
        .add_plugins(level_plugin())
        .add_systems(Update, dev_screenshot.run_if(|| std::env::var_os("RUST_REGIME_SCREENSHOT").is_some()))
        .run();
    // Picking another map started a fresh run of the game; stay until it ends.
    if let Some(code) = menu::wait_for_relaunch() {
        std::process::exit(code);
    }
}

/// The solar system is the only level.
fn level_plugin() -> solar::SolarPlugin {
    solar::SolarPlugin
}

/// Dev aid: `RUST_REGIME_SCREENSHOT=shot.png` saves a frame after a few
/// seconds and quits, so the level can be checked on a machine with no display.
fn dev_screenshot(
    mut commands: Commands,
    mut frames: Local<u32>,
    mut waited: Local<u32>,
    arms: Query<&Visibility, With<arms::Arms>>,
    tuning: Res<tuning::Tuning>,
    body: Query<&character::Rig, With<body::Body>>,
    mut exit: MessageWriter<AppExit>,
    mut arsenal: ResMut<weapon::Arsenal>,
    mut view: ResMut<input::ViewAngles>,
    mut player: Single<(&mut controller::Player, &mut Transform)>,
    surface: Res<surface::Surface>,
    origin: Option<Res<surface::Origin>>,
    vehicles: Query<(&Transform, &vehicle::Vehicle, Option<&Children>), Without<controller::Player>>,
) {
    use bevy::render::view::screenshot::{Screenshot, save_to_disk};
    // `RUST_REGIME_SCREENSHOT_FRAME` waits longer for slow loads (default 150).
    let at = std::env::var("RUST_REGIME_SCREENSHOT_FRAME").ok().and_then(|f| f.parse().ok()).unwrap_or(150u32);
    // The first-person arms load last: hold the count until they show (for a while at most), so a
    // slow load doesn't leave them out of the shot. Third person waits for the body instead.
    let loading = if tuning.third_person { body.iter().any(|r| !r.ready()) } else { arms.iter().any(|v| *v == Visibility::Hidden) };
    if *frames > 1 && *frames < at && loading && *waited < at * 2 {
        *waited += 1;
        return;
    }
    *frames += 1;
    if *frames == at {
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
        // On a round body the spot is an offset east and south of where the player stands.
        if let (Some(x), Some(z)) = (parts.next(), parts.next()) {
            let (p, tf) = &mut *player;
            if matches!(*surface, surface::Surface::Sphere(_)) {
                let frame = surface.frame(origin.map_or(tf.translation, |o| o.body(tf.translation)));
                tf.translation += frame * Vec3::new(x, 0.0, z);
            }
            p.prev_pos = tf.translation;
        }
        if let Some(pitch) = parts.next() {
            view.pitch = pitch.to_radians();
        }
    }
    if *frames == at {
        let path = std::env::var("RUST_REGIME_SCREENSHOT").unwrap_or_default();
        commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
    }
    if *frames == at + 90 {
        exit.write(AppExit::Success);
    }
}
