# Character roster: four factions, twelve characters, first-person arms

Agreed with Q on 2026-10-18 in the "character redesign" thread. Replaces the two placeholder
outfits (runner, soldier) from the 2026-10-17 character spec with a full roster built to the same
detail and look as the custom weapons (2026-10-18-custom-weapons-design.md): bevelled hard-surface
parts, cut panels, screws, straps, raised markings, baked edge wear and cavity dirt. Our own designs,
built in code with headless Blender, free and reproducible.

## Factions

| Faction | Idea | Visual language |
|---|---|---|
| Regime | Hyper-militaristic death cult that worships the Algorithm | Bone-white polymer plate etched with black code "scripture", uplink antennas worn like halos, glowing sensor slits. Grunts are faceless; elites show augmented faces. |
| Scrappers | Luddite tinkerers, repulsed by the Regime's ideas | Analog and handmade only: leather, brass gauges, riveted steel frames, hand-painted symbols. No screens, no chips, nothing glowing. |
| Deserters | Ex-cult parkour pilots who broke away (the player's side) | Regime plate with the uplinks torn out and the code scratched off and repainted, faces showing again, climbing and parkour gear. Palette (Q's ask): Anthropic-style warm colours, near-black slate `#141413` primary, clay orange `#D97757` accent, cream `#F0EEE6` and kraft `#D4A27F` secondaries. Colours only, no logos. |
| PMC | Corporate contractors who sell to every side | Slick branded tactical kit: plate carriers, sponsor patches, corporate logo, headsets, clean colour blocking. |

## Characters

Characters are looks only. Loadouts are separate: any character carries any of the ten weapons from
the gunsmith. Bots get a default loadout per faction (listed for bots only).

| Faction | Character | Look | Bot default |
|---|---|---|---|
| Regime | Acolyte | Faceless grunt: sealed bone-white helmet with a sensor slit, code-etched plate, uplink backpack | rifle |
| Regime | Zealot | Augmented officer: bare head with skull ports and barcode tattoos, robe over plate, halo antenna crown | revolver |
| Regime | Choir | Tall faceless sniper: multi-lens helmet, antenna array on the back | dmr |
| Scrappers | Mechanic | Welding goggles, leather apron, tool belt, brass wrist gauge | shotgun |
| Scrappers | Bruiser | Riveted exo-frame with piston arms over work clothes | fist |
| Scrappers | Trapper | Oilskin coat, rope coils, nets, brass spyglass | harpoon |
| Deserters | Runner | Today's runner taken further: hood, torn-out uplink stub, climbing gear, grapple launcher | smg |
| Deserters | Breaker | Heavier scratched-off Regime plate, repainted | grenade |
| Deserters | Ghost | Light scout: cloak, cracked Regime mask | pistol |
| PMC | Contractor | Branded plate carrier, sponsor patches, cap and headset | rifle |
| PMC | Juggernaut | Full heavy armour with the corporate logo | rocket |
| PMC | Handler | Drone operator with a wrist tablet | smg |

The player's default is the Runner (class `pilot`). The wardrobe can wear any character and still mix
single slots and colours, so a Deserter can wear a stolen Regime helmet.

## Model pipeline

- Same shape as the weapon kit: `tools/character/kit.py` (skeleton, shared body, part helpers, bake,
  export, checker) plus one module per faction, `tools/character/factions/<faction>.py`, each building
  that faction's parts. `tools/character/build.sh [factions] [--no-bake] [--preview] [--check]`.
  The current 810-line `build.py` is split into this; its clips and arm solver move to the kit.
- One file, `assets/models/character/character.glb`, as today: the shared 22-bone skeleton, a new
  higher-detail base body (one shared athletic build, 1.80 m), and every part as
  `<slot>.<style>` skinned to it. New styles are named for their character (`head.acolyte`,
  `torso.zealot`, `hands.bruiser` ...). The old styles are dropped.
- Faces: stylised hard-surface heads, not sculpted portraits. Tattoos, ports and scars come from the
  bake and small modelled inserts.
- Detail budget: 30-70k triangles per complete character. One baked 2048 texture per faction.
- Tinting stays: cloth regions are baked near-white with wear and dirt, and the game multiplies the
  outfit's `primary`, `secondary`, `accent` colours over them, so wardrobe colours keep working.
  Fixed materials (metal, brass, glass, emissive slits) carry their own colour.
- Skeleton, bone names and the 12 clip names stay exactly as they are, so movement, animation and
  gameplay code keep working. The clips are re-keyed only where new silhouettes need it.
- The baked-in `weapon.rifle` part goes away. The third-person character holds the real weapon glb on
  `prop_r_hand` in the existing two-hand carry pose (the fist is worn on the right hand).
- `--check` verifies bones, clips, every part named in characters.toml, triangle budget per character.

## First-person arms

- Each character's arm parts double as its first-person arms: the build splits the arm portion of
  every torso and hands part (vertices weighted to upper_arm, forearm, hand) into `fp.<slot>.<style>`
  meshes, so the arms always match what you wear with no extra modelling.
- The viewmodel spawns a second character instance on the viewmodel layer with only the `fp.*` parts
  of the current outfit visible, shoulders anchored under the camera.
- Every weapon gets `hand_r` and `hand_l` sockets in its build script, parented to the bone the hand
  holds (left hand on the pump, foregrip or handguard), and is rebuilt. A two-bone IK in the game puts
  each hand on its socket every frame, so the arms follow every existing weapon clip, including reloads.
  Weapons without a sensible left-hand spot (pistol firing one-handed, fist) leave `hand_l` out and
  the left arm drops to a rest pose.

## Game side

- `assets/characters.toml`: one `[outfit.<character>]` per character plus `faction` and a bot `loadout`;
  `[faction.<id>]` lists its characters. Island soldier teams map to factions in the same file (team 0
  Regime, team 1 Scrappers by default; 6v6 sides configurable), and each spawned soldier picks one of
  its faction's characters.
- Wardrobe: a character picker on top of the existing slot and colour editing.
- Tests: baked outfits match the model, every outfit's parts exist, every weapon has `hand_r`,
  IK reaches its targets, faction mapping parses.

## Build order

1. Kit split and new base body (one person, everything else depends on it).
2. Four factions in parallel, one worker per faction file.
3. Weapon hand sockets and first-person arms.
4. Game wiring, tests, draft PR, refreshed `rust-regime-linux.tar.gz`.

Out of scope: new clips (seated, death), ragdolls, facial animation, faction story missions,
netcode.
