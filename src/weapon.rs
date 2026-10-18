//! Weapons: a rocket launcher (slow projectile, splash knockback for rocket
//! jumps) and three hitscan guns. Hits push props and damage targets.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::{ControllerSet, MoveState, Player};
use crate::input::{PlayerInput, Rumble, ViewAngles};
use crate::tuning::{Gun, Tuning};

pub struct WeaponPlugin;

impl Plugin for WeaponPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<Rumble>()
            .add_message::<Damage>()
            .add_message::<WeaponFired>()
            .init_resource::<Arsenal>()
            .init_resource::<crate::gunsmith::Loadout>()
            .add_systems(Startup, load_assets)
            .init_resource::<Recoil>()
            .init_resource::<Aim>()
            .add_systems(FixedUpdate, (switch_weapon, fire, fly_rockets, fly_bullets).chain().before(ControllerSet))
            .add_systems(Update, (fade_explosions, fade_tracers, recoil, aim));
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum WeaponKind {
    RocketLauncher,
    Rifle,
    Shotgun,
    Pistol,
}

pub const WEAPONS: [WeaponKind; 4] = [WeaponKind::RocketLauncher, WeaponKind::Rifle, WeaponKind::Shotgun, WeaponKind::Pistol];

impl WeaponKind {
    pub fn name(self) -> &'static str {
        match self {
            WeaponKind::RocketLauncher => "ROCKET LAUNCHER",
            WeaponKind::Rifle => "RIFLE",
            WeaponKind::Shotgun => "SHOTGUN",
            WeaponKind::Pistol => "PISTOL",
        }
    }
    /// The gun's tuning with the gunsmith's parts fitted; `None` for the rocket launcher.
    fn gun(self, t: &Tuning, loadout: &crate::gunsmith::Loadout) -> Option<Gun> {
        t.gun(self).map(|g| loadout.gun(self, g))
    }
}

/// Seconds a weapon swap takes; you can't fire while the new gun is raised.
pub const SWITCH_TIME: f32 = 0.25;

#[derive(Resource, Debug)]
pub struct Arsenal {
    pub current: usize,
    pub last: usize,
    pub cooldown: f32,
    /// Counts down after a swap.
    pub switch_time: f32,
    pub shots: u32,
}

impl Default for Arsenal {
    fn default() -> Self {
        Self { current: 0, last: 1, cooldown: 0.0, switch_time: 0.0, shots: 0 }
    }
}

impl Arsenal {
    pub fn kind(&self) -> WeaponKind {
        WEAPONS[self.current]
    }
    pub fn select(&mut self, slot: usize) {
        if slot < WEAPONS.len() && slot != self.current {
            self.last = self.current;
            self.current = slot;
            self.switch_time = SWITCH_TIME;
        }
    }
}

/// Something took a hit. `targets` turns this into health loss.
#[derive(Message)]
pub struct Damage {
    pub entity: Entity,
    pub amount: f32,
    pub impulse: Vec3,
}

/// The current weapon just fired; the viewmodel kicks back by `kick`.
#[derive(Message)]
pub struct WeaponFired {
    pub kick: f32,
}

/// A bullet in flight: it drops under 9.81 m/s², slows by `drag` per metre, and does
/// `damage` times its remaining energy (the square of its speed over its muzzle speed).
#[derive(Component, Debug)]
pub struct Bullet {
    pub velocity: Vec3,
    pub muzzle: f32,
    pub damage: f32,
    pub impulse: f32,
    pub drag: f32,
    pub owner: Entity,
    pub age: f32,
    pub through: u8,
}

/// Thin cover a bullet can go through, losing `cost` of its energy (0..1).
#[derive(Component, Debug, Clone, Copy)]
pub struct Penetrable {
    pub cost: f32,
}

/// View kick from firing: `pending` is still to apply, `applied` pulls back toward zero.
#[derive(Resource, Debug, Default)]
pub struct Recoil {
    pub pending: Vec2,
    pub applied: Vec2,
    pub since_shot: f32,
    /// Sustained-fire heat, 0..1, widening the spread.
    pub heat: f32,
}

/// Aim down sights: 0 from the hip, 1 fully aimed.
#[derive(Resource, Debug, Default)]
pub struct Aim {
    pub level: f32,
}

/// Fire one bullet from `from` along `dir` (unit).
pub fn spawn_bullet(commands: &mut Commands, fx: Option<&FxAssets>, from: Vec3, dir: Vec3, gun: &Gun, owner: Entity) {
    let mut e = commands.spawn((
        Name::new("Bullet"),
        Bullet { velocity: dir * gun.velocity, muzzle: gun.velocity, damage: gun.damage, impulse: gun.prop_impulse, drag: gun.drag, owner, age: 0.0, through: 0 },
        Transform::from_translation(from).looking_to(dir, Vec3::Y).with_scale(Vec3::new(0.02, 0.02, 0.01)),
    ));
    if let Some(fx) = fx {
        e.insert((Mesh3d(fx.tracer_mesh.clone()), MeshMaterial3d(fx.tracer_mat.clone())));
    }
}

#[derive(Resource)]
pub struct FxAssets {
    rocket_mesh: Handle<Mesh>,
    rocket_mat: Handle<StandardMaterial>,
    blast_mesh: Handle<Mesh>,
    tracer_mesh: Handle<Mesh>,
    tracer_mat: Handle<StandardMaterial>,
}

#[derive(Component)]
struct Rocket {
    velocity: Vec3,
    life: f32,
}

/// A rocket's blast, growing then fading; `sound` listens for it appearing.
#[derive(Component)]
pub struct Explosion {
    age: f32,
    radius: f32,
    material: Handle<StandardMaterial>,
}

#[derive(Component)]
struct Tracer {
    age: f32,
}

const EXPLOSION_TIME: f32 = 0.25;
const TRACER_TIME: f32 = 0.07;

/// Mesh assets only exist with rendering; headless tests skip visuals.
fn load_assets(
    mut commands: Commands,
    meshes: Option<ResMut<Assets<Mesh>>>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    commands.insert_resource(FxAssets {
        rocket_mesh: meshes.add(Sphere::new(0.12)),
        rocket_mat: materials.add(StandardMaterial {
            base_color: Color::srgb(1.0, 0.5, 0.1),
            emissive: LinearRgba::rgb(8.0, 3.0, 0.5),
            ..default()
        }),
        blast_mesh: meshes.add(Sphere::new(1.0)),
        tracer_mesh: meshes.add(Cuboid::from_length(1.0)),
        tracer_mat: materials.add(StandardMaterial {
            base_color: Color::srgba(1.0, 0.9, 0.5, 0.9),
            emissive: LinearRgba::rgb(6.0, 5.0, 2.0),
            alpha_mode: AlphaMode::Blend,
            unlit: true,
            ..default()
        }),
    });
}

/// Spawn a glowing, fading sphere. Rockets, drone deaths and bullet
/// impacts all use it at different sizes.
pub fn spawn_blast(
    commands: &mut Commands,
    fx: &FxAssets,
    materials: &mut Assets<StandardMaterial>,
    center: Vec3,
    radius: f32,
) {
    let material = materials.add(StandardMaterial {
        base_color: Color::srgba(1.0, 0.6, 0.2, 0.8),
        emissive: LinearRgba::rgb(6.0, 2.5, 0.4),
        alpha_mode: AlphaMode::Blend,
        unlit: true,
        ..default()
    });
    commands.spawn((
        Explosion { age: 0.0, radius, material: material.clone() },
        Mesh3d(fx.blast_mesh.clone()),
        MeshMaterial3d(material),
        Transform::from_translation(center).with_scale(Vec3::splat(0.1)),
    ));
}

fn switch_weapon(mut input: ResMut<PlayerInput>, mut arsenal: ResMut<Arsenal>) {
    let select = input.weapon_select.take();
    let step = std::mem::take(&mut input.weapon_step);
    let last = std::mem::take(&mut input.weapon_last);
    if let Some(slot) = select {
        arsenal.select(slot);
    } else if step != 0 {
        let n = WEAPONS.len() as i32;
        let slot = (arsenal.current as i32 + step).rem_euclid(n) as usize;
        arsenal.select(slot);
    } else if last {
        let slot = arsenal.last;
        arsenal.select(slot);
    }
}

/// Tiny deterministic random source for pellet spread (no `rand` dependency).
fn next_unit(seed: &mut u64) -> f32 {
    *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    ((*seed >> 40) as f32) / (1u64 << 24) as f32
}

#[allow(clippy::too_many_arguments)]
fn fire(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    mut input: ResMut<PlayerInput>,
    view: Res<ViewAngles>,
    fx: Option<Res<FxAssets>>,
    mut arsenal: ResMut<Arsenal>,
    loadout: Res<crate::gunsmith::Loadout>,
    mut recoil: ResMut<Recoil>,
    aim_level: Res<Aim>,
    player: Single<(Entity, &Player, &Transform)>,
    mut fired: MessageWriter<WeaponFired>,
    mut rumble: MessageWriter<Rumble>,
    mut seed: Local<u64>,
) {
    let t = &*tuning;
    let dt = time.delta_secs();
    arsenal.cooldown -= dt;
    recoil.heat = (recoil.heat - dt * 0.6).max(0.0);
    let fire_pressed = std::mem::take(&mut input.fire_pressed);
    if arsenal.switch_time > 0.0 {
        arsenal.switch_time -= dt;
        return;
    }
    let kind = arsenal.kind();
    let automatic = kind.gun(t, &loadout).is_none_or(|g| g.automatic);
    let wants_fire = if automatic { input.fire_held } else { fire_pressed };
    if !wants_fire || arsenal.cooldown > 0.0 {
        return;
    }
    arsenal.shots += 1;

    let (player_entity, p, tf) = *player;
    let eye = tf.translation + Vec3::Y * p.eye_offset(t);
    let aim = view.rotation();
    let forward = aim * Vec3::NEG_Z;
    // Where tracers start: roughly the viewmodel's muzzle.
    let muzzle = eye + aim * Vec3::new(0.2, -0.15, -0.6);

    let Some(gun) = kind.gun(t, &loadout) else {
        arsenal.cooldown = t.rocket_cooldown;
        let start = eye + forward * 0.3;
        let mut e = commands.spawn((
            Rocket { velocity: forward * t.rocket_speed, life: 5.0 },
            Transform::from_translation(start),
        ));
        if let Some(fx) = &fx {
            e.insert((Mesh3d(fx.rocket_mesh.clone()), MeshMaterial3d(fx.rocket_mat.clone())));
        }
        fired.write(WeaponFired { kick: 1.5 });
        rumble.write(Rumble { strength: 0.4, seconds: 0.12 });
        return;
    };

    arsenal.cooldown = gun.cooldown;
    // Spread: the gun's, wider with heat and on the move, tighter crouched or aiming.
    let moving = (p.velocity.xz().length() / t.max_speed).clamp(0.0, 1.0);
    let mut spread = gun.spread_degrees.to_radians() * (1.0 + recoil.heat * gun.heat_spread) * (1.0 + moving * 0.8);
    if p.crouched {
        spread *= 0.7;
    }
    spread *= 1.0 - aim_level.level * (1.0 - gun.ads_spread);
    recoil.heat = (recoil.heat + 0.12).min(1.0);
    recoil.since_shot = 0.0;
    let side = ((arsenal.shots as f32) * 0.9).sin();
    let ads = 1.0 - aim_level.level * 0.5;
    recoil.pending += Vec2::new(gun.recoil_side.to_radians() * side, gun.recoil_up.to_radians()) * ads;
    for _ in 0..gun.pellets.max(1) {
        // Uniform point in a disc, as yaw/pitch offsets.
        let angle = next_unit(&mut seed) * std::f32::consts::TAU;
        let r = next_unit(&mut seed).sqrt() * spread;
        let dir = aim * Quat::from_euler(EulerRot::YXZ, r * angle.cos(), r * angle.sin(), 0.0) * Vec3::NEG_Z;
        spawn_bullet(&mut commands, fx.as_deref(), muzzle, dir.normalize(), &gun, player_entity);
    }
    fired.write(WeaponFired { kick: gun.kick });
    rumble.write(Rumble { strength: (0.15 * gun.kick).min(0.6), seconds: 0.08 });
}

#[allow(clippy::too_many_arguments)]
fn fly_rockets(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut rockets: Query<(Entity, &mut Rocket, &mut Transform), Without<Player>>,
    mut player: Single<(Entity, &mut Player, &Transform)>,
    mut bodies: Query<(&RigidBody, &Position, &mut LinearVelocity, &ComputedMass), Without<Player>>,
    mut damage: MessageWriter<Damage>,
    mut rumble: MessageWriter<Rumble>,
) {
    let t = &*tuning;
    let dt = time.delta_secs();
    let (player_entity, p, player_tf) = &mut *player;
    let filter = SpatialQueryFilter::from_excluded_entities([*player_entity]);

    for (entity, mut rocket, mut tf) in &mut rockets {
        rocket.life -= dt;
        let step = rocket.velocity * dt;
        let Ok(dir) = Dir3::new(step) else { continue };
        let hit = spatial.cast_ray(tf.translation, dir, step.length(), true, &filter);
        let Some(hit) = hit else {
            tf.translation += step;
            if rocket.life <= 0.0 {
                commands.entity(entity).despawn();
            }
            continue;
        };
        commands.entity(entity).despawn();
        let center = tf.translation + dir * hit.distance + hit.normal * 0.05;

        // Player knockback, TF2-style linear falloff to 50% at the edge.
        let to_player = player_tf.translation - center;
        let d = to_player.length();
        if d < t.blast_radius {
            let falloff = 1.0 - 0.5 * d / t.blast_radius;
            p.velocity += to_player.normalize_or(Vec3::Y) * t.self_knockback * falloff;
            p.knockback_lock = 0.1;
            if p.state != MoveState::Mantle {
                p.state = MoveState::Air;
            }
        }
        rumble.write(Rumble { strength: (1.0 - d / (t.blast_radius * 3.0)).max(0.15), seconds: 0.2 });

        // Props and targets
        let blast = Collider::sphere(t.blast_radius);
        for e in spatial.shape_intersections(&blast, center, Quat::IDENTITY, &filter) {
            let Ok((body, pos, mut lv, mass)) = bodies.get_mut(e) else { continue };
            let offset = pos.0 - center;
            let falloff = 1.0 - 0.5 * (offset.length() / t.blast_radius).min(1.0);
            let push = (offset.normalize_or(Vec3::Y) + Vec3::Y * 0.3) * t.prop_knockback * falloff;
            damage.write(Damage { entity: e, amount: t.rocket_damage * falloff, impulse: push });
            if *body != RigidBody::Dynamic {
                continue;
            }
            let scale = (t.prop_ref_mass * mass.inverse()).min(1.0);
            lv.0 += push * scale;
        }

        if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
            spawn_blast(&mut commands, fx, materials, center, t.blast_radius);
        }
    }
}

fn fade_explosions(
    mut commands: Commands,
    time: Res<Time>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut q: Query<(Entity, &mut Explosion, &mut Transform)>,
) {
    let Some(mut materials) = materials else { return };
    for (e, mut ex, mut tf) in &mut q {
        ex.age += time.delta_secs();
        let k = ex.age / EXPLOSION_TIME;
        if k >= 1.0 {
            materials.remove(&ex.material);
            commands.entity(e).despawn();
            continue;
        }
        tf.scale = Vec3::splat(ex.radius * (0.3 + 0.7 * k));
        if let Some(mut m) = materials.get_mut(&ex.material) {
            m.base_color.set_alpha(0.8 * (1.0 - k));
        }
    }
}

/// Steps every bullet: gravity and drag, a ray along the step, damage scaled by the energy left,
/// head and leg zones on soldiers, and a pass through thin cover.
#[allow(clippy::too_many_arguments)]
fn fly_bullets(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    player: Single<Entity, With<Player>>,
    wind: Option<Res<crate::world::Wind>>,
    mut bullets: Query<(Entity, &mut Bullet, &mut Transform)>,
    targets: Query<(&crate::targets::Target, &Transform), Without<Bullet>>,
    cover: Query<&Penetrable>,
    mut bodies: Query<(&RigidBody, &mut LinearVelocity, &ComputedMass), (Without<Player>, Without<Bullet>)>,
    mut damage: MessageWriter<Damage>,
    mut hits: MessageWriter<crate::health::PlayerHit>,
) {
    let dt = time.delta_secs();
    let t = &*tuning;
    for (entity, mut b, mut tf) in &mut bullets {
        b.age += dt;
        b.velocity.y -= 9.81 * dt;
        let speed = b.velocity.length();
        if b.age > 3.0 || speed < 20.0 {
            commands.entity(entity).despawn();
            continue;
        }
        // Drag acts on the bullet's speed through the air, so a crosswind pushes it sideways.
        let air = wind.as_ref().map_or(Vec3::ZERO, |w| w.0);
        let rel = b.velocity - air;
        b.velocity = air + rel * (-b.drag * rel.length() * dt).exp();
        let speed = b.velocity.length();
        let mut pos = tf.translation;
        let mut remaining = speed * dt;
        let dir = b.velocity / speed;
        let filter = SpatialQueryFilter::from_excluded_entities([b.owner, entity]);
        let mut stopped = false;
        while remaining > 0.0 {
            let Some(hit) = spatial.cast_ray(pos, Dir3::new(dir).unwrap(), remaining, true, &filter) else { break };
            let point = pos + dir * hit.distance;
            let energy = (b.velocity.length() / b.muzzle).powi(2);
            if hit.entity == *player {
                hits.write(crate::health::PlayerHit { amount: b.damage * energy });
                stopped = true;
                break;
            }
            // Head and leg zones on the capsule targets.
            let zone = targets.get(hit.entity).map_or(1.0, |(_, ttf)| {
                let local = point.y - (ttf.translation.y - crate::targets::DUMMY_HEIGHT * 0.5);
                if local > crate::targets::DUMMY_HEIGHT - 0.35 {
                    t.headshot
                } else if local < 0.85 {
                    t.legshot
                } else {
                    1.0
                }
            });
            damage.write(Damage { entity: hit.entity, amount: b.damage * energy * zone, impulse: dir * b.impulse * energy });
            if let Ok((body, mut lv, mass)) = bodies.get_mut(hit.entity)
                && *body == RigidBody::Dynamic
            {
                let scale = (t.prop_ref_mass * mass.inverse()).min(1.0);
                lv.0 += dir * b.impulse * energy * scale;
            }
            if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                spawn_blast(&mut commands, fx, materials, point + hit.normal * 0.03, 0.18);
            }
            // Through thin cover, slower, up to twice.
            match cover.get(hit.entity) {
                Ok(c) if energy > c.cost && b.through < 2 => {
                    b.through += 1;
                    let left = ((energy - c.cost) / energy).sqrt();
                    b.velocity *= left;
                    pos = point + dir * 0.3;
                    remaining = (remaining - hit.distance - 0.3) * left;
                }
                _ => {
                    stopped = true;
                    break;
                }
            }
        }
        if stopped {
            commands.entity(entity).despawn();
            continue;
        }
        pos += dir * remaining;
        let streak = (speed * dt * 2.0).min(4.0);
        *tf = Transform::from_translation(pos).looking_to(dir, Vec3::Y).with_scale(Vec3::new(0.02, 0.02, streak));
    }
}

/// Applies the pending view kick fast, then pulls most of it back once the trigger rests.
fn recoil(time: Res<Time>, mut recoil: ResMut<Recoil>, mut view: ResMut<ViewAngles>) {
    let dt = time.delta_secs();
    recoil.since_shot += dt;
    let step = recoil.pending * (1.0 - (-30.0 * dt).exp());
    recoil.pending -= step;
    recoil.applied += step;
    view.yaw += step.x;
    view.pitch = (view.pitch + step.y).min(1.54);
    if recoil.since_shot > 0.12 {
        let back = recoil.applied * (1.0 - (-8.0 * dt).exp());
        recoil.applied -= back;
        view.yaw -= back.x * 0.7;
        view.pitch = (view.pitch - back.y * 0.7).max(-1.54);
    }
}

/// Aim down sights settles in `ads_time`; driving or the rocket launcher can't aim.
fn aim(time: Res<Time>, tuning: Res<Tuning>, input: Res<PlayerInput>, arsenal: Res<Arsenal>, player: Single<Has<crate::vehicle::Driving>, With<Player>>, mut aim: ResMut<Aim>) {
    let want = input.aim_held && !*player && arsenal.kind() != WeaponKind::RocketLauncher;
    let target = if want { 1.0 } else { 0.0 };
    let k = (time.delta_secs() / tuning.ads_time.max(0.01)).min(1.0);
    aim.level += (target - aim.level) * k;
}

fn fade_tracers(mut commands: Commands, time: Res<Time>, mut q: Query<(Entity, &mut Tracer, &mut Transform)>) {
    for (e, mut tracer, mut tf) in &mut q {
        tracer.age += time.delta_secs();
        let k = tracer.age / TRACER_TIME;
        if k >= 1.0 {
            commands.entity(e).despawn();
            continue;
        }
        let thickness = 0.02 * (1.0 - k);
        tf.scale.x = thickness;
        tf.scale.y = thickness;
    }
}
