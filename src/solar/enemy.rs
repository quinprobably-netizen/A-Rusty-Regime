//! Where enemy ships exist (section 5 of
//! `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`): only near the player. A
//! raider past 6 km is gone, and a patrol whose base is gone or far behind; the next spawn
//! replaces them. The numbers are in `[ship_combat]`.
//!
//! Every enemy ship is kept awake (`KeepAwake`): the bubble would freeze a body this far from the
//! player, and they all fly, so none ever rests on ground for the bubble to wake it on.

use avian3d::prelude::*;
use bevy::prelude::*;

use super::ai::{Enemy, Role};
use super::base::Base;
use super::ship::Autopilot;
use crate::controller::Player;
use crate::planet::bubble::KeepAwake;
use crate::tuning::Tuning;

/// A base's patrols stay this much past `patrol_range` before they go, so flying along the edge
/// does not spawn and drop them over and over.
const LEAVE_MARGIN: f32 = 500.0;

pub fn build(app: &mut App) {
    app.add_systems(FixedUpdate, cull.after(super::ship::board).before(super::ai::think));
}

/// An enemy ship of spec `spec` at `at`, turned `rotation` and moving at `velocity`, flown by its
/// own pilot.
pub fn spawn_enemy(world: &mut World, spec: usize, at: Vec3, rotation: Quat, velocity: Vec3, role: Role) -> Entity {
    let ship = super::ship::spawn(world, spec, Transform::from_translation(at).with_rotation(rotation));
    // Spread evenly however many come.
    let quirk = (ship.index().index() as f32 * 0.618_034).fract();
    world.entity_mut(ship).insert((Enemy::new(role, quirk), Autopilot, KeepAwake, Position(at), Rotation(rotation), LinearVelocity(velocity)));
    ship
}

/// Raiders past `despawn`, and patrols whose base is gone (another world) or far behind, go
/// without a trace; the next spawn replaces them.
fn cull(mut commands: Commands, tuning: Res<Tuning>, players: Query<&Transform, With<Player>>, bases: Query<(&Transform, &Base)>, enemies: Query<(Entity, &Enemy, &Transform)>) {
    let t = &tuning.ship_combat;
    let Ok(player) = players.single() else { return };
    for (e, enemy, tf) in &enemies {
        let gone = match enemy.role {
            Role::Raider => tf.translation.distance(player.translation) > t.despawn,
            Role::Patrol { base, .. } => bases.iter().find(|(_, b)| b.spec == base).is_none_or(|(at, _)| at.translation.distance(player.translation) > t.patrol_range + LEAVE_MARGIN),
        };
        if gone {
            commands.entity(e).despawn();
        }
    }
}
