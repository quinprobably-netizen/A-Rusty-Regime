//! Homing missiles, stage 1 of ship combat (section 3 of
//! `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`). Every ship with guns also
//! carries `[ship_combat] missiles` of them and gets one back every `missile_reload` seconds.
//! Hold a ship of another side within `lock_cone` degrees of the nose for `lock_time` and it is
//! locked; let it leave the cone and the lock is gone. The missile trigger
//! (`ShipControls::missile`: the right mouse button for the player) fires one at the locked ship,
//! or straight ahead with no lock, on each press.
//!
//! A missile flies where it points. It leaves at the launcher's speed and gains speed until it
//! is `missile_speed` faster, steering by proportional navigation, a moment behind it
//! (`missile_lag`), and turning no faster than `missile_turn`, so a hard enough turn outturns it. Once the target is more than
//! `missile_seeker` degrees off its nose it has lost it and flies straight on. It bursts on
//! anything it touches, on the ground, within `missile_fuse` metres of its target, or after
//! `missile_life` seconds. A hit takes `missile_damage` off the ship it reaches, shield first,
//! as a shot does, and never off its own side.
//!
//! The lock (`Missiles`) is on the ship, for the HUD to read. An enemy pilot whose `ai` says
//! `missiles = true` locks and fires through its own stick (`ai`). A missile is a plain root
//! entity in the anchor's frame: the origin rebase moves it with every other root, and a handoff
//! to another world's frame converts it like a ship (`carry`, from `switch_anchor`). Its target
//! is an entity, so nothing about where that is has to be converted.

use avian3d::prelude::*;
use bevy::prelude::*;

use super::combat::{Faction, Hull, ShotLanded};
use super::ship::{clearance, Autopilot, Ship, ShipControls, Ships};
use super::Solar;
use crate::surface::{Origin, Surface};
use crate::tuning::{ShipCombat, Tuning};
use crate::weapon::{spawn_blast, FxAssets};

/// A ship's missiles and its lock.
#[derive(Component, Debug, Clone)]
pub struct Missiles {
    /// Missiles left, up to `[ship_combat] missiles`.
    pub count: u32,
    /// Seconds toward the next one coming back.
    pub reload: f32,
    /// The ship in the cone, and how far the lock on it has come, 0 to 1 (1: locked).
    pub target: Option<Entity>,
    pub lock: f32,
    /// Seconds since the last launch.
    pub since: f32,
    /// The trigger as it was last tick: a missile goes on each press, not while held.
    held: bool,
}

impl Missiles {
    pub fn new(count: u32) -> Self {
        Self { count, reload: 0.0, target: None, lock: 0.0, since: f32::MAX, held: false }
    }

    /// The ship it is locked on, if the lock is complete.
    pub fn locked(&self) -> Option<Entity> {
        self.target.filter(|_| self.lock >= 1.0)
    }
}

/// A missile in flight, in the anchor's frame. It points along its `Transform`'s -Z.
#[derive(Component, Debug)]
pub struct Missile {
    /// Along its nose, m/s, and the most it will reach.
    pub speed: f32,
    pub top: f32,
    /// Seconds before it bursts on its own.
    pub life: f32,
    pub owner: Entity,
    pub faction: Faction,
    /// What it homes on; none flies straight.
    pub target: Option<Entity>,
    /// Seconds to the next puff of smoke.
    puff: f32,
    /// How fast it is turning, rad/s about an axis: it follows the guidance a moment behind.
    spin: Vec3,
}

impl Missile {
    /// A missile off `owner`'s rail at `speed`, burning up to `top`.
    pub fn new(speed: f32, top: f32, owner: Entity, faction: Faction, target: Option<Entity>, t: &ShipCombat) -> Self {
        Self { speed, top, life: t.missile_life, owner, faction, target, puff: 0.0, spin: Vec3::ZERO }
    }
}

/// A puff of the smoke trail: it swells and fades.
#[derive(Component)]
struct Puff {
    age: f32,
}

/// How long a puff lasts, how often a missile leaves one and how big it gets.
const PUFF_LIFE: f32 = 1.4;
const PUFF_EVERY: f32 = 0.03;
const PUFF_SIZE: f32 = 2.4;
/// How big a missile's burst is, metres.
const BLAST: f32 = 7.0;

/// What every missile looks like: a grey body, its flame and its smoke.
#[derive(Resource)]
struct MissileLook {
    body: Handle<Mesh>,
    body_material: Handle<StandardMaterial>,
    flame: Handle<Mesh>,
    flame_material: Handle<StandardMaterial>,
    puff: Handle<Mesh>,
    puff_material: Handle<StandardMaterial>,
}

pub fn build(app: &mut App) {
    app.add_observer(arm)
        .add_systems(Startup, load_look)
        .add_systems(Update, smoke)
        .add_systems(FixedUpdate, (lock, launch, fly_missiles).chain().after(crate::controller::ControllerSet).before(super::combat::wreck));
}

fn load_look(mut commands: Commands, meshes: Option<ResMut<Assets<Mesh>>>, materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    commands.insert_resource(MissileLook {
        body: meshes.add(Cuboid::new(0.35, 0.35, 2.4)),
        body_material: materials.add(StandardMaterial { base_color: Color::srgb(0.55, 0.56, 0.58), metallic: 0.6, perceptual_roughness: 0.4, ..default() }),
        flame: meshes.add(Cuboid::new(0.5, 0.5, 1.6)),
        flame_material: materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.7, 0.3), emissive: LinearRgba::rgb(40.0, 16.0, 3.0), unlit: true, ..default() }),
        puff: meshes.add(Sphere::new(0.5)),
        puff_material: materials.add(StandardMaterial { base_color: Color::srgba(0.85, 0.85, 0.85, 0.55), alpha_mode: AlphaMode::Blend, perceptual_roughness: 1.0, ..default() }),
    });
}

/// Every ship with guns carries missiles too.
fn arm(add: On<Add, Ship>, mut commands: Commands, ships: Query<&Ship>, specs: Res<Ships>, tuning: Res<Tuning>) {
    let Ok(ship) = ships.get(add.entity) else { return };
    if !specs.ship[ship.spec].guns.is_empty() {
        commands.entity(add.entity).insert(Missiles::new(tuning.ship_combat.missiles));
    }
}

/// Reloads each ship's missiles and keeps its lock: the ship of another side nearest its nose
/// within the cone and range starts a lock, which grows while it stays there and is gone once it
/// leaves. An enemy pilot locks only on a ship someone flies, the one it hunts.
#[allow(clippy::type_complexity)]
fn lock(
    time: Res<Time>,
    tuning: Res<Tuning>,
    mut ships: Query<(Entity, &mut Missiles, &Faction, &Position, &Rotation, Has<Autopilot>)>,
    targets: Query<(Entity, &Ship, &Faction, &Position), With<Hull>>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    for (me, mut m, faction, pos, rot, autopilot) in &mut ships {
        if m.count < t.missiles {
            m.reload += dt;
            if m.reload >= t.missile_reload {
                m.reload = 0.0;
                m.count += 1;
            }
        } else {
            m.count = t.missiles;
            m.reload = 0.0;
        }
        m.since = (m.since + dt).min(1e6);
        let nose = rot.0 * Vec3::NEG_Z;
        // How far off the nose each ship it could lock is, radians.
        let off = |e: Entity| {
            let (_, ship, f, p) = targets.get(e).ok()?;
            let rel = p.0 - pos.0;
            let ok = e != me && f != faction && (!autopilot || ship.pilot.is_some()) && rel.length() < t.lock_range;
            let angle = nose.angle_between(rel);
            (ok && angle < t.lock_cone.to_radians()).then_some(angle)
        };
        if m.target.and_then(off).is_some() {
            m.lock = (m.lock + dt / t.lock_time).min(1.0);
            continue;
        }
        m.target = targets.iter().filter_map(|(e, ..)| off(e).map(|a| (e, a))).min_by(|a, b| a.1.total_cmp(&b.1)).map(|(e, _)| e);
        m.lock = 0.0;
    }
}

/// Each press of a ship's missile trigger sends one off its rail, at the locked ship or straight
/// ahead, while it has any left.
#[allow(clippy::type_complexity)]
fn launch(
    mut commands: Commands,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    mut ships: Query<(Entity, &Ship, &ShipControls, &mut Missiles, &Faction, &Position, &Rotation, &LinearVelocity)>,
) {
    let t = &tuning.ship_combat;
    for (entity, ship, controls, mut m, faction, pos, rot, v) in &mut ships {
        let pressed = controls.missile && !m.held;
        m.held = controls.missile;
        if !pressed || m.count == 0 {
            continue;
        }
        m.count -= 1;
        m.since = 0.0;
        debug!("{} fires a missile{}", specs.ship[ship.spec].name, if m.locked().is_some() { " with a lock" } else { "" });
        // Under the nose, between the guns.
        let guns = &specs.ship[ship.spec].guns;
        let rail = guns.iter().map(|g| Vec3::from(*g)).sum::<Vec3>() / guns.len().max(1) as f32 + Vec3::NEG_Y * 0.6;
        let ahead = v.0.dot(rot.0 * Vec3::NEG_Z).max(0.0);
        let missile = Missile::new(ahead + t.missile_kick, ahead + t.missile_speed, entity, *faction, m.locked(), t);
        let at = Transform::from_translation(pos.0 + rot.0 * rail).with_rotation(rot.0);
        commands.queue(move |world: &mut World| {
            spawn(world, missile, at);
        });
    }
}

/// Puts missile `missile` in the world at `at`, pointing along its -Z.
pub fn spawn(world: &mut World, missile: Missile, at: Transform) -> Entity {
    let e = world.spawn((Name::new("Missile"), missile, at, Visibility::default())).id();
    let Some(look) = world.get_resource::<MissileLook>() else { return e };
    let (body, flame) = ((Mesh3d(look.body.clone()), MeshMaterial3d(look.body_material.clone())), (Mesh3d(look.flame.clone()), MeshMaterial3d(look.flame_material.clone())));
    world.entity_mut(e).insert(body).with_child((flame, Transform::from_xyz(0.0, 0.0, 1.9), bevy::light::NotShadowCaster));
    e
}

/// The turn rate (rad/s, about an axis) that proportional navigation asks of a missile at `p`
/// flying `v` to close on a target `rel` away moving at `target_v`, with gain `nav`: it turns
/// the missile so the line of sight to the target stops swinging, and they meet.
pub fn navigate(rel: Vec3, v: Vec3, target_v: Vec3, nav: f32) -> Vec3 {
    let speed = v.length();
    if speed < 1e-3 || rel.length_squared() < 1e-3 {
        return Vec3::ZERO;
    }
    // How fast the line of sight turns, and the sideways pull that answers it.
    let sight = rel.cross(target_v - v) / rel.length_squared();
    let pull = sight.cross(v) * nav;
    let heading = v / speed;
    let pull = pull - heading * pull.dot(heading);
    heading.cross(pull) / speed
}

/// A missile's hit on `hull`: its damage, shield first, the same path as a shot. `by` is the ship
/// that fired it, which `Hull` records so the kill is put down to it (the bounty goes to the
/// player when it was the player's ship).
fn strike(hull: &mut Hull, by: Entity, t: &ShipCombat) {
    hull.hit_by(t.missile_damage, by, t);
}

/// Flies every missile one tick: speeds it up, homes it, and bursts it on whatever it reaches.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn fly_missiles(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    spatial: SpatialQuery,
    look: Option<Res<MissileLook>>,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut missiles: Query<(Entity, &mut Missile, &mut Transform)>,
    targets: Query<(&Ship, &Position, &LinearVelocity)>,
    bodies: Query<&ColliderOf>,
    mut hulls: Query<(&mut Hull, &Faction)>,
    mut landed: MessageWriter<ShotLanded>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    for (entity, mut m, mut tf) in &mut missiles {
        let p = tf.translation;
        let mut burst = |commands: &mut Commands, at: Vec3| {
            if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                spawn_blast(commands, fx, materials, at, BLAST);
            }
            commands.entity(entity).despawn();
        };
        m.life -= dt;
        if m.life <= 0.0 {
            burst(&mut commands, p);
            continue;
        }
        if m.speed < m.top {
            m.speed = (m.speed + t.missile_accel * dt).min(m.top);
        }
        let heading = tf.rotation * Vec3::NEG_Z;
        // Its target, while it still sees it.
        let seen = m.target.and_then(|e| targets.get(e).ok()).map(|(_, tp, tv)| (tp.0, tv.0)).filter(|(tp, _)| heading.angle_between(*tp - p) < t.missile_seeker.to_radians());
        if seen.is_none() {
            m.target = None;
        }
        let want = seen.map_or(Vec3::ZERO, |(tp, tv)| navigate(tp - p, heading * m.speed, tv, t.missile_nav));
        // It answers the guidance `missile_lag` seconds behind, as a real airframe does: a target
        // that breaks hard enough, late enough, is gone before it has come round.
        let k = if t.missile_lag > 0.0 { 1.0 - (-dt / t.missile_lag).exp() } else { 1.0 };
        let spin = (m.spin + (want - m.spin) * k).clamp_length_max(t.missile_turn);
        m.spin = spin;
        let rate = spin.length();
        if rate > 1e-6 {
            tf.rotation = (Quat::from_axis_angle(spin / rate, rate * dt) * tf.rotation).normalize();
        }
        let dir = tf.rotation * Vec3::NEG_Z;
        let step = dir * m.speed * dt;
        // Whatever it touches first along the step, then its target close by, then the ground.
        let filter = SpatialQueryFilter::from_excluded_entities([m.owner]);
        if let Some(hit) = Dir3::new(dir).ok().and_then(|d| spatial.cast_ray(p, d, step.length(), true, &filter)) {
            let body = bodies.get(hit.entity).map_or(hit.entity, |c| c.body);
            if body != m.owner
                && let Ok((mut hull, faction)) = hulls.get_mut(body)
                && *faction != m.faction
            {
                strike(&mut hull, m.owner, t);
                landed.write(ShotLanded { by: m.owner, on: body });
                if let Ok((ship, ..)) = targets.get(body) {
                    info!("missile hit the {}", specs.ship[ship.spec].name);
                }
            }
            burst(&mut commands, p + dir * hit.distance);
            continue;
        }
        if let (Some(target), Some((tp, tv))) = (m.target, seen) {
            // Closest approach over the tick, moving with the target.
            let (rel, d) = (tp - p, step - tv * dt);
            let k = (rel.dot(d) / d.length_squared().max(1e-6)).clamp(0.0, 1.0);
            if (rel - d * k).length() < t.missile_fuse {
                if let Ok((mut hull, faction)) = hulls.get_mut(target)
                    && *faction != m.faction
                {
                    strike(&mut hull, m.owner, t);
                    landed.write(ShotLanded { by: m.owner, on: target });
                    if let Ok((ship, ..)) = targets.get(target) {
                        info!("missile hit the {}", specs.ship[ship.spec].name);
                    }
                }
                burst(&mut commands, p + step * k);
                continue;
            }
        }
        // Out past the physics bubble there is no ground collider: the height map says.
        if clearance(&solar, &surface, origin.body(p + step)) <= 0.0 {
            burst(&mut commands, p + step);
            continue;
        }
        tf.translation = p + step;
        m.puff -= dt;
        if let Some(look) = look.as_ref().filter(|_| m.puff <= 0.0) {
            m.puff = PUFF_EVERY;
            commands.spawn((Puff { age: 0.0 }, Mesh3d(look.puff.clone()), MeshMaterial3d(look.puff_material.clone()), Transform::from_translation(p).with_scale(Vec3::splat(0.5)), bevy::light::NotShadowCaster));
        }
    }
}

/// The smoke swells and thins away. It is left behind in the old world's frame at a handoff, so
/// then it goes at once.
fn smoke(mut commands: Commands, time: Res<Time>, solar: Res<Solar>, mut anchor: Local<String>, mut puffs: Query<(Entity, &mut Puff, &mut Transform)>) {
    let handoff = *anchor != solar.anchor;
    anchor.clone_from(&solar.anchor);
    for (e, mut puff, mut tf) in &mut puffs {
        if handoff {
            commands.entity(e).despawn();
            continue;
        }
        puff.age += time.delta_secs();
        let k = puff.age / PUFF_LIFE;
        if k >= 1.0 {
            commands.entity(e).despawn();
            continue;
        }
        tf.scale = Vec3::splat(PUFF_SIZE * (0.3 + k.sqrt()) * (1.0 - k * k));
    }
}

/// At a handoff to another world's frame, every missile is carried into it like a ship:
/// `convert` takes a body position and velocity in the old frame to the new, `turn` turns the old
/// frame's axes to the new one's, and the origins place it. It burns on to the same speed over
/// the launcher's as before.
pub fn carry(world: &mut World, old: &Origin, new: &Origin, turn: Quat, convert: impl Fn(Vec3, Vec3) -> (Vec3, Vec3)) {
    let missiles: Vec<Entity> = world.query_filtered::<Entity, With<Missile>>().iter(world).collect();
    for e in missiles {
        let Ok(mut entity) = world.get_entity_mut(e) else { continue };
        let Some(tf) = entity.get::<Transform>().copied() else { continue };
        let Some(mut m) = entity.get_mut::<Missile>() else { continue };
        let (p, v) = convert(old.body(tf.translation), tf.rotation * Vec3::NEG_Z * m.speed);
        let up = turn * tf.rotation * Vec3::Y;
        let rotation = match v.try_normalize() {
            Some(dir) => Transform::default().looking_to(dir, up).rotation,
            None => (turn * tf.rotation).normalize(),
        };
        let speed = v.length();
        m.top += speed - m.speed;
        m.speed = speed;
        entity.insert(Transform { translation: new.world(p), rotation, ..tf });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn navigation_turns_toward_where_a_crossing_target_will_be() {
        // Dead ahead and still: no turn. Crossing to the right: turn right, ahead of it.
        assert_eq!(navigate(Vec3::NEG_Z * 1000.0, Vec3::NEG_Z * 600.0, Vec3::ZERO, 4.0), Vec3::ZERO);
        let turn = navigate(Vec3::NEG_Z * 1000.0, Vec3::NEG_Z * 600.0, Vec3::X * 200.0, 4.0);
        let heading = Quat::from_axis_angle(turn.normalize(), 0.1) * Vec3::NEG_Z;
        assert!(heading.x > 0.0, "turns toward the target's way: {heading}");
        // Four times the sight line's swing, 200/1000 rad/s, as a turn of the nose.
        assert!((turn.length() - 4.0 * 0.2).abs() < 1e-4, "{}", turn.length());
    }
}
