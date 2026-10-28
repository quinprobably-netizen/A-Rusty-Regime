//! Comic shading for the whole world (piece 2). Bevy's `apply_pbr_lighting` gets one line
//! changed at startup, so the exposed light of every `StandardMaterial`, glTF material and
//! extended material passes through `toon_shade`: flat bands, halftone dots in the shadows.
//! Emissive light is added after, unbanded. Turning `Toon` off puts the original source back.

use bevy::prelude::*;

/// The "Total light" line of `apply_pbr_lighting` in Bevy 0.19.1's `pbr_functions.wgsl`.
pub(crate) const ANCHOR: &str = "(view_bindings::view.exposure * (transmitted_light + direct_light + indirect_light)) + emissive_light,";
const WRAPPED: &str = "toon_shade(view_bindings::view.exposure * (transmitted_light + direct_light + indirect_light), in) + emissive_light,";
const PBR_FUNCTIONS: &str = "embedded://bevy_pbr/render/pbr_functions.wgsl";
const BEGIN: &str = "\n// comic-toon begin\n";

/// Bands by light ratio (exposed light over base colour, about 1 in full sun): shadow, mid, lit
/// and a highlight. Below the mid band, ink dots on a 45° screen grow as the light falls.
const TOON_SHADE: &str = r#"
fn toon_shade(lit: vec3<f32>, in: pbr_types::PbrInput) -> vec3<f32> {
    let w = vec3<f32>(0.2126, 0.7152, 0.0722);
    let base = max(dot(in.material.base_color.rgb, w), 0.02);
    let l = dot(lit, w);
    let r = l / base;
    let s = 0.03;
    var band = 0.22;
    band += 0.26 * smoothstep(0.12 - s, 0.12 + s, r);
    band += 0.32 * smoothstep(0.45 - s, 0.45 + s, r);
    band += 0.20 * smoothstep(0.85 - s, 0.85 + s, r);
    band += 0.25 * smoothstep(1.7 - s, 1.7 + s, r);
    var tint = in.material.base_color.rgb / base;
    if l > 1e-5 {
        tint = lit / l;
    }
    var out = tint * base * band;
    let pitch = 7.0;
    let a = 0.7853982;
    let p = mat2x2<f32>(cos(a), sin(a), -sin(a), cos(a)) * in.frag_coord.xy / pitch;
    let d = length(fract(p) - 0.5) * pitch;
    let rad = (1.0 - smoothstep(0.05, 0.45, r)) * pitch * 0.42;
    let cover = 1.0 - smoothstep(rad - 0.7, rad + 0.7, d);
    out = mix(out, out * 0.15, cover * step(0.5, rad));
    return out;
}
"#;

/// Whether the world is comic-shaded and outlined (`[graphics] toon`, the Comic shading setting).
#[derive(Resource, Clone, Copy, PartialEq, Debug)]
pub struct Toon(pub bool);

impl Default for Toon {
    fn default() -> Self {
        Self(true)
    }
}

/// The patched source, or None when the anchor is missing or the source is already patched.
pub(crate) fn patch(src: &str) -> Option<String> {
    if src.contains(BEGIN) || src.matches(ANCHOR).count() != 1 {
        return None;
    }
    Some(format!("{}{BEGIN}{TOON_SHADE}", src.replace(ANCHOR, WRAPPED)))
}

/// The original source back, or None when it isn't patched.
pub(crate) fn unpatch(src: &str) -> Option<String> {
    let at = src.find(BEGIN)?;
    Some(src[..at].replace(WRAPPED, ANCHOR))
}

/// The bloom preset under toon: a faint glow so flat colours stay flat.
pub(crate) fn bloom_for(toon: bool) -> bevy::post_process::bloom::Bloom {
    use bevy::post_process::bloom::Bloom;
    if toon { Bloom { intensity: 0.05, ..Bloom::NATURAL } } else { Bloom::NATURAL }
}

pub struct ToonPlugin;

impl Plugin for ToonPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Toon>().add_systems(Update, sync_shader);
    }
}

/// Patches or restores Bevy's lighting shader to match `Toon`, once the shader has loaded.
fn sync_shader(toon: Res<Toon>, server: Option<Res<AssetServer>>, shaders: Option<ResMut<Assets<bevy::shader::Shader>>>, mut handle: Local<Option<Handle<bevy::shader::Shader>>>, mut warned: Local<bool>) {
    let (Some(server), Some(mut shaders)) = (server, shaders) else { return };
    let handle = handle.get_or_insert_with(|| server.load(PBR_FUNCTIONS));
    let Some(bevy::shader::Source::Wgsl(src)) = shaders.get(&*handle).map(|s| &s.source) else { return };
    let patched = src.contains(BEGIN);
    if patched == toon.0 {
        return;
    }
    let next = if toon.0 { patch(src) } else { unpatch(src) };
    let Some(next) = next else {
        if !*warned {
            *warned = true;
            warn!("comic shading: Bevy's lighting shader changed, the world stays plain PBR");
        }
        return;
    };
    if let Some(mut shader) = shaders.get_mut(&*handle) {
        shader.source = bevy::shader::Source::Wgsl(next.into());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> String {
        format!("fn apply_pbr_lighting() {{\n    output_color = vec4<f32>(\n        {ANCHOR}\n        output_color.a\n    );\n}}\n")
    }

    #[test]
    fn patch_wraps_the_total_light_once() {
        let out = patch(&fixture()).expect("anchor found");
        assert!(out.contains(WRAPPED));
        assert!(!out.contains(ANCHOR));
        assert!(out.contains("fn toon_shade(lit: vec3<f32>, in: pbr_types::PbrInput) -> vec3<f32>"));
        assert_eq!(patch(&out), None, "a patched source is not patched twice");
    }

    #[test]
    fn patch_is_idempotent_and_reversible() {
        let src = fixture();
        assert_eq!(unpatch(&patch(&src).unwrap()).as_deref(), Some(src.as_str()));
        assert_eq!(unpatch(&src), None);
    }

    #[test]
    fn missing_anchor_leaves_it_alone() {
        assert_eq!(patch("fn x() {}"), None);
    }

    #[test]
    fn toon_bloom_is_low() {
        use bevy::post_process::bloom::Bloom;
        assert_eq!(bloom_for(true).intensity, 0.05);
        assert_eq!(bloom_for(false).intensity, Bloom::NATURAL.intensity);
    }

    /// The anchor must still be in the Bevy we build against, or the patch silently does nothing.
    /// Reads `bevy_pbr`'s source from the cargo registry; skips when it isn't there.
    #[test]
    fn anchor_is_in_bevys_lighting_shader() {
        let lock = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.lock")).unwrap();
        let version = lock.split("name = \"bevy_pbr\"\nversion = \"").nth(1).and_then(|r| r.split('"').next()).expect("bevy_pbr in Cargo.lock");
        let home = std::env::var("CARGO_HOME").unwrap_or_else(|_| format!("{}/.cargo", std::env::var("HOME").unwrap_or_default()));
        let Ok(registries) = std::fs::read_dir(format!("{home}/registry/src")) else { return };
        let file = format!("bevy_pbr-{version}/src/render/pbr_functions.wgsl");
        let Some(src) = registries.flatten().find_map(|r| std::fs::read_to_string(r.path().join(&file)).ok()) else { return };
        let patched = patch(&src).expect("the anchor line is in bevy_pbr's apply_pbr_lighting");
        assert_eq!(unpatch(&patched).as_deref(), Some(src.as_str()));
    }
}
