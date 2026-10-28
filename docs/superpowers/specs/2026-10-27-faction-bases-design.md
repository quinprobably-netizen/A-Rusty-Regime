# Faction bases

One base per faction, placed on its world around the solar system, built in code with headless
Blender like the ships (`tools/ships`) and walkable inside. Started 2026-10-27 in the "Design
faction bases across the system" thread. Follows the ship work (PR #34) in pipeline, look, budget
and runtime shape.

## Intent

- Each world has somewhere to fly to: a landing pad and a building the faction reads from a
  kilometre away, with an interior to walk through. Haven's base stands beside the apron.
- Titanfall 2 hard-kit look, the faction colours of the ships and roster. Zero third-party assets.
- Budget for an Arc A580: one base loaded at a time (the anchor world's), each under 90 k
  triangles, one 2048² baked colour texture, at most six meshes.

## The bases

Model frame (Blender): +X right, +Y into the site, Z up, the front door on -Y, origin at ground
level under the building's centre. The glTF export makes that +X right, +Y up, door on +Z.

| Id | Faction | World | Name | What it is |
|---|---|---|---|---|
| `roost` | Deserters | Haven | The Roost | A two-storey steel hangar on the flat south-east of the apron, past the course, door toward the pad: open bay, mezzanine catwalk, roof deck with a sandbag nest, external stair, water tank, mast, tarp awning. Bunks, workbench, gun racks, planning table. |
| `reliquary` | Regime | Bastion | The Reliquary | A slate basilica: 30 m nave, transept, apse, spire tower, buttresses, red slit windows, gold ribs, bone statues, steps up to a great door. Pews, altar, candelabra, censers, font, throne. |
| `yard` | Scrappers | Cinder | The Yard | A junk fort: a wall of welded containers with a gate, a workshop shed open at the front, a gantry crane, drums, tyres, pipe runs, a lookout derrick with a ladder, a water tower. Workbench, hoist, cabinets, bunks. |
| `outpost` | PMC | Frost | Site Vantage | Three white hab modules on jacks joined by corridors, an airlock vestibule with a ramp, a radar dish, floodlight masts, blue strips. Server racks, a two-seat ops desk, bunks, lockers, a gun cage. |

## Pipeline: `tools/bases`

`build.sh` shares the weapons' `bpy` venv and runs `build.py`, which builds every base (or the ids
given) to `assets/models/bases/<id>.glb`; `--check` verifies each glb (triangles under 90 k, size
within 10 %, lowest vertex at ground level, the named nodes present); `--preview` renders
`screenshots/bases/<id>.png` (and `<id>-inside.png`). `kit.py` imports the ship kit and interior
kit from `tools/ships` and adds a `Base` class (a `Ship` that exports to the bases folder and bakes
at 2048²) and site helpers (`stair`, `catwalk`, `railing`, `container`, `mast`, `floodlight`,
`sandbags`, `tank`, `dish`). `lamp.<n>` empties become point lights as in the ships.

## Runtime: `src/solar/base.rs` and `assets/bases.toml`

- `BaseSpec`: `id`, `name`, `faction`, `body`, where it stands (`near_pad = [x, z]` in Haven's
  pad frame, or `lat`/`lon`, and `yaw` to turn it on its world, snapped to the flattest ground near there with the same
  search as the home pad), `footprint` (the buried foundation slab whose top is the deck the base
  stands on), `pad` (the landing pad's centre in the base frame, if the base has one), `door` (a
  point in the doorway, for the tests), and `collider` boxes (`ShipBox`, floors, walls, roofs,
  stairs as tilted boxes) the player walks between. Fittings do not collide, as in the ships.
- `spawn_bases(world)` runs from `spawn_fixtures` for whichever body is the anchor: foundation and
  pad slabs, a static compound collider, and the model streamed from the glb one at a time after
  the ships (`Pending`). Everything is a `Fixture`, so a handoff drops it and the next world's
  bases spawn in its place.
- The flight readout names the anchor world's base and how far it is.

## Tests (headless)

- `bases.toml` lists four bases on four known bodies with a model file each; the door point and a
  point a metre inside it are clear of every collider box and have a floor under them.
- The Roost stands on Haven at start as a `Fixture`; after a handoff to Bastion the Reliquary's
  fixtures stand there and Haven's are gone.

## Waypoints (2026-10-27, Q: "add easily identifiable waypoints")

`src/solar/waypoint.rs`: one marker per base plus one for the player's parked Kestrel, hung off a
`HudRoot` so the menus hide them. A coloured diamond, the name and `world - distance` beside it
(flipped to the left past 70 % of the screen width), placed by projecting the target through the
player camera, clamped to a 36 × 105 px margin (clear of the compass and the plates) when off-screen and sat on the side it is on when behind
you; hidden within 30 m, and the Kestrel's while you pilot it. A base on the anchor world is
marked 14 m over the building; a base elsewhere at its world's centre (distance to the surface).
Colours come from `color` in each base's SPEC (`bases.toml`): Deserters green, Regime red,
Scrappers yellow, PMC blue, so the colour says the faction at a glance. Each anchor-world base also
gets a 6 m wide, 900 m tall additive beam in the same colour, to be seen from kilometres away.

## Purposes (2026-10-27, Q: "add more depth and a purpose for each base")

Each base gets a small standalone annex (`basekit.room`/`room_boxes`: hall, cap, door frame and
the matching collision boxes) and one or two **stations** in its SPEC (`stations`: kind, point,
label; emitted to `bases.toml`, spawned as children of the base so they follow handoffs). E within
2.8 m of a station does its job and uses the press up, so the ship and the wardrobe never see it
(`src/solar/station.rs`). A `footprint_at` offset lets the foundation cover an annex off to one side.

| Base | Annex | Station | Job |
|---|---|---|---|
| The Roost (Deserters) | Supply depot by the bay door | Quartermaster, Locker | free heal + ammo; the locker opens the wardrobe |
| The Yard (Scrappers) | Tuning garage outside the east wall | Tuning rig | `Save.ship_level` 0-3, $300/$700/$1400; thrust x1.12/level, speed x1.12, turn x1.05 |
| Site Vantage (PMC) | Freight office east of the armoury | Courier desk | `Save.contract`: parcel to another base, $250 + $150 per leg of the round, paid at its door |
| The Reliquary (Regime) | Chantry before the steps | Shrine | $150 tithe: +50 max health and a full heal for 5 minutes |

Contracts are the only income in the solar system (extraction is island-only), so they pay for the
tune and the blessing. The destination's waypoint says DELIVER HERE and the flight readout lists the
parcel and the bank. Save gained `ship_level`, `contract` (destination base id, pay) and
`contracts_done`. Not built: faction standing, contracts from other bases, more upgrade tracks.
