# Economy stage B (job boards) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every base has a job board with three offers a game day (courier, cull, supply run), you carry up to two jobs, they expire, and Vantage buys scrap.

**Architecture:** A new `src/solar/board.rs` owns the job model, the seeded generator, the day clock, expiry, cull progress and hand-ins. `Save` gets `contracts: Vec<Contract>`, `boards`, `day`, `day_clock`, `seed`, with the old `contract` migrated on load. A code-spawned `Board` station stands just inside every base's door (no `bases.toml` change: another thread is reworking the base kits), and Vantage's courier desk opens the same board. A new menu panel, `Panel::Board`, shows the offers and your jobs.

**Tech Stack:** Rust, Bevy 0.19, serde/toml; headless tests in `src/tests.rs`.

**Spec:** `docs/superpowers/specs/2026-10-29-economy-design.md`, "The boards" and "Staging: B".

## Global Constraints

- Every number in `[economy]` (`tuning.toml` and `Economy::default()` equal; the existing test checks it).
- Old saves load: `[contract] to, pay` becomes one courier job from Vantage with no expiry.
- The board is generated once per game day for all four bases and stored in the save, so its pay does not drift while the worlds move.
- No `bases.toml` or `tools/bases` edits.
- Commits: `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`.

## Decisions the spec left open (made here)

- **Courier pay:** `courier_base 250 + courier_per_km 3 × km` between the two worlds' centres at generation, `× danger_pay 1.5` if the destination's faction is below 0 with you, rounded to $10. Haven to Bastion (168 km) pays about $750. The spec's "per 1000 km" unit was wrong for a system 70 to 170 km across.
- **Supply runs** hand in at the issuing base's board, pay into the bank, and raise standing like a delivery (+10, through the existing `Delivered` message) rather than a separate +5. The Yard gets none until stage C's stockpile.
- **Who buys scrap:** `scrap_buyers = { yard = 1.0, outpost = 0.7 }` by base id, sold from the board (and from the Yard's parts rack, as now).
- **No abandon button.** A job you cannot finish expires at the end of the next day.

## Review Focus

- **Two jobs held, a third taken:** refused with a note, the offer stays. Task 3.
- **Day rollover with a parcel aboard past its due day:** dropped, -5 standing with its issuer, once. Task 2.
- **Cull kills by another ship or of a non-raider:** do not count. Task 4.
- **Supply hand-in short of scrap:** refused, nothing taken. Task 3.
- **Shot down holding a cull and a parcel:** the parcel goes (with its -5), the cull stays. Task 4.

---

### Task 1: The job model, the save and migration

**Files:** Create `src/solar/board.rs`; modify `src/save.rs`, `src/solar/station.rs` (`Contract` moves to `board`, re-exported), `src/solar/mod.rs`, `src/tuning.rs`, `tuning.toml`.

**Interfaces (produces):**
- `pub enum Job { Courier { to: String }, Cull { need: u32, got: u32 }, Supply { need: u32 } }` (serde, `rename_all = "lowercase"`).
- `pub struct Contract { pub job: Job, pub from: String, pub pay: u32, pub due: Option<u32> }` (`from` = issuing base id, `due` = last game day it can be done; `None` never expires).
- `Save`: `contracts: Vec<Contract>`, `boards: BTreeMap<String, Vec<Contract>>`, `board_day: Option<u32>`, `day: u32`, `day_clock: f32`, `seed: u64`; `contract` stays only as a `skip_serializing` legacy field of type `OldContract { to, pay }`, moved into `contracts` by `Save::migrate()`, called from `SaveFile::load`.
- `Economy`: drop `courier_step`; add `courier_per_km: f32 = 3.0`, `danger_pay: f32 = 1.5`, `cull_per_kill: u32 = 50`, `cull_kills: [u32; 2] = [4, 8]`, `supply_scrap: [u32; 2] = [20, 40]`, `supply_markup: f32 = 1.3`, `supply_chance: f32 = 0.5`, `scrap_buyers: BTreeMap<String, f32> = {yard: 1.0, outpost: 0.7}`, `jobs: usize = 2`, `drop_standing: i32 = -5`, `day: f32 = 2880.0`.

- [ ] Tests: `an_old_save_with_a_parcel_loads_it_as_a_courier_job` (toml `banked = 5\n[contract]\nto = "yard"\npay = 400\n` → `contracts == [Contract { job: Courier { to: "yard" }, from: "outpost", pay: 400, due: None }]`, and writing it back has no `[contract]`); `contracts_round_trip` for all three kinds.
- [ ] Implement, switch every `save.contract` user to `contracts` (station deliver, loss, waypoint, flight readout, Contracts screen) with behaviour unchanged for couriers. `cargo test` passes. Commit.

### Task 2: The generator, the day clock and expiry

**Interfaces (produces):**
- `board::offers(base: usize, bases: &Bases, day: u32, seed: u64, km: impl Fn(&str, &str) -> f32, save: &Save, e: &Economy, t: &ShipCombat) -> Vec<Contract>`: a courier (to a random other base, pay above), a cull (`need` in `cull_kills`, `pay = cull_per_kill × need`), and with `supply_chance` a supply run unless the base is the Yard (`need` in `supply_scrap`, `pay = round(scrap_value × 0.7 × supply_markup × need)`); every offer `due = Some(day + 1)`. Seeded with `Rng(hash(seed, day, base id) | 1)` (`enemy::Rng`).
- System `tick_day` (FixedUpdate): `day_clock += dt`; past `e.day` → `day += 1`, `day_clock -= e.day`, then `expire`.
- `board::expire(save, e, t) -> Vec<Contract>`: removes jobs with `due < day`, couriers cost `drop_standing` with the issuer's faction (`standing::shift`).
- System `restock`: when `board_day != Some(day)`, sets `seed` if 0 (clock), regenerates `boards` for every base from `Solar` distances (km between body centres), sets `board_day`.

- [ ] Tests: same inputs give the same offers; another day or seed differs; the courier never targets its own base; the Yard never offers supply; pay matches the formulas (danger ×1.5 when the destination's faction is below 0); `expire` drops a past-due parcel with -5 once and keeps a due-today one; in `system_app`, `run(e.day + 1)` advances `day` to 1 and `board_day` follows with four boards.
- [ ] Implement. `cargo test`. Commit.

### Task 3: The board station and screen

**Interfaces:**
- `StationKind::Board`; `base.rs` also spawns a `Board` station at `door + (0, 0, -1.5)` in the base frame for every base. `Contracts` (Vantage's desk) behaves as `Board`.
- Using it (not hunted, as now: Board and Contracts always serve) sets `menu::Board(Some(base))` and pauses; `enter_menu` opens `Panel::Board` with `menu.board = base`. Back returns to play.
- `board::take(save, base_id, i, e) -> Result<Contract, Refusal>` (`Refusal::Full` at `e.jobs` jobs); `board::hand_in(save, base_id, e) -> Option<(u32, u32)>` hands in the first supply job issued here if the hold has its `need` (scrap and pay), banking the pay.
- Rows: `Row::Offer(i)` (select takes), `Row::Job(i)` (select at the issuing base hands in a supply job), `Row::Sell` when the base is a scrap buyer (price `scrap_value × buyers[base]`, standing-adjusted via `standing::buys`), BACK. `economy::sell_scrap` takes the per-scrap value.
- Labels: `COURIER TO THE RELIQUARY  $750` / note `Bastion, 168 km. Due by the end of tomorrow.` (+ ` Danger pay.`); `CULL 6 RAIDERS  $300` / `Any raiders your ship shoots down. Bounties pay too.`; `SUPPLY 30 SCRAP  $140` / `Bring it to this board.`; jobs show `ACTIVE`, `2/6`, `HAND IN`.

- [ ] Tests: `the_board_stands_inside_every_bases_door` (four `Board` stations, each within 3 m of its door); in `counter_app`, standing at the Roost's board and pressing E opens `Panel::Board`; Enter on the first row takes the courier (one job, two offers left), the third take is refused at two jobs; `hand_in` with too little scrap refuses and takes nothing, with enough consumes it and banks the pay; `RUST_REGIME_MENU=board` opens the Roost's board for screenshots.
- [ ] Implement. `cargo test`. Commit.

### Task 4: Culls, deaths, and the HUD

- System `cull` reads `ShipDestroyed`: a raider shot down by the flown ship advances every cull job; the one that reaches `need` pays `pay` into the pocket, leaves the list and says `CULL DONE +$300` on the bounty line.
- `loss::lose`: drops every courier job (each costs `drop_standing` with its issuer), keeps culls and supply runs; `Loss.parcel` becomes `parcels: Vec<Contract>`; the card names one parcel or says `2 parcels`.
- Flight readout and Pause > Contracts list each job; the waypoint says `DELIVER HERE +$750` for every courier to that base and `HAND IN 30 SCRAP` over a supply run's base.

- [ ] Tests: a raider kill by the flown ship counts, a patrol kill or another ship's kill does not, the sixth of six pays once into the pocket; shot down with a parcel and a cull keeps the cull and costs -5 with the parcel's issuer; the readout line for each kind.
- [ ] Implement. `cargo test`, clippy on touched files, README "Money" section, screenshots (`RUST_REGIME_MENU=board`, the readout with jobs) into `screenshots/economy/`, PR for Q's merge.
