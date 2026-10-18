# Custom character, outfits and abilities

Decided with Q on 2026-10-17 (Character models thread). This thread owns the character rig, outfits and
abilities; the hyper-realism thread's stage R3 consumes this rig instead of fetching a third-party one.

## Goals

1. A player character we made ourselves, down to the clothes: a hooded parkour mercenary with climbing
   gear. Realistic proportions (1.80 m), low-poly but clean, no third-party character meshes.
2. Outfits as data: swap clothes and colours without touching code. Soldiers and bots wear outfits from
   the same system so one rig serves everyone.
3. Movement baseline for everyone: wallrun (exists), double jump (new). No dash.
4. One ability slot. First ability: a Titanfall 2 style grapple with little to no cooldown.
5. Zero budget: Blender runs headless in the container (`bpy` 5.0 on Python 3.11, verified), the
   generator lives in the repo, every asset is reproducible from a script.

Out of scope for now: first-person arms rig (viewmodel stays), ragdolls, facial animation, netcode.

6. In-game wardrobe (asked 2026-10-17): a locker at the base camp opens a screen where Tab picks the slot,
   arrows cycle the style and the three colours, and the result is saved with extraction progress in
   `save.toml` as `[outfit]` overrides on top of the class default.

## The look

Default outfit "runner": charcoal softshell jacket with the hood up, slim plate carrier over it, cargo
trousers with knee pads, fingerless climbing gloves with taped wrists, trail boots, a chalk bag on the
belt, coiled rope across the chest, grapple launcher on the left forearm. Palette: three colours per
outfit (primary cloth, secondary cloth, accent/gear straps), tinted at runtime.

## Asset pipeline

`tools/character/build.py`, run as `tools/character/build.sh` (creates a venv, installs `bpy`, runs the
script). It outputs one file, `assets/models/character/character.glb`, holding:

- **Skeleton** `rig`: 22 bones. hips, spine, chest, neck, head; per side: shoulder, upper_arm, forearm,
  hand; upper_leg, lower_leg, foot, toe. Plus `prop_l_hand`, `prop_r_hand`, `prop_back` attach bones.
- **Base body** `body` (head, hands, neck skin) always on.
- **Part meshes**, one per slot and style, named `<slot>.<style>`: `head.hood`, `head.beanie`,
  `head.cap`, `head.helmet`, `face.none`, `face.mask`, `face.goggles`, `torso.jacket`, `torso.carrier`
  (worn over torso), `torso.shirt`, `hands.gloves`, `hands.bare`, `legs.cargo`, `legs.kneepads`
  (overlay), `feet.boots`, `feet.sneakers`, `back.rope`, `back.pack`, `back.none`, `gear.launcher`,
  `gear.chalkbag`. Every part is skinned to the shared skeleton, so clothes move with the body.
  Each mesh uses a material named `primary`, `secondary`, `accent` or `skin`, which is what the game tints.
- **Animation clips**, keyframed procedurally in the script (no mocap, so they are simple but clean):
  `idle`, `walk`, `run`, `sprint`, `jump`, `fall`, `crouch`, `slide`, `wallrun_l`, `wallrun_r`,
  `mantle`, `grapple`. Seated (`drive`, `ride`), `aim` and `die` clips come with the work that uses them
  (vehicle seating, soldier AI, ragdolls) so nothing ships unused.
- A preview render per outfit to `screenshots/character-<outfit>.png` with Blender's Workbench engine
  (CPU, a few seconds each), so Q can see each pass without the game.

The script is the source of truth. Changing proportions, adding a part or a clip is a Python edit and a
rerun; the glb is committed so the game builds without Blender.

## Data

`assets/characters.toml`, hot-reloaded on F5 like `tuning.toml`:

```toml
[outfit.runner]
head = "hood"
face = "mask"
torso = ["jacket", "carrier"]
hands = "gloves"
legs = ["cargo", "kneepads"]
feet = "boots"
back = "rope"
gear = ["launcher", "chalkbag"]
primary = "#2b2f33"
secondary = "#4a5a48"
accent = "#d98b2b"

[outfit.soldier]
head = "helmet"
torso = ["shirt", "carrier"]
legs = "cargo"
feet = "boots"
back = "pack"
primary = "#4c5a3a"
secondary = "#3a3a3a"
accent = "#8a7a50"

[class.pilot]
outfit = "runner"
ability = "grapple"
health = 100
sprint_mult = 1.0

[class.grunt]
outfit = "soldier"
ability = "none"
health = 100
sprint_mult = 0.9
```

A slot may name one style or a list (base layer then overlays). Missing slot means nothing worn there.
Unknown part names fail loudly in tests and fall back to nothing at runtime.

## Game side

- `src/character.rs` (new): loads `character.glb` once, spawns a `CharacterRig` for any entity with an
  `Outfit` component, shows only the listed part meshes, tints materials, and owns the animation graph.
  `body.rs` shrinks to "attach a `CharacterRig` under the player camera, head on the shadow-only layer";
  soldiers in `targets.rs` and `bots.rs` get `Outfit("soldier")` instead of loading the Kenney glb.
  The Kenney soldier stays for the arena level only.
- `src/abilities.rs` (new): `Ability` component with `Grapple { state, power }`, plus the `Class` resource
  picked from `characters.toml`. Input: a new `ability` action (Q key, mouse 4 as alternate).
- `controller.rs` gains double jump and a grapple force hook. `tuning.toml` gains (the grapple block lives in a `[grapple]` table, shown here flattened):

```toml
# Air jump
air_jumps = 1                 # extra jumps after leaving the ground; reset on ground, wall, mantle, grapple
air_jump_speed = 6.35
air_jump_redirect = 0.6       # 0 keeps momentum, 1 fully redirects horizontal speed to the wish direction

# Grapple (Titanfall 2 ships 50 power to fire, 50/s use, 100 max, 28 m rope)
grapple_range = 30.0
grapple_power_max = 100.0
grapple_power_to_fire = 10.0
grapple_power_use_rate = 10.0  # per second while pulling
grapple_power_regen = 60.0     # per second while not pulling
grapple_pull_accel = 55.0
grapple_pull_max_speed = 22.0
grapple_look_steer = 0.6       # pull direction blends from rope toward look direction by this much
grapple_release_boost = 2.0    # m/s added along velocity when you jump off the rope
grapple_gravity_cancel = 0.8   # share of gravity the taut rope carries, so low anchors still lift
```

Grapple rules, from the Titanfall 2 script and wiki behaviour: press fires a ray from the camera; it
hooks static geometry within range. While attached the player accelerates toward a blend of the rope
direction and the look direction, capped at `pull_max_speed`, gravity still applies so looking below the
anchor swings you down and gains speed. Releasing (press again, jump, power empty, anchor out of line of
sight, or rope stretched past range) keeps all velocity; jumping off adds the boost and refunds the air
jump. The rope is a thin cylinder from the left hand to the anchor. Power shows as a small arc in the HUD.

## Tests

Rust (headless, in `tests.rs`): `characters.toml` parses and every part it names exists in the part list
baked into `character.rs`; outfit layering order; double jump count resets on each reset source; grapple
power math (cannot fire under threshold, drains and regenerates at the tuned rates, auto release on
empty); pull direction blends toward look and never exceeds max speed; release keeps velocity.
Python: `build.py --check` verifies the exported glb has every bone, part and clip name the game expects.
Screenshots: `screenshots/character-runner.png` from Blender and `screenshots/player-grapple.png` from the
game (existing xvfb path).

## Order of work

1. Generator: rig, base body, runner outfit, idle/run/jump clips, preview render. Show Q the render.
2. `character.rs` with outfit data and tinting; player and soldiers switched over; tests.
3. Double jump, then grapple with HUD arc and rope; tests and a screenshot.
4. Remaining clips (slide, wallrun, mantle, grapple) and the soldier outfit.
5. Wardrobe locker at the camp, saved outfit overrides, tests for save round-trip.

Shared files touched: `body.rs`, `controller.rs`, `input.rs`, `hud.rs`, `tuning.rs`, `tuning.toml`,
`targets.rs`, `bots.rs`. The hyper-realism thread is told before each step that edits them.
