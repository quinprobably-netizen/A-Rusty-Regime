//! The sliding origin. World positions are body coordinates minus `Origin::offset`; once the
//! player strays more than `terrain.origin_step` from the world origin, the offset jumps to the
//! nearest `QUANTUM` multiple under them and every root transform and physics position shifts back
//! by the same amount in one fixed tick, so f32 keeps millimetre precision anywhere on the body.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::Player;
use crate::surface::{Origin, QUANTUM};
use crate::tuning::Tuning;

/// How far the origin moves when the player is at `player_world`: nothing while they are within
/// `step` of it, else their position rounded per component to a multiple of `quantum`. Never a
/// zero move: with a `step` under half a `quantum` the rounding can leave the origin where it is.
pub fn rebase_delta(player_world: Vec3, step: f32, quantum: f32) -> Option<Vec3> {
    (player_world.length() > step).then(|| (player_world / quantum).round() * quantum).filter(|d| *d != Vec3::ZERO)
}

/// A root entity `rebase` moves: its transform, and its physics position if it has one.
type Root<'a> = (&'a mut Transform, Option<&'a mut Position>);

/// Re-centres the world on the player once they pass `terrain.origin_step`: the origin offset
/// grows by the delta, and every root `Transform`, every Avian `Position` and the player's
/// carried positions shrink by it.
///
/// `Transform` is the source of truth for root bodies: their `Position` is set from the shifted
/// transform rather than shifted itself. Writing `Position` marks it changed, and Avian then keeps
/// it over the transform when the step syncs the two, so a shifted stale `Position` would undo a
/// transform written since the last step (a teleport, or the controller's move this tick).
/// `Rotation` is left alone: the shift turns nothing, and Avian syncs an unmarked `Rotation` from
/// the transform as usual. Non-root colliders shift their `Position`; Avian re-derives it from
/// their body in the step anyway.
///
/// Entities with `TransformInterpolation` (vehicles; none on the moon) keep easing from their old
/// place for a frame; their easing state is shifted in the next plan, which adds
/// `bevy_transform_interpolation` as a direct dependency for the purpose.
pub fn rebase(
    tuning: Res<Tuning>,
    mut origin: ResMut<Origin>,
    mut players: Query<(Root, &mut Player), Without<ChildOf>>,
    mut roots: Query<Root, (Without<ChildOf>, Without<Player>)>,
    mut nested: Query<&mut Position, With<ChildOf>>,
) {
    let Ok(((player_tf, _), _)) = players.single() else { return };
    let Some(delta) = rebase_delta(player_tf.translation, tuning.terrain.origin_step, QUANTUM) else { return };
    origin.offset += delta;
    let shift = |(mut tf, position): (Mut<Transform>, Option<Mut<Position>>)| {
        tf.translation -= delta;
        if let Some(mut position) = position {
            position.0 = tf.translation;
        }
    };
    roots.iter_mut().for_each(shift);
    for (root, mut player) in &mut players {
        shift(root);
        player.shift(delta);
    }
    for mut position in &mut nested {
        position.0 -= delta;
    }
}

/// Runs `rebase` at the end of each fixed step, after every gameplay system and right before the
/// physics step, so every system in a fixed tick (`ControllerSet`, `VehicleSet`, `TargetSet`,
/// `freeze`, `hold_player`, `gravitate`, the grapple) sees one consistent world, and the next tick
/// starts re-centred.
///
/// Spatial queries cull with Avian's `ColliderTrees`, which keep their own copies of the collider
/// AABBs and refresh them only inside the physics step (`update_moved_collider_aabbs`, in
/// `ColliderTreeSystems::UpdateAabbs`, re-reads every collider whose `Position` changed since the
/// last step). Run first in `FixedUpdate`, the shift left the trees on the old coordinates for
/// the rest of the tick. Here the step refreshes them before anything queries again. It also
/// means the controller's move this tick is already in the transform when `Position` is set
/// from it; run earlier, the marked `Position` made Avian drop that move (11 cm lost per rebase).
pub fn add_rebase(app: &mut App) {
    app.add_systems(FixedPostUpdate, rebase.before(PhysicsSystems::First));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rebase_delta_quantizes_and_triggers_past_the_step() {
        assert_eq!(rebase_delta(Vec3::new(1500.0, 0.0, 1000.0), 2000.0, 36.0), None);
        let d = rebase_delta(Vec3::new(2100.0, -50.0, 10.0), 2000.0, 36.0).unwrap();
        for c in d.to_array() { assert_eq!(c.rem_euclid(36.0), 0.0); }
        assert!(d.distance(Vec3::new(2100.0, -50.0, 10.0)) < 36.0);
        // Past a tiny step but nearest the current origin: nothing to move.
        assert_eq!(rebase_delta(Vec3::new(10.0, -5.0, 17.0), 1.0, 36.0), None);
    }
}
