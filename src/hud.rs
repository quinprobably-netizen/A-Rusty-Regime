use bevy::prelude::*;

use crate::controller::{MoveState, Player};
use crate::health::PlayerHealth;
use crate::bots::MatchState;
use crate::loot::{Inventory, Save};
use crate::mission::ObjectiveHud;
use crate::targets::Score;
use crate::tuning::Tuning;
use crate::weapon::Arsenal;

/// Speedometer, movement state, weapon, score, and a crosshair that flashes on hits.
pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PlayerHealth>().add_systems(Startup, spawn_hud).add_systems(Update, (update_hud, update_weapon_hud, update_health_hud, update_objective_hud, update_grapple_hud));
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

#[derive(Component)]
struct HealthFill;

#[derive(Component)]
struct HealthText;

#[derive(Component)]
struct HitFlash;

#[derive(Component)]
struct ObjectiveText;

#[derive(Component)]
struct HaulText;

#[derive(Component)]
struct GrappleBar;

#[derive(Component)]
struct GrappleFill;

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
        ObjectiveText,
        Text::new(""),
        TextFont { font_size: FontSize::Px(20.0), ..default() },
        TextColor(Color::srgba(1.0, 0.95, 0.7, 0.95)),
        Node { position_type: PositionType::Absolute, top: Val::Px(48.0), left: Val::Percent(50.0), width: Val::Px(700.0), margin: UiRect::left(Val::Px(-350.0)), justify_content: JustifyContent::Center, ..default() },
        TextLayout { justify: Justify::Center, ..default() },
    ));
    commands.spawn((
        HaulText,
        Text::new(""),
        TextFont { font_size: FontSize::Px(18.0), ..default() },
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.8)),
        Node { position_type: PositionType::Absolute, top: Val::Px(36.0), right: Val::Px(24.0), ..default() },
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
    // Grapple power, a thin bar under the crosshair that only shows while charging or pulling.
    commands
        .spawn((
            GrappleBar,
            Node {
                position_type: PositionType::Absolute,
                left: Val::Percent(50.0),
                top: Val::Percent(50.0),
                width: Val::Px(40.0),
                height: Val::Px(3.0),
                margin: UiRect { left: Val::Px(-20.0), top: Val::Px(14.0), ..default() },
                ..default()
            },
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.35)),
        ))
        .with_child((GrappleFill, Node { width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(Color::srgba(1.0, 0.75, 0.3, 0.9))));
    // Red overlay that flashes on a hit and stays while dead.
    commands.spawn((
        HitFlash,
        Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() },
        BackgroundColor(Color::NONE),
        ZIndex(-1),
    ));
    // Health bar, bottom center.
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                bottom: Val::Px(28.0),
                left: Val::Percent(50.0),
                width: Val::Px(240.0),
                height: Val::Px(14.0),
                margin: UiRect::left(Val::Px(-120.0)),
                border: UiRect::all(Val::Px(2.0)),
                ..default()
            },
            BorderColor::all(Color::srgba(1.0, 1.0, 1.0, 0.7)),
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.4)),
        ))
        .with_child((
            HealthFill,
            Node { width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() },
            BackgroundColor(Color::srgb(0.85, 0.2, 0.15)),
        ));
    commands.spawn((
        HealthText,
        Text::new("100"),
        TextFont { font_size: FontSize::Px(18.0), ..default() },
        Node { position_type: PositionType::Absolute, bottom: Val::Px(46.0), left: Val::Percent(50.0), margin: UiRect::left(Val::Px(-120.0)), ..default() },
    ));
    commands.spawn((
        Text::new("Click: lock mouse / fire   WASD / left stick: move   Space / A: jump   Ctrl / B: crouch & slide\n1-4, wheel, Q / d-pad, RB-LB, Y: weapons   Space in the air: double jump   G / mouse 4: grapple   R / Select: respawn   F5: reload tuning"),
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

fn update_hud(
    player: Single<(&Player, Option<&crate::vehicle::Driving>)>,
    vehicles: Query<(&crate::vehicle::Vehicle, &avian3d::prelude::LinearVelocity)>,
    mut text: Single<&mut Text, With<SpeedText>>,
) {
    let (player, driving) = *player;
    if let Some((v, vel)) = driving.and_then(|d| vehicles.get(d.0).ok()) {
        let gear = if v.gear < 0 { "R".to_string() } else { v.gear.to_string() };
        let fuel = if v.fuel <= 0.0 { "  OUT OF FUEL" } else { "" };
        text.0 = format!(
            "{} {:4.0} km/h  gear {gear}  {:5.0} rpm   fuel {:.0}%  hull {:.0}%{fuel}",
            v.spec.name.to_uppercase(),
            vel.0.length() * 3.6,
            v.rpm,
            v.fuel / v.spec.tank * 100.0,
            v.health / v.spec.hp * 100.0
        );
        return;
    }
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

fn update_objective_hud(
    tuning: Res<Tuning>,
    objective: Option<Res<ObjectiveHud>>,
    inventory: Option<Res<Inventory>>,
    save: Option<Res<Save>>,
    match_state: Option<Res<MatchState>>,
    mut texts: ParamSet<(Single<&mut Text, With<ObjectiveText>>, Single<&mut Text, With<HaulText>>)>,
) {
    let mut line = String::new();
    if let Some(m) = &match_state {
        line = match m.over {
            Some((0, _)) => "BLUE WINS".to_string(),
            Some(_) => "RED WINS".to_string(),
            None => format!("BLUE {}   RED {}", m.score[0], m.score[1]),
        };
    } else if let Some(o) = &objective {
        line = o.text.clone();
        if let Some(d) = o.distance {
            let arrow = match o.bearing {
                b if b.abs() < 0.35 => "^",
                b if b.abs() > 2.8 => "v",
                b if b > 0.0 => ">",
                _ => "<",
            };
            line = format!("{line}   {d:.0} m {arrow}");
        }
    }
    texts.p0().0 = line;
    let mut haul = String::new();
    if let (Some(inv), Some(save)) = (&inventory, &save) {
        haul = format!("CARRY {}   BANK {}   RUNS {}", inv.carried, save.banked, save.runs);
        if inv.extracting > 0.0 {
            haul = format!("EXTRACTING {:.0}/{:.0} s   {haul}", inv.extracting, tuning.loot.extract_time);
        }
    }
    texts.p1().0 = haul;
}

fn update_health_hud(
    time: Res<Time>,
    health: Res<PlayerHealth>,
    mut fill: Single<&mut Node, With<HealthFill>>,
    mut text: Single<&mut Text, With<HealthText>>,
    mut flash: Single<&mut BackgroundColor, With<HitFlash>>,
    mut level: Local<f32>,
) {
    fill.width = Val::Percent((health.hp / health.max.max(1.0) * 100.0).clamp(0.0, 100.0));
    text.0 = if !health.alive() {
        "RESPAWNING".into()
    } else if health.bleeding > 0.0 {
        format!("{:.0}  BLEEDING", health.hp)
    } else {
        format!("{:.0}", health.hp)
    };
    if health.hit_this_tick {
        *level = 0.45;
    }
    *level = (*level - time.delta_secs() * 1.5).max(if health.alive() { 0.0 } else { 0.35 });
    flash.0 = Color::srgba(0.8, 0.0, 0.0, *level);
}

fn update_grapple_hud(
    tuning: Res<Tuning>,
    grapple: Option<Res<crate::abilities::GrappleState>>,
    mut bar: Single<&mut Visibility, With<GrappleBar>>,
    mut fill: Single<&mut Node, With<GrappleFill>>,
) {
    let Some(g) = grapple else {
        **bar = Visibility::Hidden;
        return;
    };
    fill.width = Val::Percent(100.0 * g.power / tuning.grapple.power_max.max(1.0));
    **bar = if g.enabled && (g.hooked() || g.power < tuning.grapple.power_max) { Visibility::Inherited } else { Visibility::Hidden };
}
