# Solar system programme: from one island to worlds you fly between

Agreed with Q on 2026-10-24 in the open-world brainstorm. This note records the intent, the
decomposition into sub-projects, and the one architectural decision every sub-project depends on.
Each sub-project gets its own spec and plan; the first is
`2026-10-24-round-home-world-design.md`.

## Intent

- A solar system of several worlds. You fly a ship between them in real time and land anywhere:
  seamless, no loading screens, no destination menu.
- A home world of 17.5 km radius. Faction worlds and moons of 1 to 5 km.
- Environment physics as real as we can make it, all four of: worlds that orbit and spin;
  atmospheres that behave as fluids (density falling with altitude, drag, terminal velocity,
  re-entry heating, no sound in vacuum); gravity and oceans that differ per world (buoyancy, waves
  from wind); surroundings that break and react (falling trees, fracturing walls, ragdolls, cloth,
  debris pushed by water and wind).
- The island survives as the populated core of the home continent. The Deserters' camp stays the
  spawn; the six sites, roads, missions, extraction loop and 6v6 mode keep working.
- Movement keeps its feel, at Earth gravity. Decided 2026-10-24: the home world has g = 9.8 m/s²
  and the jump, air jump, wall jump, rocket and grenade speeds are retuned once so their heights
  stay what they are today. Other worlds keep those speeds and let their own g change the heights.
- Same rules as every spec so far: zero budget, generated assets, deterministic from seeds,
  headless tests, no multiplayer.
- One world per faction is the starting roster (Regime, Scrappers, PMC, with the Deserters on the
  home world). What an hour of play is across the system is still open and gets its own
  brainstorm (sub-project 5). Until then the loops that exist keep running on the home world.

## Why the sizes are what they are

Horizon distance is about the square root of twice the radius times eye height:

| Radius | Horizon at eye level (1.6 m) | From a 40 m tower |
|---|---|---|
| 2 km | 80 m | 400 m |
| 3 km | 98 m | 490 m |
| 5 km | 126 m | 630 m |
| 17.5 km | 237 m | 1.2 km |
| Earth, 6371 km | 4.5 km | 22 km |

At 1 to 5 km the ground visibly falls away within a hundred metres and a marksman rifle outranges
the horizon from flat ground: those worlds feel like large Outer Wilds planets. The home world at
17.5 km reads nearly flat on foot. Q chose the mix: one big home world, smaller others.

## Decomposition

Five sub-projects. Each is playable on its own and gets its own spec, plan and PR.

1. **Round home world.** Cube-sphere terrain with level of detail and streamed colliders, a
   sliding origin so a 17.5 km radius fits f32 physics, gravity toward the centre in the
   controller, grapple, vehicles, bots and bullets, the island ported as the core of a continent
   with its sites in local frames, an ocean sphere with the current waves, day and night from the
   world's spin. Playable: today's game on a globe, and a drive off the island across the
   continent.
2. **Ship, star and sky.** The star and analytic orbits, the anchored-frame switching below, a
   six-degree-of-freedom ship boarded like a vehicle, Newtonian gravity on everything free, the
   atmosphere model (density, drag, terminal velocity, re-entry heat, vacuum silence), a floating
   origin in deep space, and one barren moon to fly to. Playable: take off, orbit, land on the
   moon, come home.
3. **The worlds.** Faction worlds with their own gravity, air, biome and sky; generated outposts
   plus handmade landmarks; an asteroid belt for zero-g parkour; weather as a wind field per
   world; oceans with buoyancy and swimming; per-body scattering media for their skies.
4. **Reactive surroundings.** Fractured walls from the generated blocks, trees that fall,
   ragdolls on the 22-bone skeleton, cloth banners, debris, props pushed by water and wind.
   Independent of 2 and 3; can run in parallel once 1 lands.
5. **Loops across the system.** Missions, extraction, faction war or trade across worlds. Needs
   its own brainstorm: the core-fantasy question was not settled.

Order: 1 before 2, because every later piece stands on the sphere and the two riskiest unknowns
(terrain with level of detail at 17.5 km, the movement controller in radial gravity) are both in
it.

## The frame decision: anchored frames with a sliding origin

Worlds that move need a reference frame for physics. Three were weighed; the first was chosen.

**A. Anchored frames with a sliding origin (chosen).**

- Every body has an analytic orbit and spin derived from the seed and the clock. Positions are
  computed, never integrated, so saves and tests reproduce exactly.
- Physics always runs in the body-fixed frame of the *anchor*: the body whose sphere of influence
  you are in. In that frame the ground is static, so terrain and site colliders stay static
  exactly as today. The sky moves instead: the star, other worlds and moons are placed every
  frame from their orbits. Day and night are the world turning under a fixed star, which from the
  ground looks exactly like the sun moving as it does now.
- Free bodies feel gravity toward the anchor plus the two fictitious forces of a spinning frame,
  centrifugal and Coriolis. At these spin rates they are small but real: on a world with a
  48-minute day a marksman's bullet drifts about 20 cm over 300 m. That is the correct physics,
  so it stays in.
- Crossing a sphere-of-influence boundary switches the anchor. The player, the ship, bullets and
  loose props are re-expressed in the new frame, the old world's surface despawns, and its state
  is remembered per body (loot taken, soldiers down, where vehicles were left). Positions and
  velocities are continuous, so nothing is felt; only which things count as static changes.
- The origin slides with the player in steps (2 km on a world, longer in deep space). Everything
  loaded is expressed relative to it, and since terrain, sites and vegetation stream in around
  the player, a rebase touches a few hundred loaded entities. This keeps millimetre precision in
  f32 on a 17.5 km world and across 100 km of space without Avian's f64 mode.
- Limit: one gravity source at a time (patched conics). No Lagrange points, no three-body
  wobble. At these scales nobody can tell.

**B. One inertial frame, f64 physics (rejected).** Everything in the star's frame; worlds are
kinematic bodies that orbit and spin; every tree, wall and soldier is parented to its world; the
controller learns moving platforms; Avian runs in f64. The only route to n-body gravity, which
this game does not need. The cost is pervasive and resting contacts on a spinning triangle mesh
at 66 Hz are a jitter risk.

**C. Static worlds, clockwork sky (rejected).** Worlds neither orbit nor spin; the star and the
other worlds move across the sky on a schedule. Cheapest, and the sky lies: where a world
appears is not where you reach it.

## Rules every sub-project follows

- **Nothing hard-codes +Y as up.** Everything asks the `Surface` for `up(p)`, `gravity(p)` and
  `frame(p)`. The flat arena and the headless tests use the `Flat` variant of the same API.
- **Positions stored for longer than a frame are body coordinates** (relative to the anchor
  body's centre), converted through the `Origin` resource on use. Live transforms and physics
  positions are origin-relative and get shifted on a rebase. See the sub-project 1 spec.
- **Bodies are data.** `assets/system.toml` declares the star and every world; the game never
  hard-codes a radius or a gravity.
- **Deterministic from seeds.** A body's terrain is a pure function of its seed and a direction.
  Orbits are analytic in the epoch. A save holds the anchor body, the epoch and body coordinates.
- **Streamed, bubbled, remembered.** Terrain, vegetation and sites stream in around the player;
  only ground inside the physics bubble is solid and only bodies inside it simulate; per-body
  state records what the player changed.
- **Engine facts relied on (Bevy 0.19, Avian 0.7):** Bevy's `Atmosphere` is one component per
  planet with the entity transform as the planet centre, each camera renders the nearest, and
  `AtmosphereMode::Raymarched` exists for views from orbit. Avian offers triangle-mesh colliders,
  shape casts with a rotation, per-body forces and a rigid-body-disabled marker. fastnoise-lite
  has 3D noise.
