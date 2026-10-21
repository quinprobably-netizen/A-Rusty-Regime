use bevy::prelude::*;

use crate::controller::{MoveState, Player};
use crate::input::ViewAngles;
use crate::terrain::Heightmap;
use crate::tuning::Tuning;
use crate::vehicle::{Driving, Vehicle};

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
    mut player: Single<(&mut Player, &Transform, Option<&Driving>)>,
    camera: Single<(&mut Transform, &mut PlayerCamera, &mut Projection), (Without<Player>, Without<Vehicle>)>,
    aim: Option<Res<crate::weapon::Aim>>,
    scoped: Option<Res<crate::scope::Scoped>>,
    vehicles: Query<(&Transform, &Vehicle), Without<Player>>,
    heightmap: Option<Res<Heightmap>>,
    menu: Option<Res<crate::menu::Menu>>,
    real: Res<Time<Real>>,
) {
    let (p, player_tf, driving) = &mut *player;
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

    // Driving: orbit behind the vehicle, never below the ground.
    if let Some(Driving(v)) = driving
        && let Ok((vtf, vehicle)) = vehicles.get(*v)
    {
        let (dist, height) = vehicle.spec.cam;
        let look = Quat::from_euler(EulerRot::YXZ, view.yaw, view.pitch, 0.0);
        let target = vtf.translation + Vec3::Y * height * 0.4;
        let mut eye = target - look * Vec3::NEG_Z * dist + Vec3::Y * height * 0.6;
        if let Some(hm) = &heightmap {
            eye.y = eye.y.max(hm.height_at(eye.x, eye.z) + 0.7);
        }
        tf.translation = eye;
        tf.rotation = Transform::from_translation(eye).looking_at(target, Vec3::Y).rotation;
        cam.roll = 0.0;
    }

    // Wardrobe: stand in the dressing room beside the mannequin, drifting slowly.
    let dressing = menu.as_ref().is_some_and(|m| m.showcase() == crate::menu::Showcase::Body);
    if dressing {
        use crate::dressing::{EYE, LOOK, STUDIO};
        let sway = Vec3::new((real.elapsed_secs() * 0.4).sin() * 0.12, 0.0, 0.0);
        let eye = STUDIO + EYE + sway;
        tf.translation = eye;
        tf.rotation = Transform::from_translation(eye).looking_at(STUDIO + LOOK + sway, Vec3::Y).rotation;
        cam.roll = 0.0;
    }

    if let Projection::Perspective(persp) = &mut *projection {
        let ads = aim.as_ref().map_or(0.0, |a| a.level);
        let zoom = if scoped.is_some_and(|s| s.0.is_some()) { tuning.ads_fov_scoped } else { tuning.ads_fov };
        persp.fov = if dressing { crate::dressing::FOV } else { crate::scope::main_fov(tuning.fov_degrees.to_radians(), ads, zoom) };
    }
}
