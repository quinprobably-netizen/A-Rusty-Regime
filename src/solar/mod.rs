//! The solar system level (`RUST_REGIME_LEVEL=system`): a star, Haven and its moon, and the three
//! faction worlds, all on analytic orbits, with a ship to fly between them.
//!
//! Physics runs in the body-fixed frame of the *anchor*, the body whose sphere of influence the
//! player is in (the frame decision in `docs/superpowers/specs/2026-10-24-solar-system-programme.md`).
//! Its ground streams in as chunks exactly as on the debug moon; every other body is drawn from a
//! coarse mesh placed each frame from its orbit. Crossing into another sphere of influence
//! re-expresses the player and the ship in the new body's frame, drops the old ground and streams
//! the new one, so the handoff is continuous in position and velocity.

pub mod ai;
pub mod base;
pub mod cockpit;
pub mod combat;
pub mod contacts;
pub mod enemy;
pub mod missile;
pub mod loss;
pub mod orbit;
pub mod ship;
pub mod station;
pub mod waypoint;

use avian3d::prelude::*;
use bevy::light::atmosphere::ScatteringMedium;
use bevy::light::{light_consts::lux, Atmosphere, AtmosphereEnvironmentMapLight, NotShadowCaster, SunDisk};
use bevy::math::DVec3;
use bevy::pbr::{AtmosphereMode, AtmosphereSettings};
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::camera::Exposure;
use std::collections::HashMap;
use std::sync::Arc;

use crate::camera::PlayerCamera;
use crate::controller::{carry, ControllerSet, Player, WorldBounds};
use crate::planet::chunk::{build_chunk, paint};
use crate::planet::gravity::gravitate;
use crate::planet::quadtree::NodeId;
use crate::planet::{add_streaming, origin::rebase, seed_ground, spawn_course, Chunk, ChunkLook, Chunks, Planet, Seed, COURSE_DECK};
use crate::surface::{Origin, Sphere, Surface, QUANTUM};
use crate::system::{Body, System};
use crate::tuning::Tuning;
use bevy::prelude::*;
use orbit::{Bodies, STAR};

/// Where everything is: the bodies, the anchor physics runs on, and the clock their orbits read.
#[derive(Resource)]
pub struct Solar {
    pub bodies: Bodies,
    pub spheres: HashMap<String, Arc<Sphere>>,
    pub anchor: String,
    /// Seconds since the orbits' epoch 0.
    pub epoch: f64,
    /// Whether the anchor's streamed ground has caught up since the last handoff, so its coarse
    /// stand-in can be hidden.
    pub revealed: bool,
    /// The home pad's surface point on Haven, body coordinates.
    pub pad: Vec3,
    pub star_color: [f32; 3],
}

impl Solar {
    pub fn anchor_body(&self) -> &Body {
        self.bodies.get(&self.anchor)
    }

    /// Where body `id`'s centre is, and how it is turned, in the anchor's body coordinates.
    pub fn placement(&self, id: &str) -> (Vec3, Quat) {
        let (p, _) = self.bodies.convert(id, &self.anchor, self.epoch, DVec3::ZERO, DVec3::ZERO);
        (p.as_vec3(), self.bodies.turn(id, &self.anchor, self.epoch).as_quat())
    }
}

/// A body's coarse stand-in, drawn while it is not the anchor.
#[derive(Component)]
pub struct FarMesh;

/// Kept at a body's centre and turned with it: its stand-in, its sea and its air.
#[derive(Component)]
pub struct OnBody(pub String);

/// The landing pad and the parkour course on Haven, rebuilt whenever Haven becomes the anchor.
#[derive(Component)]
pub struct Fixture;

#[derive(Component)]
pub struct Sun;

/// The background stars: a shell kept centred on the camera.
#[derive(Component)]
pub struct Starfield(Handle<StandardMaterial>);

/// The flight readout at the top of the screen.
#[derive(Component)]
struct FlightText;

/// Depth of the quadtree the stand-ins are built from: 96 chunks a body.
const FAR_DEPTH: u8 = 2;
/// Above this fraction of an atmosphere's height the sky is raymarched, which holds up from orbit.
const RAYMARCH_ABOVE: f32 = 0.4;
/// Extra scattering in every sky; see `medium`.
const SKY_GAIN: f32 = 1.5;
/// How bright the background stars are on a black sky (emissive, unaffected by exposure).
const STAR_SHINE: f32 = 3.0;
/// How the morning is chosen: the sun this high over the pad, rising.
const MORNING_SUN: f32 = 35.0;

pub struct SolarPlugin;

impl Plugin for SolarPlugin {
    fn build(&self, app: &mut App) {
        let system = System::load();
        let bodies = Bodies::new(&system);
        let spheres: HashMap<String, Arc<Sphere>> = bodies.ids().into_iter().map(|id| (id.clone(), Arc::new(Sphere::new(bodies.get(&id).clone())))).collect();
        let home = spheres["home"].clone();
        let surface = Surface::Sphere(home.clone());
        let pad = landing_site(&home);
        let frame = surface.frame(pad);
        let spawn = pad + frame * Vec3::new(5.5, COURSE_DECK + 0.95, 0.0);
        let origin = Origin::at(spawn, QUANTUM);
        let epoch = morning(&bodies, pad);
        app.insert_resource(surface)
            .insert_resource(Gravity(Vec3::ZERO))
            .insert_resource(ClearColor(Color::BLACK))
            .insert_resource(bevy::light::GlobalAmbientLight { brightness: 1500.0, ..default() })
            .insert_resource(origin)
            .insert_resource(Seed { at: pad })
            .insert_resource(WorldBounds { spawn, kill_altitude: kill_altitude(home.as_ref()) })
            .insert_resource(Solar { bodies, spheres, anchor: "home".into(), epoch, revealed: true, pad, star_color: system.star.color });
        add_streaming(app);
        ship::build(app);
        combat::build(app);
        missile::build(app);
        ai::build(app);
        enemy::build(app);
        loss::build(app);
        cockpit::build(app);
        base::build(app);
        station::build(app);
        app.add_systems(Startup, crate::quartermaster::start_kit.after(crate::gunsmith::restore));
        waypoint::build(app);
        contacts::build(app);
        // The clock moves on with the physics step, so between steps every position and the epoch
        // agree: a handoff converts positions at the instant they hold.
        app.add_systems(FixedUpdate, gravitate.before(ControllerSet))
            .add_systems(FixedPostUpdate, (switch_anchor.before(rebase), tick_epoch.after(PhysicsSystems::Last)))
            .init_resource::<crate::comic::ComicTheme>()
            .add_systems(Startup, (seed_ground, spawn_fixtures, spawn_sky, spawn_hud).chain())
            .add_systems(PostStartup, (setup_camera, dev_start.run_if(|| std::env::var_os("RUST_REGIME_AT").is_some()), ship::place_fighter.after(dev_start).run_if(|| std::env::var_os("RUST_REGIME_FIGHTER").is_some())))
            .add_systems(Update, (place_bodies, light_and_stars, flight_text).chain());
    }
}

fn kill_altitude(sphere: &Sphere) -> f32 {
    -(sphere.body.height + 100.0)
}

/// The flattest dry ground near the home continent's centre: the first spot, spiralling out in
/// 100 m steps, between 15 and 250 m above the sea where the ground 20 m around varies by under
/// 3 m. Deterministic, so the pad is always in the same place.
pub fn landing_site(sphere: &Sphere) -> Vec3 {
    let home = sphere.body.home.clone().unwrap_or(crate::system::Home { lat: 0.0, lon: 0.0, core: 0.0, continent: 0.0 });
    flat_site(sphere, lat_lon_dir(home.lat, home.lon))
}

/// The flattest dry ground near the direction `centre`, by the same search.
pub fn flat_site(sphere: &Sphere, centre: Vec3) -> Vec3 {
    let surface = Surface::Sphere(Arc::new(sphere.clone()));
    let frame = surface.frame(centre * sphere.sea_radius());
    let at = |x: f32, z: f32| (centre * sphere.sea_radius() + frame * Vec3::new(x, 0.0, z)).normalize();
    let mut best = (f32::MAX, centre);
    for ring in 0..60 {
        let r = ring as f32 * 100.0;
        let n = (ring * 6).max(1);
        for k in 0..n {
            let a = k as f32 / n as f32 * std::f32::consts::TAU;
            let (x, z) = (r * a.cos(), r * a.sin());
            let h = sphere.height(at(x, z));
            let spread = [(20.0, 0.0), (-20.0, 0.0), (0.0, 20.0), (0.0, -20.0)].iter().map(|(dx, dz)| (sphere.height(at(x + dx, z + dz)) - h).abs()).fold(0.0, f32::max);
            if (15.0..250.0).contains(&h) && spread < 3.0 {
                return sphere.surface_point(at(x, z));
            }
            let score = spread + if h > 5.0 { 0.0 } else { 1000.0 };
            if score < best.0 {
                best = (score, at(x, z));
            }
        }
    }
    sphere.surface_point(best.1)
}

/// Same convention as the debug moon: +Y north, longitude 0 at +X growing east toward -Z.
pub fn lat_lon_dir(lat: f32, lon: f32) -> Vec3 {
    let (lat, lon) = (lat.to_radians(), lon.to_radians());
    Vec3::new(lat.cos() * lon.cos(), lat.sin(), -lat.cos() * lon.sin())
}

/// How high the star stands over body point `p` on `id`, in degrees.
pub fn sun_elevation(bodies: &Bodies, id: &str, epoch: f64, p: Vec3) -> f32 {
    let (star, _) = bodies.convert(STAR, id, epoch, DVec3::ZERO, DVec3::ZERO);
    let to_star = (star - p.as_dvec3()).normalize().as_vec3();
    to_star.dot(p.normalize()).asin().to_degrees()
}

/// The first epoch of Haven's first day at which the star rises through `MORNING_SUN` over `pad`.
fn morning(bodies: &Bodies, pad: Vec3) -> f64 {
    let day = bodies.get("home").day_minutes as f64 * 60.0;
    let step = 5.0;
    let mut t = 0.0;
    while t < day {
        if sun_elevation(bodies, "home", t, pad) < MORNING_SUN && sun_elevation(bodies, "home", t + step, pad) >= MORNING_SUN {
            return t + step;
        }
        t += step;
    }
    0.0
}

fn tick_epoch(time: Res<Time>, mut solar: ResMut<Solar>) {
    solar.epoch += time.delta_secs_f64();
}

/// The anchor world's fixtures, in its frame and around the origin of the moment: its faction
/// base, and on Haven the pad, the berths and the course.
fn spawn_fixtures(world: &mut World) {
    base::spawn_bases(world);
    let solar = world.resource::<Solar>();
    if solar.anchor != "home" {
        return;
    }
    let pad = solar.pad;
    let surface = world.resource::<Surface>().clone();
    let origin = *world.resource::<Origin>();
    let Surface::Sphere(sphere) = &surface else { return };
    let frame = surface.frame(pad);
    // The apron: the pad, and a berth for each other ship running west of it (`ship::BERTHS`).
    // Each top sits a deck's height over the ground, higher where the ground rises; the rest is
    // buried, whatever the slope.
    let size = Vec3::new(26.0, 14.0, 26.0);
    let material = world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| m.add(StandardMaterial { base_color: Color::srgb(0.32, 0.33, 0.35), perceptual_roughness: 0.8, ..default() }));
    for (i, &x) in ship::BERTHS.iter().enumerate() {
        let size = if i == 0 { size } else { Vec3::new(BERTH_WIDTH, size.y, size.z) };
        let (x, deck) = if i == 0 { (0.0, COURSE_DECK) } else { (x, berth_deck(sphere, pad, x)) };
        let transform = Transform::from_translation(origin.world(pad + frame * Vec3::new(x, deck - size.y / 2.0, 0.0))).with_rotation(frame);
        let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
        let mut e = world.spawn((Name::new(if i == 0 { "Pad" } else { "Berth" }), Fixture, RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
        if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
            e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
        }
    }
    // A slab of its own for the fighter parked off the apron (`ship::FIGHTER_BERTH`).
    let [x, z] = ship::FIGHTER_BERTH;
    let size = Vec3::new(FIGHTER_PAD, size.y, FIGHTER_PAD);
    let transform = Transform::from_translation(origin.world(pad + frame * Vec3::new(x, fighter_deck(sphere, pad) - size.y / 2.0, z))).with_rotation(frame);
    let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
    let mut e = world.spawn((Name::new("Berth"), Fixture, RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), transform));
    if let (Some(mesh), Some(material)) = (mesh, material) {
        e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
    }
    // The course stands 70 m east of the pad.
    let course = sphere.surface_point((pad + frame * Vec3::X * 70.0).normalize());
    for e in spawn_course(world, &surface, &origin, course) {
        world.entity_mut(e).insert(Fixture);
    }
}

/// How wide each ship's berth is, along the row.
pub const BERTH_WIDTH: f32 = 18.0;
/// The parked fighter's slab, square.
pub const FIGHTER_PAD: f32 = 10.0;

/// The deck height of a berth `x` metres along the row from the pad, in the pad's frame: a deck
/// over the pad's ground, or more where the ground under the berth rises above that.
pub fn berth_deck(sphere: &Sphere, pad: Vec3, x: f32) -> f32 {
    COURSE_DECK.max(rise_under(sphere, pad, Vec2::new(x, 0.0), Vec2::new(BERTH_WIDTH / 2.0, 12.0)) + 0.6)
}

/// The deck height of the parked fighter's slab, in the pad's frame: just over the highest ground
/// under it, wherever that is against the pad.
pub fn fighter_deck(sphere: &Sphere, pad: Vec3) -> f32 {
    rise_under(sphere, pad, Vec2::from(ship::FIGHTER_BERTH), Vec2::splat(FIGHTER_PAD / 2.0)) + 0.6
}

/// How far the ground rises, at most, over the pad's ground under a slab centred at `at` (x, z)
/// in the pad's frame and `half` its size across.
fn rise_under(sphere: &Sphere, pad: Vec3, at: Vec2, half: Vec2) -> f32 {
    let surface = Surface::Sphere(Arc::new(sphere.clone()));
    let frame = surface.frame(pad);
    let ground = |dx: f32, dz: f32| sphere.height((pad + frame * Vec3::new(dx, 0.0, dz)).normalize());
    let here = ground(0.0, 0.0);
    let mut rise = f32::MIN;
    for dx in [-half.x, 0.0, half.x] {
        for dz in [-half.y, 0.0, half.y] {
            rise = rise.max(ground(at.x + dx, at.y + dz) - here);
        }
    }
    rise
}

/// One coarse mesh for the whole of `sphere`: every node at `FAR_DEPTH`, merged, in body
/// coordinates, painted like the streamed ground.
pub fn far_mesh(sphere: &Sphere) -> Mesh {
    use bevy::asset::RenderAssetUsages;
    use bevy::mesh::{Indices, PrimitiveTopology};
    let (mut positions, mut normals, mut colors, mut indices) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    let n = 1u32 << FAR_DEPTH;
    for face in 0..6 {
        for y in 0..n {
            for x in 0..n {
                let chunk = build_chunk(sphere, NodeId { face, depth: FAR_DEPTH, x, y });
                let base = positions.len() as u32;
                for (p, normal) in chunk.positions.iter().zip(&chunk.normals) {
                    let p = chunk.center + *p;
                    positions.push(p);
                    normals.push(*normal);
                    colors.push(match &sphere.body.palette {
                        Some(palette) => paint(sphere, palette, p, *normal),
                        None => [0.3, 0.3, 0.32, 1.0],
                    });
                }
                indices.extend(chunk.indices.iter().flatten().map(|i| base + i));
            }
        }
    }
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, colors)
        .with_inserted_indices(Indices::U32(indices))
}

/// Earth's air, thinned or thickened for a body: the same optical depth over a shell `height`
/// thick instead of 60 km, times its density, with the blue of the sky tinted.
fn medium(air: &crate::system::Air) -> ScatteringMedium {
    let mut m = ScatteringMedium::earth(256, 256);
    // Lines of sight through the air are short on a small world, so the sky is thickened by
    // `SKY_GAIN` to read as blue as Earth's.
    let k = 60_000.0 / air.height * air.density * SKY_GAIN;
    for (i, term) in m.terms.iter_mut().enumerate() {
        term.scattering *= k;
        term.absorption *= k;
        if i == 0 {
            term.scattering *= Vec3::from(air.tint);
        }
    }
    m
}

/// The stand-ins, seas, air and star, the sun, and the background stars.
fn spawn_sky(
    mut commands: Commands,
    solar: Res<Solar>,
    tuning: Res<Tuning>,
    meshes: Option<ResMut<Assets<Mesh>>>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
    mediums: Option<ResMut<Assets<ScatteringMedium>>>,
) {
    let atmosphere = tuning.graphics.atmosphere;
    commands.spawn((
        Name::new("Sun"),
        Sun,
        DirectionalLight { illuminance: if atmosphere { lux::RAW_SUNLIGHT } else { 20_000.0 }, shadow_maps_enabled: true, ..default() },
        bevy::light::CascadeShadowConfigBuilder { maximum_distance: 600.0, ..default() }.build(),
        bevy::camera::visibility::RenderLayers::from_layers(&[0, crate::body::SHADOW_ONLY_LAYER]),
        Transform::default(),
    ));
    if atmosphere {
        commands.queue(|world: &mut World| {
            let suns: Vec<Entity> = world.query_filtered::<Entity, With<Sun>>().iter(world).collect();
            for sun in suns {
                world.entity_mut(sun).insert(SunDisk::EARTH);
            }
        });
    }
    // Headless: the bodies are only orbits.
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    let mut mediums = mediums;
    for id in solar.bodies.ids() {
        let body = solar.bodies.get(&id);
        let sphere = &solar.spheres[&id];
        if id == STAR {
            let c = Vec3::from(solar.star_color);
            let glow = materials.add(StandardMaterial { base_color: Color::BLACK, emissive: LinearRgba::rgb(c.x, c.y, c.z) * 60.0, reflectance: 0.0, ..default() });
            commands.spawn((Name::new("Star"), OnBody(id.clone()), FarMesh, Mesh3d(meshes.add(bevy::math::primitives::Sphere::new(body.radius).mesh().ico(6).unwrap())), MeshMaterial3d(glow), NotShadowCaster, Transform::default()));
            continue;
        }
        let ground = materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 1.0, ..default() });
        commands.spawn((Name::new(format!("{} far", body.name)), OnBody(id.clone()), FarMesh, Mesh3d(meshes.add(far_mesh(sphere))), MeshMaterial3d(ground), NotShadowCaster, Transform::default()));
        if body.land < 1.0 {
            let sea = body.palette.as_ref().map_or([0.04, 0.16, 0.28], |p| p.sea);
            let water = materials.add(StandardMaterial {
                base_color: Color::srgba(sea[0], sea[1], sea[2], 0.94),
                alpha_mode: AlphaMode::Blend,
                perceptual_roughness: 0.15,
                reflectance: 0.5,
                ..default()
            });
            let mesh = bevy::math::primitives::Sphere::new(sphere.sea_radius()).mesh().ico(79).unwrap();
            commands.spawn((Name::new(format!("{} sea", body.name)), OnBody(id.clone()), Mesh3d(meshes.add(mesh)), MeshMaterial3d(water), NotShadowCaster, Transform::default()));
        }
        if let (Some(air), true, Some(mediums)) = (&body.air, atmosphere, mediums.as_mut()) {
            let medium = mediums.add(medium(air));
            let inner = sphere.sea_radius();
            commands.spawn((
                Name::new(format!("{} air", body.name)),
                OnBody(id.clone()),
                Atmosphere { inner_radius: inner, outer_radius: inner + air.height, ground_albedo: Vec3::splat(0.3), medium },
                Transform::from_translation(Vec3::splat(1.0e9)),
            ));
        }
    }

    let stars = star_mesh();
    let shine = materials.add(StandardMaterial { base_color: Color::BLACK, emissive: LinearRgba::WHITE * STAR_SHINE, reflectance: 0.0, ..default() });
    commands.spawn((Name::new("Stars"), Starfield(shine.clone()), Mesh3d(meshes.add(stars)), MeshMaterial3d(shine), NotShadowCaster, Transform::default()));
}

/// A shell of stars a thousand kilometres out, a few kilometres across each. Started from the
/// first star, not the unit cube it is cut from: that cube sat on the camera (a frame behind it)
/// and showed as a growing white box whenever the ship moved back past where the camera looked.
fn star_mesh() -> Mesh {
    let mut state: u64 = 0x9e37_79b9_7f4a_7c15;
    let mut next = move || {
        state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
        (state >> 40) as f32 / (1u64 << 24) as f32
    };
    let unit = Mesh::from(Cuboid::from_length(1.0));
    let mut stars: Option<Mesh> = None;
    for _ in 0..1499 {
        let z = 2.0 * next() - 1.0;
        let phi = std::f32::consts::TAU * next();
        let r = (1.0 - z * z).max(0.0).sqrt();
        let dir = Vec3::new(r * phi.cos(), z, r * phi.sin());
        let size = 1500.0 + 2500.0 * next().powi(3);
        let mut one = unit.clone();
        one.transform_by(Transform::from_translation(dir * 1.0e6).with_scale(Vec3::splat(size)).looking_to(dir, Vec3::Y));
        match &mut stars {
            Some(stars) => {
                stars.merge(&one).ok();
            }
            None => stars = Some(one),
        }
    }
    stars.unwrap_or(unit)
}

/// The camera sees across the system, through the physical sky.
fn setup_camera(mut commands: Commands, tuning: Res<Tuning>, camera: Single<(Entity, &mut Projection), With<PlayerCamera>>) {
    let (entity, mut projection) = camera.into_inner();
    if let Projection::Perspective(p) = &mut *projection {
        p.far = 5.0e6;
    }
    let g = &tuning.graphics;
    let mut e = commands.entity(entity);
    e.insert((Exposure { ev100: g.exposure }, Tonemapping::TonyMcMapface, Msaa::Off, bevy::camera::Hdr));
    if g.atmosphere {
        e.insert((AtmosphereSettings { aerial_view_lut_max_distance: 40_000.0, ..default() }, AtmosphereEnvironmentMapLight::default()));
    }
    if g.bloom {
        e.insert(crate::comic::toon::bloom_for(g.toon));
    }
    if g.toon {
        e.insert(crate::comic::toon::grade());
    }
}

/// Moves every body's stand-in, sea and air to where its orbit has it, relative to the anchor,
/// and hides the anchor's stand-in once its streamed ground has caught up.
fn place_bodies(mut solar: ResMut<Solar>, origin: Res<Origin>, chunks: Option<Res<Chunks>>, mut placed: Query<(&OnBody, &mut Transform, Option<&FarMesh>, Option<&mut Visibility>)>) {
    if !solar.revealed && chunks.as_ref().is_some_and(|c| !c.wanted.is_empty() && c.pending.is_empty() && c.wanted.iter().all(|n| c.built.contains_key(n))) {
        solar.revealed = true;
    }
    let mut at: HashMap<String, (Vec3, Quat)> = HashMap::new();
    for (on, mut tf, far, vis) in &mut placed {
        let (p, q) = *at.entry(on.0.clone()).or_insert_with(|| solar.placement(&on.0));
        tf.translation = origin.world(p);
        tf.rotation = q;
        if let (Some(_), Some(mut vis)) = (far, vis) {
            let hide = on.0 == solar.anchor && solar.revealed && on.0 != STAR;
            vis.set_if_neq(if hide { Visibility::Hidden } else { Visibility::Inherited });
        }
    }
}

/// Points the sun from the star, keeps the stars around the camera and fades them by day, and
/// raymarches the sky once the camera is high enough for the lookup tables to fail.
#[allow(clippy::type_complexity)]
fn light_and_stars(
    solar: Res<Solar>,
    origin: Res<Origin>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut sun: Query<&mut Transform, (With<Sun>, Without<Starfield>, Without<PlayerCamera>)>,
    mut stars: Query<(&mut Transform, &Starfield), Without<PlayerCamera>>,
    mut camera: Query<(&Transform, Option<&mut AtmosphereSettings>), With<PlayerCamera>>,
) {
    let Ok((cam, settings)) = camera.single_mut() else { return };
    let eye = origin.body(cam.translation);
    let (star, _) = solar.placement(STAR);
    for mut tf in &mut sun {
        *tf = Transform::default().looking_to((eye - star).normalize_or(Vec3::NEG_Y), Vec3::Y);
    }
    let body = solar.anchor_body();
    let altitude = eye.length() - (body.radius + body.sea_level);
    let elevation = if solar.anchor == STAR { -90.0 } else { sun_elevation(&solar.bodies, &solar.anchor, solar.epoch, eye) };
    // In air the day sky outshines the stars; from space or airless ground they always show.
    let day = match &body.air {
        Some(air) if solar.anchor != STAR => (1.0 - altitude / air.height).clamp(0.0, 1.0) * ((elevation + 6.0) / 8.0).clamp(0.0, 1.0),
        _ => 0.0,
    };
    for (mut tf, field) in &mut stars {
        tf.translation = cam.translation;
        if let Some(materials) = materials.as_mut()
            && let Some(mut m) = materials.get_mut(&field.0)
        {
            m.emissive = LinearRgba::WHITE * STAR_SHINE * (1.0 - day).powi(3);
        }
    }
    if let Some(mut settings) = settings {
        let high = body.air.as_ref().is_none_or(|air| solar.anchor == STAR || altitude > RAYMARCH_ABOVE * air.height);
        let mode = if high { AtmosphereMode::Raymarched } else { AtmosphereMode::LookupTexture };
        if std::mem::discriminant(&settings.rendering_method) != std::mem::discriminant(&mode) {
            settings.rendering_method = mode;
        }
    }
}

/// Re-anchors physics on the body whose sphere of influence the player has entered: the player
/// and every ship are carried into its frame with their inertial positions and velocities kept,
/// the origin restarts on the player, the old ground goes and the new body's streams in.
pub fn switch_anchor(world: &mut World) {
    let Some(solar) = world.get_resource::<Solar>() else { return };
    let epoch = solar.epoch;
    let old = solar.anchor.clone();
    let origin = *world.resource::<Origin>();
    let Ok((player_entity, player_tf, player)) = world.query::<(Entity, &Transform, &Player)>().single(world).map(|(e, t, p)| (e, *t, p.velocity)) else { return };
    let driving = world.get::<crate::vehicle::Driving>(player_entity).map(|d| d.0);
    let velocity = driving.and_then(|ship| world.get::<LinearVelocity>(ship)).map_or(player, |v| v.0);
    let solar = world.resource::<Solar>();
    let p_old = origin.body(player_tf.translation).as_dvec3();
    let (inertial, _) = solar.bodies.pose(&old, epoch).to_inertial(p_old, velocity.as_dvec3());
    let new = solar.bodies.anchor_at(inertial, epoch);
    if new != old {
        hand_off(world, &new, None);
    }
}

/// Re-anchors physics on body `new`: the player and every ship are carried into its frame with
/// their inertial positions and velocities kept, the origin restarts on the player, the old ground
/// and fixtures go and the new body's stream in. With `to` the player is put there instead (body
/// coordinates on `new`), at rest, as a respawn after being shot down does; `new` may then be the
/// anchor already, which just restarts the origin and the ground there.
pub fn hand_off(world: &mut World, new: &str, to: Option<Vec3>) {
    let solar = world.resource::<Solar>();
    let epoch = solar.epoch;
    let old = solar.anchor.clone();
    let new = new.to_string();
    let origin = *world.resource::<Origin>();
    let Ok((player_entity, player_tf, player)) = world.query::<(Entity, &Transform, &Player)>().single(world).map(|(e, t, p)| (e, *t, p.velocity)) else { return };
    let driving = world.get::<crate::vehicle::Driving>(player_entity).map(|d| d.0);
    let velocity = driving.and_then(|ship| world.get::<LinearVelocity>(ship)).map_or(player, |v| v.0);
    let solar = world.resource::<Solar>();
    let bodies = solar.bodies.clone();
    let sphere = solar.spheres[&new].clone();
    info!("anchor {old} -> {new} at epoch {epoch:.0} s");
    let turn = bodies.turn(&old, &new, epoch).as_quat();
    let (spin_old, spin_new, r_new) = {
        let (a, b) = (bodies.pose(&old, epoch), bodies.pose(&new, epoch));
        (a.spin, b.spin, b.rotation)
    };
    let carry_spin = |w: Vec3| (r_new.inverse() * (bodies.pose(&old, epoch).rotation * w.as_dvec3() + spin_old - spin_new)).as_vec3();
    let convert = |p: Vec3, v: Vec3| {
        let (p, v) = bodies.convert(&old, &new, epoch, p.as_dvec3(), v.as_dvec3());
        (p.as_vec3(), v.as_vec3())
    };

    // Where the player lands in the new frame decides the new origin.
    let (player_new, player_v) = to.map_or_else(|| convert(origin.body(player_tf.translation), velocity), |p| (p, Vec3::ZERO));
    let new_origin = Origin::at(player_new, QUANTUM);

    let ships: Vec<Entity> = world.query_filtered::<Entity, With<ship::Ship>>().iter(world).collect();
    for e in ships {
        let mut entity = world.entity_mut(e);
        let Some(tf) = entity.get::<Transform>().copied() else { continue };
        let v = entity.get::<LinearVelocity>().map_or(Vec3::ZERO, |v| v.0);
        let w = entity.get::<AngularVelocity>().map_or(Vec3::ZERO, |w| w.0);
        let (p, v) = convert(origin.body(tf.translation), v);
        let (translation, rotation) = (new_origin.world(p), (turn * tf.rotation).normalize());
        entity.insert((Transform { translation, rotation, ..tf }, Position(translation), Rotation(rotation), LinearVelocity(v), AngularVelocity(carry_spin(w))));
    }
    missile::carry(world, &origin, &new_origin, turn, convert);
    {
        let translation = new_origin.world(player_new);
        let mut entity = world.entity_mut(player_entity);
        let mut tf = entity.get_mut::<Transform>().unwrap();
        tf.translation = translation;
        tf.rotation = (turn * tf.rotation).normalize();
        let mut p = entity.get_mut::<Player>().unwrap();
        p.velocity = player_v;
        p.prev_pos = translation;
        p.frame = carry((turn * p.frame).normalize(), player_new.normalize_or(Vec3::Y));
        entity.insert(Position(translation));
    }
    let frame = world.get::<Player>(player_entity).unwrap().frame;
    world.resource_mut::<crate::input::ViewAngles>().frame = frame;

    // The old ground and its fixtures go; the new body streams from nothing.
    let stale: Vec<Entity> = world.query_filtered::<Entity, Or<(With<Chunk>, With<Fixture>)>>().iter(world).collect();
    for e in stale {
        world.despawn(e);
    }
    let cell = world.resource::<Tuning>().terrain.cell;
    let look = ChunkLook::for_body(&sphere, world.get_resource_mut::<Assets<StandardMaterial>>());
    let surface = Surface::Sphere(sphere.clone());
    // Respawns, until a parked ship says otherwise, are on the ground under the handoff.
    let spawn = sphere.surface_point(player_new.normalize_or(Vec3::Y)) + player_new.normalize_or(Vec3::Y) * 2.0;
    world.insert_resource(Planet::new(sphere.clone(), cell, new != STAR));
    world.insert_resource(Chunks::default());
    world.insert_resource(look);
    world.insert_resource(surface);
    world.insert_resource(new_origin);
    world.insert_resource(WorldBounds { spawn, kill_altitude: if new == STAR { f32::MIN } else { kill_altitude(&sphere) } });
    let mut solar = world.resource_mut::<Solar>();
    solar.anchor = new.clone();
    solar.revealed = false;
    spawn_fixtures(world);
}

/// Dev aid: `RUST_REGIME_AT=<body or base>,<altitude m>[,<speed m/s>]` starts flying the ship
/// that high over the sunlit side of a body, or over a faction base, so screenshots can be taken
/// anywhere in the system: nose level from low down and pointing at the body from high up, or
/// with a speed, diving 30° at it.
fn dev_start(world: &mut World) {
    let spec = std::env::var("RUST_REGIME_AT").unwrap_or_default();
    let mut parts = spec.split(',');
    let mut id = parts.next().unwrap_or("home").trim().to_string();
    let altitude: f32 = parts.next().and_then(|a| a.trim().parse().ok()).unwrap_or(500.0);
    let speed: Option<f32> = parts.next().and_then(|a| a.trim().parse().ok());
    let solar = world.resource::<Solar>();
    let base = world.resource::<base::Bases>().base.iter().find(|b| b.id == id).cloned();
    if let Some(b) = &base {
        id = b.body.clone();
    }
    if !solar.bodies.bodies.contains_key(&id) {
        warn!("RUST_REGIME_AT: no body or base {id}");
        return;
    }
    let (epoch, anchor, sphere) = (solar.epoch, solar.anchor.clone(), solar.spheres[&id].clone());
    let dir = match &base {
        // Over the base's landing pad.
        Some(b) => {
            let (ground, frame, _) = base::site(b, &sphere, solar.pad);
            let pad = b.pad.map_or(Vec3::ZERO, |[x, z]| Vec3::new(x, 0.0, z));
            (ground + frame * pad).normalize()
        }
        // Over the ground the star is 55° up from.
        None => {
            let (star, _) = solar.bodies.convert(STAR, &id, epoch, DVec3::ZERO, DVec3::ZERO);
            let sun = star.normalize().as_vec3();
            let side = sun.cross(Vec3::Y).normalize_or(Vec3::X);
            (Quat::from_axis_angle(side, 35f32.to_radians()) * sun).normalize()
        }
    };
    let p = sphere.surface_point(dir) + dir * altitude;
    let surface = Surface::Sphere(sphere.clone());
    let level = surface.frame(p);
    let rotation = match speed {
        Some(_) => level * Quat::from_rotation_x(-30f32.to_radians()),
        None if altitude > 5000.0 => Transform::default().looking_to(-dir, level * Vec3::NEG_Z).rotation,
        None => level,
    };
    // At rest over the target's ground, which is moving in the anchor's frame.
    let dive = (rotation * Vec3::NEG_Z * speed.unwrap_or(0.0)).as_dvec3();
    let (here, v) = solar.bodies.convert(&id, &anchor, epoch, p.as_dvec3(), dive);
    let v = v.as_vec3();
    let turn = solar.bodies.turn(&id, &anchor, epoch).as_quat();
    let origin = *world.resource::<Origin>();
    let at = origin.world(here.as_vec3());
    let Some(ship) = world.query::<(Entity, &ship::Ship)>().iter(world).find(|(_, s)| s.spec == 0).map(|(e, _)| e) else { return };
    let Ok(player) = world.query_filtered::<Entity, With<Player>>().single(world) else { return };
    let rotation = (turn * rotation).normalize();
    world.entity_mut(ship).insert((Transform::from_translation(at).with_rotation(rotation), Position(at), Rotation(rotation), LinearVelocity(v), crate::planet::bubble::KeepAwake, RigidBody::Dynamic));
    world.get_mut::<ship::Ship>(ship).unwrap().pilot = Some(player);
    world.entity_mut(player).insert((crate::vehicle::Driving(ship), ColliderDisabled, Transform::from_translation(at)));
    world.get_mut::<Player>(player).unwrap().prev_pos = at;
}

fn spawn_hud(mut commands: Commands, theme: Res<crate::comic::ComicTheme>) {
    // Below the objective caption, in the comic HUD's shadowed paper text; it hides with the HUD.
    commands.spawn((
        crate::hud::HudRoot,
        Node { position_type: PositionType::Absolute, top: Val::Px(110.0), left: Val::Px(24.0), ..default() },
        children![(FlightText, crate::comic::body_text("", 16.0, theme.paper, true, &theme), TextShadow { offset: Vec2::splat(2.0), color: theme.ink })],
    ));
}

/// Where you are, how high and how fast, and how far every other world is.
fn flight_text(
    solar: Res<Solar>,
    origin: Res<Origin>,
    player: Single<(&Transform, &Player, Option<&crate::vehicle::Driving>)>,
    ships: Query<(&Transform, &LinearVelocity, &ship::Ship)>,
    specs: Res<ship::Ships>,
    bases: Query<(&Transform, &base::Base)>,
    base_specs: Res<base::Bases>,
    prompt: Res<station::Prompt>,
    save: Option<Res<crate::save::Save>>,
    hud: Option<Res<crate::hud::FlightHud>>,
    actions: Option<Res<crate::controls::ActionState>>,
    mut text: Single<&mut Text, With<FlightText>>,
) {
    let (tf, p, driving) = *player;
    let flying = driving.and_then(|d| ships.get(d.0).ok());
    let velocity = flying.map_or(p.velocity, |(_, v, _)| v.0);
    let here = origin.body(tf.translation);
    let body = solar.anchor_body();
    let km = |m: f32| if m.abs() >= 10_000.0 { format!("{:.0} km", m / 1000.0) } else if m.abs() >= 1000.0 { format!("{:.1} km", m / 1000.0) } else { format!("{m:.0} m") };
    let mut line = if solar.anchor == STAR {
        format!("DEEP SPACE   {}/s", km(velocity.length()))
    } else {
        let ground = solar.spheres[&solar.anchor].height(here.normalize_or(Vec3::Y));
        // Flying, the height is the landing gear's over whatever is under it; on foot, the eyes'.
        let altitude = hud.as_ref().filter(|h| h.active && flying.is_some()).and_then(|h| h.altitude).unwrap_or(here.length() - (body.radius + body.sea_level) - ground.max(0.0));
        format!("{}   ALT {}   {}/s   g {:.1}", body.name.to_uppercase(), km(altitude), km(velocity.length()), body.gravity)
    };
    for (at, base) in &bases {
        line.push_str(&format!("\n{}  {}", base_specs.base[base.spec].name, km(at.translation.distance(tf.translation))));
    }
    let mut others: Vec<(f32, String)> = solar
        .bodies
        .ids()
        .into_iter()
        .filter(|id| *id != solar.anchor && id != STAR)
        .map(|id| {
            let (c, _) = solar.placement(&id);
            (c.distance(here) - solar.bodies.get(&id).radius, solar.bodies.get(&id).name.clone())
        })
        .collect();
    others.sort_by(|a, b| a.0.total_cmp(&b.0));
    for (d, name) in &others {
        line.push_str(&format!("\n{name}  {}", km(*d)));
    }
    if let Some(save) = save.filter(|s| s.banked > 0 || s.contract.is_some()) {
        line.push_str(&format!("\nBANK ${}", save.banked));
        if let Some(c) = &save.contract {
            line.push_str(&format!("   PARCEL for {} +${}", base_specs.base.iter().find(|b| b.id == c.to).map_or("?", |b| b.name.as_str()), c.pay));
        }
    }
    line.push_str(&prompt.text());
    // Prompts name the keys or the pad buttons, whichever was touched last.
    use crate::controls::{hint, Action, Ctx};
    let pad = actions.as_ref().is_some_and(|a| a.pad_last);
    let key = |ctx: Ctx, action: Action| hint(ctx, action, pad);
    if driving.is_none() {
        let near = ships.iter().filter(|(_, _, ship)| specs.ship[ship.spec].boardable()).map(|(s, _, ship)| (s.translation.distance(tf.translation), ship.spec)).filter(|(d, _)| *d < ship::BOARD_RADIUS).min_by(|a, b| a.0.total_cmp(&b.0));
        if let Some((_, spec)) = near {
            line.push_str(&format!("\n[{}] board {}", key(Ctx::Foot, Action::Use), specs.ship[spec].name));
        }
    } else if flying.is_some() {
        let f = |a: Action| key(Ctx::Ship, a);
        let steer = if pad { format!("[Left stick] pitch/roll  [{}] yaw  [Right stick] up/down", f(Action::Yaw)) } else { format!("[{}] up/down  [{}] roll", f(Action::Lift), f(Action::Roll)) };
        line.push_str(&format!(
            "\n[{}] thrust  {steer}  [{}] boost\n[{}] stop  [{}] look round  [{}] view  [{}] leave",
            f(Action::Thrust),
            f(Action::Boost),
            f(Action::Stop),
            f(Action::FreeLook),
            f(Action::ToggleView),
            f(Action::Use),
        ));
        // The nose guns and missiles, on a ship that has them (the pad's buttons are still to be
        // decided).
        if let Some((_, _, ship)) = flying
            && !specs.ship[ship.spec].guns.is_empty()
            && !pad
        {
            line.push_str(&format!("  [{}] guns  [{}] missile", f(Action::Fire), f(Action::Missile)));
        }
        if hud.as_ref().is_some_and(|h| h.too_fast > 0.0) {
            line.push_str(&format!("\nTOO FAST TO LEAVE: slow under {:.0} m/s, [{}] stops", ship::LEAVE_SPEED, f(Action::Stop)));
        }
    }
    if text.0 != line {
        text.0 = line;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_star_vertex_is_far_out() {
        let mesh = star_mesh();
        let Some(bevy::mesh::VertexAttributeValues::Float32x3(positions)) = mesh.attribute(Mesh::ATTRIBUTE_POSITION) else { panic!("no positions") };
        assert_eq!(positions.len(), 1499 * 24);
        assert!(positions.iter().all(|p| Vec3::from(*p).length() > 9.0e5), "a star sits near the camera");
    }
}
