//! The sliding origin. World positions are body coordinates minus `Origin::offset`; once the
//! player strays more than `terrain.origin_step` from the world origin, the offset jumps to the
//! nearest `QUANTUM` multiple under them and every root transform and physics position shifts back
//! by the same amount in one fixed tick, so f32 keeps millimetre precision anywhere on the body.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::{ControllerSet, Player};
use crate::surface::{Origin, QUANTUM};
use crate::targets::TargetSet;
use crate::tuning::Tuning;
use crate::vehicle::VehicleSet;

use super::bubble;
use super::gravity::gravitate;

/// How far the origin moves when the player is at `player_world`: nothing while they are within
/// `step` of it, else their position rounded per component to a multiple of `quantum`.
pub fn rebase_delta(player_world: Vec3, step: f32, quantum: f32) -> Option<Vec3> {
    (player_world.length() > step).then(|| (player_world / quantum).round() * quantum)
}

/// Re-centres the world on the player once they pass `terrain.origin_step`: the origin offset
/// grows by the delta, and every root `Transform`, every Avian `Position` and the player's
/// carried positions shrink by it. Entities with `TransformInterpolation` (vehicles; none on the
/// moon) keep easing from their old place for a frame; their easing state is shifted in the next
/// plan, which adds `bevy_transform_interpolation` as a direct dependency for the purpose.
pub fn rebase(
    tuning: Res<Tuning>,
    mut origin: ResMut<Origin>,
    mut players: Query<(&mut Transform, &mut Player), Without<ChildOf>>,
    mut roots: Query<&mut Transform, (Without<ChildOf>, Without<Player>)>,
    mut positions: Query<&mut Position>,
) {
    let Ok((player_tf, _)) = players.single() else { return };
    let Some(delta) = rebase_delta(player_tf.translation, tuning.terrain.origin_step, QUANTUM) else { return };
    origin.offset += delta;
    for mut tf in &mut roots {
        tf.translation -= delta;
    }
    for mut position in &mut positions {
        position.0 -= delta;
    }
    for (mut tf, mut player) in &mut players {
        tf.translation -= delta;
        player.shift(delta);
    }
}

/// Runs `rebase` first in the fixed step, before anything reads or writes a position.
pub fn add_rebase(app: &mut App) {
    app.add_systems(
        FixedUpdate,
        rebase.before(ControllerSet).before(VehicleSet).before(TargetSet).before(bubble::freeze).before(bubble::hold_player).before(gravitate),
    );
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
    }
}
