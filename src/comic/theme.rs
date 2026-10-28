//! Look A ("Ink & Halftone"): the comic redesign's colours, ink weights and fonts, in one resource
//! so menus and the HUD stop carrying their own constants.

use std::path::Path;

use bevy::prelude::*;

#[derive(Resource, Clone)]
pub struct ComicTheme {
    pub ink: Color,
    pub paper: Color,
    pub red: Color,
    pub yellow: Color,
    pub blue: Color,
    pub navy: Color,
    pub orange: Color,
    pub green: Color,
    pub muted: Color,
    /// Border width of panels, in 1080p px (Bevy's `UiScale` scales it).
    pub ink_px: f32,
    /// Offset of the hard shadow under panels.
    pub shadow_px: f32,
    /// Bangers: titles, labels, big numbers.
    pub display: Handle<Font>,
    /// Barlow Condensed SemiBold: body copy.
    pub body: Handle<Font>,
    /// Barlow Condensed ExtraBold: captions, hints, small caps labels.
    pub body_bold: Handle<Font>,
}

const fn hex(rgb: u32) -> Color {
    Color::srgb_u8((rgb >> 16) as u8, (rgb >> 8) as u8, rgb as u8)
}

impl ComicTheme {
    /// Look A's tokens with Bevy's default font everywhere (what `FromWorld` starts from).
    pub fn look_a() -> Self {
        Self {
            ink: hex(0x111111),
            paper: hex(0xF6EDD6),
            red: hex(0xE23A2E),
            yellow: hex(0xFFD23F),
            blue: hex(0x2B5FAD),
            navy: hex(0x14213D),
            orange: hex(0xE07A3F),
            green: hex(0x3FA34D),
            muted: hex(0x6B5E4A),
            ink_px: 4.0,
            shadow_px: 5.0,
            display: Handle::default(),
            body: Handle::default(),
            body_bold: Handle::default(),
        }
    }
}

/// Loads `path` (relative to the assets folder at `root`) only when the file is there; otherwise
/// the default handle, Bevy's built-in font, so a missing font never leaves text blank.
pub fn font_or_default(server: &AssetServer, root: &Path, path: &str) -> Handle<Font> {
    if root.join(path).is_file() { server.load(path.to_string()) } else { Handle::default() }
}

impl FromWorld for ComicTheme {
    /// The look-A defaults plus the fonts, loaded here so any plugin can `init_resource` the theme
    /// without caring which Startup system runs first.
    fn from_world(world: &mut World) -> Self {
        let mut theme = Self::look_a();
        if let Some(server) = world.get_resource::<AssetServer>() {
            let root = bevy::asset::io::file::FileAssetReader::get_base_path().join("assets");
            theme.display = font_or_default(server, &root, "fonts/Bangers-Regular.ttf");
            theme.body = font_or_default(server, &root, "fonts/BarlowCondensed-SemiBold.ttf");
            theme.body_bold = font_or_default(server, &root, "fonts/BarlowCondensed-ExtraBold.ttf");
        }
        theme
    }
}

fn styled(s: impl Into<String>, font: &Handle<Font>, px: f32, color: Color) -> (Text, TextFont, TextColor) {
    (Text::new(s), TextFont { font: font.into(), font_size: FontSize::Px(px), ..default() }, TextColor(color))
}

pub fn display_text(s: impl Into<String>, px: f32, color: Color, theme: &ComicTheme) -> (Text, TextFont, TextColor) {
    styled(s, &theme.display, px, color)
}

pub fn body_text(s: impl Into<String>, px: f32, color: Color, bold: bool, theme: &ComicTheme) -> (Text, TextFont, TextColor) {
    styled(s, if bold { &theme.body_bold } else { &theme.body }, px, color)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn look_a_tokens() {
        let t = ComicTheme::look_a();
        assert_eq!(t.ink.to_srgba().to_hex(), "#111111");
        assert_eq!(t.paper.to_srgba().to_hex(), "#F6EDD6");
        assert_eq!(t.yellow.to_srgba().to_hex(), "#FFD23F");
        assert_eq!(t.red.to_srgba().to_hex(), "#E23A2E");
    }

    #[test]
    fn missing_font_falls_back_to_default() {
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, AssetPlugin::default()));
        app.init_asset::<Font>();
        let server = app.world().resource::<AssetServer>().clone();
        let h = font_or_default(&server, Path::new("assets"), "fonts/nope.ttf");
        assert_eq!(h, Handle::default());
    }

    #[test]
    fn theme_from_world_without_asset_server() {
        let mut world = World::new();
        world.init_resource::<ComicTheme>();
        assert_eq!(world.resource::<ComicTheme>().display, Handle::default());
    }

    #[test]
    fn shipped_fonts_are_found() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("assets");
        for f in ["fonts/Bangers-Regular.ttf", "fonts/BarlowCondensed-SemiBold.ttf", "fonts/BarlowCondensed-ExtraBold.ttf"] {
            assert!(root.join(f).is_file(), "{f}");
        }
    }
}
