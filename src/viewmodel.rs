//! First-person weapon models hanging off the camera: one child per weapon,
//! only the current one visible. Recoil, movement bob and a lower/raise on swap.

use bevy::prelude::*;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};

use crate::camera::PlayerCamera;
use crate::controller::{MoveState, Player};
use crate::tuning::Tuning;
use crate::weapon::{Arsenal, WEAPONS, WeaponFired, WeaponKind, SWITCH_TIME};

pub struct ViewModelPlugin;

impl Plugin for ViewModelPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(PostStartup, spawn)
            .add_systems(Update, animate)
            .add_observer(apply_tint);
    }
}

#[derive(Component, Default)]
pub struct ViewModel {
    kick: f32,
    kick_vel: f32,
    bob: f32,
    /// 0 in play, 1 presented to the camera by the gunsmith.
    showcase: f32,
    spin: f32,
}

#[derive(Component)]
struct WeaponModel(usize);

/// Multiply a glTF's materials by this color once it has spawned.
#[derive(Component)]
pub struct Tint(pub Color);

const REST: Vec3 = Vec3::new(0.3, -0.27, -0.55);
/// Where the gun sits when aiming down sights: centered and raised to the eye.
const AIMED: Vec3 = Vec3::new(0.0, -0.16, -0.42);
/// Where the gun sits in the gunsmith: right of centre, turned to show its side.
const SHOWCASE: Vec3 = Vec3::new(0.32, -0.08, -0.62);

fn spawn(
    mut commands: Commands,
    server: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    camera: Single<Entity, With<PlayerCamera>>,
) {
    // Kenney's blasters point down +Z with the grip at the origin; turn them to face -Z.
    let gun_tf = |scale: Vec3, offset: Vec3| {
        Transform::from_translation(offset).with_rotation(Quat::from_rotation_y(std::f32::consts::PI)).with_scale(scale)
    };
    let blaster = server.load(GltfAssetLabel::Scene(0).from_asset("models/fps/blaster.glb"));
    let repeater = server.load(GltfAssetLabel::Scene(0).from_asset("models/fps/blaster-repeater.glb"));

    let tube_mat = materials.add(Color::srgb(0.25, 0.26, 0.28));
    let band_mat = materials.add(StandardMaterial {
        base_color: Color::srgb(1.0, 0.5, 0.1),
        emissive: LinearRgba::rgb(2.0, 0.8, 0.1),
        ..default()
    });
    let tube = meshes.add(Cylinder::new(0.045, 0.55));
    let band = meshes.add(Cylinder::new(0.052, 0.05));
    let grip = meshes.add(Cuboid::new(0.04, 0.12, 0.06));

    commands.entity(*camera).with_children(|cam| {
        cam.spawn((ViewModel::default(), Transform::from_translation(REST), Visibility::default()))
            .with_children(|vm| {
                for (i, kind) in WEAPONS.iter().enumerate() {
                    let mut model = vm.spawn((WeaponModel(i), Transform::default(), Visibility::default()));
                    match kind {
                        WeaponKind::RocketLauncher => {
                            model.with_children(|m| {
                                let along_z = Quat::from_rotation_x(std::f32::consts::FRAC_PI_2);
                                m.spawn((
                                    Mesh3d(tube.clone()),
                                    MeshMaterial3d(tube_mat.clone()),
                                    Transform::from_xyz(0.0, 0.0, -0.3).with_rotation(along_z),
                                ));
                                m.spawn((
                                    Mesh3d(band.clone()),
                                    MeshMaterial3d(band_mat.clone()),
                                    Transform::from_xyz(0.0, 0.0, -0.55).with_rotation(along_z),
                                ));
                                m.spawn((
                                    Mesh3d(grip.clone()),
                                    MeshMaterial3d(tube_mat.clone()),
                                    Transform::from_xyz(0.0, -0.09, -0.1),
                                ));
                            });
                        }
                        WeaponKind::Rifle => {
                            model.insert((WorldAssetRoot(repeater.clone()), gun_tf(Vec3::splat(0.2), Vec3::new(0.0, -0.1, 0.1))));
                        }
                        WeaponKind::Shotgun => {
                            model.insert((
                                WorldAssetRoot(blaster.clone()),
                                Tint(Color::srgb(0.75, 0.55, 0.4)),
                                gun_tf(Vec3::new(0.22, 0.22, 0.3), Vec3::new(0.0, -0.11, 0.15)),
                            ));
                        }
                        WeaponKind::Pistol => {
                            model.insert((WorldAssetRoot(blaster.clone()), gun_tf(Vec3::splat(0.16), Vec3::new(0.0, -0.08, 0.1))));
                        }
                    }
                }
            });
    });
}

fn apply_tint(
    ready: On<WorldInstanceReady>,
    tints: Query<&Tint>,
    children: Query<&Children>,
    mut handles: Query<&mut MeshMaterial3d<StandardMaterial>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let Ok(tint) = tints.get(ready.entity) else { return };
    for e in children.iter_descendants(ready.entity) {
        let Ok(mut handle) = handles.get_mut(e) else { continue };
        let Some(mut material) = materials.get(&handle.0).cloned() else { continue };
        material.base_color = tint.0;
        handle.0 = materials.add(material);
    }
}

fn animate(
    time: Res<Time>,
    tuning: Res<Tuning>,
    arsenal: Res<Arsenal>,
    mut fired: MessageReader<WeaponFired>,
    player: Single<&Player>,
    mut vm: Single<(&mut Transform, &mut ViewModel, &mut Visibility), Without<WeaponModel>>,
    mut models: Query<(&WeaponModel, &mut Visibility)>,
    aim: Option<Res<crate::weapon::Aim>>,
    menu: Option<Res<crate::menu::Menu>>,
    real: Res<Time<Real>>,
) {
    let dt = time.delta_secs();
    let (tf, vm, vis) = &mut *vm;
    // Menus pause game time, so the presentation runs on real time.
    let showcase = menu.as_ref().map_or(crate::menu::Showcase::None, |m| m.showcase());
    let want = if showcase == crate::menu::Showcase::Gun { 1.0 } else { 0.0 };
    vm.showcase += (want - vm.showcase) * (1.0 - (-8.0 * real.delta_secs()).exp());
    vm.spin += real.delta_secs();
    // Out of sight on the title and pause screens, unless the gunsmith is showing it.
    let in_game = menu.as_ref().is_none_or(|m| m.playing);
    let want_vis = if in_game || showcase == crate::menu::Showcase::Gun { Visibility::Inherited } else { Visibility::Hidden };
    if **vis != want_vis {
        **vis = want_vis;
    }

    for f in fired.read() {
        vm.kick_vel += f.kick * 3.0;
    }
    // Damped spring back to rest.
    let accel = -160.0 * vm.kick - 16.0 * vm.kick_vel;
    vm.kick_vel += accel * dt;
    vm.kick += vm.kick_vel * dt;

    // Walk bob scales with ground speed and stops in the air.
    let speed = player.horizontal_speed();
    let grounded = matches!(player.state, MoveState::Ground | MoveState::Slide);
    let amount = if grounded { (speed / tuning.max_speed).min(1.5) } else { 0.0 };
    vm.bob += dt * speed * 1.7;
    let bob = Vec3::new(vm.bob.cos(), -(vm.bob * 2.0).sin().abs() * 0.6, 0.0) * 0.012 * amount;

    let lower = Vec3::NEG_Y * 0.35 * (arsenal.switch_time / SWITCH_TIME).clamp(0.0, 1.0);

    let ads = aim.as_ref().map_or(0.0, |a| a.level);
    let rest = REST.lerp(AIMED, ads);
    let play_pos = rest + bob * (1.0 - 0.8 * ads) + lower + Vec3::Z * vm.kick * 0.06;
    let play_rot = Quat::from_rotation_x(vm.kick * 0.12);
    let show_rot = Quat::from_rotation_y(1.1 + 0.25 * (vm.spin * 0.7).sin()) * Quat::from_rotation_x(0.1);
    tf.translation = play_pos.lerp(SHOWCASE, vm.showcase);
    tf.rotation = play_rot.slerp(show_rot, vm.showcase);

    for (model, mut vis) in &mut models {
        *vis = if model.0 == arsenal.current { Visibility::Inherited } else { Visibility::Hidden };
    }
}
