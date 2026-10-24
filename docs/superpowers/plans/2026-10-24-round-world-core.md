# Round World Core (retune and bare moon) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Steps 1 and 2 of the round-home-world spec: the game runs at Earth gravity with its jump heights kept, and `RUST_REGIME_LEVEL=moon` drops you on a 2 km sphere with streamed, solid, level-of-detail terrain, gravity toward the centre, a sliding origin and the movement controller running in a carried local frame.

**Architecture:** A `Surface` resource (flat plane or sphere) answers up, altitude, gravity, frame and ground for every system; the flat island and arena keep working through its `Flat` variant. A `planet` module owns the cube-sphere quadtree, worker-built chunk meshes with triangle-mesh colliders inside a 400 m physics bubble, a per-body gravity acceleration applied through Avian's force API, and the origin rebase. The controller rotates position and velocity into the player's frame at the start of each tick and back out at the end, so its Source math is untouched.

**Tech Stack:** Rust edition 2024, Bevy 0.19, Avian 0.7 (f32), fastnoise-lite 1 (3D OpenSimplex2), serde + toml. No new crates.

**Spec:** `docs/superpowers/specs/2026-10-24-round-home-world-design.md` (World model, Terrain engine, Gravity, Tuning, Tests, Build order steps 1 and 2). Programme context: `docs/superpowers/specs/2026-10-24-solar-system-programme.md`. One deliberate deviation: the exact "read the loaded chunk" ground lookup lives on the planet's `Chunks` resource rather than on `Surface`, which stays a pure function of seed and direction.

## Global Constraints

- Bevy 0.19, Avian 0.7, fastnoise-lite 1; no new dependencies in `Cargo.toml`.
- Physics at 66 Hz in `FixedUpdate`; f32 everywhere; Avian's default `FixedPostUpdate` schedule.
- Everything deterministic from seeds: a body's terrain is a pure function of `Body.seed` and a direction.
- `cargo test` is headless and stays green after every task; `cargo clippy --all-targets` stays as clean as today (the repo uses `#[allow(clippy::too_many_arguments)]` where needed).
- The flat island (default level) and the arena (`RUST_REGIME_LEVEL=arena`) keep working unchanged in behaviour through every task; `terrain.rs` is not removed in this plan.
- `tuning.toml` keys are F5 reloadable except `terrain.cell`; defaults live in `tuning.rs` `Default` impls and the file carries the same values with comments.
- Positions stored longer than a frame are body coordinates converted through `Origin`; live `Transform`s and Avian `Position`s are origin-relative.
- Altitude means metres above sea level; on the test moon sea level is 1000 m under the mean surface, so a point "N metres up" in a test is `sphere.surface_point(dir) + dir * N`, never `sphere.point(dir, N)`.
- Commit after every task with an imperative one-line subject in the repo's style, ending the message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. No model identifiers anywhere else.
- Suggested branch: `claude/round-world-core`, from `claude/solar-system-design` (which holds the specs).

## Review Focus

1. A player walking across a cube-face seam or corner must keep walking: `dir_face` and `leaf_at` must agree on seam directions, and the chunk grids of two faces must meet without a gap wider than a skirt. Pinned in Task 4 (`every_direction_has_exactly_one_leaf` samples seams and corners) and Task 7 (`runs_along_the_surface_for_a_minute` starts 150 m from a seam and crosses it).
2. A focus far above the surface (10 km up on a 2 km moon) must not split to the finest depth or produce thousands of leaves. Pinned in Task 4 (`splitting_follows_the_focus_with_hysteresis`).
3. A dynamic body, or the player, standing where the ground chunk is not built yet must not fall through the world. Pinned in Task 9 (`a_body_inside_the_bubble_stays_frozen_until_its_ground_is_built`, `the_player_hovers_until_the_ground_under_them_is_built`).
4. A rebase in the middle of a grapple swing must not teleport the player or cut the rope. Pinned in Task 10 (`rebase_keeps_the_world_together` holds a hook through the rebase).
5. Degenerate tuning must not hang or overflow: `terrain.cell` larger than a face gives depth 0, `terrain.workers = 0` behaves as 1. Pinned in Task 4 (`finest_depth_matches_the_cell`) and Task 8 (`builder_respects_the_worker_cap` runs with workers 0).

---

### Task 1: Earth gravity with the old jump heights

**Files:**
- Modify: `src/tuning.rs:131-200` (defaults), `tuning.toml` (top block, `[grenade]`), `src/vehicle/mod.rs:445-447` (brake fudge), `src/tests.rs:972`
- Test: `src/tests.rs`

**Interfaces:**
- Produces: `Tuning::default().gravity == 9.8`; every later task assumes it.

- [ ] **Step 1: Write the failing test** in `src/tests.rs` next to `walks_to_max_speed_on_ground`:

```rust
#[test]
fn jump_apex_is_unchanged_by_the_retune() {
    let mut app = make_app(Tuning::default());
    run(&mut app, 0.5);
    let apex = jump_apex(&mut app, |a| player(a).0.y);
    // v²/2g for 4.74 m/s at 9.8 is 1.146 m; the tick integrator lands a few cm under it.
    assert!((1.08..1.18).contains(&apex), "apex {apex}");
    assert_eq!(Tuning::default().gravity, 9.8);
}
```

with the helper `fn jump_apex(app: &mut App, altitude: impl Fn(&mut App) -> f32) -> f32`: records `altitude(app)`, sets `jump_pressed`, runs 100 updates and returns the largest `altitude(app) - start`.

- [ ] **Step 2: Run it to verify it fails**

Run: `cargo test jump_apex_is_unchanged_by_the_retune`
Expected: FAIL on the `gravity == 9.8` assertion.

- [ ] **Step 3: Retune defaults and file.** In `Tuning::default()`: `gravity: 9.8`, `jump_speed: 4.74`, `air_jump_speed: 4.74`, `wall_jump_up: 4.85`, `self_knockback: 9.7`; in `GrenadeTuning::default()`: `self_knockback: 8.2`. The same values in `tuning.toml`, each commented with the height it keeps (1.15 m jump, 1.2 m wall jump, 4.8 m rocket jump, 3.4 m grenade jump), and the `TF2 sv_gravity 800` comment replaced by `Earth; see the round-home-world spec`. In `src/vehicle/mod.rs` replace `let brake_t = spec.brake_t * g / 9.81;` with `let brake_t = spec.brake_t;` and drop the comment about heavier gravity. In `src/tests.rs:972` replace `Gravity(Vec3::NEG_Y * 17.6)` with `Gravity(Vec3::NEG_Y * Tuning::default().gravity)`.

- [ ] **Step 4: Run the whole suite**

Run: `cargo test`
Expected: PASS. If a test fails it encoded a 17.6-era number; derive it from `Tuning::default()` rather than loosen it, and name it in the commit body.

- [ ] **Step 5: Commit**

```bash
git add src/tuning.rs tuning.toml src/vehicle/mod.rs src/tests.rs
git commit -m "Earth gravity: 9.8 everywhere, jump and knockback speeds retuned to keep their heights"
```

### Task 2: Bodies as data

**Files:**
- Create: `assets/system.toml`, `src/system.rs`
- Modify: `src/main.rs` (`mod system;`)
- Test: unit test in `src/system.rs`

**Interfaces:**
- Produces:
  - `pub struct Body { pub radius: f32, pub gravity: f32, pub day_minutes: f32, pub tilt: f32, pub sea_level: f32, pub seed: u32, pub height: f32, pub wavelength: f32, pub land: f32, pub home: Option<Home> }` (`Deserialize, Clone, Debug, PartialEq`, `#[serde(default)]`; `Default` is the home world: 17500, 9.8, 48, 12, 0, 7, 900, 2000, 0.3, None)
  - `pub struct Home { pub lat: f32, pub lon: f32, pub core: f32, pub continent: f32 }`
  - `pub struct System { pub body: HashMap<String, Body> }` with `pub fn load() -> System` (reads `assets/system.toml`; warns and returns `System::default()` on error, like `tuning::load`) and `pub fn body(&self, id: &str) -> Option<&Body>`
  - `impl Body { pub fn test_moon() -> Body }`: radius 2000, gravity 9.8, day_minutes 48, tilt 0, sea_level -1000, seed 11, height 120, wavelength 2000, land 1.0, home None. The debug moon keeps 9.8 so movement tests compare like with like.

- [ ] **Step 1: Write the failing test** in `src/system.rs`:

```rust
#[test]
fn system_toml_declares_home_and_moon() {
    let s = System::load();
    let home = s.body("home").expect("home");
    assert_eq!((home.radius, home.gravity, home.day_minutes, home.tilt), (17500.0, 9.8, 48.0, 12.0));
    assert_eq!(home.home.as_ref().map(|h| (h.lat, h.lon, h.core, h.continent)), Some((12.0, 40.0, 4000.0, 35000.0)));
    let moon = s.body("moon").expect("moon");
    assert_eq!((moon.radius, moon.gravity, moon.sea_level), (2000.0, 9.8, -1000.0));
    assert_eq!(Body::default().radius, 17500.0);
    assert_eq!(Body::test_moon().seed, 11);
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cargo test system_toml_declares_home_and_moon`
Expected: FAIL to compile (no module).

- [ ] **Step 3: Write `assets/system.toml`** with the `[body.home]` table exactly as the spec prints it plus `wavelength = 2000`, and a `[body.moon]` table with the `test_moon` values under the comment `# debug sphere for RUST_REGIME_LEVEL=moon`. Implement `src/system.rs` per the Interfaces block; `PATH` is `"assets/system.toml"`.

- [ ] **Step 4: Run the test**

Run: `cargo test system_toml_declares_home_and_moon`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add assets/system.toml src/system.rs src/main.rs
git commit -m "Bodies as data: assets/system.toml declares the home world and the debug moon"
```

### Task 3: The surface API and the origin

**Files:**
- Create: `src/surface.rs`
- Modify: `src/main.rs` (`mod surface;`)
- Test: unit tests in `src/surface.rs`

**Interfaces:**
- Consumes: `system::Body`.
- Produces:
  - `#[derive(Resource, Clone)] pub enum Surface { Flat, Sphere(Arc<Sphere>) }`, `Default` is `Flat`.
  - `pub struct Sphere { pub body: Body, relief: FastNoiseLite, rubble: FastNoiseLite }` (`Clone`, `Send + Sync`) with `pub fn new(body: Body) -> Sphere`, `pub fn radius(&self) -> f32`, `pub fn sea_radius(&self) -> f32` (radius + sea_level), `pub fn height(&self, dir: Vec3) -> f32` (metres above sea level along unit `dir`), `pub fn point(&self, dir: Vec3, altitude: f32) -> Vec3` (`dir * (sea_radius + altitude)`), `pub fn surface_point(&self, dir: Vec3) -> Vec3` (`point(dir, height(dir))`).
  - `pub struct Ground { pub point: Vec3, pub normal: Vec3 }`.
  - On `Surface`: `pub fn up(&self, p: Vec3) -> Vec3`, `pub fn altitude(&self, p: Vec3) -> f32` (`Flat`: `p.y`), `pub fn gravity(&self, p: Vec3, flat_g: f32) -> Vec3` (`Flat`: `-Y * flat_g`; sphere: `-up * g0 * (R / |p|)²`), `pub fn frame(&self, p: Vec3) -> Quat` (local +Y up, local -Z toward body +Y which is the spin axis, local +X east; `Flat`: identity), `pub fn north(&self, p: Vec3) -> Option<Vec3>` (`None` within 5 m of a pole; `Flat`: `Some(-Z)`), `pub fn ground(&self, p: Vec3) -> Ground` (analytic: `surface_point(up(p))`, normal from the two tangent finite differences 1 m apart, outward).
  - `#[derive(Resource, Clone, Copy, Default, Debug)] pub struct Origin { pub offset: Vec3 }` with `pub const QUANTUM: f32 = 36.0`, `pub fn at(body: Vec3, quantum: f32) -> Origin` (offset = `body` rounded per component to a multiple of `quantum`), `pub fn world(&self, body: Vec3) -> Vec3` (`body - offset`), `pub fn body(&self, world: Vec3) -> Vec3`.
  - `#[cfg(test)] pub mod testing { pub fn random_dirs(n: usize) -> Vec<Vec3> }`: a fixed-seed LCG over spherical coordinates, shared by every test in the crate.
- Height function (the one algorithm the tests do not fix): `relief` is `OpenSimplex2` FBm, 8 octaves, gain 0.55, frequency `1 / body.wavelength`, seeded `body.seed`, sampled at `dir * radius`; `h = ((0.5 + 0.5 n).powf(1.6) - 0.3) * body.height`. `rubble` is a second `FastNoiseLite` seeded `seed + 1`, 2 octaves, frequency `1 / 1.6`, amplitude 0.15 m, added to `h`. Masks, stamps and roads arrive in the next plan.

- [ ] **Step 1: Write the failing tests** in `src/surface.rs`:

```rust
#[test]
fn sphere_height_is_deterministic_and_bounded() {
    let (a, b) = (Sphere::new(Body::test_moon()), Sphere::new(Body::test_moon()));
    let other = Sphere::new(Body { seed: 12, ..Body::test_moon() });
    let mut differs = false;
    for dir in testing::random_dirs(1000) {
        assert_eq!(a.height(dir), b.height(dir));
        differs |= a.height(dir) != other.height(dir);
        assert!((-36.2..=84.2).contains(&a.height(dir)), "{}", a.height(dir));
    }
    assert!(differs);
}

#[test]
fn frames_are_orthonormal_with_up_outward() {
    let s = Surface::Sphere(Arc::new(Sphere::new(Body::test_moon())));
    for dir in testing::random_dirs(200) {
        let p = dir * 2000.0;
        let f = s.frame(p);
        assert!((f.length() - 1.0).abs() < 1e-5);
        assert!((f * Vec3::Y).dot(s.up(p)) > 0.99999);
        if let Some(n) = s.north(p) { assert!((f * Vec3::NEG_Z).dot(n) > 0.9999 && n.dot(s.up(p)).abs() < 1e-4); }
    }
    assert!(s.north(Vec3::Y * 2000.0).is_none());
    assert!(s.north(Vec3::X * 2000.0).is_some());
}

#[test]
fn gravity_points_at_the_centre_and_falls_off() {
    let s = Surface::Sphere(Arc::new(Sphere::new(Body::test_moon())));
    let g = s.gravity(Vec3::X * 2000.0, 1.0);
    assert!((g.length() - 9.8).abs() < 1e-4 && g.normalize().dot(Vec3::NEG_X) > 0.99999);
    assert!((s.gravity(Vec3::X * 4000.0, 1.0).length() - 2.45).abs() < 1e-4);
    assert_eq!(s.altitude(Vec3::X * 1000.0), 0.0); // the test moon's sea radius is 1000 m
}

#[test]
fn flat_surface_matches_the_old_world() {
    let s = Surface::Flat;
    let p = Vec3::new(3.0, 4.5, -2.0);
    assert_eq!((s.up(p), s.altitude(p), s.frame(p), s.gravity(p, 9.8)), (Vec3::Y, 4.5, Quat::IDENTITY, Vec3::NEG_Y * 9.8));
    assert_eq!(s.ground(p).point, Vec3::new(3.0, 0.0, -2.0));
    assert_eq!(s.north(p), Some(Vec3::NEG_Z));
}

#[test]
fn analytic_ground_sits_on_the_surface() {
    let sphere = Sphere::new(Body::test_moon());
    let s = Surface::Sphere(Arc::new(sphere.clone()));
    for dir in testing::random_dirs(200) {
        let g = s.ground(sphere.surface_point(dir) + dir * 50.0);
        assert!((g.point.length() - (sphere.sea_radius() + sphere.height(dir))).abs() < 1e-2);
        assert!(g.normal.dot(dir) > 0.7 && (g.normal.length() - 1.0).abs() < 1e-4);
    }
}

#[test]
fn origin_quantizes_and_converts_both_ways() {
    let o = Origin::at(Vec3::new(1000.0, -77.0, 3.0), QUANTUM);
    for c in o.offset.to_array() { assert_eq!(c.rem_euclid(QUANTUM), 0.0); }
    assert!(o.offset.distance(Vec3::new(1000.0, -77.0, 3.0)) < QUANTUM);
    let x = Vec3::new(5.0, 6.0, 7.0);
    assert_eq!(o.world(o.body(x)), x);
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test surface::`
Expected: FAIL to compile.

- [ ] **Step 3: Implement `src/surface.rs`** per the Interfaces block. `frame` builds `Quat::from_mat3(&Mat3::from_cols(east, up, -north))` with `north = (Y - up * up.y).normalize()`, falling back to `(X - up * up.x).normalize()` within 5 m of a pole, and `east = north.cross(up)`.

- [ ] **Step 4: Run the tests**

Run: `cargo test surface::`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/surface.rs src/main.rs
git commit -m "Surface: one API for up, altitude, gravity, frame and ground on a plane or a sphere"
```

### Task 4: Cube-sphere quadtree and the `[terrain]` table

**Files:**
- Create: `src/planet/mod.rs` (module declarations only for now), `src/planet/quadtree.rs`
- Modify: `src/main.rs` (`mod planet;`), `src/tuning.rs` (`TerrainTuning`, `Tuning.terrain`), `tuning.toml` (`[terrain]`)
- Test: unit tests in `src/planet/quadtree.rs`, one in `src/tuning.rs`

**Interfaces:**
- Produces in `tuning.rs`: `pub struct TerrainTuning { pub cell: f32, pub split: f32, pub bubble: f32, pub site_range: f32, pub origin_step: f32, pub workers: usize }`, defaults `0.5, 2.5, 400.0, 1500.0, 2000.0, 4`, `pub fn merge(&self) -> f32` (`split + 0.5`), field `pub terrain: TerrainTuning` on `Tuning`, table `[terrain]` in `tuning.toml` with the spec's comments.
- Produces in `quadtree.rs`:
  - `pub const CHUNK: usize = 32;` cells per side.
  - `#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)] pub struct NodeId { pub face: u8, pub depth: u8, pub x: u32, pub y: u32 }`
  - `pub fn face_dir(face: u8, uv: Vec2) -> Vec3` (uv in [-1, 1]², warped `tan(u * PI / 4)`, faces 0..6 = +X, -X, +Y, -Y, +Z, -Z) and `pub fn dir_face(dir: Vec3) -> (u8, Vec2)` (its inverse; the dominant axis picks the face).
  - `impl NodeId`: `pub fn roots() -> [NodeId; 6]`, `pub fn children(self) -> [NodeId; 4]`, `pub fn parent(self) -> Option<NodeId>`, `pub fn uv_min(self) -> Vec2`, `pub fn uv_size(self) -> f32` (`2.0 / 2^depth`), `pub fn center_dir(self) -> Vec3`, `pub fn arc(self, radius: f32) -> f32` (`PI / 2 * radius / 2^depth`), `pub fn cell(self, radius: f32) -> f32` (`arc / CHUNK as f32`), `pub fn contains(self, dir: Vec3) -> bool`, `pub fn is_ancestor_of(self, other: NodeId) -> bool`, `pub fn leaf_at(dir: Vec3, depth: u8) -> NodeId`.
  - `pub fn finest_depth(radius: f32, cell: f32) -> u8`: the smallest depth whose `cell(radius) <= cell`, capped at 20.
  - `pub fn node_distance(node: NodeId, radius: f32, focus: Vec3) -> f32`: `(focus.distance(node.center_dir() * radius) - 0.75 * node.arc(radius)).max(0.0)`.
  - `pub fn select_leaves(radius: f32, max_depth: u8, focus: Vec3, split: f32, merge: f32, previous: &HashSet<NodeId>) -> HashSet<NodeId>`: walk from the roots; a node at `max_depth` is a leaf; a node that was split before (some `previous` leaf is its strict descendant) stays split unless `node_distance > merge * arc`; otherwise it splits iff `node_distance < split * arc`.

- [ ] **Step 1: Write the failing tests** in `src/planet/quadtree.rs`:

```rust
#[test]
fn face_mapping_round_trips() {
    let seams = [Vec3::new(1.0, 1.0, 0.0), Vec3::ONE, Vec3::new(-1.0, 1.0, 1.0)].map(Vec3::normalize);
    for dir in random_dirs(500).into_iter().chain(seams) {
        let (face, uv) = dir_face(dir);
        assert!(uv.abs().max_element() <= 1.0 + 1e-6);
        assert!(face_dir(face, uv).dot(dir) > 1.0 - 1e-6, "{dir}");
    }
}

#[test]
fn children_tile_their_parent() {
    let n = NodeId { face: 2, depth: 3, x: 5, y: 1 };
    let kids = n.children();
    assert!(kids.iter().all(|k| k.parent() == Some(n) && (k.uv_size() - n.uv_size() / 2.0).abs() < 1e-9));
    for i in 0..200 {
        let uv = n.uv_min() + Vec2::new(((i * 7) % 23) as f32 / 23.0, ((i * 11) % 19) as f32 / 19.0) * n.uv_size();
        assert_eq!(kids.iter().filter(|k| k.contains(face_dir(2, uv))).count(), 1);
    }
}

#[test]
fn every_direction_has_exactly_one_leaf() {
    let focus = Vec3::new(0.0, 0.6, 0.8).normalize() * 2000.0;
    let leaves = select_leaves(2000.0, 8, focus, 2.5, 3.0, &HashSet::new());
    let seams = [Vec3::new(1.0, 1.0, 0.0), Vec3::new(1.0, 0.0, 1.0), Vec3::ONE, Vec3::new(1.0, -1.0, 1.0), Vec3::new(0.0, 1.0, 1.0)].map(Vec3::normalize);
    for dir in random_dirs(2000).into_iter().chain(seams) {
        assert_eq!(leaves.iter().filter(|l| l.contains(dir)).count(), 1, "{dir}");
        let finest = NodeId::leaf_at(dir, 8);
        assert!(leaves.iter().any(|l| *l == finest || l.is_ancestor_of(finest)));
    }
}

#[test]
fn splitting_follows_the_focus_with_hysteresis() {
    let focus = Vec3::X * 2000.0;
    let a = select_leaves(2000.0, 8, focus, 2.5, 3.0, &HashSet::new());
    assert!(a.contains(&NodeId::leaf_at(Vec3::X, 8)), "the leaf under the focus is finest");
    assert!(a.len() < 400, "{}", a.len());
    let high = select_leaves(2000.0, 8, Vec3::X * 12000.0, 2.5, 3.0, &HashSet::new());
    assert!(high.iter().all(|l| l.depth <= 2) && high.len() <= 96, "{}", high.len());
    // 3 m is inside the hysteresis band of every depth (half an arc, 6 m at the finest), so going back changes nothing.
    let nudged = select_leaves(2000.0, 8, focus + Vec3::Z * 3.0, 2.5, 3.0, &a);
    assert_eq!(select_leaves(2000.0, 8, focus, 2.5, 3.0, &nudged), nudged);
    // 10 m swaps a handful of finest leaves, not the whole ring.
    let moved = select_leaves(2000.0, 8, focus + Vec3::Z * 10.0, 2.5, 3.0, &a);
    assert!(moved.symmetric_difference(&a).count() <= 60, "{}", moved.symmetric_difference(&a).count());
}

#[test]
fn finest_depth_matches_the_cell() {
    assert_eq!(finest_depth(17500.0, 0.5), 11);
    assert_eq!(finest_depth(2000.0, 0.5), 8);
    assert_eq!(finest_depth(2000.0, 4.0), 5);
    assert_eq!(finest_depth(2000.0, 1e9), 0);
    assert!((NodeId::leaf_at(Vec3::X, 11).cell(17500.0) - 0.42).abs() < 0.01);
}
```

And in `src/tuning.rs` tests, `terrain_table_defaults()`: `TerrainTuning::default()` fields equal `(0.5, 2.5, 400.0, 1500.0, 2000.0, 4)` and `merge() == 3.0`.

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test quadtree:: terrain_table_defaults`
Expected: FAIL to compile.

- [ ] **Step 3: Implement** `TerrainTuning` and `src/planet/quadtree.rs` per the Interfaces block. `src/planet/mod.rs` holds `pub mod quadtree;` only.

- [ ] **Step 4: Run the tests**

Run: `cargo test quadtree:: terrain_table_defaults`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planet src/main.rs src/tuning.rs tuning.toml
git commit -m "Cube-sphere quadtree: face mapping, node ids, split and merge with hysteresis, [terrain] table"
```

### Task 5: Chunk meshes and colliders

**Files:**
- Create: `src/planet/chunk.rs`
- Modify: `src/planet/mod.rs` (`pub mod chunk;`)
- Test: unit tests in `src/planet/chunk.rs`, one physics test in `src/tests.rs`

**Interfaces:**
- Consumes: `surface::{Sphere, Ground, Origin}`, `quadtree::{NodeId, CHUNK, dir_face}`.
- Produces:
  - `pub const GRID: usize = CHUNK + 1;` (33 vertices per side)
  - `pub fn rim_order() -> Vec<usize>`: the `4 * (GRID - 1)` grid indices of the border, in order: bottom row left to right, right column bottom to top, top row right to left, left column top to bottom, each corner listed once.
  - `pub struct ChunkMesh { pub node: NodeId, pub center: Vec3, pub positions: Vec<Vec3>, pub normals: Vec<Vec3>, pub weights: Vec<[f32; 4]>, pub indices: Vec<[u32; 3]> }`: `center` in body coordinates (the surface point under the node's centre direction), positions relative to it; the first `GRID * GRID` vertices are the grid row-major with `v` outer and `u` inner, then one skirt vertex per `rim_order()` entry; triangles wound so their normals point away from the body centre.
  - `pub fn skirt_depth(arc: f32) -> f32` (`(0.05 * arc).max(1.0)`)
  - `pub fn build_chunk(sphere: &Sphere, node: NodeId) -> ChunkMesh`: evaluates `height` on the grid plus a one-cell apron; a vertex normal is `normalize((P(u, v+1) - P(u, v-1)).cross(P(u+1, v) - P(u-1, v)))` flipped if it points inward; `weights` are a placeholder `[1.0, 0.0, 0.0, 0.0]` until the next plan ports `splat_weights`; skirt vertex `k` is rim vertex `rim_order()[k]` moved toward the body centre by `skirt_depth(arc)`.
  - `impl ChunkMesh`: `pub fn mesh(&self) -> Mesh` (positions, normals, indices; no colour attribute in this plan), `pub fn collider(&self) -> Collider` (`Collider::trimesh(positions, indices)`), `pub fn ground_on(&self, dir: Vec3) -> Option<Ground>` (locate the cell with `dir_face` inside the node, interpolate on the same two triangles per cell as the mesh; `None` outside the node).
  - `#[cfg(test)] pub fn spawn_ground(world: &mut World, sphere: &Sphere, origin: &Origin, cell: f32, around: Vec3, radius: f32) -> Vec<Arc<ChunkMesh>>`: spawns `(RigidBody::Static, collider, Transform::from_translation(origin.world(center)))` for every finest-depth leaf (`finest_depth(sphere.radius(), cell)`) whose centre is within `radius + arc` of `around` (body coordinates); returns the meshes.

- [ ] **Step 1: Write the failing tests** in `src/planet/chunk.rs`:

```rust
#[test]
fn chunk_vertices_lie_on_the_surface_and_face_out() {
    let s = Sphere::new(Body::test_moon());
    let node = NodeId::leaf_at(Vec3::new(0.3, 0.9, 0.3).normalize(), 5);
    let c = build_chunk(&s, node);
    assert_eq!(c.positions.len(), GRID * GRID + 4 * (GRID - 1));
    for (i, p) in c.positions.iter().take(GRID * GRID).enumerate() {
        let world = c.center + *p;
        let dir = world.normalize();
        assert!((world.length() - (s.sea_radius() + s.height(dir))).abs() < 1e-2, "vertex {i}");
        assert!(c.normals[i].dot(dir) > 0.5);
    }
    for tri in &c.indices {
        let [a, b, d] = tri.map(|i| c.positions[i as usize]);
        assert!((b - a).cross(d - a).dot(c.center) >= -1e-3, "wound outward");
    }
}

#[test]
fn skirt_hangs_below_the_rim() {
    let s = Sphere::new(Body::test_moon());
    let node = NodeId::leaf_at(Vec3::X, 5);
    let c = build_chunk(&s, node);
    let depth = skirt_depth(node.arc(2000.0));
    for (k, rim) in rim_order().into_iter().enumerate() {
        let (top, skirt) = (c.center + c.positions[rim], c.center + c.positions[GRID * GRID + k]);
        assert!((top.length() - skirt.length() - depth).abs() < 1e-3 && top.normalize().dot(skirt.normalize()) > 0.999999);
    }
}

#[test]
fn ground_on_interpolates_the_grid() {
    let s = Sphere::new(Body::test_moon());
    let node = NodeId::leaf_at(Vec3::Z, 5);
    let c = build_chunk(&s, node);
    for i in [0usize, 17, GRID * GRID - 1] {
        let v = c.center + c.positions[i];
        assert!(c.ground_on(v.normalize()).unwrap().point.distance(v) < 1e-3);
    }
    let (a, b) = (c.center + c.positions[5], c.center + c.positions[6]);
    assert!(c.ground_on((a + b).normalize()).unwrap().point.distance((a + b) / 2.0) < 1e-2);
    assert!(c.ground_on(Vec3::NEG_Z).is_none());
}
```

And in `src/tests.rs`, with `fn drop_flat_floor(app: &mut App)` extracted from `colliders_match_heightmap`:

```rust
#[test]
fn chunk_colliders_match_their_meshes() {
    let sphere = Sphere::new(Body::test_moon());
    let origin = Origin::at(sphere.surface_point(Vec3::X), QUANTUM);
    let mut app = make_app(Tuning::default());
    drop_flat_floor(&mut app);
    let meshes = chunk::spawn_ground(app.world_mut(), &sphere, &origin, 4.0, sphere.surface_point(Vec3::X), 60.0);
    app.update();
    for dir in random_dirs(20).into_iter().map(|d| (Vec3::X * 40.0 + d).normalize()) {
        let Some(g) = meshes.iter().find_map(|m| m.ground_on(dir)) else { continue };
        let from = origin.world(sphere.surface_point(dir) + dir * 100.0);
        let hit = app.world_mut().run_system_once(move |q: SpatialQuery| q.cast_ray(from, Dir3::new(-dir).unwrap(), 300.0, true, &SpatialQueryFilter::default())).unwrap().expect("ray hits the chunk");
        assert!(origin.body(from - dir * hit.distance).distance(g.point) < 1e-2);
    }
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test chunk`
Expected: FAIL to compile.

- [ ] **Step 3: Implement `src/planet/chunk.rs`** per the Interfaces block. The apron is `(GRID + 2)²` samples one cell beyond the grid on each side in face coordinates.

- [ ] **Step 4: Run the tests**

Run: `cargo test chunk`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planet/chunk.rs src/planet/mod.rs src/tests.rs
git commit -m "Terrain chunks: 33 by 33 grids with skirts, trimesh colliders and exact ground lookup"
```

### Task 6: Gravity toward the centre for dynamic bodies

**Files:**
- Create: `src/planet/gravity.rs`
- Modify: `src/planet/mod.rs` (`pub mod gravity;`)
- Test: `src/tests.rs`

**Interfaces:**
- Consumes: `Surface`, `Origin`, `Tuning.gravity`.
- Produces: `pub fn gravitate(surface: Res<Surface>, origin: Res<Origin>, tuning: Res<Tuning>, mut bodies: Query<(&RigidBody, Forces), Without<RigidBodyDisabled>>)`: for every `RigidBody::Dynamic`, `forces.non_waking().apply_linear_acceleration(surface.gravity(origin.body(forces.position().0), tuning.gravity))`. Installed in `FixedUpdate` by the planet level only (Task 11); flat levels keep Avian's `Gravity` resource.
- Produces for tests in `src/tests.rs`: `fn sphere_app(cell: f32, spawn_dir: Vec3, ground_radius: f32) -> (App, Arc<Sphere>, Origin, Vec<Arc<ChunkMesh>>)`: `build_app` with `terrain.cell = cell`, `drop_flat_floor`, insert `Surface::Sphere`, `spawn = sphere.surface_point(spawn_dir) + spawn_dir * 1.0`, `Origin::at(spawn, QUANTUM)`, `WorldBounds { spawn, kill_y: f32::MIN }` (the field becomes `kill_altitude: -2.0` in Task 7), `Gravity(Vec3::ZERO)`, add `gravitate` to `FixedUpdate` before `ControllerSet`; `finish`, one `update`, then `spawn_ground` around `spawn` to `ground_radius` (skipped when it is 0).

- [ ] **Step 1: Write the failing tests** in `src/tests.rs`:

```rust
#[test]
fn crates_fall_toward_the_centre_and_rest() {
    let (mut app, sphere, origin, meshes) = sphere_app(4.0, Vec3::X, 80.0);
    let dir = Vec3::X;
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(sphere.surface_point(dir) + dir * 50.0)))).id();
    run(&mut app, 6.0);
    let pos = origin.body(app.world().get::<Transform>(id).unwrap().translation);
    let ground = meshes.iter().find_map(|m| m.ground_on(pos.normalize())).unwrap().point;
    assert!(pos.normalize().dot(dir) > 0.99996, "fell radially: {pos}");
    assert!((pos.length() - ground.length() - 0.5).abs() < 0.1, "rests on the ground, {} over it", pos.length() - ground.length());
    assert!(app.world().get::<LinearVelocity>(id).unwrap().0.length() < 0.05);
}

#[test]
fn resting_bodies_stay_asleep_under_gravity() {
    let (mut app, sphere, origin, _) = sphere_app(4.0, Vec3::X, 80.0);
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(sphere.surface_point(Vec3::X) + Vec3::X * 3.0)))).id();
    run(&mut app, 5.0);
    assert!(app.world().get::<Sleeping>(id).is_some(), "asleep after settling");
    run(&mut app, 1.0);
    assert!(app.world().get::<Sleeping>(id).is_some(), "gravity does not keep waking it");
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test crates_fall resting_bodies`
Expected: FAIL to compile.

- [ ] **Step 3: Implement `gravitate` and `sphere_app`.**

- [ ] **Step 4: Run the tests**

Run: `cargo test crates_fall resting_bodies`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planet/gravity.rs src/planet/mod.rs src/tests.rs
git commit -m "Dynamic bodies fall toward the body centre through Avian's force API"
```

### Task 7: The controller, camera and body in a carried frame

**Files:**
- Modify: `src/controller.rs` (whole tick), `src/input.rs:45-60`, `src/camera.rs:31-78`, `src/body.rs:96-125`, `src/abilities.rs:143-153,189-192`, `src/weapon.rs:434`, `src/sound.rs:396`, `src/vehicle/mod.rs:296`, `src/terrain.rs:267`, `src/planet/mod.rs` (`spawn_course`, `COURSE_DECK`), `src/tests.rs:513,545`
- Test: `src/tests.rs`

**Interfaces:**
- Consumes: `Surface`, `Origin`, `chunk::spawn_ground`, `sphere_app`.
- Produces:
  - `Player.frame: Quat` (pub, default identity), `pub fn up(&self) -> Vec3`, `pub fn vertical(&self) -> f32` (`velocity.dot(up)`), `horizontal_speed` becomes `(velocity - up * vertical).length()`, `pub fn shift(&mut self, delta: Vec3)` (subtracts `delta` from `prev_pos` and an active mantle's three points; used by Task 10).
  - `WorldBounds { pub spawn: Vec3, pub kill_altitude: f32 }` (`spawn` in body coordinates; default `(SPAWN, -30.0)`); the kill test is `surface.altitude(origin.body(pos)) < bounds.kill_altitude`; respawn sets `tf.translation = origin.world(bounds.spawn)` and `p.frame = surface.frame(bounds.spawn)`; `spawn_player` does the same and sets `rotation = frame`.
  - `ControllerPlugin` calls `init_resource::<Surface>()` and `init_resource::<Origin>()`.
  - `ViewAngles { pub yaw: f32, pub pitch: f32, pub frame: Quat }` with `rotation()` = `frame * from_euler(YXZ, yaw, pitch, 0)`, `flat_basis()` frame-rotated, new `pub fn local_basis(&self) -> (Vec3, Vec3)` = the old unrotated math.
  - `Space { query, filter, frame: Quat }`: `cast`, `ray` and `fits` take and return frame-local vectors, calling Avian with `frame * pos`, `frame` as the shape rotation, `frame * dir`, and rotating `normal1` back with `frame.inverse()`.
  - `camera.rs`: `PerspectiveProjection.far = 10_000.0`; translation `body + p.up() * (eye + correction)`, rotation `p.frame * from_euler(YXZ, yaw, pitch, roll)`.
  - `pub const COURSE_DECK: f32 = 3.0;` and `pub fn spawn_course(world: &mut World, surface: &Surface, origin: &Origin, at: Vec3)` in `src/planet/mod.rs`: in the frame at `at` (a body-coordinate surface point), static grey cuboids: a deck `40×0.5×50` centred at local `(4, 2.75, -22)` whose top is `COURSE_DECK`, and on it, with local y measured from the deck top, a step `3×0.4×12` at `(8, 0.2, -10.5)`, a wall `1×8×40` at `(1, 4, -40)`, a ledge `4×1.8×4` at `(-8, 0.9, -3)` and a tunnel roof `6×0.5×10` at `(16, 1.75, -10)`. The deck floats a few metres over the rolling ground so the course is flat; the terrain itself is what the run and jump tests stand on.
- Tick algorithm (the one piece the tests do not fix): read `up = surface.up(origin.body(pos))`, set `p.frame = (Quat::from_rotation_arc(p.frame * Vec3::Y, up) * p.frame).normalize()` and `view.frame = p.frame`; rotate `pos`, `p.velocity`, `p.wall_normal`, `p.last_wall` into the frame with `frame.inverse()`; take `(forward, right) = view.local_basis()`; run the existing tick unchanged with `t.gravity` replaced by `surface.gravity(origin.body(pos_world), t.gravity).length()`; at the end rotate `pos`, `velocity`, `wall_normal`, `last_wall` and each hit normal used to shove props back with `frame`, then set `tf.translation` and `tf.rotation = p.frame`. A mantle stores world points. Body: `translation = center - p.up() * half - forward * BACK`, `rotation = p.frame * from_rotation_y(yaw + PI)`, `vertical` from `p.vertical()`. Grapple and `weapon::fire`: eye offsets along `p.up()`; the grapple's gravity-cancel adds along `p.up()` with magnitude `surface.gravity(..).length()`. `sound.rs`: `p.vertical() > 2.0`. `vehicle/mod.rs:296`: the altitude test through `Res<Surface>` and `Res<Origin>`. `terrain.rs:267`: `kill_altitude: island.water_level - 2.0`.

- [ ] **Step 1: Write the failing tests** in `src/tests.rs`. Helpers: `fn course_frame(sphere, at_dir) -> (Vec3, Quat)` returns `(sphere.surface_point(at_dir), Surface::Sphere(..).frame(that point))`; `fn set_player_local(app, origin, sphere, at_dir, local_pos, local_vel)` calls `set_player` with `origin.world(at + frame * (local_pos + Vec3::Y * COURSE_DECK))` and `frame * local_vel`; `fn player_local(app, origin, sphere, at_dir) -> (Vec3, Vec3, MoveState)` inverts it (position relative to the deck top, velocity in the frame).

```rust
#[test]
fn runs_along_the_surface_for_a_minute() {
    // On the equator 150 m short of the +X/+Z face seam; local -X is west, toward +Z and across it.
    let theta = std::f32::consts::FRAC_PI_4 - 150.0 / 2000.0;
    let start = Vec3::new(theta.cos(), 0.0, theta.sin());
    let (mut app, _, origin, meshes) = sphere_app(4.0, start, 650.0);
    app.world_mut().resource_mut::<ViewAngles>().yaw = std::f32::consts::FRAC_PI_2;
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 60.0);
    let (pos, _, state) = player(&mut app);
    let body = origin.body(pos);
    let dir = body.normalize();
    assert_eq!(state, MoveState::Ground);
    assert!(dir.angle_between(start) * 2000.0 > 380.0, "travelled {} m", dir.angle_between(start) * 2000.0);
    assert!(dir.z > start.z + 0.1, "went toward +Z, across the seam");
    let ground = meshes.iter().find_map(|m| m.ground_on(dir)).expect("still on built ground").point;
    assert!((body.length() - ground.length() - 0.9).abs() < 0.05, "feet {} m over the mesh", body.length() - ground.length());
}

#[test]
fn jump_height_on_the_sphere_matches_the_flat_world() {
    let flat = { let mut app = make_app(Tuning::default()); run(&mut app, 0.5); jump_apex(&mut app, |a| player(a).0.y) };
    for dir in [Vec3::Y, Vec3::X] {
        let (mut app, _, origin, _) = sphere_app(4.0, dir, 60.0);
        run(&mut app, 0.5);
        let apex = jump_apex(&mut app, |a| origin.body(player(a).0).length());
        assert!((apex - flat).abs() < 0.02 * flat, "apex {apex} vs flat {flat} at {dir}");
    }
}

#[test]
fn stairs_wall_runs_mantles_and_slides_on_the_sphere() {
    let at = Vec3::new(0.2, 0.7, 0.68).normalize();
    let (mut app, sphere, origin, _) = sphere_app(4.0, at, 40.0);
    let surface = Surface::Sphere(sphere.clone());
    planet::spawn_course(app.world_mut(), &surface, &origin, sphere.surface_point(at));
    // Wall run and wall jump, as in wall_runs_along_wall.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(0.2, 2.5, -18.0), Vec3::new(0.0, 2.0, -9.0));
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 1.0);
    assert_eq!(player(&mut app).2, MoveState::WallRun);
    input(&mut app).jump_pressed = true;
    app.update();
    let (_, vel, state) = player_local(&mut app, &origin, &sphere, at);
    assert!(state == MoveState::Air && vel.x < -3.0 && vel.y > 3.0, "wall jump {vel}");
    // Mantle, as in mantles_onto_ledge.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(-8.0, 0.95, 0.0), Vec3::ZERO);
    input(&mut app).movement = Vec2::Y;
    run(&mut app, 0.3);
    input(&mut app).jump_pressed = true;
    run(&mut app, 0.6);
    assert!(player_local(&mut app, &origin, &sphere, at).0.y > 2.6, "mantled");
    // Stair step onto the 0.4 m block and keep walking on it.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(8.0, 0.95, -2.0), Vec3::ZERO);
    run(&mut app, 1.2);
    let (p, _, state) = player_local(&mut app, &origin, &sphere, at);
    assert!(state == MoveState::Ground && p.y > 1.2 && p.z < -6.0, "stepped up: {p}");
    // Slide under the tunnel roof, as in slides_under_low_ceiling.
    set_player_local(&mut app, &origin, &sphere, at, Vec3::new(16.0, 0.95, 0.0), Vec3::new(0.0, 0.0, -8.0));
    { let mut i = input(&mut app); i.movement = Vec2::Y; i.crouch_held = true; }
    run(&mut app, 0.4);
    assert_eq!(player(&mut app).2, MoveState::Slide);
    run(&mut app, 2.5);
    assert!(player_local(&mut app, &origin, &sphere, at).0.z < -15.0, "slid through the tunnel");
}

#[test]
fn falling_under_the_sea_respawns_on_the_sphere() {
    let (mut app, sphere, origin, _) = sphere_app(4.0, Vec3::X, 60.0);
    set_player(&mut app, origin.world(sphere.point(Vec3::Z, -5.0)), Vec3::ZERO); // 5 m under sea level, deep inside the test moon
    run(&mut app, 0.1);
    let (pos, _, _) = player(&mut app);
    assert!(origin.body(pos).distance(sphere.surface_point(Vec3::X) + Vec3::X) < 1.0);
    let frame = app.world_mut().query::<&Player>().single(app.world()).unwrap().frame;
    assert!((frame * Vec3::Y).dot(Vec3::X) > 0.9999);
}
```

Update `falling_in_water_respawns_at_world_bounds` and `player_dies_and_respawns_with_full_health` to the `kill_altitude` field, and `sphere_app` to `kill_altitude: -2.0`.

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test on_the_sphere runs_along_the_surface falling_under_the_sea`
Expected: FAIL to compile (`frame`, `kill_altitude`, `spawn_course`).

- [ ] **Step 3: Implement** per the Interfaces and Tick algorithm blocks, file by file in the order listed under Files.

- [ ] **Step 4: Run the whole suite**

Run: `cargo test`
Expected: PASS, every flat test unchanged (the identity frame makes the new path the old path).

- [ ] **Step 5: Run the flat island by hand**

Run: `cargo run --release` for a minute at base camp: jump, wall run on the camp walls, mantle a crate, drive the jeep ten seconds, open the wardrobe. Then `RUST_REGIME_LEVEL=arena cargo run --release` for the parkour course.
Expected: no behaviour change; camera and body stand upright.

- [ ] **Step 6: Commit**

```bash
git add src/controller.rs src/input.rs src/camera.rs src/body.rs src/abilities.rs src/weapon.rs src/sound.rs src/vehicle/mod.rs src/terrain.rs src/planet/mod.rs src/tests.rs
git commit -m "Controller, camera and body run in a carried local frame; up and gravity come from the surface"
```

### Task 8: Streaming the quadtree with worker-built chunks

**Files:**
- Modify: `src/planet/mod.rs`
- Test: `src/tests.rs`

**Interfaces:**
- Consumes: `quadtree::select_leaves`, `chunk::build_chunk`, `TerrainTuning`, `Origin`.
- Produces:
  - `#[derive(Resource)] pub struct Planet { pub sphere: Arc<Sphere>, pub max_depth: u8 }`
  - `#[derive(Resource, Default)] pub struct Chunks { pub wanted: HashSet<NodeId>, pub built: HashMap<NodeId, Entity>, pub pending: HashMap<NodeId, Task<ChunkMesh>>, pub loaded: HashMap<NodeId, Arc<ChunkMesh>>, pub solid: HashSet<NodeId> }` with `pub fn ground(&self, sphere: &Sphere, p_body: Vec3) -> Ground` (the finest loaded leaf containing the direction, else `Surface::Sphere` analytic) and `pub fn is_solid(&self, p_body: Vec3) -> bool` (the built leaf containing the direction is in `solid`; until Task 9 every built leaf is inserted into `solid` at apply time).
  - `#[derive(Component)] pub struct Chunk { pub node: NodeId }`
  - `pub fn focus(player_world: Vec3, velocity: Vec3, origin: &Origin) -> Vec3` (`origin.body(player_world + velocity)`, one second of lookahead)
  - `pub struct PlanetPlugin { pub body: String }` and `pub fn add_streaming(app: &mut App)`, which registers `Planet` (from the `Surface::Sphere` already in the app, `max_depth = finest_depth(radius, terrain.cell)`), `Chunks`, and `plan` then `apply` in `Update`; the plugin calls it.
- Streaming algorithm: `plan` recomputes `wanted` from `select_leaves(radius, max_depth, focus, split, merge(), &wanted)`; for each wanted node neither built nor pending, while `pending.len() < workers.max(1)`, spawn a task on `AsyncComputeTaskPool::get()` running `build_chunk(&sphere, node)`; a built node not in `wanted` is despawned and dropped from `built`, `loaded` and `solid` when (a) every wanted strict descendant of it is built, or (b) its wanted ancestor is built, or (c) it has no wanted ancestor or descendant. `apply` polls each pending task with `bevy::tasks::block_on(bevy::tasks::poll_once(&mut task))`; at most two finished chunks per frame are spawned as `(Name, Chunk, Mesh3d, MeshMaterial3d(grey StandardMaterial, perceptual_roughness 1.0), Transform::from_translation(origin.world(center)), RigidBody::Static)` plus `Collider` when `node_distance(..) <= bubble`, recorded in `built`, `loaded` and `solid`. Without a `Player` entity `plan` returns.

- [ ] **Step 1: Write the failing tests** in `src/tests.rs`:

```rust
fn streaming_app(workers: usize) -> (App, Arc<Sphere>, Origin) {
    let (mut app, sphere, origin, _) = sphere_app(4.0, Vec3::X, 0.0);
    app.world_mut().resource_mut::<Tuning>().terrain.workers = workers;
    planet::add_streaming(&mut app);
    (app, sphere, origin)
}

/// Updates until every wanted chunk is built and nothing else remains, then one more frame.
fn settle(app: &mut App) {
    for _ in 0..600 {
        app.update();
        let c = app.world().resource::<planet::Chunks>();
        if c.pending.is_empty() && c.built.keys().copied().collect::<HashSet<_>>() == c.wanted { app.update(); return; }
    }
    panic!("streaming did not converge");
}

fn covered(app: &mut App, dir: Vec3) -> usize { app.world().resource::<planet::Chunks>().built.keys().filter(|n| n.contains(dir)).count() }

#[test]
fn streaming_converges_to_a_tiling_and_never_leaves_holes() {
    let (mut app, sphere, origin) = streaming_app(4);
    settle(&mut app);
    let dirs = random_dirs(500);
    for d in &dirs { assert_eq!(covered(&mut app, *d), 1, "{d}"); }
    assert!(app.world().resource::<planet::Chunks>().built.contains_key(&NodeId::leaf_at(Vec3::X, 5)), "finest under the player");
    for step in 1..=10 {
        let dir = Vec3::new(1.0, 0.0, 0.15 * step as f32).normalize();
        set_player(&mut app, origin.world(sphere.surface_point(dir) + dir), Vec3::ZERO);
        for _ in 0..30 { app.update(); for d in &dirs { assert!(covered(&mut app, *d) >= 1, "hole at {d} during step {step}"); } }
    }
    settle(&mut app);
    for d in &dirs { assert_eq!(covered(&mut app, *d), 1); }
}

#[test]
fn builder_respects_the_worker_cap() {
    for workers in [0usize, 2] {
        let (mut app, _, _) = streaming_app(workers);
        for _ in 0..200 { app.update(); assert!(app.world().resource::<planet::Chunks>().pending.len() <= workers.max(1)); }
    }
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test streaming builder_respects`
Expected: FAIL to compile.

- [ ] **Step 3: Implement `src/planet/mod.rs`** per the Interfaces and Streaming algorithm blocks.

- [ ] **Step 4: Run the tests**

Run: `cargo test streaming builder_respects`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planet/mod.rs src/tests.rs
git commit -m "Stream terrain chunks around the player on worker threads, swapping without holes"
```

### Task 9: The physics bubble

**Files:**
- Create: `src/planet/bubble.rs`
- Modify: `src/planet/mod.rs` (`pub mod bubble;`, register the systems in `add_streaming`)
- Test: `src/tests.rs`

**Interfaces:**
- Consumes: `Chunks`, `Chunk`, `TerrainTuning.bubble`, `node_distance`, `Player`.
- Produces:
  - `#[derive(Component)] pub struct Frozen;`
  - `pub fn solidify(...)` in `Update` after `apply`: for every `Chunk` entity, inside means `node_distance(node, radius, player_body) <= bubble`; insert `Collider` from `loaded[node].collider()` and add the node to `solid` when inside and absent; remove both when outside and present.
  - `pub fn freeze(...)` in `FixedUpdate` before `ControllerSet` and before `gravitate`: for every `RigidBody::Dynamic` entity without `Player`: farther than `bubble` from the player, or `!chunks.is_solid(pos_body)` → insert `(RigidBodyDisabled, Frozen)` if absent; with `Frozen`, nearer than `bubble - 50` and `chunks.is_solid(pos_body)` → remove both.
  - `pub fn hold_player(...)` in `FixedUpdate` before `ControllerSet`: while `!chunks.is_solid(origin.body(player pos))`, set `p.velocity = Vec3::ZERO` and `p.knockback_lock = 0.0`, so the player hovers in place until the ground under them exists. The controller then snaps them down within a tick.

- [ ] **Step 1: Write the failing tests** in `src/tests.rs`:

```rust
#[test]
fn only_chunks_inside_the_bubble_are_solid() {
    let (mut app, _, origin) = streaming_app(4);
    settle(&mut app);
    let bubble = app.world().resource::<Tuning>().terrain.bubble;
    let player_body = origin.body(player(&mut app).0);
    let mut q = app.world_mut().query::<(&planet::Chunk, Has<Collider>)>();
    for (c, solid) in q.iter(app.world()) {
        assert_eq!(solid, quadtree::node_distance(c.node, 2000.0, player_body) <= bubble, "{:?}", c.node);
    }
}

#[test]
fn bodies_outside_the_bubble_freeze_and_wake_on_solid_ground() {
    let (mut app, sphere, origin) = streaming_app(4);
    settle(&mut app);
    let far = Vec3::new(1.0, 0.0, 0.35).normalize(); // about 680 m from the player
    let start = sphere.surface_point(far) + far * 20.0;
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(start)))).id();
    run(&mut app, 2.0);
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_some() && app.world().get::<RigidBodyDisabled>(id).is_some());
    assert!(origin.body(app.world().get::<Transform>(id).unwrap().translation).distance(start) < 1e-3, "did not move");
    set_player(&mut app, origin.world(sphere.surface_point(far) + far), Vec3::ZERO);
    settle(&mut app);
    run(&mut app, 6.0);
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_none());
    let height = origin.body(app.world().get::<Transform>(id).unwrap().translation).length() - sphere.surface_point(far).length();
    assert!(height < 15.0, "fell once woken, {height} m up");
}

#[test]
fn a_body_inside_the_bubble_stays_frozen_until_its_ground_is_built() {
    let (mut app, sphere, origin) = streaming_app(4);
    let start = sphere.surface_point(Vec3::X) + Vec3::X * 5.0;
    let id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin.world(start)))).id();
    app.update();
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_some(), "no ground yet");
    settle(&mut app);
    run(&mut app, 4.0);
    assert!(app.world().get::<planet::bubble::Frozen>(id).is_none());
    assert!(origin.body(app.world().get::<Transform>(id).unwrap().translation).length() < start.length() - 2.0, "fell onto the built ground");
}

#[test]
fn the_player_hovers_until_the_ground_under_them_is_built() {
    let (mut app, sphere, origin) = streaming_app(4);
    let spawn = origin.body(player(&mut app).0);
    for _ in 0..8 {
        app.update();
        assert!(origin.body(player(&mut app).0).distance(spawn) < 0.01, "held in place with no ground");
    }
    settle(&mut app);
    run(&mut app, 1.0);
    let body = origin.body(player(&mut app).0);
    let ground = app.world().resource::<planet::Chunks>().ground(&sphere, body).point;
    assert!((body.length() - ground.length() - 0.9).abs() < 0.05, "standing on the built ground");
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test bubble frozen hovers`
Expected: FAIL to compile.

- [ ] **Step 3: Implement `src/planet/bubble.rs`** and register `solidify`, `freeze` and `hold_player` in `add_streaming`. `apply` (Task 8) now adds a collider only when inside the bubble and `solid` tracks exactly the chunks with colliders.

- [ ] **Step 4: Run the suite**

Run: `cargo test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planet/bubble.rs src/planet/mod.rs src/tests.rs
git commit -m "Physics bubble: solid ground and awake bodies only within 400 m of the player"
```

### Task 10: The sliding origin

**Files:**
- Create: `src/planet/origin.rs`
- Modify: `src/planet/mod.rs` (`pub mod origin;`, `add_streaming` registers `rebase` first in `FixedUpdate`), `src/abilities.rs` (`Hook.anchor` in body coordinates)
- Test: unit test in `src/planet/origin.rs`, one in `src/tests.rs`

**Interfaces:**
- Consumes: `Origin`, `TerrainTuning.origin_step`, `QUANTUM`, `Player::shift`.
- Produces:
  - `pub fn rebase_delta(player_world: Vec3, step: f32, quantum: f32) -> Option<Vec3>`: `None` while `player_world.length() <= step`, else `Some(player_world rounded per component to a multiple of quantum)`.
  - `pub fn rebase(...)` in `FixedUpdate`, before `ControllerSet`, `VehicleSet`, `TargetSet`, `freeze`, `hold_player` and `gravitate`: on `Some(delta)`: `origin.offset += delta`; every `Transform` on an entity without `ChildOf` gets `translation -= delta`; every Avian `Position` gets `0 -= delta`; `Player::shift(delta)`. Entities carrying `TransformInterpolation` (vehicles; none on the moon) get their easing state shifted in the next plan, which adds `bevy_transform_interpolation` as a direct dependency for the purpose; say so in the system's doc comment.
  - `pub fn add_rebase(app: &mut App)`, called by `add_streaming`.
  - `abilities::Hook { pub anchor: Vec3 /* body coordinates */, pub rope: f32 }`; `grapple_tick` and `draw_rope` take `Res<Origin>` and use `origin.world(hook.anchor)`.

- [ ] **Step 1: Write the failing tests.** In `src/planet/origin.rs`:

```rust
#[test]
fn rebase_delta_quantizes_and_triggers_past_the_step() {
    assert_eq!(rebase_delta(Vec3::new(1500.0, 0.0, 1000.0), 2000.0, 36.0), None);
    let d = rebase_delta(Vec3::new(2100.0, -50.0, 10.0), 2000.0, 36.0).unwrap();
    for c in d.to_array() { assert_eq!(c.rem_euclid(36.0), 0.0); }
    assert!(d.distance(Vec3::new(2100.0, -50.0, 10.0)) < 36.0);
}
```

In `src/tests.rs`:

```rust
#[test]
fn rebase_keeps_the_world_together() {
    let (mut app, sphere, origin0) = streaming_app(4);
    settle(&mut app);
    let body_of = |app: &App, id: Entity| app.world().resource::<Origin>().body(app.world().get::<Transform>(id).unwrap().translation);
    let crate_id = app.world_mut().spawn((RigidBody::Dynamic, Collider::cuboid(1.0, 1.0, 1.0), Mass(40.0), Transform::from_translation(origin0.world(sphere.surface_point(Vec3::X) + Vec3::X * 3.0)))).id();
    let block_id = app.world_mut().spawn((RigidBody::Static, Collider::cuboid(2.0, 2.0, 2.0), Transform::from_translation(origin0.world(sphere.surface_point(Vec3::X) + Vec3::Z * 6.0)))).id();
    run(&mut app, 2.0);
    let anchor = sphere.surface_point(Vec3::X) + Vec3::X * 12.0;
    app.world_mut().resource_mut::<GrappleState>().hook = Some(Hook { anchor, rope: 12.0 });
    let (crate_before, block_before) = (body_of(&app, crate_id), body_of(&app, block_id));
    // Teleport-walk 2.5 km in 100 m hops; the crate and block fall out of the bubble and freeze where they are.
    let mut target = Vec3::ZERO;
    for i in 1..=25 {
        let dir = Quat::from_rotation_y(-(i as f32) * 100.0 / 2000.0) * Vec3::X;
        target = sphere.surface_point(dir) + dir;
        let o = *app.world().resource::<Origin>();
        set_player(&mut app, o.world(target), Vec3::ZERO);
        app.update();
    }
    let o = *app.world().resource::<Origin>();
    assert_ne!(o.offset, origin0.offset, "a rebase happened");
    let (pos, _, _) = player(&mut app);
    assert!(pos.length() < 2100.0, "the player is near the new origin");
    assert!(o.body(pos).distance(target) < 0.5, "player body coordinates survived the shift");
    assert!(body_of(&app, crate_id).distance(crate_before) < 1e-3 && body_of(&app, block_id).distance(block_before) < 1e-3);
    assert_eq!(app.world().resource::<GrappleState>().hook.map(|h| h.anchor), Some(anchor), "body-coordinate anchor untouched");
    let p = app.world_mut().query::<(&Player, &Transform)>().single(app.world()).unwrap();
    assert!(p.0.prev_pos.distance(p.1.translation) < 2.0, "no camera jump");
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cargo test rebase`
Expected: FAIL to compile.

- [ ] **Step 3: Implement `src/planet/origin.rs`**, wire `add_rebase` into `add_streaming`, convert the grapple anchor.

- [ ] **Step 4: Run the suite**

Run: `cargo test`
Expected: PASS (the grapple tests still pass with the identity origin).

- [ ] **Step 5: Commit**

```bash
git add src/planet/origin.rs src/planet/mod.rs src/abilities.rs src/tests.rs
git commit -m "Sliding origin: the world re-centres on the player every 2 km in 36 m steps"
```

### Task 11: The debug moon level

**Files:**
- Modify: `src/main.rs` (`level_plugin`), `src/planet/mod.rs` (`PlanetPlugin::build`, `seed_ground`), `README.md` (a "Debug moon" paragraph under Island)
- Test: manual run and screenshot; `cargo test`

**Interfaces:**
- Consumes: everything above; `system::System::load`.
- Produces:
  - `RUST_REGIME_LEVEL=moon` adds `planet::PlanetPlugin { body: "moon".into() }` in place of the terrain, look, vegetation and world plugins; the arena and island paths are unchanged.
  - `PlanetPlugin::build`: loads the body (panics naming the id if missing), inserts `Surface::Sphere`, `Gravity(Vec3::ZERO)`, `ClearColor(Color::srgb(0.02, 0.02, 0.05))`, `GlobalAmbientLight` at brightness 300, `Origin::at(spawn, QUANTUM)` and `WorldBounds { spawn, kill_altitude: -2.0 }` where `at = sphere.surface_point(dir(lat 20°, lon 0°))` and `spawn = at + frame * Vec3::new(0.0, COURSE_DECK + 0.95, 2.0)`; calls `add_streaming`; adds `gravitate` to `FixedUpdate` before `ControllerSet`; `Startup` (exclusive): `seed_ground` builds the finest leaf under `at` and every finest leaf within two arcs of it synchronously with `build_chunk`, spawning them exactly as `apply` would, with colliders, so the player and the course have ground on the first tick; then a `DirectionalLight` (10 000 lux, shadows, cascades to 500 m, looking along `-(dir + Vec3::X).normalize()`) and `spawn_course(world, &surface, &origin, at)`.
  - `main.rs` `dev_screenshot`: when `RUST_REGIME_SCREENSHOT_VIEW` names a spot and there is no `Heightmap`, leave the player where they are (the spot is meaningless on a sphere).

- [ ] **Step 1: Wire the level** per the Interfaces block.

- [ ] **Step 2: Run the moon**

Run: `RUST_REGIME_LEVEL=moon cargo run --release`
Expected: you stand on the course deck over grey rolling ground with a visibly curved horizon; stepping off the deck lands you on terrain; walking in any direction for a minute never shows a hole or a seam you can fall through; the step, wall run, mantle and slide work on the course.

- [ ] **Step 3: Screenshot**

Run: `RUST_REGIME_LEVEL=moon RUST_REGIME_SCREENSHOT=screenshots/moon-course.png RUST_REGIME_SCREENSHOT_VIEW=2,200 cargo run --release`
Expected: `screenshots/moon-course.png` shows the course and the horizon curve.

- [ ] **Step 4: Measure and record.** Log at info level from `apply` the chunk build time (mean and max over the first 200 chunks) and the chunks applied per second while running east for 30 s, once at `terrain.cell = 0.5` and once at `= 1`. Put both pairs of numbers in the README paragraph and the commit body; the next plan reads them.

- [ ] **Step 5: Full suite and clippy**

Run: `cargo test && cargo clippy --all-targets`
Expected: all green, no new warnings.

- [ ] **Step 6: Commit**

```bash
git add src/main.rs src/planet/mod.rs README.md screenshots/moon-course.png
git commit -m "Debug moon level: RUST_REGIME_LEVEL=moon drops you on a 2 km sphere with a parkour course"
```
