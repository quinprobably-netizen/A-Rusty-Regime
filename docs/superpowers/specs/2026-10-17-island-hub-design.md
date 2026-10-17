# Island Hub — Stage 1 design

Date: 2026-10-17. Status: draft for Q's approval.

## Goal

Replace the walled 120 m arena with a 4 km island that every later stage
builds on: extraction loop, story missions, and the optional 6v6 bot mode.
The result of stage 1 is playable on its own: run, parkour and fight across
an island with roaming soldiers and drones, die, respawn.

What stays: all movement, weapons, viewmodels, the player body, tuning.toml
with F5 reload, the headless test harness. What goes: nothing. The arena
stays reachable (`RUST_REGIME_LEVEL=arena`) because the tests and the
parkour course use it.

Out of scope for stage 1 (they are stages 2+): loot and inventory, extract
points, missions, a map or objective markers, saving, multiplayer, sound
beyond what exists.

## Non-negotiables

- Free only: no paid assets, no services. Models are Kenney CC0 plus
  generated meshes. One new crate, `fastnoise-lite` (MIT, no dependencies).
- Deterministic: the island is generated from `island.seed` in tuning.toml.
  Same seed, same island, so tests and bug reports are reproducible.
- No streaming: 4 km at 4 m resolution is about 1 million vertices, a
  few tens of MB of mesh and collider data, which Bevy renders fine when
  split into chunks and generates in well under a second. This is the
  largest size that stays simple; going past it means streaming and
  far-terrain LOD, which we do not build.
- Big island, small core: the six stage 1 sites sit inside a 1.5 km core
  so runs between them stay under a minute. The outer ring is wilderness
  reserved for later stages (extraction zones, missions) and for the
  traversal stage below.

## World

**Terrain** (`src/terrain.rs`). A 4096 m square heightmap, 4 m per cell
(1025 by 1025 samples). Four meters is coarse enough to stay at a million
vertices and fine enough for hills and cliffs; close-up detail comes from
the sites and props, not the ground mesh. Height comes from layered simplex noise times a radial
island mask, so the coast falls below water on every side. Stamps flatten
pads for the points of interest before the mesh is built. The heightmap is
a plain resource (`Heightmap { size, step, heights: Vec<f32> }`) with
`height_at(x, z)` and `normal_at(x, z)`, used by the mesh builder, the
collider, enemy placement and tests alike.

The mesh is built in 32 by 32 cell chunks (32 by 32 chunks), indexed with
smooth normals (unindexed flat shading would triple the vertex count),
vertex colored by height and slope: sand near the water, grass, rock on
steep faces, snow on the peaks. Each chunk is a static body with
`Collider::heightfield` from the same samples, so what you see is what you
stand on. Slopes over `walkable_normal_y` (about 45 degrees) are surfable
like the arena ramps, which makes mountainsides part of the movement.

**Water.** A flat plane at y = 0. Dropping below `island.water_level` minus
2 m respawns the player, same as falling out of the arena today.

**Sky and light.** Keep the directional light and clear color. Add a
distance fog so the far coast fades instead of popping, and cascaded shadow
settings tuned for 4 km.

## Points of interest

Six handmade sites (`src/island.rs`), each on a flattened pad, built from
generated meshes plus Kenney props the way `spawn_props` does today. Each
is a parkour toy first and a fight second:

All six sit in the 1.5 km core around the island's center.

1. **Base camp** (center-south): player spawn, weapon racks, crates,
   columns. Safe, no enemies.
2. **Radio tower** (highest peak): a 40 m lattice tower climbed by wall
   jumps and mantles, drones circling it.
3. **Fort** (east): walls to wall-run, a courtyard with soldiers, the
   mantle tower and chimney from the arena course rebuilt into it.
4. **Quarry** (west): terraced pit, slide down the ramps, surf the faces,
   soldiers on the terraces.
5. **Ruins** (north): broken columns and statues, a bridge over a ravine
   that is the island's wall-run gap.
6. **Lighthouse** (coast): spiral of blocks around a tower, drones.

The arena's physics playground (dominoes, barrels, balls) moves into base
camp so rocket jumping still has toys.

## Enemies

`targets.rs` grows one kind, `TargetKind::Soldier`, next to Dummy and
Drone. Soldiers walk a waypoint loop around their site at `soldier_speed`,
kinematic, feet snapped to `height_at`. Within `soldier_sight` meters and
line of sight to the player they stop, face the player and fire a hitscan
shot every `soldier_fire_interval` seconds for `soldier_damage`, with a
spread so they miss at range. They lose interest after `soldier_forget`
seconds without line of sight and resume the loop. They use the existing
soldier model, animations and ragdoll-style fall on death, and respawn after
`target_respawn` like everything else. Drones keep circling, now around
tower and lighthouse.

Patrol routes, aggro and firing are a small state machine
(`Patrol`, `Alert { since }`) that lives on the `Target` so the 6v6 bot
stage can later reuse it for bots that hunt.

**Player health** (`src/health.rs`): 100 hp, regenerates after 5 s without
damage, a red screen flash on hit, death respawns at base camp after 2 s.
The HUD gets a health bar; the score counter stays.

## Tuning

New tables in tuning.toml, all F5 reloadable:

```
[island]
seed = 7
size = 4096          # meters
cell = 4             # meters per heightmap sample
core = 1500          # meters, the sites stay inside this
height = 180         # peak height in meters
water_level = 0.0

[soldier]
health = 100
speed = 3.5
sight = 40
fire_interval = 0.6
damage = 12
spread = 0.05
forget = 4.0

[player]
health = 100
regen_delay = 5.0
regen_rate = 20
```

## Files

- `src/terrain.rs` new: heightmap, noise, stamps, chunk meshes, colliders.
- `src/island.rs` new: the six sites and player spawn; replaces
  `level.rs` as the default level. `level.rs` stays as the arena.
- `src/targets.rs`: Soldier kind, patrol and aggro.
- `src/health.rs` new: player health, regen, death and respawn.
- `src/hud.rs`: health bar and hit flash.
- `src/tuning.rs`, `tuning.toml`: the tables above.
- `src/main.rs`: pick level from `RUST_REGIME_LEVEL` (default island).

## Build order

Each step ends in something you can run:

1. Terrain with colliders, water, fog. Run around an empty island.
2. Base camp and radio tower, the two sites that prove the parkour.
3. Soldiers, player health, HUD. The island fights back.
4. The other four sites.

**Stage 1b, vehicles.** A 4 km island needs a fast way across it. Q's
decision (2026-10-17): reuse the vehicle physics from Regolith Rally
(github.com/quinprobably-netizen/tesat, `rust/src/physics`, about 5.6k lines
of engine-free f64 math: tyres, suspension, gearbox, driveline and a
soft-body frame, with a `GroundSource` trait the island heightmap
implements directly) and build custom vehicle models for this game in
code, the way Regolith builds its car bodies from lofts and parts. First
vehicle: an open buggy. The physics is vendored into `src/vehicle/` with a
one-command refresh script rather than a git dependency, because the rally
crate is a wasm build with its own renderer. Cars are kinematic Avian bodies
so the player and rockets interact with them; driving hands the camera and
input to the car. Its own spec once step 1 is playable.

## Tests (headless, in tests.rs)

- Same seed gives identical heightmaps; a different seed does not.
- Every site pad is flat within 5 cm and above water.
- `height_at` agrees with the heightfield collider for random points.
- A soldier in sight of the player switches to Alert and damages it; one
  behind a wall does not; it forgets after `forget` seconds.
- Player below water level is respawned at base camp with full health.

## Risks

- Terrain colliders and 66 Hz stair stepping: the controller's step logic
  assumes box edges. Heightfield slopes should be fine but step 1 is the
  place to find out, before any content exists.
- Shadow quality across 1 km with one directional light needs cascade
  tuning; worst case the far distance just has no shadows.
- The build is already about 15 minutes cold on 4 cores; the new crate adds
  nothing noticeable.
- A million-vertex static world plus a thousand chunk colliders is fine on
  a discrete GPU; an integrated GPU may need `island.cell = 8`. Step 1
  measures frame time and memory before any content exists.
