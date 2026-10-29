//! The ships: six-degree-of-freedom craft on Avian dynamic bodies, boarded like vehicles. Four of
//! them stand on Haven's apron, one per faction, each with its own handling from
//! `assets/ships.toml` and its own hull from `models/ships/<id>.glb` (built by `tools/ships`);
//! a fighter, which has no cabin and cannot be boarded, is parked off it.
//! The mouse pitches and yaws, A and D roll, W and S thrust along the nose, Space and Ctrl
//! lift and sink, Shift boosts from a tank, X stops, held Alt looks round. On a pad the left
//! stick is a flight joystick (pull back for nose up, sideways to roll), the bumpers yaw, the
//! right stick lifts, the triggers thrust, A boosts, Y stops and held B looks round. Flight assist bleeds off
//! sideways drift and, below a few kilometres, holds the ship against gravity and levels it over
//! the ground (fading out between 2.5 and 3.5 km), and slows the last metres of a descent to a
//! soft touchdown, so landing is a matter of sinking onto a flat spot. Speed is capped by height over the ground, low near it
//! and up to kilometres a second in space, and thick air drags at it and heats the nose.

use avian3d::prelude::*;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};
use serde::Deserialize;

use super::Solar;
use crate::camera::ChaseCam;
use crate::controller::{carry, ControllerSet, MoveState, Player, WorldBounds};
use crate::input::{PlayerInput, ViewAngles};
use crate::planet::bubble::KeepAwake;
use crate::planet::origin::rebase;
use crate::surface::{Origin, Surface};
use crate::vehicle::{Driving, VehicleSet};

/// Closer than this to a ship's centre, E boards it.
pub const BOARD_RADIUS: f32 = 8.0;
/// The fastest a ship may be going for its pilot to leave it, m/s.
pub const LEAVE_SPEED: f32 = 20.0;
/// Mouse travel, radians a second, that makes full stick (times the flight mouse setting).
const MOUSE_RATE: f32 = 2.4;
/// Below this height over the ground flight assist holds the ship up and levels it; it fades out
/// over `ASSIST_FADE` either side, so nothing changes all at once.
const ASSIST_HEIGHT: f32 = 3000.0;
const ASSIST_FADE: f32 = 500.0;
/// Below this height over the gear, a sinking ship is slowed to a safe touchdown.
const LANDING_HEIGHT: f32 = 30.0;
/// Seconds of boost in a full tank, and how long it takes to refill once let go.
const BOOST_TANK: f32 = 20.0;
const BOOST_REFILL: f32 = 10.0;
/// Drag area over mass, m²/kg: terminal speed at sea level on Haven is about 600 m/s.
const DRAG: f32 = 4.4e-5;
/// Air density times the cube of speed that makes the nose glow white hot.
const HOT: f32 = 1.5e8;
/// Where the ships stand on the apron, metres west of the pad's centre, in spec order.
pub const BERTHS: [f32; 4] = [-1.0, -19.0, -37.0, -55.0];
/// Where the parked fighter stands, metres east and south of the pad's centre: off the apron on
/// the way to the Roost, in sight of the spawn.
pub const FIGHTER_BERTH: [f32; 2] = [0.0, 60.0];

/// One collision box of a ship, in its frame.
#[derive(Deserialize, Clone, Debug)]
pub struct ShipBox {
    pub center: [f32; 3],
    pub size: [f32; 3],
    /// Euler angles about X, Y and Z, degrees; the open ramp slopes.
    #[serde(default)]
    pub rot: [f32; 3],
}

impl ShipBox {
    pub fn rotation(&self) -> Quat {
        Quat::from_euler(EulerRot::XYZ, self.rot[0].to_radians(), self.rot[1].to_radians(), self.rot[2].to_radians())
    }

    /// Whether a sphere of `margin` at `p` (ship frame) touches this box.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn touches(&self, p: Vec3, margin: f32) -> bool {
        let local = self.rotation().inverse() * (p - Vec3::from(self.center));
        let half = Vec3::from(self.size) / 2.0 + Vec3::splat(margin);
        local.abs().cmple(half).all()
    }
}

/// What a hull is: a ship with a cabin you walk up the ramp into and fly, or a small solid
/// fighter with no inside, which the player cannot board.
#[derive(Deserialize, Clone, Copy, Debug, Default, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ShipKind {
    #[default]
    Cabin,
    Fighter,
}

/// One ship's numbers from `assets/ships.toml`.
#[derive(Deserialize, Clone, Debug)]
pub struct ShipSpec {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub kind: ShipKind,
    pub mass: f32,
    /// Main engine, along the nose, m/s².
    pub thrust: f32,
    /// Lift engines, along the ship's up, m/s².
    pub lift: f32,
    /// Turn rates at full stick, rad/s: pitch, yaw, roll.
    pub rates: [f32; 3],
    /// Speed caps, m/s: cruising near the ground, and the most a boost reaches in deep space.
    pub cruise: f32,
    pub boost_max: f32,
    /// How fast the ship answers the stick, 1/s: heavy hulls swing round slowly.
    #[serde(default = "default_response")]
    pub response: f32,
    /// Scales air drag: a boxy hull slows more.
    #[serde(default = "default_drag")]
    pub drag: f32,
    /// From the ship's centre down to the bottom of its landing gear.
    pub rest: f32,
    /// Where the pilot sits, and where they step out, in the ship's frame (cabin ships only).
    #[serde(default)]
    pub seat: [f32; 3],
    #[serde(default)]
    pub exit: [f32; 3],
    /// Chase camera distance and height.
    pub cam: [f32; 2],
    /// Radius of each engine's exhaust glow.
    pub engine_r: f32,
    /// Cabin floor and ceiling heights.
    #[cfg_attr(not(test), allow(dead_code))]
    #[serde(default)]
    pub cabin: [f32; 2],
    /// The boarding ramp: its hinge, its length and how steeply it slopes when open, degrees.
    #[cfg_attr(not(test), allow(dead_code))]
    #[serde(default)]
    pub ramp: [f32; 3],
    #[cfg_attr(not(test), allow(dead_code))]
    #[serde(default)]
    pub ramp_len: f32,
    #[serde(default)]
    pub ramp_slope: f32,
    pub collider: Vec<ShipBox>,
}

/// Every ship in the game, in the order they stand on the apron. The first is the player's.
#[derive(Resource, Deserialize, Clone, Debug)]
pub struct Ships {
    pub ship: Vec<ShipSpec>,
}

impl Ships {
    pub fn parse(text: &str) -> Result<Self, toml::de::Error> {
        toml::from_str(text)
    }

    /// The ships compiled in from `assets/ships.toml`.
    pub fn load() -> Self {
        Self::parse(include_str!("../../assets/ships.toml")).expect("assets/ships.toml")
    }
}

fn default_response() -> f32 {
    8.0
}
fn default_drag() -> f32 {
    1.0
}

/// How much flight assist holds the ship at `clearance` metres over the ground: fully below
/// `ASSIST_HEIGHT - ASSIST_FADE`, not at all above `ASSIST_HEIGHT + ASSIST_FADE`.
pub fn assist(clearance: f32) -> f32 {
    1.0 - ((clearance - (ASSIST_HEIGHT - ASSIST_FADE)) / (2.0 * ASSIST_FADE)).clamp(0.0, 1.0)
}

impl ShipSpec {
    /// Whether the player can walk into this ship and fly it.
    pub fn boardable(&self) -> bool {
        self.kind == ShipKind::Cabin
    }

    /// How fast flight assist lets the ship go at `clearance` metres over the ground: with the
    /// boost on, one and a half times the clearance a second, from twice cruising speed up to the
    /// deep-space limit; off it, cruising speed near the ground, then growing smoothly with height
    /// (about seven times as fast for every kilometre) until there is no limit at all and the ship
    /// coasts. Smooth, so coming down from space brakes the ship gradually instead of at once.
    pub fn speed_cap(&self, clearance: f32, boost: bool) -> f32 {
        if boost {
            return (clearance * 1.5).max(self.cruise * 2.0).min(self.boost_max.max(self.cruise * 2.0));
        }
        self.cruise * ((clearance - ASSIST_HEIGHT).max(0.0) / 500.0).exp()
    }

    pub fn collider(&self) -> Collider {
        Collider::compound(self.collider.iter().map(|b| (Vec3::from(b.center), b.rotation(), Collider::cuboid(b.size[0], b.size[1], b.size[2]))).collect())
    }

    /// Where the open ramp meets the ground, in the ship's frame.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn ramp_foot(&self) -> Vec3 {
        let a = self.ramp_slope.to_radians();
        Vec3::from(self.ramp) + self.ramp_len * Vec3::new(0.0, -a.sin(), a.cos())
    }

    /// The turn that swings the open ramp up shut against the doorway.
    pub fn ramp_shut(&self) -> Quat {
        Quat::from_rotation_x(-(90.0 + self.ramp_slope).to_radians())
    }

    /// The lowest collider face, below the centre (negative).
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn bottom(&self) -> f32 {
        self.collider.iter().map(|b| b.center[1] - b.size[1] / 2.0).fold(f32::MAX, f32::min)
    }

    /// Half the ship's width over all its boxes.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn half_width(&self) -> f32 {
        self.collider.iter().map(|b| b.center[0].abs() + b.size[0] / 2.0).fold(0.0, f32::max)
    }
}

/// A ship. `before` holds where it was when this tick's physics step began.
#[derive(Component, Default)]
pub struct Ship {
    pub pilot: Option<Entity>,
    /// Index into `Ships`.
    pub spec: usize,
    /// 0 to 1: how hot the nose glows from ploughing through air.
    pub heat: f32,
    /// 0 to 1: how hard the engines are pushing, for their glow.
    pub burn: f32,
    /// When the pilot last stepped out, seconds since start; the newest parked ship is the respawn.
    pub landed_at: f64,
    /// Boost burnt, 0 (full tank) to 1 (empty), and seconds since it last burnt.
    pub boost_used: f32,
    pub boost_idle: f32,
    before: (Vec3, Quat),
}

/// Each ship's own stick. The player's input fills the one of the ship they fly each frame; an
/// AI can fill another's, and `fly` reads every ship's from its own.
#[derive(Component, Default, Debug, Clone, Copy)]
pub struct ShipControls {
    /// Forward thrust, -1 to 1.
    pub thrust: f32,
    /// Lift, -1 to 1.
    pub lift: f32,
    /// Pitch up, yaw left and roll left, each -1 to 1.
    pub turn: Vec3,
    pub boost: bool,
    /// Kill the speed over the ground.
    pub stop: bool,
    /// Mouse travel since the last tick, radians: yaw (x) and pitch (y).
    pub mouse: Vec2,
    /// The pad's stick, -1..1: pitch up (x) and yaw left (y).
    pub stick: Vec2,
    /// How far the pilot is looking round, yaw and pitch, radians (held Alt / B).
    pub look: Vec2,
    /// The mouse as a stick, smoothed over a few ticks so uneven frames do not jolt the ship.
    mouse_stick: Vec2,
}

#[derive(Component)]
struct Exhaust;

/// Holds a ship's meshes, offset each frame to where the ship is between fixed ticks.
#[derive(Component)]
struct Hull {
    spec: usize,
}

/// A hull whose glb has not been loaded yet; ships load one at a time.
#[derive(Component)]
pub(super) struct Pending;

/// The nose glow, and the ship it belongs to.
#[derive(Component)]
struct HeatGlow(Entity);

/// The boarding ramp's hinge node: down while the ship is parked, up while it flies.
#[derive(Component)]
struct Ramp {
    ship: Entity,
    open: Quat,
    shut: Quat,
}

/// What a ship's engines and nose glow in: its own materials, so every ship glows on its own.
#[derive(Component)]
struct ShipLook {
    exhaust: Handle<StandardMaterial>,
    heat: Handle<StandardMaterial>,
}

/// The glow meshes every ship shares.
#[derive(Resource)]
struct ShipMeshes {
    disc: Handle<Mesh>,
    nose: Handle<Mesh>,
}

pub fn build(app: &mut App) {
    app.init_resource::<crate::hud::FlightHud>()
        .insert_resource(Ships::load())
        .add_systems(Startup, spawn_fleet.after(crate::planet::seed_ground))
        .add_systems(Update, (controls, glow, stream, swing))
        .add_systems(PostUpdate, ease.before(TransformSystems::Propagate))
        .add_systems(FixedUpdate, (board.before(VehicleSet), fly.after(board).before(ControllerSet)))
        .add_systems(FixedPostUpdate, (remember.after(rebase).before(PhysicsSystems::First), measure.after(PhysicsSystems::Last), seat.after(PhysicsSystems::Last), park.after(PhysicsSystems::Last)))
        .add_observer(dress);
}

/// The fleet on the apron at Haven, noses north, the player's ship nearest the spawn.
fn spawn_fleet(world: &mut World) {
    let pad = world.resource::<Solar>().pad;
    let surface = world.resource::<Surface>().clone();
    let origin = *world.resource::<Origin>();
    let frame = surface.frame(pad);
    let Surface::Sphere(sphere) = &surface else { return };
    let count = world.resource::<Ships>().ship.len().min(BERTHS.len());
    for (spec, &x) in BERTHS.iter().enumerate().take(count) {
        let rest = world.resource::<Ships>().ship[spec].rest;
        let deck = if spec == 0 { crate::planet::COURSE_DECK } else { super::berth_deck(sphere, pad, x) };
        let at = origin.world(pad + frame * Vec3::new(x, deck + rest + 0.05, -2.0));
        spawn(world, spec, Transform::from_translation(at).with_rotation(frame));
    }
    // One fighter parked on its own slab off the apron, nose west, to look at (and, with
    // `combat`, to shoot at). `RUST_REGIME_FIGHTER=<id>` picks another; see `place_fighter`.
    let wanted = std::env::var("RUST_REGIME_FIGHTER").ok().and_then(|v| v.split(',').next().map(|id| id.trim().to_string()));
    let ships = world.resource::<Ships>();
    let Some(spec) = ships.ship.iter().position(|s| s.kind == ShipKind::Fighter && s.id == wanted.as_deref().unwrap_or("jackal")) else { return };
    let deck = super::fighter_deck(sphere, pad) + ships.ship[spec].rest + 0.05;
    let at = origin.world(pad + frame * Vec3::new(FIGHTER_BERTH[0], deck, FIGHTER_BERTH[1]));
    spawn(world, spec, Transform::from_translation(at).with_rotation(frame * Quat::from_rotation_y(std::f32::consts::FRAC_PI_2)));
}

/// Dev aid: with `RUST_REGIME_FIGHTER=<id>[,<metres>]` the parked fighter waits in front of the
/// player instead, broadside on and 80 m off unless told otherwise: ahead of the nose when flying
/// (`RUST_REGIME_AT`), along the view on foot. It hangs where it is put, parked like any ship.
pub fn place_fighter(world: &mut World) {
    let dist: f32 = std::env::var("RUST_REGIME_FIGHTER").ok().and_then(|v| v.split(',').nth(1).and_then(|d| d.trim().parse().ok())).unwrap_or(80.0);
    let Ok((player, ptf)) = world.query_filtered::<(Entity, &Transform), With<Player>>().single(world).map(|(e, t)| (e, *t)) else { return };
    let flown = world.get::<Driving>(player).and_then(|d| world.get::<Transform>(d.0)).copied();
    let (from, facing) = match flown {
        Some(tf) => (tf.translation, tf.rotation),
        None => (ptf.translation, world.resource::<ViewAngles>().rotation()),
    };
    let specs = world.resource::<Ships>().clone();
    let Some(fighter) = world.query::<(Entity, &Ship)>().iter(world).find(|(_, s)| specs.ship[s.spec].kind == ShipKind::Fighter).map(|(e, _)| e) else { return };
    let at = from + facing * Vec3::NEG_Z * dist;
    let rotation = (facing * Quat::from_rotation_y(std::f32::consts::FRAC_PI_2)).normalize();
    world.entity_mut(fighter).insert((Transform::from_translation(at).with_rotation(rotation), Position(at), Rotation(rotation), LinearVelocity::ZERO));
}

/// Ship number `spec` at `transform`: its body and collider now, its hull streamed in from the
/// glb once there is a renderer to show it.
pub fn spawn(world: &mut World, spec: usize, transform: Transform) -> Entity {
    let s = world.resource::<Ships>().ship[spec].clone();
    let ship = world
        .spawn((
            Name::new(s.name.clone()),
            Ship { spec, ..default() },
            ShipControls::default(),
            ChaseCam { dist: s.cam[0], height: s.cam[1], eye: Vec3::from(s.seat) + Vec3::Y * 0.72, ..default() },
            RigidBody::Dynamic,
            s.collider(),
            Mass(s.mass),
            SweptCcd::default(),
            AngularDamping(1.5),
            transform,
            Visibility::default(),
        ))
        .id();
    let hull = world.spawn((Hull { spec }, Transform::default(), Visibility::default())).id();
    world.entity_mut(ship).add_child(hull);
    if !world.contains_resource::<Assets<Mesh>>() || !world.contains_resource::<Assets<StandardMaterial>>() || !world.contains_resource::<AssetServer>() {
        return ship;
    }
    let mut materials = world.resource_mut::<Assets<StandardMaterial>>();
    let exhaust = materials.add(StandardMaterial { base_color: Color::BLACK, emissive: LinearRgba::rgb(1.0, 0.5, 0.2), ..default() });
    let heat = materials.add(StandardMaterial { base_color: Color::BLACK, emissive: LinearRgba::BLACK, alpha_mode: AlphaMode::Add, reflectance: 0.0, ..default() });
    world.entity_mut(ship).insert(ShipLook { exhaust, heat });
    world.entity_mut(hull).insert(Pending);
    if !world.contains_resource::<ShipMeshes>() {
        let mut meshes = world.resource_mut::<Assets<Mesh>>();
        let (disc, nose) = (meshes.add(Cylinder::new(1.0, 0.1)), meshes.add(Sphere::new(1.0)));
        world.insert_resource(ShipMeshes { disc, nose });
    }
    ship
}

/// Loads the next pending hull's glb once the previous one is in, so boot never decodes four
/// models at once. A model that fails to load leaves an invisible ship that still flies.
#[allow(clippy::type_complexity)]
fn stream(
    mut commands: Commands,
    server: Res<AssetServer>,
    ships: Res<Ships>,
    waiting: Query<(Entity, &Hull), (With<Pending>, Without<WorldAssetRoot>)>,
    loading: Query<(Entity, &WorldAssetRoot), With<Pending>>,
) {
    for (e, root) in &loading {
        if let Some(bevy::asset::LoadState::Failed(err)) = server.get_load_state(root.0.id()) {
            warn!("ship model failed to load: {err}");
            commands.entity(e).remove::<Pending>();
            return;
        }
    }
    if !loading.is_empty() {
        return;
    }
    if let Some((e, hull)) = waiting.iter().next() {
        let path = format!("models/ships/{}.glb", ships.ship[hull.spec].id);
        commands.entity(e).insert(WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(path))));
    }
}

/// Once a hull's glb is in: a glow disc on every `exhaust.<n>` node and the heat glow on `heat`.
#[allow(clippy::too_many_arguments)]
fn dress(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    hulls: Query<(&ChildOf, &Hull)>,
    looks: Query<&ShipLook>,
    meshes: Option<Res<ShipMeshes>>,
    ships: Res<Ships>,
    children: Query<&Children>,
    names: Query<&Name>,
    transforms: Query<&Transform>,
) {
    let Ok((parent, hull)) = hulls.get(ready.entity) else { return };
    let Some(meshes) = meshes else { return };
    let Ok(look) = looks.get(parent.parent()) else { return };
    let spec = &ships.ship[hull.spec];
    commands.entity(ready.entity).remove::<Pending>();
    let x90 = Quat::from_rotation_x(std::f32::consts::FRAC_PI_2);
    // The nose glow scales with the hull: the Kestrel's 2.4 m fuselage had a 2 × 1.6 × 4 m glow.
    // A fighter's one box is round its wings too, so its length against the Kestrel's 9.5 m cabin.
    let hull_scale = spec.collider.first().map_or(1.0, |b| if spec.boardable() { b.size[0] / 2.4 } else { b.size[2] / 9.5 });
    for e in children.iter_descendants(ready.entity) {
        let Ok(name) = names.get(e) else { continue };
        if name.starts_with("exhaust.") {
            let r = spec.engine_r;
            commands.entity(e).with_child((Exhaust, Mesh3d(meshes.disc.clone()), MeshMaterial3d(look.exhaust.clone()), Transform::from_rotation(x90).with_scale(Vec3::new(r, 1.0, r)), bevy::light::NotShadowCaster));
        } else if name.as_str() == "heat" {
            commands.entity(e).with_child((HeatGlow(parent.parent()), Mesh3d(meshes.nose.clone()), MeshMaterial3d(look.heat.clone()), Transform::from_scale(Vec3::new(2.0, 1.6, 4.0) * hull_scale), Visibility::Hidden, bevy::light::NotShadowCaster));
        } else if name.starts_with("lamp.") {
            // Cabin lamps: the hull is lit from inside, a few metres each, no shadows (the hull is
            // one mesh, so shadow maps would cost more than the lamps are worth).
            commands.entity(e).insert(PointLight { color: Color::srgb(1.0, 0.92, 0.8), intensity: 4.0e5, range: 7.0, radius: 0.12, shadow_maps_enabled: false, ..default() });
        } else if name.as_str() == "ramp" {
            let open = transforms.get(e).map_or(Quat::IDENTITY, |t| t.rotation);
            commands.entity(e).insert(Ramp { ship: parent.parent(), open, shut: open * spec.ramp_shut() });
        }
    }
}

/// Ramps swing shut when a pilot takes the ship and drop open again once it is parked.
fn swing(time: Res<Time>, ships: Query<&Ship>, mut ramps: Query<(&Ramp, &mut Transform)>) {
    let k = 1.0 - (-3.0 * time.delta_secs()).exp();
    for (ramp, mut tf) in &mut ramps {
        let Ok(ship) = ships.get(ramp.ship) else { continue };
        let target = if ship.pilot.is_some() { ramp.shut } else { ramp.open };
        if tf.rotation.angle_between(target) > 1e-3 {
            tf.rotation = tf.rotation.slerp(target, k);
        }
    }
}

/// Fills the stick of the ship the player flies from the keyboard, the mouse and the pad, and
/// keeps the view angles at rest so the mouse (and right stick) is read afresh each frame.
fn controls(
    time: Res<Time>,
    input: Res<PlayerInput>,
    mut view: ResMut<ViewAngles>,
    flying: Query<Entity, (With<Player>, With<Driving>)>,
    mut ships: Query<(&Ship, &mut ShipControls, &mut ChaseCam)>,
) {
    let player = flying.single().ok();
    let Some((_, mut controls, mut chase)) = ships.iter_mut().find(|(s, ..)| s.pilot.is_some() && s.pilot == player) else {
        for (_, mut controls, _) in &mut ships {
            controls.look = Vec2::ZERO;
        }
        return;
    };
    let turned = Vec2::new(view.yaw, view.pitch);
    view.yaw = 0.0;
    view.pitch = 0.0;
    // Held Alt or B: the mouse and right stick look round the cabin; let go and the view swings back.
    if input.free_look {
        controls.look = (controls.look + turned).clamp(Vec2::new(-2.6, -1.2), Vec2::new(2.6, 1.2));
    } else {
        controls.mouse += turned;
        controls.look *= (-8.0 * time.delta_secs()).exp();
    }
    chase.look = controls.look;
    // The stick comes from the bindings (see `controls`): keys, triggers, the left stick and the
    // bumpers. The left stick gets a gentle curve so small lift corrections are easy.
    controls.thrust = input.thrust;
    // Looking round with the right stick must not also lift the ship.
    let lift = if input.free_look { 0.0 } else { input.lift };
    controls.lift = lift.signum() * lift.abs().powf(1.5);
    controls.turn.z = input.roll;
    controls.boost = input.boost;
    controls.stop = input.stop;
    controls.stick = input.ship_stick;
}

/// E boards the nearest ship in reach, or leaves the one being flown: out at its exit point,
/// moving with it, standing up straight in the ground's frame and looking where the nose pointed.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
pub fn board(
    mut commands: Commands,
    time: Res<Time>,
    specs: Res<Ships>,
    mut input: ResMut<PlayerInput>,
    mut view: ResMut<ViewAngles>,
    mut hud: ResMut<crate::hud::FlightHud>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    mut players: Query<(Entity, &mut Player, &mut Transform, Option<&Driving>)>,
    mut ships: Query<(Entity, &mut Ship, &Transform, &LinearVelocity), Without<Player>>,
) {
    if !input.interact_pressed {
        return;
    }
    for (pe, mut p, mut ptf, driving) in &mut players {
        if let Some(d) = driving {
            let Ok((se, mut ship, stf, vel)) = ships.get_mut(d.0) else { continue };
            input.interact_pressed = false;
            // No stepping out of a ship at flying speed: a held X or E must not drop the pilot.
            // Speed is measured in the frame of the world below (it turns with the ground), so a
            // ship hovering over a spinning planet is at rest. The HUD says why, and how to stop.
            if vel.0.length() > LEAVE_SPEED {
                hud.too_fast = 3.0;
                continue;
            }
            ship.pilot = None;
            ship.landed_at = time.elapsed_secs_f64();
            ptf.translation = stf.translation + stf.rotation * Vec3::from(specs.ship[ship.spec].exit);
            let up = surface.up(origin.body(ptf.translation));
            p.frame = carry(stf.rotation, up);
            p.prev_pos = ptf.translation;
            p.velocity = vel.0;
            p.state = MoveState::Air;
            ptf.rotation = p.frame;
            *view = ViewAngles { yaw: 0.0, pitch: 0.0, frame: p.frame };
            commands.entity(pe).remove::<(Driving, ColliderDisabled)>();
            commands.entity(se).remove::<KeepAwake>();
        } else {
            // Fighters have no cabin to board.
            let near = ships
                .iter()
                .filter(|(_, s, _, _)| s.pilot.is_none() && specs.ship[s.spec].boardable())
                .map(|(e, _, tf, _)| (e, tf.translation.distance(ptf.translation)))
                .filter(|(_, d)| *d < BOARD_RADIUS)
                .min_by(|a, b| a.1.total_cmp(&b.1));
            if let Some((se, _)) = near {
                input.interact_pressed = false;
                ships.get_mut(se).unwrap().1.pilot = Some(pe);
                commands.entity(pe).insert((Driving(se), ColliderDisabled));
                // A parked ship is static; the pilot wakes it.
                commands.entity(se).insert((KeepAwake, RigidBody::Dynamic));
            }
        }
    }
}

/// The most flight assist brakes to get back under the cap, m/s².
const CAP_BRAKE: f32 = 600.0;
/// Past this deceleration needed to stop short of the ground, assist pulls the ship out of a dive.
const PULL_OUT: f32 = 50.0;

/// One tick of flight for each ship being flown, on its own stick, and the pilot carried in its seat.
#[allow(clippy::too_many_arguments)]
fn fly(
    time: Res<Time>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    tuning: Res<crate::tuning::Tuning>,
    specs: Res<Ships>,
    save: Option<Res<crate::save::Save>>,
    spatial: Option<SpatialQuery>,
    mut input: ResMut<PlayerInput>,
    mut hud: ResMut<crate::hud::FlightHud>,
    mut ships: Query<(Entity, &mut Ship, &mut ShipControls, &mut ChaseCam, Forces)>,
    mut players: Query<(&mut Player, &mut Transform), With<Driving>>,
) {
    let dt = time.delta_secs();
    if dt <= 0.0 {
        return;
    }
    hud.too_fast = (hud.too_fast - dt).max(0.0);
    hud.active = false;
    // The Yard's tuning rig: more thrust and speed, a little sharper turning.
    let (power, agility) = super::station::tune(save.map_or(0, |s| s.ship_level));
    let mut flown = false;
    for (entity, mut ship, mut controls, mut chase, mut forces) in &mut ships {
        // The mouse as a stick: how fast it moved against how fast makes full stick, eased over a
        // few ticks, so the same flick turns the ship the same at any frame or tick rate.
        let mouse = std::mem::take(&mut controls.mouse);
        let raw = (Vec2::new(mouse.y, mouse.x) / (MOUSE_RATE * dt) * tuning.flight_mouse).clamp(Vec2::NEG_ONE, Vec2::ONE);
        controls.mouse_stick = controls.mouse_stick.lerp(raw, 1.0 - (-30.0 * dt).exp());
        let Some(pilot) = ship.pilot else {
            ship.burn = 0.0;
            ship.heat *= (-0.5 * dt).exp();
            ship.boost_used = (ship.boost_used - dt / BOOST_REFILL).max(0.0);
            continue;
        };
        flown = true;
        let spec = &specs.ship[ship.spec];
        let rot = forces.rotation().0;
        let pos = forces.position().0;
        let body = origin.body(pos);
        let up = surface.up(body);
        let anchored = solar.anchor != super::orbit::STAR;
        let sphere = &solar.spheres[&solar.anchor];
        // Over the sea the water is the ground.
        let floor = if sphere.body.land < 1.0 { sphere.height(up).max(0.0) } else { sphere.height(up) };
        let clearance = if anchored { surface.altitude(body) - floor } else { f32::MAX };
        // Under the gear: close to the ground a ray finds the pads and decks the height map misses.
        let reach = LANDING_HEIGHT * 2.0 + spec.rest;
        let ray = (anchored && clearance < reach + 50.0)
            .then(|| spatial.as_ref().zip(Dir3::new(-up).ok()))
            .flatten()
            .and_then(|(q, down)| q.cast_ray(pos, down, reach, true, &SpatialQueryFilter::from_excluded_entities([entity, pilot])));
        let gear = ray.map_or(clearance - spec.rest, |hit| (hit.distance - spec.rest).min(clearance - spec.rest));
        let assisted = if anchored { assist(clearance) } else { 0.0 };
        let air = sphere.body.air.as_ref().filter(|_| anchored).map_or(0.0, |a| a.density_at(surface.altitude(body)));
        let v = forces.linear_velocity();
        let (fwd, ship_up, right) = (rot * Vec3::NEG_Z, rot * Vec3::Y, rot * Vec3::X);

        // Boost burns from a tank that refills once let go, and never while reversing.
        let boosting = controls.boost && controls.thrust >= 0.0 && ship.boost_used < 1.0;
        if boosting {
            ship.boost_used = (ship.boost_used + dt / BOOST_TANK).min(1.0);
            ship.boost_idle = 0.0;
        } else {
            ship.boost_idle += dt;
            if ship.boost_idle > 1.5 {
                ship.boost_used = (ship.boost_used - dt / BOOST_REFILL).max(0.0);
            }
        }

        // Turning: the mouse or right stick pitches and yaws, the keys or bumpers roll; near the
        // ground assist levels the ship, but never against the stick: pitching, it lets the nose
        // be; rolling, it lets the wings be.
        let stick = (Vec3::new(controls.mouse_stick.x + controls.stick.x, controls.mouse_stick.y + controls.stick.y, 0.0) + controls.turn).clamp(Vec3::NEG_ONE, Vec3::ONE);
        let mut w = rot * (stick * Vec3::from(spec.rates) * agility);
        if assisted > 0.0 {
            let strength = assisted * (0.8 + 1.7 * (1.0 - (clearance / 400.0).clamp(0.0, 1.0)));
            let level = ship_up.cross(up);
            let free = |s: f32| (1.0 - s.abs() * 4.0).clamp(0.0, 1.0);
            w += (right * level.dot(right) * free(stick.x) + fwd * level.dot(fwd) * free(stick.z)) * strength;
        }
        // Heavy hulls answer the stick slowly, light ones at once.
        let current = forces.angular_velocity();
        *forces.angular_velocity_mut() = current.lerp(w, 1.0 - (-spec.response * dt).exp());

        // Thrust, then assist: drift sideways bleeds off, gravity is held near the ground, and
        // the speed cap pulls back anything over it.
        let mut a = fwd * controls.thrust * spec.thrust * power + ship_up * controls.lift * spec.lift * power;
        let cap = spec.speed_cap(clearance, boosting) * power;
        if boosting {
            a += fwd * (cap * 0.25).clamp(spec.thrust * power * 2.0, 400.0 * power);
        }
        let along = fwd * v.dot(fwd);
        // Sideways drift bleeds off, and up-and-down drift too unless the lift engines are on.
        let mut drift = right * v.dot(right);
        if controls.lift == 0.0 {
            drift += ship_up * v.dot(ship_up);
        }
        // In vacuum only while the engines push, so a coasting ship keeps to its path and a
        // handoff between frames, which changes what "sideways" is measured against, nudges nothing.
        let pushing = controls.thrust != 0.0 || boosting;
        a -= drift * if air > 0.01 { 1.5 } else if pushing { 0.4 } else { 0.0 };
        // Reversing while moving forward also brakes, as hard as the trigger is pulled.
        if controls.thrust < 0.0 && v.dot(fwd) > 0.0 {
            a -= along.normalize_or_zero() * spec.thrust * power * -controls.thrust;
        }
        if assisted > 0.0 {
            // Gravity is always held, so a part push on the lift climbs or sinks gently.
            a -= surface.gravity(body, tuning.gravity) * assisted;
            // Hovering, it settles instead of bobbing.
            if controls.lift == 0.0 && controls.thrust == 0.0 {
                a -= up * v.dot(up) * 0.8 * assisted;
            }
        }
        let sinking = -v.dot(up);
        // Sinking onto the ground: the last few metres slow to a soft touchdown, about 1.5 m/s,
        // whatever the lift engines are doing.
        if assisted > 0.0 && controls.lift <= 0.0 && gear < LANDING_HEIGHT {
            let safe = 1.5 + 0.4 * gear.max(0.0);
            if sinking > safe {
                a += up * ((sinking - safe) * 6.0 + spec.lift * power * -controls.lift);
            }
        }
        // Diving at the ground faster than the engines could stop in time, assist pulls out.
        if anchored && sinking > 0.0 && clearance < ASSIST_HEIGHT * 2.0 {
            let need = sinking * sinking / (2.0 * (clearance - 30.0).max(10.0));
            if need > PULL_OUT {
                a += up * need.min(CAP_BRAKE * 5.0);
            }
        }
        // Stop (X / Y): every engine turns against the motion until the ship hangs still.
        if controls.stop {
            a -= v.normalize_or_zero() * (v.length() * 2.0).min((spec.thrust + spec.lift) * power);
        }
        let speed = v.length();
        if speed > cap {
            a -= v / speed * ((speed - cap) * 1.5).min(CAP_BRAKE);
        }
        a -= v * (0.5 * air * speed * DRAG * spec.drag);
        forces.apply_linear_acceleration(a);

        ship.burn = (controls.thrust.abs() + controls.lift.abs() + controls.stop as i32 as f32 + boosting as i32 as f32 * 2.0).min(1.0);
        // Ram heating: dense air times the cube of speed, normalised so 1 is a hard re-entry.
        let target = (air * speed * speed * speed / HOT).clamp(0.0, 1.0);
        ship.heat += (target - ship.heat) * (1.0 - (-3.0 * dt).exp());
        // The chase camera widens with speed and more with the boost.
        chase.kick = boosting as i32 as f32 * 0.7 + (speed / (spec.cruise * 3.0)).min(1.0) * 0.3;

        if let Ok((mut p, mut tf)) = players.get_mut(pilot) {
            tf.translation = pos + rot * Vec3::from(spec.seat);
            tf.rotation = carry(p.frame, up);
            p.frame = tf.rotation;
            p.prev_pos = tf.translation;
            p.velocity = v;
            p.state = MoveState::Ground;
            // The compass reads the nose against the same frame it reads the view on foot.
            let nose = p.frame.inverse() * fwd;
            hud.heading = (-nose.x).atan2(-nose.z);
        }
        hud.active = true;
        hud.speed = speed;
        hud.climb = v.dot(up);
        hud.altitude = anchored.then_some(gear.max(0.0));
        hud.pitch = fwd.dot(up).clamp(-1.0, 1.0).asin();
        hud.assist = assisted;
        hud.boost = 1.0 - ship.boost_used;
        hud.boosting = boosting;
        hud.stopping = controls.stop;
        hud.throttle = controls.thrust;
        hud.velocity = v;
        hud.nose = fwd;
        hud.up = up;
    }
    if flown {
        input.fire_held = false;
        input.fire_pressed = false;
        input.jump_pressed = false;
        input.ability_pressed = false;
    }
}

/// Where each ship starts this tick's physics step.
fn remember(mut ships: Query<(&mut Ship, &Position, &Rotation)>) {
    for (mut ship, p, r) in &mut ships {
        ship.before = (p.0, r.0);
    }
}

/// How far each ship moved and turned in the step, for the camera to ease across.
fn measure(mut ships: Query<(&Ship, &Position, &Rotation, &mut ChaseCam)>) {
    for (ship, p, r, mut chase) in &mut ships {
        chase.step = p.0 - ship.before.0;
        chase.turn = (r.0 * ship.before.1.inverse()).normalize();
    }
}

/// The pilot sits where the step left the ship, so they never trail it by a tick's travel.
fn seat(specs: Res<Ships>, ships: Query<(&Ship, &Position, &Rotation)>, mut players: Query<(&mut Player, &mut Transform), With<Driving>>) {
    for (ship, p, r) in &ships {
        let Some((mut player, mut tf)) = ship.pilot.and_then(|e| players.get_mut(e).ok()) else { continue };
        tf.translation = p.0 + r.0 * Vec3::from(specs.ship[ship.spec].seat);
        player.prev_pos = tf.translation;
    }
}

/// A ship with no pilot that has come to rest turns static, so walking about inside it cannot
/// nudge it and it never jitters on its gear; boarding wakes it. The ship the player last flew,
/// once parked, is where they come back after a fall or a reset: on its cabin floor. Before any
/// flight that is the first ship. A fighter has no cabin floor, so it is never the respawn.
fn park(mut commands: Commands, specs: Res<Ships>, ships: Query<(Entity, &Ship, &Transform, &LinearVelocity, &RigidBody)>, origin: Res<Origin>, mut bounds: ResMut<WorldBounds>) {
    for (e, ship, _, v, body) in &ships {
        if ship.pilot.is_none() && *body == RigidBody::Dynamic && v.0.length() < 0.5 {
            commands.entity(e).insert(RigidBody::Static);
        }
    }
    let newest = ships
        .iter()
        .filter(|(_, s, _, v, _)| s.pilot.is_none() && v.0.length() < 0.5 && specs.ship[s.spec].boardable())
        .max_by(|a, b| a.1.landed_at.total_cmp(&b.1.landed_at).then(b.1.spec.cmp(&a.1.spec)));
    if let Some((_, ship, tf, _, _)) = newest {
        let spawn = origin.body(tf.translation + tf.rotation * Vec3::from(specs.ship[ship.spec].exit));
        if spawn.distance(bounds.spawn) > 0.5 {
            bounds.spawn = spawn;
        }
    }
}

/// Draws each hull where its ship is between the last tick and this one, the same place the chase
/// camera puts it, so a fast ship stays steady in the view.
#[allow(clippy::type_complexity)]
fn ease(fixed: Res<Time<Fixed>>, ships: Query<(&Transform, &ChaseCam), With<Ship>>, mut hulls: Query<(&ChildOf, &mut Transform), (With<Hull>, Without<Ship>)>) {
    let behind = 1.0 - fixed.overstep_fraction();
    for (parent, mut tf) in &mut hulls {
        let Ok((ship, chase)) = ships.get(parent.parent()) else { continue };
        let inv = ship.rotation.inverse();
        tf.translation = inv * (-chase.step * behind);
        tf.rotation = (inv * chase.turn.inverse().slerp(Quat::IDENTITY, 1.0 - behind) * ship.rotation).normalize();
    }
}

/// Each ship's engines glow with its burn, its nose with its heat.
fn glow(ships: Query<(&Ship, &ShipLook)>, mut materials: Option<ResMut<Assets<StandardMaterial>>>, mut heat: Query<(&HeatGlow, &mut Visibility)>) {
    let Some(materials) = materials.as_mut() else { return };
    for (ship, look) in &ships {
        if let Some(mut m) = materials.get_mut(&look.exhaust) {
            m.emissive = LinearRgba::rgb(1.0, 0.5, 0.2) * (0.3 + 12.0 * ship.burn);
        }
        if let Some(mut m) = materials.get_mut(&look.heat) {
            m.emissive = LinearRgba::rgb(1.0, 0.4, 0.1) * 20.0 * ship.heat;
        }
    }
    for (of, mut v) in &mut heat {
        let Ok((ship, _)) = ships.get(of.0) else { continue };
        v.set_if_neq(if ship.heat > 0.02 { Visibility::Inherited } else { Visibility::Hidden });
    }
}
