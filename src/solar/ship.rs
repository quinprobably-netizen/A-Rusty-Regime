//! The ship: a six-degree-of-freedom craft on an Avian dynamic body, boarded like a vehicle.
//! The mouse pitches and yaws it, A and D roll, W and S thrust along the nose, Space and Ctrl
//! lift and sink, Shift boosts. On a pad the right stick pitches and yaws, the left stick rolls
//! and lifts, the triggers thrust and A boosts (Battlefield / Star Citizen style). Flight assist bleeds off sideways drift and, below a few
//! kilometres, holds the ship against gravity and levels it over the ground, so landing is a
//! matter of sinking onto a flat spot. Speed is capped by height over the ground, low near it
//! and up to kilometres a second in space, and thick air drags at it and heats the nose.

use avian3d::prelude::*;
use bevy::prelude::*;

use super::Solar;
use crate::camera::ChaseCam;
use crate::controller::{carry, ControllerSet, MoveState, Player, WorldBounds};
use crate::input::{PlayerInput, ViewAngles};
use crate::planet::bubble::KeepAwake;
use crate::planet::origin::rebase;
use crate::surface::{Origin, Surface};
use crate::vehicle::{Driving, VehicleSet};

/// Closer than this to the ship's centre, E boards it.
pub const BOARD_RADIUS: f32 = 8.0;
/// From the ship's centre down to the bottom of its skids.
pub const REST_HEIGHT: f32 = 1.45;
const MASS: f32 = 6000.0;
/// Where the pilot sits, in the ship's frame.
const SEAT: Vec3 = Vec3::new(0.0, 0.4, -2.0);
/// Main engine, along the nose, m/s².
const THRUST: f32 = 30.0;
/// Lift engines, along the ship's up, m/s².
const LIFT: f32 = 20.0;
/// Turn rates at full stick, rad/s: pitch, yaw, roll.
const RATES: Vec3 = Vec3::new(1.6, 1.1, 2.2);
/// Mouse radians of a tick that make full stick.
const MOUSE_FULL: f32 = 0.012;
/// Speed caps, m/s: cruising near the ground, and the most a boost reaches in deep space.
const CRUISE: f32 = 160.0;
const BOOST_MAX: f32 = 6000.0;
/// Below this height over the ground flight assist holds the ship up and levels it.
const ASSIST_HEIGHT: f32 = 3000.0;
/// Drag area over mass, m²/kg: terminal speed at sea level on Haven is about 600 m/s.
const DRAG: f32 = 4.4e-5;
/// Air density times the cube of speed that makes the nose glow white hot.
const HOT: f32 = 1.5e8;

/// The ship. `before` holds where it was when this tick's physics step began.
#[derive(Component, Default)]
pub struct Ship {
    pub pilot: Option<Entity>,
    /// 0 to 1: how hot the nose glows from ploughing through air.
    pub heat: f32,
    /// 0 to 1: how hard the engines are pushing, for their glow.
    pub burn: f32,
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

/// Holds the ship's meshes, offset each frame to where the ship is between fixed ticks.
#[derive(Component)]
struct Hull;

#[derive(Component)]
struct HeatGlow;

/// What the engines and nose glow in.
#[derive(Resource)]
struct ShipLook {
    exhaust: Handle<StandardMaterial>,
    heat: Handle<StandardMaterial>,
}

pub fn build(app: &mut App) {
    app.init_resource::<ShipControls>()
        .add_systems(Startup, spawn_home_ship.after(crate::planet::seed_ground))
        .add_systems(Update, (controls, glow))
        .add_systems(PostUpdate, ease.before(TransformSystems::Propagate))
        .add_systems(FixedUpdate, (board.before(VehicleSet), fly.after(board).before(ControllerSet)))
        .add_systems(FixedPostUpdate, (remember.after(rebase).before(PhysicsSystems::First), measure.after(PhysicsSystems::Last), seat.after(PhysicsSystems::Last), park.after(PhysicsSystems::Last)));
}

/// The ship on the pad at Haven, nose north.
fn spawn_home_ship(world: &mut World) {
    let pad = world.resource::<Solar>().pad;
    let surface = world.resource::<Surface>().clone();
    let origin = *world.resource::<Origin>();
    let frame = surface.frame(pad);
    let at = origin.world(pad + frame * Vec3::new(-1.0, crate::planet::COURSE_DECK + REST_HEIGHT + 0.05, -2.0));
    spawn(world, Transform::from_translation(at).with_rotation(frame));
}

/// A ship at `transform`: hull, wings, engines and skids built from boxes, cones and cylinders.
pub fn spawn(world: &mut World, transform: Transform) -> Entity {
    let collider = Collider::compound(vec![
        (Vec3::ZERO, Quat::IDENTITY, Collider::cuboid(2.4, 1.6, 10.0)),
        (Vec3::new(0.0, -0.2, 1.0), Quat::IDENTITY, Collider::cuboid(9.0, 0.3, 3.5)),
        (Vec3::new(0.0, -1.3, 0.5), Quat::IDENTITY, Collider::cuboid(3.2, 0.3, 6.0)),
    ]);
    let ship = world
        .spawn((
            Name::new("Ship"),
            Ship::default(),
            ChaseCam { dist: 20.0, height: 5.0, ..default() },
            RigidBody::Dynamic,
            collider,
            Mass(MASS),
            SweptCcd::default(),
            AngularDamping(1.5),
            transform,
            Visibility::default(),
        ))
        .id();
    if !world.contains_resource::<Assets<Mesh>>() || !world.contains_resource::<Assets<StandardMaterial>>() {
        return ship;
    }
    let mut materials = world.resource_mut::<Assets<StandardMaterial>>();
    let hull = materials.add(StandardMaterial { base_color: Color::srgb_u8(0xF0, 0xEE, 0xE6), perceptual_roughness: 0.45, metallic: 0.3, ..default() });
    let accent = materials.add(StandardMaterial { base_color: Color::srgb_u8(0xD9, 0x77, 0x57), perceptual_roughness: 0.5, ..default() });
    let dark = materials.add(StandardMaterial { base_color: Color::srgb_u8(0x14, 0x14, 0x13), perceptual_roughness: 0.6, metallic: 0.6, ..default() });
    let glass = materials.add(StandardMaterial { base_color: Color::srgb(0.05, 0.08, 0.12), perceptual_roughness: 0.05, metallic: 0.9, reflectance: 0.9, ..default() });
    let exhaust = materials.add(StandardMaterial { base_color: Color::BLACK, emissive: LinearRgba::rgb(1.0, 0.5, 0.2), ..default() });
    let heat = materials.add(StandardMaterial { base_color: Color::BLACK, emissive: LinearRgba::BLACK, alpha_mode: AlphaMode::Add, reflectance: 0.0, ..default() });
    let x90 = Quat::from_rotation_x(std::f32::consts::FRAC_PI_2);
    let parts: Vec<(Mesh, Handle<StandardMaterial>, Transform)> = vec![
        (Cuboid::new(2.4, 1.6, 9.0).into(), hull.clone(), Transform::from_xyz(0.0, 0.0, 0.5)),
        (Cone { radius: 1.15, height: 3.2 }.into(), hull.clone(), Transform::from_xyz(0.0, 0.0, -5.6).with_rotation(Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2))),
        (Sphere::new(1.0).into(), glass, Transform::from_xyz(0.0, 0.85, -2.0).with_scale(Vec3::new(0.9, 0.6, 1.8))),
        (Cuboid::new(9.0, 0.25, 3.5).into(), hull.clone(), Transform::from_xyz(0.0, -0.2, 1.0)),
        (Cuboid::new(1.2, 0.27, 3.6).into(), accent.clone(), Transform::from_xyz(-3.6, -0.2, 1.0)),
        (Cuboid::new(1.2, 0.27, 3.6).into(), accent.clone(), Transform::from_xyz(3.6, -0.2, 1.0)),
        (Cuboid::new(0.2, 2.0, 2.6).into(), accent.clone(), Transform::from_xyz(0.0, 1.5, 3.6).with_rotation(Quat::from_rotation_x(-0.35))),
        (Cuboid::new(2.5, 0.15, 0.6).into(), accent, Transform::from_xyz(0.0, 0.81, 0.5)),
        (Cylinder::new(0.6, 3.0).into(), dark.clone(), Transform::from_xyz(-1.6, -0.1, 3.8).with_rotation(x90)),
        (Cylinder::new(0.6, 3.0).into(), dark.clone(), Transform::from_xyz(1.6, -0.1, 3.8).with_rotation(x90)),
        (Cuboid::new(0.25, 0.25, 6.0).into(), dark.clone(), Transform::from_xyz(-1.4, -1.3, 0.5)),
        (Cuboid::new(0.25, 0.25, 6.0).into(), dark.clone(), Transform::from_xyz(1.4, -1.3, 0.5)),
        (Cuboid::new(0.15, 0.6, 0.15).into(), dark.clone(), Transform::from_xyz(-1.2, -0.95, -1.5)),
        (Cuboid::new(0.15, 0.6, 0.15).into(), dark.clone(), Transform::from_xyz(1.2, -0.95, -1.5)),
        (Cuboid::new(0.15, 0.6, 0.15).into(), dark.clone(), Transform::from_xyz(-1.2, -0.95, 2.5)),
        (Cuboid::new(0.15, 0.6, 0.15).into(), dark, Transform::from_xyz(1.2, -0.95, 2.5)),
    ];
    let (nozzle, nose, parts) = {
        let mut meshes = world.resource_mut::<Assets<Mesh>>();
        let parts: Vec<_> = parts.into_iter().map(|(mesh, material, tf)| (meshes.add(mesh), material, tf)).collect();
        (meshes.add(Cylinder::new(0.5, 0.1)), meshes.add(Sphere::new(1.0)), parts)
    };
    let mut children: Vec<Entity> = parts.into_iter().map(|(mesh, material, tf)| world.spawn((Mesh3d(mesh), MeshMaterial3d(material), tf)).id()).collect();
    for x in [-1.6, 1.6] {
        children.push(world.spawn((Exhaust, Mesh3d(nozzle.clone()), MeshMaterial3d(exhaust.clone()), Transform::from_xyz(x, -0.1, 5.33).with_rotation(x90))).id());
    }
    children.push(world.spawn((HeatGlow, Mesh3d(nose), MeshMaterial3d(heat.clone()), Transform::from_xyz(0.0, 0.0, -4.5).with_scale(Vec3::new(2.0, 1.6, 4.0)), bevy::light::NotShadowCaster)).id());
    let hull = world.spawn((Hull, Transform::default(), Visibility::default())).add_children(&children).id();
    world.entity_mut(ship).add_child(hull);
    world.insert_resource(ShipLook { exhaust, heat });
    ship
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

/// E boards the nearest ship in reach, or leaves the one being flown: out to its left, moving
/// with it, standing up straight in the ground's frame and looking where the nose pointed.
#[allow(clippy::type_complexity)]
pub fn board(
    mut commands: Commands,
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
            ship.pilot = None;
            ptf.translation = stf.translation + stf.rotation * Vec3::new(-4.5, -0.4, 0.0);
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

/// How fast flight assist lets the ship go at `clearance` metres over the ground: with the
/// boost on, one and a half times the clearance a second, from twice cruising speed up to the
/// deep-space limit; off it, cruising speed near the ground and no limit higher up, where the
/// ship coasts.
pub fn speed_cap(clearance: f32, boost: bool) -> f32 {
    match (boost, clearance < ASSIST_HEIGHT) {
        (true, _) => (clearance * 1.5).clamp(CRUISE * 2.0, BOOST_MAX),
        (false, true) => CRUISE,
        (false, false) => f32::INFINITY,
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
        let mut w = rot * (stick.clamp(Vec3::NEG_ONE, Vec3::ONE) * RATES);
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
        let mut a = fwd * controls.thrust * THRUST + ship_up * controls.lift * LIFT;
        let cap = speed_cap(clearance, controls.boost);
        if controls.boost {
            a += fwd * (cap * 0.25).clamp(THRUST * 2.0, 400.0);
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
            a -= along.normalize_or_zero() * THRUST;
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
            tf.translation = pos + rot * SEAT;
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
fn seat(ships: Query<(&Ship, &Position, &Rotation)>, mut players: Query<(&mut Player, &mut Transform), With<Driving>>) {
    for (ship, p, r) in &ships {
        let Some((mut player, mut tf)) = ship.pilot.and_then(|e| players.get_mut(e).ok()) else { continue };
        tf.translation = p.0 + r.0 * SEAT;
        player.prev_pos = tf.translation;
    }
}

/// A parked ship is where the player comes back after a fall or a reset: beside it, on its
/// left.
fn park(ships: Query<(&Ship, &Transform, &LinearVelocity)>, origin: Res<Origin>, mut bounds: ResMut<WorldBounds>) {
    for (ship, tf, v) in &ships {
        if ship.pilot.is_none() && v.0.length() < 0.5 {
            let spawn = origin.body(tf.translation + tf.rotation * Vec3::new(-4.5, 0.0, 0.0));
            if spawn.distance(bounds.spawn) > 0.5 {
                bounds.spawn = spawn;
            }
        }
    }
}

/// Draws the hull where the ship is between the last tick and this one, the same place the chase
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

/// Engines glow with the burn, the nose with the heat.
fn glow(ships: Query<&Ship>, look: Option<Res<ShipLook>>, mut materials: Option<ResMut<Assets<StandardMaterial>>>, mut heat: Query<&mut Visibility, With<HeatGlow>>) {
    let (Some(look), Some(materials)) = (look, materials.as_mut()) else { return };
    let Some(ship) = ships.iter().next() else { return };
    if let Some(mut m) = materials.get_mut(&look.exhaust) {
        m.emissive = LinearRgba::rgb(1.0, 0.5, 0.2) * (0.3 + 12.0 * ship.burn);
    }
    if let Some(mut m) = materials.get_mut(&look.heat) {
        m.emissive = LinearRgba::rgb(1.0, 0.4, 0.1) * 20.0 * ship.heat;
    }
    for mut v in &mut heat {
        v.set_if_neq(if ship.heat > 0.02 { Visibility::Inherited } else { Visibility::Hidden });
    }
}
