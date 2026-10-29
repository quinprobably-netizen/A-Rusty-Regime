# Rust Regime

FPS movement prototype in Rust: Bevy 0.19 + Avian 0.7 physics. TF2-style
movement and parkour, a solar system to fly around and a set of weapons.

## One-click update and play
Set up once, then you never redownload the whole game:
1. Install Rust from https://rustup.rs (on Windows, accept the Visual Studio Build Tools it asks for).
2. Install Git (https://git-scm.com, Windows: use the defaults), then get the game once:
   `git clone https://github.com/quinprobably-netizen/A-Rusty-Regime.git`
   (or use GitHub Desktop's Clone button, but still install Git so the script can pull).
3. Double-click `play.bat` on Windows, or run `./play.sh` on Linux.

The script pulls only what changed, rebuilds only what changed, and starts the game.
The first build takes a while; later ones are quick.

## Run
```
cargo run --release
```
First build takes a while. Linux needs `libasound2-dev libudev-dev libwayland-dev libxkbcommon-dev`.
`cargo test` runs headless physics tests of the movement and weapons.
`RUST_REGIME_SCREENSHOT=shot.png cargo run --release` saves a frame and quits (handy with Xvfb + lavapipe on a box with no GPU).

## Controls
<!-- controls:start -->
**On foot**

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Move / steer | W, A, S, D | Left stick |
| Jump / wall jump / double jump | Space | A |
| Crouch / slide | Ctrl, Shift, C | B, L3 |
| Fire | Left mouse | RT |
| Aim down sights | Right mouse | LT |
| Reload | R | X (tap) |
| Enter / leave a vehicle or ship | E | X (hold) |
| Grapple | G, Mouse 4 | LB |
| Last weapon | Q | Y |
| Next weapon | Wheel down | RB, D-pad right |
| Previous weapon | Wheel up | D-pad left |
| Knife (draw / put away) | X | R3 (hold) |
| Weapon 1-10 | 1 - 9, 0 |  |
| Inspect weapon | V | D-pad down (tap) |
| Swap shoulder (third person) | Z | D-pad down (hold) |
| First / third person | T | R3 (tap) |
| Respawn | Backspace | View |
| Menu | Escape | Start |

**Flying**

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Thrust / reverse | W, S | RT, LT |
| Lift / sink | Space, Ctrl | Right stick up / down |
| Roll | A, D | Left stick left / right |
| Pitch (pull back: nose up) |  | Left stick up / down |
| Yaw |  | LB, RB |
| Boost | Shift | A |
| Fire | Left mouse |  |
| Missile (hold a ship in the nose to lock) | Right mouse |  |
| Stop (match ground speed) | X | Y |
| Look around (hold) | Alt | B |
| Enter / leave a vehicle or ship | E | X (hold) |
| First / third person | T | R3 (tap) |
| Respawn | Backspace | View |
| Menu | Escape | Start |

**Menus** follow the same buttons: arrows or WASD (d-pad) move, Enter or Space (A) select, Esc (B or Start) backs out, Q / E (LB / RB) change weapon at the quartermaster.
<!-- controls:end -->

## Menus
The game boots to a title screen over the live world; Esc pauses (time stops, the cursor comes
back). Both lists lead to the same screens: **Wardrobe** (character, head, colours, camo, skin, gloves, boots, webbing, metal, lights, visor, wear and three presets, shown on a mannequin), **Settings** (mouse sensitivity, invert Y, FOV, five volumes, sky, bloom, ambient
occlusion, anti-aliasing, shadow distance; saved to `settings.toml`, which lays over
`tuning.toml` so F5 keeps your choices), **Maps** (the solar system) and **Controls**; paused in the
solar system, also **Starmap**, **Ship** (your ships, the Kestrel's parts and modules, and its
two module slots: A/D steps a slot through the modules you own), **Contracts** and **Standing**
(a bar per faction, the word for it and what it gets you). The paused list's hint strip shows
your bank and your scrap. Navigate with W/S or arrows, adjust with
A/D, Enter picks, Esc backs out; the d-pad, A and B do the same on a pad; the mouse works too.
`RUST_REGIME_MENU=title|pause|maps|settings|controls|quartermaster|wardrobe|starmap|ship|contracts|standing|parts|play` opens straight into a screen
(with `RUST_REGIME_SCREENSHOT` it skips the title unless set). Design notes:
`docs/superpowers/specs/2026-10-18-menus-design.md`.

## Weapons and the quartermaster
You start with one sidearm, bare, and a knife: the **Warden** revolver or the **Smite** pistol, whichever
your character carries (`start` in `assets/characters.toml`). The **Talon** knife is on X (R3 held on a pad;
the same key puts it away) and cuts what is within arm's reach. Every other gun and every attachment is
bought from the Roost's **quartermaster** with banked money (see Money for how you earn it): walk up and press E, which also tops up your health and ammunition. At the counter Q / E (LB / RB)
step through the guns and A / D through each gun's four attachment slots (parts change spread, recoil, rate,
velocity and damage and show on the viewmodel; stat bars compare the bare gun). Trying a part on is free;
Enter buys it, once, for every gun. Whatever is not bought comes off again when you leave. Prices live in
`src/quartermaster.rs`.

## HUD
Compass tape, health plate bottom left, movement readout (or ship
dials) bottom centre, weapon plate with slot pips, fitted parts and heat bottom right, and a
crosshair that opens with the gun's real spread. The Esc hint fades after a few seconds.
Flying, the ship card (hull in segments and the shield bar) and the guns card (nose gun heat,
red and OVERHEATED while they cool, and the missiles on the rails with the next one's reload)
take the health and weapon plates' places, which stay hidden until you are on foot again, the
SHOT DOWN pause and card included. Each enemy ship within 4 km (the nearest eight) carries a
diamond in its faction's colour with its type and distance, clamped to the screen edge like
the waypoints, hollow for a patrol that will not shoot you; the one in your nose gets a ring of ticks that light up as the missile lock
comes on and close into a solid ring once it is locked. Four white ticks flash round the nose
when your shots land, wider and red on a kill, and MISSILE LOCK / MISSILE! shows under the
compass while a Sentry has you locked or its missile is in the air. When your standing with a
faction changes, a short line under the bounty line says so (`REGIME -25  SCRAPPERS +5`), and
salvage taken aboard gets one under that (`+4 SCRAP`, `MODULE FOUND  AFTERBURNER`, `HOLD FULL`).
The bank, your unbanked pocket and the hold show top right (`BANK 750 +120   SCRAP 12/60`) and in
the flight readout.

## Movement
- **Source/TF2 core** at 66 ticks/s: ground friction and acceleration, air strafing (30u air cap), bunny hopping (jump on the landing tick to skip friction), crouch-jumping (legs tuck up in the air), ramp sliding and surfing on steep slopes, stair stepping.
- **Parkour**: wall run (run along a wall in the air while holding forward), wall jump (jump off a wall, alternate walls to climb), mantle (push into a ledge up to 1.5 m above your feet), slide (crouch while running, faster downhill).
- **Double jump**: one extra jump in the air, which can bend your momentum toward where you push. It comes back when you touch ground, a wall, a ledge or a grapple anchor.
- **Grapple** (the pilot class ability): G fires a hook at anything within 30 m. You are pulled toward it, the pull bends toward where you look, gravity keeps working so looking below the anchor swings you. Press again or jump to let go and keep all your speed; jumping off adds a boost. It runs on a power meter like Titanfall 2's, tuned under `[grapple]` to be nearly free.
- **Rocket jumps**: rockets knock you and props around. Aim at your feet and jump.

## Characters, factions and classes
Twelve characters in four factions, all our own, built in code with headless Blender like the
guns: the **Regime** (a death cult that worships the Algorithm: Acolyte, Zealot, Choir), the
**Scrappers** (luddite tinkerers: Mechanic, Bruiser, Trapper), the **Deserters** (ex-cult parkour
pilots, your side: Runner, Breaker, Ghost) and the **PMC** (contractors who sell to everyone:
Contractor, Juggernaut, Handler). `tools/character/build.sh [ids] [--no-bake] [--preview]
[--check]` sets up `bpy` on Python 3.11 and writes one `assets/models/character/<id>.glb` per
character from `tools/character/chars/<id>.py` and the shared kit (`kit.py`). Each has its own
body and proportions on one 22-bone skeleton, baked edge wear and dirt, and three skinned meshes
(`mesh.body`, `mesh.head`, `mesh.arms`). `--check` verifies bones, meshes, clips and the triangle
budget. Design notes: `docs/superpowers/specs/2026-10-18-character-roster-design.md`.

The twenty clips come from `tools/character/anim.py`, which needs no Blender: idle, walk, run,
sprint, jump, fall and the backward death are CMU motion capture (`cmu.py` cut the takes into
`tools/character/mocap/`) retargeted onto each character's own skeleton; crouch, crouch walk, slide,
wall runs, mantle, grapple, double jump, the forward death and the seated clips are
hand-keyed; `reload` (arms only) and `fire` (added recoil) play over whatever the body does.
In every clip both arms are solved frame by frame onto the gun (`anim.GUN_CARRIES` says where
the gun sits against the chest in each carry; the character's own `<id>.grips.toml` says where
its palms sit on that gun), so the third-person weapon stays out of the torso.
`python3 tools/character/glbanim.py [ids]` rewrites the clips in the glbs in seconds (a full build
runs it too). In game, `RUST_REGIME_SCREENSHOT_POSE=<clip>` holds the player's body in a clip for
third-person screenshots.

`assets/characters.toml` holds each character's faction, default colours and the weapon bots
wearing it carry, which factions each soldier team fields (team 0 is your side: Deserters; team 1
the Regime, Scrappers and PMC), and the classes (character, ability, health). Edit it and press F5.
The locker at the base camp opens the wardrobe: up/down picks a slot, left/right changes it, R rolls
a random look, Tab switches between three saved presets, E saves to `save.toml`. The slots are the
character, a borrowed head (any other character's helmet or hood), the three cloth colours, a camo
print over the main cloth (woodland, digital, tiger, hex, splinter), skin tone, gloves, boots,
webbing, metal finish, the lights' colour (or off), visor tint and a wear level from clean to
battered. Every slot defaults to the character's own look, so old saves are unchanged. Your body stands under the camera, so you see your legs when
you look down and your shadow on the ground; head and arms are drawn only into the shadow map.
In first person a second copy of your character shows just its arms, with both hands placed on
the current weapon every frame (two-bone IK on hand points in `character::hands`), so the arms
follow every weapon clip.

## Weapons
| Slot | Weapon | Notes |
|---|---|---|
| 1 | Rocket launcher | Slow projectile, splash knockback on you and props |
| 2 | Rifle | Automatic, fast bullet, tight spread |
| 3 | Shotgun | 10 pellets, wide spread, big push on props, short range |
| 4 | Pistol | Semi-automatic, one shot per click, accurate |

Hits push physics props. Each gun has its own `[rifle]`,
`[shotgun]`, `[pistol]` table in `tuning.toml` (damage, cooldown, pellets, spread,
range, prop impulse, automatic, recoil kick).

Rifle, shotgun and pistol fire real bullets: they drop, slow down, take time to arrive. Wood walls, crates and thin metal let them through
with less damage, stone and concrete stop them.
Recoil climbs with sustained fire and settles when you stop; aiming down sights
zooms in and tightens the spread.

## Survival and the world
- **Health**: heavy hits make you bleed until a medkit. Health regenerates only up to 60% and not while bleeding.
- **Save**: banked money and your unbanked pocket, what you own, ships shot down (by faction), times you were shot down, your standing with each faction and your salvage (scrap, the Kestrel's part levels, the modules you own and the two fitted) persist in `save.toml` next to the binary (`RUST_REGIME_SAVE` overrides the path).
- **Sound** is synthesized at startup. Put a CC0 `.ogg` with the same name in
  `assets/sounds/` (rifle, shotgun, pistol, rocket, explosion, hit, hurt, jump, land,
  wind, ship_gun_0..2, missile_launch, shield_hit, hull_hit, lock_beep, lock_tone,
  missile_warning) to replace one. In a ship fight you hear the nose guns (other ships' quieter
  with distance), missile launches, wrecks (the explosion, deeper) and missile bursts, a crackle
  on your shield and a clang through to the hull, lock beeps that climb as the lock fills and a
  steady tone once locked, and a chirp while an enemy missile is on you. Sound does not carry in
  vacuum: outside the ship, things are as loud as the air around you lets them be (nothing on
  Frost or in space), while your own cockpit's sounds always play.

All numbers live in `tuning.toml`.

### Solar system
`./play.sh` (`play.bat` on Windows) starts you on a landing pad on
Haven, a 17.5 km world with seas, beside your ship. Press E to board. The mouse pitches
and yaws, A and D roll, W and S thrust, Space and Ctrl lift and sink, Shift boosts (from a
tank that refills), X stops, held Alt looks round, T swaps cockpit and chase view, and E
steps out once you are under 20 m/s. Flight assist holds you up and levels you (never against
the stick) below about 3 km, fading out by 3.5 km, and slows the last metres of a descent to
a soft touchdown, so landing is sinking onto flat ground. Boosting is capped by your height
over the ground and reaches 6 km/s in space; thick air drags and heats the nose. Flight mouse
and stick sensitivity are in Settings.

Four ships stand on the apron, one per faction, each with its own handling from
`assets/ships.toml`: the Deserters' **Kestrel** (yours, nearest the spawn: a patched
gunship, the all-rounder), the Regime's **Litany** (a 22 m spire-finned cathedral: fast
in a straight line, slow to turn), the Scrappers' **Mule** (a welded hauler with twice the
lift and half the speed) and the PMC's **Vantage** (a faceted interceptor: light and
quick). Every hull is hollow: walk up the rear ramp into a furnished cabin (jump seats
and lockers, pews and an altar, a cargo hold, a two-seat cockpit) and E takes the pilot's
seat; the ramp swings shut in flight, and when you stand up again you are back on the
cabin floor, which is also where you respawn. Their hulls are built in code with headless
Blender like the weapons: `tools/ships/build.sh [ids] [--no-bake] [--preview] [--check]`
writes `assets/models/ships/<id>.glb` (under 30 k triangles and one 1024² baked texture
each) from `tools/ships/ships/<id>.py`; the game finds each engine's `exhaust.<n>` node,
the `heat` node and the `ramp` hinge by name, and the collision boxes in `ships.toml` are
the floor, walls, ceiling and open ramp you walk between. The four enemy fighters (the
raiders' **Jackal**, the PMC's **Sentry**, the Regime's **Censer** and the Scrappers'
**Welder**) are `kind = "fighter"` entries: solid hulls with one collision box and no cabin,
which you cannot board. A Jackal stands on a slab of its own 60 m south of the pad, toward
the Roost; `RUST_REGIME_FIGHTER=<id>[,<metres>]` parks that fighter (`jackal`, `sentry`,
`censer`, `welder`) in front of you instead, 80 m off unless told otherwise.
**Ship combat** (stage 1 of `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`):
every ship has a shield over its hull and a faction, from `ships.toml`. The Kestrel's two nose
guns fire in turn on the left mouse button (1.2 km/s tracers converging 400 m ahead, 12 damage,
2 km range); a heat meter stops them for a few seconds if you hold on too long, and shots never
hurt your own side. Damage takes the shield first, which comes back after 5 s without a hit; a
hull at zero blows the ship apart, so the parked Jackal can be shot down. The numbers are in
`[ship_combat]` in `tuning.toml`. `RUST_REGIME_SCREENSHOT_FIRE=1` holds the trigger for
screenshots, e.g. with `RUST_REGIME_AT=home,600 RUST_REGIME_FIGHTER=jackal,150`.
**Homing missiles** (`solar::missile`): every ship with guns carries four, and gets one back
every 10 s. Hold a ship of another side within 6° of the nose for 1.2 s and it is locked; let it
slip out of that cone and the lock is gone. Right mouse fires one at the locked ship, or straight
ahead with no lock. It speeds up until it is 600 m/s faster than you were, steers by
proportional navigation a moment behind (0.4 s) and never faster than 1.4 rad/s, so a hard, late
break can shake it; it loses a target more than 60° off its nose, bursts on the ground or
anything it touches, within 8 m of its target or after 8 s, and does 80 damage, shield first,
never to its own side. The Sentry (`ai = { missiles = true }`) flies with them: while it has one
it holds its nose on you and fires once locked. `RUST_REGIME_SCREENSHOT_MISSILE=<seconds>` presses the
missile trigger once a lock is complete and that many seconds of the run have gone, e.g. with
`RUST_REGIME_AT=home,600 RUST_REGIME_FIGHTER=welder,900`.
**Enemies** hunt ships, never you on foot. While you fly, **raiders** come in packs of two to
four Jackals every minute and a half or so (sooner the longer you go without a fight), 1.5 to
3 km off to one side and never ahead of your nose, but not in the first minute after you board
or within 3 km of a base; one that falls 6 km behind is gone. Each faction base but the Roost
keeps **two patrols** up while you are within 8 km (Censers over the Reliquary, Welders over the
Yard, Sentries over Site Vantage), circling it 300 m up; they come for you inside 2.5 km of it,
let you go past 4 km, and one shot down is back after ten minutes. At most eight enemy ships fly
at once. Each is flown by `solar::ai` through its own stick, with the same flight model, boost
tank and flight assist as yours: it leads its shots, fires inside a small cone, breaks off after
a pass, and keeps off the ground. How each hull fights is its `ai` entry in `ships.toml` (the
Jackal rushes in and runs at 30% hull, the Sentry stands off at 600 m, the Censer makes long
strafing passes and wide turns, the Welder closes right in); the rest is in `[ship_combat]`.
`RUST_REGIME_RAIDERS=1` sends a pack at once, and `RUST_REGIME_SCREENSHOT_LOOK=<yaw>,<pitch>`
(degrees, or `enemy` for the nearest enemy) holds the flight view looking round, e.g.
`RUST_REGIME_AT=home,1500 RUST_REGIME_RAIDERS=1 RUST_REGIME_SCREENSHOT_LOOK=100,10`.
**Bounty and loss:** an enemy you shoot down pays a bounty into your pocket (Jackal $60, Sentry
$120, Censer $150, Welder $200) with a `+$60 BOUNTY` line over the HUD, and counts in the save's
`kills` and its faction's tally; a kill by anyone else pays nothing. If your own ship is shot
down, the camera holds on the blast for three seconds under a SHOT DOWN card, then you are back
on the Roost's apron at Haven, from anywhere in the system, in a fresh Kestrel on the pad. It
costs what was aboard (the unbanked pocket, the hold's scrap and the courier parcel) and a rebuy
fee from the bank (see Money), and counts in `deaths`; your guns, parts, modules and engine tune
are kept. The timings are in `[ship_combat]`. `RUST_REGIME_DIE=<seconds>` shoots down the ship you fly after that long, for
screenshots of the card.
**Faction standing** (stage 2, `docs/superpowers/specs/2026-10-29-ship-combat-stages-2-3-design.md`,
`solar::standing`): the Regime, the Scrappers and the PMC each think of you from -100 to 100,
and you start a stranger at -20 with the Regime and the PMC, but at 0 with the Scrappers, old
friends of the Deserters, whose patrols let you pass until you give them a reason (the starts are
`standing_start`); the Deserters are your own side, fixed at 50.
A parcel delivered to a faction's base is +10 with it, a raider you shoot down +2 with each of
the three, one of a faction's ships shot down -25 with it and +5 with each faction holding a
grudge against it (the Regime hates the Deserters and the Scrappers, the Scrappers the Regime and
the PMC; the PMC holds none), and your first hit on one of its ships in a fight -3 (a kill after
it costs 25 in all). Below where it started it creeps back a point a Haven day. A patrol attacks you only
while its faction is below 0, or once you have shot it, until it lets you go; at 0 or above it
flies past and its diamond is hollow. At -60 or below the faction **hunts** you: two or three of
its patrol hulls come in like raiders, on their own clock at the raiders' rate. At its base,
standing sets the price of what it sells (15% off at 40 or above, 15% on below -40), at -60 or
below it will not serve you at all (the prompt says so) except at a courier desk, which always
hands out parcels, and a parcel to a base at 40 or above
pays 20% more. The Roost is never affected. Pause > **Standing** shows where you stand; the
numbers and the grudges are in `[ship_combat]`. `RUST_REGIME_STANDING=regime:50,pmc:-70` sets
standing at startup for screenshots (it is saved with the next save, so pair it with
`RUST_REGIME_SAVE`).
**Money** (`docs/superpowers/specs/2026-10-29-economy-design.md`, stage A, `solar::economy`):
what you earn in the field is at risk until you walk it into a base. Bounties go into your
**pocket**; walk up to the door of any base that will serve you and it banks (`Banked $120`).
Scrap rides in the **hold**: 60, and 20 more a level of hull plating; once it is full, scrap in
reach stays out there. Shot down, you lose the pocket, the hold and the parcel, but never the
bank: a fresh Kestrel costs a **rebuy fee** of a tenth of what the engine tune and parts on it
are worth (parts count their scrap at $6), at least $100 and at most $1500, and never more than
the bank holds. Reaching a base's door also **repairs** the hull of the ship you landed, if it is
parked within 400 m, at $1 a point (priced by your standing there) as far as the bank goes. The
Yard's parts rack **buys scrap** at $6 each ($7 to a friend, $5 below -40). Every price in the
game is in `[economy]` in `tuning.toml`.
**Job boards** (stage B, `solar::board`): every base has a board just inside its door, and Site
Vantage's courier desk is one too. E opens it (W/S to pick, Enter to take). It holds three offers
a game day (48 minutes), the same however often you look: a **courier** parcel for another base's
door ($250 and $3 a km between the worlds, half again to a faction whose patrols shoot you), a
**cull** of 4 to 8 raiders shot down by your ship ($50 each, into the pocket on the last one, on
top of the bounties), and on some days a **supply run** of 20 to 40 scrap brought back to that
board (never at the Yard). You carry two jobs at a time, each due by the end of the next day. A
parcel let lapse or lost with your ship costs 5 standing with whoever gave it to you; culls and
supply runs are not cargo and survive being shot down. Vantage's board buys scrap at $4. Your jobs
show in the flight readout and Pause > Contracts, and a base's marker says DELIVER HERE or HAND IN
when one is for it. `RUST_REGIME_MENU=board` (with `RUST_REGIME_BOARD=<base id>`) opens a board
for screenshots.
**Salvage** (stage 3, the same spec, `solar::salvage`): an enemy ship shot down, by you or by
anyone else, drops **scrap** where it blew apart (Jackal 2, Sentry 4, Censer 5, Welder 8): a few
glowing orange chunks that drift on with the wreck's velocity, slowing in air and coming to rest
on the ground, for 90 s. Fly within 40 m and the ship pulls it in (never on foot), with a clink
and a `+4 SCRAP` line. Your own side's wrecks, your own ship included, drop nothing, and salvage
left behind when you cross into another world's sphere of influence is gone. Scrap is spent at
the Yard's **parts rack**, beside the tuning rig: E opens the parts menu (W/S to pick, Enter to
buy) with four permanent upgrades for the Kestrel, three levels each, on top of its own numbers
and the engine tune: **hull plating** (+25 hull a level; 12 / 24 / 40 scrap), **shield cell** (+15
shield and 20% faster back; 12 / 24 / 40), **gun capacitor** (the guns heat 20% slower and cool
20% faster; 10 / 20 / 32) and **missile rack** (+1 missile, back 1.5 s sooner; 15 / 30 / 50). Its
prices follow your standing with the Scrappers like the rest of the Yard's, and at -60 it will
not sell. A quarter of the time a wreck also drops its hull's own **module**, a cyan box, picked
up the same way and kept for good (a spare is 10 scrap); two fit at a time, from Pause > Ship,
and each has a cost: the Jackal's **afterburner** refills the boost tank 40% faster for 10% less
shield, the Sentry's **targeting array** locks in 0.8 s but in a cone 4 degrees tighter, the
Censer's **spire coil** fires shots 25% faster and 15% harder but heats the guns 20% faster, and
the Welder's **ram plate** hurts an enemy you fly into for 30 for 10% less thrust. Parts and
modules are kept when you are shot down. The numbers are in `[ship_combat]`. For screenshots,
`RUST_REGIME_SCRAP=<n>`, `RUST_REGIME_PARTS=1,2,0,3` (the four levels) and
`RUST_REGIME_MODULES=afterburner,spire` (owned, the first two fitted) set the save at startup
(pair them with `RUST_REGIME_SAVE`).

Each faction has a base on its world, from `assets/bases.toml` and
`assets/models/bases/<id>.glb` (built like the ships: `tools/bases/build.sh [ids]
[--no-bake] [--preview] [--check] [--toml]`, each under 115 k triangles with one 2048² baked
texture, and `--toml` rewrites `bases.toml` from the SPEC in `tools/bases/bases/<id>.py`,
which is the single source of truth for a base's site and collision boxes). The Deserters'
**Roost** stands on the flat south-east of Haven's apron past the course: a two-storey hangar
with a mezzanine catwalk, a roof deck with a sandbag nest and an outside switchback stair.
The Regime's **Reliquary** on Bastion is a slate basilica up a flight of steps: nave, side
chapels, bell tower and spire, pews and an altar inside. The Scrappers' **Yard** on Cinder
is a fort of welded containers round a workshop shed, with a gantry crane and a lookout
derrick. The PMC's **Site Vantage** on Frost is three white hab modules on jacks joined by
link corridors, with an airlock, a radar dish and floodlights. Every base is hollow and
walkable (floors, walls, roofs and stairs are collision boxes; the fittings are not), lit
inside by its own lamps, and stands on a buried foundation slab with a landing pad in front
of its door (the Roost uses the apron). Only the world you are on has its base spawned; the
flight readout names it and how far it is.
**Waypoints** mark them from anywhere: a diamond in the faction's colour (Deserters green,
Regime red, Scrappers yellow, PMC blue; your parked Kestrel white) with the name and the
distance, clamped to the screen edge when it is off-screen or behind you, and a tall beam of
light over each base on the world you are on. A base on another world is marked at that
world's centre. Markers hide within 30 m and under the menus. `RUST_REGIME_AT=<base>,<altitude>` (`roost`,
`reliquary`, `yard`, `outpost`) starts you flying over its pad.
**Each base has a job**, done with E at a station inside its annex (listed in `bases.toml`, paid
from the banked money in `save.toml`): the Roost's quartermaster resupplies health and ammunition
for free and its hangar locker opens the wardrobe; the Yard's tuning rig upgrades the Kestrel's
engines (three levels, $300 / $700 / $1400: more thrust and top speed, a little sharper
turning) and its parts rack sells the Kestrel's parts for scrap and buys your scrap (see Salvage
and Money); Site Vantage's courier desk opens its job board (see Job boards; deliver a parcel by walking
up to the destination's door, which is marked DELIVER HERE); the Reliquary's shrine sells a blessing for a $150 tithe (+50 health for
five minutes). Those prices move with your standing with the base's faction, which may also
refuse you (see Faction standing). Every base's door banks your pocket and repairs your ship. The flight readout shows what is in reach, your bank and scrap, and the parcel you carry.

Everything is in `assets/system.toml`: a star, Haven and its low-gravity moon Ash, and
the three faction worlds, Bastion (Regime: heavy, slate, thin pale air), Cinder
(Scrappers: rust desert, dusty orange sky) and Frost (PMC: airless ice). They orbit and
spin on analytic clocks, so day and night are Haven turning and the other worlds cross
the sky where you will find them. Physics runs in the frame of the world whose sphere of
influence you are in; flying into another one hands the ship over to its frame with the
same path and speed, its ground streams in, and your old world shrinks to a coarse mesh in
the sky. The top left reads where you are, your height, speed and gravity, and how far
every other world is. `RUST_REGIME_AT=<world>,<altitude>[,<speed>]` starts you flying over
any world, for screenshots (`home`, `ash`, `bastion`, `cinder`, `frost`), or over a base.
`RUST_REGIME_NEAR=1` prints a `NEAR` line the first time a boxy mesh looms over the camera (over a
degree across, within 50 km: name, parents, size, colour) and a `STARS` line if the star shell drifts
off the camera, to name a stray box seen in flight.

Not in yet: swimming and buoyancy (the seas are only drawn) and Coriolis drift.

## Assets
The character and clothes are generated by our own Blender script (see above).
They live in `assets/models/` and must sit next to the binary. The rocket launcher
viewmodel and the effects are generated meshes. 
