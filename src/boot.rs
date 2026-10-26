//! The loading screen. The island is built on a background thread while this shows, and the
//! world spawns once it and its textures are in, so the window is never left blank.

use std::time::Instant;

use bevy::prelude::*;

use crate::look::Textures;
use crate::terrain::Building;

/// `Loading` while the island and its textures come in, then `Ready`: the world spawns on entering it.
#[derive(States, Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum Boot {
    #[default]
    Loading,
    Ready,
}

/// The island level waits on the loading screen. The other levels have nothing to wait for and start ready.
pub struct BootPlugin {
    pub island: bool,
}

impl Plugin for BootPlugin {
    fn build(&self, app: &mut App) {
        app.insert_state(if self.island { Boot::Loading } else { Boot::Ready })
            .insert_resource(Launched(Instant::now()))
            .add_systems(OnEnter(Boot::Loading), spawn_screen)
            .add_systems(Update, (show_progress, advance).run_if(in_state(Boot::Loading)))
            .add_systems(Update, leave.run_if(in_state(Boot::Ready)));
    }
}

/// The share of the loading bar the island build fills; the textures fill the rest.
const BUILD_SHARE: f32 = 0.7;

const DIM: Color = Color::srgb(0.55, 0.58, 0.62);
const AMBER: Color = Color::srgb(0.95, 0.68, 0.22);

#[derive(Component)]
struct LoadingScreen;

#[derive(Component)]
struct LoadingBar;

#[derive(Component)]
struct LoadingLabel;

fn spawn_screen(mut commands: Commands) {
    commands
        .spawn((
            LoadingScreen,
            ZIndex(1000),
            BackgroundColor(Color::srgb(0.03, 0.035, 0.045)),
            Node {
                position_type: PositionType::Absolute,
                left: Val::Px(0.0),
                top: Val::Px(0.0),
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                justify_content: JustifyContent::Center,
                row_gap: Val::Px(14.0),
                ..default()
            },
        ))
        .with_children(|screen| {
            screen.spawn((Text::new("RUST REGIME"), TextFont { font_size: FontSize::Px(40.0), ..default() }, TextColor(AMBER)));
            screen.spawn((LoadingLabel, Text::new("Loading"), TextFont { font_size: FontSize::Px(16.0), ..default() }, TextColor(DIM)));
            screen
                .spawn((
                    Node { width: Val::Px(360.0), height: Val::Px(4.0), ..default() },
                    BackgroundColor(Color::srgb(0.16, 0.17, 0.19)),
                ))
                .with_children(|track| {
                    track.spawn((LoadingBar, Node { width: Val::Percent(0.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(AMBER)));
                });
        });
}

/// Frames the screen stays up after the world spawns. The first frames with the world in them
/// compile its shaders and stall, and the screen should cover that stall rather than the window going blank.
const HOLD_FRAMES: u32 = 4;

/// Take the screen down once the world has had its first frames.
fn leave(mut commands: Commands, screens: Query<Entity, With<LoadingScreen>>, launched: Res<Launched>, mut frames: Local<u32>) {
    if screens.is_empty() {
        return;
    }
    *frames += 1;
    if *frames > HOLD_FRAMES {
        info!("the loading screen came down {:.0} ms after launch", launched.0.elapsed().as_secs_f32() * 1000.0);
        for screen in &screens {
            commands.entity(screen).despawn();
        }
    }
}

/// Fill the bar and name what is still loading.
fn show_progress(
    building: Option<Res<Building>>,
    textures: Option<Res<Textures>>,
    server: Res<AssetServer>,
    mut bars: Query<&mut Node, With<LoadingBar>>,
    mut labels: Query<&mut Text, With<LoadingLabel>>,
) {
    let built = building.as_ref().map_or(1.0, |b| b.progress());
    let loaded = textures.as_ref().map_or(1.0, |t| t.loaded_fraction(&server));
    let label = match building.as_ref() {
        Some(b) => b.step_label(),
        None if loaded < 1.0 => "Loading the textures",
        None => "Almost there",
    };
    for mut bar in &mut bars {
        bar.width = Val::Percent(100.0 * (BUILD_SHARE * built + (1.0 - BUILD_SHARE) * loaded));
    }
    for mut text in &mut labels {
        if text.0 != label {
            text.0 = label.to_string();
        }
    }
}

/// Nothing is left to wait for: the island is built and its textures are in.
fn advance(
    building: Option<Res<Building>>,
    textures: Option<Res<Textures>>,
    server: Res<AssetServer>,
    launched: Res<Launched>,
    mut next: ResMut<NextState<Boot>>,
) {
    if building.is_none() && textures.is_none_or(|t| t.loaded_fraction(&server) >= 1.0) {
        info!("the island is ready {:.0} ms after launch", launched.0.elapsed().as_secs_f32() * 1000.0);
        next.set(Boot::Ready);
    }
}

/// When the game started, so the log can say how long the loading screen was up.
#[derive(Resource)]
struct Launched(Instant);
