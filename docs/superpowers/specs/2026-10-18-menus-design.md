# Menus (2026-10-18)

Reference: Titanfall 2's front end (big left-aligned uppercase list, the live world blurred-ish
behind it, button hints along the bottom) and Delta Force's gunsmith (attachment slots around the
weapon with stat bars). No new assets: Bevy UI, the built-in Fira Mono font, the island as the
backdrop and the first-person weapon models as the gunsmith render.

## Screens
- `Screen` state: `Title` (boot), `Playing`, `Paused`. Time (`Time<Virtual>`) is paused on the
  title and pause screens, so physics, AI and the clock stop; the world still renders behind.
- A `Panel` on top of Title/Paused: `Main`, `Settings`, `Controls`, `Gunsmith`.
- Title list: PLAY, GUNSMITH, SETTINGS, CONTROLS, QUIT. Pause list: RESUME, GUNSMITH, SETTINGS,
  CONTROLS, QUIT. Esc: Playing -> Paused, Paused -> Playing, any panel -> Main.
- Navigation: W/S or arrows (d-pad) move, A/D or left/right (d-pad) adjust, Enter/Space (A) pick,
  Esc (B) back, Q/E (LB/RB) switch the gunsmith weapon. Mouse: hover selects, click picks, `<`
  `>` buttons adjust. The HUD hides while a menu is up; the cursor is released.

## Settings (`settings.toml` next to `tuning.toml`)
Mouse sensitivity, invert Y, FOV, five volumes, atmosphere (restart), bloom, SSAO, TAA, shadow
distance, grass, tree density (restart). Saved as overrides that `tuning::load` applies after
`tuning.toml`, so F5 and hand edits keep working. Sound, look and post effects apply live.

## Gunsmith (now the quartermaster's counter)

*Since 2026-10-27 this panel is the Roost quartermaster's counter: no longer in the pause list, opened with E at the station, and parts and guns are bought with banked money (`src/quartermaster.rs`).*

Rifle, shotgun and pistol each have four slots (optic, muzzle, grip, stock) with three parts.
Parts are multipliers on the `Gun` tuning (spread, recoil, cooldown, velocity, damage) applied
when firing; primitive meshes (scope, suppressor, grip, stock pad) appear on the viewmodel. Stat
bars: damage, rate, accuracy, control, range. The loadout saves in `save.toml`.

## HUD
Same look as the menus. Top centre: a compass tape (N/E/S/W, ticks every 15 degrees) with an amber
notch for the heading and an amber mark where the objective is, the objective line and distance
under it. Top right: hits/kills, the haul, the world clock. Bottom left: health plate (number, tag
HP / BLEEDING / CRITICAL / RESPAWNING, bar that turns amber then red). Bottom centre: movement
state (AIR / SLIDE / WALLRUN / MANTLE / CROUCH) over the speed in m/s and u/s; while driving the
vehicle name, gear and hull with km/h, rpm and fuel bars. Bottom right: weapon slot pips, weapon
name, fitted gunsmith parts and the heat bar. Crosshair: four lines that open with the real spread
(heat, movement, crouch, ADS), amber when aiming, red on a hit; grapple power bar beneath it.
