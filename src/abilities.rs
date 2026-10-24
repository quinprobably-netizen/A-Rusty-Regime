//! Class abilities. The first is a Titanfall 2 style grapple: fire a hook at anything within range,
//! get pulled toward it with the pull bending toward where you look, keep every bit of speed when
//! you let go, and jump off the rope for a sling. It runs on a power meter, not a cooldown; the
//! meter is tuned to be nearly free (`[grapple]` in tuning.toml).

use avian3d::prelude::*;
use bevy::prelude::*;

use crate::character::Characters;
use crate::controller::{ControllerSet, Player};
use crate::input::{PlayerInput, ViewAngles};
use crate::surface::{Origin, Surface};
use crate::tuning::{GrappleTuning, Tuning};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Hook {
    pub anchor: Vec3,
    /// Current rope length; it only ever shortens, which is what makes swings work.
    pub rope: f32,
}

#[derive(Resource, Debug)]
pub struct GrappleState {
    /// The player's class has the grapple.
    pub enabled: bool,
    pub power: f32,
    pub hook: Option<Hook>,
}

impl GrappleState {
    pub fn hooked(&self) -> bool {
        self.hook.is_some()
    }
}

/// Marks the rope mesh entity.
#[derive(Component)]
struct Rope;

/// Which class the player is. Read from `characters.toml`; `pilot` unless `RUST_REGIME_CLASS` says otherwise.
#[derive(Resource, Clone, Debug, PartialEq)]
pub struct Class(pub String);

impl Default for Class {
    fn default() -> Self {
        Class(std::env::var("RUST_REGIME_CLASS").unwrap_or_else(|_| "pilot".into()))
    }
}

pub struct AbilitiesPlugin;

impl Plugin for AbilitiesPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Class>()
            .add_systems(Startup, setup)
            .add_systems(FixedUpdate, grapple_tick.before(ControllerSet))
            .add_systems(PostUpdate, draw_rope.before(TransformSystems::Propagate));
    }
}

fn setup(mut commands: Commands, tuning: Res<Tuning>, class: Res<Class>, characters: Res<Characters>) {
    commands.insert_resource(GrappleState { enabled: has_grapple(&characters, &class), power: tuning.grapple.power_max, hook: None });
}

pub fn has_grapple(characters: &Characters, class: &Class) -> bool {
    characters.class.get(&class.0).is_some_and(|c| c.ability == "grapple")
}

// ----------------------------------------------------------------------------------- pure math

/// Where the pull goes: the rope direction bent toward the look direction when you look roughly at
/// the anchor, so you can steer over or around it like in Titanfall.
pub fn pull_direction(to_anchor: Vec3, look: Vec3, t: &GrappleTuning) -> Vec3 {
    let rope = to_anchor.normalize_or_zero();
    if look.dot(rope) <= 0.0 {
        return rope;
    }
    rope.lerp(look, t.look_steer).normalize_or_zero()
}

/// One tick of pull on `v`: accelerate along the pull, cap the speed along it, and never let the
/// rope stretch: velocity away from the anchor past the rope length is clipped, which is the swing.
pub fn pull_velocity(v: Vec3, eye: Vec3, hook: &Hook, look: Vec3, t: &GrappleTuning, dt: f32) -> Vec3 {
    let to_anchor = hook.anchor - eye;
    let dir = pull_direction(to_anchor, look, t);
    let mut v = v + dir * t.pull_accel * dt;
    let along = v.dot(dir);
    if along > t.pull_max_speed {
        v -= dir * (along - t.pull_max_speed);
    }
    let rope = to_anchor.normalize_or_zero();
    if to_anchor.length() >= hook.rope && v.dot(rope) < 0.0 {
        v -= rope * v.dot(rope);
    }
    v
}

/// Power after `dt` seconds, pulling or not. Clamped to `[0, power_max]`.
pub fn power_step(power: f32, pulling: bool, t: &GrappleTuning, dt: f32) -> f32 {
    let p = if pulling { power - t.power_use_rate * dt } else { power + t.power_regen * dt };
    p.clamp(0.0, t.power_max)
}

// -------------------------------------------------------------------------------------- systems

#[allow(clippy::too_many_arguments)]
fn grapple_tick(
    time: Res<Time>,
    tuning: Res<Tuning>,
    surface: Res<Surface>,
    origin: Res<Origin>,
    view: Res<ViewAngles>,
    characters: Res<Characters>,
    class: Res<Class>,
    mut input: ResMut<PlayerInput>,
    mut state: ResMut<GrappleState>,
    spatial: SpatialQuery,
    mut player: Single<(Entity, &mut Player, &Transform)>,
) {
    let t = &tuning.grapple;
    let dt = time.delta_secs();
    if characters.is_changed() {
        state.enabled = has_grapple(&characters, &class);
    }
    let pressed = std::mem::take(&mut input.ability_pressed);
    let (entity, p, tf) = &mut *player;
    let eye = tf.translation + p.up() * p.eye_offset(&tuning);
    let look = view.rotation() * Vec3::NEG_Z;
    let filter = SpatialQueryFilter::from_excluded_entities([*entity]);

    if !state.enabled {
        state.hook = None;
        state.power = power_step(state.power, false, t, dt);
        return;
    }

    if let Some(hook) = state.hook {
        let to_anchor = hook.anchor - eye;
        let dist = to_anchor.length();
        // Anchor hidden behind something: the rope is cut.
        let blocked = dist > 0.5
            && spatial
                .cast_ray(eye, Dir3::new(to_anchor).unwrap_or(Dir3::Y), dist - 0.3, true, &filter)
                .is_some();
        let let_go = pressed || input.jump_pressed || state.power <= 0.0 || dist < t.arrive_distance || dist > t.range * 1.5 || blocked;
        if let_go {
            if input.jump_pressed {
                let boost = p.velocity.normalize_or_zero() * t.release_boost;
                p.velocity += boost;
            }
            state.hook = None;
        } else {
            p.velocity = pull_velocity(p.velocity, eye, &Hook { anchor: hook.anchor, rope: hook.rope }, look, t, dt);
            // The taut rope carries most of your weight, so a low anchor still lifts you.
            let g = surface.gravity(origin.body(tf.translation), tuning.gravity).length();
            let up = p.up();
            p.velocity += up * g * t.gravity_cancel * dt;
            // Being pulled counts as airborne: no ground snap, air jumps refunded.
            p.knockback_lock = dt * 2.0;
            p.air_jumps_left = tuning.air_jumps;
            state.hook = Some(Hook { anchor: hook.anchor, rope: hook.rope.min(dist) });
            state.power = power_step(state.power, true, t, dt);
            return;
        }
    } else if pressed && state.power >= t.power_to_fire {
        if let Some(hit) = spatial.cast_ray(eye, Dir3::new(look).unwrap_or(Dir3::NEG_Z), t.range, true, &filter) {
            let anchor = eye + look * hit.distance;
            state.hook = Some(Hook { anchor, rope: hit.distance });
            p.air_jumps_left = tuning.air_jumps;
            return;
        }
    }
    state.power = power_step(state.power, false, t, dt);
}

/// A thin cylinder from the left hand to the anchor while hooked.
fn draw_rope(
    mut commands: Commands,
    state: Res<GrappleState>,
    tuning: Res<Tuning>,
    view: Res<ViewAngles>,
    fixed: Res<Time<Fixed>>,
    meshes: Option<ResMut<Assets<Mesh>>>,
    materials: Option<ResMut<Assets<StandardMaterial>>>,
    player: Single<(&Player, &Transform)>,
    mut rope: Query<(Entity, &mut Transform), (With<Rope>, Without<Player>)>,
) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    let Some(hook) = state.hook else {
        for (e, _) in &rope {
            commands.entity(e).despawn();
        }
        return;
    };
    let (p, tf) = *player;
    let center = p.prev_pos.lerp(tf.translation, fixed.overstep_fraction());
    let (forward, right) = view.flat_basis();
    let hand = center + p.up() * (p.eye_offset(&tuning) - 0.35) - right * 0.25 + forward * 0.3;
    let to = hook.anchor - hand;
    let len = to.length().max(0.01);
    let transform = Transform {
        translation: hand + to * 0.5,
        rotation: Quat::from_rotation_arc(Vec3::Y, to / len),
        scale: Vec3::new(1.0, len, 1.0),
    };
    if let Ok((_, mut tf)) = rope.single_mut() {
        *tf = transform;
    } else {
        commands.spawn((
            Rope,
            Name::new("Grapple rope"),
            Mesh3d(meshes.add(Cylinder::new(0.012, 1.0))),
            MeshMaterial3d(materials.add(StandardMaterial { base_color: Color::srgb(0.25, 0.22, 0.18), unlit: true, ..default() })),
            transform,
        ));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t() -> GrappleTuning {
        GrappleTuning::default()
    }

    #[test]
    fn pull_bends_toward_look_only_when_looking_at_the_anchor() {
        let t = t();
        let up = Vec3::Y * 10.0;
        let d = pull_direction(up, Vec3::new(0.0, 0.7, -0.7).normalize(), &t);
        assert!(d.z < -0.2 && d.y > 0.5, "{d}");
        let away = pull_direction(up, Vec3::NEG_Y, &t);
        assert_eq!(away, Vec3::Y);
    }

    #[test]
    fn pull_accelerates_and_caps() {
        let t = t();
        let hook = Hook { anchor: Vec3::new(0.0, 20.0, 0.0), rope: 20.0 };
        let mut v = Vec3::ZERO;
        for _ in 0..200 {
            v = pull_velocity(v, Vec3::ZERO, &hook, Vec3::Y, &t, 1.0 / 66.0);
        }
        assert!((v.y - t.pull_max_speed).abs() < 0.01, "{v}");
    }

    #[test]
    fn rope_never_stretches() {
        let t = t();
        let hook = Hook { anchor: Vec3::new(0.0, 10.0, 0.0), rope: 10.0 };
        // Falling straight away from an anchor at full rope: the downward part is removed.
        let v = pull_velocity(Vec3::new(5.0, -8.0, 0.0), Vec3::ZERO, &hook, Vec3::NEG_Z, &t, 0.0);
        assert!(v.y >= 0.0 && (v.x - 5.0).abs() < 1e-5, "{v}");
    }

    #[test]
    fn power_drains_and_refills() {
        let t = t();
        let p = power_step(t.power_max, true, &t, 1.0);
        assert!((p - (t.power_max - t.power_use_rate)).abs() < 1e-4);
        assert_eq!(power_step(0.0, true, &t, 1.0), 0.0);
        assert_eq!(power_step(t.power_max - 1.0, false, &t, 1.0), t.power_max);
    }
}
