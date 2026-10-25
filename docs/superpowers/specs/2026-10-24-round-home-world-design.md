# Round home world (solar system sub-project 1) design

Date: 2026-10-24. Agreed with Q section by section in the open-world brainstorm; written for Q's
review before the implementation plan. Programme context, decomposition and the frame decision:
`2026-10-24-solar-system-programme.md`.

## Goal

Put the current game on a sphere. The island becomes the populated core of a continent on a
17.5 km radius home world; gravity points at the centre everywhere; the terrain is built at
0.5 m cells under your feet and streamed around you; day and night come from the world's spin.
Playable on its own: every system that works today works on the globe, and you can drive off the
island and across the continent.

What stays: all movement math, weapons, viewmodels, arms, characters, vehicles, menus, gunsmith,
wardrobe, sound, loot, missions, extraction, 6v6, `tuning.toml` with F5 reload, the headless
test harness. What goes: the flat `Heightmap` grid and the `[island]` table.

Out of scope, in later sub-projects: the ship and anything in space, orbits and anchor switching
(the home world is the only body and the only anchor here), the atmosphere-as-fluid model,
swimming and buoyancy (falling in the sea still respawns you), other worlds, destruction, new
play loops.

## Decisions and why

- **Earth gravity.** g = 9.8 m/s² at sea level on the home world, everywhere else too (the arena
  and the tests). Jump heights are kept by retuning speeds once (table under Tuning). Rocket and
  grenade jumps keep their heights the same way. Hang times get about a third longer; slides
  accelerate half as hard downhill; cars corner at a realistic 1 g instead of 1.8 g. The vehicle
  code drops its `g / 9.81` brake fudge. Gravity falls off as g0 (R/r)²; on the ground that is
  constant and it matters once the ship exists.
- **0.5 m finest cells with finer noise.** Today's noise has six octaves and no detail under
  about 43 m of wavelength, so finer cells alone would show smoother hills. The height function
  gains two octaves (down to about 10 m) and a rubble layer at 1 to 2 m. Each halving of the cell
  adds one quadtree depth, about 40 chunks and 80 k triangles, and halves the radius of the finest
  ring: at 0.5 m the finest ring reaches about 40 m, and a vehicle at 30 m/s asks for about ten
  chunk builds a second, which four workers cover. `terrain.cell = 1` is the fallback for a weak
  machine.
- **The player's frame is carried, not looked up.** No pole where the controls flip; true north
  is computed separately for the compass.
- **The home landmass is a continent.** Otherwise the sphere would be invisible until the ship
  exists.

## World model

### Bodies: `assets/system.toml`

A new data file declares the star and every world as a `[body.<id>]` table. This sub-project
reads only the home body; sub-projects 2 and 3 add orbits, atmospheres and the other worlds to
the same file. Body parameters are read at startup, not on F5: regenerating a planet is not a hot
reload.

```toml
[body.home]
radius = 17500       # m
gravity = 9.8        # m/s² at sea level
day_minutes = 48     # one rotation in real minutes; moves here from [world]
tilt = 12            # axial tilt, degrees; the star's declination this far north until orbits exist
sea_level = 0        # m above radius
seed = 7
height = 900         # tallest peaks above the sea, m
land = 0.3           # fraction of the surface above water
# The home continent: about 35 km across, with the 4 km island region at its heart where the
# six sites go. Latitude and longitude in degrees.
home = { lat = 12, lon = 40, core = 4000, continent = 35000 }
```

### The `Surface` resource (`src/surface.rs`)

`Heightmap` goes. A `Surface` resource replaces it and is the one thing terrain, colliders,
sites, roads, vegetation, soldiers, grass, the camera and the tests query. Two variants share the
API: `Flat` (up is +Y, ground is the plane `y = 0`, gravity is `tuning.gravity` down -Y) for the
arena and the existing tests, and `Sphere` for a body.

- `height(dir: Vec3) -> f32`: terrain height above sea level along a unit direction from the
  centre. A pure function of the seed and the direction, in this order:
  1. **Relief.** Eight octaves of 3D OpenSimplex (fastnoise-lite `get_noise_3d` at `dir * R`),
     base wavelength about a quarter of the radius, gain 0.55, shaped `(0.5 + 0.5 n)^1.6` as
     today, times `height`.
  2. **Continents.** A low-frequency 3D noise thresholded so the land fraction is `land`;
     below the threshold the relief is pulled under the sea with the same smoothstep the island
     uses at its coast.
  3. **The home continent.** Within `continent / 2` geodesic metres of `home` the mask is forced
     to land, blended over the outer 20 percent of that radius into the global mask. Within
     `core / 2` of `home` the island formula applies exactly as today, with geodesic distance in
     place of planar distance, so the island keeps its character.
  4. **Rubble.** Two cheap value-noise layers at 1 to 2 m wavelength and 0.15 m amplitude,
     damped to zero on sand and inside stamps.
  5. **Stamps.** The site pads, applied last so they win.
  6. **Roads.** The carve, applied last of all (roads cross pads' edges but never their flat
     discs).
- `ground(p: Vec3) -> Ground { point, normal }`: the surface point and normal under a world
  position, replacing `height_at` and `normal_at`. When the finest terrain chunk under `p` is
  loaded it interpolates that chunk's vertex grid, so it matches the collider exactly, as today.
  Otherwise it evaluates `height` and its neighbours.
- `up(p)`, `altitude(p)`, `gravity(p) -> Vec3` (magnitude g0 (R/r)², toward the centre),
  `frame(p) -> Quat` (local +Y up, local -Z toward the spin axis, local +X east),
  `north(p) -> Option<Vec3>` (None within 5 m of a pole).

**Stamps flatten to the tangent plane** at the stamp's centre, not to a constant radius: for a
direction `d` inside the pad, the surface point is the intersection of the ray along `d` with the
plane through the pad centre perpendicular to the centre's up, blended back to the relief over
`blend` metres beyond `radius`. Over a 50 m pad the difference from a constant radius is 7 cm on
the home world and 60 cm on a 2 km moon, enough to sink a wall. The quarry's four descending rings
are four stamps, as now.

### Coordinates and the sliding origin (`src/planet/origin.rs`)

Body coordinates are metres from the body's centre in the body-fixed frame. They are what the
generator, the sites and anything stored for longer than a frame use. The render and physics
origin is a point in body coordinates held by the `Origin` resource:

- `Origin { offset: Vec3 }`, with `world(body: Vec3) -> Vec3` and `body(world: Vec3) -> Vec3`.
- **Rebase.** When the player is more than `terrain.origin_step` (2 km) from the origin, a system
  at the start of `FixedUpdate`, before the controller, vehicles and the physics step, moves the
  origin to the player's position quantized to 36 m (a multiple of every texture tile and the
  wave length, so world-space triplanar textures and the waves land exactly where they were) and
  subtracts the difference from every root entity's `Transform`, every Avian `Position`, and the
  interpolation caches Avian keeps for `TransformInterpolation` bodies, plus `Player.prev_pos`
  and an active mantle's points. One frame, a few thousand entities.
- **What stores body coordinates and converts on use:** `Sites` and each `Placed`, soldier
  routes, last-seen spots and cover targets, drone centres, vehicle home spots, the grapple
  anchor, `WorldBounds.spawn`, `Roads`, vegetation cells. Everything else is a `Transform` on a
  root entity and is shifted by the rebase.

## Terrain engine (`src/planet/`)

**Cube-sphere quadtree (`quadtree.rs`).** Six cube faces, each a quadtree. A node at depth `d`
covers `1 / 2^d` of its face in face coordinates `(u, v) ∈ [-1, 1]`, warped with
`u' = tan(u π/4)` so cells are near-equal in angle, and projected to the unit sphere. Every node,
at every depth, is a 33 by 33 vertex grid (32 cells). The finest depth per body is the first depth
whose cell is at or under `terrain.cell`: depth 11 on the home world (0.42 m), depth 8 on a 2 km
moon (0.38 m). A node splits when the point the camera will be at in one second (position plus
velocity) is nearer than `terrain.split` (2.5) times the node's size, and merges past `split +
0.5`. That gives about 40 leaf chunks per depth, roughly 480 chunks and about a million triangles
on the home world, with the finest ring reaching about 40 m and each coarser ring twice as far.

**Chunk builds (`chunk.rs`).** A worker task on Bevy's `AsyncComputeTaskPool` evaluates `height`
for the 33 by 33 grid plus a one-cell apron, and produces:

- positions relative to the chunk centre (f32 never holds a 17 km number inside a mesh),
- normals from the apron,
- splat weights in vertex colours from `splat_weights(dir, altitude, dot(normal, up))`, the
  current function with altitude for height and the dot product for `normal_y`, plus the road
  blend as today,
- a skirt: the border ring duplicated and pulled toward the centre by 5 percent of the chunk size
  (at least 1 m), so neighbours of different depths meet without cracks,
- for leaf chunks inside the physics bubble, a triangle-mesh collider at the chunk's own
  resolution.

At most two finished chunks are applied per frame and `terrain.workers` (4) tasks run at once.
Chunks directly under the player are always finest, so the ground under your feet never swaps
resolution; only distant chunks do.

**The physics bubble (`bubble.rs`).** Colliders exist only for leaf chunks within
`terrain.bubble` (400 m, past the longest bullet) of the player. A dynamic body farther than the
bubble, or whose ground chunk has no collider yet, gets `RigidBodyDisabled` and a `Frozen` marker;
it wakes when it is within `bubble - 50` m and its ground chunk is solid. Parked vehicles and
site props freeze this way. Soldiers and drones never needed colliders under them: soldiers snap
their feet with `ground`, drones circle at a set altitude. Trees carry their trunk collider only
while inside the bubble.

**Sites stream (`island.rs`).** A site's contents spawn when the player is within
`terrain.site_range` (1.5 km) of its centre and despawn past `site_range + 500`. A `SiteState`
per site keeps loot `down` timers and soldier dead-and-respawn timers; props are rebuilt fresh on
load. Vehicles are few and carry fuel and hull, so they are never despawned, only frozen. On the
island all six sites are usually loaded; the rule is what lets sub-project 3 scatter sites over
whole worlds.

**Vegetation (`veg.rs`).** Placement keys on quadtree nodes at the depth whose chunk is nearest
110 m (depth 8 on the home world) instead of a grid over the island: one candidate per 18 m as
now, hashed from the node address, kept by forest noise over `dir * R`, slope from `ground`,
altitude under the treeline, and distance from pads and roads. Cells spawn within
`graphics.tree_range` and despawn 200 m past it. Grass keys on nodes at the depth nearest 24 m and
is built around the player from `ground`, exactly as today.

**Water.** A sphere mesh at `R + sea_level`, about 20 k triangles, with the water shader. Dropping
2 m under it respawns the player and vehicles, as the kill plane does today.

**Shaders.** `terrain.wgsl` goes fully triplanar: the grass, dirt and sand layers and the macro
variation sample from three world axes like the rock already does, since there is no world XZ
plane. `water.wgsl` builds its wave coordinates from two tangents of the sphere normal, with the
body centre in world space passed as a uniform and updated on rebase. `surface.wgsl` is already
triplanar and does not change.

**Light and sky.** The sun `DirectionalLight` points along `-sun_dir`, with the current
four-cascade shadows to 500 m. The camera far plane goes from Bevy's default to 10 km: the
highest peaks see 5.6 km. The `Atmosphere` entity sits at the body centre (a transform updated
on rebase) with inner radius `R` and outer radius `R + 100 km`, Earth's scattering medium for
now; sub-project 3 gives each body its own medium. `aerial_view_lut_max_distance` goes to 10 km.

## Gravity that points at the centre, in every system

**Avian's global gravity goes to zero on the sphere.** A `FixedUpdate` system applies mass
times `gravity(p)` as a force to every awake dynamic body through Avian's `Forces` API, so
vehicles, crates and barrels (later ragdolls and the ship) fall toward the centre inside the
proper integrator. The flat arena keeps global gravity.

**The player's frame (`controller.rs`, `input.rs`).** `Player.frame: Quat` is initialized from
`surface.frame(spawn)`. Each tick the new up is read from the surface and the frame is rotated by
`Quat::from_rotation_arc(old_up, new_up)`, so its forward reference is transported along with
you. `ViewAngles` gains `frame`, set by the controller each tick; `rotation()` returns
`frame * yaw-pitch` and `flat_basis()` returns frame-rotated vectors, so every caller (weapons,
grapple, camera, body, HUD) gets world directions without change. On the flat surface the frame
is the identity.

**The controller runs in local coordinates.** `player_tick` is correct code for a flat world and
keeps running in one: position and velocity are rotated into the frame at the start of the tick
and back out at the end. The `Space` helper holds the frame and does the only conversions:
shape casts go out in world space with the capsule rotated to the frame, hit normals come back
rotated into it. Every `.y` and `.xz()` in the tick stays valid. The capsule's `Transform`
rotation is set to the frame so it stands along local up (Avian syncs transform to position for
the kinematic body, as it does today). `Player.velocity` stays world space, since the camera,
vehicles, animation and loot read it; `vertical()` and `horizontal_speed()` take the frame into
account. Gravity magnitude comes from `surface.gravity(pos)`; the mantle's three points are
world space and short-lived.

**Camera, body, arms, viewmodel (`camera.rs`, `body.rs`).** Camera rotation is
`frame * yaw-pitch-roll`; its position is the interpolated body plus `up` times eye height. The
player body stands at the body minus `up` times half height, rotated `frame * yaw`. The arms and
viewmodel hang off the camera and need no change. The vehicle camera orbits about the vehicle's
up and clamps its eye above `ground`.

**Grapple (`abilities.rs`).** Eye point, rope hand point and the gravity-cancel term use `up`;
the anchor is stored in body coordinates.

**Vehicles (`vehicle/mod.rs`).** The wheel rays, suspension and tyre forces already use the
chassis up. Changes: the local g magnitude from `surface.gravity` instead of `tuning.gravity`
(the sag and brake figures follow); spawn and respawn transforms built from `surface.frame` at
the ground point; the bike's upright reference from `up(p)`; the road lookup against
body-coordinate polylines; the fall-out check as `altitude < sea_level - 2`; exits and ejections
along `up`.

**Soldiers and drones (`targets.rs`).** Routes are body-coordinate polylines generated in the
site frame; `square` takes the frame. Feet snap with `ground`; eyes, cover probes and the path
check use `up`; facing uses `looking_to(dir, up)`; death tumbles spin about `up`. Drones circle
in their site's frame. `hear` and the squad call are distance-based and do not change.

**Weapons (`weapon.rs`).** Eye and muzzle offsets along `up`; `looking_to(dir, up)` for
tracers, grenades and spears; bullets, grenades, spears and rockets add `gravity(p) * dt` as a
vector each step (bullets today use a hard-coded 9.81 down -Y); hit zones project the hit point
onto the target's up; explosion pushes and self-knockback lift along the local up; wind is a
tangent-plane vector at the player.

**Sun and clock (`world.rs`).** The star is fixed in space and the body spins under it, so in
the body frame the sun direction rotates once per `day_minutes` about the spin axis:
`sun_dir = (cos δ cos H, sin δ, cos δ sin H)` in the body's equatorial frame, with hour angle
`H = 2π t / day` and declination `δ = tilt` until orbits exist. The initial phase puts local
solar time at the camp at `world.start_hour`. `daylight()` at a point is `dot(sun_dir, up(p))`
through the existing ramp. The HUD clock shows local solar time at the player's longitude. The
placeholder moon light stays until sub-project 2 brings real moons. Weather, fog, rain and wind
keep working; rain streaks fall along the camera's `-up`.

**HUD (`hud.rs`).** Heading is the angle between the view's flat forward and `north(p)`, dashes
within 5 m of a pole. The objective bearing is computed in the tangent plane.

**Loot, missions, bots, save.** Pickup and pad radii are distances and do not change.
`Objective::Reach` offsets are in the site frame: `origin + frame * offset`. `Drive` and `Kill`
radii use 3D distance. The 6v6 setup spawns in the fort's frame. `save.toml` holds no positions.

## Porting the island (`island.rs`, `roads.rs`)

**Placing the sites.** `place` keeps its rules but measures them in the island's tangent frame at
`home`: base camp 350 m south of the centre, the radio tower on the highest point inside the
1.5 km core (coarse search on a 16 m grid of directions, refined to 1 m), fort 900 m east, quarry
900 m west with its four rings, ruins 900 m north, the lighthouse where the ground first meets the
sea walking south, three extraction pads on the first dry gentle ground inward from the coast at
the current bearings. Each `Placed` carries `dir`, `height`, `frame` and the pad and footprint
radii; `origin()` returns body coordinates. Pads register as stamps on the surface.

**Roads.** The 2D router runs unchanged in the island's tangent plane, sampling `ground`. Its
output is stored as body-coordinate 3D polylines. The carve runs inside `height(dir)`: for
directions inside the island's bounding cone, the nearest segment within reach blends the height
toward the road profile, same blend as today. Grip lookup is `Roads::near(body_pos)`.

**The `Kit`.** Every builder call takes site-local coordinates as it does now and the `Kit`
applies `origin + frame * local` and `frame * Quat::from_rotation_y(yaw)`. The six site functions,
`wilderness_loot` and `spawn_vehicles` do not change a coordinate.

**Spawn and bounds.** `WorldBounds { spawn: camp.origin + frame * (0, 1, 6) }` in body
coordinates and `kill_altitude = sea_level - 2`.

## Tuning

New `[terrain]` table in `tuning.toml`; everything but `cell` is F5 safe:

```toml
[terrain]
cell = 0.5          # finest terrain cell, m; 1 on a weak machine
split = 2.5         # a chunk splits when you will be nearer than this many chunk sizes in a second; merges past 3
bubble = 400        # m, solid ground and awake physics around you
site_range = 1500   # m, sites load within this and unload 500 m further out
origin_step = 2000  # m, the world re-centres on you after this far
workers = 4         # chunk builds in flight
```

Removed: `[island]`. Moved: `world.day_minutes` to the body (`world.start_hour`, weather and sky
stay). Retuned for 9.8, with the heights they preserve:

| Key | Was | Now | Keeps |
|---|---|---|---|
| `gravity` | 17.6 | 9.8 | |
| `jump_speed` | 6.35 | 4.74 | 1.15 m jump |
| `air_jump_speed` | 6.35 | 4.74 | 1.15 m |
| `wall_jump_up` | 6.5 | 4.85 | 1.2 m |
| `self_knockback` (rocket) | 13.0 | 9.7 | 4.8 m rocket jump |
| `grenade.self_knockback` | 11.0 | 8.2 | 3.4 m |

`terminal_velocity`, `ramp_launch_speed`, the slide and wall-run numbers and the grapple stay;
their feel changes are listed under Decisions. Vehicle specs are unchanged; the brake fudge
`brake_t * g / 9.81` goes.

## Tests (headless, in `tests.rs` plus unit tests in the new modules)

Surface and generator:
- Same seed gives the same heights at a thousand random directions; a different seed does not.
- The home point is land, the continent edge is land, a point 60 percent of the way across the
  ocean mask away is below sea level for the default seed.
- Every pad is flat to its tangent plane within 1 cm across its radius and above sea level.
- Road segments never exceed the 15 percent grade and never enter a pad's flat disc.
- `ground` agrees with the loaded leaf chunk's mesh under a hundred random points within 1 cm,
  and with the analytic height where no chunk is loaded.

Quadtree and streaming:
- For a camera position the leaf set tiles the sphere exactly once: no gaps, no overlaps, the
  union of face coverage equals six faces.
- Moving the camera 1 km causes a bounded number of splits and merges (hysteresis holds).
- Leaf chunks inside the bubble have colliders; outside they do not.

Frame and controller (on a 2 km test moon built synchronously):
- A minute of running forward stays on the surface within 5 cm of altitude and travels along a
  great circle.
- Jump height at the pole and at the equator matches the flat case within 2 percent.
- Stair stepping over a 0.4 m block, a wall run along a wall, a mantle onto a 1.2 m ledge and a
  slide down a slope all work when the blocks are built in a site frame on the sphere.
- The carried frame stays orthonormal and its up matches `surface.up` after a lap over the pole.

Gravity, bubble, origin:
- A crate dropped from 50 m altitude falls toward the centre and comes to rest on the ground; a
  crate placed outside the bubble does not move until the player approaches.
- After a scripted 2.5 km drive a rebase has happened; relative positions of player, vehicle,
  crate and grapple anchor are unchanged within 1 mm and the camera does not jump.

Game systems on the sphere:
- The Humvee settles at ride height; roads grip better than grass; vehicles park at their sites.
- Soldiers patrol a site-frame route, stay on the ground, see and damage the player, forget them
  behind a wall; drones hold altitude on their circle.
- Pads flat and above water; loot carried, banked and lost; missions advance in order with the
  cache-loss step back; 6v6 scoring: the existing tests ported to `fake_sites` in frames.
- At the camp's local noon the sun's elevation equals 90° minus latitude plus declination within
  1°; a full day returns the sun direction.

Regression: every existing test passes on the flat surface at 9.8 with the retune.

## Build order

Each step ends in something you can run.

1. **Retune to 9.8** on the flat world; update the tests' numbers. Small; banks the gravity
   decision.
2. **Bare moon.** `Surface` with `Flat` and `Sphere`, the eight-octave height function without
   masks or stamps, the quadtree with workers and colliders in the bubble, the sliding origin, the
   gravity force, the controller and camera in the carried frame. `RUST_REGIME_LEVEL=moon` drops
   you on a 2 km moon with a few debug blocks. Measures: chunk build time, builds per second while
   running, frame time, skirt behaviour under a sliding capsule.
3. **The home world.** Continent and island masks, stamps and roads in `height`, sites in frames
   with the `Kit`, streamed vegetation and grass, the water sphere, triplanar shaders, the
   atmosphere at the body centre, sun from spin, the compass. The island on the globe.
4. **Everything else on the sphere.** Vehicles, soldiers, drones, weapons and grapple, loot,
   missions, extraction, 6v6, bubble freezing, site streaming. The full game, and the drive off
   the island across the continent.
5. **Screenshots, README, PR.** One shot from the tower showing the curve, one from the far
   coast of the continent.

## Risks

- **Skirts under vehicles at the ring edge.** Chunks under the player never swap, but a vehicle
  can cross from a finest chunk onto a merged coarser one at the ring boundary and clip a skirt.
  Step 2 measures it; the fallback is a wider finest ring (`split` 3) and skirts that lean inward.
- **Rebase stutter.** Shifting Avian positions without their interpolation caches, or shifting a
  frame late, shows as a one-frame jump. The rebase test and the camera check exist for this.
- **Continent seam.** Where the forced continent meets the global mask a visible ring can
  appear; the 20 percent blend width is tuned in step 3.
- **Builder throughput on two cores** at 0.5 m cells while driving. `cell` and `workers` are the
  knobs; 1 m is one line away.
- **Atmosphere at a 17.5 km inner radius** with Earth's medium: horizons are less reddened than
  today's. Correct for a small planet, and sub-project 3 tunes media per body.
- **Build time.** No new crates; compile time does not move.

## Files

New: `assets/system.toml`; `src/surface.rs` (surface API, height function, stamps, splat
weights and value noise moved from `terrain.rs`); `src/planet/mod.rs` (`PlanetPlugin`: water,
sun, atmosphere placement, level wiring), `quadtree.rs`, `chunk.rs`, `bubble.rs`, `origin.rs`.

Changed: `controller.rs`, `input.rs`, `camera.rs`, `body.rs`, `abilities.rs`, `weapon.rs`,
`targets.rs`, `vehicle/mod.rs`, `world.rs`, `hud.rs`, `island.rs`, `roads.rs`, `veg.rs`,
`look.rs`, `mission.rs`, `loot.rs`, `bots.rs`, `main.rs` (level plugin: planet for the default
level, `moon` debug level, arena unchanged), `tuning.rs`, `tuning.toml`, `tests.rs`, `README.md`,
`assets/shaders/terrain.wgsl`, `assets/shaders/water.wgsl`.

Removed: `src/terrain.rs` (its pieces move to `surface.rs` and `planet/`).
