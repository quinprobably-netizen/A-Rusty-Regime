//! Controller aim assist, pad only (the mouse is left alone): friction slows the stick's turn while
//! the crosshair is over an enemy, and magnetism eases the view toward one that is close to it
//! while the stick is being used. They are separate, as the genre's talks recommend.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::Player;
use crate::input::{PlayerInput, ViewAngles};
use crate::targets::{Target, TargetKind, Team};
use crate::tuning::Tuning;

pub struct AimAssistPlugin;

impl Plugin for AimAssistPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(PreUpdate, assist_system.after(crate::input::gather));
    }
}

/// Targets farther than this are not assisted.
const RANGE: f32 = 120.0;
/// Half-angle (degrees) of the cone around the crosshair that assists, from the hip and aimed.
const CONE_HIP: f32 = 4.0;
const CONE_ADS: f32 = 2.0;
/// Share of the stick's turn given back inside the cone (friction).
const FRICTION: f32 = 0.45;
/// Fraction of the remaining angle closed per second (magnetism).
const PULL: f32 = 1.2;

/// Yaw and pitch (radians) that point the view along `dir`, in the player's frame.
fn angles(frame: Quat, dir: Vec3) -> Vec2 {
    let d = frame.inverse() * dir.normalize_or_zero();
    Vec2::new((-d.x).atan2(-d.z), d.y.clamp(-1.0, 1.0).asin())
}

/// The view's error toward a target: wrapped yaw and pitch difference.
fn error(view: &ViewAngles, dir: Vec3) -> Vec2 {
    let want = angles(view.frame, dir);
    let mut yaw = want.x - view.yaw;
    yaw = (yaw + std::f32::consts::PI).rem_euclid(std::f32::consts::TAU) - std::f32::consts::PI;
    Vec2::new(yaw, want.y - view.pitch)
}

/// How much of a pad turn to hand back (friction) and how far to ease toward the target this frame
/// (magnetism), for a target `err` radians off the crosshair. Both are zero outside the cone.
pub fn assist(err: Vec2, aimed: f32, dt: f32, strength: f32) -> (f32, Vec2) {
    let cone = (CONE_HIP + (CONE_ADS - CONE_HIP) * aimed).to_radians();
    let off = err.length();
    if off > cone || strength <= 0.0 {
        return (0.0, Vec2::ZERO);
    }
    let closeness = 1.0 - off / cone;
    (FRICTION * strength, err * (PULL * dt * closeness * strength).min(1.0))
}

#[allow(clippy::too_many_arguments)]
fn assist_system(
    tuning: Res<Tuning>,
    time: Res<Time>,
    input: Res<PlayerInput>,
    aim: Option<Res<crate::weapon::Aim>>,
    spatial: SpatialQuery,
    player: Single<(Entity, &Player, &Transform)>,
    targets: Query<(&Target, &Transform, Option<&Team>)>,
    mut view: ResMut<ViewAngles>,
) {
    let pad = input.pad_look;
    if pad == Vec2::ZERO || tuning.aim_assist <= 0.0 {
        return;
    }
    let (player_entity, p, player_tf) = *player;
    let eye = player_tf.translation + p.up() * p.eye_offset(&tuning);
    let aimed = aim.as_ref().map_or(0.0, |a| a.level);
    let filter = SpatialQueryFilter::from_excluded_entities([player_entity]);
    let dt = time.delta_secs();
    // The nearest enemy to the crosshair within the cone and in plain sight.
    let mut best: Option<(f32, Vec2)> = None;
    for (target, tf, team) in &targets {
        if !target.alive() || team.is_some_and(|t| *t == Team(0)) {
            continue;
        }
        let lift = if matches!(target.kind, TargetKind::Drone { .. }) { 0.0 } else { 0.3 };
        let at = tf.translation + Vec3::Y * lift;
        let to = at - eye;
        let range = to.length();
        if range > RANGE || range < 1.0 {
            continue;
        }
        let err = error(&view, to);
        let (friction, _) = assist(err, aimed, dt, 1.0);
        if friction == 0.0 || best.is_some_and(|(e, _)| e <= err.length()) {
            continue;
        }
        let seen = Dir3::new(to).ok().is_none_or(|d| spatial.cast_ray(eye, d, range - 0.5, true, &filter).is_none());
        if seen {
            best = Some((err.length(), err));
        }
    }
    let Some((_, err)) = best else { return };
    let (friction, pull) = assist(err, aimed, dt, tuning.aim_assist);
    // Hand back part of the stick's turn, then ease toward the target.
    view.yaw += pad.x * friction;
    view.pitch = (view.pitch + pad.y * friction).clamp(-1.54, 1.54);
    view.yaw += pull.x;
    view.pitch = (view.pitch + pull.y).clamp(-1.54, 1.54);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn assist_only_inside_the_cone_and_stronger_nearer_the_middle() {
        let far = Vec2::new(10f32.to_radians(), 0.0);
        assert_eq!(assist(far, 0.0, 0.016, 1.0), (0.0, Vec2::ZERO));
        let near = Vec2::new(1f32.to_radians(), 0.0);
        let edge = Vec2::new(3.5f32.to_radians(), 0.0);
        let (f1, p1) = assist(near, 0.0, 0.016, 1.0);
        let (_, p2) = assist(edge, 0.0, 0.016, 1.0);
        assert!(f1 > 0.0 && p1.x > 0.0, "friction and pull inside the cone");
        assert!(p1.x / near.x > p2.x / edge.x, "pull is stronger near the middle");
        assert_eq!(assist(near, 0.0, 0.016, 0.0), (0.0, Vec2::ZERO), "off when set to 0");
        // Aimed, the cone is tighter.
        assert_eq!(assist(edge, 1.0, 0.016, 1.0), (0.0, Vec2::ZERO));
    }

    #[test]
    fn error_points_at_the_target() {
        let view = ViewAngles { yaw: 0.0, pitch: 0.0, frame: Quat::IDENTITY };
        // Straight ahead is -Z; a target to the right and above is a negative yaw error (yaw turns left) and a positive pitch error.
        let e = error(&view, Vec3::new(1.0, 1.0, -10.0));
        assert!(e.x < 0.0 && e.y > 0.0, "{e}");
        assert!(error(&view, Vec3::new(0.0, 0.0, -5.0)).length() < 1e-5);
    }
}
