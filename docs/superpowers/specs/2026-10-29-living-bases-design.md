# Living bases

Q asked on 2026-10-29: "use the existing bases as references and redesign them around their planets
and make them feel more alive". Builds on `2026-10-27-faction-bases-design.md` (pipeline, budget,
stations, waypoints), which stays the reference for anything not changed here.

## Short version

- Every base is rebuilt in `tools/bases` to read as *of its world*: lush comic camp on Haven,
  a squat fortress-cathedral braced against Bastion's 12.5 g, a dune-buried junk fort on Cinder,
  sealed modules sunk in Frost's airless ice.
- A shared life layer (`src/solar/life.rs`) staffs each base with its own faction's existing
  characters (no new models): a keeper at every station and two or three people walking rounds.
- The models carry named nodes the game animates: spinning parts (radar, turbines, fans, a crane),
  blinking beacons, flickering fire and weld light, smoke and spark puffs, and looping sounds.
- A faction transport lands on each base's pad every few minutes, sits, and leaves (scripted, not
  combat AI). The Roost's lands on Haven's apron.
- Every station, door, price and save field stays as it is. Frost has no air, so its outside is
  silent; you hear its machines only indoors.

## Per base

| Base | World | Redesign | Life |
|---|---|---|---|
| The Roost (Deserters) | Haven: temperate, green, 9.8 g, the comic look | The hangar becomes a lived-in rebel camp: bold painted panels and chevrons sized for the ink shading, a timber lookout deck, tarps and shade cloth, a greenhouse and veg beds, laundry lines, string lights, a cook fire, a windsock and a turning radar on the roof, crates spilling out of the bay. | Cook fire flicker and smoke, string lights, radio chatter and a generator, runners and breakers on their rounds, the quartermaster behind the counter. |
| The Reliquary (Regime) | Bastion: heavy, cold, slate grey, thin pale sky | Lower and wider: the nave sunk into a cut rock terrace, massive stepped buttresses, a squat bell tower rather than a spire, braziers lining the steps, long red banners, gold ribs. A data fortress worked through it (Q, 2026-10-29): black monoliths with red data seams as buttresses and belfry piers, vaults and cable trunks on the rock, server stacks in gold niches inside, a sealed archive core behind the altar, uplink spires. | Braziers flicker and smoke, censer smoke inside, a bell tolls each in-game hour, a low organ drone, acolytes processing down the nave, a priest at the shrine. |
| The Yard (Scrappers) | Cinder: rust desert, dusty orange sky, 6 g | The container fort half-buried in dunes with sand fences, shade sails, two wind turbines, a glowing smelter, a scrap mountain and a crane over it. | Turbines and crane turn, the smelter glows, weld flashes and sparks in the workshop, grinders and wind, mechanics at the rig and the rack. |
| Site Vantage (PMC) | Frost: airless ice, 8 g, a 90-minute day | Modules sunk into ice berms with insulated skirts, heat-radiator fins, a tracking radar dish, an ice-core drill rig, chasing pad lights, strobe beacons. | Radar sweeps, drill turns, strobes and pad lights chase; server hum and air handling indoors only, contractors at the desk and on patrol. |

## Model conventions (`tools/bases/basekit.py`)

Named nodes the game reads, beside the existing `lamp.<n>` and `flood.<n>`:

| Node | Becomes |
|---|---|
| `spin.<axis>.<rpm>.<n>` (a mesh group with its origin on the pivot, `basekit.spinner`) | turns about its local x, y or z (game frame) at `rpm`, negative for the other way |
| `blink.<n>` | a red point light and glow that pulses once a second, phase by `n` |
| `strobe.<n>` | a white flash every 1.5 s |
| `fire.<n>` | a warm light that flickers (braziers, cook fire, smelter) |
| `weld.<n>` | blue-white crackling bursts with sparks, a few seconds on, a few off |
| `smoke.<n>` | grey puffs that rise, grow and fade |
| `sound.<kind>.<n>` | a looping spatial sound: `generator`, `radio`, `fire`, `organ`, `bell`, `grinder`, `wind`, `hum`, `vent` |

The mesh cap for a base rises from six to twelve so spinners can be their own meshes.

## Crew and traffic (SPEC, written to `assets/bases.toml`)

- `crew`: `[(character, at, facing_deg, path)]` in the Blender frame. With no path the person
  stands idle at `at` and turns to face you within 6 m; a path is a loop of points walked at
  1.4 m/s with a short pause at each. Characters come from the base's faction.
- `traffic`: the ship id that visits the pad (Regime litany, Scrappers mule, PMC vantage, Deserters
  kestrel), every 150-240 s: comes in from 400 m, slows, settles, sits 40 s, lifts and leaves.
  It has no collider while it flies and is a Fixture like the base.
- People and ships are cosmetic: no colliders, no combat, nothing saved.

## Tests

- Every crew point and path point has a floor under it and is clear of the collider boxes.
- Every node named in a base's `nodes` list parses as a known kind.
- The life layer spawns a keeper for each station of the anchor world's bases.
- Traffic's cycle lands on and leaves the pad (pure function of time).

## Posts (Q, 2026-10-29: "add procedurally placed small outposts across the planets")

Prototyped and approved before the build ("show me prototypes first"). `tools/bases/posts.sh`
builds `assets/models/posts/<id>.glb` (under 15 k triangles, 4 meshes, 1024² texture, footprint
under 14 m) and `assets/posts.toml` (the bases' format with no site, `[[post]]`, a `cache`
station at each door). `src/solar/post.rs` places each world's post `count(radius)` times
(radius / 500 m, 6 to 12) from the world's seed: `flat_site` on a random direction (on Haven, on
the home continent between the island region and the rim, above 5 m), 400 m from bases and the
apron, 600 m from each other. Each gets a foundation, its collider, two crew and the cache (free
heal and ammunition, refused when the faction hunts you). Within 150 m it is found:
`Save.posts_found` (`<body>.<n>`) and a smaller waypoint from then on.

| Post | World | What it is |
|---|---|---|
| `watch` | Haven | Timber watchtower, tarp roof, sandbags, radio, cook fire |
| `relay` | Bastion | A small data fortress: black vault with red seams cabled into a crag, uplink spire, braziers |
| `camp` | Cinder | Two containers, one tipped into a dune, shade sail, wind turbine, drum fire |
| `sensor` | Frost | White pod on jacks in an ice berm, turning dish, strobes, hum only inside |

## Approach ramps

A base whose deck stands a metre or more over the ground in front of its door (the Roost stands
on a ridge about 12 m over the slope toward the apron) gets a ramp from its front edge down to
the ground in line with the door, at most 1 in 2, 7 m wide (`base::approach`).
