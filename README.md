# Rust Regime

FPS movement prototype in Rust: Bevy 0.19 + Avian 0.7 physics. TF2-style
movement and parkour, four weapons, a physics playground and a shooting range.

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
| Look | Mouse (click to lock, Esc to release) | Right stick |
| Jump / wall jump | Space | A / Cross |
| Crouch / slide | Ctrl, Shift or C | B / Circle, L3 or LT |
| Fire | Left mouse | RT |
| Weapon 1-4 | 1 2 3 4 | D-pad up / right / down / left |
| Next / previous weapon | Wheel down / up | RB / LB |
| Last weapon | Q | Y / Triangle |
| Enter / leave a vehicle | E | X / Square |
| Drive (throttle, brake, reverse, steer) | WASD | Left stick |
| Handbrake | Space | A / Cross |
| Respawn | R | Select / Back |
| Reload `tuning.toml` | F5 | |

## Movement
- **Source/TF2 core** at 66 ticks/s: ground friction and acceleration, air strafing (30u air cap), bunny hopping (jump on the landing tick to skip friction), crouch-jumping (legs tuck up in the air), ramp sliding and surfing on steep slopes, stair stepping.
- **Parkour**: wall run (run along a wall in the air while holding forward), wall jump (jump off a wall, alternate walls to climb), mantle (push into a ledge up to 1.5 m above your feet), slide (crouch while running, faster downhill).
- **Rocket jumps**: rockets knock you and props around. Aim at your feet and jump.

## Player body
You have a body: Kenney's soldier stands under the camera, so you see your legs
and feet when you look down and your shadow on the ground. It plays idle, walk,
sprint, jump, fall and crouch clips from the movement state (sliding crouches,
wall running sprints, mantling jumps), with footsteps paced to your speed. The
head is drawn only into the shadow map so it never covers the screen.

## Weapons
| Slot | Weapon | Notes |
|---|---|---|
| 1 | Rocket launcher | Slow projectile, splash knockback on you, props and targets |
| 2 | Rifle | Automatic hitscan, tight spread |
| 3 | Shotgun | 10 pellets, wide spread, big push on props, short range |
| 4 | Pistol | Semi-automatic, one shot per click, accurate |

Hits push physics props and damage targets. Each gun has its own `[rifle]`,
`[shotgun]`, `[pistol]` table in `tuning.toml` (damage, cooldown, pellets, spread,
range, prop impulse, automatic, recoil kick).

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
(Mini Arena: the rigged, animated soldier used for the player body and the dummies, columns, statue, trees, banners, racks, blocks, bricks).
They live in `assets/models/` and must sit next to the binary. The rocket launcher
viewmodel and the effects are generated meshes.
