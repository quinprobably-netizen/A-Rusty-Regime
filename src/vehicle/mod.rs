//! Drivable vehicles: a raycast-wheel vehicle on an Avian dynamic body, stepped at the game's 66 Hz with the
//! tyre, suspension and engine models ported from Regolith Rally (`physics`), the island's three vehicles as
//! numbers (`spec`) and their code-built bodies (`body`). Walk up to one and press E to drive; E again steps out.

pub mod body;
pub mod physics;
pub mod spec;

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::{ControllerSet, MoveState, Player, WorldBounds};
use crate::input::PlayerInput;
use crate::tuning::{Tuning, VehicleTuning};
use physics::{coilover, damp, engine_net, tyre_force, TyreCurve, SUSP};
pub use spec::{Kind, VehicleSpec};

pub struct VehiclePlugin;

impl Plugin for VehiclePlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load_assets)
            .add_systems(FixedUpdate, (enter_exit, drive).chain().in_set(VehicleSet).before(ControllerSet))
            .add_systems(Update, (wheel_visuals, hide_while_driving));
    }
}

#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct VehicleSet;

/// Per-wheel state carried between ticks.
#[derive(Clone, Copy, Debug, Default)]
pub struct WheelState {
    /// Suspension compression (m) and its rate (m/s).
    pub comp: f32,
    pub comp_vel: f32,
    /// Distance from the mount to the ground along the ray (the full length when airborne).
    pub dist: f32,
    pub grounded: bool,
    pub normal: Vec3,
    /// Vertical load (N), and the relaxed slip ratio and angle the tyre runs at.
    pub load: f32,
    pub kappa: f32,
    pub alpha: f32,
    /// Spin rate (rad/s) and accumulated angle, for the visuals.
    pub om: f32,
    pub spin: f32,
}

#[derive(Component, Debug)]
pub struct Vehicle {
    pub spec: VehicleSpec,
    pub wheels: Vec<WheelState>,
    pub steer: f32,
    /// 1.. forward gears, -1 reverse.
    pub gear: i32,
    pub rpm: f32,
    shift: f32,
    pub throttle: f32,
    pub brake: f32,
    pub handbrake: bool,
    pub driver: Option<Entity>,
    /// Where it respawns after falling off the island.
    pub home: Transform,
}

impl Vehicle {
    pub fn new(spec: VehicleSpec, home: Transform) -> Self {
        let wheels = vec![WheelState { normal: Vec3::Y, ..default() }; spec.wheels.len()];
        Vehicle { spec, wheels, steer: 0.0, gear: 1, rpm: 0.0, shift: 0.0, throttle: 0.0, brake: 0.0, handbrake: false, driver: None, home }
    }

    pub fn grounded_wheels(&self) -> usize {
        self.wheels.iter().filter(|w| w.grounded).count()
    }
}

/// On the player while they drive `0`.
#[derive(Component, Debug, Clone, Copy)]
pub struct Driving(pub Entity);

/// A wheel's visual: a child of the vehicle, moved by `wheel_visuals`.
#[derive(Component)]
pub struct WheelVisual(pub usize);

/// One unit cube, one unit cylinder and the paint shop, shared by every vehicle body.
#[derive(Resource, Clone)]
pub struct VehicleAssets {
    pub cube: Handle<Mesh>,
    pub cylinder: Handle<Mesh>,
    pub olive: Handle<StandardMaterial>,
    pub dark: Handle<StandardMaterial>,
    pub rubber: Handle<StandardMaterial>,
    pub glass: Handle<StandardMaterial>,
    pub tan: Handle<StandardMaterial>,
    pub steel: Handle<StandardMaterial>,
    pub light: Handle<StandardMaterial>,
}

pub fn load_assets(mut commands: Commands, meshes: Option<ResMut<Assets<Mesh>>>, materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    let mut paint = |r: f32, g: f32, b: f32, rough: f32, metal: f32| {
        materials.add(StandardMaterial { base_color: Color::srgb(r, g, b), perceptual_roughness: rough, metallic: metal, ..default() })
    };
    let assets = VehicleAssets {
        olive: paint(0.33, 0.36, 0.22, 0.8, 0.1),
        dark: paint(0.1, 0.1, 0.1, 0.6, 0.4),
        rubber: paint(0.06, 0.06, 0.06, 0.95, 0.0),
        glass: paint(0.55, 0.7, 0.8, 0.1, 0.6),
        tan: paint(0.55, 0.47, 0.32, 0.9, 0.0),
        steel: paint(0.5, 0.5, 0.52, 0.4, 0.8),
        light: materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.95, 0.7), emissive: LinearRgba::new(2.0, 1.8, 1.0, 1.0), ..default() }),
        cube: meshes.add(Cuboid::from_length(1.0)),
        cylinder: meshes.add(Cylinder::new(0.5, 1.0)),
    };
    commands.insert_resource(assets);
}

/// Spawns a `kind` standing on the ground at `ground` facing `yaw` (0 = -Z). Without assets (headless tests) it has no body.
pub fn spawn(commands: &mut Commands, assets: Option<&VehicleAssets>, tuning: &Tuning, kind: Kind, ground: Vec3, yaw: f32) -> Entity {
    let spec = spec::spec(kind);
    let home = Transform::from_translation(ground + Vec3::Y * (spec.cg_h + 0.05)).with_rotation(Quat::from_rotation_y(yaw));
    let volume = spec.hull.x * spec.hull.y * spec.hull.z;
    let hull = Collider::compound(vec![(spec.hull_center, Quat::IDENTITY, Collider::cuboid(spec.hull.x, spec.hull.y, spec.hull.z))]);
    let g = tuning.gravity;
    let mounts: Vec<Vec3> = (0..spec.wheels.len()).map(|k| spec.mount(k, g)).collect();
    let entity = commands
        .spawn((
            Name::new(spec.name),
            RigidBody::Dynamic,
            hull,
            ColliderDensity(spec.mass / volume),
            TransformInterpolation,
            home,
            Visibility::default(),
            Vehicle::new(spec.clone(), home),
        ))
        .id();
    if let Some(assets) = assets {
        body::build(commands, assets, entity, &spec, &mounts);
    }
    entity
}

#[derive(Default, Clone, Copy)]
struct Controls {
    /// +1 accelerate, -1 brake or reverse.
    axis: f32,
    /// +1 left.
    steer: f32,
    handbrake: bool,
}

fn enter_exit(
    mut commands: Commands,
    mut input: ResMut<PlayerInput>,
    tuning: Res<Tuning>,
    mut players: Query<(Entity, &mut Player, &mut Transform, Option<&Driving>)>,
    mut vehicles: Query<(Entity, &mut Vehicle, &Transform, &LinearVelocity), Without<Player>>,
) {
    if !std::mem::take(&mut input.interact_pressed) {
        return;
    }
    for (pe, mut p, mut ptf, driving) in &mut players {
        if let Some(d) = driving {
            if let Ok((_, mut v, vtf, vel)) = vehicles.get_mut(d.0) {
                v.driver = None;
                ptf.translation = vtf.translation + vtf.rotation * v.spec.exit;
                p.prev_pos = ptf.translation;
                p.velocity = vel.0;
                p.state = MoveState::Air;
            }
            commands.entity(pe).remove::<(Driving, ColliderDisabled)>();
        } else {
            let near = vehicles
                .iter()
                .filter(|(_, v, _, _)| v.driver.is_none())
                .map(|(e, _, tf, _)| (e, tf.translation.distance(ptf.translation)))
                .filter(|(_, d)| *d < tuning.vehicle.enter_radius)
                .min_by(|a, b| a.1.total_cmp(&b.1));
            if let Some((ve, _)) = near {
                vehicles.get_mut(ve).unwrap().1.driver = Some(pe);
                commands.entity(pe).insert((Driving(ve), ColliderDisabled));
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn drive(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    bounds: Res<WorldBounds>,
    mut input: ResMut<PlayerInput>,
    spatial: SpatialQuery,
    mut vehicles: Query<(Entity, &mut Vehicle, Forces)>,
    mut players: Query<(Entity, &Driving, &mut Player, &mut Transform)>,
) {
    let dt = time.delta_secs();
    if dt <= 0.0 {
        return;
    }
    let g = tuning.gravity;
    let mut anyone_driving = false;
    for (entity, mut v, mut forces) in &mut vehicles {
        let driver = players.iter().find(|(_, d, _, _)| d.0 == entity).map(|(e, _, _, _)| e);
        let ctl = match driver {
            Some(_) => Controls { axis: input.movement.y, steer: -input.movement.x, handbrake: input.jump_held },
            None => Controls::default(),
        };
        step(&mut v, &mut forces, &spatial, entity, driver, ctl, &tuning.vehicle, g, dt);

        if forces.position().y < bounds.kill_y {
            let home = v.home;
            for w in &mut v.wheels {
                *w = WheelState { normal: Vec3::Y, ..default() };
            }
            commands.entity(entity).insert((Position(home.translation), Rotation(home.rotation), LinearVelocity::ZERO, AngularVelocity::ZERO, home));
        }

        if let Some(d) = driver {
            anyone_driving = true;
            let (_, _, mut p, mut tf) = players.get_mut(d).unwrap();
            tf.translation = forces.position().0 + forces.rotation().0 * v.spec.seat;
            p.prev_pos = tf.translation;
            p.velocity = forces.linear_velocity();
            p.state = MoveState::Ground;
        }
    }
    if anyone_driving {
        input.fire_held = false;
        input.fire_pressed = false;
        input.jump_pressed = false;
    }
}

/// One 66 Hz step of a vehicle: steering and gearbox from the controls, then each wheel's ray, coil-over and tyre.
#[allow(clippy::too_many_arguments)]
fn step(v: &mut Vehicle, f: &mut avian3d::dynamics::rigid_body::forces::ForcesItem<'_, '_>, spatial: &SpatialQuery, entity: Entity, driver: Option<Entity>, ctl: Controls, t: &VehicleTuning, g: f32, dt: f32) {
    let spec = v.spec.clone();
    let pos = f.position().0;
    let rot = f.rotation().0;
    let up = rot * Vec3::Y;
    let fwd = rot * Vec3::NEG_Z;
    let vel = f.linear_velocity();
    let ang = f.angular_velocity();
    let m = spec.mass;
    let n = spec.wheels.len() as f32;
    let m_s = spec.sprung_mass() / n;
    let k_s = spec.spring_rate();
    let sag = spec.sag(g);
    let c_d = 2.0 * (k_s * m_s).sqrt();
    let (c_b, c_r) = (c_d * SUSP.bump, c_d * SUSP.rebound);
    let karb = k_s * SUSP.arb;
    let v_fwd = vel.dot(fwd);

    // Steering: full lock when slow, less with speed.
    let lock = spec.max_steer / (1.0 + v_fwd.abs() / 15.0);
    v.steer = damp(v.steer, ctl.steer * lock, 8.0, dt);

    // Pedals: the axis accelerates in the direction of the gear and brakes against the direction of travel;
    // reverse engages from a standstill.
    if ctl.axis < -0.1 && v_fwd < 0.8 && v.gear > 0 {
        v.gear = -1;
    } else if ctl.axis > 0.1 && v_fwd > -0.8 && v.gear < 0 {
        v.gear = 1;
    }
    let dir = if v.gear < 0 { -1.0 } else { 1.0 };
    let (throttle, brake) = if ctl.axis * dir >= 0.0 {
        (ctl.axis.abs(), 0.0)
    } else if v_fwd * dir > 0.5 {
        (0.0, ctl.axis.abs())
    } else {
        (0.0, 0.0)
    };
    v.throttle = damp(v.throttle, throttle, 10.0, dt);
    // Parked vehicles hold their brakes.
    v.brake = if driver.is_some() { brake } else { 1.0 };
    v.handbrake = ctl.handbrake;

    // Engine and gearbox: an automatic that shifts near the redline and back down when the revs fall.
    let ratio = if v.gear > 0 { spec.gears[(v.gear - 1) as usize] * spec.final_drive } else { -spec.rev * spec.final_drive };
    let driven: Vec<usize> = (0..spec.wheels.len()).filter(|&k| spec.wheels[k].driven).collect();
    let om_drive = driven.iter().map(|&k| v.wheels[k].om).sum::<f32>() / driven.len() as f32;
    let rpm_wheels = om_drive * ratio * 60.0 / std::f32::consts::TAU;
    let rpm = rpm_wheels.max(spec.idle);
    v.rpm = damp(v.rpm, rpm, 20.0, dt);
    let mut t_e = engine_net(spec.curve, rpm.min(spec.redline * 1.05), v.throttle, spec.disp, spec.redline, 0.9);
    if rpm > spec.redline {
        t_e = t_e.min(0.0);
    }
    if rpm_wheels < spec.idle {
        // the clutch slips: the engine can't brake the wheels below idle
        t_e = t_e.max(0.0);
    }
    v.shift -= dt;
    if v.shift > 0.0 {
        t_e = 0.0;
    } else if v.gear > 0 {
        if rpm > 0.9 * spec.redline && (v.gear as usize) < spec.gears.len() {
            v.gear += 1;
            v.shift = 0.3;
        } else if rpm_wheels < 0.4 * spec.redline && v.gear > 1 {
            v.gear -= 1;
            v.shift = 0.2;
        }
    }
    let per_wheel = t_e * ratio / driven.len() as f32;
    let om_max = spec.redline * 1.1 / 60.0 * std::f32::consts::TAU / ratio.abs();

    // Wheels.
    let filter = SpatialQueryFilter::from_excluded_entities(std::iter::once(entity).chain(driver));
    let comps: Vec<f32> = v.wheels.iter().map(|w| w.comp).collect();
    let m_k = m / n;
    for k in 0..spec.wheels.len() {
        let ws = spec.wheels[k];
        let mount = pos + rot * spec.mount(k, g);
        let full = spec.travel + ws.radius;
        let hit = spatial.cast_ray(mount, Dir3::new(-up).unwrap_or(Dir3::NEG_Y), full, true, &filter);
        let w = &mut v.wheels[k];
        let prev = w.comp;
        match hit {
            Some(h) => {
                w.dist = h.distance;
                w.comp = full - h.distance;
                w.grounded = true;
                w.normal = h.normal;
            }
            None => {
                w.dist = full;
                w.comp = 0.0;
                w.grounded = false;
            }
        }
        w.comp_vel = ((w.comp - prev) / dt).clamp(-12.0, 12.0);

        let t_drive = if ws.driven { per_wheel } else { 0.0 };
        let t_brake = v.brake * spec.brake_t + if v.handbrake && !ws.steers { 2.0 * spec.brake_t } else { 0.0 };
        let i_w = spec.unsprung * ws.radius * ws.radius * 0.6;
        let mut om = w.om + t_drive / i_w * dt;

        if w.grounded {
            let pair = if spec.wheels.len() == 4 { k ^ 1 } else { k };
            let arb = karb * (w.comp - comps[pair]);
            let load = (coilover(&SUSP, w.comp, w.comp_vel, k_s, c_b, c_r, c_d, m_s, sag, spec.travel) + arb).clamp(0.0, 3.0 * m * g);
            w.load = load;
            // The ground pushes back along its normal at the contact patch, as it does on a real tyre.
            let contact = mount - up * w.dist;
            let nrm = w.normal;
            f.apply_force_at_point(nrm * load, contact);
            let steer = if ws.steers { v.steer } else { 0.0 };
            let wheel_fwd: Vec3 = Quat::from_axis_angle(up, steer).mul_vec3(fwd);
            let f_t = (wheel_fwd - nrm * wheel_fwd.dot(nrm)).normalize_or_zero();
            let left_t = nrm.cross(f_t);
            let v_c = vel + ang.cross(contact - pos);
            let v_long = v_c.dot(f_t);
            let v_lat = v_c.dot(left_t);
            let relax = (v_long.abs() / 0.4).max(6.0);
            w.alpha = damp(w.alpha, v_lat.atan2(v_long.abs() + 0.8), relax, dt);
            let slip_v = om * ws.radius - v_long;
            w.kappa = damp(w.kappa, slip_v / v_long.abs().max(3.0), relax, dt);
            let tf = tyre_force(&TyreCurve::GRAVEL, t.mu * load, w.kappa, w.alpha);
            // Neither force may reverse the slip it acts on within one tick.
            let lim_y = m_k * v_lat.abs() / dt;
            let lim_x = (m_k + i_w / (ws.radius * ws.radius)) * slip_v.abs() / dt;
            let fy = tf.fy.clamp(-lim_y, lim_y);
            let fx = tf.fx.clamp(-lim_x, lim_x);
            let rr = t.rolling * load * v_long.clamp(-1.0, 1.0);
            f.apply_force_at_point(f_t * (fx - rr) + left_t * fy, contact);
            om -= fx * ws.radius / i_w * dt;
        } else {
            w.load = 0.0;
            w.alpha = damp(w.alpha, 0.0, 10.0, dt);
            w.kappa = damp(w.kappa, 0.0, 10.0, dt);
            om *= (-0.3 * dt).exp();
        }
        let d_om = t_brake / i_w * dt;
        om = if om.abs() <= d_om { 0.0 } else { om - d_om * om.signum() };
        if ws.driven {
            om = om.clamp(-om_max, om_max);
        }
        w.om = om;
        w.spin += om * dt;
    }

    // Air drag.
    let speed = vel.length();
    if speed > 0.1 {
        f.apply_force(-vel * (0.5 * 1.225 * spec.drag * speed));
    }

    // A bike balances itself: it leans into the turn its steering asks for, and stands up otherwise.
    if spec.kind == Kind::DirtBike {
        let fwd_flat = Vec3::new(fwd.x, 0.0, fwd.z).normalize_or_zero();
        if fwd_flat != Vec3::ZERO {
            let right_flat = fwd_flat.cross(Vec3::Y);
            let roll = up.dot(right_flat).clamp(-1.0, 1.0).asin();
            let v_f = v_fwd.max(0.0);
            let target = -(v_f * v_f * v.steer.tan() / (spec.wheelbase() * g)).atan().clamp(-0.7, 0.7);
            // The rider's balance is a constraint, not a spring: the roll rate is set straight toward the target
            // lean, so the lateral forces of a fast turn can't throw the bike over.
            let roll_rate = ((target - roll) * t.bike_upright).clamp(-6.0, 6.0);
            let w = ang - fwd_flat * ang.dot(fwd_flat) + fwd_flat * roll_rate;
            *f.angular_velocity_mut() = w;
        }
    }
}

fn wheel_visuals(time: Res<Time>, tuning: Res<Tuning>, vehicles: Query<&Vehicle>, mut wheels: Query<(&ChildOf, &WheelVisual, &mut Transform)>) {
    let g = tuning.gravity;
    let dt = time.delta_secs();
    for (parent, wheel, mut tf) in &mut wheels {
        let Ok(v) = vehicles.get(parent.parent()) else { continue };
        let k = wheel.0;
        let (ws, w) = (v.spec.wheels[k], v.wheels[k]);
        let drop = if w.grounded { w.dist - ws.radius } else { v.spec.travel };
        tf.translation = v.spec.mount(k, g) - Vec3::Y * drop;
        let steer = if ws.steers { v.steer } else { 0.0 };
        // Spin between ticks too, so wheels don't strobe at 66 Hz.
        let spin = w.spin + w.om * dt;
        tf.rotation = Quat::from_rotation_y(steer) * Quat::from_rotation_x(-spin);
    }
}

fn hide_while_driving(
    driving: Query<(), With<Driving>>,
    mut hidden: Query<&mut Visibility, Or<(With<crate::body::Body>, With<crate::viewmodel::ViewModel>)>>,
) {
    let want = if driving.is_empty() { Visibility::Inherited } else { Visibility::Hidden };
    for mut vis in &mut hidden {
        if *vis != want {
            *vis = want;
        }
    }
}
