# Hyper-realism plan

Where the game is: a 4 km procedural island with six sites, patrolling soldiers, three vehicle types on
Regolith Rally physics, an extraction loop with a save, six story missions and an optional 6v6 bot mode.
Everything is flat-shaded primitives, no textures, no sound, no animation, hitscan guns, 40 headless tests.

What "hyper realistic" costs, honestly: a studio spends years and millions on it. On a zero budget with one
agent the lever is **free, high-quality assets plus physically based systems**, in an order where each stage
is playable on its own and the earlier stages are the ones you notice most. Everything below is CC0 or
permissive-license only, and nothing needs a GPU to build (lavapipe screenshots keep working, just slower).

One tension to decide up front: TF2 movement (air strafing, rocket jumps, 6 m/s sprint, instant respawn) is
not realistic, and it is the thing that makes the game fun right now. Recommendation: **keep the movement
feel, make everything around it realistic** (the "Titanfall" compromise). A `realism` tuning profile can
dial sprint, jump and air control down later if you want the full sim.

## Stage R1: look (biggest win per hour)

*Done 2026-10-17* (see `src/look.rs`, `src/veg.rs`, `assets/shaders/`): items 1, 4, 5 as written; 2 and 3 as generated meshes rather than CC0 model kits; 6 as triplanar textures on the existing generated walls. Props kits are left for the model thread.

1. **PBR terrain splatting**: 4-layer material (grass, dirt, rock, sand) blended by slope and height, with
   normal and roughness maps. Source: ambientCG (CC0) 1K textures, ~2 MB each. Triplanar on steep rock.
   Custom Bevy `Material` with a WGSL shader; the heightmap already gives slope.
2. **Detail at your feet**: tiled detail normal map, grass blades as instanced cards from a CC0 atlas
   (Kenney or Poly Haven), fading at 60 m. Rocks and driftwood scattered by the noise field.
3. **Trees and scrub**: Poly Haven / Quaternius (CC0) low-poly pines and shrubs, instanced on the hills with
   three LODs and impostor cards past 300 m. Collision cylinders on trunks only.
4. **Sky, sun, fog**: Bevy atmosphere (`Atmosphere` component, 0.16+) for a physical sky, `DistanceFog`
   tuned to it, cascaded shadow maps from the sun, bloom + tonemapping (AgX), screen-space ambient
   occlusion, temporal anti-aliasing. All in Bevy already; it is tuning work.
5. **Water**: Gerstner-wave shader with depth-tinted shoreline foam, planar-ish reflection faked by the sky
   cubemap. The existing water plane stays.
6. **Buildings and props**: replace the primitive site walls with Kenney / KayKit / Quaternius CC0 modular
   kits (military base, ruins, lighthouse) in glTF; stock the camp with crates, barrels, sandbags, tents.

Effort: about 3 to 4 cycles like the vehicle one. Tests: material load, instance counts, shader compiles
headless, screenshot diffs.

## Stage R2: sound

*Done 2026-10-17* (`src/sound.rs`): every sound is synthesized at startup (gunshots, steps, impacts, explosions, RPM-pitched engine loops, wind, surf, rain), spatial, with volumes in `[sound]`. Drop a CC0 `.ogg` into `assets/sounds/` to replace any of them. Wall occlusion and per-surface step sets are not built.


1. `bevy_audio` (built in) or `bevy_kira_audio` for mixing. Spatial emitters with distance roll-off and a
   low-pass "behind a wall" filter from a raycast.
2. Free sources: freesound.org (CC0 filter), Sonniss GDC bundles (free for commercial use), Kenney audio.
   Gunshots with distant-tail variants, footsteps per surface (the splat layer under you picks the set),
   wind that scales with altitude, surf near the coast, engine loops pitched by RPM with a load crossfade.
3. Vehicle engine: granular loop pitched by `Vehicle.rpm`, gear-change blip, gravel spray from slip `s`.

Effort: 1 cycle. Tests: emitter counts, pitch follows rpm, surface picks the right set.

## Stage R3: bodies and animation

*Owned by the Character customization thread (its own Blender rig in `assets/models/character/`); this plan does not fetch rigs.*

1. Player and soldiers become rigged humanoids: Quaternius Universal Base Characters or Mixamo-compatible
   CC0 rigs, with CC0 animation packs (idle, run, crouch, slide, jump, aim, die). Bevy's animation graph
   blends by speed and aim pitch.
2. Ragdolls on death: Avian joints on the skeleton, kicked by the hit impulse already in `Damage`.
3. Drivers and riders: seat the humanoid in the vehicle with hands on the wheel and a lean pose on bikes
   driven by the existing lean target.
4. First-person arms with the same rig, and proper gun models (Quaternius weapon pack, CC0) with reload and
   aim-down-sights poses.

Effort: 2 cycles. Tests: animation state picks, ragdoll spawns on kill, driver pose matches lean.

## Stage R4: ballistics and damage

*Done 2026-10-17* (`src/weapon.rs`, `src/health.rs`): projectile bullets with drop, drag and wind; wood, crates and thin metal let bullets through; head and leg zones; recoil that climbs and settles; aim down sights on right mouse; bleeding, capped regen and medkits at six sites. Body armour and limb slowdowns are not built.


1. **Projectile bullets** for every weapon: each shot is a point with velocity, gravity and air drag
   (0.9 at 850 m/s for rifles, pistol at 350), stepped at 66 Hz with a raycast per step. Bullet drop
   shows past 100 m, travel time matters for moving soldiers.
2. **Penetration**: material tags on colliders (wood, plaster, steel, dirt) with a thickness-based energy
   loss; thin walls leak, sandbags stop.
3. **Hit zones**: head, torso, limbs on the rig; damage by zone and by remaining bullet energy. Body armour
   as a hit-zone modifier.
4. **Recoil as a pattern plus random cone**, grows with sustained fire, settles when you stop; sway from
   breathing and stance; aim-down-sights halves it.
5. **Health model**: bleeding (damage over time until bandaged), limb hits slow sprint or wobble aim,
   no regeneration above a floor, medkits as loot. Keep the TF2 respawn.

Effort: 2 cycles. Tests: drop at range matches the formula, a plywood wall leaks and a steel one stops,
recoil returns to zero, bleed ends on bandage.

## Stage R5: smarter soldiers

*Done 2026-10-17* (`src/targets.rs`): soldiers hear gunshots, call their squad, and run to cover that hides them from the threat when hit. Formations, flanking and bot drivers are not built.


1. **Senses**: vision cone with distance falloff and lighting, hearing of gunshots and engines through
   the audio emitters, "last seen" already exists.
2. **Cover**: bake cover points from the site walls and rocks (ray tests at build time), move cover to
   cover with suppressed and flanking behaviour, peek and lean animations from R3.
3. **Squads**: patrols become fireteams of 3 to 4 with a leader, formation movement, shouted callouts
   (CC0 voice lines or radio chatter noise), reinforcements by Humvee when a site goes loud.
4. **Vehicles for bots**: path-following driver using the same raycast-wheel model, so patrol convoys
   drive the island roads.

Effort: 2 cycles. Tests: a soldier under fire picks cover, hearing a shot raises alert, a squad stays in
formation.

## Stage R6: vehicles the rest of the way

*Done 2026-10-17* (`src/roads.rs`, `src/vehicle/`): dirt roads from camp to every site, capped at a 15% grade; tarmac grip on roads, gravel off them; fuel, hull damage from crashes and bullets, wrecks that respawn, refuel and repair at camp. Punctures, cockpit and turrets are not built.


1. Roads: splines between sites carved into the heightmap with a tarmac splat layer; tyres read the layer
   and switch between `TARMAC` and `GRAVEL` (both curves already ported).
2. Damage: per-wheel puncture, engine health that caps torque, fuel that runs out, visible dents via
   swapped damaged meshes, fire and explosion when destroyed.
3. Cockpit view with a modelled interior and working gauges driven by `rpm` and speed.
4. Turrets: the Humvee gets a roof gun a passenger can use; bots man it.

Effort: 1 to 2 cycles. Tests: tarmac grip exceeds gravel, puncture pulls to one side, empty tank stalls.

## Stage R7: world and weather

*Done 2026-10-17* (`src/world.rs`): 48-minute day with sun, moon and exposure, headlights and an F flashlight; clear, overcast, rain and fog with wet ground and rain streaks; wind that pushes bullets. Lit windows, night vision and the economy are not built.


1. Day-night cycle on the sun with lit windows and vehicle headlights at night, flashlight and night vision
   as equipment.
2. Weather states: clear, overcast, rain (particles, wet-surface roughness drop, puddles in the splat),
   fog banks, wind that moves the grass and pushes bullets a little.
3. Dynamic economy: loot value varies by site danger, prices for armour, medkits and vehicle repair at camp.

Effort: 1 to 2 cycles.

## Stage R8 (optional): netcode

*Not built*, as planned.


Still last and still optional. `lightyear` or `bevy_replicon` with server authority, client prediction of
the TF2 controller and interpolation for everyone else. The headless test harness is the server already.
Only worth it if the bots mode proves fun with people.

## Order and budget

R1 then R2 then R4 is the fastest route to "looks and feels real" with most of the fun kept; R3 is the
biggest single chunk of work and could slot after R4 if you prefer feel over look. Each stage is a branch
and a PR, with screenshots and tests like the previous ones. Asset storage: the repo stays small by
keeping textures at 1K and meshes low-poly; the download bundle grows to roughly 150 to 300 MB by the end
of R3.

Sources, all free: ambientCG (CC0), Poly Haven (CC0), Kenney (CC0), Quaternius (CC0), KayKit (CC0),
freesound CC0 filter, Sonniss GDC (royalty free). No Mixamo (licence), no Quixel (Epic only), no
Sketchfab paid packs.
