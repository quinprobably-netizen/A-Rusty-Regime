//! What makes a base feel lived in (docs/superpowers/specs/2026-10-29-living-bases-design.md):
//!
//! - its crew, the faction's own characters from `bases.toml`: a keeper at each station who turns
//!   to face you, and people walking their rounds;
//! - the named nodes in its model: `spin.<axis>.<rpm>.<n>` parts that turn, `blink.<n>` and
//!   `strobe.<n>` beacons, `fire.<n>` and `weld.<n>` light that flickers, `smoke.<n>` puffs and
//!   weld sparks, and `sound.<kind>.<n>` loops (played by `sound`);
//! - a ship that visits: lands on the base's pad, sits a while and leaves, or passes over a base
//!   with no pad of its own.
//!
//! All of it is scenery: no colliders, nothing saved, nobody shoots. It hangs off the base entity,
//! so it goes with the base at a handoff.

use std::f32::consts::{PI, TAU};

use bevy::prelude::*;

use crate::camera::PlayerCamera;
use crate::character::{self, Pose, RigPose};
use crate::tuning::Tuning;

/// Walkers' pace, m/s, and how long they stop at each point of their round.
const WALK_SPEED: f32 = 1.4;
const PAUSE_SECS: f32 = 3.0;
/// A keeper turns to face you within this far, at this rate (rad/s).
const GREET_RADIUS: f32 = 6.0;
const TURN_RATE: f32 = 3.0;
/// The visiting ship's round, seconds: in, settle, sit, lift, out, then away for the rest.
pub const TRAFFIC_CYCLE: f32 = 200.0;
const APPROACH: f32 = 28.0;
const SETTLE: f32 = 10.0;
const SIT: f32 = 40.0;
const LIFT: f32 = 8.0;
const DEPART: f32 = 24.0;
/// Where it comes from and goes to: this far out along the pad's approach, this high.
const FAR: f32 = 420.0;
const HIGH: f32 = 140.0;
/// It hovers this high over the pad before settling.
const HOVER: f32 = 9.0;
/// A pass over a base with no pad: this high.
const PASS: f32 = 55.0;

/// One crew member's place in the base frame, from `assets/bases.toml`.
#[derive(serde::Deserialize, Clone, Debug)]
pub struct CrewSpec {
    pub character: String,
    /// Feet, base frame.
    pub at: [f32; 3],
    /// Degrees about up; 0 looks out of the front door (+Z), 90 toward +X.
    #[serde(default)]
    pub facing: f32,
    /// A round to walk, after `at`; empty for a keeper who stands.
    #[serde(default)]
    pub path: Vec<[f32; 3]>,
}

/// A crew member: walks `round` (base frame) or stands at its first point.
#[derive(Component)]
pub struct Crew {
    round: Vec<Vec3>,
    facing: f32,
    /// The point being walked to, and how long to wait before setting off.
    next: usize,
    wait: f32,
    yaw: f32,
}

/// The visiting ship, a child of the base; `pad` is its landing spot in the base frame.
#[derive(Component)]
pub struct Traffic {
    pub pad: Option<Vec3>,
    /// Seconds into the round the base was spawned at, so the worlds are not in step.
    pub phase: f32,
}

/// A model node the life layer runs.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Node {
    /// Turns about a base-frame axis, rad/s.
    Spin(Vec3, f32),
    Blink(u32),
    Strobe(u32),
    Fire(u32),
    Weld(u32),
    Smoke(u32),
    Sound(Ambient),
}

/// The ambient loops a base can make (`sound` synthesizes them).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Ambient {
    Generator,
    Radio,
    Fire,
    Organ,
    Bell,
    Grinder,
    Wind,
    Hum,
    Vent,
}

impl Ambient {
    pub const ALL: [Ambient; 9] = [Ambient::Generator, Ambient::Radio, Ambient::Fire, Ambient::Organ, Ambient::Bell, Ambient::Grinder, Ambient::Wind, Ambient::Hum, Ambient::Vent];

    pub fn id(self) -> &'static str {
        ["generator", "radio", "fire", "organ", "bell", "grinder", "wind", "hum", "vent"][Self::ALL.iter().position(|a| *a == self).unwrap()]
    }
}

impl Node {
    /// What a node named `name` in a base's glb is, if the life layer runs it.
    pub fn parse(name: &str) -> Option<Node> {
        let parts: Vec<&str> = name.split('.').collect();
        let n = || parts.last().and_then(|s| s.parse::<u32>().ok());
        match parts.as_slice() {
            ["spin", axis, rpm, _] => {
                let axis = match *axis {
                    "x" => Vec3::X,
                    "y" => Vec3::Y,
                    "z" => Vec3::Z,
                    _ => return None,
                };
                Some(Node::Spin(axis, rpm.parse::<f32>().ok()? * TAU / 60.0))
            }
            ["blink", _] => n().map(Node::Blink),
            ["strobe", _] => n().map(Node::Strobe),
            ["fire", _] => n().map(Node::Fire),
            ["weld", _] => n().map(Node::Weld),
            ["smoke", _] => n().map(Node::Smoke),
            ["sound", kind, _] => Ambient::ALL.iter().find(|a| a.id() == *kind).map(|a| Node::Sound(*a)),
            _ => None,
        }
    }
}

/// A node that turns, rad/s about its own axis.
#[derive(Component)]
pub struct Spin(Vec3, f32);

/// A light the life layer drives: what it is and its steady intensity.
#[derive(Component)]
pub struct Flicker {
    kind: Node,
    seed: f32,
    peak: f32,
}

/// Puffs of smoke (or a weld's sparks) rising from a node.
#[derive(Component)]
pub struct Puffer {
    sparks: bool,
    seed: f32,
    due: f32,
}

#[derive(Component)]
struct Puff {
    age: f32,
    life: f32,
    vel: Vec3,
    grow: f32,
    sparks: bool,
}

/// A looping sound placed in a base; `sound` starts it when the camera is near.
#[derive(Component)]
pub struct Emitter {
    pub kind: Ambient,
    /// The playing loop's entity, while one plays.
    pub playing: Option<Entity>,
    /// Bells: seconds to the next toll.
    pub next: f32,
}

/// Shared meshes and materials for puffs; absent in headless tests.
#[derive(Resource)]
struct PuffAssets {
    mesh: Handle<Mesh>,
    smoke: Handle<StandardMaterial>,
    spark: Handle<StandardMaterial>,
}

pub fn build(app: &mut App) {
    app.add_systems(Startup, puff_assets).add_systems(Update, (spin, flicker, puff, walk, fly));
}

fn puff_assets(mut commands: Commands, meshes: Option<ResMut<Assets<Mesh>>>, materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    commands.insert_resource(PuffAssets {
        mesh: meshes.add(Sphere::new(0.5).mesh().ico(1).unwrap()),
        smoke: materials.add(StandardMaterial { base_color: Color::srgba(0.42, 0.4, 0.38, 0.32), alpha_mode: AlphaMode::Blend, perceptual_roughness: 1.0, ..default() }),
        spark: materials.add(StandardMaterial { base_color: Color::LinearRgba(LinearRgba::new(6.0, 4.0, 1.6, 1.0)), alpha_mode: AlphaMode::Add, unlit: true, ..default() }),
    });
}

/// The crew and the visitor of base `spec`, under its entity: `pad` is its pad's top (base frame).
pub fn spawn(world: &mut World, base: Entity, crew: &[CrewSpec], traffic: Option<&str>, pad: Option<Vec3>, phase: f32) {
    let scale = world.get_resource::<Tuning>().map_or(1.0, |t| t.stand_height / character::MODEL_HEIGHT);
    for c in crew {
        let round: Vec<Vec3> = std::iter::once(c.at).chain(c.path.iter().copied()).map(Vec3::from).collect();
        let yaw = c.facing.to_radians();
        let tf = Transform::from_translation(round[0]).with_rotation(Quat::from_rotation_y(yaw)).with_scale(Vec3::splat(scale));
        let e = world.spawn((Name::new(format!("Crew {}", c.character)), Crew { next: 1 % round.len(), wait: PAUSE_SECS, round, facing: yaw, yaw }, character::bundle(&c.character, tf))).id();
        world.entity_mut(base).add_child(e);
    }
    if let Some(ship) = traffic {
        // The hull's origin stands this high over its skids.
        let rest = world.get_resource::<super::ship::Ships>().and_then(|s| s.ship.iter().find(|s| s.id == ship)).map_or(0.0, |s| s.rest);
        let pad = pad.map(|p| p + Vec3::Y * rest);
        let e = world.spawn((Name::new(format!("Visiting {ship}")), Traffic { pad, phase }, Transform::default(), Visibility::Hidden)).id();
        world.entity_mut(base).add_child(e);
        if world.contains_resource::<AssetServer>() {
            world.entity_mut(e).insert(super::base::Pending(format!("models/ships/{ship}.glb")));
        }
    }
}

/// Once a base's glb is in: what its life-layer nodes become.
pub fn dress(commands: &mut Commands, e: Entity, name: &str) {
    let Some(node) = Node::parse(name) else { return };
    let seed = name.bytes().fold(7.0_f32, |a, b| (a * 31.0 + b as f32) % 997.0);
    let light = |color: Color, range: f32| PointLight { color, intensity: 0.0, range, radius: 0.1, shadow_maps_enabled: false, ..default() };
    match node {
        Node::Spin(axis, rate) => {
            commands.entity(e).insert(Spin(axis, rate));
        }
        Node::Blink(_) => {
            commands.entity(e).insert((light(Color::srgb(1.0, 0.15, 0.1), 18.0), Flicker { kind: node, seed, peak: 4.0e5 }));
        }
        Node::Strobe(_) => {
            commands.entity(e).insert((light(Color::srgb(0.95, 0.97, 1.0), 30.0), Flicker { kind: node, seed, peak: 3.0e6 }));
        }
        Node::Fire(_) => {
            commands.entity(e).insert((light(Color::srgb(1.0, 0.55, 0.2), 12.0), Flicker { kind: node, seed, peak: 9.0e5 }));
        }
        Node::Weld(_) => {
            commands.entity(e).insert((light(Color::srgb(0.7, 0.85, 1.0), 10.0), Flicker { kind: node, seed, peak: 1.2e6 }, Puffer { sparks: true, seed, due: 0.0 }));
        }
        Node::Smoke(_) => {
            commands.entity(e).insert(Puffer { sparks: false, seed, due: 0.0 });
        }
        Node::Sound(kind) => {
            commands.entity(e).insert(Emitter { kind, playing: None, next: seed % 20.0 });
        }
    }
}

fn spin(time: Res<Time>, mut parts: Query<(&mut Transform, &Spin)>) {
    for (mut tf, s) in &mut parts {
        tf.rotate_local(Quat::from_axis_angle(s.0, s.1 * time.delta_secs()));
    }
}

/// Smooth noise in 0..1 from a few sines.
fn wobble(t: f32, seed: f32) -> f32 {
    0.5 + 0.22 * (t * 7.3 + seed).sin() + 0.16 * (t * 13.1 + seed * 1.7).sin() + 0.12 * (t * 23.7 + seed * 2.3).sin()
}

/// How bright a life light is at time `t`, 0..1.
pub fn level(kind: Node, t: f32, seed: f32) -> f32 {
    match kind {
        // A one-second beat; numbered beacons fire in turn, so a row of them chases.
        Node::Blink(n) => {
            let p = (t - n as f32 * 0.12).fract();
            if p < 0.18 { 1.0 } else { 0.0 }
        }
        Node::Strobe(n) => {
            let p = ((t + n as f32 * 0.11) / 1.5).fract();
            if p < 0.04 { 1.0 } else { 0.0 }
        }
        Node::Fire(_) => 0.65 + 0.35 * wobble(t, seed),
        // A few seconds of crackling arc, a few seconds dark.
        Node::Weld(_) => {
            let p = ((t + seed) / 7.0).fract();
            if p < 0.45 && wobble(t * 3.0, seed) > 0.42 { 0.6 + 0.4 * wobble(t * 5.0, seed + 1.0) } else { 0.0 }
        }
        _ => 0.0,
    }
}

fn flicker(time: Res<Time>, mut lights: Query<(&mut PointLight, &Flicker)>) {
    let t = time.elapsed_secs();
    for (mut light, f) in &mut lights {
        let want = f.peak * level(f.kind, t, f.seed);
        if light.intensity != want {
            light.intensity = want;
        }
    }
}

/// Smoke rises, swells and thins; sparks fly out and fall, only while a weld burns.
#[allow(clippy::type_complexity)]
fn puff(
    mut commands: Commands,
    time: Res<Time>,
    assets: Option<Res<PuffAssets>>,
    camera: Query<&GlobalTransform, With<PlayerCamera>>,
    mut puffers: Query<(Entity, &mut Puffer, &GlobalTransform)>,
    mut puffs: Query<(Entity, &mut Puff, &mut Transform)>,
) {
    let dt = time.delta_secs();
    for (e, mut p, mut tf) in &mut puffs {
        p.age += dt;
        if p.age >= p.life {
            commands.entity(e).despawn();
            continue;
        }
        if p.sparks {
            p.vel.y -= 9.0 * dt;
        }
        tf.translation += p.vel * dt;
        let k = p.age / p.life;
        tf.scale = Vec3::splat(if p.sparks { 0.05 * (1.0 - k) } else { 0.4 + p.grow * k.sqrt() } * if p.sparks { 1.0 } else { (1.0 - k * k).max(0.05) });
    }
    let Some(assets) = assets else { return };
    let Some(eye) = camera.iter().next().map(|c| c.translation()) else { return };
    let t = time.elapsed_secs();
    for (e, mut p, at) in &mut puffers {
        // Nobody sees smoke from a kilometre off.
        if at.translation().distance(eye) > 250.0 {
            continue;
        }
        p.due -= dt;
        if p.due > 0.0 {
            continue;
        }
        let seed = p.seed;
        let r = |k: f32| ((t * 91.7 + seed * k).sin() * 43758.5).fract();
        if p.sparks {
            p.due = 0.05;
            if level(Node::Weld(0), t, seed) <= 0.0 {
                continue;
            }
            for i in 0..3 {
                let a = r(1.0 + i as f32) * TAU;
                let vel = Vec3::new(a.cos() * 2.5, 1.5 + 2.0 * r(3.0 + i as f32), a.sin() * 2.5);
                let s = commands.spawn((Puff { age: 0.0, life: 0.5 + 0.4 * r(5.0), vel, grow: 0.0, sparks: true }, Mesh3d(assets.mesh.clone()), MeshMaterial3d(assets.spark.clone()), Transform::from_scale(Vec3::splat(0.05)), bevy::light::NotShadowCaster)).id();
                commands.entity(e).add_child(s);
            }
        } else {
            p.due = 0.45 + 0.3 * r(2.0);
            let vel = Vec3::new(0.3 * (r(7.0) - 0.5), 1.1 + 0.4 * r(8.0), 0.3 * (r(9.0) - 0.5));
            let s = commands.spawn((Puff { age: 0.0, life: 5.0 + 2.0 * r(4.0), vel, grow: 1.6, sparks: false }, Mesh3d(assets.mesh.clone()), MeshMaterial3d(assets.smoke.clone()), Transform::from_scale(Vec3::splat(0.4)), bevy::light::NotShadowCaster)).id();
            commands.entity(e).add_child(s);
        }
    }
}

/// Walkers walk their rounds and stop at each point; keepers turn to whoever comes up to them.
fn walk(time: Res<Time>, camera: Query<&GlobalTransform, With<PlayerCamera>>, parents: Query<&GlobalTransform, Without<Crew>>, mut crew: Query<(&mut Crew, &mut Transform, &mut RigPose, &ChildOf)>) {
    let dt = time.delta_secs();
    let eye = camera.iter().next().map(|c| c.translation());
    for (mut c, mut tf, mut pose, parent) in &mut crew {
        let mut want = c.facing;
        let mut moving = false;
        if c.round.len() > 1 {
            if c.wait > 0.0 {
                c.wait -= dt;
            } else {
                let to = c.round[c.next];
                let d = (to - tf.translation).with_y(0.0);
                let step = WALK_SPEED * dt;
                if d.length() <= step {
                    tf.translation = to;
                    c.next = (c.next + 1) % c.round.len();
                    c.wait = PAUSE_SECS;
                } else {
                    tf.translation += d.normalize() * step;
                    tf.translation.y = to.y;
                    want = d.x.atan2(d.z);
                    c.facing = want;
                    moving = true;
                }
            }
        }
        if !moving {
            // Turn to the player standing close by.
            if let (Some(eye), Ok(base)) = (eye, parents.get(parent.parent())) {
                let local = base.affine().inverse().transform_point3(eye) - tf.translation;
                if local.with_y(0.0).length() < GREET_RADIUS {
                    want = local.x.atan2(local.z);
                }
            }
        }
        let diff = (want - c.yaw + PI).rem_euclid(TAU) - PI;
        c.yaw += diff.clamp(-TURN_RATE * dt, TURN_RATE * dt);
        tf.rotation = Quat::from_rotation_y(c.yaw);
        let next = if moving { RigPose::new(Pose::Walk, crate::body::playback_rate(Pose::Walk, WALK_SPEED, WALK_SPEED)) } else { RigPose::default() };
        if *pose != next {
            *pose = next;
        }
    }
}

/// Where the visitor is `t` seconds into its round, relative to its pad (or the base, passing
/// over one with no pad), nose along -Z: `None` while it is away.
pub fn traffic_pose(t: f32, pad: bool) -> Option<(Vec3, Quat)> {
    let t = t.rem_euclid(TRAFFIC_CYCLE);
    // It comes in from the south-west, nose toward the pad, and leaves to the north-east.
    let dir_in = Vec3::new(-0.6, 0.0, 0.8).normalize();
    let dir_out = Vec3::new(0.7, 0.0, -0.7).normalize();
    let ease = |k: f32| k * k * (3.0 - 2.0 * k);
    let facing = |d: Vec3| Quat::from_rotation_arc(Vec3::NEG_Z, d.normalize());
    if !pad {
        // A pass straight over, low and level.
        let k = t / (APPROACH + DEPART);
        return (k < 1.0).then(|| (dir_in * FAR * (1.0 - 2.0 * k) + Vec3::Y * PASS, facing(-dir_in)));
    }
    let mut t = t;
    if t < APPROACH {
        // Slowing all the way in: the far end of the run in, then the hover over the pad.
        let k = 1.0 - (1.0 - t / APPROACH).powi(2);
        let at = dir_in * FAR * (1.0 - k) + Vec3::Y * (HIGH + (HOVER - HIGH) * k);
        return Some((at, facing(-dir_in)));
    }
    t -= APPROACH;
    if t < SETTLE {
        return Some((Vec3::Y * HOVER * (1.0 - ease(t / SETTLE)), facing(-dir_in)));
    }
    t -= SETTLE;
    // Sitting, it turns its nose round for the way out.
    if t < SIT {
        return Some((Vec3::ZERO, facing(-dir_in).slerp(facing(dir_out), ease((t / SIT).min(1.0)))));
    }
    t -= SIT;
    if t < LIFT {
        return Some((Vec3::Y * HOVER * ease(t / LIFT), facing(dir_out)));
    }
    t -= LIFT;
    if t < DEPART {
        let k = (t / DEPART).powi(2);
        return Some((dir_out * FAR * k + Vec3::Y * (HOVER + (HIGH - HOVER) * k), facing(dir_out)));
    }
    None
}

fn fly(time: Res<Time>, mut ships: Query<(&Traffic, &mut Transform, &mut Visibility)>) {
    let t = time.elapsed_secs();
    for (traffic, mut tf, mut vis) in &mut ships {
        let want = match traffic_pose(t + traffic.phase, traffic.pad.is_some()) {
            Some((at, rot)) => {
                tf.translation = traffic.pad.unwrap_or_default() + at;
                tf.rotation = rot;
                Visibility::Inherited
            }
            None => Visibility::Hidden,
        };
        if *vis != want {
            *vis = want;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn node_names_parse_to_what_they_do() {
        assert_eq!(Node::parse("spin.y.-6.0"), Some(Node::Spin(Vec3::Y, -6.0 * TAU / 60.0)));
        assert_eq!(Node::parse("blink.3"), Some(Node::Blink(3)));
        assert_eq!(Node::parse("sound.organ.1"), Some(Node::Sound(Ambient::Organ)));
        assert_eq!(Node::parse("sound.kazoo.1"), None);
        assert_eq!(Node::parse("lamp.0"), None);
        assert_eq!(Node::parse("spin.q.6.0"), None);
    }

    #[test]
    fn the_visitor_lands_on_the_pad_sits_and_leaves() {
        assert!(traffic_pose(1.0, true).unwrap().0.y > 100.0, "it comes in high");
        let (sat, _) = traffic_pose(APPROACH + SETTLE + SIT / 2.0, true).unwrap();
        assert!(sat.length() < 1e-3, "it sits on the pad");
        let gone = APPROACH + SETTLE + SIT + LIFT + DEPART + 1.0;
        assert!(traffic_pose(gone, true).is_none() && traffic_pose(gone + TRAFFIC_CYCLE, true).is_none());
        // It never jumps: a tenth of a second apart, it has moved a few metres at most.
        let mut last = traffic_pose(0.0, true).unwrap().0;
        for i in 1..1000 {
            let Some((at, _)) = traffic_pose(i as f32 * 0.1, true) else { break };
            assert!(at.distance(last) < 4.0, "smooth at {}", i as f32 * 0.1);
            last = at;
        }
        assert!(traffic_pose(10.0, false).is_some_and(|(at, _)| at.y == PASS));
    }

    #[test]
    fn beacons_blink_and_fires_never_go_out() {
        let lit = (0..100).filter(|i| level(Node::Blink(0), *i as f32 * 0.01, 0.0) > 0.0).count();
        assert!((10..30).contains(&lit), "on about a fifth of each second");
        assert!((0..500).all(|i| level(Node::Fire(0), i as f32 * 0.037, 3.0) > 0.2));
    }
}
