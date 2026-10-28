//! The comic look (A, "Ink & Halftone"): theme, halftone fill, widgets, SFX pops, and the
//! toon-shaded, ink-outlined world. See
//! docs/superpowers/specs/2026-10-28-comic-redesign-design.md.

mod demo;
pub mod edges;
pub mod halftone;
pub mod sfx;
pub mod theme;
pub mod toon;
pub mod widgets;

use bevy::prelude::*;
use bevy::ui_render::prelude::UiMaterialPlugin;

pub use halftone::{halftone_layer, Halftone};
pub use theme::{body_text, display_text, ComicTheme};
pub use widgets::{bubble, caption, hint_strip, panel, segment_bar, stat_bar, Tail};

pub struct ComicPlugin;

impl Plugin for ComicPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((UiMaterialPlugin::<Halftone>::default(), toon::ToonPlugin, edges::EdgesPlugin))
            .init_resource::<ComicTheme>()
            .add_systems(Update, sfx::animate_pops);
        if std::env::var_os("RUST_REGIME_COMIC_DEMO").is_some() {
            app.add_systems(PostStartup, demo::spawn).add_systems(Update, demo::blam);
        }
    }
}
