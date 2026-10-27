//! The ships: six-degree-of-freedom craft on Avian dynamic bodies, boarded like vehicles. Four of
//! them stand on Haven's apron, one per faction, each with its own handling from
//! `assets/ships.toml` and its own hull from `models/ships/<id>.glb` (built by `tools/ships`).
//! The mouse pitches and yaws, A and D roll, W and S thrust along the nose, Space and Ctrl
//! lift and sink, Shift boosts. On a pad the right stick pitches and yaws, the left stick rolls
//! and lifts, the triggers thrust and A boosts (Battlefield / Star Citizen style). Flight assist bleeds off sideways drift and, below a few
//! kilometres, holds the ship against gravity and levels it over the ground, so landing is a
//! matter of sinking onto a flat spot. Speed is capped by height over the ground, low near it
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
const LEAVE_SPEED: f32 = 20.0;
/// Mouse radians of a tick that make full stick.
const MOUSE_FULL: f32 = 0.012;
/// Below this height over the ground flight assist holds the ship up and levels it.
const ASSIST_HEIGHT: f32 = 3000.0;
/// Drag area over mass, m²/kg: terminal speed at sea level on Haven is about 600 m/s.
const DRAG: f32 = 4.4e-5;
/// Air density times the cube of speed that makes the nose glow white hot.
const HOT: f32 = 1.5e8;
/// Where the ships stand on the apron, metres west of the pad's centre, in spec order.
pub const BERTHS: [f32; 4] = [-1.0, -19.0, -37.0, -55.0];

/// One collision box of a ship, in its frame.
#[derive(Deserialize, Clone, Debug)]
pub struct ShipBox {
    pub center: [f32; 3],
    pub size: [f32; 3],
}

/// One ship's numbers from `assets/ships.toml`.
#[derive(Deserialize, Clone, Debug)]
pub struct ShipSpec {
    pub id: String,
    pub name: String,
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
    /// From the ship's centre down to the bottom of its landing gear.
    pub rest: f32,
    /// Where the pilot sits, and where they step out, in the ship's frame.
    pub seat: [f32; 3],
    pub exit: [f32; 3],
    /// Chase camera distance and height.
    pub cam: [f32; 2],
    /// Radius of each engine's exhaust glow.
    pub engine_r: f32,
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

impl ShipSpec {
    /// How fast flight assist lets the ship go at `clearance` metres over the ground: with the
    /// boost on, one and a half times the clearance a second, from twice cruising speed up to the
    /// deep-space limit; off it, cruising speed near the ground and no limit higher up, where the
    /// ship coasts.
    pub fn speed_cap(&self, clearance: f32, boost: bool) -> f32 {
        match (boost, clearance < ASSIST_HEIGHT) {
            (true, _) => (clearance * 1.5).clamp(self.cruise * 2.0, self.boost_max),
            (false, true) => self.cruise,
            (false, false) => f32::INFINITY,
        }
    }

    pub fn collider(&self) -> Collider {
        Collider::compound(self.collider.iter().map(|b| (Vec3::from(b.center), Quat::IDENTITY, Collider::cuboid(b.size[0], b.size[1], b.size[2]))).collect())
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
    before: (Vec3, Quat),
}

/// The stick, filled from the keyboard and mouse each frame while flying. Tests write it.
#[derive(Resource, Default, Debug, Clone, Copy)]
pub struct ShipControls {
    /// Forward thrust, -1 to 1.
    pub thrust: f32,
    /// Lift, -1 to 1.
    pub lift: f32,
    /// Pitch up, yaw left and roll left, each -1 to 1.
    pub turn: Vec3,
    pub boost: bool,
    /// Mouse travel since the last tick, radians: yaw (x) and pitch (y).
    pub mouse: Vec2,
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
struct Pending;

/// The nose glow, and the ship it belongs to.
#[derive(Component)]
struct HeatGlow(Entity);

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
    app.init_resource::<ShipControls>()
        .insert_resource(Ships::load())
        .add_systems(Startup, spawn_fleet.after(crate::planet::seed_ground))
        .add_systems(Update, (controls, glow, stream))
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
    for spec in 0..count {
        let rest = world.resource::<Ships>().ship[spec].rest;
        let deck = if spec == 0 { crate::planet::COURSE_DECK } else { super::berth_deck(sphere, pad, BERTHS[spec]) };
        let at = origin.world(pad + frame * Vec3::new(BERTHS[spec], deck + rest + 0.05, -2.0));
        spawn(world, spec, Transform::from_translation(at).with_rotation(frame));
    }
}

/// Ship number `spec` at `transform`: its body and collider now, its hull streamed in from the
/// glb once there is a renderer to show it.
pub fn spawn(world: &mut World, spec: usize, transform: Transform) -> Entity {
    let s = world.resource::<Ships>().ship[spec].clone();
    let ship = world
        .spawn((
            Name::new(s.name.clone()),
            Ship { spec, ..default() },
            ChaseCam { dist: s.cam[0], height: s.cam[1], ..default() },
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
) {
    let Ok((parent, hull)) = hulls.get(ready.entity) else { return };
    let Some(meshes) = meshes else { return };
    let Ok(look) = looks.get(parent.parent()) else { return };
    let spec = &ships.ship[hull.spec];
    commands.entity(ready.entity).remove::<Pending>();
    let x90 = Quat::from_rotation_x(std::f32::consts::FRAC_PI_2);
    // The nose glow scales with the hull: the Kestrel's 2.4 m fuselage had a 2 × 1.6 × 4 m glow.
    let hull_scale = spec.collider.first().map_or(1.0, |b| b.size[0] / 2.4);
    for e in children.iter_descendants(ready.entity) {
        let Ok(name) = names.get(e) else { continue };
        if name.starts_with("exhaust.") {
            let r = spec.engine_r;
            commands.entity(e).with_child((Exhaust, Mesh3d(meshes.disc.clone()), MeshMaterial3d(look.exhaust.clone()), Transform::from_rotation(x90).with_scale(Vec3::new(r, 1.0, r)), bevy::light::NotShadowCaster));
        } else if name.as_str() == "heat" {
            commands.entity(e).with_child((HeatGlow(parent.parent()), Mesh3d(meshes.nose.clone()), MeshMaterial3d(look.heat.clone()), Transform::from_scale(Vec3::new(2.0, 1.6, 4.0) * hull_scale), Visibility::Hidden, bevy::light::NotShadowCaster));
        }
    }
}

/// Fills the stick from the keyboard, the mouse and the pad while the player flies, and keeps
/// the view angles at rest so the mouse (and right stick) is read afresh each frame.
fn controls(
    input: Res<PlayerInput>,
    mut controls: ResMut<ShipControls>,
    mut view: ResMut<ViewAngles>,
    flying: Query<(), (With<Player>, With<Driving>)>,
    ships: Query<&Ship>,
) {
    if flying.is_empty() || ships.iter().all(|s| s.pilot.is_none()) {
        return;
    }
    controls.mouse += Vec2::new(view.yaw, view.pitch);
    view.yaw = 0.0;
    view.pitch = 0.0;
    // The stick comes from the bindings (see `controls`): keys, triggers and the left stick.
    controls.thrust = input.thrust;
    controls.lift = input.lift;
    controls.turn.z = input.roll;
    controls.boost = input.boost;
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
            if vel.0.length() > LEAVE_SPEED {
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
            let near = ships
                .iter()
                .filter(|(_, s, _, _)| s.pilot.is_none())
                .map(|(e, _, tf, _)| (e, tf.translation.distance(ptf.translation)))
                .filter(|(_, d)| *d < BOARD_RADIUS)
                .min_by(|a, b| a.1.total_cmp(&b.1));
            if let Some((se, _)) = near {
                input.interact_pressed = false;
                ships.get_mut(se).unwrap().1.pilot = Some(pe);
                commands.entity(pe).insert((Driving(se), ColliderDisabled));
                commands.entity(se).insert(KeepAwake);
            }
        }
    }
}

/// The most flight assist brakes to get back under the cap, m/s².
const CAP_BRAKE: f32 = 600.0;
/// Past this deceleration needed to stop short of the ground, assist pulls the ship out of a dive.
const PULL_OUT: f32 = 50.0;

/// One tick of flight for the ship being flown, and the pilot carried in its seat.
#[allow(clippy::too_many_arguments)]
fn fly(
    time: Res<Time>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    tuning: Res<crate::tuning::Tuning>,
    specs: Res<Ships>,
    mut controls: ResMut<ShipControls>,
    mut input: ResMut<PlayerInput>,
    mut ships: Query<(&mut Ship, Forces)>,
    mut players: Query<(&mut Player, &mut Transform), With<Driving>>,
) {
    let dt = time.delta_secs();
    if dt <= 0.0 {
        return;
    }
    let mouse = std::mem::take(&mut controls.mouse);
    let mut flown = false;
    for (mut ship, mut forces) in &mut ships {
        let Some(pilot) = ship.pilot else {
            ship.burn = 0.0;
            ship.heat *= (-0.5 * dt).exp();
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
        let air = sphere.body.air.as_ref().filter(|_| anchored).map_or(0.0, |a| a.density_at(surface.altitude(body)));
        let v = forces.linear_velocity();
        let (fwd, ship_up) = (rot * Vec3::NEG_Z, rot * Vec3::Y);

        // Turning: the mouse pitches and yaws, the keys roll; near the ground, assist levels.
        let stick = Vec3::new(mouse.y / MOUSE_FULL, mouse.x / MOUSE_FULL, 0.0).clamp(Vec3::NEG_ONE, Vec3::ONE) + Vec3::new(controls.turn.x, controls.turn.y, controls.turn.z);
        let mut w = rot * (stick.clamp(Vec3::NEG_ONE, Vec3::ONE) * Vec3::from(spec.rates));
        let assisted = clearance < ASSIST_HEIGHT;
        if assisted && controls.turn.z == 0.0 {
            let strength = if clearance < 200.0 { 2.5 } else { 0.8 };
            let level = ship_up.cross(up);
            // Level pitch and roll but leave the heading alone.
            w += (level - up * level.dot(up)) * strength;
        }
        let current = forces.angular_velocity();
        *forces.angular_velocity_mut() = current.lerp(w, 1.0 - (-10.0 * dt).exp());

        // Thrust, then assist: drift sideways bleeds off, gravity is held near the ground, and
        // the speed cap pulls back anything over it.
        let mut a = fwd * controls.thrust * spec.thrust + ship_up * controls.lift * spec.lift;
        let cap = spec.speed_cap(clearance, controls.boost);
        if controls.boost {
            a += fwd * (cap * 0.25).clamp(spec.thrust * 2.0, 400.0);
        }
        let along = fwd * v.dot(fwd);
        // Sideways drift bleeds off, and up-and-down drift too unless the lift engines are on.
        let right = rot * Vec3::X;
        let mut drift = right * v.dot(right);
        if controls.lift == 0.0 {
            drift += ship_up * v.dot(ship_up);
        }
        // In vacuum only while the engines push, so a coasting ship keeps to its path and a
        // handoff between frames, which changes what "sideways" is measured against, nudges nothing.
        let pushing = controls.thrust != 0.0 || controls.boost;
        a -= drift * if air > 0.01 { 1.5 } else if pushing { 0.4 } else { 0.0 };
        if controls.thrust < 0.0 && v.dot(fwd) > 0.0 {
            a -= along.normalize_or_zero() * spec.thrust;
        }
        if assisted && controls.lift == 0.0 {
            a -= surface.gravity(body, tuning.gravity);
            // Hovering, it settles instead of bobbing.
            a -= up * v.dot(up) * 0.8 * (controls.thrust == 0.0) as i32 as f32;
        }
        // Diving at the ground faster than the engines could stop in time, assist pulls out.
        let sinking = -v.dot(up);
        if anchored && sinking > 0.0 && clearance < ASSIST_HEIGHT * 2.0 {
            let need = sinking * sinking / (2.0 * (clearance - 30.0).max(10.0));
            if need > PULL_OUT {
                a += up * need.min(CAP_BRAKE * 5.0);
            }
        }
        let speed = v.length();
        if speed > cap {
            a -= v / speed * ((speed - cap) * 1.5).min(CAP_BRAKE);
        }
        a -= v * (0.5 * air * speed * DRAG);
        forces.apply_linear_acceleration(a);

        ship.burn = (controls.thrust.abs() + controls.lift.abs() + controls.boost as i32 as f32 * 2.0).min(1.0);
        // Ram heating: dense air times the cube of speed, normalised so 1 is a hard re-entry.
        let target = (air * speed * speed * speed / HOT).clamp(0.0, 1.0);
        ship.heat += (target - ship.heat) * (1.0 - (-3.0 * dt).exp());

        if let Ok((mut p, mut tf)) = players.get_mut(pilot) {
            tf.translation = pos + rot * Vec3::from(spec.seat);
            tf.rotation = carry(p.frame, up);
            p.frame = tf.rotation;
            p.prev_pos = tf.translation;
            p.velocity = v;
            p.state = MoveState::Ground;
        }
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

/// The ship the player last flew, once parked, is where they come back after a fall or a
/// reset: beside it, at its door. Before any flight that is the first ship.
fn park(specs: Res<Ships>, ships: Query<(&Ship, &Transform, &LinearVelocity)>, origin: Res<Origin>, mut bounds: ResMut<WorldBounds>) {
    let newest = ships
        .iter()
        .filter(|(s, _, v)| s.pilot.is_none() && v.0.length() < 0.5)
        .max_by(|a, b| a.0.landed_at.total_cmp(&b.0.landed_at).then(b.0.spec.cmp(&a.0.spec)));
    if let Some((ship, tf, _)) = newest {
        let exit = Vec3::from(specs.ship[ship.spec].exit);
        let spawn = origin.body(tf.translation + tf.rotation * Vec3::new(exit.x, 0.0, exit.z));
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
