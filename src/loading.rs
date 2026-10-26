//! The loading screen: a full-window cover with a progress bar, up from the first frame until every
//! character on the island has its model and outfit (the player's body, the first-person arms and
//! the soldiers stream in after the world is built). The menu ignores input behind it.
//!
//! The island itself is built before the first frame (see `terrain`), so the window stays blank
//! until that is done; this covers the part after, when models and animations load.

use bevy::prelude::*;

use crate::character::Rig;

/// Give up waiting after this long, so a model that never loads cannot hide the menu forever.
const GIVE_UP: f32 = 60.0;

#[derive(Resource, Debug, Default)]
pub struct Loading {
    /// Everything is in (or we gave up waiting), and the cover is gone.
    pub done: bool,
    /// 0..1 of the rigs dressed and holding their weapons.
    pub progress: f32,
}

/// The fraction of `total` rigs that are `ready`; nothing to wait on is not done yet.
pub fn progress(ready: usize, total: usize) -> f32 {
    if total == 0 { 0.0 } else { ready as f32 / total as f32 }
}

#[derive(Component)]
struct LoadingCover;

#[derive(Component)]
struct LoadingBar;

#[derive(Component)]
struct LoadingLabel;

const AMBER: Color = Color::srgb(1.0, 0.72, 0.25);

pub struct LoadingPlugin;

impl Plugin for LoadingPlugin {
    fn build(&self, app: &mut App) {
        // A screenshot run measures the finished scene, not the wait for it.
        let skip = std::env::var_os("RUST_REGIME_SCREENSHOT").is_some();
        app.insert_resource(Loading { done: skip, progress: 0.0 });
        if !skip {
            app.add_systems(Startup, spawn).add_systems(Update, update.run_if(|l: Res<Loading>| !l.done));
        }
    }
}

fn spawn(mut commands: Commands) {
    let text = |s: &str, px: f32, color: Color| (Text::new(s), TextFont { font_size: FontSize::Px(px), ..default() }, TextColor(color));
    commands
        .spawn((
            LoadingCover,
            Node {
                position_type: PositionType::Absolute,
                left: Val::Px(0.0),
                top: Val::Px(0.0),
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                flex_direction: FlexDirection::Column,
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                row_gap: Val::Px(14.0),
                ..default()
            },
            BackgroundColor(Color::srgb(0.02, 0.03, 0.04)),
            GlobalZIndex(1000),
        ))
        .with_children(|p| {
            p.spawn(text("RUST REGIME", 56.0, Color::WHITE));
            p.spawn((Node { width: Val::Px(420.0), height: Val::Px(6.0), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.1)))).with_children(|bar| {
                bar.spawn((LoadingBar, Node { width: Val::Percent(0.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(AMBER)));
            });
            p.spawn((LoadingLabel, text("LOADING", 16.0, Color::srgba(1.0, 1.0, 1.0, 0.55))));
        });
}

fn update(
    mut commands: Commands,
    time: Res<Time<Real>>,
    rigs: Query<&Rig>,
    mut loading: ResMut<Loading>,
    cover: Query<Entity, With<LoadingCover>>,
    mut bar: Query<&mut Node, With<LoadingBar>>,
    mut label: Query<&mut Text, With<LoadingLabel>>,
) {
    let total = rigs.iter().count();
    let ready = rigs.iter().filter(|r| r.ready()).count();
    // Never move the bar backwards when more rigs spawn behind a finished few.
    loading.progress = loading.progress.max(progress(ready, total));
    let timed_out = time.elapsed_secs() > GIVE_UP;
    if (total > 0 && ready == total) || timed_out {
        info!("loading done after {:.1}s: {ready}/{total} rigs ready{}", time.elapsed_secs(), if timed_out { " (gave up)" } else { "" });
        loading.done = true;
        loading.progress = 1.0;
        for e in &cover {
            commands.entity(e).despawn();
        }
        return;
    }
    for mut node in &mut bar {
        node.width = Val::Percent(loading.progress * 100.0);
    }
    for mut text in &mut label {
        text.0 = format!("LOADING  {}/{}", ready, total);
    }
}
