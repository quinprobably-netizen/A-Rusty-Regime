//! The dressing room: the wardrobe menu's own space. A lit studio far above the island holds a
//! mannequin wearing the outfit being edited, holding its character's weapon on a slow turntable.
//! While the wardrobe panel is open the camera stands in the room (see `camera`), with its own
//! exposure and ambient light so the time of day outside doesn't matter.

use bevy::camera::Exposure;
use bevy::light::GlobalAmbientLight;
use bevy::prelude::*;

use crate::abilities::Class;
use crate::camera::PlayerCamera;
use crate::character::{self, CharacterAssets, Characters, Rig};
use crate::menu::{Menu, Showcase};

/// Where the room's floor centre sits, high above anything on the island.
pub const STUDIO: Vec3 = Vec3::new(0.0, 2500.0, 0.0);
/// The camera's spot in the room: left of the mannequin so it stands beside the menu panel.
pub const EYE: Vec3 = Vec3::new(-0.8, 1.35, 4.6);
/// Where the camera looks: straight down the room, level.
pub const LOOK: Vec3 = Vec3::new(-0.8, 1.0, 0.0);
/// Vertical field of view in the room (radians): a portrait lens, not the game's wide one.
pub const FOV: f32 = 0.66;
const EV100: f32 = 9.0;
const AMBIENT: f32 = 60.0;
/// Turntable speed (radians per real second); the menu pauses game time.
const SPIN: f32 = 0.35;

pub struct DressingPlugin;

impl Plugin for DressingPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn).add_systems(Update, (show, turn, arm)).add_systems(PostUpdate, light);
    }
}

#[derive(Component)]
struct Studio;

/// The figure on the turntable; the wardrobe dresses it with the player's body.
#[derive(Component)]
pub struct Mannequin;

fn spawn(
    mut commands: Commands,
    assets: Option<Res<CharacterAssets>>,
    characters: Res<Characters>,
    class: Res<Class>,
    meshes: Option<ResMut<Assets<Mesh>>>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
) {
    // No render assets in headless tests: no room.
    let (Some(_), Some(mut meshes), Some(mut materials)) = (assets, meshes, materials) else { return };
    let outfit = characters.class.get(&class.0).map_or("runner", |c| c.character.as_str());
    let mut mat = |c: Color, rough: f32, glow: f32| {
        materials.add(StandardMaterial { base_color: c, perceptual_roughness: rough, emissive: LinearRgba::from(c) * glow, ..default() })
    };
    let wall = mat(Color::srgb(0.11, 0.115, 0.125), 0.92, 0.0);
    let floor = mat(Color::srgb(0.16, 0.165, 0.17), 0.8, 0.0);
    let plinth = mat(Color::srgb(0.26, 0.27, 0.28), 0.55, 0.0);
    let amber = mat(Color::srgb(1.0, 0.72, 0.25), 1.0, 6.0);
    let mut cube = |x: f32, y: f32, z: f32| meshes.add(Cuboid::new(x, y, z));
    let parts = [
        (cube(14.0, 0.1, 14.0), floor.clone(), Vec3::new(0.0, -0.05, 0.0)),
        (cube(14.0, 0.1, 14.0), wall.clone(), Vec3::new(0.0, 5.5, 0.0)),
        (cube(14.0, 6.0, 0.2), wall.clone(), Vec3::new(0.0, 2.75, -3.5)),
        (cube(14.0, 6.0, 0.2), wall.clone(), Vec3::new(0.0, 2.75, 7.0)),
        (cube(0.2, 6.0, 14.0), wall.clone(), Vec3::new(-5.0, 2.75, 0.0)),
        (cube(0.2, 6.0, 14.0), wall, Vec3::new(5.0, 2.75, 0.0)),
        // Two amber light strips on the back wall frame the figure, a third runs along the floor.
        (cube(0.05, 4.2, 0.03), amber.clone(), Vec3::new(-1.7, 2.4, -3.39)),
        (cube(0.05, 4.2, 0.03), amber.clone(), Vec3::new(1.7, 2.4, -3.39)),
        (cube(3.45, 0.03, 0.05), amber.clone(), Vec3::new(0.0, 0.015, -3.38)),
    ];
    commands
        .spawn((Name::new("Dressing room"), Studio, Transform::from_translation(STUDIO), Visibility::Hidden))
        .with_children(|room| {
            for (mesh, material, at) in parts {
                room.spawn((Mesh3d(mesh), MeshMaterial3d(material), Transform::from_translation(at)));
            }
            room.spawn((Mesh3d(meshes.add(Cylinder::new(0.85, 0.06))), MeshMaterial3d(plinth), Transform::from_xyz(0.0, 0.03, 0.0)));
            room.spawn((Mesh3d(meshes.add(Torus::new(0.85, 0.87))), MeshMaterial3d(amber), Transform::from_xyz(0.0, 0.062, 0.0)));
            // Key from the front left, fill from the right, rim from behind and above.
            let spot = |intensity: f32, from: Vec3, at: Vec3, shadows: bool| {
                (
                    SpotLight { intensity, range: 14.0, outer_angle: 0.6, inner_angle: 0.3, shadow_maps_enabled: shadows, color: Color::srgb(1.0, 0.96, 0.9), ..default() },
                    Transform::from_translation(from).looking_at(at, Vec3::Y),
                )
            };
            room.spawn(spot(4.0e5, Vec3::new(-2.4, 3.6, 2.8), Vec3::new(0.0, 1.1, 0.0), true));
            room.spawn(spot(1.2e5, Vec3::new(2.8, 2.2, 2.4), Vec3::new(0.0, 1.0, 0.0), false));
            room.spawn(spot(3.0e5, Vec3::new(0.6, 4.2, -2.6), Vec3::new(0.0, 1.3, 0.0), false));
            room.spawn((
                Name::new("Mannequin"),
                Mannequin,
                character::bundle(outfit, Transform::from_xyz(0.0, 0.06, 0.0).with_rotation(Quat::from_rotation_y(-0.35))),
            ));
        });
}

/// The room exists only while the wardrobe is open.
fn show(menu: Option<Res<Menu>>, mut room: Query<&mut Visibility, With<Studio>>) {
    let open = menu.is_some_and(|m| m.showcase() == Showcase::Body);
    let want = if open { Visibility::Inherited } else { Visibility::Hidden };
    for mut vis in &mut room {
        if *vis != want {
            *vis = want;
        }
    }
}

/// Turn slowly so the back of the outfit shows too.
fn turn(menu: Option<Res<Menu>>, real: Res<Time<Real>>, mut figure: Query<&mut Transform, With<Mannequin>>) {
    if !menu.is_some_and(|m| m.showcase() == Showcase::Body) {
        return;
    }
    for mut tf in &mut figure {
        tf.rotate_y(SPIN * real.delta_secs());
    }
}

/// Hold the worn character's own weapon.
fn arm(characters: Res<Characters>, mut figure: Query<&mut Rig, With<Mannequin>>) {
    for mut rig in &mut figure {
        let weapon = characters.outfit(&rig.outfit).and_then(|o| characters.loadout(&o.character));
        if rig.weapon != weapon {
            rig.weapon = weapon;
        }
    }
}

/// Studio exposure and ambient light while the room is shown, over the day/night cycle's.
fn light(menu: Option<Res<Menu>>, ambient: Option<ResMut<GlobalAmbientLight>>, mut exposure: Query<&mut Exposure, With<PlayerCamera>>) {
    if !menu.is_some_and(|m| m.showcase() == Showcase::Body) {
        return;
    }
    if let Some(mut ambient) = ambient {
        ambient.brightness = AMBIENT;
    }
    for mut e in &mut exposure {
        e.ev100 = EV100;
    }
}

