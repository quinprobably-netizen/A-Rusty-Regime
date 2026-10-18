//! The player's own body: our character standing under the first-person camera, so you see your
//! legs when you look down and cast a shadow. It is driven by the controller's move state (idle,
//! walk, sprint, jump, fall, crouch/slide). The head renders only into shadow maps (see `character`).

use std::f32::consts::PI;

use bevy::prelude::*;

pub use crate::character::{Pose, SHADOW_ONLY_LAYER};
use crate::character::{self, CharacterAssets, FirstPerson, RigPose};
use crate::controller::{MoveState, Player};
use crate::input::ViewAngles;
use crate::tuning::Tuning;

/// How far behind the eyes the body stands, so the camera sits in the head.
const BACK: f32 = 0.12;

/// Which clip fits the current movement. `wall_side` is the wall's side while wall running
/// (+1 left, -1 right) and `hooked` whether the grapple is pulling.
pub fn pose_for(state: MoveState, crouched: bool, speed: f32, vertical: f32, max_speed: f32, wall_side: f32, hooked: bool) -> Pose {
    match state {
        _ if hooked && state == MoveState::Air => Pose::Grapple,
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
            if crouched {
                Pose::Crouch
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
        Pose::Walk => (speed / (max_speed * 0.3)).clamp(0.7, 1.6),
        Pose::Run => (speed / (max_speed * 0.65)).clamp(0.7, 1.6),
        Pose::Sprint | Pose::WallRunL | Pose::WallRunR => (speed / max_speed).clamp(0.7, 1.8),
        _ => 1.0,
    }
}

pub struct BodyPlugin;

impl Plugin for BodyPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn)
            .add_systems(Update, animate)
            .add_systems(PostUpdate, follow.before(TransformSystems::Propagate));
    }
}

#[derive(Component)]
pub struct Body;

fn spawn(mut commands: Commands, assets: Option<Res<CharacterAssets>>, characters: Res<character::Characters>, class: Res<crate::abilities::Class>) {
    // No render assets in headless tests: no body.
    let Some(assets) = assets else { return };
    let outfit = characters.class.get(&class.0).map_or("runner", |c| c.outfit.as_str());
    commands.spawn((Name::new("Player body"), Body, FirstPerson, character::bundle(&assets, outfit, Transform::default())));
}

/// Stand at the interpolated feet position, facing the view yaw.
fn follow(
    fixed: Res<Time<Fixed>>,
    view: Res<ViewAngles>,
    tuning: Res<Tuning>,
    player: Single<(&Player, &Transform)>,
    mut body: Single<&mut Transform, (With<Body>, Without<Player>)>,
) {
    let (p, player_tf) = *player;
    let center = p.prev_pos.lerp(player_tf.translation, fixed.overstep_fraction());
    let (forward, _) = view.flat_basis();
    body.translation = center - Vec3::Y * p.half_height(&tuning) - forward * BACK;
    // The model faces +Z; the camera looks down -Z at yaw 0.
    body.rotation = Quat::from_rotation_y(view.yaw + PI);
    body.scale = Vec3::splat(tuning.stand_height / character::MODEL_HEIGHT);
}

fn animate(
    tuning: Res<Tuning>,
    view: Res<ViewAngles>,
    grapple: Option<Res<crate::abilities::GrappleState>>,
    player: Single<&Player>,
    mut body: Single<&mut RigPose, With<Body>>,
) {
    let speed = player.horizontal_speed();
    // A wall on the left has a normal pointing to the right of the view.
    let (_, right) = view.flat_basis();
    let wall_side = player.wall_normal.dot(right);
    let hooked = grapple.is_some_and(|g| g.hooked());
    let pose = pose_for(player.state, player.crouched, speed, player.velocity.y, tuning.max_speed, wall_side, hooked);
    let want = RigPose { pose, rate: playback_rate(pose, speed, tuning.max_speed) };
    if **body != want {
        **body = want;
    }
}
