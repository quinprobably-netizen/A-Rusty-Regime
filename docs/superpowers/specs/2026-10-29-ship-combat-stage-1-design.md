# Ship combat, stage 1: something to shoot at

Agreed with Q on 2026-10-28 in the "what is missing" brainstorm. Since PR #52 removed the island,
soldiers and vehicles, nothing in the solar system can be shot and nothing shoots back. This is
the first of three stages that fix that. It is a spec for review: nothing is built from it yet.

## TL;DR

You fly the Kestrel with **nose guns** (left click) and a **homing missile** (right click).
**Raiders** (small packs of Jackals) jump you anywhere in the air or in orbit while you fly, and
each faction's base has **patrols** that attack if you come close. Ships have a **shield and a
hull**. Kills pay a **bounty** into the bank. If your ship is destroyed you respawn at the Roost
in a fresh Kestrel, **lose the courier parcel and a quarter of your bank**, and keep your guns,
parts and engine tune.

**One decision for Q:** do enemies ever attack you on foot? Recommended: no, in stage 1. They
hunt ships only, so walking round a base is always safe and the on-foot guns stay idle until a
later stage. The alternative (patrols also shoot a player on foot near their base) needs a
ground-target model and aiming at a human-sized target from a ship, so it would grow stage 1.

## Agreed with Q

| Question | Answer |
|---|---|
| Where does fighting happen first | In ships, not on foot |
| Who you fight | Faction patrols guard their bases, and raiders roam between worlds |
| How you shoot | Nose guns plus a homing missile |
| What losing costs | Respawn at the Roost; lose the parcel and part of the bank; keep guns, parts and tune |
| What winning gives | Bounty money now; salvage and faction standing in later stages |

## The three stages

1. **This spec.** The fight itself: weapons, hull and shield, raiders, patrols, bounty, the loss
   rule, HUD, sound. Kills are recorded by faction so stage 2 can use them.
2. **Faction standing.** Kills move your standing with each faction. Bases and patrols react.
3. **Salvage.** Wrecks drop parts you fly into, and a place to spend them.

Out of scope here: enemies shooting a player on foot, enemy ships landing or boarding, capital
ships, ship-mounted turrets for allies, weapon upgrades beyond the existing engine tune.

## What exists that we build on

- `solar::ship`: one rigid body per ship, flown by `fly()`, steered by the global `ShipControls`
  resource. The pilot is `Ship.pilot: Option<Entity>`.
- The four enemy hulls (Censer, Welder, Sentry, Jackal), merged in PR #53: solid hulls,
  `exhaust.<n>`, `heat` and `light.<n>` nodes, no interior.
- `weapon.rs` bullets (ray-swept, drag, energy-scaled damage) and `PlayerHit`.
- `planet::bubble`: only bodies near the player simulate; `KeepAwake` marks a flown ship.
- `hud::FlightHud`, the waypoint projector in `solar::waypoint`, synthesized sound in `sound.rs`.
- `Save` (`banked`, `contract`, `ship_level`) and the station code that spends it.

## Design

### 1. A stick per ship

`ShipControls` becomes a component on each ship instead of one global resource. The player's
input still fills the controls of the ship they pilot; an enemy's AI fills its own. `fly()`
reads each ship's own controls, so enemies use exactly the flight model you do: same turn rates,
boost tank and drag, from each hull's entry in `ships.toml`. This is the one real refactor, and
it comes first, behind the existing tests, so a pure rename lands before any new behaviour.

### 2. New module `solar/combat.rs`

Components and what they hold:

- `Hull { hp, shield, shield_regen_after }`: damage drains the shield first. The shield
  regenerates after 5 s with no hit. At 0 hp the ship is destroyed.
- `Gun { heat, fire_timer }`: nose guns on the pilot's fire input. Heat builds per shot and an
  overheated gun stops until it cools, so there is no ammo count.
- `Missiles { count, reload, lock }`: four missiles, one regained every 10 s.
- `Projectile` and `Missile` entities, below.
- `Faction` on every ship, so stage 2 can read who was shot.

Fire input: left click is `input.fire_held`, right click is `input.aim_held`, which `ship.rs`
currently clears while flying. Those two lines change to feed the ship instead. On a pad every
button is already taken in flight (RT and LT are thrust, LB and RB yaw, A boost, Y stop, B look),
so the pad mapping is an open question for Q: the likely answer is to move guns to RT and thrust
to the left stick's click, but that changes how the pad flies today, so it is decided when we
get there. Stage 1 ships the keyboard and mouse bindings in the controls table the README is
generated from.

### 3. Weapons

- **Nose guns:** 2 shots per second per barrel, two barrels at the wing roots converging 400 m
  ahead. A shot is a short-lived projectile at 1.2 km/s in the ship's frame plus the ship's own
  velocity, ray-swept each tick like `weapon.rs` bullets so nothing tunnels at 6 km/s closing
  speed. Damage 12 per shot, shield and hull alike. Range 2 km, then it despawns. No gravity
  in space; in air a little drag. Shots do not hurt their own ship or the same faction's.
- **Homing missile:** hold the target in a 6 degree cone in front of the nose for 1.2 s and it
  locks (a tone and a HUD ring); right click fires a missile at the locked ship. It accelerates
  to 600 m/s, steers by proportional navigation at a capped turn rate of 1.4 rad/s, lives 8 s and
  explodes on contact or within 8 m of the target for 80 damage. It can be outturned and it dies
  on the ground, so flying low is a defence. Without a lock right click fires it straight ahead.
- **Damage numbers** live in `tuning.toml` under `[ship_combat]`, one table, F5-reloadable like
  every other tuning section.

### 4. Hull and shield per ship

All in `ships.toml` so each hull carries its own. Starting values, to tune by feel:

| Ship | Shield | Hull | Notes |
|---|---|---|---|
| Kestrel (you) | 60 | 100 | The all-rounder |
| Jackal | 30 | 40 | Fragile, comes in packs |
| Sentry | 50 | 70 | Light and quick, keeps its distance |
| Censer | 50 | 90 | Fast in a straight line, slow to turn |
| Welder | 60 | 200 | Twice the hull of the others, slow |

The tune levels from the Yard's rig stay as they are; they change thrust and agility, not hull.

### 5. Enemy ships and where they exist

The four fighters get `[[ship]]` entries with `kind = "fighter"`: no ramp, no cabin, one box or
capsule collider. They only exist near you, because physics only runs inside the bubble:

- **Cap:** at most 8 enemy ships alive at once.
- **Spawn:** at 1.5 to 3 km from you, off to a random side, never in front of the nose.
- **Despawn:** past 6 km from you, with no event. A killed ship stays killed; one that merely
  left is replaced by the next spawn.

### 6. Raiders

While the player is piloting a ship (on foot is always safe, see the decision above), a timer
spawns a pack of 2 to 4 Jackals. The delay starts at about 90 s and shortens the longer you have
flown without a fight, so a long trip is always interrupted. No raiders spawn within 3 km of a
base, so landing and takeoff stay calm, and none in the first minute after boarding.

### 7. Patrols

Each base spawns two patrol ships of its faction while the player is within 8 km: Censers for
the Regime, Welders for the Scrappers, Sentries for the PMC. The Deserters' Roost has none. A
patrol circles its base at 300 m altitude. It attacks if you come within 2.5 km, and gives up
when you are past 4 km. Patrols killed are replaced after 10 minutes of game time. One body's
patrols are rebuilt from the base list, so a save needs nothing.

### 8. AI

One state machine, steering by writing the ship's own `ShipControls` (stick, thrust, boost):

`Patrol` (follow a loop) → `Pursue` (fly to a lead point ahead of the target) → `Attack`
(inside 1.2 km and within a firing cone: fire) → `Break` (a hard turn after a pass, or when
hurt). Per-type tuning in `ships.toml`: the Jackal rushes in and breaks off at 30% hull, the
Sentry keeps 600 m and prefers missiles, the Censer makes long strafing passes and a wide turn,
the Welder closes to ramming range and fires heavy shots. All of it reads the shared flight model
through the stick, so an enemy cannot do what you cannot.

### 9. Death and the loss rule

When your hull hits 0 your ship explodes. You respawn on the Roost's apron in a fresh Kestrel
(the same respawn the ship already uses), keeping your owned guns, fitted parts and Yard tune.
You lose the courier parcel you carried and 25% of your bank (rounded down). Dying to a raider
while carrying nothing and with an empty bank costs nothing, so a broke player is not
softlocked. The loss is shown on the respawn card.

### 10. Bounty

A kill pays into `save.banked`: Jackal $60, Sentry $120, Censer $150, Welder $200, tuned in
`[ship_combat]`. `Save` gains `kills: u32` and a faction tally. Both default to zero so an old
`save.toml` still loads. The kill line (`+$120 BOUNTY`) shows over the HUD.

### 11. HUD and sound

- Hull and shield bars next to the boost tank, a heat bar for the guns, a missile count.
- A diamond on each enemy ship (reusing `waypoint::project`) with its faction colour, a lock
  ring when the cone has held, and a hit marker when your shots land.
- Sounds synthesized at startup like the rest: gun, missile launch, explosion, shield hit, hull
  hit, lock tone.

### 12. The gravity fix, first

Item 3 of the gap list: bullets, grenades, harpoons and debris in `weapon.rs` always fall along
-Y at 9.81, which is wrong on a round world. It is a small change (take the gravity vector from
`Surface`) that stage 1 relies on for anything fired in air near the ground, so it lands as its
own PR before this work starts.

## Testing

Headless, in `tests.rs` style, no GPU:

- The per-ship controls refactor leaves the existing ship tests passing unchanged.
- Shield drains before hull; it regenerates only after 5 s quiet; a hull at 0 destroys the ship.
- A shot at a ship in range damages it; a shot from its own faction does not.
- A missile with a lock hits a steady target and misses one that turns hard enough.
- A pack spawns at the right range, never ahead of the nose, never over the cap, and despawns
  past 6 km.
- Patrols appear near a base only inside 8 km, attack inside 2.5 km and give up past 4 km.
- Death clears the contract, takes a quarter of the bank, and keeps guns, parts and tune.
- A kill pays the right bounty and an old save without the new fields loads.
- A dogfight run for ten simulated seconds across an origin rebase leaves every ship's
  position consistent (the rebase moves enemies like any other loaded entity).

## Risks

- **Many dynamic ships in the bubble.** Avian 0.7 has a known island assertion in `bubble.rs`
  when a woken body lands. Enemy ships wake and sleep a lot, so this needs watching; the cap of
  8 is the first defence.
- **AI that is too good or too dumb at 6 km/s.** The boost cap over the ground and the flight
  assist below 3 km shape what is fair. All AI numbers are in data so they can be tuned by feel.
- **Homing across a rebase.** Missiles store body coordinates like every long-lived thing, and
  are converted on use.
- **Not yet flown.** None of the new fighter models has been seen in game; the first build step
  is wiring them in and flying one.

## Build order

1. Gravity fix (own PR).
2. Per-ship controls refactor (tests unchanged).
3. Fighters wired in as `ships.toml` entries; one parked Jackal you can walk up to.
4. Hull, shield, guns, and a stationary target that dies.
5. Raiders with the AI, then patrols.
6. Missile and lock.
7. Death, loss rule, bounty, save fields.
8. HUD and sound.
