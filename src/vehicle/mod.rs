//! What the player is driving. The ship is the only vehicle, and it lives in `solar::ship`; this
//! module keeps the `Driving` marker on the player and the system set the ship's boarding runs in.

use bevy::prelude::*;

pub struct VehiclePlugin;

impl Plugin for VehiclePlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, hide_while_driving);
    }
}

#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct VehicleSet;

/// On the player while they drive `0`.
#[derive(Component, Debug, Clone, Copy)]
pub struct Driving(pub Entity);

/// The body hides while anyone drives. The viewmodel's visibility belongs to `viewmodel::animate`, which also
/// hides it while driving; two systems writing it would fight each other every frame.
fn hide_while_driving(driving: Query<(), With<Driving>>, mut hidden: Query<&mut Visibility, With<crate::body::Body>>) {
    let want = if driving.is_empty() { Visibility::Inherited } else { Visibility::Hidden };
    for mut vis in &mut hidden {
        if *vis != want {
            *vis = want;
        }
    }
}
