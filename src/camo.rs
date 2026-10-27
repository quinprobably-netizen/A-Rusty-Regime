//! Camouflage patterns for the wardrobe: small procedural textures laid over a character's primary
//! and secondary cloth in place of its painted colour (the weave stays, it lives in the normal and
//! roughness maps). Every pattern is our own noise, so nothing here needs a licence entry.
//!
//! Characters are UV-unwrapped at a uniform texel density, so one texture across the whole atlas
//! gives blotches of the same size on every panel, with the pattern breaking at the seams the way
//! printed cloth does.

use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageSampler, ImageSamplerDescriptor};
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use fastnoise_lite::{FastNoiseLite, FractalType, NoiseType};

/// Pattern ids, `none` first. Saved outfits name them.
pub const PATTERNS: [&str; 6] = ["none", "woodland", "digital", "tiger", "hex", "splinter"];
/// Texture edge in pixels. The atlas spans roughly two metres of cloth, so 256 px is about 8 mm.
pub const SIZE: u32 = 256;

/// Whether `pattern` names a pattern that draws anything.
pub fn draws(pattern: Option<&str>) -> bool {
    matches!(pattern, Some(p) if p != "none" && PATTERNS.contains(&p))
}

/// Which of the three tones each texel wears, row-major, `SIZE * SIZE` long. Tone 0 is the base
/// (primary), 1 the blotches (secondary), 2 the dark detail. `None` for `none` or an unknown name.
pub fn tones(pattern: &str) -> Option<Vec<u8>> {
    if !draws(Some(pattern)) {
        return None;
    }
    let n = SIZE as usize;
    let mut noise = FastNoiseLite::with_seed(7);
    noise.set_noise_type(Some(NoiseType::OpenSimplex2));
    noise.set_fractal_type(Some(FractalType::FBm));
    noise.set_fractal_octaves(Some(3));
    let mut detail = FastNoiseLite::with_seed(11);
    detail.set_noise_type(Some(NoiseType::OpenSimplex2));
    // Each pattern is a scalar field; the tones split it at fixed shares (base half, blotches a
    // third, dark detail the rest) so every pattern reads the same way whatever the noise's range.
    let mut field = vec![0f32; n * n];
    for y in 0..n {
        for x in 0..n {
            let (u, v) = (x as f32 / n as f32, y as f32 / n as f32);
            field[y * n + x] = match pattern {
                // Soft blobs with finer specks at the edges.
                "woodland" => noise.get_noise_2d(u * 9.0, v * 9.0) + 0.25 * detail.get_noise_2d(u * 20.0 + 5.0, v * 20.0),
                // Blocky pixels: noise sampled per 6 px cell.
                "digital" => {
                    let (cx, cy) = ((x / 6) as f32 * 6.0 / n as f32, (y / 6) as f32 * 6.0 / n as f32);
                    noise.get_noise_2d(cx * 12.0, cy * 12.0) + 0.3 * detail.get_noise_2d(cx * 40.0, cy * 40.0)
                }
                // Horizontal stripes bent by noise, thinned where a second field dips.
                "tiger" => {
                    let warp = 0.12 * noise.get_noise_2d(u * 6.0, v * 6.0);
                    let band = ((v + warp) * 28.0 + u * 2.0).sin();
                    band + 0.3 * detail.get_noise_2d(u * 14.0, v * 3.0)
                }
                // Hexagon cells, each wearing one tone from the noise at its centre.
                "hex" => {
                    let (cx, cy) = hex_centre(u * 14.0, v * 14.0);
                    noise.get_noise_2d(cx * 1.3, cy * 1.3)
                }
                // Angular shards: the plane sheared two ways and quantised.
                _ => {
                    let (sx, sy) = ((u + 0.6 * v) * 7.0, (v - 0.35 * u) * 7.0);
                    noise.get_noise_2d(sx.floor() * 2.1, sy.floor() * 2.1) + 0.2 * detail.get_noise_2d(u * 30.0, v * 30.0)
                }
            };
        }
    }
    let mut sorted = field.clone();
    sorted.sort_by(|a, b| a.total_cmp(b));
    let (blotch, dark) = (sorted[n * n / 2], sorted[n * n * 82 / 100]);
    Some(field.iter().map(|f| if *f >= dark { 2 } else if *f >= blotch { 1 } else { 0 }).collect())
}

/// The centre of the pointy-top hexagon (edge 1) around a point.
fn hex_centre(x: f32, y: f32) -> (f32, f32) {
    let (w, h) = (3f32.sqrt(), 1.5);
    let mut best = (0.0, 0.0);
    let mut best_d = f32::MAX;
    let row = (y / h).floor() as i32;
    for r in row - 1..=row + 1 {
        let off = if r.rem_euclid(2) == 0 { 0.0 } else { w / 2.0 };
        let col = ((x - off) / w).round();
        for c in [col - 1.0, col, col + 1.0] {
            let (cx, cy) = (c * w + off, r as f32 * h);
            let d = (cx - x).powi(2) + (cy - y).powi(2);
            if d < best_d {
                best_d = d;
                best = (cx, cy);
            }
        }
    }
    best
}

/// The texture for `pattern` in `base` (primary) and `blotch` (secondary); the detail tone is the
/// base darkened. `None` when the pattern draws nothing.
pub fn image(pattern: &str, base: Color, blotch: Color) -> Option<Image> {
    let tones = tones(pattern)?;
    let to_bytes = |c: Color| {
        let s = c.to_srgba();
        [(s.red * 255.0) as u8, (s.green * 255.0) as u8, (s.blue * 255.0) as u8, 255]
    };
    let dark = {
        let l = base.to_linear();
        Color::LinearRgba(LinearRgba::new(l.red * 0.35, l.green * 0.35, l.blue * 0.35, 1.0))
    };
    let palette = [to_bytes(base), to_bytes(blotch), to_bytes(dark)];
    let data: Vec<u8> = tones.iter().flat_map(|t| palette[*t as usize]).collect();
    let mut img = Image::new(Extent3d { width: SIZE, height: SIZE, depth_or_array_layers: 1 }, TextureDimension::D2, data, TextureFormat::Rgba8UnormSrgb, RenderAssetUsages::RENDER_WORLD);
    img.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor::linear());
    Some(img)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_pattern_uses_all_three_tones_and_none_draws_nothing() {
        assert!(tones("none").is_none() && tones("plaid").is_none());
        assert!(!draws(None) && !draws(Some("none")) && draws(Some("hex")));
        for p in &PATTERNS[1..] {
            let t = tones(p).unwrap();
            assert_eq!(t.len(), (SIZE * SIZE) as usize);
            let share = |k: u8| t.iter().filter(|x| **x == k).count() as f32 / t.len() as f32;
            for k in 0..3 {
                assert!(share(k) > 0.05, "{p}: tone {k} covers {:.0}%", share(k) * 100.0);
            }
            assert!(share(0) > 0.3, "{p}: the base shows most ({:.0}%)", share(0) * 100.0);
        }
    }

    #[test]
    fn patterns_differ_and_are_stable() {
        let a = tones("woodland").unwrap();
        assert_eq!(a, tones("woodland").unwrap());
        assert_ne!(a, tones("digital").unwrap());
        let img = image("tiger", Color::srgb_u8(255, 0, 0), Color::srgb_u8(0, 255, 0)).unwrap();
        assert_eq!(img.data.as_ref().unwrap().len(), (SIZE * SIZE * 4) as usize);
        assert!(image("none", Color::WHITE, Color::BLACK).is_none());
    }
}
