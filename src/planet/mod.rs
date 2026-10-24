pub mod chunk;
pub mod gravity;
pub mod quadtree;

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::surface::{Origin, Surface};

/// Height of the course deck's top over the surface point it is built at.
pub const COURSE_DECK: f32 = 3.0;

/// A small parkour course (a step, a wall to run, a ledge to mantle and a roof to slide under)
/// on a flat deck floating over the ground at `at`, a body-coordinate surface point, built in
/// the surface frame there. Grey boxes when the renderer is present, colliders always.
// Only the tests build it until the planet level does.
#[allow(dead_code)]
pub fn spawn_course(world: &mut World, surface: &Surface, origin: &Origin, at: Vec3) {
    let frame = surface.frame(at);
    let deck = Vec3::Y * COURSE_DECK;
    // (size, centre) in the frame; everything but the deck stands on the deck top.
    let boxes = [
        (Vec3::new(40.0, 0.5, 50.0), Vec3::new(4.0, 2.75, -22.0)),
        (Vec3::new(3.0, 0.4, 12.0), deck + Vec3::new(8.0, 0.2, -10.5)),
        (Vec3::new(1.0, 8.0, 40.0), deck + Vec3::new(1.0, 4.0, -40.0)),
        (Vec3::new(4.0, 1.8, 4.0), deck + Vec3::new(-8.0, 0.9, -3.0)),
        (Vec3::new(6.0, 0.5, 10.0), deck + Vec3::new(16.0, 1.75, -10.0)),
    ];
    let material = world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| m.add(Color::srgb(0.5, 0.5, 0.52)));
    for (size, centre) in boxes {
        let transform = Transform::from_translation(origin.world(at + frame * centre)).with_rotation(frame);
        let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
        let mut e = world.spawn((Name::new("Course"), RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
        if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
            e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
        }
    }
}
