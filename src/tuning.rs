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

    // Air jump (double jump): extra jumps after leaving the ground, reset on ground, wall, mantle, grapple
    pub air_jumps: u32,
    pub air_jump_speed: f32,
    /// 0 keeps momentum, 1 fully redirects horizontal speed to the wish direction.
    pub air_jump_redirect: f32,

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
    /// Rockets in the tube and seconds to reload it.
    pub rocket_mag: u32,
    pub rocket_reload: f32,

    // Hitscan guns (tables `[rifle]`, `[shotgun]`, `[pistol]`, `[smg]`, `[dmr]`, `[revolver]`)
    pub rifle: Gun,
    pub shotgun: Gun,
    pub pistol: Gun,
    pub smg: Gun,
    pub dmr: Gun,
    pub revolver: Gun,
    pub grenade: GrenadeTuning,
    pub harpoon: HarpoonTuning,
    pub fist: FistTuning,
    pub knife: KnifeTuning,

    // Shooting range targets
    pub target_health: f32,
    /// Damage multipliers for hits above the shoulders and below the hips.
    pub headshot: f32,
    pub legshot: f32,
    pub drone_health: f32,
    pub target_respawn: f32,
    pub drone_speed: f32,

    // Island level (table `[island]`)
    pub island: Island,
    pub soldier: Soldier,
    pub player: PlayerTuning,
    pub vehicle: VehicleTuning,
    pub loot: LootTuning,
    pub r#match: MatchTuning,
    pub grapple: GrappleTuning,
    pub graphics: Graphics,
    pub sound: Sound,
    pub world: WorldTuning,
    pub terrain: TerrainTuning,

    // Look
    pub mouse_sensitivity: f32,
    pub stick_yaw_speed: f32,
    pub stick_pitch_speed: f32,
    pub stick_deadzone: f32,
    pub stick_look_curve: f32,
    pub invert_y: bool,
    pub fov_degrees: f32,
    /// Play from behind the right shoulder (T toggles), and how far back and right the camera sits.
    pub third_person: bool,
    pub third_person_distance: f32,
    pub third_person_shoulder: f32,
    /// The gun and arms are drawn as if through this narrower vertical field of view, as shooters
    /// do: a wide view stretches anything a hand's breadth from the eye.
    pub viewmodel_fov_degrees: f32,
    /// Aim down sights (right mouse): field of view multiplier and the time to settle.
    pub ads_fov: f32,
    /// The view's multiplier aiming through a magnifying scope: the scope's own picture does the
    /// zooming, so the screen around it stays near normal.
    pub ads_fov_scoped: f32,
    pub ads_time: f32,
    pub wallrun_tilt_degrees: f32,
    pub rumble: bool,
}

impl Default for Tuning {
    fn default() -> Self {
        Self {
            gravity: 9.8,
            max_speed: 7.5,
            crouch_speed_mult: 0.33,
            accelerate: 10.0,
            air_accelerate: 10.0,
            air_speed_cap: 0.66,
            friction: 4.0,
            stop_speed: 2.2,
            jump_speed: 4.74,
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
            wall_jump_up: 4.85,
            wall_reach: 0.3,
            air_jumps: 1,
            air_jump_speed: 4.74,
            air_jump_redirect: 0.6,

            mantle_min_height: 0.45,
            mantle_max_height: 1.5,
            mantle_time: 0.3,

            rocket_damage: 90.0,
            rocket_speed: 24.0,
            rocket_cooldown: 0.8,
            blast_radius: 3.2,
            self_knockback: 9.7,
            prop_knockback: 14.0,
            prop_ref_mass: 40.0,
            push_strength: 0.6,
            rocket_mag: 4,
            rocket_reload: 1.4,

            rifle: Gun {
                damage: 18.0,
                velocity: 850.0,
                drag: 0.0006,
                recoil_up: 0.35,
                recoil_side: 0.18,
                heat_spread: 2.5,
                ads_spread: 0.4,
                cooldown: 0.09,
                pellets: 1,
                spread_degrees: 0.6,
                range: 200.0,
                prop_impulse: 3.0,
                automatic: true,
                kick: 0.5,
                mag: 30,
                reload: 2.0,
                scope_mag: 3.0,
            },
            shotgun: Gun {
                damage: 9.0,
                velocity: 400.0,
                drag: 0.002,
                recoil_up: 2.5,
                recoil_side: 0.6,
                heat_spread: 1.0,
                ads_spread: 0.7,
                cooldown: 0.75,
                pellets: 10,
                spread_degrees: 5.0,
                range: 40.0,
                prop_impulse: 2.5,
                automatic: false,
                kick: 2.0,
                mag: 20,
                reload: 2.6,
                scope_mag: 3.0,
            },
            pistol: Gun {
                damage: 25.0,
                velocity: 360.0,
                drag: 0.001,
                recoil_up: 1.1,
                recoil_side: 0.35,
                heat_spread: 1.5,
                ads_spread: 0.5,
                cooldown: 0.17,
                pellets: 1,
                spread_degrees: 0.3,
                range: 150.0,
                prop_impulse: 4.0,
                automatic: false,
                kick: 0.8,
                mag: 9,
                reload: 1.5,
                scope_mag: 0.0,
            },
            smg: Gun {
                damage: 12.0,
                velocity: 400.0,
                drag: 0.001,
                recoil_up: 0.25,
                recoil_side: 0.2,
                heat_spread: 2.0,
                ads_spread: 0.5,
                cooldown: 0.06,
                pellets: 1,
                spread_degrees: 1.0,
                range: 90.0,
                prop_impulse: 2.0,
                automatic: true,
                kick: 0.35,
                mag: 40,
                reload: 1.8,
                scope_mag: 3.0,
            },
            dmr: Gun {
                damage: 45.0,
                velocity: 900.0,
                drag: 0.0005,
                recoil_up: 1.6,
                recoil_side: 0.3,
                heat_spread: 3.0,
                ads_spread: 0.25,
                cooldown: 0.28,
                pellets: 1,
                spread_degrees: 0.15,
                range: 300.0,
                prop_impulse: 5.0,
                automatic: false,
                kick: 1.6,
                mag: 20,
                reload: 2.4,
                scope_mag: 8.0,
            },
            revolver: Gun {
                damage: 60.0,
                velocity: 420.0,
                drag: 0.001,
                recoil_up: 3.0,
                recoil_side: 0.5,
                heat_spread: 1.5,
                ads_spread: 0.5,
                cooldown: 0.45,
                pellets: 1,
                spread_degrees: 0.25,
                range: 160.0,
                prop_impulse: 6.0,
                automatic: false,
                kick: 2.4,
                mag: 6,
                reload: 2.2,
                scope_mag: 3.0,
            },
            grenade: GrenadeTuning::default(),
            harpoon: HarpoonTuning::default(),
            fist: FistTuning::default(),
            knife: KnifeTuning::default(),

            target_health: 100.0,
            headshot: 2.5,
            legshot: 0.6,
            drone_health: 60.0,
            target_respawn: 3.0,
            drone_speed: 2.5,

            island: Island::default(),
            soldier: Soldier::default(),
            terrain: TerrainTuning::default(),
            player: PlayerTuning::default(),
            vehicle: VehicleTuning::default(),
            loot: LootTuning::default(),
            r#match: MatchTuning::default(),
            grapple: GrappleTuning::default(),
            graphics: Graphics::default(),
            sound: Sound::default(),
            world: WorldTuning::default(),

            mouse_sensitivity: 0.002,
            stick_yaw_speed: 4.5,
            stick_pitch_speed: 3.0,
            stick_deadzone: 0.15,
            stick_look_curve: 2.0,
            invert_y: false,
            fov_degrees: 75.0,
            third_person: false,
            third_person_distance: 2.6,
            third_person_shoulder: 0.55,
            viewmodel_fov_degrees: 65.0,
            ads_fov: 0.7,
            ads_fov_scoped: 0.85,
            ads_time: 0.15,
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
    /// Muzzle velocity (m/s); bullets drop under 9.81 m/s² and slow by `drag` per metre.
    pub velocity: f32,
    pub drag: f32,
    /// View kick per shot (degrees) up and sideways; the sideways kick follows a pattern.
    pub recoil_up: f32,
    pub recoil_side: f32,
    /// Spread multiplier at full heat (sustained fire) and while aiming down sights.
    pub heat_spread: f32,
    pub ads_spread: f32,
    pub cooldown: f32,
    pub pellets: u32,
    pub spread_degrees: f32,
    pub range: f32,
    pub prop_impulse: f32,
    pub automatic: bool,
    pub kick: f32,
    /// Rounds per magazine and seconds to reload it.
    pub mag: u32,
    pub reload: f32,
    /// The fitted scope's magnification (fixed); 0 for a gun with no scope part.
    pub scope_mag: f32,
}

/// The break-action grenade launcher: bouncy frags that burst on a fuse or on hitting a target.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct GrenadeTuning {
    pub damage: f32,
    pub radius: f32,
    pub speed: f32,
    /// Upward speed added at launch, for a lob.
    pub lift: f32,
    pub gravity: f32,
    /// Speed kept per bounce.
    pub bounce: f32,
    pub fuse: f32,
    pub self_knockback: f32,
    pub cooldown: f32,
    pub mag: u32,
    pub reload: f32,
}

impl Default for GrenadeTuning {
    fn default() -> Self {
        Self { damage: 100.0, radius: 3.5, speed: 22.0, lift: 2.5, gravity: 12.0, bounce: 0.45, fuse: 2.2, self_knockback: 8.2, cooldown: 0.6, mag: 1, reload: 1.8 }
    }
}

/// The harpoon: a fast spear that yanks you to the wall it hits, or yanks what it hits to you.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct HarpoonTuning {
    pub damage: f32,
    pub speed: f32,
    pub gravity: f32,
    /// Seconds the spear flies before it gives up.
    pub life: f32,
    /// Speed given to you toward the spear when it sticks in the world.
    pub pull_player: f32,
    /// Speed given to a prop or a falling body toward you.
    pub pull_target: f32,
    pub cooldown: f32,
    pub mag: u32,
    pub reload: f32,
}

impl Default for HarpoonTuning {
    fn default() -> Self {
        Self { damage: 45.0, speed: 70.0, gravity: 4.0, life: 1.2, pull_player: 17.0, pull_target: 14.0, cooldown: 0.4, mag: 1, reload: 1.6 }
    }
}

/// The power fist: a short punch that knocks things away and, off any surface, launches you back.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct FistTuning {
    pub damage: f32,
    pub range: f32,
    pub knockback: f32,
    /// Speed you get away from whatever you punched.
    pub launch: f32,
    pub cooldown: f32,
}

impl Default for FistTuning {
    fn default() -> Self {
        Self { damage: 70.0, range: 2.4, knockback: 16.0, launch: 11.0, cooldown: 0.7 }
    }
}

/// The knife: a quick slash, short reach, no recoil and no magazine.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct KnifeTuning {
    pub damage: f32,
    pub range: f32,
    pub knockback: f32,
    pub cooldown: f32,
}

impl Default for KnifeTuning {
    fn default() -> Self {
        Self { damage: 55.0, range: 2.1, knockback: 3.0, cooldown: 0.42 }
    }
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
    /// How close a soldier gets to an enemy it can see.
    pub hold: f32,
    /// Their bullets' muzzle velocity.
    pub bullet_speed: f32,
    /// How far a gunshot carries (m): soldiers who hear one go to look.
    pub hearing: f32,
    /// A soldier who sees an enemy calls it out to squad mates this close (m).
    pub squad_radius: f32,
    /// Seconds a soldier stays in cover after being hit before peeking out.
    pub cover_time: f32,
}

impl Default for Soldier {
    fn default() -> Self {
        Self { health: 100.0, speed: 3.5, sight: 40.0, fire_interval: 0.6, damage: 12.0, spread: 0.02, forget: 4.0, hold: 12.0, bullet_speed: 750.0, hearing: 150.0, squad_radius: 60.0, cover_time: 2.5 }
    }
}

/// The planet's terrain and streaming (table `[terrain]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct TerrainTuning {
    /// The finest terrain cell (m).
    pub cell: f32,
    /// A chunk splits when the player will be nearer than this many chunk sizes in a second.
    pub split: f32,
    /// Solid ground and awake physics within this of the player (m).
    pub bubble: f32,
    /// Sites load within this (m) and unload 500 m further out.
    pub site_range: f32,
    /// The world re-centres on the player after this far (m).
    pub origin_step: f32,
    /// Chunk builds in flight.
    pub workers: usize,
}

impl Default for TerrainTuning {
    fn default() -> Self {
        Self { cell: 0.5, split: 2.5, bubble: 400.0, site_range: 1500.0, origin_step: 2000.0, workers: 4 }
    }
}

impl TerrainTuning {
    /// A split chunk merges back only past this many chunk sizes, half a chunk beyond `split`.
    pub fn merge(&self) -> f32 {
        self.split + 0.5
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
    /// Regen stops at this fraction of max health; medkits do the rest.
    pub regen_cap: f32,
    /// A hit of at least `bleed_threshold` bleeds `bleed_rate` hp/s for `bleed_time` s (no regen meanwhile).
    pub bleed_threshold: f32,
    pub bleed_rate: f32,
    pub bleed_time: f32,
}

impl Default for PlayerTuning {
    fn default() -> Self {
        Self { health: 100.0, regen_delay: 5.0, regen_rate: 20.0, respawn_delay: 2.0, regen_cap: 0.6, bleed_threshold: 15.0, bleed_rate: 2.0, bleed_time: 8.0 }
    }
}

/// Vehicles (table `[vehicle]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct VehicleTuning {
    /// How close you must stand to press E.
    pub enter_radius: f32,
    /// Peak tyre grip as a fraction of the wheel load.
    pub mu: f32,
    pub rolling: f32,
    /// How fast a bike rolls toward its balanced lean (1/s).
    pub bike_upright: f32,
    /// Grip off the roads, as a fraction of `mu` (grass and dirt hold less than a packed road).
    pub offroad_grip: f32,
    /// A speed change bigger than this in one tick (m/s) is a crash that damages the vehicle.
    pub crash_speed: f32,
    /// Seconds a wreck sits before a fresh vehicle replaces it at its spot.
    pub wreck_time: f32,
}

impl Default for VehicleTuning {
    fn default() -> Self {
        Self { enter_radius: 4.0, mu: 1.0, rolling: 0.02, bike_upright: 6.0, offroad_grip: 0.7, crash_speed: 9.0, wreck_time: 30.0 }
    }
}

/// The extraction loop (table `[loot]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct LootTuning {
    pub pickup_radius: f32,
    /// Seconds a taken cache stays gone.
    pub respawn: f32,
    /// Seconds on a pad to extract.
    pub extract_time: f32,
}

impl Default for LootTuning {
    fn default() -> Self {
        Self { pickup_radius: 1.6, respawn: 300.0, extract_time: 8.0 }
    }
}

/// The 6v6 mode (table `[match]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct MatchTuning {
    pub kills_to_win: u32,
    pub bots_per_team: u32,
}

impl Default for MatchTuning {
    fn default() -> Self {
        Self { kills_to_win: 30, bots_per_team: 6 }
    }
}

/// The grapple ability (table `[grapple]`). Titanfall 2 ships 50 power to fire of 100, 50/s while
/// pulling and a 28 m rope; we keep the meter but make it nearly free.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct GrappleTuning {
    pub range: f32,
    pub power_max: f32,
    pub power_to_fire: f32,
    /// Per second while pulling.
    pub power_use_rate: f32,
    /// Per second while not pulling.
    pub power_regen: f32,
    pub pull_accel: f32,
    pub pull_max_speed: f32,
    /// Pull direction blends from the rope toward the look direction by this much.
    pub look_steer: f32,
    /// m/s added along the velocity when you jump off the rope.
    pub release_boost: f32,
    /// Let go this close to the anchor.
    pub arrive_distance: f32,
    /// How much of gravity the taut rope carries while you are pulled (0 none, 1 all).
    pub gravity_cancel: f32,
}

impl Default for GrappleTuning {
    fn default() -> Self {
        Self {
            range: 30.0,
            power_max: 100.0,
            power_to_fire: 10.0,
            power_use_rate: 10.0,
            power_regen: 60.0,
            pull_accel: 55.0,
            pull_max_speed: 22.0,
            look_steer: 0.6,
            release_boost: 2.0,
            arrive_distance: 1.5,
            gravity_cancel: 0.8,
        }
    }
}

/// The look (table `[graphics]`): the physical sky and post effects, texture tiling and the vegetation.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Graphics {
    pub atmosphere: bool,
    pub ssao: bool,
    pub taa: bool,
    pub bloom: bool,
    /// Camera EV100; 15 is full sun.
    pub exposure: f32,
    pub shadow_distance: f32,
    /// Metres per texture tile.
    pub grass_tile: f32,
    pub dirt_tile: f32,
    pub rock_tile: f32,
    pub sand_tile: f32,
    pub wave_height: f32,
    pub wave_length: f32,
    /// Multiplies the tree and scrub density; 0 for none.
    pub trees: f32,
    pub grass: bool,
    /// Grass blades per 24 m cell.
    pub grass_density: u32,
    /// Trees fade out past this (m).
    pub tree_range: f32,
}

impl Default for Graphics {
    fn default() -> Self {
        Self {
            atmosphere: true,
            ssao: true,
            taa: true,
            bloom: true,
            exposure: 15.0,
            shadow_distance: 500.0,
            grass_tile: 3.0,
            dirt_tile: 4.0,
            rock_tile: 6.0,
            sand_tile: 3.0,
            wave_height: 0.25,
            wave_length: 9.0,
            trees: 1.0,
            grass: true,
            grass_density: 4000,
            tree_range: 900.0,
        }
    }
}

/// Time and weather (table `[world]`).
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct WorldTuning {
    /// The hour the game starts at.
    pub start_hour: f32,
    /// Real minutes per game day; 0 stops the clock.
    pub day_minutes: f32,
    /// Weather changes; false keeps it clear.
    pub weather: bool,
    /// Roughly how long each sky lasts (real minutes).
    pub weather_minutes: f32,
    /// "auto", or hold one sky: clear, overcast, rain or fog.
    pub sky: String,
}

impl Default for WorldTuning {
    fn default() -> Self {
        Self { start_hour: 15.0, day_minutes: 48.0, weather: true, weather_minutes: 6.0, sky: "auto".into() }
    }
}

/// Volumes (table `[sound]`), 0 to 1.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Sound {
    pub master: f32,
    pub guns: f32,
    pub effects: f32,
    pub engine: f32,
    pub ambience: f32,
}

impl Default for Sound {
    fn default() -> Self {
        Self { master: 0.8, guns: 0.9, effects: 0.7, engine: 0.6, ambience: 0.5 }
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
    let mut tuning = match std::fs::read_to_string(PATH) {
        Ok(text) => toml::from_str(&text).unwrap_or_else(|e| {
            warn!("{PATH} is invalid, using defaults: {e}");
            Tuning::default()
        }),
        Err(_) => Tuning::default(),
    };
    // What the settings menu saved wins over the file, so F5 keeps the player's choices.
    if let Some(settings) = crate::menu::Settings::load() {
        settings.apply(&mut tuning);
    }
    tuning
}

impl Tuning {
    /// The hitscan gun's table, or `None` for the launchers, the harpoon and the fist.
    pub fn gun(&self, kind: crate::weapon::WeaponKind) -> Option<&Gun> {
        use crate::weapon::WeaponKind::*;
        match kind {
            Rifle => Some(&self.rifle),
            Shotgun => Some(&self.shotgun),
            Pistol => Some(&self.pistol),
            Smg => Some(&self.smg),
            Dmr => Some(&self.dmr),
            Revolver => Some(&self.revolver),
            RocketLauncher | Grenade | Harpoon | Fist | Knife => None,
        }
    }
}

fn reload(keys: Res<ButtonInput<KeyCode>>, mut tuning: ResMut<Tuning>) {
    if keys.just_pressed(KeyCode::F5) {
        *tuning = load();
        info!("Reloaded {PATH}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn terrain_table_defaults() {
        let t = TerrainTuning::default();
        assert_eq!((t.cell, t.split, t.bubble, t.site_range, t.origin_step, t.workers), (0.5, 2.5, 400.0, 1500.0, 2000.0, 4));
        assert_eq!(t.merge(), 3.0);
    }
}
