# Comic-book redesign (2026-10-28)

Q's brief: redesign all of it (UI and world) with an overall comic-book feel, weapon customization
in the style of The Division and Delta Force. Q picked look A, "Ink & Halftone" (pulp comic), from
three mockups; the other screens were drawn in it. Mockups:
https://claude.ai/artifact/PBGpeLaUgoCGNBSYYWZdrD (images in the project files, `ui-redesign/`).

The work splits into four pieces. Each gets its own plan and PR, in this order: 1, then 3 and 4,
with 2 running alongside once 1 lands.

## Look A: tokens
- Ink `#111111`, paper `#F6EDD6`, red `#E23A2E`, yellow `#FFD23F`, blue `#2B5FAD`, navy `#14213D`,
  orange `#E07A3F`, green `#3FA34D`. Muted text on paper `#6B5E4A`.
- Display lettering: Bangers (OFL). Body and numbers: Barlow Condensed 600/800 (OFL). Both go in
  `assets/fonts/` and `CREDITS.md`. Fira Mono stays as the fallback.
- Ink weight: 4-7 px borders at 1080p, scaled with the UI scale. Hard offset shadows (4-7 px, ink),
  never blurred. Panels tilt -3..3 degrees. Halftone: dot grids, 9-13 px pitch.
- Selected rows are a yellow box with an ink border and an offset shadow, tilted -2 degrees, with
  a red triangle. Unselected rows are bare lettering. Tooltips are white speech bubbles.
- Button hints sit in a black strip along the bottom (pad glyph circles: A green, B red), with
  banked money at the right in yellow.

## 1. Comic kit (`src/comic/`)
- `ComicTheme` resource: the tokens above, the two font handles, ink weight and UI scale. Menus,
  HUD and waypoints read colours and sizes from it, not from their own constants (`menu.rs`
  AMBER/WHITE/DIM/PANEL, `hud.rs` plates).
- Widget spawners (plain functions returning bundles, as `menu::text`/`hud::plate` do now):
  `caption` (yellow box), `panel` (paper box with ink and shadow), `bubble` (speech bubble with a
  tail), `stat_bar` (ink fill plus a blue gain or red loss segment), `pip_row` (ammo dots),
  `segment_bar` (health), `hint_strip`, `sfx_pop` (a word like BLAM! that pops, tilts and fades).
- Halftone and tilt: Bevy UI has no rotation or pattern fills, so a small `UiMaterial`
  (`assets/shaders/comic_ui.wgsl`) draws a panel's fill, ink border, offset shadow and optional
  halftone in one quad, with rotation passed in as a uniform. Text sits on top, unrotated, unless
  it's an SFX pop (a `Transform` rotation on the text node).
- Tests: theme defaults load; every widget spawns under a test app without panicking.

## 2. World: per-material toon shading
- About 90 call sites create a plain `StandardMaterial`; three use `ExtendedMaterial`
  (`look.rs`: terrain, surface, water). Add `ToonExt` as a `MaterialExtension` on
  `StandardMaterial`: it keeps the base colour, textures and normal maps, but replaces the lit
  result with 3 light bands (lit, mid, shadow) plus a halftone dot screen in the shadow band, in
  screen space. Rim light stays as a thin paper-coloured edge.
- Terrain, surface and water shaders get the same banding through a shared WGSL include
  (`assets/shaders/toon.wgsl`), so they stay one material each.
- Outlines: inverted-hull for skinned and small meshes (characters, guns, FP arms, ships,
  vehicles, props), drawn as a second, front-culled mesh pushed out along normals in the vertex
  shader. Large static geometry (terrain, bases) gets a depth/normal edge pass (one post-process
  node using the depth and normal prepasses), so we don't double huge meshes.
- `Toon` graphics setting (on by default): off swaps every toon material back to its plain
  `StandardMaterial`, for the Arc A580 if it struggles. SSAO is off under toon; bloom drops to
  a low preset; the atmosphere stays.
- The conversion goes in groups, one PR each: (a) terrain, water and the planet surfaces;
  (b) bases, ships and vehicles; (c) characters, guns and FP arms; (d) effects (muzzle flash,
  hits, tracers drawn as flat ink shapes, `sfx_pop` on hits).
- One helper, `toon::material(base: StandardMaterial) -> Handle<ToonMaterial>`, replaces direct
  `materials.add(StandardMaterial { .. })` at each site, so the change at each call site is one line.

## 3. HUD, menus, flight HUD
- `menu.rs` (1,213 lines) splits into `src/menu/` with one file per panel (`main.rs`, `maps.rs`,
  `settings.rs`, `controls.rs`, `quartermaster.rs`, `wardrobe.rs`). The `Panel`/`Row`/`act` input
  path stays as it is; only the drawing moves onto the kit.
- Main and pause screens: the left paper panel slanted at its right edge, a tilted title with an
  issue caption, a speech-bubble tooltip for the selected row, and the hint strip. The live world
  shows on the right.
- HUD: a paper compass strip top centre with a red N; the objective as a yellow MEANWHILE...
  caption at the top left; a health card bottom left (character name, number and 10-segment bar,
  grapple bar under it); a black weapon card bottom right (name in yellow, mag count, reserve,
  pip row); a white crosshair with an ink outline; a red halftone vignette for damage; `sfx_pop`
  on hits and kills.
- Waypoints keep their faction colours, with an ink border and a black name/distance tag.
- Flight HUD (after PR #40 merges): the ship card (name, speed, boost bar), a roll gauge in the
  centre, and a yellow caption for warnings ("Too fast to bail out"). Markers as above.

## 4. Customization and space screens
- Quartermaster (Division/Delta Force): the gun turns in the centre on a paper ground; four slot
  callouts on ink leader lines (OPTIC, MUZZLE, GRIP, STOCK); the slot you're on is the yellow
  tilted one marked TRYING ON. Part cards along the bottom show price and effect text from
  `gunsmith::PARTS`. The weapon list is on the left with OWNED or price. The stat card on the
  right uses `stat_bar` with gain/loss segments against the bought setup. Buying and sanitising
  work as they do now (`quartermaster.rs`).
- Wardrobe: the character in the middle on a yellow halftone spotlight; slot tiles in two
  grids at left and right (the existing 14 slots); a bubble explaining the selected slot; presets
  and RANDOM! at the bottom right.
- New screens (each a `Panel`, opened from stations or the pause menu): system map (worlds,
  bases, your ship), ship status (hull, boost, tuning from the ship-tuning station) and a
  contract log (courier contracts). Each one is specced in its own plan once pieces 1 and 3 land.

## Out of scope
New gameplay, netcode, character model changes, changes to how input is mapped (the `controls.rs`
BINDINGS table stays the only source).

## Risks
- Toon shading across ~90 materials and four custom shaders is the biggest cost; the
  `toon::material` helper and the grouped PRs keep each step reviewable.
- Inverted-hull outlines double draw calls for outlined meshes; measure on lavapipe and keep the
  setting switch.
- Gamepad-only navigation has to work on every screen; keep `act()` as the single input path.
- Fonts and any new shader code must be commercial-OK and logged in `CREDITS.md`.
