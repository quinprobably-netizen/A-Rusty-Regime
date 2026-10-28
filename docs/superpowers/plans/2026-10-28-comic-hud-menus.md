# Comic HUD and Menus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Piece 3 of the comic redesign: move the HUD, the front-end menus and the waypoint markers onto the comic kit (look A).

**Architecture:** `hud.rs` and the drawing half of `menu.rs` swap their own colour constants and `text()` helpers for `ComicTheme` and the kit's spawners. The update systems keep their queries and only change what they colour. `ComicTheme` builds itself through `FromWorld`, so any plugin can `init_resource` it and get the fonts without depending on `ComicPlugin`'s ordering. That matters for the headless tests, which add `HudPlugin` or `MenuPlugin` on their own.

**Tech Stack:** Rust 2024, Bevy 0.19 UI, the `src/comic/` kit.

**Spec:** `docs/superpowers/specs/2026-10-28-comic-redesign-design.md`, section "3. HUD, menus, flight HUD".

## Global Constraints

- Colours, fonts, ink widths and tilts all come from `ComicTheme`; no new colour constants in `hud.rs` or `menu.rs`, except faction colours from `bases.toml`.
- Input and navigation stay as they are: `act()`, `RowId`, `Arrow`, `Button` hover and click all keep working. Every row stays a `Button` with its `RowId`.
- Gamepad-only play must keep working on every screen.
- The flight HUD waits for PR #40 to merge (spec); this plan doesn't touch `ship.rs`.
- All existing tests stay green (`cargo test --release`).

## Review Focus

1. A headless test app adds `HudPlugin` or `MenuPlugin` without `ComicPlugin`. The expected result is no panic over a missing `ComicTheme`. Owned by Task 1.
2. Weapons with no magazine (knife, fist) or a reload in progress should show no pips and RELOADING, never an empty card. Owned by Task 2.
3. A burst of hits in one frame should give one pop per frame at most, so the screen never fills with stacked words. Owned by Task 2.
4. The objective goes empty (no mission, no match) and the caption should hide, never leave an empty yellow box. Owned by Task 2.
5. A long menu (Settings has ~20 rows) on the tilted paper panel should keep the list clipped inside the panel and every row clickable. Owned by Task 3.

---

### Task 1: `ComicTheme` from the world

**Files:** Modify `src/comic/theme.rs` and `src/comic/mod.rs`; `src/hud.rs` and `src/menu.rs` (`init_resource::<ComicTheme>()` in each plugin's `build`).

**Interfaces:** Produces `impl FromWorld for ComicTheme`. It is `Default` plus fonts through `font_or_default` when an `AssetServer` exists. The `load_fonts` Startup system is removed.

- [ ] Test `theme_from_world_without_asset_server`: `World::new().init_resource::<ComicTheme>()` gives default handles and doesn't panic.
- [ ] Run it and expect a FAIL (no `FromWorld` impl beyond `Default`, so this compiles but the next test fails). Test `hud_without_comic_plugin_spawns`: an app with `MinimalPlugins` + `AssetPlugin` + `HudPlugin` and the resources HUD systems read (copy `tests.rs` line ~311's setup); one `update()`; expect no panic.
- [ ] Implement, run both tests (PASS), commit.

### Task 2: HUD on the kit

**Files:** Modify `src/hud.rs`; `assets/shaders/halftone.wgsl` + `src/comic/halftone.rs` (vignette).

**Interfaces:**
- Consumes: `ComicTheme`, `display_text`, `body_text`, `panel`, `pip_row`-style pips, `segment_bar` logic (`widgets::filled_segments`, `widgets::pips`), `sfx_pop`, `Halftone`.
- Produces in `hud.rs`: `pub(crate) fn pop_word(hits: u32, kills: u32, prev: (u32, u32)) -> Option<&'static str>` returns "KO!" when kills went up, "HIT!" when only hits went up, and None otherwise. `Halftone.params.w` is the vignette: 0 for a full fill, and 1 for dots only towards the edges (`cover *= smoothstep(0.55, 0.85, length(uv - 0.5) * 2.0)` when w > 0).
- Layout:
  - Compass: a paper strip with an ink border and hard shadow, red N, ink ticks, ink notch.
  - Objective: a `caption` at the top left, hidden while the text is empty.
  - Score and haul: paper body text with ink `TextShadow`, top right.
  - Health: a paper `panel` tilted -1.5° at the bottom left, holding a tag (HP / BLEEDING / CRITICAL / RESPAWNING), a big red display number, and 10 `HealthSeg(i)` segments recoloured by `filled_segments`.
  - Movement: a small paper panel at the bottom centre, as now.
  - Weapon: an ink `panel` tilted 1.5° at the bottom right, holding the yellow display name, a big count `/ mag`, a row of up to 30 `AmmoPip(i)` dots recoloured by `pips` (hidden past `mag`), parts text, and the heat bar.
  - Crosshair: white lines with a 2 px ink `Outline`.
  - Hit flash: a full-screen `Halftone` with w = 1, red dots, alpha = the current flash level.
  - Pops: `sfx_pop` at screen centre + (60, -80), tilt ±12°, alternating.
- [ ] Tests: `pop_word_prefers_kills` (`pop_word(5, 1, (4, 0)) == Some("KO!")`, `pop_word(5, 0, (4, 0)) == Some("HIT!")`, `pop_word(4, 0, (4, 0)) == None`). Extend `hud_without_comic_plugin_spawns` to assert there are 30 `AmmoPip` and 10 `HealthSeg` entities.
- [ ] Run them (FAIL), implement, run them and the full suite (PASS), commit.

### Task 3: Menus on the kit

**Files:** `git mv src/menu.rs src/menu/mod.rs`; create `src/menu/draw.rs` holding everything from the `// --- ui` divider down (`rebuild`, `action_row`, `value_row`, `arrow`, `tile`), restyled.

**Interfaces:**
- Produces in `draw.rs`: `pub(super) fn blurb(action: Action) -> &'static str`, one line per main-menu action, shown in a `bubble` beside the selected row. `pub(super) fn pad_glyph(key: &str) -> &'static str` maps the hint keys: "ENTER / A" to "A", "ESC / B" to "B", "Q E / LB RB" to "LB RB", "W S" to "UP DN", and "A D" to "L R".
- Layout:
  - The left paper panel is 560 px wide and taller than the screen, tilted 3° so its right edge slants. It has a red halftone layer and ink right border.
  - The header is a display-font title in red with an ink `TextShadow`, tilted -3°, plus a yellow `caption` subtitle.
  - The selected action row is a yellow box with an ink border and hard shadow, tilted -2°, with a red diamond. Other rows are bare ink display text.
  - Value rows use body text. The selected row gets a yellow fill and ink border, and arrows become ink boxes.
  - Sections are red display text. The quartermaster stat card is a paper `panel` of `stat_bar(base, fitted)`. Wardrobe tiles are paper boxes with an ink border; the selected tile is yellow and tilted -2°.
  - The bottom uses `hint_strip` with `pad_glyph`, plus money (`save.banked`) on Main and Quartermaster.
- [ ] Tests: `every_main_action_has_a_blurb` (non-empty for each `Action` reachable from `rows(Panel::Main, ..)`), and `hint_keys_map_to_glyphs` (each key in the hint table maps to a non-empty glyph different from the key text). The existing `every_panel_has_rows_and_back_lands_on_its_opener` must still pass.
- [ ] Run (FAIL), implement, run the full suite (PASS), commit.

### Task 4: Waypoints in ink

**Files:** Modify `src/solar/waypoint.rs` (spawn only).

- [ ] Each diamond keeps its faction colour but gets a 3 px ink border. Each label becomes a black tag with paper ExtraBold text and 4 px padding. No logic change; `project` tests stay green.
- [ ] Run the full suite, then render the game once (solar level, `RUST_REGIME_MENU=title`, then `play`) to check the HUD, menus and markers by eye; commit.
