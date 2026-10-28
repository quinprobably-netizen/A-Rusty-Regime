//! Dev aid: `RUST_REGIME_NEAR=1` prints a `NEAR` line the first time a boxy mesh looms over the
//! camera (more than a degree across, within 50 km: name, parents, size, distance, colour, whether
//! it is visible), and a `STARS` line when the star shell drifts off the camera, so a stray cube
//! seen in the game can be named: run with it on and send the `NEAR` and `STARS` lines.

use bevy::camera::primitives::Aabb;
use bevy::prelude::*;
use std::collections::HashSet;

use crate::camera::PlayerCamera;
use crate::solar::Starfield;

pub struct NearPlugin;

impl Plugin for NearPlugin {
    fn build(&self, app: &mut App) {
        if std::env::var_os("RUST_REGIME_NEAR").is_some() {
            app.add_systems(Update, report).add_systems(PostUpdate, stars.after(TransformSystems::Propagate));
        }
    }
}

#[allow(clippy::type_complexity)]
fn report(
    mut seen: Local<HashSet<Entity>>,
    camera: Query<&GlobalTransform, With<PlayerCamera>>,
    meshes: Query<(Entity, &GlobalTransform, &Aabb, Option<&Name>, &InheritedVisibility, Option<&MeshMaterial3d<StandardMaterial>>)>,
    names: Query<&Name>,
    parents: Query<&ChildOf>,
    materials: Res<Assets<StandardMaterial>>,
) {
    let Ok(camera) = camera.single() else { return };
    for (entity, at, aabb, name, visible, material) in &meshes {
        if seen.contains(&entity) {
            continue;
        }
        let (scale, _, translation) = at.to_scale_rotation_translation();
        let size = Vec3::from(aabb.half_extents) * scale * 2.0;
        let distance = at.transform_point(Vec3::from(aabb.center)).distance(camera.translation());
        // Boxy (ground patches are flat), big on screen, and not the star shell around the camera.
        let boxy = size.min_element() > 0.5 * size.max_element();
        if !boxy || !visible.get() || size.max_element() < 2.0 || size.max_element() >= 1.0e5 || distance >= 5.0e4 || size.max_element() < 0.026 * distance {
            continue;
        }
        // Ground chunks are boxy at this scale and there are hundreds: Q's stray cube is not one.
        if name.is_some_and(|n| n.as_str() == "Chunk") {
            continue;
        }
        seen.insert(entity);
        let mut chain = Vec::new();
        let mut up = entity;
        while let Ok(parent) = parents.get(up) {
            up = parent.parent();
            chain.push(names.get(up).map_or("?".to_string(), |n| n.to_string()));
        }
        let look = material.and_then(|m| materials.get(&m.0)).map(|m| format!("{:?} emissive {:?} {:?}", m.base_color, m.emissive, m.alpha_mode));
        println!("NEAR {:?} under {chain:?} size {size} {distance:.0} m away at {translation} visible {} {look:?}", name.map(|n| n.to_string()), visible.get());
    }
}

/// The star shell is meant to sit on the camera; a few metres of lag is fine, a kilometre is not.
fn stars(shell: Query<&GlobalTransform, With<Starfield>>, camera: Query<&GlobalTransform, With<PlayerCamera>>, mut frame: Local<u32>) {
    *frame += 1;
    let (Ok(shell), Ok(camera)) = (shell.single(), camera.single()) else { return };
    let off = shell.translation().distance(camera.translation());
    if off > 1000.0 && *frame > 2 {
        println!("STARS shell {off:.0} m off the camera on frame {}", *frame);
    }
}
