# Ship combat, stages 2 and 3: faction standing and salvage

Follows `2026-10-29-ship-combat-stage-1-design.md`, which is built and merged (guns, missile,
shields and hulls, raiders, patrols, loss rule, bounty, HUD). Q asked on 2026-10-29 to start on
both remaining stages. This is a spec for review; nothing is built from it yet.

## TL;DR

**Stage 2, standing:** each faction has a standing with you, -100 to 100. Today a faction's patrols
shoot you on sight. After this, you start as a stranger (hostile), and you earn peace: deliver
parcels to a faction's base, or kill its rivals, and its patrols leave you alone and its base
gives you better prices. Shoot its patrols and you are hunted.

**Stage 3, salvage:** wrecks drop scrap you fly into. Scrap is a second currency, spent at the
Yard's rig on four permanent ship upgrades: hull, shield, gun cooling and missile rack.

**Two decisions for Q** (my recommended defaults are written below; say "yes" or change them):

1. Do you start as a **stranger** (patrols hostile until you earn standing) or **neutral**
   (patrols ignore you until you shoot one)? Recommended: **stranger**, because it matches how
   the game plays today and gives deliveries a purpose.
2. Is salvage **one currency, scrap, spent on four upgrades** (recommended), or **loose parts**
   you pick up and fit one at a time? Loose parts need an inventory screen, so I left them out.

## Stage 2: faction standing

### The model

- A `Standing` per faction, an integer from -100 to 100, saved as `standing: BTreeMap<String,
  i32>` with serde defaults so an old `save.toml` still loads. The factions are Regime,
  Scrappers and PMC (the three with patrols and a base). The Deserters are your own side: their
  standing is fixed at 50 and cannot move. Raiders have no standing: they always attack.
- Starting values (decision 1, stranger): **-20** with each of the three. At -20 patrols are
  hostile, as they are now.
- Rivalries, from the setting: the Regime hates the Deserters and the Scrappers; the Scrappers
  and the PMC distrust each other; the PMC sells to everyone and holds no grudge. Used only to
  decide who is pleased when you shoot someone.

### What moves it

| Action | Effect |
|---|---|
| Deliver a parcel to a faction's base | +10 with that base's faction |
| Kill a raider | +2 with each of the three factions |
| Kill a patrol ship of a faction | -25 with it; +5 with its rival (if any) |
| Shoot a patrol ship without killing it | -3, once per patrol per fight |
| Time | +1 a day (game time) toward 0 for any standing you pushed below -20 |

All numbers in `[ship_combat]`. A kill is recorded through the `ShipDestroyed` message and the
bounty path the stage-1 loss rule already added; the per-faction tally in the save stays as it is.

### What it changes

- **Patrols:** a patrol attacks you only if its faction's standing is below 0. At 0 or above they
  fly past, and a friendly patrol (40 or above) breaks off to escort you for a minute, which is
  only cosmetic. Raiders ignore standing.
- **Hunters:** at -60 or below, that faction sends a hunting pack of its own ships (2 to 3,
  from its patrol hulls) in the same way raiders spawn, at the same rate. Standing is restored
  by deliveries, not by waiting out the -60.
- **Base services:** at a base, standing sets the price of what the base sells: 15% off at 40 or
  above, 15% on at below -40, and at -60 or below the base refuses service (the prompt says so).
  The Deserters' Roost is unaffected.
- **Contracts:** a courier parcel to a faction you stand well with pays 20% more at 40 or above.

### UI

- A **Standing** screen under the pause menu, next to Starmap, Ship and Contracts: one bar per
  faction, a word for it (Hostile, Wary, Neutral, Friendly, Allied), and what each level gives.
- The enemy markers already use the faction colour; a patrol that will not shoot you gets a
  hollow diamond.
- A short line over the HUD when standing changes (`REGIME -25`).

### Why not more

No treaties, no faction war that plays out without you, no per-ship personality. That is the
"loops across worlds" brainstorm and it can follow once this exists.

## Stage 3: salvage

### The model

- A wreck (any `ShipDestroyed` that was not the player's) drops a **scrap** pickup where it
  died, drifting with the wreck's last velocity, lasting 90 s. Amount by hull: Jackal 2, Sentry 4,
  Censer 5, Welder 8, in `[ship_combat]`. Kills by AI on AI drop scrap too, so a fight between
  raiders and a patrol leaves some for you.
- **Pickup:** fly within 40 m and it is pulled in and added to your scrap. Your own ship only,
  never on foot. A sound and a `+4 SCRAP` line.
- `Save` gains `scrap: u32` and `ship_parts: [u8; 4]` (hull plating, shield cell, gun capacitor,
  missile rack), both serde-defaulted.

### What scrap buys

At the Yard's tuning rig (the workshop station), a second menu next to the engine tune. Four
upgrades, three levels each, bought with scrap, kept through death:

| Part | Per level | Cost per level (scrap) |
|---|---|---|
| Hull plating | +25 hull | 12, 24, 40 |
| Shield cell | +15 shield and faster regeneration | 12, 24, 40 |
| Gun capacitor | the guns heat 20% slower and cool 20% faster | 10, 20, 32 |
| Missile rack | +1 missile and a 1.5 s shorter reload | 15, 30, 50 |

They apply to the Kestrel only, on top of the Deserter hull's base numbers and the engine tune,
and the Ship screen shows them. The price in scrap is separate from money, so bounty buys guns
and engine tunes at the Roost and the Yard, and scrap buys durability.

### UI

- A scrap count beside the bank on the HUD and the pause menu.
- The Ship screen lists the four parts and their levels.
- At the Yard, E opens the rig prompt for the engine tune as now, and a second prompt for parts
  (up and down to pick, the same widgets as the quartermaster's counter).

## Architecture

- `solar/standing.rs`: the model, the rules above, and the message that changes it. Reads
  `ShipDestroyed`, deliveries (a message from `station.rs`) and `ShotLanded`.
- `ai.rs` patrol behaviour asks `standing::hostile(faction)` instead of attacking always.
- `solar/salvage.rs`: the pickup entity, its drift, the pickup and the upgrade table.
- `station.rs`: prices and refusal read `standing`; the workshop gains the parts menu.
- `menu/space.rs`: the Standing screen and the parts on the Ship screen.
- `hud.rs` and `solar/contacts.rs`: the hollow diamond, the scrap line, standing lines.
- `save.rs`: `standing`, `scrap`, `ship_parts`.

## Testing

Headless, in the existing `tests.rs` style:

- A new save starts at -20 with each faction, 50 with the Deserters, and an old save loads.
- A delivery, a raider kill, a patrol kill and a damaging hit each move standing by the table;
  it clamps to -100 and 100; the Deserters never move.
- A patrol attacks at -20 and ignores you at 0, and goes back to attacking after you shoot one.
- At -60 hunters spawn from that faction; at 40 prices drop; at -60 the base refuses.
- Scrap drops where a ship dies, is picked up within 40 m only by your ship, and times out.
- Upgrade purchase: price, level cap, effect on a freshly spawned Kestrel's hull, shield, heat
  and missiles; kept after death.

## Risks

- **Hostile-by-default feel.** Patrols that suddenly leave you alone could make the game feel
  empty; the hunters at -60 and the raiders keep fights coming. Numbers are data and can be tuned.
- **Menu growth.** The Ship, Starmap, Contracts and Standing screens all hang off the pause
  menu; the list may need a second page.
- **Pickup drift in space.** Scrap uses the same sphere-of-influence conversion as missiles; it
  can be allowed to vanish at a handoff, since it only lasts 90 s.

## Build order

1. Standing: the model, save fields and the rules, with the patrol change.
2. Standing: prices, refusal, hunters, the screen and the HUD lines.
3. Salvage: the drop, the pickup and the save fields.
4. Salvage: the upgrade menu at the Yard and the effects on the Kestrel.
5. Salvage: the HUD and the Ship screen.
