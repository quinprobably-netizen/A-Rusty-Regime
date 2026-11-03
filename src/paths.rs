//! Where the game's files live. `tuning.toml`, `settings.toml`, `save.toml` and `assets/` all sit
//! in one folder, the game root, found once at startup so the game runs from whatever directory it
//! is launched in (a desktop shortcut, the exe double-clicked, `cargo run`).

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use bevy::prelude::*;

/// The file that marks the game root.
const MARKER: &str = "assets/system.toml";
/// Set to a folder to use it as the game root ahead of the search.
const ROOT_ENV: &str = "RUST_REGIME_ROOT";

struct Root {
    dir: PathBuf,
    found: bool,
    searched: Vec<PathBuf>,
}

static ROOT: OnceLock<Root> = OnceLock::new();

fn root() -> &'static Root {
    ROOT.get_or_init(|| {
        let env = std::env::var_os(ROOT_ENV).map(PathBuf::from);
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        let exe = std::env::current_exe().ok().and_then(|e| e.parent().map(Path::to_path_buf));
        let searched = search_order(env.as_deref(), &cwd, exe.as_deref());
        match find_root(&searched) {
            Some(dir) => Root { dir, found: true, searched },
            None => Root { dir: cwd, found: false, searched },
        }
    })
}

/// The game root: the first folder holding `assets/system.toml`, else the working directory.
pub fn game_root() -> &'static Path {
    &root().dir
}

/// A file or folder in the game root, e.g. `file("tuning.toml")`.
pub fn file(name: &str) -> PathBuf {
    game_root().join(name)
}

/// The folders searched for the game root, for error messages.
pub fn searched() -> String {
    root().searched.iter().map(|p| p.display().to_string()).collect::<Vec<_>>().join(", ")
}

/// Says in the log where the game's files are coming from. Add it after `DefaultPlugins`: the log
/// is not up yet when the root is first looked up.
pub struct PathsPlugin;

impl Plugin for PathsPlugin {
    fn build(&self, _: &mut App) {
        report();
    }
}

fn report() {
    let r = root();
    if r.found {
        info!("game folder: {}", r.dir.display());
    } else {
        error!("could not find the game folder (one holding {MARKER}); searched {}. Set {ROOT_ENV} to it. Using {}", searched(), r.dir.display());
    }
}

/// Where to look, in order: the env override, the working directory, then the exe's folder and
/// each folder above it (target/debug in development, the shipped folder next to the exe).
fn search_order(env: Option<&Path>, cwd: &Path, exe_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    for dir in env.into_iter().chain([cwd]).chain(exe_dir.into_iter().flat_map(Path::ancestors)) {
        if !dirs.iter().any(|d| d == dir) {
            dirs.push(dir.to_path_buf());
        }
    }
    dirs
}

/// The first of `dirs` holding the marker file.
fn find_root(dirs: &[PathBuf]) -> Option<PathBuf> {
    dirs.iter().find(|d| d.join(MARKER).is_file()).cloned()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A fresh scratch folder, unique to the test.
    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("rust-regime-paths-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn mark(dir: &Path) {
        std::fs::create_dir_all(dir.join("assets")).unwrap();
        std::fs::write(dir.join(MARKER), "").unwrap();
    }

    #[test]
    fn the_root_is_found_above_the_exe_folder() {
        let base = scratch("ancestor");
        let game = base.join("game");
        let exe = game.join("target").join("release");
        std::fs::create_dir_all(&exe).unwrap();
        mark(&game);
        let elsewhere = base.join("elsewhere");
        std::fs::create_dir_all(&elsewhere).unwrap();
        assert_eq!(find_root(&search_order(None, &elsewhere, Some(&exe))), Some(game));
        std::fs::remove_dir_all(&base).ok();
    }

    #[test]
    fn the_env_override_wins() {
        let base = scratch("env");
        let (chosen, cwd) = (base.join("chosen"), base.join("cwd"));
        mark(&chosen);
        mark(&cwd);
        assert_eq!(find_root(&search_order(Some(&chosen), &cwd, Some(&cwd))), Some(chosen));
        // The working directory comes before the exe's folder.
        assert_eq!(find_root(&search_order(None, &cwd, Some(&base))), Some(cwd.clone()));
        // An override without the game falls through to the rest of the search.
        assert_eq!(find_root(&search_order(Some(&base), &cwd, None)), Some(cwd));
        std::fs::remove_dir_all(&base).ok();
    }

    #[test]
    fn no_game_folder_is_none() {
        let base = scratch("none");
        let exe = base.join("bin");
        std::fs::create_dir_all(&exe).unwrap();
        assert_eq!(find_root(&search_order(None, &base, Some(&exe))), None);
        std::fs::remove_dir_all(&base).ok();
    }
}
