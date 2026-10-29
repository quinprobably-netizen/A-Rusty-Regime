//! Weapons: a rocket launcher (slow projectile, splash knockback for rocket jumps), six hitscan
//! guns, a bouncing grenade launcher, a harpoon that yanks you or what it hits, and a power fist.
//! Everything but the fist has a magazine; R reloads and an empty weapon reloads itself.

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::controller::{ControllerSet, MoveState, Player};
use crate::input::{PlayerInput, Rumble, ViewAngles};
use crate::save::Save;
use crate::surface::Origin;
use crate::tuning::{Gun, Tuning};

pub struct WeaponPlugin;

impl Plugin for WeaponPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<Rumble>()
            .add_message::<WeaponFired>()
            .add_message::<Detonate>()
            .init_resource::<Muzzle>()
            .init_resource::<Arsenal>()
            .init_resource::<crate::gunsmith::Loadout>()
            .add_systems(Startup, load_assets)
            .init_resource::<Recoil>()
            .init_resource::<Aim>()
            .add_systems(FixedUpdate, (switch_weapon, fire, fly_rockets, fly_grenades, fly_spears, detonate, fly_bullets).chain().before(ControllerSet))
            .add_systems(Update, (fade_explosions, fade_tracers, recoil, aim, fly_debris, hitstop));
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum WeaponKind {
    RocketLauncher,
    Rifle,
    Shotgun,
    Pistol,
    Smg,
    Dmr,
    Revolver,
    Grenade,
    Harpoon,
    Fist,
    Knife,
}

/// Number keys 1-9 then 0, then the knife on X. The first four keep their old slots so saved loadouts stay valid.
pub const WEAPONS: [WeaponKind; 11] = [
    WeaponKind::RocketLauncher,
    WeaponKind::Rifle,
    WeaponKind::Shotgun,
    WeaponKind::Pistol,
    WeaponKind::Smg,
    WeaponKind::Dmr,
    WeaponKind::Revolver,
    WeaponKind::Grenade,
    WeaponKind::Harpoon,
    WeaponKind::Fist,
    WeaponKind::Knife,
];

/// The knife's slot: X draws it, and X again puts it away.
pub const KNIFE: usize = 10;

impl WeaponKind {
    pub fn name(self) -> &'static str {
        match self {
            WeaponKind::RocketLauncher => "ROCKET LAUNCHER",
            WeaponKind::Rifle => "MA-14 RIFLE",
            WeaponKind::Shotgun => "BREACHER",
            WeaponKind::Pistol => "SMITE",
            WeaponKind::Smg => "STINGER",
            WeaponKind::Dmr => "LONGSHOT",
            WeaponKind::Revolver => "WARDEN",
            WeaponKind::Grenade => "THUMPER",
            WeaponKind::Harpoon => "HARPOON",
            WeaponKind::Fist => "POWER FIST",
            WeaponKind::Knife => "TALON",
        }
    }
    /// The model's file name in `assets/models/weapons/`.
    pub fn id(self) -> &'static str {
        match self {
            WeaponKind::RocketLauncher => "rocket",
            WeaponKind::Rifle => "rifle",
            WeaponKind::Shotgun => "shotgun",
            WeaponKind::Pistol => "pistol",
            WeaponKind::Smg => "smg",
            WeaponKind::Dmr => "dmr",
            WeaponKind::Revolver => "revolver",
            WeaponKind::Grenade => "grenade",
            WeaponKind::Harpoon => "harpoon",
            WeaponKind::Fist => "fist",
            WeaponKind::Knife => "knife",
        }
    }
    /// The gun's tuning with the gunsmith's parts fitted; `None` for everything that isn't a hitscan gun.
    fn gun(self, t: &Tuning, loadout: &crate::gunsmith::Loadout) -> Option<Gun> {
        t.gun(self).map(|g| loadout.gun(self, g))
    }
    /// Rounds per magazine; 0 for the fist, which never runs dry.
    pub fn mag(self, t: &Tuning) -> u32 {
        match self {
            WeaponKind::RocketLauncher => t.rocket_mag,
            WeaponKind::Grenade => t.grenade.mag,
            WeaponKind::Harpoon => t.harpoon.mag,
            WeaponKind::Fist | WeaponKind::Knife => 0,
            _ => t.gun(self).map_or(0, |g| g.mag),
        }
    }
    pub fn reload_time(self, t: &Tuning) -> f32 {
        match self {
            WeaponKind::RocketLauncher => t.rocket_reload,
            WeaponKind::Grenade => t.grenade.reload,
            WeaponKind::Harpoon => t.harpoon.reload,
            WeaponKind::Fist | WeaponKind::Knife => 0.0,
            _ => t.gun(self).map_or(0.0, |g| g.reload),
        }
    }
    /// Seconds between shots, for pacing the fire animation.
    pub fn cooldown(self, t: &Tuning, loadout: &crate::gunsmith::Loadout) -> f32 {
        match self {
            WeaponKind::RocketLauncher => t.rocket_cooldown,
            WeaponKind::Grenade => t.grenade.cooldown,
            WeaponKind::Harpoon => t.harpoon.cooldown,
            WeaponKind::Fist => t.fist.cooldown,
            WeaponKind::Knife => t.knife.cooldown,
            _ => self.gun(t, loadout).map_or(0.1, |g| g.cooldown),
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
    /// Rounds fired from each weapon's magazine since its last reload.
    pub spent: [u32; WEAPONS.len()],
    /// Seconds left on the reload in progress, 0 when not reloading.
    pub reload: f32,
}

impl Default for Arsenal {
    fn default() -> Self {
        Self { current: 0, last: 1, cooldown: 0.0, switch_time: 0.0, shots: 0, spent: [0; WEAPONS.len()], reload: 0.0 }
    }
}

impl Arsenal {
    pub fn kind(&self) -> WeaponKind {
        WEAPONS[self.current]
    }
    /// Rounds left and magazine size for the current weapon, or `None` for the fist.
    pub fn rounds(&self, t: &Tuning) -> Option<(u32, u32)> {
        let mag = self.kind().mag(t);
        (mag > 0).then(|| (mag.saturating_sub(self.spent[self.current]), mag))
    }
    pub fn select(&mut self, slot: usize) {
        if slot < WEAPONS.len() && slot != self.current {
            self.last = self.current;
            self.current = slot;
            self.switch_time = SWITCH_TIME;
            self.reload = 0.0;
        }
    }
}

/// The current weapon just fired; the viewmodel kicks back by `kick`.
#[derive(Message)]
pub struct WeaponFired {
    pub kick: f32,
}

/// An explosion at `center`: rockets and grenades both end in one.
#[derive(Message)]
pub struct Detonate {
    pub center: Vec3,
    pub radius: f32,
    pub self_knockback: f32,
}

/// Where shots leave the visible weapon, in the camera's frame; the viewmodel keeps it on the muzzle.
#[derive(Resource, Debug, Clone, Copy)]
pub struct Muzzle(pub Vec3);

impl Default for Muzzle {
    fn default() -> Self {
        Self(Vec3::new(0.2, -0.15, -0.6))
    }
}

/// A bullet in flight: it drops under the surface's gravity, slows by `drag` per metre, and does
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
    /// Shots in the current burst: the gun's fixed recoil pattern is indexed by it.
    pub streak: u32,
    /// Camera shake from firing, 0..1, easing off by itself.
    pub trauma: f32,
    /// Real seconds of hit-stop left after a melee blow lands.
    pub hitstop: f32,
}

/// The `n`th shot of a burst from weapon `slot`: how much its upward kick has climbed (1 on the
/// first shot, settling near 1.6) and how far along the gun's sideways pattern it is (-1..1).
/// The pattern is the same every burst, so it can be learned and pulled against.
pub fn recoil_pattern(slot: usize, n: u32) -> (f32, f32) {
    let n = n as f32;
    let climb = 1.0 + 0.6 * (1.0 - (-n / 4.0).exp());
    let drift = (n / 5.0).min(1.0) * (n * 0.55 + slot as f32 * 1.3).sin();
    (climb, drift)
}

/// What a bullet hit, for the sparks, dust or chips it throws.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Surface {
    Metal,
    Dirt,
    Stone,
}

/// Gravity on a projectile at world position `at`: the surface's pull there, scaled by
/// `weight` over the flat world's 9.8, so a 12 m/s² grenade falls 12/9.8 times as hard as a
/// bullet on any world, and nothing falls in deep space.
fn pull(surface: &crate::surface::Surface, origin: &Origin, t: &Tuning, at: Vec3, weight: f32) -> Vec3 {
    surface.gravity(origin.body(at), t.gravity) * (weight / t.gravity)
}

/// A bit of debris, casing or spark: flies under `gravity` (scaled as in `pull`), spins, shrinks away over its last 40%.
#[derive(Component)]
pub struct Debris {
    velocity: Vec3,
    spin: Vec3,
    life: f32,
    age: f32,
    gravity: f32,
    size: Vec3,
}

fn spawn_debris(commands: &mut Commands, fx: &FxAssets, material: &Handle<StandardMaterial>, at: Vec3, velocity: Vec3, spin: Vec3, size: Vec3, life: f32, gravity: f32) {
    commands.spawn((
        Debris { velocity, spin, life, age: 0.0, gravity, size },
        Mesh3d(fx.tracer_mesh.clone()),
        MeshMaterial3d(material.clone()),
        Transform::from_translation(at).looking_to(velocity.try_normalize().unwrap_or(Vec3::Z), Vec3::Y).with_scale(size),
    ));
}

fn fly_debris(mut commands: Commands, time: Res<Time>, tuning: Res<Tuning>, surface: Res<crate::surface::Surface>, origin: Res<Origin>, mut bits: Query<(Entity, &mut Debris, &mut Transform)>) {
    let dt = time.delta_secs();
    for (e, mut d, mut tf) in &mut bits {
        d.age += dt;
        if d.age >= d.life {
            commands.entity(e).despawn();
            continue;
        }
        let fall = pull(&surface, &origin, &tuning, tf.translation, d.gravity);
        d.velocity += fall * dt;
        tf.translation += d.velocity * dt;
        if d.spin != Vec3::ZERO {
            tf.rotate_local(Quat::from_euler(EulerRot::XYZ, d.spin.x * dt, d.spin.y * dt, d.spin.z * dt));
        }
        tf.scale = d.size * ((d.life - d.age) / (d.life * 0.4)).min(1.0);
    }
}

/// A seed from where something happened, for effects that need a few random numbers.
fn point_seed(p: Vec3) -> u64 {
    (p.x.to_bits() as u64) << 32 ^ (p.y.to_bits() as u64) << 16 ^ p.z.to_bits() as u64 | 1
}

/// Sparks, dust or chips thrown back off `point` along `normal`; a head hit throws more.
fn spawn_impact(commands: &mut Commands, fx: &FxAssets, point: Vec3, normal: Vec3, surface: Surface) {
    let mut seed = point_seed(point);
    let (material, count, speed, gravity, size, life) = match surface {
        Surface::Metal => (&fx.spark_mat, 7, 6.0, 6.0, Vec3::new(0.008, 0.008, 0.07), 0.25),
        Surface::Dirt => (&fx.dust_mat, 6, 2.5, 9.8, Vec3::splat(0.045), 0.6),
        Surface::Stone => (&fx.chip_mat, 5, 4.0, 9.8, Vec3::splat(0.03), 0.5),
    };
    for _ in 0..count {
        let scatter = Vec3::new(next_unit(&mut seed) - 0.5, next_unit(&mut seed) - 0.5, next_unit(&mut seed) - 0.5);
        let velocity = (normal * (0.6 + next_unit(&mut seed)) + scatter * 1.4) * speed;
        let spin = if surface == Surface::Dirt || surface == Surface::Stone { scatter * 18.0 } else { Vec3::ZERO };
        spawn_debris(commands, fx, material, point + normal * 0.02, velocity, spin, size, life * (0.6 + next_unit(&mut seed) * 0.8), gravity);
    }
    // Stone and metal also throw a couple of sparks.
    if matches!(surface, Surface::Stone | Surface::Metal) {
        for _ in 0..2 {
            let scatter = Vec3::new(next_unit(&mut seed) - 0.5, next_unit(&mut seed) - 0.5, next_unit(&mut seed) - 0.5);
            spawn_debris(commands, fx, &fx.spark_mat, point + normal * 0.02, (normal + scatter) * 7.0, Vec3::ZERO, Vec3::new(0.008, 0.008, 0.06), 0.18, 4.0);
        }
    }
}

/// The world slows to a crawl for a few frames when a melee blow lands, then comes back.
fn hitstop(real: Res<Time<Real>>, mut recoil: ResMut<Recoil>, mut clock: ResMut<Time<Virtual>>) {
    if recoil.hitstop > 0.0 {
        recoil.hitstop -= real.delta_secs();
        clock.set_relative_speed(if recoil.hitstop > 0.0 { 0.05 } else { 1.0 });
    } else if clock.relative_speed() != 1.0 {
        clock.set_relative_speed(1.0);
    }
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
    grenade_mesh: Handle<Mesh>,
    grenade_mat: Handle<StandardMaterial>,
    spear_mesh: Handle<Mesh>,
    spear_mat: Handle<StandardMaterial>,
    blast_mesh: Handle<Mesh>,
    tracer_mesh: Handle<Mesh>,
    tracer_mat: Handle<StandardMaterial>,
    brass_mat: Handle<StandardMaterial>,
    spark_mat: Handle<StandardMaterial>,
    dust_mat: Handle<StandardMaterial>,
    chip_mat: Handle<StandardMaterial>,
}

#[derive(Component)]
struct Rocket {
    velocity: Vec3,
    life: f32,
}

#[derive(Component)]
pub struct GrenadeShell {
    pub velocity: Vec3,
    fuse: f32,
}

#[derive(Component)]
struct Spear {
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
        grenade_mesh: meshes.add(Sphere::new(0.06)),
        grenade_mat: materials.add(StandardMaterial { base_color: Color::srgb(0.3, 0.33, 0.2), emissive: LinearRgba::rgb(1.5, 1.0, 0.1), ..default() }),
        spear_mesh: meshes.add(Cuboid::new(0.012, 0.012, 0.6)),
        spear_mat: materials.add(StandardMaterial { base_color: Color::srgb(0.55, 0.56, 0.58), metallic: 1.0, perceptual_roughness: 0.3, ..default() }),
        blast_mesh: meshes.add(Sphere::new(1.0)),
        tracer_mesh: meshes.add(Cuboid::from_length(1.0)),
        tracer_mat: materials.add(StandardMaterial {
            base_color: Color::srgba(1.0, 0.9, 0.5, 0.9),
            emissive: LinearRgba::rgb(6.0, 5.0, 2.0),
            alpha_mode: AlphaMode::Blend,
            unlit: true,
            ..default()
        }),
        brass_mat: materials.add(StandardMaterial { base_color: Color::srgb(0.8, 0.6, 0.2), metallic: 1.0, perceptual_roughness: 0.35, ..default() }),
        spark_mat: materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.85, 0.5), emissive: LinearRgba::rgb(14.0, 8.0, 2.0), unlit: true, ..default() }),
        dust_mat: materials.add(StandardMaterial { base_color: Color::srgb(0.45, 0.38, 0.3), perceptual_roughness: 1.0, ..default() }),
        chip_mat: materials.add(StandardMaterial { base_color: Color::srgb(0.5, 0.5, 0.5), perceptual_roughness: 0.9, ..default() }),
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

fn switch_weapon(mut input: ResMut<PlayerInput>, mut arsenal: ResMut<Arsenal>, save: Option<Res<Save>>) {
    let select = input.weapon_select.take();
    let step = std::mem::take(&mut input.weapon_step);
    let last = std::mem::take(&mut input.weapon_last);
    let owned = |slot: usize| crate::quartermaster::owns_weapon(save.as_deref(), WEAPONS[slot]);
    let n = WEAPONS.len() as i32;
    if let Some(slot) = select.filter(|s| *s < WEAPONS.len()) {
        // The knife key draws the knife, and pressed again puts it away.
        let slot = if slot == KNIFE && arsenal.current == KNIFE { arsenal.last } else { slot };
        if owned(slot) {
            arsenal.select(slot);
        }
    } else if step != 0 {
        // Scrolling skips what the quartermaster has not sold you.
        let mut slot = arsenal.current as i32;
        for _ in 0..step.abs() {
            for _ in 0..n {
                slot = (slot + step.signum()).rem_euclid(n);
                if owned(slot as usize) {
                    break;
                }
            }
        }
        arsenal.select(slot as usize);
    } else if last && owned(arsenal.last) {
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
    muzzle_at: Res<Muzzle>,
    spatial: SpatialQuery,
    mut arsenal: ResMut<Arsenal>,
    loadout: Res<crate::gunsmith::Loadout>,
    mut recoil: ResMut<Recoil>,
    aim_level: Res<Aim>,
    // The camera, for aiming in third person, rides with the player to stay under Bevy's 16 parameters.
    (mut player, camera): (
        Single<(Entity, &mut Player, &Transform, Has<crate::vehicle::Driving>)>,
        Option<Single<&Transform, (With<crate::camera::PlayerCamera>, Without<Player>)>>,
    ),
    mut bodies: Query<(&RigidBody, &mut LinearVelocity, &ComputedMass), Without<Player>>,
    writers: (MessageWriter<WeaponFired>, MessageWriter<Rumble>),
    mut seed: Local<u64>,
) {
    let (mut fired, mut rumble) = writers;
    let t = &*tuning;
    let dt = time.delta_secs();
    arsenal.cooldown -= dt;
    recoil.heat = (recoil.heat - dt * 0.6).max(0.0);
    let fire_pressed = std::mem::take(&mut input.fire_pressed);
    let reload_pressed = std::mem::take(&mut input.reload_pressed);
    if arsenal.switch_time > 0.0 {
        arsenal.switch_time -= dt;
        return;
    }
    let kind = arsenal.kind();
    let slot = arsenal.current;
    if arsenal.reload > 0.0 {
        arsenal.reload -= dt;
        if arsenal.reload <= 0.0 {
            arsenal.reload = 0.0;
            arsenal.spent[slot] = 0;
        }
        return;
    }
    // Rockets and the fist repeat while held; the grenade launcher and harpoon fire per press.
    let automatic = match kind {
        WeaponKind::Grenade | WeaponKind::Harpoon => false,
        _ => kind.gun(t, &loadout).is_none_or(|g| g.automatic),
    };
    let wants_fire = if automatic { input.fire_held } else { fire_pressed };
    // Reload on R, on an empty trigger pull, or by itself once the last round is gone.
    if let Some((left, mag)) = arsenal.rounds(t)
        && arsenal.cooldown <= 0.0
        && (left == 0 || (reload_pressed && left < mag))
    {
        arsenal.reload = kind.reload_time(t);
        return;
    }
    if !wants_fire || arsenal.cooldown > 0.0 {
        return;
    }
    arsenal.shots += 1;
    if kind.mag(t) > 0 {
        arsenal.spent[slot] += 1;
    }

    let (player_entity, p, tf, driving) = &mut *player;
    let player_entity = *player_entity;
    let eye = tf.translation + p.up() * p.eye_offset(t);
    let filter = SpatialQueryFilter::from_excluded_entities([player_entity]);
    let mut aim = view.rotation();
    // Third person: the crosshair is the camera's, behind the shoulder. Shoot from the eyes at
    // whatever it covers, looking only past the player so nothing behind them is the target.
    if crate::camera::third_person(t, *driving, None)
        && let Some(cam) = &camera
    {
        let dir = aim * Vec3::NEG_Z;
        let from = cam.translation + dir * (eye - cam.translation).dot(dir).max(0.0);
        let reach = spatial.cast_ray(from, Dir3::new(dir).unwrap(), 2000.0, true, &filter).map_or(2000.0, |h| h.distance);
        let target = from + dir * reach.max(1.0);
        aim = Transform::from_translation(eye).looking_at(target, p.up()).rotation;
    }
    let forward = aim * Vec3::NEG_Z;
    // Where tracers start: the viewmodel's muzzle.
    let muzzle = eye + aim * muzzle_at.0;

    match kind {
        WeaponKind::RocketLauncher => {
            arsenal.cooldown = t.rocket_cooldown;
            let mut e = commands.spawn((Rocket { velocity: forward * t.rocket_speed, life: 5.0 }, Transform::from_translation(eye + forward * 0.3)));
            if let Some(fx) = &fx {
                e.insert((Mesh3d(fx.rocket_mesh.clone()), MeshMaterial3d(fx.rocket_mat.clone())));
            }
            fired.write(WeaponFired { kick: 1.5 });
            rumble.write(Rumble { strength: 0.4, seconds: 0.12 });
            return;
        }
        WeaponKind::Grenade => {
            let g = &t.grenade;
            arsenal.cooldown = g.cooldown;
            let velocity = forward * g.speed + p.up() * g.lift + p.velocity * 0.5;
            let mut e = commands.spawn((GrenadeShell { velocity, fuse: g.fuse }, Transform::from_translation(muzzle)));
            if let Some(fx) = &fx {
                e.insert((Mesh3d(fx.grenade_mesh.clone()), MeshMaterial3d(fx.grenade_mat.clone())));
            }
            fired.write(WeaponFired { kick: 2.0 });
            rumble.write(Rumble { strength: 0.45, seconds: 0.14 });
            return;
        }
        WeaponKind::Harpoon => {
            let h = &t.harpoon;
            arsenal.cooldown = h.cooldown;
            let mut e = commands.spawn((Spear { velocity: forward * h.speed, life: h.life }, Transform::from_translation(muzzle).looking_to(forward, Vec3::Y)));
            if let Some(fx) = &fx {
                e.insert((Mesh3d(fx.spear_mesh.clone()), MeshMaterial3d(fx.spear_mat.clone())));
            }
            fired.write(WeaponFired { kick: 1.2 });
            rumble.write(Rumble { strength: 0.3, seconds: 0.1 });
            return;
        }
        WeaponKind::Fist => {
            let f = &t.fist;
            arsenal.cooldown = f.cooldown;
            fired.write(WeaponFired { kick: 0.8 });
            let Some(hit) = spatial.cast_ray(eye, Dir3::new(forward).unwrap(), f.range, true, &filter) else { return };
            recoil.hitstop = 0.06;
            if let Ok((body, mut lv, mass)) = bodies.get_mut(hit.entity)
                && *body == RigidBody::Dynamic
            {
                lv.0 += (forward * f.knockback + p.up() * 2.0) * (t.prop_ref_mass * mass.inverse()).min(1.0);
            }
            // Punching anything throws you back off it: off a wall, off the floor.
            p.velocity += -forward * f.launch;
            p.knockback_lock = 0.1;
            if p.state != MoveState::Mantle {
                p.state = MoveState::Air;
            }
            rumble.write(Rumble { strength: 0.7, seconds: 0.15 });
            return;
        }
        WeaponKind::Knife => {
            let k = &t.knife;
            arsenal.cooldown = k.cooldown;
            fired.write(WeaponFired { kick: 0.5 });
            let Some(hit) = spatial.cast_ray(eye, Dir3::new(forward).unwrap(), k.range, true, &filter) else { return };
            recoil.hitstop = 0.04;
            if let Ok((body, mut lv, mass)) = bodies.get_mut(hit.entity)
                && *body == RigidBody::Dynamic
            {
                lv.0 += forward * k.knockback * (t.prop_ref_mass * mass.inverse()).min(1.0);
            }
            rumble.write(Rumble { strength: 0.35, seconds: 0.08 });
            return;
        }
        _ => {}
    }
    let Some(gun) = kind.gun(t, &loadout) else { return };

    arsenal.cooldown = gun.cooldown;
    // Spread: the gun's, wider with heat and on the move, tighter crouched or aiming.
    let moving = (p.horizontal_speed() / t.max_speed).clamp(0.0, 1.0);
    let mut spread = gun.spread_degrees.to_radians() * (1.0 + recoil.heat * gun.heat_spread) * (1.0 + moving * 0.8);
    if p.crouched {
        spread *= 0.7;
    }
    spread *= 1.0 - aim_level.level * (1.0 - gun.ads_spread);
    recoil.heat = (recoil.heat + 0.12).min(1.0);
    // The gun's fixed pattern: a burst starts straight up, climbs, and drifts the same way each time.
    if recoil.since_shot > 0.35 {
        recoil.streak = 0;
    }
    let (climb, drift) = recoil_pattern(slot, recoil.streak);
    recoil.streak += 1;
    recoil.since_shot = 0.0;
    let mut ads = 1.0 - aim_level.level * 0.5;
    // The marksman rifle's folded bipod: braced while crouched, it kicks far less.
    if kind == WeaponKind::Dmr && p.crouched {
        ads *= 0.5;
    }
    recoil.pending += Vec2::new(gun.recoil_side.to_radians() * drift, gun.recoil_up.to_radians() * climb) * ads;
    // Brass out of the ejection port, to the right and up, carrying a little of the player's own speed.
    if let Some(fx) = fx.as_deref()
        && kind != WeaponKind::Revolver
    {
        let seed = &mut *seed;
        let right = aim * Vec3::X;
        let up = aim * Vec3::Y;
        let velocity = right * (2.0 + next_unit(seed)) + up * (1.5 + next_unit(seed) * 0.8) - forward * 0.4 + p.velocity * 0.8;
        let shell = kind == WeaponKind::Shotgun;
        let size = if shell { Vec3::new(0.02, 0.02, 0.05) } else { Vec3::new(0.01, 0.01, 0.035) };
        spawn_debris(&mut commands, fx, &fx.brass_mat, eye + aim * Vec3::new(0.14, -0.1, -0.45), velocity, Vec3::new(20.0, 14.0, 6.0), size, 1.0, 9.8);
    }
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

fn fly_rockets(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    mut rockets: Query<(Entity, &mut Rocket, &mut Transform)>,
    player: Single<Entity, With<Player>>,
    mut detonate: MessageWriter<Detonate>,
) {
    let t = &*tuning;
    let dt = time.delta_secs();
    let filter = SpatialQueryFilter::from_excluded_entities([*player]);
    for (entity, mut rocket, mut tf) in &mut rockets {
        rocket.life -= dt;
        let step = rocket.velocity * dt;
        let Ok(dir) = Dir3::new(step) else { continue };
        let Some(hit) = spatial.cast_ray(tf.translation, dir, step.length(), true, &filter) else {
            tf.translation += step;
            if rocket.life <= 0.0 {
                commands.entity(entity).despawn();
            }
            continue;
        };
        commands.entity(entity).despawn();
        let center = tf.translation + dir * hit.distance + hit.normal * 0.05;
        detonate.write(Detonate { center, radius: t.blast_radius, self_knockback: t.self_knockback });
    }
}

/// Frags lob under gravity, bounce off the world, and burst on a fuse.
fn fly_grenades(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    surface: Res<crate::surface::Surface>,
    origin: Res<Origin>,
    mut shells: Query<(Entity, &mut GrenadeShell, &mut Transform)>,
    player: Single<Entity, With<Player>>,
    mut detonate: MessageWriter<Detonate>,
) {
    let g = &tuning.grenade;
    let dt = time.delta_secs();
    let filter = SpatialQueryFilter::from_excluded_entities([*player]);
    for (entity, mut shell, mut tf) in &mut shells {
        shell.fuse -= dt;
        shell.velocity += pull(&surface, &origin, &tuning, tf.translation, g.gravity) * dt;
        let step = shell.velocity * dt;
        let burst = shell.fuse <= 0.0;
        if let Ok(dir) = Dir3::new(step)
            && let Some(hit) = spatial.cast_ray(tf.translation, dir, step.length(), true, &filter)
        {
            tf.translation += dir * hit.distance + hit.normal * 0.04;
            let v = shell.velocity;
            shell.velocity = (v - 2.0 * v.dot(hit.normal) * hit.normal) * g.bounce;
        } else {
            tf.translation += step;
        }
        if burst {
            commands.entity(entity).despawn();
            detonate.write(Detonate { center: tf.translation, radius: g.radius, self_knockback: g.self_knockback });
        }
    }
}

/// The harpoon's spear: stuck in the world it yanks you to it; in a prop it yanks that to you.
#[allow(clippy::too_many_arguments)]
fn fly_spears(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    surface: Res<crate::surface::Surface>,
    origin: Res<Origin>,
    mut spears: Query<(Entity, &mut Spear, &mut Transform), Without<Player>>,
    mut player: Single<(Entity, &mut Player, &Transform)>,
    mut bodies: Query<(&RigidBody, &mut LinearVelocity, &ComputedMass), Without<Player>>,
    mut rumble: MessageWriter<Rumble>,
) {
    let h = &tuning.harpoon;
    let dt = time.delta_secs();
    let (player_entity, p, player_tf) = &mut *player;
    let filter = SpatialQueryFilter::from_excluded_entities([*player_entity]);
    for (entity, mut spear, mut tf) in &mut spears {
        spear.life -= dt;
        spear.velocity += pull(&surface, &origin, &tuning, tf.translation, h.gravity) * dt;
        let step = spear.velocity * dt;
        let Ok(dir) = Dir3::new(step) else { continue };
        let Some(hit) = spatial.cast_ray(tf.translation, dir, step.length(), true, &filter) else {
            tf.translation += step;
            tf.look_to(dir, Vec3::Y);
            if spear.life <= 0.0 {
                commands.entity(entity).despawn();
            }
            continue;
        };
        commands.entity(entity).despawn();
        let point = tf.translation + dir * hit.distance;
        let up = surface.up(origin.body(point));
        let to_player = (player_tf.translation - point).normalize_or(up);
        let dynamic = bodies.get(hit.entity).is_ok_and(|(b, _, _)| *b == RigidBody::Dynamic);
        if dynamic {
            if let Ok((body, mut lv, mass)) = bodies.get_mut(hit.entity)
                && *body == RigidBody::Dynamic
            {
                lv.0 += (to_player * h.pull_target + up * 2.0) * (tuning.prop_ref_mass * mass.inverse()).min(1.0);
            }
        } else {
            p.velocity = -to_player * h.pull_player + p.up() * 2.5;
            p.knockback_lock = 0.15;
            if p.state != MoveState::Mantle {
                p.state = MoveState::Air;
            }
        }
        rumble.write(Rumble { strength: 0.35, seconds: 0.12 });
    }
}

/// Every explosion: TF2-style self knockback, splash damage and a push on props.
#[allow(clippy::too_many_arguments)]
fn detonate(
    mut commands: Commands,
    tuning: Res<Tuning>,
    spatial: SpatialQuery,
    surface: Res<crate::surface::Surface>,
    origin: Res<Origin>,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut blasts: MessageReader<Detonate>,
    mut player: Single<(Entity, &mut Player, &Transform)>,
    mut bodies: Query<(&RigidBody, &Position, &mut LinearVelocity, &ComputedMass), Without<Player>>,
    mut rumble: MessageWriter<Rumble>,
) {
    let t = &*tuning;
    let (player_entity, p, player_tf) = &mut *player;
    let filter = SpatialQueryFilter::from_excluded_entities([*player_entity]);
    for b in blasts.read() {
        let center = b.center;
        let up = surface.up(origin.body(center));
        // Player knockback, TF2-style linear falloff to 50% at the edge.
        let to_player = player_tf.translation - center;
        let d = to_player.length();
        if d < b.radius {
            let falloff = 1.0 - 0.5 * d / b.radius;
            p.velocity += to_player.normalize_or(up) * b.self_knockback * falloff;
            p.knockback_lock = 0.1;
            if p.state != MoveState::Mantle {
                p.state = MoveState::Air;
            }
        }
        rumble.write(Rumble { strength: (1.0 - d / (b.radius * 3.0)).max(0.15), seconds: 0.2 });

        // Props
        let blast = Collider::sphere(b.radius);
        for e in spatial.shape_intersections(&blast, center, Quat::IDENTITY, &filter) {
            let Ok((body, pos, mut lv, mass)) = bodies.get_mut(e) else { continue };
            let offset = pos.0 - center;
            let falloff = 1.0 - 0.5 * (offset.length() / b.radius).min(1.0);
            let push = (offset.normalize_or(up) + up * 0.3) * t.prop_knockback * falloff;
            if *body != RigidBody::Dynamic {
                continue;
            }
            let scale = (t.prop_ref_mass * mass.inverse()).min(1.0);
            lv.0 += push * scale;
        }

        if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
            spawn_blast(&mut commands, fx, materials, center, b.radius);
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
    mut bullets: Query<(Entity, &mut Bullet, &mut Transform)>,
    cover: Query<&Penetrable>,
    mut bodies: Query<(&RigidBody, &mut LinearVelocity, &ComputedMass), (Without<Player>, Without<Bullet>)>,
    mut hits: MessageWriter<crate::health::PlayerHit>,
    surfaces: Query<(Has<crate::planet::Chunk>, Has<crate::solar::ship::Ship>, Has<crate::solar::Fixture>)>,
    surface: Res<crate::surface::Surface>,
    origin: Res<Origin>,
) {
    let dt = time.delta_secs();
    let t = &*tuning;
    for (entity, mut b, mut tf) in &mut bullets {
        b.age += dt;
        b.velocity += pull(&surface, &origin, t, tf.translation, t.gravity) * dt;
        let speed = b.velocity.length();
        if b.age > 3.0 || speed < 20.0 {
            commands.entity(entity).despawn();
            continue;
        }
        // Drag acts on the bullet's speed through the air.
        let drag = b.drag * b.velocity.length();
        b.velocity *= (-drag * dt).exp();
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
            if let Ok((body, mut lv, mass)) = bodies.get_mut(hit.entity)
                && *body == RigidBody::Dynamic
            {
                let scale = (t.prop_ref_mass * mass.inverse()).min(1.0);
                lv.0 += dir * b.impulse * energy * scale;
            }
            if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
                let surface = match surfaces.get(hit.entity) {
                    Ok((true, _, _)) => Surface::Dirt,
                    Ok((_, true, _)) | Ok((_, _, true)) => Surface::Metal,
                    _ => Surface::Stone,
                };
                spawn_blast(&mut commands, fx, materials, point + hit.normal * 0.03, 0.06);
                spawn_impact(&mut commands, fx, point, hit.normal, surface);
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

/// Applies the pending view kick fast, then pulls most of it back once the trigger rests: the
/// sideways part comes back quicker and further than the upward part, so the end of a burst is
/// pure climb.
fn recoil(time: Res<Time>, mut recoil: ResMut<Recoil>, mut view: ResMut<ViewAngles>, mut fired: MessageReader<WeaponFired>) {
    let dt = time.delta_secs();
    for f in fired.read() {
        recoil.trauma = (recoil.trauma + f.kick * 0.2).min(1.0);
    }
    recoil.trauma = (recoil.trauma - 3.0 * dt).max(0.0);
    recoil.since_shot += dt;
    let step = recoil.pending * (1.0 - (-30.0 * dt).exp());
    recoil.pending -= step;
    recoil.applied += step;
    view.yaw += step.x;
    view.pitch = (view.pitch + step.y).min(1.54);
    if recoil.since_shot > 0.12 {
        let back = Vec2::new(recoil.applied.x * (1.0 - (-14.0 * dt).exp()), recoil.applied.y * (1.0 - (-8.0 * dt).exp()));
        recoil.applied -= back;
        view.yaw -= back.x * 0.95;
        view.pitch = (view.pitch - back.y * 0.7).max(-1.54);
    }
}

/// Aim down sights settles in `ads_time`; only the hitscan guns aim, and not while driving.
fn aim(time: Res<Time>, tuning: Res<Tuning>, input: Res<PlayerInput>, arsenal: Res<Arsenal>, player: Single<Has<crate::vehicle::Driving>, With<Player>>, mut aim: ResMut<Aim>) {
    // Dev aid: `RUST_REGIME_SCREENSHOT_AIM` holds the aim for screenshots of the sights.
    let dev = std::env::var_os("RUST_REGIME_SCREENSHOT_AIM").is_some();
    let want = (input.aim_held || dev) && !*player && tuning.gun(arsenal.kind()).is_some();
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
