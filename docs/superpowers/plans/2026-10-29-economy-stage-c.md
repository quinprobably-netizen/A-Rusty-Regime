# Economy stage C (the Yard's stockpile) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Yard's scrap price falls as you sell it scrap and recovers over a game day; the Yard sells scrap back at a markup; when its stock runs low its board asks for supply runs at a premium.

**Architecture:** All in `src/solar/economy.rs` (stock, price, sale, purchase, recovery system) plus a branch in `board::offers` for the Yard. The parts rack and the boards call one sale function that knows which base is buying.

**Tech Stack:** Rust, Bevy 0.19; headless tests.

**Spec:** `docs/superpowers/specs/2026-10-29-economy-design.md`, "Selling scrap" and "Staging: C".

## Global Constraints

- New numbers in `[economy]`: `yard_target = 300`, `yard_recover = 0.01` (share of the gap a game minute), `scrap_price_min = 3`, `scrap_price_max = 12`, `scrap_markup = 1.5`, `yard_shortage = 0.5`, `shortage_pay = 1.6`, `scrap_lot = 10`.
- `Save::yard_stock: Option<f32>`; `None` reads as `yard_target`, so old saves start full.
- Selling sells one scrap at a time at the price that scrap meets, so a big hold cannot dump at the full price.

## Review Focus

- **Selling 120 scrap at once:** the price falls during the sale; the total is less than 120 × the opening price. Task 1.
- **Stock far above target (debug or old values):** price clamps at the floor, recovery pulls it back down. Task 1.
- **Buying scrap with a full hold or too little money:** buys what fits and what is affordable, never negative. Task 2.
- **Yard supply hand-in:** fills the stock, so the shortage offer stops appearing. Task 3.
- **Vantage's price:** unaffected by the Yard's stock. Task 1.

---

### Task 1: Stock, price, sale, recovery

**Interfaces (produces), `src/solar/economy.rs`:**
- `yard_stock(save, e) -> f32`; `yard_price(stock: f32, e) -> f32` = `clamp(scrap_value × sqrt(yard_target / max(stock, 1)), scrap_price_min, scrap_price_max)`.
- `scrap_value_at(save, base: &str, e) -> Option<f32>`: per scrap before standing: the Yard's `yard_price × scrap_buyers["yard"]`, another buyer's `scrap_value × share`, `None` if it buys none.
- `sale(save, base, faction, e, t) -> (u32, u32)`: scrap sold and money, pure: one scrap at a time at `standing::buys(round(value))` with the Yard's stock rising by one after each.
- `sell_scrap(save, base, faction, e, t) -> u32` applies `sale`: hold to 0, money banked, the Yard's stock up by the scrap.
- System `recover_stock`: `stock += (target - stock) × (1 - (1 - yard_recover)^(dt / 60))`.
- Tests: price at target is 6, at half stock about 8.5, at 4× stock 3 (floor), at 0 stock 12 (cap); selling 60 at the Yard pays less than 360 and leaves stock 360; Vantage's 30 pays 120 whatever the Yard's stock; recovery moves 1% of the gap a minute and reaches within 10% of target in a day.

### Task 2: Buying scrap at the Yard

- `buy_scrap(save, faction, e, t) -> Result<(u32, u32), Short>`: up to `scrap_lot`, limited by hold room and money, at `standing::price(round(yard_price × scrap_markup))` each; takes scrap from the stock.
- Parts rack: a `BUY 10 SCRAP` row under the sell row.
- Tests: buys 10 at 9 each with money for it; a hold with 4 free buys 4; $20 buys 2; nothing in the bank or no room refuses.

### Task 3: Shortage supply runs at the Yard

- `board::offers` at the Yard: when `yard_stock < yard_shortage × yard_target`, the third offer is a supply run (`supply_scrap` range) paying `round(yard_price × supply_markup × shortage_pay × need)`.
- `board::hand_in` at the Yard adds the scrap to the stock.
- Tests: no Yard supply at full stock; one at 100 stock with the premium pay; handing it in raises the stock by `need`.
- README "Money" and "Job boards" lines, screenshots of the rack, PR for Q.
