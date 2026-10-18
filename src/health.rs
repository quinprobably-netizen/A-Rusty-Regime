//! Player health: soldiers write `PlayerHit`, health regenerates after a
//! quiet spell, and death respawns through the controller's reset.

use bevy::prelude::*;

use crate::controller::ControllerSet;
use crate::input::PlayerInput;
use crate::tuning::Tuning;

pub struct HealthPlugin;

impl Plugin for HealthPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PlayerHealth>()
            .add_message::<PlayerHit>()
            .add_systems(FixedUpdate, tick.before(ControllerSet));
    }
}

#[derive(Message, Debug, Clone, Copy)]
pub struct PlayerHit {
    pub amount: f32,
}

#[derive(Resource, Debug, Clone)]
pub struct PlayerHealth {
    pub hp: f32,
    pub max: f32,
    /// Seconds since the last hit.
    pub since_hit: f32,
    /// Seconds until respawn while dead.
    pub dead_for: Option<f32>,
    /// Set for one tick when a hit lands, for the HUD flash.
    pub hit_this_tick: bool,
    /// Seconds of bleeding left.
    pub bleeding: f32,
}

impl Default for PlayerHealth {
    fn default() -> Self {
        Self { hp: 100.0, max: 100.0, since_hit: 1e9, dead_for: None, hit_this_tick: false, bleeding: 0.0 }
    }
}

impl PlayerHealth {
    pub fn alive(&self) -> bool {
        self.dead_for.is_none()
    }

    /// A medkit: full health and the bleeding stops.
    pub fn heal(&mut self) {
        self.hp = self.max;
        self.bleeding = 0.0;
    }
}

fn tick(time: Res<Time>, tuning: Res<Tuning>, mut hits: MessageReader<PlayerHit>, mut health: ResMut<PlayerHealth>, mut input: ResMut<PlayerInput>) {
    let dt = time.delta_secs();
    let t = &tuning.player;
    health.max = t.health;
    health.hit_this_tick = false;
    if let Some(left) = health.dead_for.as_mut() {
        *left -= dt;
        hits.clear();
        if *left <= 0.0 {
            health.dead_for = None;
            health.hp = t.health;
            health.since_hit = 1e9;
            health.bleeding = 0.0;
            input.reset_pressed = true;
        }
        return;
    }
    for hit in hits.read() {
        health.hp -= hit.amount;
        health.since_hit = 0.0;
        health.hit_this_tick = true;
        if hit.amount >= t.bleed_threshold {
            health.bleeding = t.bleed_time;
        }
    }
    if health.bleeding > 0.0 {
        health.bleeding -= dt;
        health.hp -= t.bleed_rate * dt;
    }
    if health.hp <= 0.0 {
        health.hp = 0.0;
        health.dead_for = Some(t.respawn_delay);
        return;
    }
    health.since_hit += dt;
    let cap = t.health * t.regen_cap;
    if health.bleeding <= 0.0 && health.since_hit >= t.regen_delay && health.hp < cap {
        health.hp = (health.hp + t.regen_rate * dt).min(cap);
    }
}
