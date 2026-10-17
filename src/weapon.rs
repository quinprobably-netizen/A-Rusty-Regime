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
            .add_systems(Startup, load_assets)
            .add_systems(FixedUpdate, (switch_weapon, fire, fly_rockets).chain().before(ControllerSet))
            .add_systems(Update, (fade_explosions, fade_tracers));
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
    fn gun(self, t: &Tuning) -> Option<&Gun> {
        match self {
            WeaponKind::RocketLauncher => None,
            WeaponKind::Rifle => Some(&t.rifle),
            WeaponKind::Shotgun => Some(&t.shotgun),
            WeaponKind::Pistol => Some(&t.pistol),
        }
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

#[derive(Component)]
struct Explosion {
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
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    spatial: SpatialQuery,
    mut arsenal: ResMut<Arsenal>,
    player: Single<(Entity, &Player, &Transform)>,
    mut bodies: Query<(&RigidBody, &mut LinearVelocity, &ComputedMass), Without<Player>>,
    mut damage: MessageWriter<Damage>,
    mut fired: MessageWriter<WeaponFired>,
    mut rumble: MessageWriter<Rumble>,
    mut seed: Local<u64>,
) {
    let t = &*tuning;
    let dt = time.delta_secs();
    arsenal.cooldown -= dt;
    let fire_pressed = std::mem::take(&mut input.fire_pressed);
    if arsenal.switch_time > 0.0 {
        arsenal.switch_time -= dt;
        return;
    }
    let kind = arsenal.kind();
    let automatic = kind.gun(t).is_none_or(|g| g.automatic);
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

    let Some(gun) = kind.gun(t) else {
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
    let filter = SpatialQueryFilter::from_excluded_entities([player_entity]);
    let spread = gun.spread_degrees.to_radians();
    for _ in 0..gun.pellets.max(1) {
        // Uniform point in a disc, as yaw/pitch offsets.
        let angle = next_unit(&mut seed) * std::f32::consts::TAU;
        let r = next_unit(&mut seed).sqrt() * spread;
        let dir = aim * Quat::from_euler(EulerRot::YXZ, r * angle.cos(), r * angle.sin(), 0.0) * Vec3::NEG_Z;
        let Ok(dir) = Dir3::new(dir) else { continue };
        let hit = spatial.cast_ray(eye, dir, gun.range, true, &filter);
        let end = match hit {
            Some(hit) => {
                let point = eye + dir * hit.distance;
                damage.write(Damage { entity: hit.entity, amount: gun.damage, impulse: dir * gun.prop_impulse });
                if let Ok((body, mut lv, mass)) = bodies.get_mut(hit.entity)
                    && *body == RigidBody::Dynamic
                {
                    let scale = (t.prop_ref_mass * mass.inverse()).min(1.0);
                    lv.0 += dir * gun.prop_impulse * scale;
                }
                if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                    spawn_blast(&mut commands, fx, materials, point + hit.normal * 0.03, 0.18);
                }
                point
            }
            None => eye + dir * gun.range,
        };
        if let Some(fx) = &fx {
            let delta = end - muzzle;
            let len = delta.length();
            if len > 0.5 {
                commands.spawn((
                    Tracer { age: 0.0 },
                    Mesh3d(fx.tracer_mesh.clone()),
                    MeshMaterial3d(fx.tracer_mat.clone()),
                    Transform::from_translation(muzzle + delta * 0.5)
                        .looking_to(delta / len, Vec3::Y)
                        .with_scale(Vec3::new(0.02, 0.02, len)),
                ));
            }
        }
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
