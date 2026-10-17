# Island Terrain (stage 1, step 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 4 km seeded island you can run around on, with water that respawns you and fog at the coast, as the default level, with the arena kept for tests.

**Architecture:** A pure `Heightmap` resource (noise times island mask, plus flat stamps) is generated at plugin build time. A `TerrainPlugin` turns it into 32 by 32 chunk entities, each a static body with a mesh and an Avian heightfield collider built from the same samples, plus a water plane, a directional light and camera fog. A small `WorldBounds` resource replaces the hardcoded spawn point and kill height in the controller so both levels share one respawn path.

**Tech Stack:** Rust 2024, Bevy 0.19, Avian3d 0.7, `fastnoise-lite` (new, MIT, no deps), existing `tuning.toml` loader and headless test harness in `src/tests.rs`.

**Spec:** `docs/superpowers/specs/2026-10-17-island-hub-design.md` (sections World, Tuning, Files, Build order step 1, Tests, Risks).

## Global Constraints

- Free assets and crates only; the only new dependency is `fastnoise-lite`.
- Deterministic from `island.seed`; same seed gives the identical heightmap.
- No streaming, no LOD: `size = 4096`, `cell = 4`, 1025 by 1025 samples, 32 by 32 chunks of 32 cells.
- Arena stays reachable with `RUST_REGIME_LEVEL=arena`; all 17 existing tests keep passing.
- Every number lives in `tuning.toml` under `[island]` and reloads with F5 where it can (water and fog colors are not tunable; terrain is generated once at startup).
- Build in a copy outside `/mnt/project-files` with `CARGO_TARGET_DIR` outside the mount; use `cargo test --release`. Sync source back to the mount and repackage `rust-regime-linux.tar.gz` and `rust-regime.zip` at the end.

## Review Focus

1. A `tuning.toml` with `cell` that does not divide `size` evenly: the heightmap must still have `size / cell + 1` samples per side and chunking must not index past the end. Test in Task 1.
2. `height_at` outside the island (beyond ±size/2): must clamp to the edge sample, never panic. Test in Task 1.
3. Player spawning inside terrain: spawn height must come from `height_at` plus the hull half height, not a constant. Test in Task 5.
4. Heightfield orientation: parry's heightfield is centered on its entity and indexes rows along z and columns along x; a swap or a half-cell offset puts you walking through hills. Task 3's agreement test checks random points, including off-diagonal ones.
5. Respawn after water: `Player` fields (velocity, state, cooldowns) must reset exactly like the arena kill plane does today. Task 5 reuses the existing reset branch.

---

### Task 1: `[island]` tuning table and heightmap generation

**Files:**
- Modify: `src/tuning.rs` (add `Island` struct and `pub island: Island` field with defaults)
- Modify: `tuning.toml` (append the `[island]` table from the spec)
- Modify: `Cargo.toml` (add `fastnoise-lite = "1"`)
- Create: `src/terrain.rs`
- Modify: `src/main.rs` (`mod terrain;`)
- Test: `src/tests.rs`

**Interfaces:**
- Produces: `tuning::Island { seed: u32, size: f32, cell: f32, core: f32, height: f32, water_level: f32 }`, defaults `7, 4096.0, 4.0, 1500.0, 180.0, 0.0`.
- Produces: `terrain::Heightmap { pub size: f32, pub cell: f32, pub n: usize, pub heights: Vec<f32> }` (row-major, index `z * n + x`, sample `(x, z)` is at world `(-size/2 + x*cell, -size/2 + z*cell)`), `terrain::generate(island: &Island) -> Heightmap`, `Heightmap::height_at(&self, x: f32, z: f32) -> f32` (bilinear, clamped to the edge), `Heightmap::normal_at(&self, x: f32, z: f32) -> Vec3`.

- [ ] **Step 1: Write the failing tests** in `src/tests.rs`

```rust
#[test]
fn heightmap_is_deterministic_and_island_shaped() {
    let island = Island::default();
    let a = terrain::generate(&island);
    let b = terrain::generate(&island);
    assert_eq!(a.heights, b.heights);
    let other = terrain::generate(&Island { seed: 8, ..island.clone() });
    assert_ne!(a.heights, other.heights);
    assert_eq!(a.n, 1025);
    assert!(a.height_at(0.0, 0.0) > island.water_level + 5.0, "center is land");
    let half = island.size / 2.0;
    for (x, z) in [(-half, -half), (half, -half), (-half, half), (half, half), (0.0, half), (half, 0.0)] {
        assert!(a.height_at(x, z) < island.water_level - 1.0, "coast is under water at {x},{z}");
    }
    let peak = a.heights.iter().cloned().fold(f32::MIN, f32::max);
    assert!(peak > 0.6 * island.height && peak <= island.height);
}

#[test]
fn heightmap_handles_odd_sizes_and_out_of_range() {
    let hm = terrain::generate(&Island { size: 100.0, cell: 3.0, ..Island::default() });
    assert_eq!(hm.n, 100 / 3 + 1);
    assert_eq!(hm.height_at(1e6, -1e6), hm.height_at(hm.size / 2.0, -hm.size / 2.0));
    let n = hm.normal_at(0.0, 0.0);
    assert!((n.length() - 1.0).abs() < 1e-3 && n.y > 0.0);
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cargo test --release heightmap`
Expected: compile error, `terrain` and `Island` not found.

- [ ] **Step 3: Add the crate, the `Island` table and `terrain::generate`**

`Island` derives `Deserialize, Clone, Debug` with `#[serde(default)]` like `Gun`. In `generate`: `n = (size / cell) as usize + 1`; one `FastNoiseLite` with `set_seed(seed as i32)`, `NoiseType::OpenSimplex2`, `FractalType::FBm`, 5 octaves, frequency `2.0 / size`; sample `h = noise(x, z)` in [-1, 1] mapped to [0, 1]; island mask `m = smoothstep(1.0, 0.55, r / (size / 2))` with `r` the distance from center; `height = (h * m) * island.height - (1.0 - m) * 40.0` so the coast dips below water. `height_at` clamps `x, z` to `[-size/2, size/2]`, then bilinear between the four surrounding samples. `normal_at` is the cross product of central differences one cell apart.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cargo test --release heightmap`
Expected: 2 passed. Adjust the mask edge or the fractal gain, not the tests, if the peak or coast assertions miss.

- [ ] **Step 5: Commit**

```bash
git add Cargo.toml Cargo.lock src/terrain.rs src/tuning.rs src/main.rs src/tests.rs tuning.toml
git commit -m "feat: seeded island heightmap and [island] tuning table"
```

### Task 2: Flat stamps for site pads

**Files:**
- Modify: `src/terrain.rs`
- Test: `src/tests.rs`

**Interfaces:**
- Produces: `Heightmap::stamp_flat(&mut self, center: Vec2, radius: f32, height: f32, blend: f32)`: every sample within `radius` of `center` becomes exactly `height`; between `radius` and `radius + blend` it lerps smoothly to the original.
- Produces: `terrain::generate` ends by calling `stamp_flat(Vec2::ZERO, 40.0, generate_height_at_center, 30.0)` for the spawn pad (sites come in a later plan and add their own stamps).

- [ ] **Step 1: Write the failing test**

```rust
#[test]
fn stamp_flattens_a_pad() {
    let mut hm = terrain::generate(&Island::default());
    hm.stamp_flat(Vec2::new(200.0, -300.0), 30.0, 50.0, 20.0);
    for (dx, dz) in [(0.0, 0.0), (29.0, 0.0), (0.0, -29.0), (20.0, 20.0)] {
        assert!((hm.height_at(200.0 + dx, -300.0 + dz) - 50.0).abs() < 0.05);
    }
    let outside = hm.height_at(200.0 + 60.0, -300.0);
    assert!((outside - 50.0).abs() > 0.05 || outside == 50.0, "unaffected beyond radius + blend");
    assert!((hm.height_at(0.0, 0.0) - hm.height_at(20.0, 20.0)).abs() < 0.05, "spawn pad is flat");
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cargo test --release stamp_flattens`
Expected: compile error, no method `stamp_flat`.

- [ ] **Step 3: Implement `stamp_flat`** in `src/terrain.rs` and call it at the end of `generate` for the spawn pad.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo test --release stamp_flattens heightmap`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/terrain.rs src/tests.rs
git commit -m "feat: flat stamps on the heightmap, spawn pad at the island center"
```

### Task 3: Chunk colliders that agree with `height_at`

**Files:**
- Modify: `src/terrain.rs`
- Test: `src/tests.rs`

**Interfaces:**
- Produces: `pub const CHUNK: usize = 32` (cells per chunk side), `Heightmap::chunks(&self) -> usize` (chunks per side, `(n - 1).div_ceil(CHUNK)`), `terrain::chunk_collider(hm: &Heightmap, cx: usize, cz: usize) -> (Collider, Transform)`: an Avian `Collider::heightfield` over the chunk's `(CHUNK + 1)` by `(CHUNK + 1)` samples (fewer on the last chunk when `n - 1` is not a multiple of `CHUNK`), with a transform that places it so its samples land on the world positions in Task 1's layout.
- Produces: `terrain::spawn_colliders(world: &mut World, hm: &Heightmap)` for tests: spawns one `(RigidBody::Static, Collider, Transform)` per chunk.

- [ ] **Step 1: Write the failing test**

```rust
#[test]
fn colliders_match_heightmap() {
    let island = Island { size: 512.0, ..Island::default() };
    let hm = terrain::generate(&island);
    let mut app = make_app(Tuning::default());
    terrain::spawn_colliders(app.world_mut(), &hm);
    app.update();
    let mut query = app.world_mut().query::<&SpatialQueryPipeline>();
    let pipeline = query.single(app.world()).unwrap();
    for (x, z) in [(0.0, 0.0), (100.0, -37.0), (-211.0, 180.0), (255.0, 3.0), (-3.0, -250.0), (130.0, 130.0)] {
        let hit = pipeline
            .cast_ray(Vec3::new(x, 400.0, z), Dir3::NEG_Y, 800.0, true, &SpatialQueryFilter::default())
            .expect("ray hits terrain");
        let got = 400.0 - hit.distance;
        assert!((got - hm.height_at(x, z)).abs() < 0.1, "at {x},{z}: collider {got} vs heightmap {}", hm.height_at(x, z));
    }
}
```

Note: `make_app` already spawns a 200 m floor at y = -0.5; use `size = 512` and points inside it only where the island is above 0, or remove that floor for this test by spawning the island with a `Transform` 1000 m up and adjusting the ray. Pick the simplest that keeps the asserts meaningful and say which in the test.

- [ ] **Step 2: Run it to verify it fails**

Run: `cargo test --release colliders_match`
Expected: compile error, no `chunk_collider` / `spawn_colliders`.

- [ ] **Step 3: Implement `chunk_collider` and `spawn_colliders`**

Parry heightfields are centered on the entity: a field of `rows` by `cols` samples with `scale = Vec3::new(width, 1.0, depth)` spans `x` in `[-width/2, width/2]` and `z` in `[-depth/2, depth/2]`, rows along z, columns along x. Translate each chunk to its center. Check the row/column order against the agreement test rather than the docs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo test --release colliders_match`
Expected: 1 passed, all six points within 0.1 m.

- [ ] **Step 5: Commit**

```bash
git add src/terrain.rs src/tests.rs
git commit -m "feat: per-chunk heightfield colliders matching the heightmap"
```

### Task 4: Terrain meshes, water, light, fog, and level selection

**Files:**
- Modify: `src/terrain.rs` (`TerrainPlugin`, `chunk_mesh`, `spawn_terrain`, `add_fog`)
- Modify: `src/main.rs` (pick level plugin from `RUST_REGIME_LEVEL`)
- Modify: `README.md` (Level section: island default, `RUST_REGIME_LEVEL=arena`)

**Interfaces:**
- Consumes: `Heightmap`, `chunk_collider`, `Island` from Tasks 1 to 3; `PlayerCamera` from `src/camera.rs`.
- Produces: `terrain::TerrainPlugin`: in `build`, generates the heightmap from `tuning::load().island`, logs generation time, sample count and chunk count with `info!`, inserts `Heightmap` as a resource, and adds `spawn_terrain` to `Startup` and `add_fog` to `PostStartup`.
- Produces: `terrain::chunk_mesh(hm: &Heightmap, cx: usize, cz: usize) -> Mesh`: indexed `TriangleList` with `ATTRIBUTE_POSITION` (chunk-local), `ATTRIBUTE_NORMAL` from `normal_at`, `ATTRIBUTE_COLOR` by height and slope: sand `(0.76, 0.70, 0.50)` below `water_level + 3`, grass `(0.33, 0.52, 0.25)`, rock `(0.45, 0.42, 0.40)` where `normal.y < 0.75`, snow `(0.92, 0.92, 0.95)` above `0.8 * height`.

- [ ] **Step 1: Implement `chunk_mesh`, `spawn_terrain`, `add_fog`, `TerrainPlugin`**

`spawn_terrain` spawns, per chunk, `(Name, Mesh3d, MeshMaterial3d<StandardMaterial>, Transform, RigidBody::Static, Collider)` with one shared white `StandardMaterial { perceptual_roughness: 1.0, ..}`; a water entity `Mesh3d(Plane3d::new(Vec3::Y, Vec2::splat(size / 2.0)))` at `y = water_level` with `base_color: Color::srgba(0.15, 0.35, 0.55, 0.85)`, `alpha_mode: AlphaMode::Blend`, no collider; a `DirectionalLight { illuminance: 10_000.0, shadow_maps_enabled: true, ..}` with the same `RenderLayers` as the arena light and `CascadeShadowConfigBuilder { num_cascades: 4, maximum_distance: 400.0, first_cascade_far_bound: 20.0, ..}`; `ClearColor(Color::srgb(0.55, 0.7, 0.85))`. `add_fog` inserts `DistanceFog { color: Color::srgb(0.55, 0.7, 0.85), falloff: FogFalloff::Linear { start: 800.0, end: 2500.0 }, ..}` on the `PlayerCamera` entity.

- [ ] **Step 2: Level selection in `main.rs`**

Read `RUST_REGIME_LEVEL`; `"arena"` adds `level::LevelPlugin`, anything else (and unset) adds `terrain::TerrainPlugin`. `targets::TargetsPlugin` stays in both.

- [ ] **Step 3: Build and check it compiles and the arena still runs**

Run: `cargo build --release && cargo test --release`
Expected: build OK; all tests pass (17 old + 4 new).

- [ ] **Step 4: Screenshot the island headless**

Run (from the build dir, assets next to the binary, per project memory): `xvfb-run -a env RUST_REGIME_SCREENSHOT=island.png RUST_REGIME_SCREENSHOT_VIEW="2,0,0,0,-5" WGPU_BACKEND=vulkan VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./rust-regime`
Expected: a PNG showing terrain, water at the horizon and fog; the log line with generation time (expect well under 1 s) and 1024 chunks. Save the PNG to `/mnt/project-files/screenshots/island-terrain.png`.

- [ ] **Step 5: Commit**

```bash
git add src/terrain.rs src/main.rs README.md
git commit -m "feat: island terrain level with water, fog and cascaded shadows; RUST_REGIME_LEVEL picks arena"
```

### Task 5: Shared spawn point and kill plane (`WorldBounds`)

**Files:**
- Modify: `src/controller.rs:15` (`SPAWN`), `:93-101` (`spawn_player`), `:299-303` (reset branch)
- Modify: `src/terrain.rs` (`TerrainPlugin::build` inserts `WorldBounds`)
- Modify: `src/main.rs` (`dev_screenshot` places the player at `height_at + 1` when x,z are given)
- Test: `src/tests.rs`

**Interfaces:**
- Produces: `controller::WorldBounds { pub spawn: Vec3, pub kill_y: f32 }`, `Resource`, `Default = { spawn: SPAWN, kill_y: -30.0 }`, `init_resource`'d by `ControllerPlugin` so the arena and the tests are unchanged; `TerrainPlugin` does `insert_resource(WorldBounds { spawn: Vec3::new(0.0, hm.height_at(0.0, 0.0) + 1.0, 0.0), kill_y: island.water_level - 2.0 })` (an inserted resource wins over a later `init_resource`).
- `spawn_player` and the reset branch read `WorldBounds` instead of `SPAWN` and `-30.0`.

- [ ] **Step 1: Write the failing test**

```rust
#[test]
fn falling_in_water_respawns_at_world_bounds() {
    let mut app = make_app(Tuning::default());
    app.insert_resource(controller::WorldBounds { spawn: Vec3::new(5.0, 30.0, -5.0), kill_y: 10.0 });
    set_player(&mut app, Vec3::new(50.0, 9.0, 50.0), Vec3::new(3.0, -5.0, 0.0));
    run(&mut app, 0.1);
    let (pos, vel, state) = player(&mut app);
    assert!((pos.xz() - Vec2::new(5.0, -5.0)).length() < 0.5 && pos.y > 25.0, "respawned at spawn, got {pos}");
    assert!(vel.length() < 1.0, "velocity reset, got {vel}");
    assert_eq!(state, MoveState::Air);
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cargo test --release falling_in_water`
Expected: compile error, no `WorldBounds`.

- [ ] **Step 3: Implement `WorldBounds`** and switch the three controller sites and the screenshot helper to it.

- [ ] **Step 4: Run the whole suite**

Run: `cargo test --release`
Expected: 22 passed (17 old, 5 new), the arena tests untouched.

- [ ] **Step 5: Commit**

```bash
git add src/controller.rs src/terrain.rs src/main.rs src/tests.rs
git commit -m "feat: WorldBounds resource for spawn point and kill plane; island spawns on the pad"
```

### Task 6: Package and deliver

**Files:**
- Modify: `/mnt/project-files/rust-regime/` (sync source, docs, README)
- Modify: `/mnt/project-files/rust-regime-linux.tar.gz`, `/mnt/project-files/rust-regime.zip`

- [ ] **Step 1: Sync the source tree back to the mount** (`rsync -a --exclude target --exclude .git` from the build copy), then re-read `Cargo.toml` and `src/terrain.rs` from the mount to confirm.

- [ ] **Step 2: Repackage** the stripped release binary, `run.sh`, `tuning.toml` and `assets/` into `rust-regime-linux.tar.gz`, and the source into `rust-regime.zip`, the same layout as the current archives (inspect them with `tar tzf` and `unzip -l` first).

- [ ] **Step 3: Verify** `tar tzf` lists `rust-regime`, `run.sh`, `tuning.toml`, `assets/models/...`; `unzip -l` lists `src/terrain.rs` and the spec and plan.
