use bevy::prelude::*;
use serde::Deserialize;

/// Every tunable number in one place. Loaded from `tuning.toml` at startup
/// (missing keys fall back to these defaults); press F5 to reload live.
///
/// Distances are meters. Source-engine values are converted with
/// 1 Hammer unit = 0.022 m, so the TF2 hull (82u) maps to our 1.8 m player.
#[derive(Resource, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct Tuning {
    // Core Source movement
    pub gravity: f32,
    pub max_speed: f32,
    pub crouch_speed_mult: f32,
    pub accelerate: f32,
    pub air_accelerate: f32,
    pub air_speed_cap: f32,
    pub friction: f32,
    pub stop_speed: f32,
    pub jump_speed: f32,
    pub jump_buffer: f32,
    pub auto_bhop: bool,
    /// 0 disables. Otherwise landing-jumps above `cap * max_speed` are scaled down (TF2 style).
    pub bhop_speed_cap: f32,
    pub ramp_launch_speed: f32,
    pub walkable_normal_y: f32,
    pub step_height: f32,
    pub terminal_velocity: f32,

    // Hull
    pub radius: f32,
    pub stand_height: f32,
    pub crouch_height: f32,
    pub eye_from_top: f32,

    // Slide
    pub slide_min_speed: f32,
    pub slide_boost: f32,
    pub slide_boost_cooldown: f32,
    pub slide_friction: f32,
    pub slide_end_speed: f32,
    pub slide_steer: f32,

    // Wall run / wall jump
    pub wallrun_min_speed: f32,
    pub wallrun_speed: f32,
    pub wallrun_max_time: f32,
    pub wallrun_gravity_scale: f32,
    pub wall_jump_out: f32,
    pub wall_jump_up: f32,
    pub wall_reach: f32,

    // Mantle
    pub mantle_min_height: f32,
    pub mantle_max_height: f32,
    pub mantle_time: f32,

    // Rocket launcher
    pub rocket_damage: f32,
    pub rocket_speed: f32,
    pub rocket_cooldown: f32,
    pub blast_radius: f32,
    pub self_knockback: f32,
    pub prop_knockback: f32,
    pub prop_ref_mass: f32,
    pub push_strength: f32,

    // Hitscan guns (tables `[rifle]`, `[shotgun]`, `[pistol]` in tuning.toml)
    pub rifle: Gun,
    pub shotgun: Gun,
    pub pistol: Gun,

    // Shooting range targets
    pub target_health: f32,
    pub drone_health: f32,
    pub target_respawn: f32,
    pub drone_speed: f32,

    // Island level (table `[island]`)
    pub island: Island,
    pub soldier: Soldier,
    pub player: PlayerTuning,

    // Look
    pub mouse_sensitivity: f32,
    pub stick_yaw_speed: f32,
    pub stick_pitch_speed: f32,
    pub stick_deadzone: f32,
    pub stick_look_curve: f32,
    pub invert_y: bool,
    pub fov_degrees: f32,
    pub wallrun_tilt_degrees: f32,
    pub rumble: bool,
}

impl Default for Tuning {
    fn default() -> Self {
        Self {
            gravity: 17.6,
            max_speed: 7.5,
            crouch_speed_mult: 0.33,
            accelerate: 10.0,
            air_accelerate: 10.0,
            air_speed_cap: 0.66,
            friction: 4.0,
            stop_speed: 2.2,
            jump_speed: 6.35,
            jump_buffer: 0.08,
            auto_bhop: false,
            bhop_speed_cap: 0.0,
            ramp_launch_speed: 4.0,
            walkable_normal_y: 0.7,
            step_height: 0.4,
            terminal_velocity: 77.0,

            radius: 0.4,
            stand_height: 1.8,
            crouch_height: 1.36,
            eye_from_top: 0.2,

            slide_min_speed: 6.0,
            slide_boost: 2.5,
            slide_boost_cooldown: 1.0,
            slide_friction: 0.6,
            slide_end_speed: 3.0,
            slide_steer: 1.5,

            wallrun_min_speed: 5.0,
            wallrun_speed: 9.0,
            wallrun_max_time: 1.6,
            wallrun_gravity_scale: 0.25,
            wall_jump_out: 6.0,
            wall_jump_up: 6.5,
            wall_reach: 0.3,

            mantle_min_height: 0.45,
            mantle_max_height: 1.5,
            mantle_time: 0.3,

            rocket_damage: 90.0,
            rocket_speed: 24.0,
            rocket_cooldown: 0.8,
            blast_radius: 3.2,
            self_knockback: 13.0,
            prop_knockback: 14.0,
            prop_ref_mass: 40.0,
            push_strength: 0.6,

            rifle: Gun {
                damage: 18.0,
                cooldown: 0.09,
                pellets: 1,
                spread_degrees: 0.6,
                range: 200.0,
                prop_impulse: 3.0,
                automatic: true,
                kick: 0.5,
            },
            shotgun: Gun {
                damage: 9.0,
                cooldown: 0.75,
                pellets: 10,
                spread_degrees: 5.0,
                range: 40.0,
                prop_impulse: 2.5,
                automatic: false,
                kick: 2.0,
            },
            pistol: Gun {
                damage: 25.0,
                cooldown: 0.17,
                pellets: 1,
                spread_degrees: 0.3,
                range: 150.0,
                prop_impulse: 4.0,
                automatic: false,
                kick: 0.8,
            },

            target_health: 100.0,
            drone_health: 60.0,
            target_respawn: 3.0,
            drone_speed: 2.5,

            island: Island::default(),
            soldier: Soldier::default(),
            player: PlayerTuning::default(),

            mouse_sensitivity: 0.002,
            stick_yaw_speed: 4.5,
            stick_pitch_speed: 3.0,
            stick_deadzone: 0.15,
            stick_look_curve: 2.0,
            invert_y: false,
            fov_degrees: 75.0,
            wallrun_tilt_degrees: 12.0,
            rumble: true,
        }
    }
}

/// One hitscan gun. `pellets` rays per shot, each deviating up to
/// `spread_degrees`; `prop_impulse` is the velocity change a hit adds to a
/// `prop_ref_mass` prop; `kick` is how hard the viewmodel recoils.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct Gun {
    pub damage: f32,
    pub cooldown: f32,
    pub pellets: u32,
    pub spread_degrees: f32,
    pub range: f32,
    pub prop_impulse: f32,
    pub automatic: bool,
    pub kick: f32,
}

impl Default for Gun {
    fn default() -> Self {
        Tuning::default().rifle
    }
}

/// The island level: a seeded heightmap `size` meters square sampled every
/// `cell` meters, peaks up to `height`, water at `water_level`. The stage 1
/// sites stay inside `core` meters of the center.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Island {
    pub seed: u32,
    pub size: f32,
    pub cell: f32,
    pub core: f32,
    pub height: f32,
    pub water_level: f32,
}

impl Default for Island {
    fn default() -> Self {
        Self { seed: 7, size: 4096.0, cell: 4.0, core: 1500.0, height: 260.0, water_level: 0.0 }
    }
}

/// Patrolling soldiers (table `[soldier]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Soldier {
    pub health: f32,
    pub speed: f32,
    pub sight: f32,
    pub fire_interval: f32,
    pub damage: f32,
    /// Radians of aim error.
    pub spread: f32,
    pub forget: f32,
}

impl Default for Soldier {
    fn default() -> Self {
        Self { health: 100.0, speed: 3.5, sight: 40.0, fire_interval: 0.6, damage: 12.0, spread: 0.02, forget: 4.0 }
    }
}

/// Player health (table `[player]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct PlayerTuning {
    pub health: f32,
    pub regen_delay: f32,
    pub regen_rate: f32,
    pub respawn_delay: f32,
}

impl Default for PlayerTuning {
    fn default() -> Self {
        Self { health: 100.0, regen_delay: 5.0, regen_rate: 20.0, respawn_delay: 2.0 }
    }
}

const PATH: &str = "tuning.toml";

pub struct TuningPlugin;

impl Plugin for TuningPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(load())
            .add_systems(Update, reload.run_if(resource_exists::<ButtonInput<KeyCode>>));
    }
}

pub fn load() -> Tuning {
    match std::fs::read_to_string(PATH) {
        Ok(text) => toml::from_str(&text).unwrap_or_else(|e| {
            warn!("{PATH} is invalid, using defaults: {e}");
            Tuning::default()
        }),
        Err(_) => Tuning::default(),
    }
}

fn reload(keys: Res<ButtonInput<KeyCode>>, mut tuning: ResMut<Tuning>) {
    if keys.just_pressed(KeyCode::F5) {
        *tuning = load();
        info!("Reloaded {PATH}");
    }
}
