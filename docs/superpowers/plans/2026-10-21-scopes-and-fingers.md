# Scopes and Fingers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Picture-in-picture scopes with fixed per-gun magnification and reticles, and characters whose fingers wrap each weapon's real grip and pull its trigger.

**Architecture:** A second camera renders the magnified view into an image shown on a disc at the scope's eyepiece. The disc's placement comes from a new `scope.eye` socket in the weapon glbs. The character build keeps its three finger bones per finger in the game rig. A new Blender solver curls them against each weapon's real mesh, and writes the poses to one file per character. The game puts those poses on top of the clips and the first-person IK.

**Tech Stack:** Bevy 0.19, WGSL, headless Blender (bpy 5 in a Python 3.11 venv), TOML.

**Spec:** `docs/superpowers/specs/2026-10-21-scopes-and-fingers-design.md`

## Global Constraints

- Free tools and assets only. Everything is built in code (no paid assets).
- Zoom is fixed: DMR 8×, rifle 3×, SMG 3×, red dot and irons 1×.
- Scoped main-view zoom: `ads_fov_scoped = 0.85`.
- Finger bones are named `f_<finger>.<1-3>.<L|R>`, with fingers thumb, index, middle, ring, pinky. The rig has 52 bones.
- A weapon or character with no solved pose falls back to the rest fist (the current look). It never shows a broken hand.

## Review Focus

- Switching weapons while aimed: the scope camera must turn off and the finger pose must change on the same frame.
- A gun without a scope fitted: no scope camera, and the main view uses `ads_fov`, not `ads_fov_scoped`.
- The gunsmith showcase and the menus: the scope camera stays off.
- Driving: the scope camera is off and the arms are hidden, as now.
- A missing or malformed `<id>.grips.toml`: the game logs it and keeps the fist.

---

### Task 1: Shared grip points

**Files:** Create `assets/grips.toml`. Modify `src/character.rs` (`Hands`, `hands`, `held_transform`) and `src/arms.rs`. Test in `src/character.rs`.

**Interfaces:**
- Produces: `grips.toml` with `[<weapon id>] right = [x,y,z]`, `left = [x,y,z]`, `left_bone = "root"|"pump"`, and optionally `vertical = [x,y,z]` and `angled = [x,y,z]`, all in weapon glTF space. The values are today's `hands()` table; the vertical and angled points are the foregrip bodies' centres.
- `hands(kind) -> &'static Hands`, where `Hands { right: Vec3, left: Option<(Vec3, String)>, vertical: Option<Vec3>, angled: Option<Vec3> }` is parsed once from an `include_str!`.

- [ ] Test `grip_points_match_the_old_table`: rifle right `(0,-0.038,0.030)`, shotgun left bone `pump`, pistol has no left hand.
- [ ] Move the table to the toml, then parse it with `OnceLock`.
- [ ] `cargo test` passes. Commit.

### Task 2: Scope sockets in the weapon glbs

**Files:** Modify `tools/weapons/parts.py` (`optic_scope`, `optic_reddot`) and `tools/weapons/guns/dmr.py` (`long_scope`). Rebuild `rifle`, `smg`, `pistol`, `dmr`.

**Interfaces:**
- Produces: the empty `scope.eye`, parented like the optic, sitting at the rear lens centre with scale = the lens radius. Its -Z (glTF) runs down the scope. The empty `reddot.lens` sits at the window centre with scale `(half width, 1, half height)` in Blender.

- [ ] Add the sockets, and add `scope.eye` and `reddot.lens` to each gun's `--check` sockets where the part exists.
- [ ] `tools/weapons/build.sh rifle smg pistol dmr`, then `build.sh --check` passes for all ten. Commit the glbs.

### Task 3: Zoom and sensitivity maths

**Files:** Modify `src/tuning.rs`, `tuning.toml` and `src/input.rs`. Create `src/scope.rs` (the pure functions first).

**Interfaces:**
- Produces: `Gun::scope_mag: f32` (0 = no magnifying optic for this gun; rifle 3, smg 3, dmr 8) and `Tuning::ads_fov_scoped: f32 = 0.85`.
- `scope::main_fov(hip: f32, level: f32, ads_fov: f32) -> f32`.
- `scope::scope_fov(lens_angle: f32, hip: f32, main: f32, mag: f32) -> f32 = lens_angle * hip / (main * mag)`.
- `scope::look_scale(level: f32, ads_fov: f32, mag: Option<f32>) -> f32`: with a scope it is `lerp(1, 1/mag, level)`, otherwise today's `1 - level*(1-ads_fov)`.

- [ ] Tests: `scope_fov_magnifies` (with the lens at 13° and the main view at 0.85 of hip, mag 3 gives 13/(0.85·3)), `look_scale_scoped` (level 1 with mag 8 gives 0.125), `look_scale_irons_unchanged`.
- [ ] Implement, and wire `input.rs` and `camera.rs` to the functions. Commit.

### Task 4: Scope camera, lens and red dot

**Files:** Modify `src/scope.rs`, `src/viewmodel.rs` (expose the current optic part and the socket entities in `Rig`, align ADS to the socket) and `src/main.rs`. Create `assets/shaders/scope.wgsl`.

**Interfaces:**
- Consumes: `scope.eye` and `reddot.lens` (Task 2); `scope_mag` and `scope_fov` (Task 3).
- Produces: `ScopeCamera` (Camera3d, order -1, near 1.0 m, renders into a 512² `Rgba16Float` image with `Tonemapping::None` and the main camera's fog). It is active only while `Aim.level > 0.01`, a scope is fitted, and you are in game.
- Produces: `LensMaterial` (a `Material` with the image, `reticle: u32` (1 = mil-dot, 2 = chevron, 3 = red dot), `eye: Vec2` (the eye's offset from the axis in lens radii) and `aim: f32`), on a unit circle child of `scope.eye`, or a 2×2 rectangle child of `reddot.lens`.

- [ ] Test (headless App): the scope camera is inactive at `Aim.level == 0`.
- [ ] Implement, then run `cargo test` and `cargo clippy`. Commit.

### Task 5: Finger bones in the character rig

**Files:** Modify `tools/character/real.py` (`Anatomy.__init__`, `body`), `tools/character/kit.py` (`build_armature`, `check`).

**Interfaces:**
- Produces: game bones `f_<finger>.<i>.<side>` at their rest-fist places (`fit[n] @ base[n]`), deforming, with weights kept (no merge into `hand.*`).

- [ ] Change, then rebuild `runner` and run `--check` (52 bones, finger weights present). Commit when all are rebuilt (Task 8).

### Task 6: Grip solver

**Files:** Create `tools/character/grips.py`, called from `Char.finish` after the export.

**Interfaces:**
- Consumes: `assets/grips.toml` and `assets/models/weapons/<id>.glb`.
- Produces: `assets/models/character/<id>.grips.toml`, with tables `[<weapon>.<pose>]` where pose is one of `R`, `R_fire`, `L`, `L_vertical`, `L_angled`. Each has `at = [x,y,z]` (the grip point, in weapon space, after the palm-touch shift), `rot = [x,y,z,w]` (the grip frame → weapon space rotation) and, per finger, three `[x,y,z,w]` local deltas (the joint's rest rotation × delta).
- Curl: flex each joint in 0.5° steps until a distal sample lies within the finger radius + 2 mm of the weapon mesh. On the right hand, the index finger is solved by a grid search that puts its distal pad on the trigger (the weapon origin, 5 mm forward). `R_fire` moves that target 6 mm back.

- [ ] Run it on `runner`, then sanity-check the file (every two-handed weapon has `R` and `L`, and the deltas are unit quaternions).

### Task 7: Game applies finger poses

**Files:** Create `src/fingers.rs`. Modify `src/arms.rs` (use `at`/`rot` and recompute the finger globals after the IK) and `src/main.rs`.

**Interfaces:**
- Consumes: the per-character grip files (Task 6); `hands()` (Task 1).
- Produces: `fingers::Solved` (character id → weapon → pose → `HandPose { at, rot, fingers: [Quat; 15] }`), loaded at startup. A `fingers::pose` system sets finger joint locals = rest × delta, for every rig holding a weapon, before transform propagation. Trigger pull: `R` slerps to `R_fire` for 0.06 s after each `WeaponFired`. The left pose follows the fitted grip part.

- [ ] Tests: `parses_solved_grips`, `missing_pose_falls_back_to_rest`.
- [ ] Implement, then run `cargo test` and `cargo clippy`. Commit.

### Task 8: Rebuild and ship

- [ ] Rebuild all twelve characters, run `build.sh --check`, `cargo test` and `cargo clippy`.
- [ ] Commit the glbs and grip files, push, and update PR #7.
