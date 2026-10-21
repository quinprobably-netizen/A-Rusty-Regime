# Working scopes and fingered hands

Decided with Q on 2026-10-21 in the "Rigging brainstorm" thread.

## Problem

- **Hands:** the 22-bone rig has no finger bones. Each hand is a fixed curled mitt (`tools/character/kit.py`, the hand builder), and `src/arms.rs` IK only places the wrist on `prop_hand.R` / `prop_hand.L`. Fingers never wrap the grip or reach the trigger.
- **Scopes:** every optic gives the same zoom (`ads_fov = 0.7`, `src/camera.rs`), lens glass is opaque, and there is no reticle.

## Scopes: picture-in-picture

- **Scope camera.** While `Aim.level > 0` and a magnifying optic is fitted, a second camera renders into a 512x512 texture (a `scope_resolution` setting). It sits at the player eye, looks down the aim direction, and uses FOV = main FOV / magnification. It is turned off when you aren't aiming, so the hip view costs nothing.
- **Main view.** With a magnifying optic, the main camera zooms only to `ads_fov_scoped = 0.85`, so the screen around the scope stays near normal. Irons and the red dot keep `ads_fov` as now.
- **Magnification per gun** (fixed, the values live in `tuning.toml` under each gun as `scope_mag`):
  - DMR long scope: 8x
  - rifle and SMG scope: 3x
  - red dot and irons on any gun: 1x (no scope camera)
- **Lens material.** A new `assets/shaders/scope.wgsl` puts the scope texture on the rear lens (`lens_r`). It draws:
  - the reticle: mil-dot cross on the 8x, chevron on the 3x
  - an eye-box vignette: the image darkens and shifts toward the rim as the eye moves off the scope axis, during sway and recoil
  - The front lens stays tinted glass.
- **Red dot.** Its lens shader draws an emissive dot projected at infinity, so the dot stays on target while the gun sways.
- **Sensitivity.** Look sensitivity is scaled by `1 / scope_mag` while scoped. This replaces the `ads_fov` factor in `src/input.rs` for scoped guns.

## Hands: full fingers

- **Rig.** Add 15 bones per hand to `kit.py`'s skeleton, parented under `hand.L` / `hand.R`:
  - `thumb.01-03.X`, `index.01-03.X`, `middle.01-03.X`, `ring.01-03.X`, `pinky.01-03.X`
  - That makes the rig 52 bones.
  - The hand mesh is rebuilt flat with fingers straight and weight-painted to those bones.
  - All twelve characters are rebuilt through `tools/character/build.sh`. Existing clips keep a relaxed default curl.
- **Grip solver.** `tools/weapons/grip.py` runs headless after each weapon build:
  - It loads the weapon glb, places the rig's hand on each grip frame and curls each finger joint, one joint at a time, until it touches the weapon mesh. This uses BVH raycasts against the weapon's collision of the visible mesh.
  - The right index finger stops on the trigger face instead.
  - The thumb wraps the far side of the grip, or rests along the frame on pistols.
  - It writes `assets/grips.toml`, which holds per-weapon joint angles for the right hand and for every left-hand support surface the gun has: `pump`, `handguard`, `att.grip.vertical`, `att.grip.angled`, `mag` (for the pistol's two-hand hold, which stays out of scope for now).
- **Game side** (`src/arms.rs`, `src/character.rs`):
  - After the wrist IK, the game sets finger bone rotations from `grips.toml`. The left-hand pose follows whichever support part the gunsmith has fitted.
  - Firing animates the right index finger from rest to a pulled angle and back, over the gun's fire interval.
  - Reloads blend the left hand to an open pose while it is off the gun.
  - Third-person bodies, the player body and bots read the same poses.
- **Fallback.** A weapon missing from `grips.toml` uses a generic closed fist, so a new gun never shows a broken hand.

## Testing

- `tools/character/build.sh --check`: 52 bones, 15 finger bones per hand, finger weights present.
- `tools/weapons/build.sh --check`: every two-hand weapon has a `grips.toml` entry for its right hand and its default support surface.
- Rust tests:
  - `grips.toml` parses and every `WeaponKind` resolves to a pose or the fallback
  - scope FOV = main FOV / `scope_mag`
  - sensitivity scaling while scoped
  - the scope camera is inactive at `Aim.level == 0`

## Out of scope

Variable zoom, scope glint, death and seated poses, and finger animation on non-weapon clips (climb, grapple).
