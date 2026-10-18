# Custom weapons: models, rigs and the new arsenal

Agreed with Q on 2026-10-18 in the "custom guns" thread. Q's references: a MAD.ASA concept
rifle (olive polymer, receiver dial, side window), a Smite 1911 long-slide pistol with stabilizer
and light, a grey/red Stinger bullpup SMG, and a scrap piston power fist with steam vents.
Look: clean sci-fi military guns plus scrap-built gadgets. Our own designs, not copies.

## Lineup (number keys)

| Key | Weapon | Kind | Notes |
|---|---|---|---|
| 1 | Rocket launcher | rocket | unchanged mechanics, new model, 4-round tube |
| 2 | MA-14 rifle | auto | from MAD.ASA: dial, side window, foregrip, top optic |
| 3 | Breacher shotgun | pump | drum mag, pump bone |
| 4 | Smite pistol | semi | long slide, stabilizer, rail light |
| 5 | Stinger SMG | auto | grey bullpup, red accents, skeleton handguard |
| 6 | Longshot DMR | semi | long barrel, scope, folded bipod; crouching cuts its recoil |
| 7 | Warden revolver | semi | top-break, 6 rounds, cylinder turns per shot |
| 8 | Thumper grenade launcher | grenade | break-action, bouncy frag on a fuse |
| 9 | Harpoon | harpoon | spear pulls soldiers to you, or you to the wall it hits |
| 0 | Power fist | melee | piston punch: knocks soldiers away, punch a surface to launch off it |

The first four keep their old slots so saved gunsmith loadouts stay valid.

## Models and rigs (the contract every weapon module follows)

- Build: `tools/weapons/build.sh <id>` runs `tools/weapons/guns/<id>.py` in headless Blender and
  writes `assets/models/weapons/<id>.glb`. `--check` verifies the rig straight from the glb,
  `--preview` renders `screenshots/weapons/<id>.png` (look-dev only, not shipped), `--no-bake` skips
  the wear bake. ids: rocket rifle shotgun pistol smg dmr revolver grenade harpoon fist.
- Shared code: `kit.py` (prism/plan/block/cyl/tube/ring, `cut` booleans, rail, screw, pin, slots,
  mlok, dimples, label, the Gun rig/clip/bake/export class) and `parts.py` (gunsmith attachments,
  `attachments()`, `common_clips()`, `mag_drop()`). `guns/pistol.py` is the reference weapon.
- Axes: metres, Blender Z up, the weapon points down +Y, trigger at the origin, bore usually at
  z 0.02-0.05. The first-person camera sees the LEFT side (-X) and the top, so markings and the
  richest detail go there; the right side still needs to read well in inspect.
- Detail: bevelled hard-surface parts, cut slots and ports, rail teeth, screws and pins, raised
  markings, stippling, see-through windows. Body budget 20-70k triangles (checker counts meshes
  that are not `att.*`). One baked 2048 texture per weapon: palette color + edge wear + cavity dirt.
- Rig: armature `rig` with `root` plus one bone per moving part, declared in `begin(id, bones)`
  as `{name: (pivot, parent)}`; bones point +Y with no roll, so a bone's local axes are the
  weapon's axes (translate y = along the barrel, rotate x = pitch about the pivot). Parts are
  rigidly parented with `g.add(obj, bone)`; the export is node animation, no skinning. Meshes come
  out as `mesh.<bone>`.
- Sockets via `g.socket`: `muzzle` (bore exit, where tracers and flash start) on every weapon that
  shoots; `eject` where it has a port; `optic`, `under`, `stock` on gunsmith weapons.
- Gunsmith weapons (rifle shotgun pistol smg dmr revolver) carry all eight parts
  `att.optic.reddot|scope`, `att.muzzle.comp|supp`, `att.grip.vertical|angled`,
  `att.stock.light|heavy` (a weapon may reinterpret one, e.g. the pistol's grip slot is a rail
  light and its stock slot an extended base pad). The bare gun's own pieces that a part replaces
  are optional meshes `att.optic.irons`, `att.muzzle.bare`, `att.grip.standard`,
  `att.stock.standard`; the game shows exactly the fitted part per slot, so flip-up irons vanish
  under an optic and the standard stock vanishes when a light or heavy one is fitted. The others
  (rocket grenade harpoon fist) have no parts.
- Clips, every weapon: `idle` (rest, loops), `fire` (one full shot cycle, the game speeds it up to
  fit the fire rate), `reload` (stretched to the reload time), `draw` (stretched to the swap time),
  `inspect`. Every clip keys every bone at rest at both ends (the kit does this), so no clip leaves
  a part displaced. The `root` bone carries whole-weapon motion (kick, reload tilt, draw, inspect).
- No first-person arms: those belong to the character work Q owns.

## Gameplay

- Every weapon gets `mag` and `reload` in tuning.toml; R reloads (reset moves to Backspace),
  firing an empty gun reloads it. Reserve ammo is unlimited.
- New kinds share the existing bullet, rocket and explosion code where they can.
