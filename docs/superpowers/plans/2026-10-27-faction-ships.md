# Faction Ships Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four generated faction spaceships, each boardable on Haven's apron with its own handling, replacing the primitive ship.

**Architecture:** `tools/ships` builds one glb per ship with headless Blender on top of the weapons kit. `assets/ships.toml` holds every number the game and the tests need (handling, collider, seat, exit); `src/solar/ship.rs` becomes spec-driven, loads the glb under the eased `Hull` child and finds exhaust and heat nodes by name. The pad grows into an apron that parks all four.

**Tech Stack:** Rust 2024, Bevy 0.19, Avian3d 0.7, serde + toml 0.9; Python 3.11 `bpy` wheel (Blender), reused from `tools/weapons/kit.py`.

**Spec:** `docs/superpowers/specs/2026-10-27-faction-ships-design.md`

## Global Constraints

- No third-party assets; `CREDITS.md` unchanged.
- Each ship: under 12 000 triangles, one 1024² baked colour texture (JPEG in the glb), at most four meshes (`hull`, `glass`, `lights`, plus nothing else).
- Ship frame in the game: +X right, +Y up, −Z nose. In Blender: +X right, +Y nose, +Z up (the glTF exporter maps Blender (x, y, z) to game (x, z, −y)).
- Blender wear bake must stay CPU-only and under ~2 minutes per ship on 4 cores (samples 12, 1024²).
- All headless tests (`cargo test --release`) keep passing; no test is skipped or loosened.
- The Kestrel inherits the current ship's exact numbers: mass 6000, thrust 30, lift 20, rates 1.6/1.1/2.2, cruise 160, boost 6000, rest 1.45, seat (0, 0.4, −2), exit (−4.5, −0.4, 0), cam (20, 5), parked at pad + (−1, deck + rest + 0.05, −2).

## Review Focus

1. A glb that fails to load (missing file, bad path) must leave an invisible but still flyable ship, never a panic: Task 6's `a_ship_without_assets_still_flies` test.
2. Leaving a ship whose `exit` point would be inside a neighbour's collider: Task 7's row spacing test checks every exit point is at least 2 m outside every other ship's boxes.
3. Two ships touching while parked would jitter forever: Task 7's disjoint-colliders test.
4. The respawn point must follow the ship the player last flew, not whichever ship iterates last: Task 7's `respawn_follows_the_last_flown_ship` test.
5. `RUST_REGIME_AT` and the test helpers call `.single()` on ships; with four ships that panics: Task 6 switches both to the Kestrel (spec index 0).

---

### Task 1: Ship kit, build script and the Kestrel

**Files:**
- Create: `tools/ships/kit.py`, `tools/ships/build.py`, `tools/ships/build.sh`, `tools/ships/ships/__init__.py`, `tools/ships/ships/kestrel.py`
- Output: `assets/models/ships/kestrel.glb`, `screenshots/ships/kestrel.png`

**Interfaces:**
- Consumes from `tools/weapons/kit.py` (import as `wk` after `sys.path.insert(0, <tools/weapons>)`): `block, prism, plan, cyl, tube, ring, cut, unite, join, label, screw, apply_modifiers, bake_wear, read_glb, PALETTE, _current, TEX`.
- Produces in `tools/ships/kit.py`:
  - `class Ship(sid)`: `add(obj, group="hull")` (groups `hull`, `glass`, `lights`), `node(name, at)` (an empty at Blender coords, exported as a glTF node of that name), `finish(out_dir, bake=True) -> str` (joins each group into one mesh named after it, `wk.TEX = 1024`, `wk.bake_wear(self, objs, scale=40.0)`, exports GLB with `export_animations=False, export_yup=True`, prints tris and size).
  - `plate(name, c, s, material, lines=(), bevel=0.02)`: a `block` with 3 cm panel-line grooves cut at each `(axis, offset)` in `lines`.
  - `rivets(name, p0, p1, n, r=0.03, material="steel")`: `n` hemispheres along p0→p1, joined.
  - `stripe(name, c, s, material)`: a block 5 mm proud of the surface.
  - `bell(name, p0, p1, r_mouth, r_throat, material="steel")`: nozzle, a `tube` flared from throat (p0) to mouth (p1).
  - `skid(name, c, length, material="black")`: a bar under two 0.6 m struts, joined.
  - `preview(path, cam, look, lens=35, res=(960, 600))`: `wk.preview` with the grey world replaced by a dark navy sky `(0.05, 0.07, 0.1)` and the key light at energy 4.
  - `check(path, spec) -> (problems: list[str], stats: dict)`: reads the glb with `wk.read_glb`; problems when tris ≥ 12000, any `spec["size"]` axis differs from the bounding box by more than 10 %, a `spec["nodes"]` name is missing, meshes > 4, or the lowest vertex differs from `-spec["rest"]` by more than 5 cm.
  - Palette additions (`wk.PALETTE.update`): `slate (0.20,0.22,0.25)`, `bone (0.86,0.84,0.78)`, `gold (0.79,0.64,0.15, metallic 1)`, `leather (0.30,0.18,0.10)`, `gunmetal (0.16,0.17,0.19, metallic 0.6)`, `blue_light (0.3,0.6,1.0, emission 6)`, `deserter_dark #141413`, `deserter_pale #F0EEE6`, `deserter_orange #D97757`, `deserter_tan #D4A27F`, each with a worn colour a little lighter and wear 0.5.
- `tools/ships/ships/<id>.py` exports `SPEC = {"build": build, "size": (length, span, height), "rest": f, "nodes": [...], "view": {"cam": (x,y,z), "look": (x,y,z)}}`; `build() -> Ship`.
- `build.sh [ids] [--check] [--preview] [--no-bake]`, same venv recipe as `tools/weapons/build.sh`; `build.py` mirrors `tools/weapons/build.py` with `ORDER = ["kestrel", "litany", "mule", "vantage"]`, `OUT = assets/models/ships`, `SHOTS = screenshots/ships`.

- [ ] **Step 1: Write `kit.py`, `build.py`, `build.sh` and an empty `ships/__init__.py`** as specified above.
- [ ] **Step 2: Write `ships/kestrel.py`**: `SPEC["size"] = (14.0, 11.0, 4.5)`, `rest = 1.45`, nodes `exhaust.0`, `exhaust.1` at Blender (∓1.6, −5.4, −0.1), `heat` at (0, 5.5, 0). Slab fuselage 2.4 wide × 9 long × 1.6 tall centred (0, −0.5, 0) in `deserter_dark` with `deserter_pale` plates on the flanks and panel lines; chin cockpit glass (group `glass`) at (0, 2.0, 0.85); stub wings 9 m span, `deserter_orange` stripe on each tip; twin pod engines (`cyl` + `bell`) at x = ±1.6 behind the wings; tail fin raked back; four `skid`s with the bar bottom at z = −1.45; `deserter_tan` canvas roll and strap blocks on the roof; two `rivets` rows along each flank; `label("DSR-07", …)` on the left flank.
- [ ] **Step 3: Build and check**

Run: `tools/ships/build.sh kestrel --no-bake && tools/ships/build.sh --check kestrel`
Expected: `wrote .../kestrel.glb` and `kestrel: ok {...}` with tris < 12000.

- [ ] **Step 4: Bake and preview**

Run: `tools/ships/build.sh kestrel --preview`
Expected: `assets/models/ships/kestrel.glb` under 1.5 MB, `screenshots/ships/kestrel.png` written. Look at it; fix proportions until it reads as a gunship.

- [ ] **Step 5: Commit** `tools/ships`, `assets/models/ships/kestrel.glb`, `screenshots/ships/kestrel.png`: "Ships: build kit and the Deserters' Kestrel".

### Task 2: Litany (Regime)

**Files:** Create `tools/ships/ships/litany.py`; output `assets/models/ships/litany.glb`, `screenshots/ships/litany.png`.

**Interfaces:** Consumes Task 1's kit. `SPEC["size"] = (22.0, 9.0, 9.0)`, `rest = 2.2`, nodes `exhaust.0..2` in a trefoil at the tail (Blender (0, −10.5, 1.2), (±1.9, −10.5, −0.6)), `heat` at (0, 10.0, 0).

- [ ] **Step 1: Write `litany.py`**: long narrow hull 3 × 18 m in `slate` with `bone` plating, prow blade (`prism`), dorsal spire fin rising to z = 6.8 with `gold` edge stripes, two slit-window galleries (`glass` cut strips along each flank), three `bell` engines in the trefoil, gold `rivets` rows and a `label("LITANY")` on the fin, three `skid`s (two forward, one aft) with bar bottom at z = −2.2.
- [ ] **Step 2: Build, check, preview** — `tools/ships/build.sh litany --no-bake && tools/ships/build.sh --check litany && tools/ships/build.sh litany --preview`; expected `litany: ok`, tris < 12000.
- [ ] **Step 3: Commit** "Ships: the Regime's Litany".

### Task 3: Mule (Scrappers)

**Files:** Create `tools/ships/ships/mule.py`; output `assets/models/ships/mule.glb`, `screenshots/ships/mule.png`.

**Interfaces:** `SPEC["size"] = (16.0, 13.0, 6.0)`, `rest = 1.9`, nodes `exhaust.0` (big) at Blender (2.6, −7.5, 0.0), `exhaust.1` (small) at (−2.4, −7.0, −0.3), `heat` at (0, 7.5, 0).

- [ ] **Step 1: Write `mule.py`**: box hull 6 × 11 × 3.6 m in `rust` with `brass` and `copper` plates, the right flank 1.5 m longer than the left; big engine (r 1.2) right, small (r 0.7) left; three external `tube` tanks on the left flank with `copper` pipe runs (`cyl` chains); crane arm folded over the roof (`block` segments + `cyl` pivot); `hazard` stripes on the bay door; `leather`/`deserter_tan` canvas over the cargo bay (a `block` with `taper`); four `skid`s, bar bottom at z = −1.9; `label("MULE")` painted crooked (`rot`) on the right.
- [ ] **Step 2: Build, check, preview** — same commands with `mule`; expected `mule: ok`, tris < 12000.
- [ ] **Step 3: Commit** "Ships: the Scrappers' Mule".

### Task 4: Vantage (PMC)

**Files:** Create `tools/ships/ships/vantage.py`; output `assets/models/ships/vantage.glb`, `screenshots/ships/vantage.png`.

**Interfaces:** `SPEC["size"] = (12.0, 10.0, 3.5)`, `rest = 1.1`, nodes `exhaust.0`, `exhaust.1` at Blender (±1.2, −5.5, 0.0) (flat slots: scale the glow disc in-game is fine), `heat` at (0, 5.5, 0), `light.0..3` at wingtips and tail.

- [ ] **Step 1: Write `vantage.py`**: faceted hull from `plan` outlines (a diamond top-down, chamfered by `taper`) in `gunmetal` with `bone`-white upper plates; flush canopy (`glass` `prism`); swept wings from `plan`; two flat slot engines (`block` with `taper` plus a `tube` liner); `blue_light` running lights (group `lights`) as small `cyl` discs at each `light.n`; `label("VANTAGE SEC")` stencil on the wing; three `skid`s, bar bottom at z = −1.1.
- [ ] **Step 2: Build, check, preview** — same commands with `vantage`; expected `vantage: ok`, tris < 12000.
- [ ] **Step 3: Full check and commit** — `tools/ships/build.sh --check` prints `ok` for all four. Commit "Ships: the PMC's Vantage".

### Task 5: `assets/ships.toml` and `ShipSpec`

**Files:**
- Create: `assets/ships.toml`
- Modify: `src/solar/ship.rs` (add the spec types at the top; nothing else yet)
- Test: `src/tests.rs` (near the other ship tests, after `fn inertial`)

**Interfaces:**
- Produces in `src/solar/ship.rs`:
  ```rust
  #[derive(Deserialize, Clone, Debug)] pub struct ShipBox { pub center: [f32; 3], pub size: [f32; 3] }
  #[derive(Deserialize, Clone, Debug)] pub struct ShipSpec { pub id: String, pub name: String, pub faction: String, pub mass: f32, pub thrust: f32, pub lift: f32, pub rates: [f32; 3], pub cruise: f32, pub boost_max: f32, pub rest: f32, pub seat: [f32; 3], pub exit: [f32; 3], pub cam: [f32; 2], pub collider: Vec<ShipBox> }
  #[derive(Resource, Deserialize, Clone, Debug)] pub struct Ships { pub ship: Vec<ShipSpec> }
  impl Ships { pub fn parse(text: &str) -> Result<Self, toml::de::Error>; pub fn load() -> Self /* include_str!("../../assets/ships.toml") */; pub fn index(&self, id: &str) -> Option<usize> }
  impl ShipSpec { pub fn speed_cap(&self, clearance: f32, boost: bool) -> f32; pub fn collider(&self) -> Collider; pub fn bottom(&self) -> f32 /* lowest collider face, negative */ }
  ```
- `speed_cap` keeps the current formula with `self.cruise` and `self.boost_max`; `ASSIST_HEIGHT` stays a module constant.

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn ships_toml_lists_four_ships_with_models_and_matching_rest_heights() {
    let ships = solar::ship::Ships::load();
    assert_eq!(ships.ship.iter().map(|s| s.id.as_str()).collect::<Vec<_>>(), ["kestrel", "litany", "mule", "vantage"]);
    for s in &ships.ship {
        assert!(std::path::Path::new(&format!("assets/models/ships/{}.glb", s.id)).exists(), "{} has a model", s.id);
        assert!((s.bottom() + s.rest).abs() < 0.05, "{}: collider bottom {} vs rest {}", s.id, s.bottom(), s.rest);
        assert!(s.mass > 0.0 && s.thrust > 0.0 && s.lift > 0.0 && s.cruise > 0.0 && s.boost_max > s.cruise);
    }
    let k = &ships.ship[0];
    assert_eq!((k.mass, k.thrust, k.lift, k.cruise, k.boost_max, k.rest), (6000.0, 30.0, 20.0, 160.0, 6000.0, 1.45));
}

#[test]
fn each_ship_caps_speed_by_its_own_numbers() {
    let ships = solar::ship::Ships::load();
    let (k, v) = (&ships.ship[0], &ships.ship[3]);
    assert_eq!(k.speed_cap(100.0, false), 160.0);
    assert_eq!(v.speed_cap(100.0, false), 190.0);
    assert_eq!(k.speed_cap(1.0e9, true), 6000.0);
    assert_eq!(v.speed_cap(1.0e9, true), 6500.0);
    assert_eq!(k.speed_cap(1.0e5, false), f32::INFINITY);
}
```

- [ ] **Step 2: Run** `cargo test --release ships_toml each_ship_caps` — expected: compile error, `Ships` not found.
- [ ] **Step 3: Write `assets/ships.toml`** with `[[ship]]` tables in the order kestrel, litany, mule, vantage using the spec's handling table; colliders: Kestrel = today's three boxes; Litany `{center [0,0,0], size [3,3.2,18]}`, `{center [0,3.5,2], size [0.6,6.6,8]}`, `{center [0,-1.6,-2], size [5,1.2,10]}`; Mule `{center [0,0.3,0], size [6,3.6,11]}`, `{center [3.0,0.4,2], size [3,2.6,6]}`, `{center [0,-1.3,0], size [4,1.2,9]}`; Vantage `{center [0,0,0], size [2.6,1.4,10]}`, `{center [0,-0.2,1], size [10,0.3,3]}`, `{center [0,-0.95,0], size [3,0.3,6]}`. Seats: Litany (0, 1.0, −6), Mule (0, 1.2, −3.5), Vantage (0, 0.5, −1.5); exits: Litany (−3.5, −1.0, 0), Mule (−5.0, −0.8, 0), Vantage (−3.5, −0.3, 0); cams: Litany (30, 8), Mule (24, 7), Vantage (18, 4). Adjust each `rest` so `bottom()` matches (Litany 2.2, Mule 1.9, Vantage 1.1).
- [ ] **Step 4: Add the types and impls to `ship.rs`**; `Ships::load()` panics with the toml error if the file is malformed (it is compiled in).
- [ ] **Step 5: Run** the two tests — expected PASS.
- [ ] **Step 6: Commit** "Ships: per-ship spec in assets/ships.toml".

### Task 6: Spec-driven ship with a glb hull

**Files:**
- Modify: `src/solar/ship.rs` (whole module), `src/solar/mod.rs:522-562` (`RUST_REGIME_AT` picks the Kestrel), `src/tests.rs:2406-2436` (helpers pick the Kestrel)
- Test: `src/tests.rs`

**Interfaces:**
- `Ship { pub pilot: Option<Entity>, pub heat: f32, pub burn: f32, pub spec: usize, pub landed_at: f64, before: (Vec3, Quat) }`.
- `pub fn spawn(world: &mut World, spec: usize, transform: Transform) -> Entity`: reads `Ships` from the world; collider = `spec.collider()`, `Mass(spec.mass)`, `ChaseCam { dist: cam[0], height: cam[1] }`, a `Hull { spec }` child with `Transform::default()`; when `AssetServer` and `Assets<StandardMaterial>` exist, adds `ShipLook { exhaust, heat }` as a **component** on the ship (its own emissive materials) and marks the hull `Pending` for streaming.
- `fn stream(server, hulls: Query<(Entity, &Hull), (With<Pending>, Without<WorldAssetRoot>)>, loading: Query<(), (With<Pending>, With<WorldAssetRoot>)>, commands)`: when nothing is loading, inserts `WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(format!("models/ships/{id}.glb"))))` on one hull; ships load one at a time.
- `fn dress(ready: On<WorldInstanceReady>, ...)`: removes `Pending` from `ready.entity`; walks its descendants (`Query<&Children>`, `Query<&Name>`): a name starting `exhaust.` gets `Exhaust` and `MeshMaterial3d(look.exhaust)`, a name `heat` gets `HeatGlow`, `NotShadowCaster` and `MeshMaterial3d(look.heat)`; anything else keeps the glb material. Node names arrive as `Name` on the empty; put the glow disc mesh on the empty itself: an `exhaust.n` node gets `Mesh3d(disc)` where `disc` is a shared `Cylinder::new(0.5, 0.1)` rotated to face +Z, scaled by the spec's engine radius (default 1.0); `heat` gets `Mesh3d(Sphere::new(1.0))` scaled (2, 1.6, 4). Keep `ShipMeshes { disc, nose }` as a resource made in `build`.
- `fly`, `board`, `seat`, `park` read `Ships` and the ship's spec: `THRUST → spec.thrust`, `LIFT → spec.lift`, `RATES → Vec3::from(spec.rates)`, `SEAT → Vec3::from(spec.seat)`, exit offset `→ Vec3::from(spec.exit)`, `speed_cap → spec.speed_cap`. Delete the module constants `MASS, SEAT, THRUST, LIFT, RATES, CRUISE, BOOST_MAX, REST_HEIGHT`; keep `BOARD_RADIUS`, `LEAVE_SPEED`, `MOUSE_FULL`, `ASSIST_HEIGHT`, `DRAG`, `HOT`, `CAP_BRAKE`, `PULL_OUT`.
- `board` on leaving sets `ship.landed_at = time.elapsed_secs_f64()`.
- `park` picks, among parked ships (`pilot.is_none()` and speed < 0.5), the one with the greatest `landed_at`; only that ship moves `bounds.spawn`.
- `glow(ships: Query<(&Ship, &ShipLook)>, ...)` updates each ship's own materials; `HeatGlow` visibility per ship via `Query<(&ChildOf, &mut Visibility), With<HeatGlow>>` walking up to the ship (two parents: node → hull → ship).
- `spawn_home_ship` keeps its name for now and spawns spec 0 at the same transform (Task 7 replaces it).
- Test helper `ship_entity(app)` returns the ship whose `spec == 0`; `put_ship`, `board`, `ship_state` unchanged otherwise. `RUST_REGIME_AT` in `solar/mod.rs` uses the same selection.

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn a_ship_without_assets_still_flies() {
    // Headless apps have no AssetServer or meshes: the Kestrel must still board and move.
    let mut app = system_app();
    board(&mut app);
    let (p0, _) = ship_state(&mut app);
    app.world_mut().resource_mut::<ShipControls>().thrust = 1.0;
    run(&mut app, 2.0);
    let (p1, _) = ship_state(&mut app);
    assert!(p0.distance(p1) > 20.0, "moved {} m", p0.distance(p1));
    let ship = ship_entity(&mut app);
    assert_eq!(app.world().get::<Ship>(ship).unwrap().spec, 0);
    assert_eq!(app.world().get::<Mass>(ship).unwrap().0, 6000.0);
}

#[test]
fn leaving_the_ship_uses_its_exit_point() {
    let mut app = system_app();
    board(&mut app);
    run(&mut app, 0.5);
    let ship = ship_entity(&mut app);
    let tf = *app.world().get::<Transform>(ship).unwrap();
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    let player = app.world_mut().query_filtered::<&Transform, With<Player>>().single(app.world()).unwrap().translation;
    let expect = tf.translation + tf.rotation * Vec3::new(-4.5, -0.4, 0.0);
    assert!(player.distance(expect) < 1.5, "stepped out {} m from the exit", player.distance(expect));
}
```

- [ ] **Step 2: Run** `cargo test --release a_ship_without_assets leaving_the_ship_uses` — expected: compile error (`spec` field missing).
- [ ] **Step 3: Rewrite `ship.rs`** per the Interfaces block. Remove the primitive hull parts entirely.
- [ ] **Step 4: Update `src/solar/mod.rs` `RUST_REGIME_AT`** to pick the ship with `spec == 0`, and the test helper `ship_entity`.
- [ ] **Step 5: Run** `cargo test --release` — expected: all pass, including the pre-existing ship tests.
- [ ] **Step 6: Commit** "Ships: spec-driven flight and glb hulls".

### Task 7: The fleet on the apron

**Files:**
- Modify: `src/solar/ship.rs` (`spawn_home_ship` → `spawn_fleet`), `src/solar/mod.rs:198-216` (apron), `src/solar/mod.rs:606-612` (HUD board line)
- Test: `src/tests.rs`

**Interfaces:**
- `fn spawn_fleet(world: &mut World)`: for `(i, x)` in `[-1.0, -19.0, -37.0, -55.0]`, spawn spec `i` at `pad + frame * Vec3::new(x, COURSE_DECK + spec.rest + 0.05, -2.0)`, rotation `frame`.
- Apron: `size = Vec3::new(80.0, 14.0, 26.0)` centred at `pad + frame * Vec3::new(-27.0, COURSE_DECK - size.y / 2.0, 0.0)`.
- HUD: `"[E] board {name}"` for the nearest ship within `BOARD_RADIUS`, name from `Ships`.
- `pub fn ship_boxes(spec: &ShipSpec, tf: &Transform) -> Vec<(Vec3, Vec3)>` is **not** added; the test computes box separation from the toml and the parked x offsets directly.

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn four_ships_rest_in_a_row_on_the_apron_without_touching() {
    let mut app = system_app();
    run(&mut app, 1.0);
    let ships = app.world().resource::<solar::ship::Ships>().clone();
    let mut parked: Vec<(usize, Vec3)> = app.world_mut().query::<(&Ship, &Transform)>().iter(app.world()).map(|(s, tf)| (s.spec, tf.translation)).collect();
    parked.sort_by_key(|p| p.0);
    assert_eq!(parked.len(), 4);
    let origin = *app.world().resource::<Origin>();
    let solar_res = app.world().resource::<Solar>();
    let (pad, frame) = (solar_res.pad, app.world().resource::<Surface>().frame(solar_res.pad));
    for (spec, at) in &parked {
        let local = frame.inverse() * (origin.body(*at) - pad);
        let rest = crate::planet::COURSE_DECK + ships.ship[*spec].rest;
        assert!((local.y - rest).abs() < 2.0, "{} rests at {} (want {})", ships.ship[*spec].id, local.y, rest);
    }
    // Boxes along the row never overlap: every neighbour gap is positive, and no exit point lands in a neighbour.
    for a in 0..4 {
        for b in 0..4 {
            if a == b { continue; }
            let (sa, sb) = (&ships.ship[a], &ships.ship[b]);
            let dx = (parked[a].1 - parked[b].1).length();
            let half = |s: &solar::ship::ShipSpec| s.collider.iter().map(|c| c.center[0].abs() + c.size[0] / 2.0).fold(0.0, f32::max);
            assert!(dx > half(sa) + half(sb), "{} and {} touch", sa.id, sb.id);
            let exit = Vec3::from(sa.exit).x;
            assert!((dx - exit.abs()).abs() > half(sb) + 2.0 || exit.signum() != (parked[b].1 - parked[a].1).x.signum(), "{}'s exit is beside {}", sa.id, sb.id);
        }
    }
}

#[test]
fn respawn_follows_the_last_flown_ship() {
    let mut app = system_app();
    // Walk to the Litany (spec 1), board it, hop 30 m north, land and leave.
    let litany = app.world_mut().query::<(Entity, &Ship, &Transform)>().iter(app.world()).find(|(_, s, _)| s.spec == 1).map(|(e, _, tf)| (e, *tf)).unwrap();
    let player = app.world_mut().query_filtered::<Entity, With<Player>>().single(app.world()).unwrap();
    let near = litany.1.translation + litany.1.rotation * Vec3::new(-4.0, 0.0, 0.0);
    app.world_mut().entity_mut(player).insert(Transform::from_translation(near));
    input(&mut app).interact_pressed = true;
    run(&mut app, 0.1);
    assert_eq!(app.world().get::<Driving>(player).map(|d| d.0), Some(litany.0));
    input(&mut app).interact_pressed = true;
    run(&mut app, 1.0);
    let spawn = app.world().resource::<WorldBounds>().spawn;
    let origin = *app.world().resource::<Origin>();
    let expect = origin.body(litany.1.translation + litany.1.rotation * Vec3::from(app.world().resource::<solar::ship::Ships>().ship[1].exit));
    assert!(spawn.distance(expect) < 3.0, "respawn {} m from the Litany's door", spawn.distance(expect));
}
```

- [ ] **Step 2: Run** `cargo test --release four_ships_rest respawn_follows` — expected FAIL (one ship, respawn beside the Kestrel).
- [ ] **Step 3: Implement** `spawn_fleet`, the apron, and the HUD name. Register `spawn_fleet` where `spawn_home_ship` was.
- [ ] **Step 4: Run** `cargo test --release` — expected: all pass (`the_system_starts_on_havens_pad_beside_the_ship` still finds the Kestrel in reach).
- [ ] **Step 5: Commit** "Ships: four faction ships parked on Haven's apron".

### Task 8: Screenshots, README and PR

**Files:**
- Modify: `README.md` (the solar system paragraph: name the four ships and their handling in two sentences; mention `tools/ships/build.sh`).
- Output: `screenshots/ships/apron.png` (one in-game shot of the row).

- [ ] **Step 1: Build the release binary and take one in-game shot** of the apron from the east looking west over the player's spawn: `xvfb-run -a env BEVY_ASSET_ROOT=$PWD RUST_REGIME_SCREENSHOT=screenshots/ships/apron.png RUST_REGIME_SCREENSHOT_VIEW="slot,yaw,x,z,pitch" WGPU_BACKEND=vulkan VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json target/release/rust-regime` (yaw 90 looks toward −X, pitch −10). Expected: a PNG with four ships visible and no missing-hull gaps.
- [ ] **Step 2: Run** `cargo test --release` and `cargo clippy --release -- -D warnings` — expected: pass, no warnings.
- [ ] **Step 3: Commit** README and the screenshot; push `claude/project-thread-iubf0p`; open a draft PR titled "Four faction ships" with the four look-dev renders and the apron shot; report in the thread with the shots and wait for Q's merge.
