# Comic Customization and Space Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Piece 4 of the comic redesign. The quartermaster becomes a Division/Delta Force gun bench, the wardrobe becomes a spotlight with slot grids on both sides, and the pause menu gains three space screens: STARMAP, SHIP and CONTRACTS.

**Architecture:** All of it is drawing in `src/menu/draw.rs` plus a new `src/menu/space.rs` for the three space screens. `rows()`, `act()`, `RowId`, `Arrow` and the cursor work as they do now. The new panels are ordinary `Panel`s with a BACK row, opened from the paused main list when the solar system is the running level. The space screens read live state (`Solar`, `Bases`, `Ships`, the ship entities, `Save`) through one `SystemParam`.

**Tech Stack:** Rust 2024, Bevy 0.19 UI, the `src/comic/` kit.

**Spec:** `docs/superpowers/specs/2026-10-28-comic-redesign-design.md`, section "4. Customization and space screens".

## Global Constraints

- Buying, sanitising, presets and randomise keep working as they do now (`quartermaster.rs`, `wardrobe.rs`); only drawing changes on those two panels.
- Every selectable row stays a `Button` with its `RowId`, so mouse and pad both work.
- Colours, fonts and tilts come from `ComicTheme`.
- The space rows only appear on the paused main list, and only on the solar level; the title screen list is unchanged.

## Rulings against the spec

- Ruling: there is no paper ground behind the gun. The gun is the 3D viewmodel, and a UI ground would cover it, so the room behind stays. Cost if wrong: the bench reads less like a comic page.
- Ruling: callouts sit at fixed screen spots around the gun (OPTIC above, MUZZLE left, GRIP below, STOCK right), with leader lines drawn toward the centre. They don't follow the 3D parts. Cost if wrong: a line can point a little off its part on long or short guns.
- Ruling: SHIP shows the ship, its engine tune level, heat and where it is parked. Boost and the flight tank wait for PR #40, like the flight HUD. Cost if wrong: one more line to add after #40 merges.
- Ruling: the screens are named STARMAP, SHIP and CONTRACTS, so each panel's name is its opener row (the existing opener test).

- Ruling (found in the render): no yellow halftone spotlight behind the character. UI always draws over the 3D scene, so the dots covered the body; the dressing room's own lighting stays. Cost if wrong: the wardrobe is less comic-page than the mockup.

## Review Focus

1. A gun with no attachment slots (rocket launcher) on the bench should show no callouts and no part cards, just the picker, stats and BACK. Owned by Task 1.
2. Opening STARMAP, SHIP or CONTRACTS on a level without `Solar` (island via env) should never offer the rows, and drawing them without the resources should not panic. Owned by Task 3.
3. STARMAP with worlds at very different distances (moons at a few hundred km, planets at tens of thousands) should keep every world on screen and apart. Owned by Task 3 (`map_radius`, a log scale).
4. No contract: CONTRACTS says where to get one, never an empty card. Owned by Task 3.
5. The wardrobe's 15 tiles split across two grids must keep cursor order, top to bottom and left grid first, so W/S still walks them in order. Owned by Task 2.

---

### Task 1: The gun bench

**Files:** Modify `src/menu/draw.rs`.

**Interfaces:** Produces `pub(super) const CALLOUTS: [(f32, f32); 4]`: each slot's callout centre as a fraction of the screen (x, y), in `SLOTS` order: OPTIC (0.50, 0.20), MUZZLE (0.20, 0.50), GRIP (0.50, 0.78), STOCK (0.80, 0.50).

- Layout: there is no slab on this panel. Top left: the title and BANKED subtitle as now. Left column (LEFT, top 150, 300 wide): the WEAPON picker row, then a list of every `WEAPONS` entry: the current one in a yellow box, each with OWNED or its price. Callouts: one `panel` per slot at `CALLOUTS[slot]`, paper (yellow and tilted -2° when it is the cursor's slot). Each callout holds the slot name, the part name, OWNED or the price, and a small "TRYING ON" red tag when the fitted part isn't owned. It is a `Button` + `RowId`, and its tune row, if any, sits inside it as a value row with its own `RowId`. A 3 px ink leader line runs from each callout toward the screen centre (a rotated `Node`). Part cards: along the bottom above the hint strip, the three parts of the slot under the cursor (or the last slot touched), with name, price or OWNED, and desc. The fitted one is yellow. The stat card stays at the right, moved to top 120.
- [ ] Test `callouts_stay_on_screen_and_apart`: every callout is in 0.1..=0.9 on both axes, and every pair is at least 0.2 apart.
- [ ] Run (FAIL), implement, run the full suite (PASS), commit.

### Task 2: The wardrobe spotlight

**Files:** Modify `src/menu/draw.rs`.

**Interfaces:** Produces `pub(super) fn wardrobe_columns(tiles: usize) -> (usize, usize)`: tiles in the left grid and the right grid, left first, left holding the extra one.

- Layout: there is no slab. The title is top left. A yellow halftone spotlight (an ellipse-ish `Node` with a big `border_radius`, holding a `halftone_layer`) sits behind the centre, behind the character. Left grid: the first `left` tiles, 2 columns of 140 px at LEFT. Right grid: the rest, 2 columns at right 72. Cursor indices keep row order. The bubble explaining the selected slot sits beside its tile, pointing at it (`Tail::Left` for the left grid; the right grid uses the same tail, with the bubble placed to its left). Bottom right above the hints: the RANDOMISE and BACK action rows.
- `pub(super) fn slot_blurb(row: Row) -> &'static str`: one line per wardrobe slot label and the preset.
- [ ] Tests: `wardrobe_columns_split_left_heavy` (`(15) -> (8, 7)`, `(14) -> (7, 7)`, `(0) -> (0, 0)`); `every_wardrobe_slot_has_a_blurb`.
- [ ] Run (FAIL), implement, run (PASS), commit.

### Task 3: Space screens

**Files:** Create `src/menu/space.rs`. Modify `src/menu/mod.rs` (`Panel::{Starmap, Ship, Contracts}`, `Action::{Starmap, Ship, Contracts}`, rows, `main_cursor` 5/6/7, `act`, hints, blurbs, the opener test list) and `src/menu/draw.rs` (call `space::draw` for the three panels).

**Interfaces:**
- `fn space_level() -> bool` in `mod.rs`: `MAPS[current_map()].level == "system"`.
- In `space.rs`: `#[derive(SystemParam)] pub(super) struct Space` with `solar: Option<Res<Solar>>`, `bases: Option<Res<Bases>>`, `ships: Option<Res<Ships>>`, `parked: Query<(&Ship, &GlobalTransform)>`. Also `pub(super) fn map_radius(distance_km: f64, nearest: f64, farthest: f64) -> f32`, a log scale from 60 px to 300 px (nearest maps to 60, farthest to 300), and `pub(super) fn draw(p, theme, panel, space: &Space, save: Option<&Save>)`.
- STARMAP: an ink-bordered paper disc (600 px) centred right of the title. The star is in the middle (yellow). Each world sits at `map_radius` along its angle around its parent (planets around the star; moons offset from their planet by a small fixed ring), as a dot with its name tag. Bases are coloured diamonds beside their world. YOU is a red tag on the anchor world.
- SHIP: a paper card per ship spec: name, ENGINE TUNE `segment_bar(level, 3, 3)`, HEAT as a `stat_bar`, PARKED ON the body under it, or FLYING.
- CONTRACTS: a yellow caption with the current contract ("DELIVER TO <base name> · PAYS ¢n"), or "No job. Contract desks at any base hand them out." Then a paper card: contracts done and banked.
- [ ] Tests: `space_rows_only_on_the_paused_solar_list` (`rows(Panel::Main, Screen::Paused, ..)` holds STARMAP/SHIP/CONTRACTS at selectable 5/6/7 when `space_level()`; Title never). `map_radius_is_monotonic_and_bounded` (`map_radius(n, n, f) == 60`, `map_radius(f, n, f) == 300`, increasing between). Extend the opener test's panel list with the three panels (it gets skipped off the solar level). Add `space_screens_draw_without_solar` (an app with `MenuPlugin`, opening each panel, `update()` doesn't panic).
- [ ] Run (FAIL), implement, run the full suite (PASS), commit.

### Task 4: Check it in the game

- [ ] Render `RUST_REGIME_MENU=quartermaster`, `wardrobe`, and add `starmap|ship|contracts` to the env list. Check the layouts by eye, fix any overlaps, commit, push.
