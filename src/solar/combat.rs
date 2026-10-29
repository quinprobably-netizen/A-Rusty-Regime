//! Ship combat, stage 1 (`docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`): every
//! ship has a hull behind a shield and a faction, and a ship with `guns` in `ships.toml` fires them
//! from its own stick (`ShipControls::fire`: the left mouse button for the player). A shot is a
//! short-lived projectile at `[ship_combat] gun_speed` on top of the ship's own velocity, swept by
//! a ray each tick so nothing tunnels at a closing speed of kilometres a second, with no gravity
//! and a little drag in air. It never hurts its own ship or its own side. Damage drains the shield
//! first, which comes back after a quiet spell; a hull at zero blows the ship apart. Each hull
//! remembers whose fire hit it last, so the `ShipDestroyed` message names the killer (`loss` pays
//! the bounty from it and takes the player's own ship through the loss rule).

use avian3d::prelude::*;
use bevy::prelude::*;
use serde::Deserialize;

use super::ship::{Ship, ShipControls, Ships};
use super::Solar;
use crate::surface::{Origin, Surface};
use crate::tuning::{ShipCombat, Tuning};
use crate::weapon::{spawn_blast, FxAssets};

/// Whose ship it is, from `ships.toml`. The apron's ships are the player's, the Deserters'.
#[derive(Component, Deserialize, Clone, Copy, Debug, Default, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Faction {
    #[default]
    Deserters,
    Regime,
    Scrappers,
    Pmc,
    Raiders,
}

impl Faction {
    /// Its name in the data files, as in `bases.toml`.
    pub fn id(self) -> &'static str {
        match self {
            Faction::Deserters => "deserters",
            Faction::Regime => "regime",
            Faction::Scrappers => "scrappers",
            Faction::Pmc => "pmc",
            Faction::Raiders => "raiders",
        }
    }

    /// The faction named `id` in the data files.
    pub fn from_id(id: &str) -> Option<Faction> {
        [Faction::Deserters, Faction::Regime, Faction::Scrappers, Faction::Pmc, Faction::Raiders].into_iter().find(|f| f.id() == id)
    }

    /// Its name on screen.
    pub fn name(self) -> &'static str {
        match self {
            Faction::Deserters => "Deserters",
            Faction::Regime => "Regime",
            Faction::Scrappers => "Scrappers",
            Faction::Pmc => "PMC",
            Faction::Raiders => "Raiders",
        }
    }
}

/// A ship's hull points behind its shield.
#[derive(Component, Clone, Copy, Debug)]
pub struct Hull {
    pub hp: f32,
    pub shield: f32,
    pub max_shield: f32,
    /// Seconds until the shield starts to come back; every hit starts the wait again.
    pub shield_regen_after: f32,
    /// The ship whose fire landed the last hit, if anyone's did: at zero hp it is the killer.
    pub last_hit_by: Option<Entity>,
}

impl Hull {
    pub fn new(hp: f32, shield: f32) -> Self {
        Self { hp, shield, max_shield: shield, shield_regen_after: 0.0, last_hit_by: None }
    }

    /// Takes `damage` from nobody's fire: the shield holds what it can and the hull takes the rest.
    pub fn hit(&mut self, damage: f32, t: &ShipCombat) {
        let held = damage.min(self.shield);
        self.shield -= held;
        self.hp = (self.hp - (damage - held)).max(0.0);
        self.shield_regen_after = t.shield_delay;
        self.last_hit_by = None;
    }

    /// Takes `damage` fired by ship `by` (a shot's or a missile's owner), who is then the killer
    /// if this hit or none after it empties the hull.
    pub fn hit_by(&mut self, damage: f32, by: Entity, t: &ShipCombat) {
        self.hit(damage, t);
        self.last_hit_by = Some(by);
    }

    /// `dt` seconds go by: after the quiet spell the shield comes back.
    pub fn tick(&mut self, dt: f32, t: &ShipCombat) {
        if self.shield_regen_after > 0.0 {
            self.shield_regen_after -= dt;
        } else {
            self.shield = (self.shield + t.shield_regen * dt).min(self.max_shield);
        }
    }
}

/// The nose guns: heat builds per shot and an overheated gun stops until it cools, so there is no
/// ammunition to count. The barrels fire in turn.
#[derive(Component, Default, Debug)]
pub struct Gun {
    pub heat: f32,
    pub overheated: bool,
    /// Seconds until the next barrel may fire.
    pub fire_timer: f32,
    barrel: usize,
}

/// A shot in flight, in the anchor's frame.
#[derive(Component)]
pub struct Projectile {
    pub velocity: Vec3,
    /// Seconds left before it is gone (its range at muzzle speed).
    life: f32,
    /// The ship that fired it.
    pub owner: Entity,
    faction: Faction,
}

/// A ship's hull reached zero this tick. Written for every ship, the flown one too; `killer` is
/// the ship whose fire landed the last hit (`Hull::last_hit_by`), if anyone's.
#[derive(Message, Debug, Clone, Copy)]
pub struct ShipDestroyed {
    pub ship: Entity,
    pub spec: usize,
    pub faction: Faction,
    pub killer: Option<Entity>,
}

/// A shot or a missile from ship `by` took shield or hull off ship `on`: the cockpit's hit
/// marker, and a hit that costs standing with `on`'s faction.
#[derive(Message, Debug, Clone, Copy)]
pub struct ShotLanded {
    pub by: Entity,
    pub on: Entity,
}

/// What every shot looks like: a glowing streak.
#[derive(Resource)]
struct ShotLook {
    mesh: Handle<Mesh>,
    material: Handle<StandardMaterial>,
}

pub fn build(app: &mut App) {
    app.add_message::<ShipDestroyed>()
        .add_message::<ShotLanded>()
        .add_observer(arm)
        .add_systems(Startup, load_look)
        .add_systems(FixedUpdate, (shields, fire, fly_projectiles, wreck).chain().after(crate::controller::ControllerSet));
}

fn load_look(mut commands: Commands, meshes: Option<ResMut<Assets<Mesh>>>, materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    commands.insert_resource(ShotLook {
        mesh: meshes.add(Cuboid::from_length(1.0)),
        material: materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.8, 0.4), emissive: LinearRgba::rgb(30.0, 14.0, 3.0), unlit: true, ..default() }),
    });
}

/// Every ship gets its hull, shield and faction from its spec as it is spawned, and guns if it has
/// muzzles.
fn arm(add: On<Add, Ship>, mut commands: Commands, ships: Query<&Ship>, specs: Res<Ships>) {
    let Ok(ship) = ships.get(add.entity) else { return };
    let spec = &specs.ship[ship.spec];
    let mut e = commands.entity(add.entity);
    e.insert((Hull::new(spec.hull, spec.shield), spec.faction));
    if !spec.guns.is_empty() {
        e.insert(Gun::default());
    }
}

fn shields(time: Res<Time>, tuning: Res<Tuning>, mut hulls: Query<&mut Hull>) {
    for mut hull in &mut hulls {
        hull.tick(time.delta_secs(), &tuning.ship_combat);
    }
}

/// Fires each ship's guns while its trigger is held: one barrel at a time, aimed to cross the
/// other's shots `converge` metres ahead, each shot carrying the ship's own velocity.
#[allow(clippy::type_complexity)]
fn fire(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    look: Option<Res<ShotLook>>,
    mut ships: Query<(Entity, &Ship, &ShipControls, &mut Gun, &Faction, &Position, &Rotation, &LinearVelocity)>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    for (entity, ship, controls, mut gun, faction, pos, rot, v) in &mut ships {
        gun.heat = (gun.heat - t.cool * dt).max(0.0);
        if gun.overheated && gun.heat <= t.resume {
            gun.overheated = false;
        }
        if !controls.fire || gun.overheated {
            gun.fire_timer = (gun.fire_timer - dt).max(0.0);
            continue;
        }
        gun.fire_timer -= dt;
        let muzzles = &specs.ship[ship.spec].guns;
        while gun.fire_timer <= 0.0 && !gun.overheated {
            let muzzle = Vec3::from(muzzles[gun.barrel % muzzles.len()]);
            gun.barrel = (gun.barrel + 1) % muzzles.len();
            let dir = rot.0 * (Vec3::NEG_Z * t.converge - muzzle).normalize();
            let from = pos.0 + rot.0 * muzzle;
            let mut shot = commands.spawn((
                Name::new("Shot"),
                Projectile { velocity: v.0 + dir * t.gun_speed, life: t.gun_range / t.gun_speed, owner: entity, faction: *faction },
                streak(from, dir, t.gun_speed * dt),
            ));
            if let Some(look) = &look {
                shot.insert((Mesh3d(look.mesh.clone()), MeshMaterial3d(look.material.clone()), bevy::light::NotShadowCaster));
            }
            gun.fire_timer += 1.0 / (t.gun_rate * muzzles.len() as f32);
            gun.heat += t.heat_per_shot;
            if gun.heat >= 1.0 {
                gun.overheated = true;
            }
        }
    }
}

/// A shot's streak along its flight, a tick or two of travel long and thicker than any bullet,
/// so it reads from a kilometre off.
fn streak(at: Vec3, dir: Vec3, step: f32) -> Transform {
    Transform::from_translation(at).with_rotation(Quat::from_rotation_arc(Vec3::NEG_Z, dir)).with_scale(Vec3::new(0.5, 0.5, (step * 1.5).clamp(4.0, 40.0)))
}

/// Steps every shot: drag in air, then a ray along the step. A hull of another side takes the
/// damage; anything else it hits just stops it. Shots are dropped at a handoff to another world.
#[allow(clippy::too_many_arguments)]
fn fly_projectiles(
    mut commands: Commands,
    time: Res<Time>,
    tuning: Res<Tuning>,
    solar: Res<Solar>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    spatial: SpatialQuery,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut landed: MessageWriter<ShotLanded>,
    mut shots: Query<(Entity, &mut Projectile, &mut Transform)>,
    bodies: Query<&ColliderOf>,
    mut hulls: Query<(&mut Hull, &Faction)>,
    mut anchor: Local<String>,
) {
    let t = &tuning.ship_combat;
    let dt = time.delta_secs();
    let handoff = *anchor != solar.anchor;
    anchor.clone_from(&solar.anchor);
    let air = solar.anchor_body().air.as_ref().filter(|_| solar.anchor != super::orbit::STAR);
    for (entity, mut shot, mut tf) in &mut shots {
        shot.life -= dt;
        if shot.life <= 0.0 || handoff {
            commands.entity(entity).despawn();
            continue;
        }
        if let Some(air) = air {
            let density = air.density_at(surface.altitude(origin.body(tf.translation)));
            shot.velocity *= (-t.air_drag * density / 1.225 * dt).exp();
        }
        let Ok(dir) = Dir3::new(shot.velocity) else { continue };
        let step = shot.velocity.length() * dt;
        let filter = SpatialQueryFilter::from_excluded_entities([shot.owner, entity]);
        let Some(hit) = spatial.cast_ray(tf.translation, dir, step, true, &filter) else {
            *tf = streak(tf.translation + dir * step, *dir, t.gun_speed * dt);
            continue;
        };
        let point = tf.translation + dir * hit.distance;
        let body = bodies.get(hit.entity).map_or(hit.entity, |c| c.body);
        if body != shot.owner
            && let Ok((mut hull, faction)) = hulls.get_mut(body)
            && *faction != shot.faction
        {
            hull.hit_by(t.gun_damage, shot.owner, t);
            landed.write(ShotLanded { by: shot.owner, on: body });
        }
        if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
            spawn_blast(&mut commands, fx, materials, point - dir * 0.2, 0.8);
        }
        commands.entity(entity).despawn();
    }
}

/// A ship whose hull is gone blows apart, and says so in a `ShipDestroyed`. The one the player
/// flies is not removed from under its pilot here: `loss` takes it through the loss rule.
#[allow(clippy::type_complexity)]
pub(super) fn wreck(
    mut commands: Commands,
    specs: Res<Ships>,
    fx: Option<Res<FxAssets>>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
    mut destroyed: MessageWriter<ShipDestroyed>,
    ships: Query<(Entity, &Ship, &Hull, &Faction, &Transform)>,
) {
    for (entity, ship, hull, faction, tf) in &ships {
        if hull.hp > 0.0 {
            continue;
        }
        info!("{} destroyed", specs.ship[ship.spec].name);
        destroyed.write(ShipDestroyed { ship: entity, spec: ship.spec, faction: *faction, killer: hull.last_hit_by });
        if let (Some(fx), Some(materials)) = (&fx, materials.as_mut()) {
            let size = specs.ship[ship.spec].collider.first().map_or(Vec3::splat(4.0), |b| Vec3::from(b.size));
            spawn_blast(&mut commands, fx, materials, tf.translation, size.max_element() * 0.8);
            for corner in [Vec3::new(0.4, 0.2, -0.3), Vec3::new(-0.4, -0.1, 0.1), Vec3::new(0.1, 0.3, 0.4)] {
                spawn_blast(&mut commands, fx, materials, tf.translation + tf.rotation * (corner * size), size.max_element() * 0.45);
            }
        }
        if ship.pilot.is_none() {
            commands.entity(entity).despawn();
        }
    }
}
