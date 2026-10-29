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
    /// Damage multipliers for hits above the shoulders and below the hips.

    pub player: PlayerTuning,
    pub grapple: GrappleTuning,
    pub graphics: Graphics,
    pub sound: Sound,
    pub terrain: TerrainTuning,
    pub ship_combat: ShipCombat,

    // Look
    pub mouse_sensitivity: f32,
    pub stick_yaw_speed: f32,
    pub stick_pitch_speed: f32,
    pub stick_deadzone: f32,
    pub stick_look_curve: f32,
    pub invert_y: bool,
    /// Flying: how hard the mouse and the right stick steer, 1 = stock.
    pub flight_mouse: f32,
    pub flight_stick: f32,
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
    /// Controller aim assist strength, 0 (off) to 1; the pad only.
    pub aim_assist: f32,
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


            terrain: TerrainTuning::default(),
            ship_combat: ShipCombat::default(),
            player: PlayerTuning::default(),
            grapple: GrappleTuning::default(),
            graphics: Graphics::default(),
            sound: Sound::default(),

            mouse_sensitivity: 0.002,
            stick_yaw_speed: 4.5,
            stick_pitch_speed: 3.0,
            stick_deadzone: 0.15,
            stick_look_curve: 2.0,
            invert_y: false,
            flight_mouse: 1.0,
            flight_stick: 1.0,
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
            aim_assist: 1.0,
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
        Self { radius: 3.5, speed: 22.0, lift: 2.5, gravity: 12.0, bounce: 0.45, fuse: 2.2, self_knockback: 8.2, cooldown: 0.6, mag: 1, reload: 1.8 }
    }
}

/// The harpoon: a fast spear that yanks you to the wall it hits, or yanks what it hits to you.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct HarpoonTuning {
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
        Self { speed: 70.0, gravity: 4.0, life: 1.2, pull_player: 17.0, pull_target: 14.0, cooldown: 0.4, mag: 1, reload: 1.6 }
    }
}

/// The power fist: a short punch that knocks things away and, off any surface, launches you back.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct FistTuning {
    pub range: f32,
    pub knockback: f32,
    /// Speed you get away from whatever you punched.
    pub launch: f32,
    pub cooldown: f32,
}

impl Default for FistTuning {
    fn default() -> Self {
        Self { range: 2.4, knockback: 16.0, launch: 11.0, cooldown: 0.7 }
    }
}

/// The knife: a quick slash, short reach, no recoil and no magazine.
#[derive(Deserialize, Clone, Debug)]
#[serde(default)]
pub struct KnifeTuning {
    pub range: f32,
    pub knockback: f32,
    pub cooldown: f32,
}

impl Default for KnifeTuning {
    fn default() -> Self {
        Self { range: 2.1, knockback: 3.0, cooldown: 0.42 }
    }
}

impl Default for Gun {
    fn default() -> Self {
        Tuning::default().rifle
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
    /// The world re-centres on the player after this far (m).
    pub origin_step: f32,
    /// Chunk builds in flight.
    pub workers: usize,
}

impl Default for TerrainTuning {
    fn default() -> Self {
        Self { cell: 0.5, split: 2.5, bubble: 400.0, origin_step: 2000.0, workers: 4 }
    }
}

impl TerrainTuning {
    /// A split chunk merges back only past this many chunk sizes, half a chunk beyond `split`.
    pub fn merge(&self) -> f32 {
        self.split + 0.5
    }
}

/// Ship guns and shields (table `[ship_combat]`); each ship's shield, hull and gun muzzles are
/// in `assets/ships.toml`.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct ShipCombat {
    /// Shots a second from each barrel; the two barrels fire in turn.
    pub gun_rate: f32,
    /// Muzzle speed (m/s), on top of the ship's own velocity.
    pub gun_speed: f32,
    /// Per shot, shield and hull alike.
    pub gun_damage: f32,
    /// How far a shot flies before it is gone (m).
    pub gun_range: f32,
    /// How far ahead of the nose the barrels' shots cross (m).
    pub converge: f32,
    /// Gun heat: added per shot (1 overheats), lost a second, and where an overheated gun fires again.
    pub heat_per_shot: f32,
    pub cool: f32,
    pub resume: f32,
    /// A shot's drag in sea-level air (1/s), thinning with the air; none in vacuum.
    pub air_drag: f32,
    /// Seconds with no hit before a shield comes back, and how fast it comes back (points a second).
    pub shield_delay: f32,
    pub shield_regen: f32,
    /// Enemy ships (`solar::enemy`): at most `enemy_cap` alive, raiders coming in between
    /// `spawn_near` and `spawn_far` (m) from you and gone past `despawn`.
    pub enemy_cap: usize,
    pub spawn_near: f32,
    pub spawn_far: f32,
    pub despawn: f32,
    /// Raiders: packs of `raid_pack` (fewest, most) of the `raider` ship, `raid_delay` seconds
    /// apart, the clock running twice as fast after `raid_hurry` seconds without a fight; none in
    /// the first `raid_grace` seconds after boarding or within `raid_clear` metres of a base.
    pub raider: String,
    pub raid_pack: [usize; 2],
    pub raid_delay: f32,
    pub raid_hurry: f32,
    pub raid_grace: f32,
    pub raid_clear: f32,
    /// Patrols: `patrols` per base while you are within `patrol_range` (m), circling
    /// `patrol_radius` out at `patrol_altitude`; they take you on inside `patrol_engage` of the
    /// base and let you go past `patrol_give_up`, and one shot down is back after
    /// `patrol_respawn` seconds of game time.
    pub patrols: usize,
    pub patrol_range: f32,
    pub patrol_radius: f32,
    pub patrol_altitude: f32,
    pub patrol_engage: f32,
    pub patrol_give_up: f32,
    pub patrol_respawn: f32,
    /// Enemy pilots (`solar::ai`) keep `ai_floor` metres over the ground, looking `ai_lookahead`
    /// seconds ahead along their sink rate.
    pub ai_floor: f32,
    pub ai_lookahead: f32,
    /// Homing missiles (`solar::missile`): `missiles` carried, one more every `missile_reload`
    /// seconds. A ship of another side held within `lock_cone` degrees of the nose and inside
    /// `lock_range` (m) for `lock_time` seconds is locked.
    pub missiles: u32,
    pub missile_reload: f32,
    pub lock_cone: f32,
    pub lock_time: f32,
    pub lock_range: f32,
    /// A missile leaves at the launcher's speed plus `missile_kick` and gains `missile_accel`
    /// (m/s²) until it is `missile_speed` faster than the launcher was. It steers by proportional
    /// navigation with gain `missile_nav`, answering it `missile_lag` seconds behind and turning
    /// at most `missile_turn` rad/s, and loses its target once that is more than
    /// `missile_seeker` degrees off its nose.
    pub missile_speed: f32,
    pub missile_kick: f32,
    pub missile_accel: f32,
    pub missile_turn: f32,
    pub missile_nav: f32,
    pub missile_lag: f32,
    pub missile_seeker: f32,
    /// Seconds before it bursts on its own; it bursts on contact or within `missile_fuse` (m) of
    /// its target, for `missile_damage`, shield first.
    pub missile_life: f32,
    pub missile_fuse: f32,
    pub missile_damage: f32,
    /// An enemy pilot that flies with missiles (`ai = { missiles = true }`) waits this long
    /// between launches.
    pub ai_missile_gap: f32,
    /// What shooting down each enemy hull pays into the bank, by ship id; a hull not listed pays
    /// nothing (`solar::loss`).
    pub bounty: std::collections::BTreeMap<String, u32>,
    /// When your own ship is shot down: the share of the bank you lose (rounded down), seconds
    /// before you are back at the Roost, and seconds the card stays up after that.
    pub bank_loss: f32,
    pub downed: f32,
    pub loss_card: f32,
    /// Seconds the `+$120 BOUNTY` line stays over the HUD after a kill.
    pub bounty_line: f32,
    /// Faction standing (`solar::standing`), -100 to 100, with the Regime, the Scrappers and the
    /// PMC: where you start with each, by faction id (a faction not listed starts at -20, a
    /// stranger); the Deserters are your own side and stay at `standing_deserters`.
    pub standing_start: std::collections::BTreeMap<String, i32>,
    pub standing_deserters: i32,
    /// What moves it: a parcel delivered to a faction's base, a raider shot down (with each of
    /// the three), one of a faction's ships shot down (with it, and with each faction that holds
    /// a grudge against it), and a hit on one of its ships, once a ship a fight.
    pub standing_delivery: i32,
    pub standing_raider_kill: i32,
    pub standing_kill: i32,
    pub standing_rival_kill: i32,
    pub standing_hit: i32,
    /// Below where it started it creeps back by `standing_recovery` every `standing_day` seconds
    /// of game time (a Haven day), no further than where it started.
    pub standing_recovery: i32,
    pub standing_day: f32,
    /// At `standing_friendly` or above a base sells for `standing_discount` less and a parcel to
    /// it pays `standing_bonus` more; below `standing_wary` it sells for `standing_markup` more;
    /// at `standing_hunted` or below it will not serve you and that faction hunts you.
    pub standing_friendly: i32,
    pub standing_wary: i32,
    pub standing_hunted: i32,
    pub standing_discount: f32,
    pub standing_markup: f32,
    pub standing_bonus: f32,
    /// Hunters: packs of `hunt_pack` (fewest, most) of the faction's patrol hull, on their own
    /// clock at the raiders' rate.
    pub hunt_pack: [usize; 2],
    /// Who holds a grudge against whom, by faction id: shooting down one of their enemies'
    /// ships pleases them by `standing_rival_kill`.
    pub grudges: std::collections::BTreeMap<String, Vec<String>>,
    /// Seconds the `REGIME -25` line stays over the HUD after standing changes.
    pub standing_line: f32,
    /// Salvage (`solar::salvage`): the scrap each enemy hull drops where it is shot down, by ship
    /// id (a hull not listed, the Kestrel among them, drops nothing). It drifts on with the
    /// wreck's velocity, slowed by air as a shot is, for `scrap_life` seconds, and the ship you
    /// fly pulls it in from `scrap_pull` metres. The `+4 SCRAP` line stays up `scrap_line` seconds.
    pub scrap: std::collections::BTreeMap<String, u32>,
    pub scrap_life: f32,
    pub scrap_pull: f32,
    pub scrap_line: f32,
    /// Ship parts, bought with scrap at the Yard: what each level of hull plating, shield cell,
    /// gun capacitor and missile rack costs, three levels each.
    pub part_costs: [[u32; 3]; 4],
    /// What each level gives the Kestrel: hull plating `plating_hull`; a shield cell
    /// `cell_shield` and `cell_regen` faster regeneration; a gun capacitor guns that heat
    /// `capacitor_heat` slower and cool `capacitor_cool` faster; a missile rack `rack_missiles`
    /// more and `rack_reload` seconds off the reload.
    pub plating_hull: f32,
    pub cell_shield: f32,
    pub cell_regen: f32,
    pub capacitor_heat: f32,
    pub capacitor_cool: f32,
    pub rack_missiles: u32,
    pub rack_reload: f32,
    /// Modules: which hull drops which (by ship id), the chance it does, and the scrap a
    /// duplicate turns into.
    pub module_from: std::collections::BTreeMap<String, String>,
    pub module_chance: f32,
    pub module_scrap: u32,
    /// What each module gives and what it costs. Afterburner: the boost tank refills
    /// `afterburner_refill` faster, for `afterburner_shield` less shield. Targeting array: a lock
    /// in `targeting_lock` seconds, in a cone `targeting_cone` degrees tighter. Spire coil: shots
    /// `spire_speed` faster and `spire_damage` harder, guns heating `spire_heat` faster. Ram
    /// plate: a ramming hit on an enemy hurts it for `ram_damage`, for `ram_thrust` less thrust.
    pub afterburner_refill: f32,
    pub afterburner_shield: f32,
    pub targeting_lock: f32,
    pub targeting_cone: f32,
    pub spire_speed: f32,
    pub spire_damage: f32,
    pub spire_heat: f32,
    pub ram_damage: f32,
    pub ram_thrust: f32,
}

impl Default for ShipCombat {
    fn default() -> Self {
        Self {
            gun_rate: 2.0,
            gun_speed: 1200.0,
            gun_damage: 12.0,
            gun_range: 2000.0,
            converge: 400.0,
            heat_per_shot: 0.08,
            cool: 0.15,
            resume: 0.4,
            air_drag: 0.1,
            shield_delay: 5.0,
            shield_regen: 10.0,
            enemy_cap: 8,
            spawn_near: 1500.0,
            spawn_far: 3000.0,
            despawn: 6000.0,
            raider: "jackal".into(),
            raid_pack: [2, 4],
            raid_delay: 90.0,
            raid_hurry: 120.0,
            raid_grace: 60.0,
            raid_clear: 3000.0,
            patrols: 2,
            patrol_range: 8000.0,
            patrol_radius: 900.0,
            patrol_altitude: 300.0,
            patrol_engage: 2500.0,
            patrol_give_up: 4000.0,
            patrol_respawn: 600.0,
            ai_floor: 150.0,
            ai_lookahead: 4.0,
            missiles: 4,
            missile_reload: 10.0,
            lock_cone: 6.0,
            lock_time: 1.2,
            lock_range: 3000.0,
            missile_speed: 600.0,
            missile_kick: 40.0,
            missile_accel: 400.0,
            missile_turn: 1.4,
            missile_nav: 4.0,
            missile_lag: 0.4,
            missile_seeker: 60.0,
            missile_life: 8.0,
            missile_fuse: 8.0,
            missile_damage: 80.0,
            ai_missile_gap: 8.0,
            bounty: [("jackal", 60), ("sentry", 120), ("censer", 150), ("welder", 200)].into_iter().map(|(id, pay)| (id.to_string(), pay)).collect(),
            bank_loss: 0.25,
            downed: 3.0,
            loss_card: 4.0,
            bounty_line: 3.0,
            standing_start: [("regime", -20), ("scrappers", 0), ("pmc", -20)].into_iter().map(|(id, v)| (id.to_string(), v)).collect(),
            standing_deserters: 50,
            standing_delivery: 10,
            standing_raider_kill: 2,
            standing_kill: -25,
            standing_rival_kill: 5,
            standing_hit: -3,
            standing_recovery: 1,
            standing_day: 2880.0,
            standing_friendly: 40,
            standing_wary: -40,
            standing_hunted: -60,
            standing_discount: 0.15,
            standing_markup: 0.15,
            standing_bonus: 0.2,
            hunt_pack: [2, 3],
            grudges: [("regime", &["deserters", "scrappers"][..]), ("scrappers", &["regime", "pmc"][..]), ("pmc", &[][..])]
                .into_iter()
                .map(|(id, foes)| (id.to_string(), foes.iter().map(|f| f.to_string()).collect()))
                .collect(),
            standing_line: 3.0,
            scrap: [("jackal", 2), ("sentry", 4), ("censer", 5), ("welder", 8)].into_iter().map(|(id, n)| (id.to_string(), n)).collect(),
            scrap_life: 90.0,
            scrap_pull: 40.0,
            scrap_line: 3.0,
            part_costs: [[12, 24, 40], [12, 24, 40], [10, 20, 32], [15, 30, 50]],
            plating_hull: 25.0,
            cell_shield: 15.0,
            cell_regen: 0.2,
            capacitor_heat: 0.2,
            capacitor_cool: 0.2,
            rack_missiles: 1,
            rack_reload: 1.5,
            module_from: [("jackal", "afterburner"), ("sentry", "targeting"), ("censer", "spire"), ("welder", "ram")].into_iter().map(|(id, m)| (id.to_string(), m.to_string())).collect(),
            module_chance: 0.25,
            module_scrap: 10,
            afterburner_refill: 0.4,
            afterburner_shield: 0.1,
            targeting_lock: 0.8,
            targeting_cone: 4.0,
            spire_speed: 0.25,
            spire_damage: 0.15,
            spire_heat: 0.2,
            ram_damage: 30.0,
            ram_thrust: 0.1,
        }
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

/// The look (table `[graphics]`): the physical sky and post effects.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Graphics {
    pub atmosphere: bool,
    /// Comic shading: banded light, shadow dots and ink outlines (turns SSAO off, bloom down).
    pub toon: bool,
    pub ssao: bool,
    pub taa: bool,
    pub bloom: bool,
    /// Camera EV100; 15 is full sun.
    pub exposure: f32,
    pub shadow_distance: f32,
}

impl Default for Graphics {
    fn default() -> Self {
        Self {
            atmosphere: true,
            toon: true,
            ssao: true,
            taa: true,
            bloom: true,
            exposure: 15.0,
            shadow_distance: 500.0,
        }
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
        assert_eq!((t.cell, t.split, t.bubble, t.origin_step, t.workers), (0.5, 2.5, 400.0, 2000.0, 4));
        assert_eq!(t.merge(), 3.0);
    }
}
