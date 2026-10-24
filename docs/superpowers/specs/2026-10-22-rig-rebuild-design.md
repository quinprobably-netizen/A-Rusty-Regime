# Character rig rebuild

Decided 2026-10-22 in the "Character rerig" thread. Q's complaints after PRs #7-#11: the hands never
looked like they gripped the guns (fingers fell back to a fist, the first-person support hand floated
or crumpled, the left forearm filled the view) and scopes were unreliable. This rebuilds the hand rig
and the grip pipeline from the ground up; the body, garments, textures and clips are untouched.

## What was wrong

- The rest pose was a **closed fist** solved around a fixed cylinder, so every grip was "fist plus a
  delta". A finger the solver gave up on kept the fist, which rarely matched the gun. The
  first-person support hand did not use solved poses at all: it was the fist part-opened and cupped
  around a point (`arms::support_frame`, `fingers::opened`).
- The finger solver curled bone centrelines until a raycast touched the mesh. On thin or stepped
  parts (trigger guards, DMR grips, the harpoon) it missed and fell back.
- The left and right hands took different code paths in the game (`arms.rs` had a cradle/vertical/
  angled special case per hold), and third-person carries placed the support hand by a fixed offset,
  not where the gun actually is.
- The weapon's hip position put the handguard beyond the left arm's reach, so the arm stretched
  straight across the view.

## Rig contract (v2)

Bone names, counts and clip names are unchanged, so every character file, `characters.toml` and the
game's bone lookups keep working: 22 body bones, `prop_back`, `prop_hand.L/R`, and three bones per
finger `f_<thumb|index|middle|ring|pinky>.<1-3>.<L|R>` (52 deform bones).

- **Rest hands are open and relaxed**: MCP 12°, PIP 18°, DIP 8° of flexion, the thumb lightly
  opposed. Nothing is wrapped around anything at rest. A hand with no pose looks like a hand.
- **Finger bone rolls are consistent**: each finger bone's local +Z points out of the palm, so
  flexion is a positive rotation about local +X on both hands, and spread is about local +Z.
- **`prop_hand.X` is the palm frame**: origin on the palm's skin surface under the middle/ring
  knuckles (0.75 of the way from the wrist to the knuckles); +Y runs wrist to knuckles, +Z out of
  the palm, +X = Y x Z (toward the thumb on the right hand, the little finger on the left).
- **A hold is a cylinder**: the gun's grip, handguard, pump or foregrip is fitted as a cylinder
  (axis, radius) from the weapon mesh around the point in `assets/grips.toml`. The palm frame sits
  tangent to it (palm pad against the surface, the cylinder crossing the palm along the frame's X)
  on the side the hold approaches from, and the fingers wrap it in closed form from their measured
  lengths and radii. Only then are the joints nudged against the real mesh (opened until they clear
  it, closed until they touch, never more than 25° from the closed-form wrap). The right index lies
  on the trigger blade (`mesh.trigger`); `R_fire` pulls it 6 mm. The thumb crosses the far side of
  the grip, or lies along the frame on the support hand.
- **One pose format, one game path.** `assets/models/character/<id>.grips.toml` keeps its schema
  (`at`, `rot` = the palm frame in weapon space; three quaternions per finger over the rest pose) and
  keys (`R`, `R_fire`, `L`, `L_vertical`, `L_angled`). The game puts each `prop_hand` on its solved
  frame, first and third person, both hands, and sets the finger joints from the pose. The only
  fallback is `grip_rotation()` plus the table point for a weapon with no solved pose.
- **Third-person carries** are solved with the character's own loadout weapon: the right palm frame on
  the carry point and the left on where that weapon's solved `L` frame sits relative to `R`, so the
  support hand is on the handguard in every clip.
- **First person**: the hip rest position is brought in and left so the support hand reaches the
  handguard with a bent elbow; the elbow poles keep the forearms below the sight line. The support
  hand's fingers wrap from below so nothing crosses an optic.

## Build and checks

- `tools/character/build.sh <ids>` builds as before; `--grips <ids>` re-solves only the poses;
  `--hands <ids>` renders each hand on each weapon (headless Workbench, seconds) to
  `screenshots/characters/<id>-hands.png` for checking contact without running the game.
- `build.sh --check` verifies 52 bones, finger rolls (local +Z out of the palm), every weapon has
  every pose it needs and no pose is the rest fallback.
- Rust tests: the grips table parses, every shipped `<id>.grips.toml` has `R` and `L` for every
  two-handed weapon, `grip_rotation()` matches the v2 frame, the IK still reaches.

## Out of scope

Reload hand animation, death and seated poses, new weapons, scope rendering changes (the scope code
from PRs #7-#10 stays; the rig only has to keep the hands out of the sight line).
