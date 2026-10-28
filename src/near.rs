//! Dev aid: `RUST_REGIME_NEAR=1` prints a `NEAR` line the first time a mesh bigger than 8 m comes
//! within 400 m of the camera (name, parents, size, distance, colour, whether it is visible), so a
//! stray box seen in the game can be named: run with it on and send the `NEAR` lines.

use bevy::camera::primitives::Aabb;
use bevy::prelude::*;
use std::collections::HashSet;

use crate::camera::PlayerCamera;

pub struct NearPlugin;

impl Plugin for NearPlugin {
    fn build(&self, app: &mut App) {
        if std::env::var_os("RUST_REGIME_NEAR").is_some() {
            app.add_systems(Update, report);
        }
    }
}

#[allow(clippy::type_complexity)]
fn report(
    mut seen: Local<HashSet<Entity>>,
    camera: Query<&GlobalTransform, With<PlayerCamera>>,
    meshes: Query<(Entity, &GlobalTransform, &Aabb, Option<&Name>, &InheritedVisibility, &MeshMaterial3d<StandardMaterial>)>,
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
        // The star shell is thousands of metres across: not a stray box.
        if size.max_element() <= 8.0 || size.max_element() >= 5000.0 || distance >= 400.0 {
            continue;
        }
        seen.insert(entity);
        let mut chain = Vec::new();
        let mut up = entity;
        while let Ok(parent) = parents.get(up) {
            up = parent.parent();
            chain.push(names.get(up).map_or("?".to_string(), |n| n.to_string()));
        }
        let look = materials.get(&material.0).map(|m| format!("{:?} emissive {:?} {:?}", m.base_color, m.emissive, m.alpha_mode));
        println!("NEAR {:?} under {chain:?} size {size} {distance:.0} m away at {translation} visible {} {look:?}", name.map(|n| n.to_string()), visible.get());
    }
}
