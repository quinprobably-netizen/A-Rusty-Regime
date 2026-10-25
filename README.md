# Rust Regime

FPS movement prototype in Rust: Bevy 0.19 + Avian 0.7 physics. TF2-style
movement and parkour, four weapons, a physics playground and a shooting range.

## One-click update and play
Set up once, then you never redownload the whole game:
1. Install Rust from https://rustup.rs (on Windows, accept the Visual Studio Build Tools it asks for).
2. Install Git (https://git-scm.com, Windows: use the defaults), then get the game once:
   `git clone https://github.com/quinprobably-netizen/A-Rusty-Regime.git`
   (or use GitHub Desktop's Clone button, but still install Git so the script can pull).
3. Double-click `play.bat` on Windows, or run `./play.sh` on Linux.

The script pulls only what changed, rebuilds only what changed, and starts the game.
The first build takes a while; later ones are quick.

## Run
```
cargo run --release
```
First build takes a while. Linux needs `libasound2-dev libudev-dev libwayland-dev libxkbcommon-dev`.
`cargo test` runs headless physics tests of the movement and weapons.
`RUST_REGIME_SCREENSHOT=shot.png cargo run --release` saves a frame and quits (handy with Xvfb + lavapipe on a box with no GPU).

## Controls
| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Move | WASD | Left stick (analog) |
| Look | Mouse (click to lock) | Right stick |
| Menu / pause | Esc | Start |
| Jump / wall jump / double jump | Space | A / Cross |
| Grapple (fire, press again to let go) | G or mouse 4 | L3 |
| Wardrobe (at the camp locker) | E, then arrows, 1 2 3 | |
| Crouch / slide | Ctrl, Shift or C | B / Circle, L3 or LT |
| Fire | Left mouse | RT |
| Aim down sights | Right mouse | LT |
| Flashlight | F | |
| Weapon 1-4 | 1 2 3 4 | D-pad up / right / down / left |
| Next / previous weapon | Wheel down / up | RB / LB |
| Last weapon | Q | Y / Triangle |
| Enter / leave a vehicle | E | X / Square |
| Drive (throttle, brake, reverse, steer) | WASD | Left stick |
| Handbrake | Space | A / Cross |
| Respawn | R | Select / Back |
| Reload `tuning.toml` | F5 | |

## Menus
The game boots to a title screen over the live island; Esc pauses (time stops, the cursor comes
back). Both lists lead to the same screens: **Gunsmith** (four attachment slots per hitscan gun,
parts change spread, recoil, rate, velocity and damage and show on the viewmodel; stat bars compare
the bare gun), **Wardrobe** (pick a character and its three colours, shown from the front), **Settings** (mouse sensitivity, invert Y, FOV, five volumes, sky, bloom, ambient
occlusion, anti-aliasing, shadow distance, grass, trees; saved to `settings.toml`, which lays over
`tuning.toml` so F5 keeps your choices) and **Controls**. Navigate with W/S or arrows, adjust with
A/D, Enter picks, Esc backs out; the d-pad, A and B do the same on a pad; the mouse works too.
`RUST_REGIME_MENU=title|pause|settings|controls|gunsmith|wardrobe` opens straight into a screen
(with `RUST_REGIME_SCREENSHOT` it skips the title unless set). Design notes:
`docs/superpowers/specs/2026-10-18-menus-design.md`.

## HUD
Compass tape with the objective marked, health plate bottom left, movement readout (or vehicle
dials) bottom centre, weapon plate with slot pips, fitted parts and heat bottom right, and a
crosshair that opens with the gun's real spread. The Esc hint fades after a few seconds.

## Movement
- **Source/TF2 core** at 66 ticks/s: ground friction and acceleration, air strafing (30u air cap), bunny hopping (jump on the landing tick to skip friction), crouch-jumping (legs tuck up in the air), ramp sliding and surfing on steep slopes, stair stepping.
- **Parkour**: wall run (run along a wall in the air while holding forward), wall jump (jump off a wall, alternate walls to climb), mantle (push into a ledge up to 1.5 m above your feet), slide (crouch while running, faster downhill).
- **Double jump**: one extra jump in the air, which can bend your momentum toward where you push. It comes back when you touch ground, a wall, a ledge or a grapple anchor.
- **Grapple** (the pilot class ability): G fires a hook at anything within 30 m. You are pulled toward it, the pull bends toward where you look, gravity keeps working so looking below the anchor swings you. Press again or jump to let go and keep all your speed; jumping off adds a boost. It runs on a power meter like Titanfall 2's, tuned under `[grapple]` to be nearly free.
- **Rocket jumps**: rockets knock you and props around. Aim at your feet and jump.

## Characters, factions and classes
Twelve characters in four factions, all our own, built in code with headless Blender like the
guns: the **Regime** (a death cult that worships the Algorithm: Acolyte, Zealot, Choir), the
**Scrappers** (luddite tinkerers: Mechanic, Bruiser, Trapper), the **Deserters** (ex-cult parkour
pilots, your side: Runner, Breaker, Ghost) and the **PMC** (contractors who sell to everyone:
Contractor, Juggernaut, Handler). `tools/character/build.sh [ids] [--no-bake] [--preview]
[--check]` sets up `bpy` on Python 3.11 and writes one `assets/models/character/<id>.glb` per
character from `tools/character/chars/<id>.py` and the shared kit (`kit.py`). Each has its own
body and proportions on one 22-bone skeleton with twelve procedural clips (idle, walk, run,
sprint, jump, fall, crouch, slide, wall run left/right, mantle, grapple), baked edge wear and dirt,
and three skinned meshes (`mesh.body`, `mesh.head`, `mesh.arms`). `--check` verifies bones,
meshes, clips and the triangle budget. Design notes:
`docs/superpowers/specs/2026-10-18-character-roster-design.md`.

`assets/characters.toml` holds each character's faction, default colours and the weapon bots
wearing it carry, which factions each soldier team fields (team 0 is your side: Deserters; team 1
the Regime, Scrappers and PMC), and the classes (character, ability, health). Edit it and press F5.
The locker at the base camp opens the wardrobe: left/right picks the character, 1/2/3 cycle its
colours, E saves it to `save.toml`. Your body stands under the camera, so you see your legs when
you look down and your shadow on the ground; head and arms are drawn only into the shadow map.
In first person a second copy of your character shows just its arms, with both hands placed on
the current weapon every frame (two-bone IK on hand points in `character::hands`), so the arms
follow every weapon clip.

## Weapons
| Slot | Weapon | Notes |
|---|---|---|
| 1 | Rocket launcher | Slow projectile, splash knockback on you, props and targets |
| 2 | Rifle | Automatic, fast bullet, tight spread |
| 3 | Shotgun | 10 pellets, wide spread, big push on props, short range |
| 4 | Pistol | Semi-automatic, one shot per click, accurate |

Hits push physics props and damage targets. Each gun has its own `[rifle]`,
`[shotgun]`, `[pistol]` table in `tuning.toml` (damage, cooldown, pellets, spread,
range, prop impulse, automatic, recoil kick).

Rifle, shotgun and pistol fire real bullets: they drop, slow down, drift in the
wind and take time to arrive. Wood walls, crates and thin metal let them through
with less damage, stone and concrete stop them. Head hits do 2.5x, legs 0.6x.
Recoil climbs with sustained fire and settles when you stop; aiming down sights
zooms in and tightens the spread.

## Survival and the world
- **Health**: heavy hits make you bleed until a medkit (green boxes at camp and five
  sites). Health regenerates only up to 60% and not while bleeding.
- **Soldiers** hear gunshots up to 150 m, call nearby squadmates, and run to cover
  that hides them from you when hit.
- **Roads**: dirt roads link camp to every site. Tyres grip better on them than off.
- **Vehicles** burn fuel and take damage from crashes and bullets (HUD shows speed,
  gear, fuel and hull). A wreck throws you out and respawns at camp after 30 s.
  Park within 15 m of your vehicle's home spot to refuel and repair.
- **Day and night**: a 48-minute day (`[world] day_minutes`, 0 stops the clock) with
  a moon, headlights and an F flashlight.
- **Weather**: clear, overcast, rain and fog roll through, with wet ground and rain.
  `[world] sky` can hold one.
- **Sound** is synthesized at startup. Put a CC0 `.ogg` with the same name in
  `assets/sounds/` (rifle, shotgun, pistol, rocket, explosion, hit, hurt, jump, land,
  engine_big, engine_small, engine_bike, wind, surf) to replace one.

All numbers live in `tuning.toml`.

## Island
The default level is a 4 km seeded island (`[island]` in `tuning.toml`: seed, size,
cell size, peak height, water level). Fall in the water and you respawn on the
spawn pad. `RUST_REGIME_LEVEL=arena` runs the original arena below, which the
tests also use.

Six sites sit in the island's core, each a parkour toy first and a fight second:
base camp (spawn, no enemies, the physics playground), the radio tower on the
highest peak (a spiral of ledges to mantle up, drones circling), the fort to the
east (walls to run, the mantle tower and wall-jump chimney, four soldiers), the
quarry to the west (terraces to slide and surf down, soldiers on every ring), the
ruins to the north (a wall-run gap, two soldiers) and the lighthouse on the south
coast (a spiral around the tower, drones).

Soldiers patrol a route and shoot when they have a clear line to you within
`soldier.sight` meters; they lose interest after `soldier.forget` seconds. You
have `player.health` hit points that regenerate after `player.regen_delay`
seconds; dying puts you back at base camp. Everything is in `tuning.toml`.

### Vehicles
Three vehicles sit in a row south of base camp, with a Humvee outside the fort
gate, a jeep on the quarry rim and a bike at the lighthouse: a Humvee (2.6 t,
4WD, 4-speed auto), a Willys-style jeep (1.1 t, 4WD, 3-speed) and a military
dirt bike (150 kg, 5-speed, leans into its turns). Walk up and press E; the
camera swings behind, the mouse orbits it, W/S accelerate and brake (S from a
standstill reverses), Space is the handbrake, E steps out. Fall off the island
and the vehicle respawns where it started. The physics is a raycast-wheel port
of the tyre, suspension and engine models from Q's Regolith Rally, stepped at
66 Hz on an Avian body (`src/vehicle/`); the bodies are built from scaled cubes
and cylinders in code. `[vehicle]` in `tuning.toml` sets grip and the enter
radius.


### Extraction loop
Caches (brown boxes) lie around every site and out in the wilderness ring;
walk over one to carry its value. Three extraction pads (yellow discs with
lit posts) sit in the ring between the core and the coast; stand on one for
`loot.extract_time` seconds to bank your haul and start a new run from base
camp. Die and you lose what you carry. Banked value, runs, deaths and
mission progress persist in `save.toml` next to the binary
(`RUST_REGIME_SAVE` overrides the path).

### Missions
A chain of six objectives shows at the top of the screen with its distance
and a bearing mark (`^` ahead, `<` `>` to a side, `v` behind): climb the
radio tower, clear the fort, recover the quarry cache and extract with it,
drive a Humvee to the ruins, reach the lighthouse top. Soldiers now chase
the last place they saw you and close to `soldier.hold` meters.

### 6v6 (optional)
`RUST_REGIME_MODE=6v6` starts you at the fort gate with five blue bots
against six red bots. Bots fight each other and you; first team to
`match.kills_to_win` kills wins and the scores reset. There is no netcode:
this is the bot mode the open-world design called for, and the spec leaves
networking for later only if still wanted.

### The look
The island renders with a physical sky and sun (Bevy's atmosphere), sunlight exposure,
AgX tonemapping, bloom, screen-space ambient occlusion and temporal anti-aliasing. The
ground is a four-layer PBR splat (grass, dirt, rock, sand; rock is triplanar on cliffs)
and the site walls, crates and posts use triplanar concrete, wood and rusty metal, so
nothing stretches. The sea has moving waves and foam where it meets the shore. Pines,
scrub and boulders are generated meshes placed by noise (about 5500 trees), and grass
blades are built in cells around you. `[graphics]` in `tuning.toml` turns each effect
off, scales the textures and the vegetation, and sets the exposure.

### Debug moon
`RUST_REGIME_LEVEL=moon` drops you on the moon from `assets/system.toml`: a bare 2 km
sphere with ±10 m of grey rolling ground, a black sky and a visibly curved horizon. You
start on a small parkour course (a step, a wall to run, a ledge to mantle, a roof to
slide under) on a deck at latitude 20°. Gravity points at the centre wherever you walk,
terrain chunks stream in around you on worker threads, only the ground within
`terrain.bubble` is solid, and the world re-centres on you every 2 km. There is nothing
to fight yet; it is the test bed for the round home world. Measured on a Ryzen 5 8500G
(release, headless, 4 workers, 66 updates a second, running east at 7.5 m/s for 30 s
once the first tiling had loaded): at `terrain.cell = 0.5` a chunk builds in 0.49 ms
on average (0.79 ms at most over the first 200) and 21.0 chunks a second are applied;
at `terrain.cell = 1` 0.48 ms (0.71 ms max) and 10.1 a second.

## Arena
- Spawn area: dominoes, crate pyramid, barrels, balls, heavy crates
- Ramps at 15, 30 and 45 degrees, a long wall for wall running, box steps
- Parkour course (far side): wall-run gap, wall-jump chimney, mantle tower, slide tunnel
- Shooting range (south wall): six soldier dummies that fall over when killed and
  drones that circle overhead and pop; everything respawns after `target_respawn` seconds.
  The HUD counts hits and kills and the crosshair flashes on a hit.
- Props: columns, statues, trees, banners, weapon racks, plus blocks and brick
  piles you can shoot around.

## Assets
All models are CC0 glTF files by [Kenney](https://kenney.nl) (thanks!), taken from
the MIT-licensed [Starter Kit FPS](https://github.com/KenneyNL/Starter-Kit-FPS)
(blasters, flying enemy) and [Starter Kit Basic Scene](https://github.com/KenneyNL/Starter-Kit-Basic-Scene)
(Mini Arena: columns, statue, trees, banners, racks, blocks, bricks; its soldier is no longer used).
The character and clothes are generated by our own Blender script (see above).
They live in `assets/models/` and must sit next to the binary. The rocket launcher
viewmodel and the effects are generated meshes. The textures in `assets/textures/` are
CC0 1K sets from [ambientCG](https://ambientcg.com) (Grass004, Ground103, Rock035,
Ground054, Concrete034, Planks037A, Metal063). Trees, rocks and grass are generated.
