//! The comic UI kit (look A, "Ink & Halftone"): theme, halftone fill, widgets and SFX pops. See
//! docs/superpowers/specs/2026-10-28-comic-redesign-design.md.
//!
//! Only the demo board uses most of it until the HUD and menus move onto the kit (piece 3).
#![allow(dead_code, unused_imports)]

mod demo;
pub mod halftone;
pub mod sfx;
pub mod theme;
pub mod widgets;

use bevy::prelude::*;
use bevy::ui_render::prelude::UiMaterialPlugin;

pub use halftone::{halftone_layer, Halftone};
pub use sfx::sfx_pop;
pub use theme::{body_text, display_text, ComicTheme};
pub use widgets::{bubble, caption, hint_strip, panel, pip_row, segment_bar, stat_bar, Tail};

pub struct ComicPlugin;

impl Plugin for ComicPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(UiMaterialPlugin::<Halftone>::default())
            .init_resource::<ComicTheme>()
            .add_systems(Startup, theme::load_fonts)
            .add_systems(Update, sfx::animate_pops);
        if std::env::var_os("RUST_REGIME_COMIC_DEMO").is_some() {
            app.add_systems(PostStartup, demo::spawn).add_systems(Update, demo::blam);
        }
    }
}
