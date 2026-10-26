//! The optional 6v6 mode (`RUST_REGIME_MODE=6v6`): you and five bots against six bots at the fort, first
//! team to `match.kills_to_win` wins and the scores reset. Bots are the island's soldiers with a `Team`;
//! their aiming, chasing and shooting live in `targets::soldier_ai`.

use bevy::prelude::*;

use crate::controller::WorldBounds;
use crate::health::PlayerHealth;
use crate::island::Sites;
use crate::targets::{self, Killed, TargetAssets, TargetKind, Team};
use crate::terrain::Heightmap;
use crate::tuning::Tuning;

pub struct MatchPlugin;

impl Plugin for MatchPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<MatchState>()
            .add_systems(OnEnter(crate::boot::Boot::Ready), setup.after(crate::island::spawn_sites))
            .add_systems(FixedUpdate, score.after(targets::TargetSet));
    }
}

const FORT: usize = 2;

#[derive(Resource, Debug, Default)]
pub struct MatchState {
    /// Kills by team 0 (you and the blue bots) and team 1 (red).
    pub score: [u32; 2],
    /// Seconds left showing the winner before the scores reset.
    pub over: Option<(u8, f32)>,
    was_alive: bool,
}

/// Puts the player at the fort gate and fills both teams.
fn setup(mut commands: Commands, tuning: Res<Tuning>, sites: Option<Res<Sites>>, assets: Option<Res<TargetAssets>>, heightmap: Option<Res<Heightmap>>, mut bounds: ResMut<WorldBounds>) {
    let Some(sites) = sites else { return };
    let Some(fort) = sites.0.get(FORT) else { return };
    let o = fort.origin();
    let ground = |x: f32, z: f32| Vec3::new(o.x + x, heightmap.as_ref().map_or(o.y, |hm| hm.height_at(o.x + x, o.z + z)), o.z + z);
    bounds.spawn = ground(-52.0, 0.0) + Vec3::Y;
    let n = tuning.r#match.bots_per_team as usize;
    // Blue bots start outside the west gate and push in; red bots hold the east half and come out to meet them.
    for i in 0..n.saturating_sub(1) {
        let z = -12.0 + 6.0 * i as f32;
        let route = vec![ground(-46.0, z), ground(-20.0, z * 0.5), ground(0.0, z), ground(-30.0, -z)];
        targets::spawn_soldier_team(&mut commands, &tuning, assets.as_deref(), route, Team(0));
    }
    for i in 0..n {
        let z = -15.0 + 6.0 * i as f32;
        let route = vec![ground(28.0, z), ground(10.0, -z * 0.5), ground(-10.0, z), ground(20.0, -z)];
        targets::spawn_soldier_team(&mut commands, &tuning, assets.as_deref(), route, Team(1));
    }
}

fn score(time: Res<Time>, tuning: Res<Tuning>, health: Res<PlayerHealth>, mut killed: MessageReader<Killed>, mut state: ResMut<MatchState>) {
    let dt = time.delta_secs();
    if let Some((_, left)) = state.over.as_mut() {
        *left -= dt;
        killed.clear();
        if *left <= 0.0 {
            state.over = None;
            state.score = [0, 0];
        }
        return;
    }
    for k in killed.read() {
        if k.kind == TargetKind::Soldier {
            let scorer = if k.team.0 == 0 { 1 } else { 0 };
            state.score[scorer] += 1;
        }
    }
    let alive = health.alive();
    if state.was_alive && !alive {
        state.score[1] += 1;
    }
    state.was_alive = alive;
    for team in 0..2 {
        if state.score[team] >= tuning.r#match.kills_to_win {
            state.over = Some((team as u8, 8.0));
        }
    }
}
