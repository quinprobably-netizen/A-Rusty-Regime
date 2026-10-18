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

## Gunsmith
Rifle, shotgun and pistol each have four slots (optic, muzzle, grip, stock) with three parts.
Parts are multipliers on the `Gun` tuning (spread, recoil, cooldown, velocity, damage) applied
when firing; primitive meshes (scope, suppressor, grip, stock pad) appear on the viewmodel. Stat
bars: damage, rate, accuracy, control, range. The loadout saves in `save.toml`.
