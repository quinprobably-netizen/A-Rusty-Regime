# Stages 2 and 3: extraction loop, missions, bots (done 2026-10-17)

## Extraction loop (`src/loot.rs`)
- `Loot { value, key, down }` caches spawned by `island.rs` at every site (tower and lighthouse tops pay 80,
  the quarry pit holds the mission cache) and ten in the wilderness ring; walk within `loot.pickup_radius`
  to carry them; they come back after `loot.respawn` seconds.
- Three `ExtractPad`s placed by `island::place` on dry, gentle ground inward from the coast (sites 6-8, so
  the terrain stamps them flat). Standing on one with a haul for `loot.extract_time` banks it, counts a run,
  writes the save and resets you to base camp.
- `Save` (banked, runs, deaths, missions_done) in `save.toml`; `SaveFile(None)` keeps tests off the disk.
- Death zeroes the carried value and brings mission caches back within 2 s.

## Missions (`src/mission.rs`)
Six fixed missions over the sites (reach, kill-count, collect, extract-with, drive, reach). `Killed`
messages from `targets::take_damage` feed kill counts; losing the cache steps the chain back. The HUD line
comes from `ObjectiveHud` (text, distance, bearing relative to the view).

## Teams and bots (`src/bots.rs`, `targets.rs`)
- `Team(u8)` on soldiers (island patrols are team 1, the player is team 0). `soldier_ai` now picks the
  nearest visible enemy among the player and other teams' soldiers, damages soldiers through `Damage`,
  closes to `soldier.hold`, chases the last seen spot, and follows the heightmap when it moves.
- `RUST_REGIME_MODE=6v6` adds `MatchPlugin`: spawn at the fort gate, five blue and six red bots on looping
  routes through the fort, `MatchState` score, first to `match.kills_to_win`, then an 8 s banner and reset.
- No netcode (spec: only if still wanted).

## Tests
5 new (40 total): loot carried/banked/lost, save round trip, missions in order with the cache-loss step
back, cross-team fights, 6v6 setup and scoring.
