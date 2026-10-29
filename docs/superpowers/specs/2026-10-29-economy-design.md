# Economy: one ledger, boards at every base, scrap as cargo

Follows `2026-10-29-ship-combat-stages-2-3-design.md` (standing and salvage, both merged). Q asked
on 2026-10-29 for "a proper economy system". This is a spec for review; nothing is built from it.

## TL;DR

Today money has no shape: pay lands straight in the bank, the bank is the thing you lose when shot
down, scrap cannot be sold, only Vantage hands out jobs, and once the gun counter is bought there is
nothing left to spend on. This spec gives the economy a loop:

- **Earn in the field, bank at a base.** Bounties and scrap go into your *pocket* and *hold*. They
  bank when you land at a base that will serve you. Being shot down loses the pocket, the hold and
  the parcel, never the bank. A fresh Kestrel costs a rebuy fee from the bank instead.
- **A job board at all four bases**, three offers each, reseeded every game day: courier parcels,
  raider culls, and scrap supply runs. Pay scales with distance, danger and standing.
- **Scrap is cargo.** The Yard buys it at a price that falls as its stockpile fills and recovers
  over time. Vantage buys at a flat worse rate. A hold cap makes you fly back to sell.
- **Recurring sinks:** hull repair, the rebuy fee and the tithe keep money mattering after the
  counter is bought. **A top goal:** at Allied standing a faction sells you one of its own hulls.
- **One pricing rule.** Every price lives in `tuning.toml [economy]`, reloads on F5, and goes
  through the same standing formula.

**The one decision for Q:** the death rule. **Recommended: pocket-at-risk** (above). **Alternative:
keep today's 25% bank loss** and add the pocket on top. Pocket-at-risk is the Sea of Thieves /
Hunt rule and fits a movement game: the run home is the tension. The 25% rule punishes saving and
is why the bank feels pointless. Everything else below is a recommended default; say so if you
want any of it changed. Faction hulls for sale (stage D) is the part most worth a veto.

## The model

### Values in the save (all `serde(default)`, old saves load)

| Field | Type | Meaning |
|---|---|---|
| `banked` | u32 | Safe money. Unchanged field. |
| `pocket` | u32 | New. Unbanked credits earned since you last landed. Lost when shot down. |
| `scrap` | u32 | Now the ship's hold. Lost when shot down. Capped by `hold_cap`. |
| `contract` | `Option<Contract>` | Becomes `contracts: Vec<Contract>`, at most 2 active. Old field migrates. |
| `contracts_done` | u32 | Unchanged. |
| `board_day` | u32 | New. Game day the boards were last generated for. |
| `yard_stock` | u32 | New. The Yard's scrap stockpile. Starts at `yard_target`. |
| `day_clock` | f32 | New. Game seconds into the current day. A day is 2880 s, as standing recovery already uses. |

Standing, weapons, parts, tune, ship parts, modules and fitted are unchanged and survive death.

### Pocket and bank

- Parcel pay is banked on delivery (you are at a door). Bounties and contract bonuses go to
  `pocket`. Scrap goes to the hold.
- Landing within 12 m of any station door at a base that serves you (standing above Hunted)
  moves `pocket` into `banked`. The HUD shows `BANK n  +p` while the pocket is non-zero, and
  `SCRAP s/cap`. On banking, a short chime and the `+p` folds into the bank.
- Shot down: `pocket = 0`, `scrap = 0`, every active contract with a parcel is dropped (-5
  standing with its issuer), `deaths += 1`. Then the rebuy fee: `fee = clamp(0.10 × ship_value,
  rebuy_min 100, rebuy_max 1500)` where `ship_value` is everything spent on the tune and the four
  parts at list price. `banked -= min(banked, fee)`. You never go into debt and you always get a
  Kestrel. On-foot death stays free.
- The old 25% bank loss is removed (alternative: keep it; then the rebuy fee is dropped so death
  is not charged twice).

### Hold cap

`hold_cap = 60 + 20 × hull_plating_level` (60 to 120). Scrap beyond the cap is not picked up; the
wreck's scrap stays until its 90 s life ends. The HUD shows the cap, and the pickup sound changes
when the hold is full.

### Selling scrap

- **The Yard** buys at `scrap_price = clamp(scrap_base 6 × sqrt(yard_target / yard_stock), 3, 12)`
  credits each, then standing-adjusted (Friendly sells for 15% *more*, Wary for 15% *less*: the
  formula is the same one, read the other way for things the base buys). Selling adds to
  `yard_stock`. The stock moves toward `yard_target` (300) by 1% of the gap per game minute, so a
  dumped hold recovers in roughly a day.
- **Vantage** buys at a flat `scrap_base × 0.7`, no stock, standing-adjusted.
- **The Reliquary** and **the Roost** do not buy scrap.
- Buying scrap at the Yard: `scrap_price × 1.5`, so grinding parts with credits is possible but
  bad value. Scrap spent on parts does not touch the stock.

### One pricing rule

`price(base, faction, kind)` with kind Sells or Buys. Sells: ×0.85 at standing ≥ 40, ×1.15 below
-40, else ×1. Buys is the inverse. Applied to: the gun counter and attachments, the engine tune,
the parts rack, the tithe, repair, scrap, rebuy (fee uses the Roost's Deserter standing, so always
×0.85), and faction hulls. The Roost is Deserters at a fixed 50, so its list prices are shown as
the Friendly price. Hunted (≤ -60) refuses everything but the board, as today.

Every number here moves into `tuning.toml [economy]` with defaults in `tuning.rs`, including the
gun counter prices, `UPGRADE_COST`, `TITHE` and the courier formula, which are hard-coded today.

## The boards

Every base has a `kind = "board"` station (Vantage's desk becomes one). Each board holds three
offers, regenerated at the start of each game day from `seed = hash(save.seed, day, base_name)`;
the same save on the same day shows the same offers, which the tests rely on. Taking an offer
removes it from the board; the slot stays empty until the next day. Up to two contracts active.
An offer not completed by the end of the *next* game day expires silently, except a parcel, which
costs -5 standing with its issuer.

| Kind | What | Pay | Appears |
|---|---|---|---|
| **Courier** | Carry a parcel to another base's door. | `courier_base 250 + courier_per_Mm 60 × distance in 1000 km` at offer time, ×1.5 if the destination faction is below 0 with you (you must get past its patrols), +20% at Friendly with the issuer. Banked on delivery, +10 standing with the destination faction. | Always one per board. |
| **Cull** | Kill `n` raiders anywhere, `n` in 4..8 from the seed. Any kill by the ship you fly counts; the normal bounty still pays per kill. | Bonus `cull_per_kill 50 × n`, into the pocket on the `n`th kill. +2 standing per raider stays. | Always one per board. |
| **Supply run** | Bring `n` scrap to this board, `n` in 20..40. | `scrap_price × n × 1.3` at the Yard, `scrap_base × 0.7 × 1.3 × n` elsewhere, into the pocket. Scrap is consumed. +5 standing with the issuer. | Third slot. At the Yard, only while `yard_stock < 0.5 × yard_target`, then at ×1.6. Elsewhere, half the days. |

Escorts and bounty hunts on named ships are not in this spec; the hooks are the `Contract.kind`
enum and the board generator.

Courier pay today is 250/400/550 by a counter. With the four worlds' distances, the new formula
should land between 400 and 900. The number to tune first is `courier_per_Mm`.

## Recurring sinks and the top goal

- **Repair:** every base that serves you repairs hull at `repair_per_hp 1` credit per point,
  charged on landing like banking (shown as `-r` beside the `+p`). Shields regenerate free. The
  Roost charges the Friendly price, not nothing: free repair at home drains the loop.
- **Tithe** and the **blessing** stay as they are.
- **Faction hulls (stage D, Q to confirm):** at Allied (≥ 80) a base sells its patrol hull:
  sentry at Vantage 6000, welder at the Yard 8000, censer at the Reliquary 9000. Bought hulls
  appear on the Ship screen beside the Kestrel; the tune, parts and modules are your kit and
  carry to whichever hull you fly. Being shot down in a faction hull gives you back that hull
  (you own it), with the same rebuy fee. Flying a faction's hull does not change how other
  factions treat you. The ships, controls and AI stats already exist in `ships.toml`.

## The curve

Targets, so the numbers above can be checked against play rather than argued about:

| Milestone | Target time | Source of money |
|---|---|---|
| First gun (600-700) | 15 min | one or two courier runs |
| Whole counter (~7600 with attachments) | 2 h | couriers and culls |
| Tune 3 and all parts at 3 | 3 h | culls for bounties, salvage sold or spent |
| First faction hull | 5 h and Allied with one faction | everything, plus 10 deliveries to one base |

A death mid-run should cost 10 to 20 minutes of earnings, never a session.

## Staging (each stage is its own PR, playable on its own)

- **A. Ledger:** pocket, banking on landing, hold cap, death rule and rebuy, selling scrap, repair,
  all prices into tuning, one price rule everywhere, HUD. Save migration.
- **B. Boards:** board station at all four bases, seeded generator, courier/cull/supply contracts,
  two active, expiry, board screen and HUD contract lines.
- **C. Yard stock:** stockpile, dynamic scrap price, shortage supply runs.
- **D. Faction hulls** (optional): purchase at Allied, hull selection on the Ship screen.

A is the one that changes what the player feels; B is the one that adds content. C and D are
small once A and B exist.

Out of this spec, but found while reading: `standing::recover` creeps every faction back +1 a day,
so a Hunted faction stops hunting after 2880 s, which the stage-2 spec says should not happen. That
is a one-line fix in its own PR.

## Testing (headless, `cargo test`)

- Bounty goes to pocket, banks on landing, HUD shows `+p` then folds it.
- Shot down: pocket, scrap and parcel gone; bank reduced by the rebuy fee and never below zero;
  parts, modules, tune kept; standing -5 with the parcel's issuer.
- Hold cap: pickup refused at cap; cap rises with plating.
- Scrap price falls after a sale and recovers toward the base price over a day; Vantage flat;
  Friendly sells higher, Wary lower.
- Boards: same seed gives the same three offers; a taken offer leaves a gap; new day reseeds;
  two active max; expiry at the end of the next day; parcel expiry costs standing.
- Cull completes on the nth kill by the flown ship and pays the bonus once.
- Supply run consumes scrap and pays; the Yard shortage offer appears only below half stock.
- Repair charged on landing, Friendly price at the Roost.
- Old `save.toml` with `banked` and `contract` loads with pocket 0, one migrated contract and a
  full Yard stock.
- Every price reads from tuning and F5 reloads it (one test per station kind).
