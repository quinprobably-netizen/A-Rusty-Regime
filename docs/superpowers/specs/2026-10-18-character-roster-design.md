# Character roster: four factions, twelve characters, first-person arms

Agreed with Q on 2026-10-18 in the "character redesign" thread. Replaces the two placeholder
outfits (runner, soldier) from the 2026-10-17 character spec with a full roster built to the same
detail and look as the custom weapons (2026-10-18-custom-weapons-design.md): bevelled hard-surface
parts, cut panels, screws, straps, raised markings, baked edge wear and cavity dirt. Our own designs,
built in code with headless Blender, free and reproducible.

> **2026-10-22:** the hand rig, grip frames and finger poses described below were rebuilt; see `2026-10-22-rig-rebuild-design.md` (open rest hands, palm frames, solved holds on every weapon).

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

The player's default is the Runner (class `pilot`). Every character has its own body (Q's call): its
own proportions and build, modelled as one piece with its gear. So parts no longer mix between
characters; the wardrobe picks a character and its three colours.

## Model pipeline

- Same shape as the weapon kit: `tools/character/kit.py` (skeleton builder, body helpers, part
  helpers, clips, arm solver, bake, export, checker) plus one module per character,
  `tools/character/chars/<id>.py`. `tools/character/build.sh [ids] [--no-bake] [--preview] [--check]`.
  The current 810-line `build.py` is split into this.
- One file per character, `assets/models/character/<id>.glb`: its own body and gear, skinned to a
  22-bone skeleton with the same bone names as today. Each character sets its own proportions (bone
  lengths, height 1.65-2.05 m, bulk); the kit builds the skeleton from those and keys the 12 clips on
  it, so every character runs the same animations. The gameplay capsule and hitbox stay the same for
  everyone. The old shared `character.glb` is gone.
- Faces: stylised hard-surface heads, not sculpted portraits. Tattoos, ports and scars come from the
  bake and small modelled inserts.
- Detail budget: 30-70k triangles per complete character. One baked 2048 texture per character.
- Tinting stays: cloth regions are baked near-white with wear and dirt, and the game multiplies the
  character's `primary`, `secondary`, `accent` colours over them, so wardrobe colours keep working.
  Fixed materials (metal, brass, glass, emissive slits) carry their own colour.
- Skeleton, bone names and the 12 clip names stay exactly as they are, so movement, animation and
  gameplay code keep working. The clips are re-keyed only where new silhouettes need it.
- The baked-in `weapon.rifle` part goes away. The third-person character holds the real weapon glb on
  its `prop_hand.R` grip frame in the two-hand carry pose (the fist is worn on the right hand).
- Each glb has three skinned meshes: `mesh.body`, `mesh.head` and `mesh.arms`. The player's own body
  draws head and arms only into shadow maps.
- `--check` verifies bones, clips, the three meshes and the triangle budget per character.

## First-person arms

- Each character's own arms double as its first-person arms: the build splits the arm portion of the
  model (vertices weighted to upper_arm, forearm, hand) into `mesh.arms`, so the arms always match
  who you are with no extra modelling.
- `src/arms.rs` spawns a second instance of the worn character under the camera with only `mesh.arms`
  visible, shoulders anchored under the eye and turned slightly so the left shoulder leads.
- Hand points live in code (`character::hands`), in each weapon's model space: the right fist's centre
  and the support hand's spot with the bone it rides (the shotgun's pump, else the weapon root). So the
  weapons did not need rebuilding. A two-bone IK puts each `prop_hand` grip frame on its point every
  frame, so the arms follow every existing weapon clip, including reloads. Pistol, revolver and fist
  have no support point and the left arm drops out of view.

## Game side

- `assets/characters.toml`: one `[character.<id>]` per character with `faction`, colours and a bot
  `loadout`; `[faction.<id>]` lists its characters. Classes point at a character instead of an outfit. Soldier teams map to factions in the same file
  (`[teams]`). Team 0 fights on the player's side, so it fields the Deserters; team 1 fields the
  Regime, Scrappers and PMC. Each spawned soldier picks one of its team's characters and carries
  that character's bot loadout.
- Wardrobe: pick a character, then its three colours. Saved choices from the old slot system fall
  back to the class default.
- Tests: every character in characters.toml has a glb with the shared bone, mesh and clip names,
  every weapon lands in the fist, the IK reaches its targets, the faction mapping parses.

## Build order

1. Kit split: skeleton from proportions, clips, bake, export, checker, rebuilt Runner as the reference
   character (one person, everything else depends on it).
2. The other eleven in parallel, one worker per faction.
3. Hand points and first-person arms.
4. Game wiring, tests, draft PR, refreshed `rust-regime-linux.tar.gz`.

Out of scope: new clips (seated, death), ragdolls, facial animation, faction story missions,
netcode.
