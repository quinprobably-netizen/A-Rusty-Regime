//! Source/TF2-style kinematic character controller with parkour moves.
//!
//! Runs at 66 Hz (TF2's tick rate) in `FixedUpdate`. Movement follows the
//! Source engine's order: categorize ground, jump, friction, accelerate,
//! collide-and-slide. Air strafing, bunny hopping and ramp sliding fall out
//! of that math rather than being special cases.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::input::{PlayerInput, ViewAngles};
use crate::tuning::Tuning;

pub const SKIN: f32 = 0.015;
pub const SPAWN: Vec3 = Vec3::new(0.0, 1.0, 10.0);

/// Where the player starts and the height below which they are sent back
/// there. The arena uses the defaults; the island inserts its own.
#[derive(Resource, Clone, Copy, Debug)]
pub struct WorldBounds {
    pub spawn: Vec3,
    pub kill_y: f32,
}

impl Default for WorldBounds {
    fn default() -> Self {
        Self { spawn: SPAWN, kill_y: -30.0 }
    }
}
const GROUND_PROBE: f32 = 0.06;
const MAX_WALL_NORMAL_Y: f32 = 0.3;

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum MoveState {
    #[default]
    Air,
    Ground,
    Slide,
    WallRun,
    Mantle,
}

#[derive(Clone, Copy, Debug)]
pub struct Mantle {
    from: Vec3,
    mid: Vec3,
    to: Vec3,
    elapsed: f32,
    exit_velocity: Vec3,
}

#[derive(Component, Debug, Default)]
pub struct Player {
    pub velocity: Vec3,
    pub state: MoveState,
    pub crouched: bool,
    /// Position at the start of the last tick, for camera interpolation.
    pub prev_pos: Vec3,
    pub wall_normal: Vec3,
    /// Instant eye-height changes (crouching) for the camera to smooth out.
    pub eye_shift: f32,
    /// While positive the player can't be grounded (keeps rocket jumps airborne).
    pub knockback_lock: f32,
    jump_buffer: f32,
    slide_cooldown: f32,
    wallrun_time: f32,
    wall_cooldown: f32,
    last_wall: Option<Vec3>,
    mantle: Option<Mantle>,
}

impl Player {
    pub fn half_height(&self, t: &Tuning) -> f32 {
        if self.crouched { t.crouch_height / 2.0 } else { t.stand_height / 2.0 }
    }
    pub fn eye_offset(&self, t: &Tuning) -> f32 {
        self.half_height(t) - t.eye_from_top
    }
    pub fn horizontal_speed(&self) -> f32 {
        self.velocity.xz().length()
    }
}

/// Which hull the entity's `Collider` currently matches.
#[derive(Component)]
struct HullCrouched(bool);

pub fn hull(t: &Tuning, crouched: bool) -> Collider {
    let h = if crouched { t.crouch_height } else { t.stand_height };
    Collider::capsule(t.radius, h - 2.0 * t.radius)
}

#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct ControllerSet;

pub struct ControllerPlugin;

impl Plugin for ControllerPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<WorldBounds>().add_systems(Startup, spawn_player).add_systems(
            FixedUpdate,
            (player_tick, sync_hull).chain().in_set(ControllerSet),
        );
    }
}

fn spawn_player(mut commands: Commands, tuning: Res<Tuning>, bounds: Res<WorldBounds>) {
    commands.spawn((
        Name::new("Player"),
        Player { prev_pos: bounds.spawn, ..default() },
        HullCrouched(false),
        Transform::from_translation(bounds.spawn),
        RigidBody::Kinematic,
        hull(&tuning, false),
    ));
}

fn sync_hull(tuning: Res<Tuning>, mut q: Query<(&Player, &mut Collider, &mut HullCrouched)>) {
    for (p, mut collider, mut applied) in &mut q {
        if p.crouched != applied.0 {
            *collider = hull(&tuning, p.crouched);
            applied.0 = p.crouched;
        }
    }
}

// ---------------------------------------------------------------------------
// Source movement math (pure functions, unit tested)

pub fn friction(v: &mut Vec3, friction: f32, stop_speed: f32, dt: f32) {
    let speed = v.xz().length();
    if speed < 0.01 {
        v.x = 0.0;
        v.z = 0.0;
        return;
    }
    let control = speed.max(stop_speed);
    let scale = (speed - control * friction * dt).max(0.0) / speed;
    v.x *= scale;
    v.z *= scale;
}

pub fn accelerate(v: &mut Vec3, wish_dir: Vec3, wish_speed: f32, accel: f32, dt: f32) {
    let add = wish_speed - v.dot(wish_dir);
    if add > 0.0 {
        *v += wish_dir * (accel * dt * wish_speed).min(add);
    }
}

/// The air-strafe rule: speed is only capped along the wish direction, so
/// turning while strafing keeps adding speed.
pub fn air_accelerate(v: &mut Vec3, wish_dir: Vec3, wish_speed: f32, accel: f32, cap: f32, dt: f32) {
    let add = wish_speed.min(cap) - v.dot(wish_dir);
    if add > 0.0 {
        *v += wish_dir * (accel * wish_speed * dt).min(add);
    }
}

pub fn clip_velocity(v: Vec3, normal: Vec3) -> Vec3 {
    v - normal * v.dot(normal)
}

// ---------------------------------------------------------------------------
// Collision queries

#[derive(Clone, Copy, Debug)]
struct Hit {
    distance: f32,
    normal: Vec3,
    entity: Entity,
}

struct Space<'a, 'w, 's> {
    query: &'a SpatialQuery<'w, 's>,
    filter: SpatialQueryFilter,
}

impl Space<'_, '_, '_> {
    fn cast(&self, shape: &Collider, pos: Vec3, dir: Vec3, max: f32) -> Option<Hit> {
        let dir = Dir3::new(dir).ok()?;
        let config = ShapeCastConfig {
            max_distance: max,
            compute_contact_on_penetration: true,
            ignore_origin_penetration: false,
            ..ShapeCastConfig::DEFAULT
        };
        self.query
            .cast_shape(shape, pos, Quat::IDENTITY, dir, &config, &self.filter)
            .map(|h| Hit { distance: h.distance, normal: h.normal1, entity: h.entity })
    }

    fn ray(&self, origin: Vec3, dir: Vec3, max: f32) -> Option<Hit> {
        let dir = Dir3::new(dir).ok()?;
        self.query
            .cast_ray(origin, dir, max, true, &self.filter)
            .map(|h| Hit { distance: h.distance, normal: h.normal, entity: h.entity })
    }

    fn fits(&self, shape: &Collider, pos: Vec3) -> bool {
        self.query.shape_intersections(shape, pos, Quat::IDENTITY, &self.filter).is_empty()
    }

    /// Quake-style collide and slide. Returns true if a wall (non-walkable
    /// surface) blocked the move.
    fn slide_move(&self, shape: &Collider, pos: &mut Vec3, vel: &mut Vec3, dt: f32, walkable: f32, hits: &mut Vec<Hit>) -> bool {
        let original = *vel;
        let mut planes: Vec<Vec3> = Vec::with_capacity(4);
        let mut remaining = dt;
        let mut blocked = false;
        for _ in 0..4 {
            let motion = *vel * remaining;
            let len = motion.length();
            if len < 1e-6 {
                break;
            }
            let dir = motion / len;
            let Some(hit) = self.cast(shape, *pos, dir, len + SKIN) else {
                *pos += motion;
                break;
            };
            if hit.distance <= 0.0 {
                // Started inside something: nudge out along its normal.
                *pos += hit.normal * SKIN;
            } else {
                let travel = (hit.distance - SKIN).max(0.0);
                *pos += dir * travel;
                remaining *= 1.0 - travel / len;
            }
            blocked |= hit.normal.y < walkable;
            hits.push(hit);
            planes.push(hit.normal);

            // Find a velocity that satisfies every plane touched so far.
            let base = *vel;
            let single = (0..planes.len()).find_map(|i| {
                let v = clip_velocity(base, planes[i]);
                planes.iter().enumerate().all(|(j, p)| j == i || v.dot(*p) >= -1e-4).then_some(v)
            });
            *vel = match single {
                Some(v) => v,
                None if planes.len() == 2 => {
                    let crease = planes[0].cross(planes[1]).normalize_or_zero();
                    crease * crease.dot(base)
                }
                None => Vec3::ZERO,
            };
            if vel.dot(original) <= 0.0 {
                *vel = Vec3::ZERO;
                break;
            }
        }
        blocked
    }

    /// Ground move with stair stepping: if a wall blocks us, try the same
    /// move lifted by the step height and keep whichever goes further.
    fn step_move(&self, shape: &Collider, pos: &mut Vec3, vel: &mut Vec3, dt: f32, t: &Tuning, hits: &mut Vec<Hit>) {
        let (start_pos, start_vel) = (*pos, *vel);
        if !self.slide_move(shape, pos, vel, dt, t.walkable_normal_y, hits) {
            return;
        }
        let mut p = start_pos;
        let mut v = start_vel;
        let up = self.cast(shape, p, Vec3::Y, t.step_height + SKIN).map_or(t.step_height, |h| (h.distance - SKIN).max(0.0));
        p.y += up;
        let mut step_hits = Vec::new();
        self.slide_move(shape, &mut p, &mut v, dt, t.walkable_normal_y, &mut step_hits);
        match self.cast(shape, p, Vec3::NEG_Y, up + SKIN) {
            Some(h) if h.normal.y >= t.walkable_normal_y => p.y -= (h.distance - SKIN).max(0.0),
            _ => return,
        }
        if (p - start_pos).xz().length_squared() > (*pos - start_pos).xz().length_squared() + 1e-6 {
            *pos = p;
            *vel = Vec3::new(v.x, 0.0, v.z);
            hits.extend(step_hits);
        }
    }

    fn find_wall(&self, shape: &Collider, pos: Vec3, dirs: &[Vec3], reach: f32) -> Option<Vec3> {
        dirs.iter()
            .filter(|d| d.length_squared() > 0.01)
            .filter_map(|d| self.cast(shape, pos, d.normalize(), reach))
            .find(|h| h.normal.y.abs() < MAX_WALL_NORMAL_Y)
            .map(|h| Vec3::new(h.normal.x, 0.0, h.normal.z).normalize())
    }
}

// ---------------------------------------------------------------------------
// The tick

fn player_tick(
    bounds: Res<WorldBounds>,
    time: Res<Time>,
    tuning: Res<Tuning>,
    mut input: ResMut<PlayerInput>,
    view: Res<ViewAngles>,
    spatial: SpatialQuery,
    mut players: Query<(Entity, &mut Player, &mut Transform, Has<crate::vehicle::Driving>)>,
    mut bodies: Query<(&RigidBody, &mut LinearVelocity, &ComputedMass), Without<Player>>,
) {
    let t = &*tuning;
    let dt = time.delta_secs();
    if dt <= 0.0 {
        return;
    }
    let jump_pressed = std::mem::take(&mut input.jump_pressed);
    let reset = std::mem::take(&mut input.reset_pressed);

    for (entity, mut p, mut tf, driving) in &mut players {
        if driving {
            continue;
        }
        let space = Space { query: &spatial, filter: SpatialQueryFilter::from_excluded_entities([entity]) };
        let mut pos = tf.translation;
        p.prev_pos = pos;

        if reset || pos.y < bounds.kill_y {
            *p = Player { prev_pos: bounds.spawn, crouched: p.crouched, ..default() };
            tf.translation = bounds.spawn;
            continue;
        }

        p.slide_cooldown -= dt;
        p.wall_cooldown -= dt;
        p.knockback_lock -= dt;
        p.jump_buffer = if jump_pressed { t.jump_buffer.max(dt * 0.5) } else { p.jump_buffer - dt };
        let wants_jump = p.jump_buffer > 0.0 || (t.auto_bhop && input.jump_held);

        if p.mantle.is_some() {
            tf.translation = advance_mantle(&mut p, dt, t);
            continue;
        }

        let (forward, right) = view.flat_basis();
        let wish = forward * input.movement.y + right * input.movement.x;
        let wish_dir = wish.normalize_or_zero();
        let mut wish_speed = wish.length().min(1.0) * t.max_speed;

        // Crouch (feet stay put on the ground, legs tuck up in the air)
        let was_grounded = matches!(p.state, MoveState::Ground | MoveState::Slide);
        let want_crouch = input.crouch_held || p.state == MoveState::Slide;
        update_crouch(&space, &mut p, &mut pos, want_crouch, was_grounded, t);
        let shape = hull(t, p.crouched);

        // Categorize: ground only counts if walkable and we aren't launching off it.
        let ground = (p.knockback_lock <= 0.0 && p.velocity.y <= t.ramp_launch_speed)
            .then(|| space.cast(&shape, pos, Vec3::NEG_Y, GROUND_PROBE + SKIN))
            .flatten()
            .filter(|h| h.normal.y >= t.walkable_normal_y);
        match ground {
            Some(h) => {
                if !matches!(p.state, MoveState::Ground | MoveState::Slide) {
                    p.state = MoveState::Ground;
                    p.last_wall = None;
                }
                pos.y -= h.distance - SKIN;
            }
            None => {
                if matches!(p.state, MoveState::Ground | MoveState::Slide) {
                    p.state = MoveState::Air;
                }
            }
        }
        let grounded = ground.is_some();
        if grounded && p.crouched {
            wish_speed *= t.crouch_speed_mult;
        }

        // Jump, wall jump
        if wants_jump {
            if grounded {
                jump(&mut p, t);
            } else {
                let wall = if p.state == MoveState::WallRun {
                    Some(p.wall_normal)
                } else {
                    space.find_wall(&shape, pos, &[wish_dir, forward, -forward, right, -right], t.wall_reach)
                };
                if let Some(n) = wall.filter(|n| p.wall_cooldown <= 0.0 && p.last_wall.is_none_or(|l| l.dot(*n) < 0.7)) {
                    wall_jump(&mut p, n, t);
                }
            }
        }
        let grounded = matches!(p.state, MoveState::Ground | MoveState::Slide);

        // Slide start: crouch while running fast (also works landing into it)
        if grounded && p.state != MoveState::Slide && input.crouch_held && p.horizontal_speed() >= t.slide_min_speed {
            p.state = MoveState::Slide;
            if p.slide_cooldown <= 0.0 {
                let dir = p.velocity.with_y(0.0).normalize_or_zero();
                p.velocity += dir * t.slide_boost;
                p.slide_cooldown = t.slide_boost_cooldown;
            }
        }

        let v_before = p.velocity;
        let mut hits = Vec::new();
        let mut vel = p.velocity;

        if grounded {
            vel.y = 0.0;
            if p.state == MoveState::Slide {
                friction(&mut vel, t.slide_friction, 0.0, dt);
                if let Some(h) = ground {
                    // Gravity along the slope: slides speed up downhill.
                    let g = Vec3::NEG_Y * t.gravity;
                    vel += clip_velocity(g, h.normal).with_y(0.0) * dt;
                }
                accelerate(&mut vel, wish_dir, wish_speed, t.slide_steer, dt);
                if vel.xz().length() < t.slide_end_speed || !input.crouch_held {
                    p.state = MoveState::Ground;
                }
            } else {
                friction(&mut vel, t.friction, t.stop_speed, dt);
                accelerate(&mut vel, wish_dir, wish_speed, t.accelerate, dt);
            }
            space.step_move(&shape, &mut pos, &mut vel, dt, t, &mut hits);
            if vel.y > t.ramp_launch_speed {
                // Ran up a slope fast enough to leave it (Source ramp launch).
                p.state = MoveState::Air;
            } else {
                // Stick to the ground going down slopes and steps.
                if let Some(h) = space.cast(&shape, pos, Vec3::NEG_Y, t.step_height + SKIN) {
                    if h.normal.y >= t.walkable_normal_y {
                        pos.y -= (h.distance - SKIN).max(0.0);
                    }
                }
                vel.y = 0.0;
            }
        } else {
            update_wallrun(&space, &mut p, &shape, pos, &mut vel, input.movement, input.crouch_held, t);
            if p.state == MoveState::WallRun {
                p.wallrun_time += dt;
                let n = p.wall_normal;
                vel = clip_velocity(vel, n);
                let along = vel.with_y(0.0).normalize_or_zero();
                accelerate(&mut vel, along, t.wallrun_speed, t.accelerate, dt);
                vel.y -= t.gravity * t.wallrun_gravity_scale * dt;
                vel -= n * 0.5; // hug the wall
            } else {
                air_accelerate(&mut vel, wish_dir, wish_speed, t.air_accelerate, t.air_speed_cap, dt);
                vel.y -= t.gravity * dt;
                if input.movement.y > 0.5 {
                    if let Some(m) = try_mantle(&space, &p, &shape, pos, forward, vel, t) {
                        p.mantle = Some(m);
                        p.state = MoveState::Mantle;
                        p.velocity = Vec3::ZERO;
                        tf.translation = pos;
                        continue;
                    }
                }
            }
            vel.y = vel.y.max(-t.terminal_velocity);
            space.slide_move(&shape, &mut pos, &mut vel, dt, t.walkable_normal_y, &mut hits);
        }

        p.velocity = vel;
        tf.translation = pos;

        // Shove dynamic props we ran into.
        let mut pushed: Vec<Entity> = Vec::new();
        for h in hits {
            if pushed.contains(&h.entity) {
                continue;
            }
            let Ok((body, mut lv, mass)) = bodies.get_mut(h.entity) else { continue };
            let into = -v_before.dot(h.normal);
            if *body == RigidBody::Dynamic && into > 0.0 {
                let scale = (t.prop_ref_mass * mass.inverse()).min(1.0);
                lv.0 += -h.normal * into * t.push_strength * scale;
                pushed.push(h.entity);
            }
        }
    }
}

fn jump(p: &mut Player, t: &Tuning) {
    p.jump_buffer = 0.0;
    if t.bhop_speed_cap > 0.0 {
        let cap = t.bhop_speed_cap * t.max_speed;
        let speed = p.horizontal_speed();
        if speed > cap {
            let s = cap * 0.9 / speed;
            p.velocity.x *= s;
            p.velocity.z *= s;
        }
    }
    p.velocity.y = p.velocity.y.max(0.0) + t.jump_speed;
    p.state = MoveState::Air;
}

fn wall_jump(p: &mut Player, n: Vec3, t: &Tuning) {
    p.jump_buffer = 0.0;
    let along = clip_velocity(p.velocity, n).with_y(0.0);
    p.velocity = along + n * t.wall_jump_out + Vec3::Y * t.wall_jump_up;
    p.last_wall = Some(n);
    p.wall_cooldown = 0.25;
    p.state = MoveState::Air;
}

fn update_crouch(space: &Space, p: &mut Player, pos: &mut Vec3, want: bool, grounded: bool, t: &Tuning) {
    let dh = t.stand_height - t.crouch_height;
    let eye_before = pos.y + p.eye_offset(t);
    if want && !p.crouched {
        p.crouched = true;
        pos.y += if grounded { -dh / 2.0 } else { dh / 2.0 };
    } else if !want && p.crouched {
        let stand = hull(t, false);
        let options: &[f32] = if grounded { &[dh / 2.0] } else { &[-dh / 2.0, dh / 2.0] };
        let Some(dy) = options.iter().copied().find(|dy| space.fits(&stand, *pos + Vec3::Y * *dy)) else {
            return; // no headroom, stay crouched
        };
        p.crouched = false;
        pos.y += dy;
    } else {
        return;
    }
    p.eye_shift += eye_before - (pos.y + p.eye_offset(t));
}

#[allow(clippy::too_many_arguments)]
fn update_wallrun(space: &Space, p: &mut Player, shape: &Collider, pos: Vec3, vel: &mut Vec3, movement: Vec2, crouch: bool, t: &Tuning) {
    let speed = vel.xz().length();
    if p.state == MoveState::WallRun {
        let wall = space.find_wall(shape, pos, &[-p.wall_normal], t.wall_reach + 0.1);
        let keep = wall.is_some()
            && p.wallrun_time < t.wallrun_max_time
            && movement.y > 0.1
            && !crouch
            && speed > t.wallrun_min_speed * 0.5;
        match wall {
            Some(n) if keep => p.wall_normal = n,
            _ => {
                p.state = MoveState::Air;
                p.last_wall = Some(p.wall_normal);
                p.wall_cooldown = 0.3;
            }
        }
        return;
    }
    if p.crouched || movement.y <= 0.3 || speed < t.wallrun_min_speed || p.wall_cooldown > 0.0 {
        return;
    }
    let dir = vel.with_y(0.0) / speed;
    let side = Vec3::Y.cross(dir);
    let Some(n) = space.find_wall(shape, pos, &[side, -side], t.wall_reach) else { return };
    if n.dot(dir).abs() > 0.5 || p.last_wall.is_some_and(|l| l.dot(n) > 0.9) {
        return;
    }
    p.state = MoveState::WallRun;
    p.wall_normal = n;
    p.wallrun_time = 0.0;
    vel.y = vel.y.clamp(0.0, 4.0);
}

fn try_mantle(space: &Space, p: &Player, shape: &Collider, pos: Vec3, forward: Vec3, vel: Vec3, t: &Tuning) -> Option<Mantle> {
    let half = p.half_height(t);
    let feet = pos.y - half;
    let wall = space.cast(shape, pos, forward, 0.35)?;
    if wall.normal.y.abs() > MAX_WALL_NORMAL_Y {
        return None;
    }
    let into = -Vec3::new(wall.normal.x, 0.0, wall.normal.z).normalize();
    // Probe for a ledge top just past the wall face.
    let probe = pos + into * (wall.distance + t.radius + 0.1);
    let top = feet + t.mantle_max_height + 0.05;
    let down = space.ray(probe.with_y(top), Vec3::NEG_Y, t.mantle_max_height - t.mantle_min_height + 0.05)?;
    if down.distance <= 0.001 || down.normal.y < t.walkable_normal_y {
        return None; // wall goes higher than we can reach, or the top is too steep
    }
    let ledge_y = top - down.distance;
    let to = (pos + into * (wall.distance + t.radius + 0.15)).with_y(ledge_y + half + SKIN * 2.0);
    let mid = pos.with_y(to.y);
    if space.cast(shape, pos, Vec3::Y, mid.y - pos.y).is_some() || !space.fits(shape, mid) || !space.fits(shape, to) {
        return None;
    }
    let exit_speed = vel.xz().length().clamp(3.0, t.max_speed);
    Some(Mantle { from: pos, mid, to, elapsed: 0.0, exit_velocity: into * exit_speed })
}

fn advance_mantle(p: &mut Player, dt: f32, t: &Tuning) -> Vec3 {
    let m = p.mantle.as_mut().unwrap();
    m.elapsed += dt;
    let k = (m.elapsed / t.mantle_time).min(1.0);
    let pos = if k < 0.6 { m.from.lerp(m.mid, k / 0.6) } else { m.mid.lerp(m.to, (k - 0.6) / 0.4) };
    if k >= 1.0 {
        p.velocity = m.exit_velocity;
        p.mantle = None;
        p.state = MoveState::Air;
    }
    pos
}
