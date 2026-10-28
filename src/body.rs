//! The player's own body: our character standing under the first-person camera, casting your
//! shadow. It is driven by the controller's move state (idle, walk, sprint, jump, double jump, fall,
//! crouch/slide, wall run, mantle, grapple), hides while driving, dies with the
//! player, and layers the weapon's reloads and recoil on top. In first person it renders only into
//! shadow maps (see `character`) and the arms are their own rig; in third person, and in a vehicle's
//! chase camera, it is the player you see.

use std::f32::consts::PI;

use bevy::camera::visibility::RenderLayers;
use bevy::prelude::*;

pub use crate::character::{Pose, SHADOW_ONLY_LAYER};
use crate::character::{self, CharacterAssets, FirstPerson, Rig, RigPose};
use crate::controller::{MoveState, Player};
use crate::input::ViewAngles;
use crate::tuning::Tuning;
use crate::vehicle::Driving;

/// How long the double-jump tuck shows, seconds.
const DOUBLE_JUMP_TIME: f32 = 0.45;

/// How far behind the eyes the body stands, so the camera sits in the head.
const BACK: f32 = 0.12;

/// Which clip fits the current movement. `wall_side` is the wall's side while wall running
/// (+1 left, -1 right), `hooked` whether the grapple is pulling and `double_jump` whether an air
/// jump just went off.
#[allow(clippy::too_many_arguments)]
pub fn pose_for(state: MoveState, crouched: bool, speed: f32, vertical: f32, max_speed: f32, wall_side: f32, hooked: bool, double_jump: bool) -> Pose {
    match state {
        _ if hooked && state == MoveState::Air => Pose::Grapple,
        MoveState::Air if double_jump => Pose::DoubleJump,
        MoveState::Mantle => Pose::Mantle,
        MoveState::WallRun => {
            if wall_side >= 0.0 {
                Pose::WallRunL
            } else {
                Pose::WallRunR
            }
        }
        MoveState::Air => {
            if vertical > 0.5 {
                Pose::Jump
            } else {
                Pose::Fall
            }
        }
        MoveState::Slide => Pose::Slide,
        MoveState::Ground => {
            if crouched && speed < 0.3 {
                Pose::Crouch
            } else if crouched {
                Pose::CrouchWalk
            } else if speed < 0.3 {
                Pose::Idle
            } else if speed < max_speed * 0.45 {
                Pose::Walk
            } else if speed < max_speed * 0.85 {
                Pose::Run
            } else {
                Pose::Sprint
            }
        }
    }
}

/// Playback rate so the feet roughly keep up with the ground speed.
pub fn playback_rate(pose: Pose, speed: f32, max_speed: f32) -> f32 {
    match pose {
        // The mocap cycles were taken at about 1.6, 2.8 and 3.6 m/s; past that the stride lengthens
        // as much as the cadence quickens.
        Pose::Walk => (speed / 1.6).clamp(0.7, 1.8),
        Pose::Run => (speed / 2.8).sqrt().clamp(0.8, 1.6),
        Pose::Sprint | Pose::WallRunL | Pose::WallRunR => (speed / 3.6).sqrt().clamp(0.8, 1.6),
        Pose::CrouchWalk => (speed / (max_speed * 0.25)).clamp(0.6, 1.6),
        _ => 1.0,
    }
}

pub struct BodyPlugin;

impl Plugin for BodyPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn)
            .add_systems(Update, (animate, arm))
            .add_systems(PostUpdate, (follow.before(TransformSystems::Propagate), show));
    }
}

#[derive(Component)]
pub struct Body;

fn spawn(mut commands: Commands, assets: Option<Res<CharacterAssets>>, characters: Res<character::Characters>, class: Res<crate::abilities::Class>) {
    // No render assets in headless tests: no body.
    if assets.is_none() {
        return;
    }
    let outfit = characters.class.get(&class.0).map_or("runner", |c| c.character.as_str());
    commands.spawn((Name::new("Player body"), Body, FirstPerson, character::bundle(outfit, Transform::default())));
}

/// The body holds the weapon in hand, and puts it away to drive.
fn arm(arsenal: Option<Res<crate::weapon::Arsenal>>, driving: Query<(), (With<Player>, With<Driving>)>, mut body: Single<&mut Rig, With<Body>>) {
    let kind = arsenal.map(|a| a.kind()).filter(|_| driving.is_empty());
    if body.weapon != kind {
        body.weapon = kind;
    }
}

/// Seen in third person and from the driving camera, only a shadow in first person. Runs every frame
/// so freshly dressed meshes and a newly held gun follow too.
fn show(
    tuning: Res<Tuning>,
    menu: Option<Res<crate::menu::Menu>>,
    driving: Query<(), (With<Player>, With<Driving>)>,
    body: Single<Entity, With<Body>>,
    children: Query<&Children>,
    mut layers: Query<&mut RenderLayers>,
) {
    let playing = menu.as_deref().is_none_or(|m| m.playing);
    let seen = crate::camera::third_person(&tuning, !driving.is_empty(), menu.as_deref()) || (!driving.is_empty() && playing);
    let want = RenderLayers::layer(if seen { 0 } else { SHADOW_ONLY_LAYER });
    for e in children.iter_descendants(*body) {
        if let Ok(mut l) = layers.get_mut(e)
            && *l != want
        {
            *l = want.clone();
        }
    }
}

/// Stand at the interpolated feet position, upright in the player's frame, facing the view yaw; in a
/// vehicle, sit in its seat.
fn follow(
    fixed: Res<Time<Fixed>>,
    view: Res<ViewAngles>,
    tuning: Res<Tuning>,
    player: Single<(&Player, &Transform)>,
    mut body: Single<&mut Transform, (With<Body>, Without<Player>)>,
) {
    let (p, player_tf) = *player;
    let scale = tuning.stand_height / character::MODEL_HEIGHT;
    body.scale = Vec3::splat(scale);
    let center = p.prev_pos.lerp(player_tf.translation, fixed.overstep_fraction());
    let (forward, _) = view.flat_basis();
    body.translation = center - p.up() * p.half_height(&tuning) - forward * BACK;
    // The model faces +Z; the camera looks down -Z at yaw 0.
    body.rotation = p.frame * Quat::from_rotation_y(view.yaw + PI);
}

/// Air jumps left and the double-jump clip's time left, between frames.
#[derive(Default)]
struct Jumps {
    left: u32,
    showing: f32,
}

#[allow(clippy::too_many_arguments)]
fn animate(
    time: Res<Time>,
    tuning: Res<Tuning>,
    view: Res<ViewAngles>,
    grapple: Option<Res<crate::abilities::GrappleState>>,
    health: Option<Res<crate::health::PlayerHealth>>,
    arsenal: Option<Res<crate::weapon::Arsenal>>,
    mut fired: MessageReader<crate::weapon::WeaponFired>,
    player: Single<(&Player, Option<&Driving>)>,
    mut body: Single<&mut RigPose, With<Body>>,
    mut jumps: Local<Jumps>,
) {
    let (player, driving) = *player;
    let speed = player.horizontal_speed();
    // A wall on the left has a normal pointing to the right of the view.
    let (_, right) = view.flat_basis();
    let wall_side = player.wall_normal.dot(right);
    let hooked = grapple.is_some_and(|g| g.hooked());
    if player.state == MoveState::Air && player.air_jumps_left < jumps.left {
        jumps.showing = DOUBLE_JUMP_TIME;
    }
    jumps.left = player.air_jumps_left;
    jumps.showing = (jumps.showing - time.delta_secs()).max(0.0);
    let mut pose = pose_for(player.state, player.crouched, speed, player.vertical(), tuning.max_speed, wall_side, hooked, jumps.showing > 0.0);
    if health.as_ref().is_some_and(|h| !h.alive()) {
        pose = Pose::Death;
    }
    // Dev aid: `RUST_REGIME_SCREENSHOT_POSE=slide` holds a clip for screenshots ("reload" reloads).
    static DEV: std::sync::OnceLock<Option<String>> = std::sync::OnceLock::new();
    let dev = DEV.get_or_init(|| std::env::var("RUST_REGIME_SCREENSHOT_POSE").ok());
    if let Some(p) = dev.as_deref().and_then(|n| Pose::ALL.into_iter().find(|p| p.name() == n)) {
        pose = p;
    }
    let mut want = RigPose { pose, rate: playback_rate(pose, speed, tuning.max_speed), reload: body.reload, shots: body.shots };
    want.reload = match arsenal {
        Some(a) if a.reload > 0.0 && driving.is_none() => a.kind().reload_time(&tuning),
        _ => 0.0,
    };
    if dev.as_deref() == Some("reload") {
        want.reload = 2.0;
    }
    want.shots = want.shots.wrapping_add(fired.read().count() as u32);
    if **body != want {
        **body = want;
    }
}
