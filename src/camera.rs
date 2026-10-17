use bevy::prelude::*;

use crate::controller::{MoveState, Player};
use crate::input::ViewAngles;
use crate::tuning::Tuning;

/// First-person camera. Interpolates between fixed ticks so 66 Hz physics
/// looks smooth at any frame rate, and smooths crouch height and wall-run tilt.
pub struct CameraPlugin;

impl Plugin for CameraPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn_camera)
            .add_systems(PostUpdate, follow.before(TransformSystems::Propagate));
    }
}

#[derive(Component, Default)]
pub struct PlayerCamera {
    eye_correction: f32,
    roll: f32,
}

fn spawn_camera(mut commands: Commands, tuning: Res<Tuning>) {
    commands.spawn((
        PlayerCamera::default(),
        Camera3d::default(),
        Projection::from(PerspectiveProjection {
            fov: tuning.fov_degrees.to_radians(),
            ..default()
        }),
        Transform::default(),
    ));
}

fn follow(
    time: Res<Time>,
    fixed: Res<Time<Fixed>>,
    view: Res<ViewAngles>,
    tuning: Res<Tuning>,
    mut player: Single<(&mut Player, &Transform)>,
    camera: Single<(&mut Transform, &mut PlayerCamera, &mut Projection), Without<Player>>,
) {
    let (p, player_tf) = &mut *player;
    let (mut tf, mut cam, mut projection) = camera.into_inner();
    let dt = time.delta_secs();

    cam.eye_correction += std::mem::take(&mut p.eye_shift);
    cam.eye_correction *= (-12.0 * dt).exp();

    let target_roll = if p.state == MoveState::WallRun {
        let (_, right) = view.flat_basis();
        -p.wall_normal.dot(right) * tuning.wallrun_tilt_degrees.to_radians()
    } else {
        0.0
    };
    cam.roll += (target_roll - cam.roll) * (1.0 - (-10.0 * dt).exp());

    let body = p.prev_pos.lerp(player_tf.translation, fixed.overstep_fraction());
    tf.translation = body + Vec3::Y * (p.eye_offset(&tuning) + cam.eye_correction);
    tf.rotation = Quat::from_euler(EulerRot::YXZ, view.yaw, view.pitch, cam.roll);

    if let Projection::Perspective(persp) = &mut *projection {
        persp.fov = tuning.fov_degrees.to_radians();
    }
}
