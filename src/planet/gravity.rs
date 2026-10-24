//! Gravity toward the body's centre. On a round world Avian's global `Gravity` is zero and
//! each dynamic body gets its own pull, straight down at its position, through the force API.

// Nothing in the game uses the planet yet; the planet level installs this.
#![allow(dead_code)]

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::surface::{Origin, Surface};
use crate::tuning::Tuning;

/// Applies the surface's gravity at each dynamic body as a linear acceleration for this step,
/// without waking bodies that sleep.
pub fn gravitate(surface: Res<Surface>, origin: Res<Origin>, tuning: Res<Tuning>, mut bodies: Query<(&RigidBody, Forces), Without<RigidBodyDisabled>>) {
    for (body, mut forces) in &mut bodies {
        if *body != RigidBody::Dynamic {
            continue;
        }
        let g = surface.gravity(origin.body(forces.position().0), tuning.gravity);
        forces.non_waking().apply_linear_acceleration(g);
    }
}
