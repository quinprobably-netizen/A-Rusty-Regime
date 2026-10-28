# Faction ships

Four custom spaceships, one per faction, built in code with headless Blender like the weapons and
characters, each with its own handling. Started 2026-10-27 in the "Design custom spaceships" thread.
Scope decision put to Q with "four ships in a row at Haven's pad" recommended; this spec follows
that option.

## Intent

- Replace the grey primitive ship with a Deserters' gunship, and give the Regime, the Scrappers
  and the PMC a ship each, so the factions read in the sky the way they read on the ground.
- Titanfall 2 / hard-kit look: chunky plated hulls, visible frames and fasteners, hinged panels,
  stencilled markings, big engine bells. Nothing sleek-and-smooth except the PMC.
- Every ship is boardable and flyable now. Each flies differently (mass, thrust, lift, turn rates,
  speed caps) so the choice matters.
- Zero third-party assets: everything is generated, so `CREDITS.md` gains nothing.
- Budget for an Arc A580 with 8 GB and a PC that has run out of RAM before: each ship under 12 k
  triangles, one 1024² baked colour texture (JPEG in the glb), three or four meshes per ship.

## The ships

All in the ship frame used by `solar::ship`: +X right, +Y up, -Z forward (nose). Lengths are
nose to tail; "rest" is the centre to the bottom of the landing gear.

| Id | Faction | Name | Silhouette | Length × span × height | Mass | Handling |
|---|---|---|---|---|---|---|
| `kestrel` | Deserters | Kestrel | Patched ex-military gunship: slab fuselage, stub wings with twin pod engines, chin cockpit, tail fin, four skids. | 14 × 11 × 4.5 m | 6 t | All-rounder: today's numbers (thrust 30, lift 20, rates 1.6/1.1/2.2, cruise 160, boost 6000). |
| `litany` | Regime | Litany | Cathedral in flight: long narrow hull, tall dorsal spire fin, two slit-window galleries, three bell engines in a trefoil, prow blade. Symmetrical and pristine. | 22 × 9 × 9 m | 14 t | Heavy: thrust 38, lift 16, rates 0.9/0.6/1.0, cruise 140, boost 7500. Fast straight, slow to turn. |
| `mule` | Scrappers | Mule | Welded hauler: box hull with one side longer than the other, two mismatched engines (one big, one small), external tanks and pipe runs, a crane arm folded over the roof, hazard stripes, canvas over the cargo bay. | 16 × 13 × 6 m | 11 t | Lifter: thrust 22, lift 30, rates 1.1/0.8/1.2, cruise 120, boost 4500. |
| `vantage` | PMC | Vantage | Faceted interceptor: angular stealth hull, swept wings, canopy flush with the hull, two flat slot engines, blue running lights, corporate stencil. | 12 × 10 × 3.5 m | 4 t | Agile: thrust 36, lift 18, rates 2.4/1.6/3.2, cruise 190, boost 6500. |

Colours. Deserters: `#141413` hull, `#F0EEE6` panels, `#D97757` stripes, `#D4A27F` tape and canvas.
Regime: slate `#33383f`, bone white, gold `#c9a227` trim, black glass. Scrappers: brass, copper,
rust, oiled leather brown, hazard yellow. PMC: gunmetal, white, cool blue emissive lights.

Every ship carries the same named nodes so the game can find them: `exhaust.<n>` empties where
each engine's glow disc goes (pointing +Z, out the back), `heat` where the re-entry glow sits (the
nose), and `light.<n>` for emissive running lights (PMC only). Seat, exit and collider boxes live in
`assets/ships.toml`, not in the glb, because tests run without assets.

## Pipeline: `tools/ships`

- `build.sh` makes the same Python 3.11 `bpy` venv the weapons use and runs `build.py`.
- `build.py` builds every ship (or the ids given) to `assets/models/ships/<id>.glb`,
  `--preview` renders a look-dev image to `screenshots/ships/<id>.png`, `--check` verifies each glb
  (triangle count under 12 k, bounding box within 10 % of the spec's size, the named nodes present,
  rest height matching the lowest vertex).
- `kit.py` imports the weapons kit (`block`, `prism`, `plan`, `cyl`, `tube`, `cut`, `unite`,
  `join`, `label`, `screw`, `bake_wear`, `preview`, `read_glb`) and adds: a `Ship` class (parts
  list, named empties, `finish()` that joins parts into `hull`, `glass` and `lights` meshes, bakes
  wear at `TEX=1024` with the wear scale grown for metres, exports without an armature); hull
  helpers at metre scale (`plate` for a bevelled armour plate with panel-line cuts, `rivets` for a
  row of fasteners, `stripe` for a painted band, `bell` for an engine nozzle, `skid` for landing
  gear); and extra palette entries (`slate`, `bone`, `gold`, `leather`, `gunmetal`, `blue_light`,
  `deserter_dark`, `deserter_pale`, `deserter_orange`, `deserter_tan`).
- `ships/<id>.py` holds `build()` and `SPEC` (size, rest height, node names) as the guns do.

## Runtime: `src/solar/ship.rs` and `assets/ships.toml`

- `ShipSpec` (serde, loaded once into a `Ships` resource from `assets/ships.toml`, F5 not needed):
  `name`, `faction`, `mass`, `thrust`, `lift`, `rates`, `cruise`, `boost_max`, `rest`, `seat`,
  `exit`, `cam: (dist, height)`, `collider: [{center, size}]`.
- `Ship` gains `spec: usize` (index into `Ships`). `fly`, `board`, `park`, `speed_cap` and the
  camera read the spec instead of module constants. `speed_cap(clearance, boost)` becomes
  `spec.speed_cap(clearance, boost)`.
- `spawn(world, id, transform)` builds the compound collider from the spec and, when there is an
  asset server, loads `models/ships/<id>.glb` as a scene under the `Hull` child. When the scene is
  ready (`SceneInstanceReady`), descendants named `exhaust.*` get the `Exhaust` marker and the
  ship's emissive exhaust material, the one named `heat` gets `HeatGlow`, `NotShadowCaster` and the
  additive heat material. `ShipLook` becomes a component on each ship so four ships glow
  independently.
- `spawn_home_ship` becomes `spawn_fleet`: the pad becomes an 80 × 26 m apron extending west (the
  Kestrel's spot and the player's spawn stay where they are, the course stays 70 m east), with the
  Kestrel at x = −1, the Litany at −19, the Mule at −37 and the Vantage at −55, noses north.
- The HUD's "[E] board ship" line names the ship ("[E] board Kestrel").
- Memory: ships load one at a time like characters do (sequential `load` by readiness) so boot
  never holds four decode buffers at once.

## Tests (headless, in `src/tests.rs`)

- `ships.toml` parses to four ships whose ids match a glb on disk and whose colliders' lowest face
  equals `-rest` within 5 cm.
- The system starts with four ships on the apron, none overlapping (collider boxes disjoint) and
  all within 2 m of resting height after a second of settling.
- Boarding picks the nearest ship; leaving puts the player at that ship's `exit`, clear of its
  collider.
- Each ship's `speed_cap` honours its own cruise and boost values; the heavier ship accelerates
  slower under the same stick (thrust is m/s², so this checks the spec plumbed through, not
  physics).
- The existing ship tests keep passing against the Kestrel.

## Out of scope

Ships parked on their own worlds (needs far-ship stowing across frame handoffs), ship weapons,
interiors, a hangar menu, damage. Each is its own thread when wanted.

## Round 2 (Q, 2026-10-27): more detail and walkable interiors

Q asked for more detailed hulls and interiors you can walk through on foot.

- **Cabins.** Every ship is hollow: a cabin at least 1.8 m wide and 2.2 m tall inside (the player
  is a 1.8 m, 0.4 m radius capsule with a 0.4 m step) with a floor, walls, ceiling and a rear
  ramp that reaches the ground at under 25°. Fuselages grow to fit: Kestrel 2.8 × 2.7 m,
  Vantage 3.0 × 2.6 m; the Litany and Mule were already tall enough. The ramp is a `ramp` node
  in the glb, hinged at its top edge: the game lays it open when the ship is parked and swings it
  shut while flying. Fittings per ship: a pilot's seat and console with lit screens, crew seats
  or pews, racks, crates, lockers, a ceiling light strip (group `lights`). Faction dressing
  carries inside (gold and candles in the Litany, chains and tools in the Mule, white panels in
  the Vantage, tape and canvas in the Kestrel).
- **Colliders.** `ShipBox` gains an optional `rot: [x, y, z]` in degrees, so a ramp slopes.
  Interiors are built from boxes: floor, two walls, ceiling, front bulkhead, ramp. The walkable
  volume is clear of collision boxes.
- **Boarding and leaving.** Unchanged: E within `BOARD_RADIUS` of a ship flies it from the seat.
  Leaving puts the player on the cabin floor behind the seat (`exit` is now inside the hull), and
  they walk out down the ramp. The respawn is that same cabin spot: you wake up in your ship.
- **Parked ships are static.** A ship with no pilot moving under 0.5 m/s becomes
  `RigidBody::Static` (so walking in it cannot nudge it and it never jitters); boarding makes it
  `Dynamic` again. `RUST_REGIME_AT` boards through the same path.
- **Detail pass.** Exterior parts roughly double: hinges and latches on every plate, nav lights,
  antenna arrays, wing fences and hardpoints (missile pods on the Kestrel, braziers on the
  Litany, a winch and tyre bumpers on the Mule, sensor blisters on the Vantage), cable runs,
  stencils, chevrons at the ramps. Budget per ship rises to 30 k triangles (still one 1024²
  texture); the A580 is nowhere near that limit.
- **Tests.** Interior clearance: for every ship, a 1.8 m capsule standing on the exit point
  touches no collision box, and the ramp's foot is within 0.3 m of the ground. Parking: a ship
  is static two seconds after the pilot leaves it at rest, dynamic again once boarded. Leaving
  leaves the player standing (`Ground`) on the cabin floor, and walking aft takes them out the
  ramp onto the apron without a jump.

## Round 3 (Q, 2026-10-27): detailed interiors, not boxes

Every fitting inside a cabin is a real object from `tools/ships/interior.py`, built the way the
hulls are: flight seats with bolsters, raked backs, headrests, armrests and harnesses; fold-down
troop seats on wall brackets; church pews with carved ends and kneelers; a console with a kick
plate, a desk of switches and a keyboard, and a raked bank of bezelled screens; stick and
throttle on a plinth; an overhead switch panel; cabinets with proud door panels, pull handles,
hinges and vents; bunks on tube frames with pillows and rolled blankets; crates with corner caps,
bands, latches and stencils; oil drums with hoops; gas bottles; rope cargo nets; a gun rack;
an equipment rack; pipe runs with saddles and a valve wheel; flanged ducts; clipped cable
bundles; open grating floors; bolted wall lining; round ceiling lamps (caged on the Mule) that
are `lamp.<n>` nodes the game lights the cabin from; a pressure hatch; a workbench with a vice
and tools; a chain hoist on a ceiling rail; candelabra, censers, an altar and a font for the
Litany. The triangle budget rises to 60 k per ship (Kestrel 44 k, Litany 52 k, Mule 51 k,
Vantage 27 k); fittings do not collide, the cabin boxes still do.
