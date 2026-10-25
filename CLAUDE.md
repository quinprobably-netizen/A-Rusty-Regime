# Rules for working on Rust Regime

## Asset licences (hard rule)
The game may be sold. Every third-party asset or dataset in it (models, textures, sounds, music,
fonts, mocap, code) must carry a licence that allows use in a commercially sold game: CC0, public
domain, MIT/BSD/Apache/zlib, CC BY (with credit), or terms that explicitly allow commercial
products (e.g. CMU mocap). Never use NC, ND, "personal use only", "editorial", ripped game assets,
or anything with an unclear licence. Before adding a third-party file, record it in `CREDITS.md`
(what, where from, licence, link). Assets we generate ourselves (Blender scripts, synthesized
sound) need no entry.

## Merging (standing approval from Q, 2026-10-25)
Merge your own PR without asking when it is a **simple fix**: it fixes a bug or makes a small
tweak to something that exists (a script, a number, a message, docs), changes roughly 100 lines
or fewer, adds no new feature, asset, dependency or save-format change, and `cargo test` passes
with the fix checked in the running game where it shows there. Say in the thread that it was
merged and what it fixed. Anything else (new features, levels, systems, larger refactors, or
anything you are unsure about) opens a PR and waits for Q's yes before merging.
