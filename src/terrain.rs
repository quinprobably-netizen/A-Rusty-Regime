//! The island: a seeded heightmap, chunked into meshes and heightfield
//! colliders. `Heightmap` is plain data so the generator, the colliders,
//! enemy placement and the tests all read the same samples.

use avian3d::prelude::*;
use bevy::prelude::*;
use fastnoise_lite::{FastNoiseLite, FractalType, NoiseType};

use crate::tuning::Island;

/// `n` by `n` samples, row-major (`z * n + x`). Sample `(x, z)` sits at world
/// `(-size/2 + x*cell, -size/2 + z*cell)`.
#[derive(Resource, Clone, Debug)]
pub struct Heightmap {
    pub size: f32,
    pub cell: f32,
    pub n: usize,
    pub heights: Vec<f32>,
}

/// Layered simplex noise times a radial island mask: land in the middle,
/// coast below water on every side.
pub fn generate(island: &Island) -> Heightmap {
    let n = (island.size / island.cell) as usize + 1;
    let mut noise = FastNoiseLite::with_seed(island.seed as i32);
    noise.set_noise_type(Some(NoiseType::OpenSimplex2));
    noise.set_fractal_type(Some(FractalType::FBm));
    noise.set_fractal_octaves(Some(6));
    noise.set_fractal_gain(Some(0.55));
    noise.set_frequency(Some(3.0 / island.size));
    let half = island.size / 2.0;
    let mut heights = Vec::with_capacity(n * n);
    for zi in 0..n {
        for xi in 0..n {
            let x = -half + xi as f32 * island.cell;
            let z = -half + zi as f32 * island.cell;
            // Squared so valleys stay low and the peaks stand out.
            let h = (0.5 + 0.5 * noise.get_noise_2d(x, z)).powf(1.6);
            let r = (x * x + z * z).sqrt() / half;
            let m = smoothstep(1.0, 0.55, r);
            heights.push(h * m * island.height - (1.0 - m) * 40.0);
        }
    }
    Heightmap { size: island.size, cell: island.cell, n, heights }
}

/// Cells per chunk side.
pub const CHUNK: usize = 32;

fn smoothstep(edge0: f32, edge1: f32, x: f32) -> f32 {
    let t = ((x - edge0) / (edge1 - edge0)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

impl Heightmap {
    /// Flattens every sample within `radius` of `center` to `height`, blending
    /// back to the original over the next `blend` meters.
    pub fn stamp_flat(&mut self, center: Vec2, radius: f32, height: f32, blend: f32) {
        for zi in 0..self.n {
            for xi in 0..self.n {
                let d = self.sample_pos(xi, zi).distance(center);
                if d >= radius + blend {
                    continue;
                }
                // Exact out to one cell past the radius so the bilinear
                // surface is flat over the whole disc.
                let t = smoothstep(radius + blend, radius, (d - self.cell).max(radius.min(d)));
                let i = zi * self.n + xi;
                self.heights[i] += (height - self.heights[i]) * t;
            }
        }
    }

    /// Chunks per side; the last one is short when `n - 1` is not a multiple of `CHUNK`.
    pub fn chunks(&self) -> usize {
        (self.n - 1).div_ceil(CHUNK)
    }

    /// Sample index range `[lo, hi]` (inclusive) covered by chunk `c` along one axis.
    pub fn chunk_range(&self, c: usize) -> (usize, usize) {
        (c * CHUNK, ((c + 1) * CHUNK).min(self.n - 1))
    }

    #[inline]
    pub fn sample(&self, xi: usize, zi: usize) -> f32 {
        self.heights[zi.min(self.n - 1) * self.n + xi.min(self.n - 1)]
    }

    /// Position of sample `(xi, zi)` in the XZ plane.
    #[inline]
    pub fn sample_pos(&self, xi: usize, zi: usize) -> Vec2 {
        let half = self.size / 2.0;
        Vec2::new(-half + xi as f32 * self.cell, -half + zi as f32 * self.cell)
    }

    /// Grid coordinates of a world point, clamped to the sampled area.
    fn grid(&self, x: f32, z: f32) -> (f32, f32) {
        let max = (self.n - 1) as f32;
        let half = self.size / 2.0;
        (((x + half) / self.cell).clamp(0.0, max), ((z + half) / self.cell).clamp(0.0, max))
    }

    /// Height at a world point on the same two triangles per cell that the
    /// mesh and the parry heightfield use (diagonal from `(x1, z0)` to
    /// `(x0, z1)`); clamps to the edge outside the island.
    pub fn height_at(&self, x: f32, z: f32) -> f32 {
        let (gx, gz) = self.grid(x, z);
        let (x0, z0) = (gx.floor() as usize, gz.floor() as usize);
        let (fx, fz) = (gx - x0 as f32, gz - z0 as f32);
        let h00 = self.sample(x0, z0);
        let h10 = self.sample(x0 + 1, z0);
        let h01 = self.sample(x0, z0 + 1);
        let h11 = self.sample(x0 + 1, z0 + 1);
        if fx + fz <= 1.0 {
            h00 + (h10 - h00) * fx + (h01 - h00) * fz
        } else {
            h11 + (h01 - h11) * (1.0 - fx) + (h10 - h11) * (1.0 - fz)
        }
    }

    /// Unit normal from central differences one cell apart.
    pub fn normal_at(&self, x: f32, z: f32) -> Vec3 {
        let d = self.cell;
        let dx = self.height_at(x + d, z) - self.height_at(x - d, z);
        let dz = self.height_at(x, z + d) - self.height_at(x, z - d);
        Vec3::new(-dx, 2.0 * d, -dz).normalize()
    }
}

/// A static heightfield collider for chunk `(cx, cz)` and the transform that
/// puts its samples on the world positions `sample_pos` gives. Parry centers
/// the field on the entity.
pub fn chunk_collider(hm: &Heightmap, cx: usize, cz: usize) -> (Collider, Transform) {
    let (x0, x1) = hm.chunk_range(cx);
    let (z0, z1) = hm.chunk_range(cz);
    // Parry's Array2 is column-major with rows along z and columns along x,
    // so the data runs x outer, z inner. (Avian's `Collider::heightfield`
    // flattens row-major and only works for square chunks.)
    use avian3d::parry::{shape::SharedShape, utils::Array2};
    let (nx, nz) = (x1 - x0 + 1, z1 - z0 + 1);
    let data: Vec<f32> = (x0..=x1).flat_map(|xi| (z0..=z1).map(move |zi| hm.sample(xi, zi))).collect();
    let scale = Vec3::new((nx - 1) as f32 * hm.cell, 1.0, (nz - 1) as f32 * hm.cell);
    let shape = SharedShape::heightfield(Array2::new(nz, nx, data), scale.into());
    let center = (hm.sample_pos(x0, z0) + hm.sample_pos(x1, z1)) / 2.0;
    (Collider::from(shape), Transform::from_xyz(center.x, 0.0, center.y))
}

/// Colliders only (no meshes), for the headless tests.
#[cfg(test)]
pub fn spawn_colliders(world: &mut World, hm: &Heightmap) {
    for cz in 0..hm.chunks() {
        for cx in 0..hm.chunks() {
            let (collider, transform) = chunk_collider(hm, cx, cz);
            world.spawn((RigidBody::Static, collider, transform));
        }
    }
}

/// Indexed chunk mesh in chunk-local coordinates (the chunk entity sits at
/// the chunk center, like its collider), smooth normals from the heightmap,
/// splat weights in the vertex colors.
pub fn chunk_mesh(hm: &Heightmap, cx: usize, cz: usize, island: &Island, roads: Option<&crate::roads::Roads>) -> Mesh {
    use bevy::asset::RenderAssetUsages;
    use bevy::mesh::{Indices, PrimitiveTopology};
    let (x0, x1) = hm.chunk_range(cx);
    let (z0, z1) = hm.chunk_range(cz);
    let center = (hm.sample_pos(x0, z0) + hm.sample_pos(x1, z1)) / 2.0;
    // Only the road segments that come near this chunk.
    let near = roads.map(|r| {
        let (lo, hi) = (hm.sample_pos(x0, z0) - Vec2::splat(12.0), hm.sample_pos(x1, z1) + Vec2::splat(12.0));
        crate::roads::Roads {
            segments: r.segments.iter().filter(|(a, b)| a.xz().max(b.xz()).cmpge(lo).all() && a.xz().min(b.xz()).cmple(hi).all()).cloned().collect(),
        }
    });
    let w = x1 - x0 + 1;
    let mut positions = Vec::with_capacity(w * (z1 - z0 + 1));
    let mut normals = Vec::with_capacity(positions.capacity());
    let mut colors = Vec::with_capacity(positions.capacity());
    for zi in z0..=z1 {
        for xi in x0..=x1 {
            let p = hm.sample_pos(xi, zi);
            let h = hm.sample(xi, zi);
            let n = hm.normal_at(p.x, p.y);
            positions.push([p.x - center.x, h, p.y - center.y]);
            normals.push(n.to_array());
            let mut w = splat_weights(p, h, n.y, island);
            // Roads are packed dirt with a soft edge.
            if let Some((d, _)) = near.as_ref().and_then(|r| r.nearest(p)) {
                let r = 1.0 - smoothstep(crate::roads::HALF_WIDTH - 0.5, crate::roads::HALF_WIDTH + 1.5, d);
                w = [w[0] * (1.0 - r), w[1] * (1.0 - r) + r, w[2] * (1.0 - r), w[3] * (1.0 - r)];
            }
            colors.push(w);
        }
    }
    let mut indices = Vec::with_capacity((x1 - x0) * (z1 - z0) * 6);
    for zi in 0..(z1 - z0) {
        for xi in 0..(x1 - x0) {
            let i = (zi * w + xi) as u32;
            let w = w as u32;
            indices.extend_from_slice(&[i, i + w, i + 1, i + 1, i + w, i + w + 1]);
        }
    }
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, colors)
        .with_inserted_indices(Indices::U32(indices))
}

/// Splat weights for the terrain shader (vertex color r, g, b, a = grass, dirt, rock, sand):
/// rock on steep faces, sand by the water, dirt in noisy patches, grass elsewhere.
pub fn splat_weights(p: Vec2, h: f32, normal_y: f32, island: &Island) -> [f32; 4] {
    let rock = smoothstep(0.86, 0.66, normal_y) + smoothstep(0.72 * island.height, 0.9 * island.height, h) * 0.6;
    let rock = rock.min(1.0);
    let rest = 1.0 - rock;
    let sand = rest * smoothstep(island.water_level + 5.0, island.water_level + 1.5, h);
    let rest = rest - sand;
    let n = value_noise(p * 0.011) * 0.65 + value_noise(p * 0.047) * 0.35;
    let dirt = rest * smoothstep(0.52, 0.7, n);
    [rest - dirt, dirt, rock, sand]
}

fn hash2(p: Vec2) -> f32 {
    let v = (p.dot(Vec2::new(127.1, 311.7))).sin() * 43758.547;
    v - v.floor()
}

/// Smooth value noise in 0..1.
pub fn value_noise(p: Vec2) -> f32 {
    let i = p.floor();
    let f = p - i;
    let u = f * f * (3.0 - 2.0 * f);
    let a = hash2(i);
    let b = hash2(i + Vec2::X);
    let c = hash2(i + Vec2::Y);
    let d = hash2(i + Vec2::ONE);
    let x1 = a + (b - a) * u.x;
    let x2 = c + (d - c) * u.x;
    x1 + (x2 - x1) * u.y
}

/// The island level: terrain chunks, water, sun and fog.
pub struct TerrainPlugin;

impl Plugin for TerrainPlugin {
    fn build(&self, app: &mut App) {
        let tuning = crate::tuning::load();
        let island = tuning.island;
        // With the physical sky the camera's exposure is ~30 times lower, and the sky itself lights the shade.
        let ambient = if tuning.graphics.atmosphere { 2000.0 } else { 450.0 };
        let start = std::time::Instant::now();
        let mut hm = generate(&island);
        let sites = crate::island::place(&mut hm, &island);
        let roads = crate::roads::carve(&mut hm, &sites, &island);
        info!("roads: {} segments", roads.segments.len());
        info!(
            "island: {}x{} samples, {} chunks, generated in {:.0} ms",
            hm.n,
            hm.n,
            hm.chunks() * hm.chunks(),
            start.elapsed().as_secs_f32() * 1000.0
        );
        for s in &sites {
            info!("site {}: x {:.0} z {:.0} y {:.1}", s.name, s.center.x, s.center.y, s.height);
        }
        let camp = sites[0].origin();
        app.insert_resource(crate::controller::WorldBounds { spawn: camp + Vec3::new(0.0, 1.0, 6.0), kill_y: island.water_level - 2.0 })
            .insert_resource(crate::island::Sites(sites))
            .insert_resource(roads)
            .insert_resource(hm)
            .insert_resource(ClearColor(SKY))
            .insert_resource(bevy::light::GlobalAmbientLight { color: Color::srgb(0.75, 0.85, 1.0), brightness: ambient, ..default() })
            .add_systems(Startup, (spawn_terrain, crate::island::spawn_sites.after(crate::targets::load_assets).after(crate::vehicle::load_assets)))
        .add_systems(PostStartup, add_fog.run_if(|t: Res<crate::tuning::Tuning>| !t.graphics.atmosphere));
    }
}

const SKY: Color = Color::srgb(0.55, 0.7, 0.85);

pub fn spawn_terrain(
    mut commands: Commands,
    hm: Res<Heightmap>,
    tuning: Res<crate::tuning::Tuning>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    textures: Option<Res<crate::look::Textures>>,
    roads: Option<Res<crate::roads::Roads>>,
) {
    let island = &tuning.island;
    // Textured splat when the look is loaded, else flat shading (tests, or a GPU that can't).
    let ground = textures.as_ref().map(|t| t.terrain.clone());
    let plain = materials.add(StandardMaterial { perceptual_roughness: 1.0, ..default() });
    let mut vertices = 0usize;
    for cz in 0..hm.chunks() {
        for cx in 0..hm.chunks() {
            let (collider, transform) = chunk_collider(&hm, cx, cz);
            let mesh = chunk_mesh(&hm, cx, cz, island, roads.as_deref());
            vertices += mesh.count_vertices();
            let mut e = commands.spawn((Name::new(format!("Terrain {cx},{cz}")), Mesh3d(meshes.add(mesh)), transform, RigidBody::Static, collider));
            match &ground {
                Some(g) => e.insert(MeshMaterial3d(g.clone())),
                None => e.insert(MeshMaterial3d(plain.clone())),
            };
        }
    }
    info!("island: {vertices} terrain vertices");

    let mut water = commands.spawn((Name::new("Water"), Mesh3d(meshes.add(Plane3d::new(Vec3::Y, Vec2::splat(island.size * 5.0)))), Transform::from_xyz(0.0, island.water_level, 0.0)));
    match &textures {
        Some(t) => water.insert(MeshMaterial3d(t.water.clone())),
        None => water.insert(MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgba(0.15, 0.35, 0.55, 0.85),
            alpha_mode: AlphaMode::Blend,
            perceptual_roughness: 0.2,
            ..default()
        }))),
    };

    commands.spawn((
        Name::new("Sun"),
        DirectionalLight { illuminance: 10_000.0, shadow_maps_enabled: true, ..default() },
        bevy::light::CascadeShadowConfigBuilder {
            num_cascades: 4,
            maximum_distance: tuning.graphics.shadow_distance,
            first_cascade_far_bound: 20.0,
            ..default()
        }
        .build(),
        // Also sees the shadow-only layer, so the player's hidden head still casts a shadow.
        bevy::camera::visibility::RenderLayers::from_layers(&[0, crate::body::SHADOW_ONLY_LAYER]),
        // Mid-afternoon sun from the south-west, low enough for long shadows.
        Transform::from_xyz(300.0, 230.0, 180.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
}

fn add_fog(mut commands: Commands, camera: Single<Entity, With<crate::camera::PlayerCamera>>) {
    commands.entity(*camera).insert(DistanceFog {
        color: SKY,
        falloff: FogFalloff::Linear { start: 800.0, end: 2500.0 },
        ..default()
    });
}
