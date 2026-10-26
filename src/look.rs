//! The look (hyper-realism stage R1): CC0 PBR texture sets from ambientCG, the terrain splat
//! and triplanar surface materials, the sea, the physical sky with its sun, and the camera's
//! exposure, tonemapping, bloom, ambient occlusion and temporal anti-aliasing. Everything
//! here is optional: tests and the arena never load it, and `[graphics]` in tuning.toml turns
//! the expensive parts off.

use bevy::anti_alias::taa::TemporalAntiAliasing;
use bevy::camera::Exposure;
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::image::{ImageAddressMode, ImageFilterMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::light::atmosphere::ScatteringMedium;
use bevy::light::{light_consts::lux, Atmosphere, AtmosphereEnvironmentMapLight, SunDisk};
use bevy::pbr::{AtmosphereSettings, ExtendedMaterial, MaterialExtension, ScreenSpaceAmbientOcclusion};
use bevy::post_process::bloom::Bloom;
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;

use crate::camera::PlayerCamera;
use crate::tuning::Tuning;

pub struct LookPlugin;

impl Plugin for LookPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((
            MaterialPlugin::<TerrainMaterial>::default(),
            MaterialPlugin::<SurfaceMaterial>::default(),
            MaterialPlugin::<WaterMaterial>::default(),
        ))
        .add_systems(Startup, load)
        .add_systems(PostStartup, (setup_view, setup_sky))
        .add_systems(Update, mip_textures);
    }
}

pub type TerrainMaterial = ExtendedMaterial<StandardMaterial, TerrainExt>;
pub type SurfaceMaterial = ExtendedMaterial<StandardMaterial, SurfaceExt>;
pub type WaterMaterial = ExtendedMaterial<StandardMaterial, WaterExt>;

/// Four splatted layers: see `assets/shaders/terrain.wgsl`.
#[derive(Asset, TypePath, AsBindGroup, Debug, Clone)]
pub struct TerrainExt {
    #[texture(100)]
    #[sampler(101)]
    pub grass_c: Handle<Image>,
    #[texture(102)]
    #[sampler(103)]
    pub grass_n: Handle<Image>,
    #[texture(104)]
    #[sampler(105)]
    pub dirt_c: Handle<Image>,
    #[texture(106)]
    #[sampler(107)]
    pub dirt_n: Handle<Image>,
    #[texture(108)]
    #[sampler(109)]
    pub rock_c: Handle<Image>,
    #[texture(110)]
    #[sampler(111)]
    pub rock_n: Handle<Image>,
    #[texture(112)]
    #[sampler(113)]
    pub sand_c: Handle<Image>,
    #[texture(114)]
    #[sampler(115)]
    pub sand_n: Handle<Image>,
    #[uniform(116)]
    pub splat: Splat,
}

#[derive(ShaderType, Debug, Clone)]
pub struct Splat {
    /// Tiles per metre: grass, dirt, rock, sand.
    pub scale: Vec4,
    pub rough: Vec4,
}

impl MaterialExtension for TerrainExt {
    fn fragment_shader() -> ShaderRef {
        "shaders/terrain.wgsl".into()
    }
    fn deferred_fragment_shader() -> ShaderRef {
        "shaders/terrain.wgsl".into()
    }
}

/// One triplanar texture set: see `assets/shaders/surface.wgsl`.
#[derive(Asset, TypePath, AsBindGroup, Debug, Clone)]
pub struct SurfaceExt {
    #[texture(100)]
    #[sampler(101)]
    pub color: Handle<Image>,
    #[texture(102)]
    #[sampler(103)]
    pub normal: Handle<Image>,
    #[texture(104)]
    #[sampler(105)]
    pub rough: Handle<Image>,
    #[uniform(106)]
    pub params: SurfaceParams,
}

#[derive(ShaderType, Debug, Clone)]
pub struct SurfaceParams {
    pub scale: f32,
    pub rough: f32,
    pub normal_strength: f32,
    pub _pad: f32,
}

impl MaterialExtension for SurfaceExt {
    fn fragment_shader() -> ShaderRef {
        "shaders/surface.wgsl".into()
    }
    fn deferred_fragment_shader() -> ShaderRef {
        "shaders/surface.wgsl".into()
    }
}

/// The sea: see `assets/shaders/water.wgsl`.
#[derive(Asset, TypePath, AsBindGroup, Debug, Clone)]
pub struct WaterExt {
    #[uniform(100)]
    pub sea: Sea,
}

#[derive(ShaderType, Debug, Clone)]
pub struct Sea {
    pub shallow: Vec4,
    pub deep: Vec4,
    /// Wave amplitude (m), wavelength (m), speed, foam depth (m).
    pub params: Vec4,
}

impl MaterialExtension for WaterExt {
    fn fragment_shader() -> ShaderRef {
        "shaders/water.wgsl".into()
    }
}

/// The loaded material set. Absent in tests and in the arena.
#[derive(Resource, Clone)]
pub struct Textures {
    pub terrain: Handle<TerrainMaterial>,
    pub water: Handle<WaterMaterial>,
    pub concrete: Handle<SurfaceMaterial>,
    pub wood: Handle<SurfaceMaterial>,
    pub metal: Handle<SurfaceMaterial>,
    pub rock: Handle<SurfaceMaterial>,
    /// Every image still waiting for its mip chain, so `mip_textures` can give each one once it is loaded.
    images: Vec<Handle<Image>>,
    /// How many images there were to begin with.
    total: usize,
}

impl Textures {
    /// The share of the images that are loaded with their mip chains built, from 0 to 1. `mip_textures`
    /// takes an image out of `images` once it is done; a failed image never gets there, so it counts as done
    /// here and one missing file cannot hold the loading screen up for ever.
    pub fn loaded_fraction(&self, server: &AssetServer) -> f32 {
        if self.total == 0 {
            return 1.0;
        }
        let waiting = self.images.iter().filter(|h| !server.load_state(*h).is_failed()).count();
        (self.total - waiting) as f32 / self.total as f32
    }
}

/// A tiling texture; normal and roughness maps are linear.
fn tex(server: &AssetServer, images: &mut Vec<Handle<Image>>, path: &str, srgb: bool) -> Handle<Image> {
    let h: Handle<Image> = server
        .load_builder()
        .with_settings(move |s: &mut ImageLoaderSettings| {
            s.is_srgb = srgb;
            s.asset_usage = bevy::asset::RenderAssetUsages::MAIN_WORLD | bevy::asset::RenderAssetUsages::RENDER_WORLD;
            s.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
                address_mode_u: ImageAddressMode::Repeat,
                address_mode_v: ImageAddressMode::Repeat,
                mag_filter: ImageFilterMode::Linear,
                min_filter: ImageFilterMode::Linear,
                mipmap_filter: ImageFilterMode::Linear,
                anisotropy_clamp: 8,
                ..default()
            });
        })
        .load(format!("textures/{path}"));
    images.push(h.clone());
    h
}

pub fn load(
    mut commands: Commands,
    server: Res<AssetServer>,
    tuning: Res<Tuning>,
    mut terrain: ResMut<Assets<TerrainMaterial>>,
    mut surfaces: ResMut<Assets<SurfaceMaterial>>,
    mut water: ResMut<Assets<WaterMaterial>>,
) {
    let mut images = Vec::new();
    let mut set = |name: &str| {
        (
            tex(&server, &mut images, &format!("{name}/color.jpg"), true),
            tex(&server, &mut images, &format!("{name}/normal.jpg"), false),
            tex(&server, &mut images, &format!("{name}/rough.jpg"), false),
        )
    };
    let grass = set("grass");
    let dirt = set("dirt");
    let rock = set("rock");
    let sand = set("sand");
    let mut surface = |(c, n, r): (Handle<Image>, Handle<Image>, Handle<Image>), scale: f32, tint: Color| {
        surfaces.add(ExtendedMaterial {
            base: StandardMaterial { base_color: tint, perceptual_roughness: 1.0, ..default() },
            extension: SurfaceExt { color: c, normal: n, rough: r, params: SurfaceParams { scale, rough: 1.0, normal_strength: 1.0, _pad: 0.0 } },
        })
    };
    let concrete = surface(set("concrete"), 0.35, Color::WHITE);
    let wood = surface(set("wood"), 0.5, Color::WHITE);
    let metal = surface(set("metal"), 0.4, Color::WHITE);
    let rock_m = surface(rock.clone(), 0.3, Color::WHITE);
    let g = &tuning.graphics;
    let terrain = terrain.add(ExtendedMaterial {
        base: StandardMaterial { perceptual_roughness: 1.0, ..default() },
        extension: TerrainExt {
            grass_c: grass.0,
            grass_n: grass.1,
            dirt_c: dirt.0,
            dirt_n: dirt.1,
            rock_c: rock.0,
            rock_n: rock.1,
            sand_c: sand.0,
            sand_n: sand.1,
            splat: Splat { scale: Vec4::new(1.0 / g.grass_tile, 1.0 / g.dirt_tile, 1.0 / g.rock_tile, 1.0 / g.sand_tile), rough: Vec4::new(0.92, 0.95, 0.85, 0.8) },
        },
    });
    let water = water.add(ExtendedMaterial {
        base: StandardMaterial { base_color: Color::srgba(0.1, 0.3, 0.45, 0.9), perceptual_roughness: 0.08, alpha_mode: AlphaMode::Blend, ..default() },
        extension: WaterExt {
            sea: Sea {
                shallow: Vec4::new(0.12, 0.45, 0.45, 1.0),
                deep: Vec4::new(0.02, 0.09, 0.2, 1.0),
                params: Vec4::new(g.wave_height, g.wave_length, 1.0, 1.6),
            },
        },
    });
    commands.insert_resource(Textures { terrain, water, concrete, wood, metal, rock: rock_m, total: images.len(), images });
}

/// JPEGs load with one mip level, which shimmers at a distance; build a box-filtered chain for
/// each texture once, then let it go to the GPU only.
fn mip_textures(textures: Option<ResMut<Textures>>, mut images: ResMut<Assets<Image>>) {
    let Some(mut textures) = textures else { return };
    let mut done = Vec::new();
    for (i, handle) in textures.images.iter().enumerate() {
        let Some(mut image) = images.get_mut(handle) else { continue };
        if image.texture_descriptor.mip_level_count > 1 {
            done.push(i);
            continue;
        }
        let Some(data) = image.data.as_ref() else { continue };
        let (w, h) = (image.width() as usize, image.height() as usize);
        if data.len() != w * h * 4 {
            warn!("texture {:?} is not RGBA8; no mipmaps", handle.path());
            done.push(i);
            continue;
        }
        let mut chain = data.clone();
        let (mut cw, mut ch) = (w, h);
        let mut level: Vec<u8> = data.clone();
        let mut levels = 1;
        while cw > 1 && ch > 1 {
            let (nw, nh) = (cw / 2, ch / 2);
            let mut next = vec![0u8; nw * nh * 4];
            for y in 0..nh {
                for x in 0..nw {
                    for c in 0..4 {
                        let s = |dx: usize, dy: usize| level[((2 * y + dy) * cw + 2 * x + dx) * 4 + c] as u32;
                        next[(y * nw + x) * 4 + c] = ((s(0, 0) + s(1, 0) + s(0, 1) + s(1, 1) + 2) / 4) as u8;
                    }
                }
            }
            chain.extend_from_slice(&next);
            level = next;
            cw = nw;
            ch = nh;
            levels += 1;
        }
        image.data = Some(chain);
        image.texture_descriptor.mip_level_count = levels;
        image.asset_usage = bevy::asset::RenderAssetUsages::RENDER_WORLD;
        done.push(i);
    }
    for i in done.into_iter().rev() {
        textures.images.swap_remove(i);
    }
}

/// Exposure for sunlight, filmic tonemapping, bloom, ambient occlusion, temporal anti-aliasing
/// and the sky's light on the player's camera.
fn setup_view(mut commands: Commands, tuning: Res<Tuning>, camera: Single<Entity, With<PlayerCamera>>) {
    let g = &tuning.graphics;
    let mut e = commands.entity(*camera);
    e.insert((Exposure { ev100: g.exposure }, Tonemapping::TonyMcMapface, Msaa::Off));
    if g.atmosphere {
        e.insert((
            bevy::camera::Hdr,
            AtmosphereSettings { aerial_view_lut_max_distance: 6000.0, ..default() },
            AtmosphereEnvironmentMapLight::default(),
        ));
    }
    if g.bloom {
        e.insert(Bloom::NATURAL);
    }
    if g.ssao {
        e.insert(ScreenSpaceAmbientOcclusion::default());
    }
    if g.taa {
        e.insert(TemporalAntiAliasing::default());
    }
}

/// An earth atmosphere around the island, and the sun gets its disc and real brightness.
fn setup_sky(mut commands: Commands, tuning: Res<Tuning>, mut mediums: ResMut<Assets<ScatteringMedium>>, mut suns: Query<(Entity, &mut DirectionalLight)>) {
    if !tuning.graphics.atmosphere {
        return;
    }
    commands.spawn((Name::new("Atmosphere"), Atmosphere::earth(mediums.add(ScatteringMedium::earth(256, 256)))));
    for (e, mut sun) in &mut suns {
        sun.illuminance = lux::RAW_SUNLIGHT;
        commands.entity(e).insert(SunDisk::EARTH);
    }
}
