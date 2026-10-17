# Island sites and enemies (stage 1, steps 2 to 4) Implementation Plan

**Goal:** The island fights back and has places to climb: patrolling soldiers that shoot, player health with a HUD bar, and the six sites from the spec.

**Spec:** `docs/superpowers/specs/2026-10-17-island-hub-design.md` (Points of interest, Enemies, Tuning, Tests).

**Architecture:** `targets.rs` grows a `Soldier` component (waypoint route, alert timer, fire cooldown) next to the dummies and drones; `health.rs` owns `PlayerHealth`, the `PlayerHit` message, regen and death-respawn; `island.rs` resolves the six site positions on the heightmap, stamps their pads, and builds each one from generated blocks and Kenney props with a small `Builder`. The arena is untouched.

## Tasks

1. **`[soldier]` and `[player]` tables** in `tuning.rs` / `tuning.toml` with the spec's values (soldier spread 0.02 rad so they hit at short range).
2. **Player health** (`src/health.rs`): `PlayerHealth { hp, max, since_hit, dead_for }` resource, `PlayerHit { amount }` message, FixedUpdate system: apply hits, regen after `regen_delay`, death sets `dead_for`, respawn through `PlayerInput::reset_pressed` and refill. Test: `player_dies_and_respawns_with_full_health`.
3. **Soldiers** (`src/targets.rs`): `TargetKind::Soldier`, `Soldier { route: Vec<Vec3>, next, alert: Option<f32>, fire_cd }`, `spawn_soldier(commands, tuning, assets, route)`. `soldier_ai` in FixedUpdate: patrol along the route at `speed`; within `sight` with a clear ray to the player's eye, stop, face, fire every `fire_interval` with `spread`; lose interest after `forget` seconds without a line of sight. Death falls like a dummy, respawn like a dummy but kinematic. Tests: `soldier_shoots_player_in_sight`, `soldier_ignores_player_behind_wall`, `soldier_forgets_hidden_player`.
4. **HUD** (`src/hud.rs`): health bar bottom center, red overlay flash on hit, stays while dead.
5. **Sites** (`src/island.rs`): `Site` list resolved by `place(hm, island) -> Vec<Placed>` (base camp south, fort east, quarry west, ruins north, tower on the highest core sample, lighthouse on the south coast), pads stamped (quarry as four descending rings), spawn at base camp. `Builder` with `block`, `prop`, `dynamic`, `soldier`, `drone`. Test: `site_pads_are_flat_and_above_water`.
6. **Screenshots, package, push**: one shot per site where cheap, tarball and zip, PR #1 updated.
