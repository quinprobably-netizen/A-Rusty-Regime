//! The physics bubble: only the ground within `terrain.bubble` of the player is solid, and
//! dynamic bodies are held frozen wherever there is nothing solid to land on.

use avian3d::prelude::*;
use bevy::prelude::*;

use super::quadtree::node_distance;
use super::{Chunk, Chunks, Planet};
use crate::controller::Player;
use crate::surface::Origin;
use crate::tuning::Tuning;

/// A dynamic body the bubble disabled: outside it, or over ground with no collider yet.
#[derive(Component)]
pub struct Frozen;

/// How far inside the bubble a frozen body must come before it wakes, so a body at the edge
/// does not flicker between the two.
const WAKE_MARGIN: f32 = 50.0;

/// Gives colliders to the chunks inside the bubble and takes them from those outside, keeping
/// `Chunks::solid` to exactly the chunks with a collider.
pub fn solidify(
    mut commands: Commands,
    mut chunks: ResMut<Chunks>,
    planet: Res<Planet>,
    tuning: Res<Tuning>,
    origin: Res<Origin>,
    players: Query<&Transform, With<Player>>,
    terrain: Query<(Entity, &Chunk, Has<Collider>)>,
) {
    let Ok(tf) = players.single() else { return };
    let player_body = origin.body(tf.translation);
    let radius = planet.sphere.sea_radius();
    for (entity, chunk, solid) in &terrain {
        let inside = node_distance(chunk.node, radius, player_body) <= tuning.terrain.bubble;
        if inside && !solid {
            let Some(built) = chunks.loaded.get(&chunk.node) else { continue };
            commands.entity(entity).insert(built.collider());
            chunks.solid.insert(chunk.node);
        } else if !inside && solid {
            commands.entity(entity).remove::<Collider>();
            chunks.solid.remove(&chunk.node);
        }
    }
}

/// A body `freeze` looks at: its kind, where it is, whether it is frozen and its colliders.
type BodyItem<'a> = (Entity, &'a RigidBody, &'a Transform, Has<Frozen>, Option<&'a RigidBodyColliders>);

/// Disables the dynamic bodies, the player aside, that are outside the bubble or over ground
/// with no collider, and wakes them once they are well inside it over solid ground.
pub fn freeze(
    mut commands: Commands,
    chunks: Res<Chunks>,
    tuning: Res<Tuning>,
    origin: Res<Origin>,
    players: Query<&Transform, With<Player>>,
    bodies: Query<BodyItem, Without<Player>>,
) {
    let Ok(player) = players.single() else { return };
    let bubble = tuning.terrain.bubble;
    for (entity, body, tf, frozen, colliders) in &bodies {
        if *body != RigidBody::Dynamic {
            continue;
        }
        let distance = tf.translation.distance(player.translation);
        let solid = chunks.is_solid(origin.body(tf.translation));
        if !frozen && (distance > bubble || !solid) {
            commands.entity(entity).insert((RigidBodyDisabled, Frozen));
        } else if frozen && distance < bubble - WAKE_MARGIN && solid {
            commands.entity(entity).remove::<(RigidBodyDisabled, Frozen)>();
            // Works around Avian 0.7 panicking with `islands/mod.rs:518 assertion failed:
            // contact.island.is_none()` when a woken body lands; drop on the next Avian upgrade.
            // Avian leaves a woken body's collider proxies marked disabled and keeps the contact
            // pairs found while it was, which double-links the first contact it then touches.
            // Taking the colliders out of the broad phase and back, once the body is enabled,
            // starts them afresh.
            for collider in colliders.into_iter().flat_map(|c| c.iter()) {
                commands.entity(collider).insert(ColliderDisabled).remove::<ColliderDisabled>();
            }
        }
    }
}

/// A player hovering in place, untouched by the controller, until the ground under them is solid.
#[derive(Component)]
pub struct Held;

/// Holds the player while the ground under them has no collider and lets go once it does; the
/// controller then sets them down on it.
pub fn hold_player(mut commands: Commands, chunks: Res<Chunks>, origin: Res<Origin>, mut players: Query<(Entity, &Transform, &mut Player, Has<Held>)>) {
    for (entity, tf, mut p, held) in &mut players {
        let solid = chunks.is_solid(origin.body(tf.translation));
        if !solid && !held {
            p.velocity = Vec3::ZERO;
            p.knockback_lock = 0.0;
            commands.entity(entity).insert(Held);
        } else if solid && held {
            commands.entity(entity).remove::<Held>();
        }
    }
}
