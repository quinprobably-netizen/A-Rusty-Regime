//! What persists between sessions, in `save.toml` next to `tuning.toml`: banked money, the outfit, the
//! loadout, the weapons and parts you own, the ship's tune, the courier parcel, the ships you
//! have shot down and lost, where you stand with each faction, and your salvage.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use bevy::prelude::*;
use serde::{Deserialize, Deserializer, Serialize};

pub struct SavePlugin;

impl Plugin for SavePlugin {
    fn build(&self, app: &mut App) {
        let file = app.world().get_resource::<SaveFile>().cloned().unwrap_or_default();
        let (save, writable) = file.read();
        // A save we could neither read nor move out of the way must not be written over: play on
        // in memory and leave the file for the player.
        let file = if writable { file } else { SaveFile(None) };
        app.insert_resource(file).insert_resource(save);
    }
}

/// Where the save lives; `None` keeps everything in memory (tests).
#[derive(Resource, Clone, Debug)]
pub struct SaveFile(pub Option<PathBuf>);

impl Default for SaveFile {
    fn default() -> Self {
        SaveFile(Some(std::env::var_os("RUST_REGIME_SAVE").map_or_else(|| crate::paths::file("save.toml"), PathBuf::from)))
    }
}

/// `path` with `suffix` on the end of its file name, in the same directory (`save.toml.bak`).
pub fn sibling(path: &Path, suffix: &str) -> PathBuf {
    let mut name = path.file_name().unwrap_or_default().to_os_string();
    name.push(suffix);
    path.with_file_name(name)
}

/// Writes `text` to `path` without ever leaving it half-written: into `<path>.tmp` beside it,
/// flushed to disk, then renamed over `path` (a rename within one directory is atomic). A crash
/// or a full disk leaves the old file whole.
pub fn write_atomic(path: &Path, text: &str) -> std::io::Result<()> {
    use std::io::Write;
    let tmp = sibling(path, ".tmp");
    let result = std::fs::File::create(&tmp).and_then(|mut f| {
        f.write_all(text.as_bytes())?;
        f.sync_all()
    });
    let result = result.and_then(|()| std::fs::rename(&tmp, path));
    if result.is_err() {
        std::fs::remove_file(&tmp).ok();
    }
    result
}

/// Moves an unreadable `path` aside to `<path>.broken-<unix secs>` so nothing writes over it,
/// and returns where it went.
fn move_aside(path: &Path) -> std::io::Result<PathBuf> {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_secs());
    let mut to = sibling(path, &format!(".broken-{secs}"));
    let mut n = 1;
    while to.exists() {
        n += 1;
        to = sibling(path, &format!(".broken-{secs}-{n}"));
    }
    std::fs::rename(path, &to)?;
    Ok(to)
}

/// Reads and parses a save, bringing it up to date.
fn parse(path: &Path) -> Result<(Save, String), String> {
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut save: Save = toml::from_str(&text).map_err(|e| e.to_string())?;
    save.migrate();
    Ok((save, text))
}

impl SaveFile {
    /// The save, or a fresh one; see `read`. (The game itself uses `read`.)
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn load(&self) -> Save {
        self.read().0
    }

    /// The save, and whether it is safe to write over the file.
    ///
    /// - No file: a fresh save.
    /// - A file that loads: that, and a copy of it as `save.toml.bak`. The backup is taken here,
    ///   once a session, rather than on every write, so it holds the last save that loaded and
    ///   not one a few seconds older than the file (which a bad session would soon overwrite).
    /// - A file that will not load (bad TOML, a field of the wrong type): moved aside to
    ///   `save.toml.broken-<unix secs>` and never written over, then `save.toml.bak` if that
    ///   loads, else a fresh save. If it cannot even be moved, the save is not writable.
    pub fn read(&self) -> (Save, bool) {
        let Some(path) = &self.0 else { return (Save::default(), true) };
        if !path.exists() {
            return (Save::default(), true);
        }
        let bak = sibling(path, ".bak");
        let error = match parse(path) {
            Ok((save, text)) => {
                if let Err(e) = write_atomic(&bak, &text) {
                    warn!("could not back the save up to {}: {e}", bak.display());
                }
                return (save, true);
            }
            Err(e) => e,
        };
        match move_aside(path) {
            Ok(kept) => warn!("{} will not load ({error}); it is kept as {} and will not be written over", path.display(), kept.display()),
            Err(e) => {
                error!("{} will not load ({error}) and could not be moved aside ({e}); playing without saving so it is not lost", path.display());
                return (Save::default(), false);
            }
        }
        if bak.exists() {
            match parse(&bak) {
                Ok((save, _)) => {
                    warn!("loaded the backup {} instead", bak.display());
                    return (save, true);
                }
                Err(e) => match move_aside(&bak) {
                    Ok(kept) => warn!("the backup {} will not load either ({e}); it is kept as {}", bak.display(), kept.display()),
                    Err(_) => return (Save::default(), false),
                },
            }
        }
        warn!("starting a fresh save");
        (Save::default(), true)
    }

    pub fn write(&self, save: &Save) {
        let Some(path) = &self.0 else { return };
        match toml::to_string(save) {
            Ok(text) => {
                if let Err(e) = write_atomic(path, &text) {
                    warn!("could not write {}: {e}", path.display());
                }
            }
            Err(e) => warn!("could not serialize the save: {e}"),
        }
    }
}

/// The save format; written into every save. A save with none is from before versions (0).
/// Bump it with each change `migrate` has to make to an older save.
pub const SAVE_VERSION: u32 = 1;

/// A save's format version: `SAVE_VERSION` for a new save, 0 for one written before versions.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
#[serde(transparent)]
pub struct Version(pub u32);

impl Default for Version {
    fn default() -> Self {
        Version(SAVE_VERSION)
    }
}

impl Version {
    fn unversioned() -> Self {
        Version(0)
    }
}

/// Reads a list one entry at a time, dropping (with a warning) any entry that will not parse
/// (a job of a kind this build does not know, say) instead of failing the whole save.
pub fn tolerant<'de, D: Deserializer<'de>, T: Deserialize<'de>>(d: D) -> Result<Vec<T>, D::Error> {
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Entry<T> {
        Good(T),
        Bad(serde::de::IgnoredAny),
    }
    let entries = Vec::<Entry<T>>::deserialize(d)?;
    let n = entries.len();
    let good: Vec<T> = entries.into_iter().filter_map(|e| if let Entry::Good(t) = e { Some(t) } else { None }).collect();
    if good.len() < n {
        warn!("dropped {} unreadable entries from the save", n - good.len());
    }
    Ok(good)
}

/// `tolerant` for each list in a map (the job boards).
fn tolerant_map<'de, D: Deserializer<'de>, T: Deserialize<'de>>(d: D) -> Result<BTreeMap<String, Vec<T>>, D::Error> {
    #[derive(Deserialize)]
    #[serde(bound = "T: Deserialize<'de>")]
    struct List<T>(#[serde(deserialize_with = "tolerant")] Vec<T>);
    Ok(BTreeMap::<String, List<T>>::deserialize(d)?.into_iter().map(|(k, v)| (k, v.0)).collect())
}

/// Reads a fixed-size array from a list of any length: missing entries are the default (0), extra
/// ones dropped, so a save from before a slot was added (or after one was removed) still loads.
fn padded<'de, D: Deserializer<'de>, T: Deserialize<'de> + Default + Copy, const N: usize>(d: D) -> Result<[T; N], D::Error> {
    let list = Vec::<T>::deserialize(d)?;
    let mut out = [T::default(); N];
    for (o, v) in out.iter_mut().zip(list) {
        *o = v;
    }
    Ok(out)
}

/// The one courier parcel a save from before the job boards carried.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct OldContract {
    pub to: String,
    pub pay: u32,
}

impl Save {
    /// Brings an older save up to date, a version at a step, and marks it current.
    ///
    /// - 0 (before versions, and before the job boards): its one parcel becomes a courier job
    ///   from Site Vantage (the only desk there was) that is never due. Every other field added
    ///   since loads as its default.
    pub fn migrate(&mut self) {
        if self.version < Version(1)
            && let Some(c) = self.contract.take()
        {
            self.contracts.push(crate::solar::board::Contract { job: crate::solar::board::Job::Courier { to: c.to }, from: "outpost".into(), pay: c.pay, due: None });
        }
        if self.version > Version(SAVE_VERSION) {
            warn!("the save is from a newer build (version {}); fields this build does not know will be lost", self.version.0);
        }
        self.version = Version(SAVE_VERSION);
    }
}

/// What persists between sessions.
#[derive(Resource, Serialize, Deserialize, Clone, Debug, Default, PartialEq)]
#[serde(default)]
pub struct Save {
    /// The format this save was written in (`migrate`); missing in a save from before versions.
    #[serde(default = "Version::unversioned")]
    pub version: Version,
    pub banked: u32,
    /// Money earned in the field and not yet banked (bounties): it banks at a base's door and is
    /// lost when your ship is shot down (`solar::economy`).
    pub pocket: u32,
    /// Clothes picked at the camp wardrobe, over the class default.
    pub outfit: Option<crate::character::OutfitDef>,
    /// The wardrobe's saved looks and which one `outfit` is.
    pub presets: Vec<crate::character::OutfitDef>,
    pub preset: usize,
    /// Gunsmith parts fitted to each weapon.
    pub loadout: Option<crate::gunsmith::Loadout>,
    /// Weapons owned, by id: the starter kit, then whatever the quartermaster has sold. Empty on
    /// worlds with no quartermaster (and in an old save, until the solar system grants the kit),
    /// where every weapon is yours.
    pub weapons: Vec<String>,
    /// Attachments bought, a bit per part in each slot (part 0, the bare gun's own, is always yours).
    #[serde(deserialize_with = "padded")]
    pub parts: [u8; 4],
    /// How far the Yard has tuned the Kestrel's engines.
    pub ship_level: u8,
    /// The jobs you carry (`solar::board`), and how many parcels have been delivered.
    #[serde(deserialize_with = "tolerant")]
    pub contracts: Vec<crate::solar::board::Contract>,
    pub contracts_done: u32,
    /// A save from before the job boards carried one parcel here; `migrate` makes it a job.
    #[serde(skip_serializing)]
    pub contract: Option<OldContract>,
    /// The job boards: each base's offers by base id, put up on game day `board_day`; the game
    /// day and the seconds into it; the seed every board is drawn from (0 until the first).
    #[serde(deserialize_with = "tolerant_map")]
    pub boards: BTreeMap<String, Vec<crate::solar::board::Contract>>,
    pub board_day: Option<u32>,
    pub day: u32,
    pub day_clock: f32,
    pub seed: u64,
    /// The Yard's scrap stockpile (`solar::economy`); `None` is full, at `[economy] yard_target`.
    pub yard_stock: Option<f32>,
    /// Fighters bought from the factions, by ship id, in hangar order (`solar::hangar`).
    pub hulls: Vec<String>,
    /// Enemy ships you have shot down, in all and by faction id (`combat::Faction::id`), and how
    /// often your own ship has been shot down.
    pub kills: u32,
    pub faction_kills: BTreeMap<String, u32>,
    pub deaths: u32,
    /// Your standing with each faction that has moved from where a stranger starts, by faction id
    /// (`solar::standing::get` reads it, falling back to `[ship_combat] standing_start`), and the
    /// game time toward the next day's slow recovery, s.
    pub standing: BTreeMap<String, i32>,
    pub standing_clock: f32,
    /// Salvage (`solar::salvage`): scrap picked up from wrecks and not yet spent, the level of
    /// each ship part bought with it (hull plating, shield cell, gun capacitor, missile rack), the
    /// modules found, by id, and the ones fitted (at most two).
    pub scrap: u32,
    #[serde(deserialize_with = "padded")]
    pub ship_parts: [u8; 4],
    pub modules: Vec<String>,
    pub fitted: Vec<String>,
    /// The posts you have come across (`solar::post`), as `<body>.<n>`: each has a waypoint.
    pub posts_found: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::solar::board::{Contract, Job};

    /// A fresh, empty directory for one test, and the save path in it.
    fn scratch(name: &str) -> (PathBuf, SaveFile) {
        let dir = std::env::temp_dir().join(format!("rust-regime-{name}-{}", std::process::id()));
        std::fs::remove_dir_all(&dir).ok();
        std::fs::create_dir_all(&dir).unwrap();
        let file = SaveFile(Some(dir.join("save.toml")));
        (dir, file)
    }

    fn files(dir: &Path) -> Vec<String> {
        let mut names: Vec<String> = std::fs::read_dir(dir).unwrap().map(|e| e.unwrap().file_name().to_string_lossy().into_owned()).collect();
        names.sort();
        names
    }

    fn rich() -> Save {
        let job = |job, from: &str, pay, due| Contract { job, from: from.into(), pay, due };
        Save {
            version: Version(SAVE_VERSION),
            banked: 1234,
            pocket: 56,
            outfit: Some(crate::character::OutfitDef::default()),
            presets: vec![crate::character::OutfitDef::default(); 2],
            preset: 1,
            loadout: Some(crate::gunsmith::Loadout { parts: vec![[1, 2, 0, 3]], tune: vec![[2, -1, 0, 4]] }),
            weapons: vec!["warden".into(), "knife".into()],
            parts: [1, 3, 0, 7],
            ship_level: 2,
            contracts: vec![job(Job::Courier { to: "yard".into() }, "outpost", 400, Some(3)), job(Job::Cull { need: 4, got: 1 }, "yard", 200, None)],
            contracts_done: 9,
            contract: None,
            boards: [("outpost".to_string(), vec![job(Job::Supply { need: 30 }, "outpost", 150, Some(4))]), ("yard".to_string(), vec![])].into_iter().collect(),
            board_day: Some(3),
            day: 3,
            day_clock: 12.5,
            seed: 0xdead_beef,
            yard_stock: Some(42.5),
            hulls: vec!["jackal".into()],
            kills: 7,
            faction_kills: [("raiders".to_string(), 5), ("pmc".to_string(), 2)].into_iter().collect(),
            deaths: 2,
            standing: [("regime".to_string(), -20)].into_iter().collect(),
            standing_clock: 3.25,
            scrap: 88,
            ship_parts: [1, 0, 2, 1],
            modules: vec!["afterburner".into(), "scanner".into()],
            fitted: vec!["scanner".into()],
            posts_found: vec!["home.2".into()],
        }
    }

    #[test]
    fn the_whole_economy_round_trips_and_leaves_no_tmp() {
        let (dir, file) = scratch("round-trip");
        let s = rich();
        file.write(&s);
        assert_eq!(file.load(), s);
        file.write(&s);
        assert_eq!(files(&dir), ["save.toml", "save.toml.bak"], "no .tmp left behind; the loaded save is backed up");
        assert_eq!(SaveFile(Some(sibling(file.0.as_ref().unwrap(), ".bak"))).load(), s, "the backup is the save");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_save_that_will_not_load_is_kept_and_never_written_over() {
        let (dir, file) = scratch("corrupt");
        let path = file.0.clone().unwrap();
        std::fs::write(&path, "banked = \"lots\"\n[[[nonsense").unwrap();
        let (save, writable) = file.read();
        assert!(writable);
        assert_eq!(save, Save::default(), "no backup: a fresh save");
        let names = files(&dir);
        assert_eq!(names.len(), 1);
        assert!(names[0].starts_with("save.toml.broken-"), "{names:?}");
        file.write(&rich());
        let kept = std::fs::read_to_string(dir.join(&names[0])).unwrap();
        assert_eq!(kept, "banked = \"lots\"\n[[[nonsense", "the broken save is untouched");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn the_backup_loads_when_the_save_will_not() {
        let (dir, file) = scratch("backup");
        let path = file.0.clone().unwrap();
        file.write(&rich());
        assert_eq!(file.load(), rich(), "a good load backs it up");
        std::fs::write(&path, "banked = [").unwrap();
        assert_eq!(file.load(), rich(), "the backup stands in for the broken save");
        assert!(!path.exists() && files(&dir).iter().any(|n| n.starts_with("save.toml.broken-")));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn an_old_or_odd_save_still_loads() {
        let (dir, file) = scratch("old-format");
        let path = file.0.clone().unwrap();
        std::fs::write(
            &path,
            "banked = 500\nparts = [1, 2]\nship_parts = [1, 0, 2, 1, 9]\n\n\
             [[contracts]]\njob = { courier = { to = \"yard\" } }\nfrom = \"outpost\"\n\n\
             [[contracts]]\njob = { cull = { need = 3 } }\nfrom = \"yard\"\npay = 90\n\n\
             [[contracts]]\njob = { smuggle = { to = \"moon\" } }\nfrom = \"yard\"\npay = 1\n\n\
             [[boards.yard]]\njob = { teleport = {} }\n\n\
             [[boards.yard]]\njob = { supply = { need = 20 } }\nfrom = \"yard\"\npay = 50\ndue = 4\n",
        )
        .unwrap();
        let save = file.load();
        assert_eq!(save.banked, 500);
        assert_eq!(save.version, Version(SAVE_VERSION), "an unversioned save is brought up to date");
        assert_eq!((save.parts, save.ship_parts), ([1, 2, 0, 0], [1, 0, 2, 1]), "short arrays pad, long ones truncate");
        assert_eq!(
            save.contracts,
            [
                Contract { job: Job::Courier { to: "yard".into() }, from: "outpost".into(), pay: 0, due: None },
                Contract { job: Job::Cull { need: 3, got: 0 }, from: "yard".into(), pay: 90, due: None },
            ],
            "missing fields default; a job this build does not know is dropped"
        );
        assert_eq!(save.boards["yard"], [Contract { job: Job::Supply { need: 20 }, from: "yard".into(), pay: 50, due: Some(4) }]);
        assert!(path.exists() && files(&dir).iter().all(|n| !n.contains("broken")), "nothing was moved aside");
        assert!(toml::to_string(&save).unwrap().contains(&format!("version = {SAVE_VERSION}")));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn atomic_writes_replace_the_file_and_leave_no_tmp() {
        let (dir, _) = scratch("atomic");
        let path = dir.join("settings.toml");
        write_atomic(&path, "a = 1\n").unwrap();
        write_atomic(&path, "a = 2\n").unwrap();
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "a = 2\n");
        assert_eq!(files(&dir), ["settings.toml"]);
        std::fs::remove_dir_all(&dir).ok();
    }
}
