use bevy::prelude::*;

use crate::controller::{MoveState, Player};
use crate::targets::Score;
use crate::weapon::Arsenal;

/// Speedometer, movement state, weapon, score, and a crosshair that flashes on hits.
pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn_hud).add_systems(Update, (update_hud, update_weapon_hud));
    }
}

#[derive(Component)]
struct SpeedText;

#[derive(Component)]
struct WeaponText;

#[derive(Component)]
struct ScoreText;

#[derive(Component)]
struct Crosshair;

fn spawn_hud(mut commands: Commands) {
    commands.spawn((
        SpeedText,
        Text::new(""),
        TextFont { font_size: FontSize::Px(22.0), ..default() },
        Node {
            position_type: PositionType::Absolute,
            bottom: Val::Px(24.0),
            left: Val::Px(24.0),
            ..default()
        },
    ));
    commands.spawn((
        WeaponText,
        Text::new(""),
        TextFont { font_size: FontSize::Px(22.0), ..default() },
        Node {
            position_type: PositionType::Absolute,
            bottom: Val::Px(24.0),
            right: Val::Px(24.0),
            ..default()
        },
    ));
    commands.spawn((
        ScoreText,
        Text::new(""),
        TextFont { font_size: FontSize::Px(18.0), ..default() },
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.8)),
        Node {
            position_type: PositionType::Absolute,
            top: Val::Px(12.0),
            right: Val::Px(24.0),
            ..default()
        },
    ));
    commands.spawn((
        Crosshair,
        Node {
            position_type: PositionType::Absolute,
            left: Val::Percent(50.0),
            top: Val::Percent(50.0),
            width: Val::Px(4.0),
            height: Val::Px(4.0),
            margin: UiRect::all(Val::Px(-2.0)),
            ..default()
        },
        BackgroundColor(Color::WHITE),
    ));
    commands.spawn((
        Text::new("Click: lock mouse / fire   WASD / left stick: move   Space / A: jump   Ctrl / B: crouch & slide\n1-4, wheel, Q / d-pad, RB-LB, Y: weapons   R / Select: respawn   F5: reload tuning.toml"),
        TextFont { font_size: FontSize::Px(14.0), ..default() },
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.6)),
        Node {
            position_type: PositionType::Absolute,
            top: Val::Px(12.0),
            left: Val::Px(12.0),
            ..default()
        },
    ));
}

fn update_hud(player: Single<&Player>, mut text: Single<&mut Text, With<SpeedText>>) {
    let speed = player.horizontal_speed();
    let state = match player.state {
        MoveState::Ground => "",
        MoveState::Air => "AIR",
        MoveState::Slide => "SLIDE",
        MoveState::WallRun => "WALLRUN",
        MoveState::Mantle => "MANTLE",
    };
    // Hammer units per second shown too, for comparing against TF2 numbers.
    text.0 = format!("{speed:5.1} m/s  ({:4.0} u/s)  {state}", speed / 0.022);
}

fn update_weapon_hud(
    time: Res<Time>,
    arsenal: Res<Arsenal>,
    score: Res<Score>,
    mut weapon_text: Single<&mut Text, With<WeaponText>>,
    mut score_text: Single<&mut Text, (With<ScoreText>, Without<WeaponText>)>,
    mut crosshair: Single<(&mut BackgroundColor, &mut Node), With<Crosshair>>,
    mut flash: Local<f32>,
) {
    weapon_text.0 = format!("[{}] {}", arsenal.current + 1, arsenal.kind().name());
    if score.is_changed() {
        score_text.0 = format!("HITS {}   KILLS {}", score.hits, score.kills);
        if score.hits > 0 {
            *flash = 0.12;
        }
    }
    *flash -= time.delta_secs();
    let (color, node) = &mut *crosshair;
    let size = if *flash > 0.0 { 8.0 } else { 4.0 };
    color.0 = if *flash > 0.0 { Color::srgb(1.0, 0.3, 0.2) } else { Color::WHITE };
    node.width = Val::Px(size);
    node.height = Val::Px(size);
    node.margin = UiRect::all(Val::Px(-size / 2.0));
}
