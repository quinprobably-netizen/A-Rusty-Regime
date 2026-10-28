# Comic Toon World Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Piece 2 of the comic redesign: every lit surface in the world shades in flat bands with halftone dots in the shadows, and ink outlines run around everything, behind one "Comic shading" setting.

**Architecture:** Toon shading goes into Bevy's own lighting function. At startup `comic::toon` patches the `bevy_pbr::pbr_functions` shader asset so `apply_pbr_lighting` passes its exposed light through `toon_shade` (3 bands + highlight, halftone in the shadow band, emissive untouched). Every `StandardMaterial`, every glTF material and the three `ExtendedMaterial`s in `look.rs` call that function, so they all go toon with no call-site changes. Turning the setting off puts the original source back. Outlines come from one post-process pass, `comic::edges`, that reads the depth and normal prepasses on the player camera and draws ink where depth or normals break.

**Tech Stack:** Rust 2024, Bevy 0.19.1 render graph (`Core3dSystems::PostProcess`, `ViewPrepassTextures`), WGSL.

**Spec:** `docs/superpowers/specs/2026-10-28-comic-redesign-design.md`, section "2. World: per-material toon shading".

## Global Constraints

- Lighting stays physical up to the band step: sun, shadows, atmosphere and exposure are unchanged; only the final exposed light is quantised.
- Emissive light (glows, exhausts, muzzle flash) is never banded.
- The "Comic shading" setting is on by default. Off restores plain PBR, removes the edge pass and its prepasses, and restores SSAO and bloom to the player's own settings.
- Under toon: SSAO is off, bloom is a low preset (intensity 0.05), the atmosphere stays.
- Ink is `ComicTheme::ink` (#111111).
- Headless tests (no render app, no `Assets<Shader>`) must still build every plugin.

## Rulings against the spec

- Ruling: toon shading is a patch of Bevy's `apply_pbr_lighting`, not a `ToonExt` material swapped in at ~90 call sites. About 15 systems mutate or query `StandardMaterial` at runtime (ship exhaust glow, muzzle flash, field alpha, scope lens, character tinting), and a material swap would silently break each one. The patch keeps per-material shading (it runs in each material's fragment shader, not as a post filter). Cost if wrong: it is tied to Bevy 0.19.1's shader text. If an upgrade moves the anchor line, the patch logs a warning and the game renders plain PBR; a test pins the anchor.
- Ruling: one depth/normal edge pass draws all outlines, with no inverted hulls. Inverted hulls on skinned characters would need a custom skinned vertex pipeline. Cost if wrong: line width is screen-constant, not per-object.
- Ruling: the spec's four conversion groups land as commits on PR #41, not as four PRs, because Q asked for everything on one branch. Effects (group d) need no separate work: emissive stays smooth and the edge pass inks them like everything else, and `sfx_pop` on hits shipped in piece 3.

## Review Focus

1. Metallic surfaces (near-black diffuse) and fully unlit surfaces must not blow up the band ratio to white or NaN. Owned by Task 1 (`toon_shade` divides by `max(lum(base), 0.02)`).
2. The patch must apply exactly once: a second run must not double-wrap, and off then on must work. Owned by Task 1 (`patch_is_idempotent_and_reversible`).
3. The sky (depth 0) next to geometry should give a clean silhouette, never a full-screen ink flood. Distant terrain at grazing angles should not turn black. Owned by Task 2 (Laplacian on reverse-Z depth, which is flat on planes; a relative threshold).
4. When the setting is toggled at runtime, the prepass components and the edge pass must come and go together, so the edge pass never runs without its prepass textures. Owned by Task 2 (`edges_follow_the_setting`).
5. An old `settings.toml` with no `toon` key loads with toon on. Owned by Task 3.

---

### Task 1: Toon shading patch

**Files:** Create `src/comic/toon.rs`. Modify `src/comic/mod.rs`.

**Interfaces:** Produces `pub(crate) const ANCHOR: &str` (the "Total light" line of `apply_pbr_lighting`), `pub(crate) fn patch(src: &str) -> Option<String>` (None when the anchor is missing or the source is already patched), `pub(crate) fn unpatch(src: &str) -> Option<String>`, `#[derive(Resource)] pub struct Toon(pub bool)` (default true), and `ToonPlugin`. `ToonPlugin`'s `sync_shader` system loads `embedded://bevy_pbr/render/pbr_functions.wgsl` and, once the shader is loaded, patches or unpatches it to match `Toon`.

- [ ] Tests: `patch_wraps_the_total_light_once` (a fixture holding `ANCHOR` gets `toon_shade(` in place of the exposure line, plus `fn toon_shade` appended, and `patch` of the result is None); `patch_is_idempotent_and_reversible` (`unpatch(patch(s)) == s`); `missing_anchor_leaves_it_alone` (`patch("fn x() {}") == None`).
- [ ] Run (FAIL), implement, run (PASS), commit.

### Task 2: Ink edge pass

**Files:** Create `src/comic/edges.rs` and `assets/shaders/ink_edges.wgsl`.

**Interfaces:** Produces `#[derive(Component, Clone, Copy, ExtractComponent, ShaderType)] pub struct InkEdges { ink: Vec4, depth_threshold: f32, normal_threshold: f32, width: f32, _pad: f32 }` and `EdgesPlugin`. `follow_toon` puts `InkEdges` + `DepthPrepass` + `NormalPrepass` on the `PlayerCamera` while `Toon(true)`, and removes all three on `Toon(false)`. The render system runs in `Core3dSystems::PostProcess` before tonemapping. It binds the source colour, a sampler, the prepass depth and normal textures, and the uniform. It keeps one pipeline per view texture format.

- [ ] Test `edges_follow_the_setting`: an app with `MinimalPlugins` + `EdgesPlugin`, a `PlayerCamera` entity and `Toon(true)`. After `update()` the camera has `InkEdges`, `DepthPrepass` and `NormalPrepass`. Set `Toon(false)`, then `update()`, and all three are gone.
- [ ] Run (FAIL), implement, run (PASS), commit.

### Task 3: Setting and camera presets

**Files:** Modify `src/tuning.rs` (`graphics.toon`, default true), `tuning.toml`, `src/menu/mod.rs` (`Settings.toon`, a GRAPHICS row "COMIC SHADING", camera apply), `src/solar/mod.rs` and `src/look.rs` (bloom preset, no SSAO under toon), `src/main.rs` (`Toon` from tuning at startup).

**Interfaces:** Produces `pub(crate) fn bloom_for(toon: bool) -> Bloom` in `comic::toon` (intensity 0.05 when toon, else `Bloom::NATURAL`).

- [ ] Tests: `old_settings_without_toon_load_with_toon_on` (`toml::from_str::<Settings>("bloom = true")` gives `toon == true`); `toon_bloom_is_low` (`bloom_for(true).intensity == 0.05`, `bloom_for(false).intensity == Bloom::NATURAL.intensity`). `settings_round_trip_through_tuning_and_toml` must still pass.
- [ ] Run (FAIL), implement, run the full suite (PASS), commit.

### Task 4: Check it in the game

- [ ] Render the solar level (`RUST_REGIME_MENU=play`) with toon on and off. Check the bands, the dots, outlines on the ship, base and gun, and that the sky shows no ink flood. Tune the thresholds, then commit and push.
