use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::{MoveState, Player};
use crate::input::ViewAngles;
use crate::terrain::Heightmap;
use crate::tuning::Tuning;
use crate::vehicle::{Driving, Vehicle};

/// First-person camera, or over the right shoulder in third person (T). Interpolates between fixed
/// ticks so 66 Hz physics looks smooth at any frame rate, and smooths crouch height and wall-run tilt.
pub struct CameraPlugin;

impl Plugin for CameraPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn_camera)
            .add_systems(Update, toggle_view.run_if(resource_exists::<crate::input::PlayerInput>))
            .add_systems(PostUpdate, follow.before(TransformSystems::Propagate));
    }
}

/// A craft flown in all six degrees of freedom: the camera rides behind and above it, turning
/// with it, `dist` back and `height` up. `step` and `turn` are how far it moved and turned over
/// the last fixed tick, so the camera can ease between ticks without its own copy of where it was
/// (which a rebase of the origin would leave behind).
#[derive(Component, Default)]
pub struct ChaseCam {
    pub dist: f32,
    pub height: f32,
    pub step: Vec3,
    pub turn: Quat,
    /// The pilot's eyes in the craft's frame, for the cockpit view.
    pub eye: Vec3,
    /// Looking out of the cockpit rather than from behind (T / R3 while flying).
    pub cockpit: bool,
    /// How far the pilot is looking round, yaw and pitch, radians.
    pub look: Vec2,
    /// 0 to 1: how much the view widens for speed and boost.
    pub kick: f32,
}

/// The third-person camera's offset from the eyes in view space (+X right, +Z back), pulled in
/// over the shoulder while aiming.
pub fn shoulder_offset(distance: f32, shoulder: f32, ads: f32) -> Vec3 {
    let back = distance * (1.0 - 0.55 * ads);
    Vec3::new(shoulder * (1.0 - 0.2 * ads), 0.2, back)
}

/// How close the camera may get to a wall behind it.
const CAMERA_RADIUS: f32 = 0.2;

/// Whether the camera is behind the player right now: third person on, on foot, in game.
pub fn third_person(tuning: &Tuning, driving: bool, menu: Option<&crate::menu::Menu>) -> bool {
    tuning.third_person && !driving && menu.is_none_or(|m| m.playing)
}

/// T or R3 flips between first and third person, and the settings remember it. Flying, it flips
/// between the cockpit and the chase view instead; driving, the camera is always behind.
#[allow(clippy::too_many_arguments)]
fn toggle_view(
    mut input: ResMut<crate::input::PlayerInput>,
    menu: Option<Res<crate::menu::Menu>>,
    mut tuning: ResMut<Tuning>,
    settings: Option<ResMut<crate::menu::Settings>>,
    driving: Query<&Driving, With<Player>>,
    mut chased: Query<&mut ChaseCam>,
) {
    let pressed = std::mem::take(&mut input.view_pressed);
    if !pressed || menu.is_some_and(|m| !m.playing) {
        return;
    }
    if let Ok(Driving(v)) = driving.single() {
        if let Ok(mut chase) = chased.get_mut(*v) {
            chase.cockpit = !chase.cockpit;
        }
        return;
    }
    tuning.third_person = !tuning.third_person;
    if let Some(mut s) = settings {
        s.third_person = tuning.third_person;
        s.save();
    }
}

/// Carries the gun and the first-person arms: scaled across the view about the camera's axis so
/// they look drawn through `viewmodel_fov_degrees` while depth stays true (see viewmodel::widen).
#[derive(Component)]
pub struct Widen;

#[derive(Component, Default)]
pub struct PlayerCamera {
    eye_correction: f32,
    roll: f32,
    /// Distance from the eyes to the third-person camera: snaps in against walls, eases back out.
    boom: f32,
    /// The chase camera's turn, trailing the craft's so it swings a little behind every manoeuvre.
    chase: Option<Quat>,
    /// The flight view's widening, eased.
    kick: f32,
}

fn spawn_camera(mut commands: Commands, tuning: Res<Tuning>) {
    commands.spawn((
        PlayerCamera::default(),
        Camera3d::default(),
        Projection::from(PerspectiveProjection {
            fov: tuning.fov_degrees.to_radians(),
            // At ADS the rifle's stock sits a few cm from the eye; the default 0.1 m sliced it into a
            // dark ring. Bevy's reverse-Z depth keeps a small near plane precise.
            near: 0.02,
            far: 10_000.0,
            ..default()
        }),
        Transform::default(),
        children![(Widen, Transform::default(), Visibility::default())],
    ));
}

type CameraItem<'a> = (&'a mut Transform, &'a mut PlayerCamera, &'a mut Projection);
type CameraFilter = (Without<Player>, Without<Vehicle>, Without<ChaseCam>);

fn follow(
    time: Res<Time>,
    fixed: Res<Time<Fixed>>,
    view: Res<ViewAngles>,
    tuning: Res<Tuning>,
    mut player: Single<(Entity, &mut Player, &Transform, Option<&Driving>)>,
    camera: Single<CameraItem, CameraFilter>,
    aim: Option<Res<crate::weapon::Aim>>,
    scoped: Option<Res<crate::scope::Scoped>>,
    vehicles: Query<(&Transform, &Vehicle), Without<Player>>,
    chased: Query<(&Transform, &ChaseCam), Without<Player>>,
    heightmap: Option<Res<Heightmap>>,
    menu: Option<Res<crate::menu::Menu>>,
    real: Res<Time<Real>>,
    spatial: Option<SpatialQuery>,
) {
    let (player_entity, p, player_tf, driving) = &mut *player;
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
    tf.translation = body + p.up() * (p.eye_offset(&tuning) + cam.eye_correction);
    tf.rotation = p.frame * Quat::from_euler(EulerRot::YXZ, view.yaw, view.pitch, cam.roll);

    // Third person: back over the right shoulder, pulled in front of anything behind.
    let third = third_person(&tuning, driving.is_some(), menu.as_deref());
    if third {
        let ads = aim.as_ref().map_or(0.0, |a| a.level);
        let want = tf.rotation * shoulder_offset(tuning.third_person_distance, tuning.third_person_shoulder, ads);
        let (dir, max) = (want.normalize_or_zero(), want.length());
        let reach = spatial
            .as_ref()
            .zip(Dir3::new(dir).ok())
            .and_then(|(spatial, dir)| {
                let config = ShapeCastConfig { max_distance: max, ignore_origin_penetration: true, ..ShapeCastConfig::DEFAULT };
                let filter = SpatialQueryFilter::from_excluded_entities([*player_entity]);
                spatial.cast_shape(&Collider::sphere(CAMERA_RADIUS), tf.translation, Quat::IDENTITY, dir, &config, &filter)
            })
            .map_or(max, |hit| hit.distance);
        cam.boom = if reach < cam.boom { reach } else { cam.boom + (reach - cam.boom) * (1.0 - (-5.0 * dt).exp()) };
        tf.translation += dir * cam.boom;
    } else {
        cam.boom = 0.0;
    }

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

    // Flying: from the cockpit, or behind and above the craft, trailing its turns a little and
    // pulled in ahead of anything behind it. Held free look turns either view.
    let mut flying = None;
    if let Some(Driving(v)) = driving
        && let Ok((ctf, chase)) = chased.get(*v)
    {
        let behind = 1.0 - fixed.overstep_fraction();
        let rot = (chase.turn.inverse().slerp(Quat::IDENTITY, 1.0 - behind) * ctf.rotation).normalize();
        let at = ctf.translation - chase.step * behind;
        let look = Quat::from_euler(EulerRot::YXZ, chase.look.x, chase.look.y, 0.0);
        if chase.cockpit {
            cam.chase = None;
            tf.translation = at + rot * chase.eye;
            tf.rotation = rot * look;
        } else {
            // A trailing turn, snapped back if the craft jumped (a handoff between frames).
            let trail = match cam.chase {
                Some(q) if q.angle_between(rot) < 0.8 => q.slerp(rot, 1.0 - (-9.0 * dt).exp()),
                _ => rot,
            };
            cam.chase = Some(trail);
            let view = (trail * look).normalize();
            let want = view * Vec3::new(0.0, chase.height, chase.dist);
            let (dir, max) = (want.normalize_or_zero(), want.length());
            let reach = spatial
                .as_ref()
                .zip(Dir3::new(dir).ok())
                .and_then(|(spatial, dir)| {
                    let config = ShapeCastConfig { max_distance: max, ignore_origin_penetration: true, ..ShapeCastConfig::DEFAULT };
                    let filter = SpatialQueryFilter::from_excluded_entities([*player_entity, *v]);
                    spatial.cast_shape(&Collider::sphere(CAMERA_RADIUS * 2.0), at, Quat::IDENTITY, dir, &config, &filter)
                })
                .map_or(max, |hit| hit.distance);
            tf.translation = at + dir * reach;
            tf.rotation = view * Quat::from_rotation_x(-(chase.height / (chase.dist + 30.0)).atan());
        }
        cam.roll = 0.0;
        flying = Some(chase.kick);
    } else {
        cam.chase = None;
    }
    cam.kick += (flying.unwrap_or(0.0) - cam.kick) * (1.0 - (-3.0 * dt).exp());

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
        // In third person there is no scope picture to look through: the view itself zooms.
        let zoom = if !third && scoped.is_some_and(|s| s.0.is_some()) { tuning.ads_fov_scoped } else { tuning.ads_fov };
        persp.fov = if dressing { crate::dressing::FOV } else { crate::scope::main_fov(tuning.fov_degrees.to_radians(), ads, zoom) };
        // Flying fast or boosting, the view widens up to 12 degrees.
        persp.fov += cam.kick * 12f32.to_radians();
    }
}
