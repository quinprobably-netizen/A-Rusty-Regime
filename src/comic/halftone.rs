//! Halftone fill: a dot grid on a flat colour, drawn by `assets/shaders/halftone.wgsl`. Spawn it as
//! a panel's first child so the panel's ink border and shadow sit around it.

use bevy::prelude::*;
use bevy::render::render_resource::AsBindGroup;
use bevy::shader::ShaderRef;
use bevy::ui_render::prelude::{MaterialNode, UiMaterial};

#[derive(AsBindGroup, Asset, TypePath, Debug, Clone)]
pub struct Halftone {
    #[uniform(0)]
    pub fill: LinearRgba,
    #[uniform(0)]
    pub dot: LinearRgba,
    /// x: pitch px, y: dot radius px, z: grid angle in radians, w: > 0 for a vignette (dots only
    /// towards the edges).
    #[uniform(0)]
    pub params: Vec4,
}

impl UiMaterial for Halftone {
    fn fragment_shader() -> ShaderRef {
        "shaders/halftone.wgsl".into()
    }
}

/// Pitch held to 4..=64 px and the dot radius to 0.5..=pitch/2, so dots never merge into a solid
/// fill or vanish.
pub fn halftone_params(pitch: f32, radius: f32) -> Vec4 {
    let pitch = pitch.clamp(4.0, 64.0);
    Vec4::new(pitch, radius.clamp(0.5, pitch / 2.0), 0.0, 0.0)
}

/// A node filling its parent with `dot` circles every `pitch` px on `fill`.
pub fn halftone_layer(materials: &mut Assets<Halftone>, fill: Color, dot: Color, pitch: f32, radius: f32) -> impl Bundle {
    (
        Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() },
        MaterialNode(materials.add(Halftone { fill: fill.into(), dot: dot.into(), params: halftone_params(pitch, radius) })),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn params_are_clamped() {
        assert_eq!(halftone_params(1.0, 9.0), Vec4::new(4.0, 2.0, 0.0, 0.0));
        assert_eq!(halftone_params(12.0, 3.0), Vec4::new(12.0, 3.0, 0.0, 0.0));
        assert_eq!(halftone_params(200.0, 0.0), Vec4::new(64.0, 0.5, 0.0, 0.0));
    }
}
