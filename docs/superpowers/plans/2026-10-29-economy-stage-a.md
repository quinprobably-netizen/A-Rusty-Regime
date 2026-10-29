# Economy stage A (the ledger) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Money earned in the field sits at risk until you walk up to a base; being shot down costs the pocket, the hold and the parcel plus a rebuy fee, never a share of the bank; scrap has a hold cap and sells at the Yard; hulls are repaired for money; every price is in `tuning.toml [economy]`.

**Architecture:** A new `src/solar/economy.rs` holds the ledger's pure functions (hold cap, banking, ship value, rebuy fee, repair cost, scrap sale) and two systems (bank and repair at a base door). A new `Economy` tuning section replaces the hard-coded prices in `quartermaster.rs` and `station.rs` and the `bank_loss` field. `loss.rs`, `salvage.rs`, `hud.rs` and the parts rack menu call into it.

**Tech Stack:** Rust, Bevy 0.19, Avian 0.7, serde/toml. Headless tests in `src/tests.rs` (`cargo test`).

**Spec:** `docs/superpowers/specs/2026-10-29-economy-design.md`, sections "The model" and "Staging: A". Q chose pocket-at-risk on 2026-10-29.

## Global Constraints

- Every new save field is `#[serde(default)]` through the existing `#[serde(default)]` on `Save`; an old `save.toml` must load.
- Every number lives in `[economy]` in `tuning.toml` with the same default in `tuning.rs` (tests use the defaults).
- The Roost (Deserters) charges list price, as today: `standing::price` is unchanged for factions that do not move. (Spec deviation, simpler: the spec's "Roost at Friendly price" would have cut every gun 15% for no gameplay reason.)
- Selling scrap is at the Yard's parts rack only in stage A. Vantage buys scrap from stage B, when its desk becomes a board screen; `bases.toml` is generated and another thread is editing the base kits, so no new stations here.
- A dropped parcel costs no standing in stage A: `Contract` has no issuer until stage B.
- Commits: `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`.

## Review Focus

- **Pocket with a Hunted base:** walking to the door of a faction that hunts you must not bank or repair. Test in Task 2.
- **Rebuy with a poor bank:** a fee larger than the bank takes the bank to 0, never wraps. Test in Task 4.
- **A scrap pickup larger than the room left:** takes what fits and leaves the rest floating, not lost. Test in Task 3.
- **Repair with too little money:** repairs what the bank affords, never charges more than it has. Test in Task 5.
- **Banking every frame:** standing in the doorway must bank once and repair once, not spam the note. Test in Task 2.

---

### Task 1: `[economy]` tuning, prices out of the code

**Files:**
- Modify: `src/tuning.rs` (new `Economy` struct, `pub economy: Economy` on `Tuning`; drop `ShipCombat::bank_loss`)
- Modify: `tuning.toml` (new `[economy]` section; drop `bank_loss`)
- Modify: `src/quartermaster.rs` (prices from tuning), `src/solar/station.rs` (tune, tithe, courier from tuning), `src/menu/draw.rs`, `src/menu/mod.rs` (callers)
- Test: `src/tests.rs`, `src/quartermaster.rs` unit tests

**Interfaces:**
- Produces: `crate::tuning::Economy` with fields and defaults:
  `guns: BTreeMap<String, u32>` (pistol 300, revolver 500, harpoon 400, smg 600, fist 600, shotgun 700, rifle 900, grenade 1000, dmr 1100, rocket 1500, by `WeaponKind::id()`), `attachments: [[u32; 3]; 4]` ([[0,200,400],[0,200,350],[0,150,150],[0,200,250]]), `tune: [u32; 3]` ([300,700,1400]), `tithe: u32` (150), `courier_base: u32` (250), `courier_step: u32` (150), `scrap_value: u32` (6), `hold_base: u32` (60), `hold_per_plating: u32` (20), `rebuy_share: f32` (0.10), `rebuy_min: u32` (100), `rebuy_max: u32` (1500), `repair_per_hp: f32` (1.0), `repair_reach: f32` (400.0).
- Produces: `quartermaster::price(kind: WeaponKind, e: &Economy) -> Option<u32>`; `quartermaster::buy_weapon(save, kind, e)`, `buy_part(save, slot, part, e)` take `&Economy`. `PART_PRICES` removed (use `e.attachments`). `station::offer(bases, from, done, e: &Economy)`. `UPGRADE_COST` and `TITHE` removed (use `e.tune`, `e.tithe`).

- [ ] **Step 1: Write the failing test** `the_economy_section_in_tuning_toml_matches_the_defaults`: parse `tuning.toml` with `toml::from_str::<Tuning>` and assert `parsed.economy == Tuning::default().economy` (derive `PartialEq` on `Economy`); assert `Tuning::default().economy.guns["rocket"] == 1500` and `.tune == [300, 700, 1400]`.
- [ ] **Step 2: Run** `cargo test the_economy_section` and see it fail to compile (no `economy`).
- [ ] **Step 3: Implement** `Economy` with `#[serde(default)]` and the defaults above; the `[economy]` section in `tuning.toml` with a comment per key; switch every caller listed above. Existing tests that import `UPGRADE_COST`/`TITHE` read `Tuning::default().economy.tune`/`.tithe` instead.
- [ ] **Step 4: Run** `cargo test` (all). Expected: PASS, including the existing counter, tuning rig, shrine and parcel tests unchanged in what they assert.
- [ ] **Step 5: Commit** "Economy: every price in tuning.toml [economy]".

### Task 2: The pocket, banking at a base door, the HUD

**Files:**
- Create: `src/solar/economy.rs` (registered from `src/solar/mod.rs` like `loss::build`)
- Modify: `src/save.rs` (`pub pocket: u32` after `banked`), `src/solar/loss.rs` (`pay` puts the bounty in `pocket`), `src/hud.rs` (`haul`), `src/solar/station.rs` (make `Prompt::say` `pub(super)`)
- Test: `src/tests.rs`, unit tests in `economy.rs`

**Interfaces:**
- Produces: `economy::bank(save: &mut Save) -> u32` moves `pocket` into `banked` (saturating) and returns the amount.
- Produces: system `bank_at_door` in `FixedUpdate` after `station::deliver`: the player on foot (no `Driving`) and alive, within `station::DELIVER_RADIUS` of a placed base's door (same door maths as `deliver`), at a base whose faction does not hunt you (`standing::hunted`), banks a non-zero pocket, writes the save and says `Banked $p`. It calls `repair` from Task 5 once that exists.
- Produces: `hud::haul(save, e: &Economy) -> String`: `BANK 750   SCRAP 12/60`, and with a pocket `BANK 750 +120   SCRAP 12/60`.

- [ ] **Step 1: Write the failing tests:**
  - unit `bank_moves_the_pocket_into_the_bank`: `Save { banked: 10, pocket: 120, .. }` → `bank` returns 120, banked 130, pocket 0; a second call returns 0.
  - `shooting_down_an_enemy_pays_its_bounty_and_counts_the_kill_by_faction` (existing): now asserts `(save.pocket, save.banked, save.kills) == (60, 0, 1)`.
  - `bounty_in_the_pocket_banks_at_the_roosts_door`: `system_app()`, set `pocket = 200`, place the player at the Roost's door as `a_parcel_is_taken_at_the_desk...` does, `run(0.2)` → `(banked, pocket) == (200, 0)` and the prompt text contains `Banked $200`; `run(1.0)` more → still 200 (banked once).
  - `a_base_that_hunts_you_keeps_your_pocket_out`: same, with the Roost replaced by setting the Deserters... (Deserters never hunt) so instead call `economy::serves(save, faction, t) -> bool` directly: false for Scrappers at -60, true at -59 and for Deserters always.
  - unit in `hud.rs` or tests: `haul` gives `BANK 750   SCRAP 12/60` and with pocket 120 `BANK 750 +120   SCRAP 12/60`.
- [ ] **Step 2: Run** them; expect compile failure / FAIL.
- [ ] **Step 3: Implement** the field, `bank`, `serves` (`!standing::hunted`), the system, `pay` into pocket, `haul` (hold cap from Task 3's `hold_cap`; write Task 3's function first if doing tasks in order, or show `/cap` once Task 3 lands). Update `loss.rs`'s module doc ("pays its bounty into the pocket").
- [ ] **Step 4: Run** `cargo test`. PASS.
- [ ] **Step 5: Commit** "Economy: bounties go in your pocket and bank at a base's door".

### Task 3: The hold cap

**Files:**
- Modify: `src/solar/economy.rs`, `src/solar/salvage.rs` (`collect`, `gather`)
- Test: unit tests in `salvage.rs`/`economy.rs`, `src/tests.rs`

**Interfaces:**
- Produces: `economy::hold_cap(save: &Save, e: &Economy) -> u32` = `hold_base + hold_per_plating * ship_parts[0]` (60 to 120).
- Changes: `salvage::collect(save, loot, t, cap: u32) -> (Gain, Option<Loot>)`; the second value is what did not fit (`Some(Loot::Scrap(rest))`), `None` when all of it came aboard. A module always comes aboard; a spare's `module_scrap` is clamped to the room left, the excess is lost (a module has no "rest").
- `gather` does not pull a `Loot::Scrap` pickup while the hold is full; a pickup that only partly fits keeps the rest, stops being pulled (`pulled = false`) and floats on.

- [ ] **Step 1: Write the failing tests:**
  - unit `the_hold_holds_sixty_and_twenty_more_a_plating_level`: `hold_cap` is 60 at plating 0, 120 at 3.
  - unit `a_pickup_that_does_not_fit_leaves_the_rest`: scrap 58 of 60, `collect(Scrap(8))` → gain 2, rest `Some(Scrap(6))`, scrap 60; then `collect(Scrap(4))` → gain 0, rest `Some(Scrap(4))`.
  - unit `a_spare_module_fills_the_hold_only_to_the_top`: scrap 55, spare module → gain 5, scrap 60.
  - update `a_spare_module_turns_into_scrap` and the HUD scrap test to the new signature.
  - `src/tests.rs` `a_full_hold_leaves_scrap_floating`: following the existing scrap-pull test (`3880`), with `save.scrap = 60` the pickup is still there after the time it took to arrive in the original test.
- [ ] **Step 2: Run**, expect FAIL.
- [ ] **Step 3: Implement.** The `+n SCRAP` line shows what came aboard; when the hold is full and a pickup is in pull range, the salvage line says `HOLD FULL` (reuse `SalvageLine`, a `full: bool` flag drawn in place of the scrap count).
- [ ] **Step 4: Run** `cargo test`. PASS.
- [ ] **Step 5: Commit** "Economy: the hold holds 60 scrap, 20 more a plating level".

### Task 4: The death rule: pocket, hold and parcel; the rebuy fee

**Files:**
- Modify: `src/solar/economy.rs`, `src/solar/loss.rs` (`Loss`, `lose`, `card_text`, `shot_down`, the module doc), `tuning.toml`/`src/tuning.rs` (`bank_loss` already gone in Task 1)
- Test: `src/tests.rs` (rewrite the two `shot_down_*` loss tests), unit tests

**Interfaces:**
- Produces: `economy::ship_value(save: &Save, e: &Economy, t: &ShipCombat) -> u32` = sum of `e.tune[..ship_level]` + `e.scrap_value` × sum over parts of `t.part_costs[i][..ship_parts[i]]`.
- Produces: `economy::rebuy_fee(save, e, t) -> u32` = `clamp(round(rebuy_share × ship_value), rebuy_min, rebuy_max)`.
- Changes: `Loss { pocket: u32, scrap: u32, parcel: Option<Contract>, fee: u32 }`; `loss::lose(save: &mut Save, e: &Economy, t: &ShipCombat) -> Loss` zeroes pocket and scrap, takes the parcel, takes `min(banked, fee)` and counts the death. Weapons, parts, tune, ship parts, modules, fitted, standing untouched.
- `card_text(lost, bases)`: the parts that are non-zero, joined: `Lost $120 unbanked, 30 scrap and the parcel for The Reliquary. Rebuy $100`. All zero but the fee: `Nothing aboard lost. Rebuy $100`. Fee 0 (empty bank): `... Rebuy free: the bank is empty`.

- [ ] **Step 1: Write the failing tests:**
  - unit `a_bare_kestrel_is_worth_nothing_and_rebuys_at_the_floor`: default save → `ship_value` 0, `rebuy_fee` 100.
  - unit `the_rebuy_fee_is_a_tenth_of_the_kit_up_to_the_cap`: `ship_level 3`, `ship_parts [3,3,3,3]` → `ship_value` = 2400 + 6 × (76+76+62+95) = 4254, fee 425; with `rebuy_share 1.0` fee 1500.
  - `shot_down_you_lose_the_pocket_the_hold_and_the_parcel_and_pay_the_rebuy`: replaces the quarter-of-the-bank test: banked 1003, pocket 120, scrap 30, parcel to the Reliquary, `ship_level 2` (value 1000, fee 100) → `Loss { pocket: 120, scrap: 30, parcel, fee: 100 }`, banked 903, pocket 0, scrap 0, guns, parts, tune kept; card text as above; banked still 903 after `back_at_the_roost`.
  - `shot_down_with_a_poor_bank_rebuys_for_what_is_there`: banked 40 → fee 40, banked 0; card `Nothing aboard lost. Rebuy $40`. Empty bank → `Rebuy free: the bank is empty`.
  - `parts_land_on_a_fresh_kestrel_and_are_kept_after_being_shot_down` and `fitted_modules_are_kept_through_being_shot_down` still pass (scrap now lost: update the scrap assertion in the first if it checks scrap kept).
- [ ] **Step 2: Run**, expect FAIL.
- [ ] **Step 3: Implement.** The card footer becomes `Guns, parts, modules and tune kept.` + the existing back-to-Roost line.
- [ ] **Step 4: Run** `cargo test`. PASS.
- [ ] **Step 5: Commit** "Economy: shot down, you lose what is aboard and pay a rebuy fee, not the bank".

### Task 5: Repair at a base

**Files:**
- Modify: `src/solar/economy.rs`
- Test: unit tests, `src/tests.rs`

**Interfaces:**
- Produces: `economy::repair_cost(missing_hp: f32, faction: Faction, save: &Save, e: &Economy, t: &ShipCombat) -> u32` = `standing::price(ceil(missing_hp × repair_per_hp), faction, save, t)`.
- Produces: `economy::repair(hull: &mut Hull, faction, save: &mut Save, e, t) -> Option<(f32, u32)>`: repairs as much of `max_hp - hp` as the bank affords (whole points), takes the money, returns `(hp repaired, cost)`; `None` if nothing to do or the bank is empty.
- `bank_at_door` (Task 2) also repairs the newest parked ship (no pilot, greatest `Ship::landed_at`) within `e.repair_reach` of the door, once per arrival: it runs only on the frame the player comes within the radius (track `Local<bool>` "was at a door"), and says `Repaired 40 hull: -$40` (joined with the banked note on one line when both happen).

- [ ] **Step 1: Write the failing tests:**
  - unit `repair_costs_a_credit_a_point_at_list_price`: missing 40 at the Roost → 40; at the Yard with Scrappers at 40 → 34.
  - unit `repair_stops_at_what_the_bank_affords`: missing 40, banked 25 → repairs 25 hp, banked 0; banked 0 → `None`.
  - `a_damaged_kestrel_is_repaired_when_you_reach_the_door`: `system_app()`, damage the parked Kestrel to `max_hp - 30`, banked 100, place the player at the Roost's door → hull full, banked 70; `run(1.0)` more → banked still 70.
- [ ] **Step 2: Run**, expect FAIL. **Step 3: Implement.** **Step 4: Run** `cargo test`, PASS.
- [ ] **Step 5: Commit** "Economy: a base repairs your ship's hull for money when you reach its door".

### Task 6: Selling scrap at the Yard

**Files:**
- Modify: `src/solar/standing.rs` (`buys`), `src/solar/economy.rs` (`sell_scrap`), `src/menu/mod.rs` (`Row::Sell` on `Panel::Parts`), `src/menu/draw.rs` (draw the row), `src/menu/draw.rs` hint strip shows the bank too on the parts rack
- Test: unit tests, `src/tests.rs`

**Interfaces:**
- Produces: `standing::buys(value: u32, faction, save, t) -> u32`: what a base pays for something worth `value`: ×1.15 at Friendly, ×0.85 below -40, else ×1, rounded; list for factions that do not move.
- Produces: `economy::sell_scrap(save: &mut Save, faction, e, t) -> u32`: sells the whole hold at `standing::buys(e.scrap_value, ..)` each, banks it straight away (you are at the base), returns the money.
- Menu: `Row::Sell` above BACK on the parts rack: `SELL SCRAP  12 × $6 = $72`; select sells and the note says `Sold 12 scrap: +$72`; nothing to sell → `The hold is empty`. Refused when hunted (the rack does not open then anyway).

- [ ] **Step 1: Write the failing tests:**
  - unit `a_friend_pays_more_for_scrap_and_a_wary_base_less`: Scrappers 0 → 6, 40 → 7, -41 → 5.
  - unit `selling_empties_the_hold_into_the_bank`: scrap 12 at the Yard, Scrappers 0 → returns 72, scrap 0, banked +72.
  - menu test following `the_parts_rack...` (`3940`): open the rack, move to SELL SCRAP, press select → scrap 0, banked up by the price.
- [ ] **Step 2: Run**, FAIL. **Step 3: Implement.** **Step 4: Run** `cargo test`, PASS.
- [ ] **Step 5: Commit** "Economy: the Yard buys your scrap".

### Task 7: Docs, the running game, the PR

**Files:**
- Modify: `README.md` (bounty and loss, salvage, stations, save sections), `src/solar/station.rs` module doc ("the only income" is stale), spec status line ("Stage A built")

- [ ] **Step 1:** Update the README lines found by `grep -n "bank\|scrap" README.md` to the new rules.
- [ ] **Step 2:** `cargo test` and `cargo clippy --all-targets` clean.
- [ ] **Step 3:** Run the game (`RUST_REGIME_LEVEL=system`, with `RUST_REGIME_DIE=5` for the card) and take screenshots of the HUD haul with a pocket, the shot-down card and the parts rack's sell row into `screenshots/economy/`.
- [ ] **Step 4:** Commit, push `claude/economy-a`, open a draft PR that waits for Q's merge (a feature and a save-format change).
