//! The start-up state. Nothing is built on a background thread any more, so the game starts
//! `Ready` and the world spawns on entering it.

use bevy::prelude::*;

/// `Ready` from the first frame; systems that spawn the world run on entering it.
#[derive(States, Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum Boot {
    #[default]
    Ready,
}

pub struct BootPlugin;

impl Plugin for BootPlugin {
    fn build(&self, app: &mut App) {
        app.init_state::<Boot>();
    }
}
