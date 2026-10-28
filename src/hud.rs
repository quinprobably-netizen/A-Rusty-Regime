//! The in-game HUD, in the menus' look (Fira Mono, amber accent, dark plates): a compass tape with
//! the objective marked on it, the objective line under it, a health plate bottom left with the
//! grapple meter, a movement readout bottom centre (speedo while driving), the weapon plate bottom
//! right with slot pips, fitted parts and the heat bar, and a crosshair that opens with spread and
//! flashes on hits. Everything hangs off `HudRoot` so the menus can hide it.

use bevy::prelude::*;

use crate::bots::MatchState;
use crate::controller::{MoveState, Player};
use crate::gunsmith::{Loadout, PARTS, SLOTS};
use crate::health::PlayerHealth;
use crate::input::ViewAngles;
use crate::loot::{Inventory, Save};
use crate::mission::ObjectiveHud;
use crate::targets::Score;
use crate::tuning::Tuning;
use crate::weapon::{Aim, Arsenal, Recoil, WEAPONS, WeaponKind};

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PlayerHealth>()
            .init_resource::<FlightHud>()
            .add_systems(Startup, spawn_hud)
            .add_systems(Update, (update_speed, update_weapon, update_crosshair, update_health, update_objective, update_compass, update_grapple, update_hint, update_reticle));
    }
}

/// What the ship being flown tells the HUD each tick; `active` is false when nobody flies.
#[derive(Resource, Default, Debug, Clone)]
pub struct FlightHud {
    pub active: bool,
    /// The nose's heading in the view's convention (as `ViewAngles::yaw`), and how far it points
    /// above the horizon, radians.
    pub heading: f32,
    pub pitch: f32,
    pub speed: f32,
    /// Vertical speed, up positive.
    pub climb: f32,
    /// Height of the landing gear over the ground; none in deep space.
    pub altitude: Option<f32>,
    /// 1 where flight assist holds the ship, fading to 0 by 3.5 km.
    pub assist: f32,
    /// Boost left, 0 to 1, and whether it is burning.
    pub boost: f32,
    pub boosting: bool,
    pub stopping: bool,
    pub throttle: f32,
    /// Seconds left of the "too fast to leave" warning.
    pub too_fast: f32,
    /// Which way the ship moves, and where its nose points, in world space.
    pub velocity: Vec3,
    pub nose: Vec3,
    /// Straight up from the ground below, world space.
    pub up: Vec3,
}

/// Every HUD element hangs off this, so menus can hide it in one go. Other modules put it on
/// their own in-game text (the world clock) for the same reason.
#[derive(Component)]
pub struct HudRoot;

const AMBER: Color = Color::srgb(1.0, 0.72, 0.25);
const WHITE: Color = Color::WHITE;
const DIM: Color = Color::srgba(1.0, 1.0, 1.0, 0.55);
const FAINT: Color = Color::srgba(1.0, 1.0, 1.0, 0.14);
const PLATE: Color = Color::srgba(0.02, 0.03, 0.04, 0.5);
const RED: Color = Color::srgb(0.9, 0.3, 0.22);
/// Compass tape: pixels per degree and how many degrees each side of the heading it shows.
const TAPE_PX: f32 = 2.4;
const TAPE_HALF: f32 = 70.0;

#[derive(Component)]
struct SpeedText;
#[derive(Component)]
struct StateText;
#[derive(Component)]
struct RpmFill;
#[derive(Component)]
struct FuelFill;
#[derive(Component)]
struct VehicleBars;
#[derive(Component)]
struct WeaponText;
#[derive(Component)]
struct PartsText;
#[derive(Component)]
struct SlotPip(usize);
#[derive(Component)]
struct HeatFill;
#[derive(Component)]
struct ScoreText;
#[derive(Component)]
struct CrosshairLine(Vec2);
/// The weapon plate, hidden while flying.
#[derive(Component)]
struct WeaponPlate;
/// Flight reticle: where the ship is going, where its nose points, and a horizon line.
#[derive(Component)]
struct VelocityMark;
#[derive(Component)]
struct NoseMark;
#[derive(Component)]
struct Horizon;
#[derive(Component)]
struct CrosshairDot;
#[derive(Component)]
struct HealthFill;
#[derive(Component)]
struct HealthText;
#[derive(Component)]
struct HealthTag;
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
#[derive(Component)]
struct CompassTick(f32);
#[derive(Component)]
struct ObjectiveMark;
#[derive(Component)]
struct HintText;

fn text(s: impl Into<String>, px: f32, color: Color) -> (Text, TextFont, TextColor) {
    (Text::new(s), TextFont { font_size: FontSize::Px(px), ..default() }, TextColor(color))
}

fn plate() -> (Node, BackgroundColor, BorderColor) {
    (
        Node { position_type: PositionType::Absolute, padding: UiRect::axes(Val::Px(12.0), Val::Px(8.0)), flex_direction: FlexDirection::Column, row_gap: Val::Px(4.0), border: UiRect::all(Val::Px(1.0)), ..default() },
        BackgroundColor(PLATE),
        BorderColor::all(FAINT),
    )
}

fn bar(width: f32, height: f32) -> (Node, BackgroundColor) {
    (Node { width: Val::Px(width), height: Val::Px(height), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.1)))
}

fn fill(color: Color) -> (Node, BackgroundColor) {
    (Node { width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(color))
}

fn spawn_hud(mut commands: Commands) {
    let root = commands.spawn((HudRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() })).id();
    let mut root = commands.entity(root);
    root.with_children(|p| {
        // Red overlay that flashes on a hit and stays while dead.
        p.spawn((HitFlash, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(Color::NONE), ZIndex(-1)));

        // Compass tape, top centre: cardinal letters slide past a notch; the objective rides on it.
        let tape_w = TAPE_HALF * 2.0 * TAPE_PX;
        p.spawn((
            Node { position_type: PositionType::Absolute, top: Val::Px(14.0), left: Val::Percent(50.0), width: Val::Px(tape_w), height: Val::Px(30.0), margin: UiRect::left(Val::Px(-tape_w / 2.0)), overflow: Overflow::clip(), border: UiRect::bottom(Val::Px(1.0)), ..default() },
            BackgroundColor(PLATE),
            BorderColor::all(FAINT),
        ))
        .with_children(|t| {
            for i in 0..24 {
                let angle = i as f32 * 15.0;
                let label = match i {
                    0 => Some(("N", 15.0, WHITE)),
                    6 => Some(("E", 15.0, WHITE)),
                    12 => Some(("S", 15.0, WHITE)),
                    18 => Some(("W", 15.0, WHITE)),
                    3 | 9 | 15 | 21 => Some((["NE", "SE", "SW", "NW"][(i / 6) as usize], 11.0, DIM)),
                    _ => None,
                };
                match label {
                    Some((s, px, c)) => {
                        t.spawn((CompassTick(angle), text(s, px, c), Node { position_type: PositionType::Absolute, top: Val::Px(6.0), ..default() }));
                    }
                    None => {
                        t.spawn((CompassTick(angle), Node { position_type: PositionType::Absolute, top: Val::Px(20.0), width: Val::Px(1.0), height: Val::Px(8.0), ..default() }, BackgroundColor(DIM)));
                    }
                }
            }
            t.spawn((ObjectiveMark, Node { position_type: PositionType::Absolute, top: Val::Px(22.0), width: Val::Px(7.0), height: Val::Px(7.0), ..default() }, BackgroundColor(AMBER), Visibility::Hidden));
            t.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(tape_w / 2.0 - 1.0), top: Val::Px(0.0), width: Val::Px(2.0), height: Val::Px(30.0), ..default() }, BackgroundColor(AMBER)));
        });
        // Objective line under the tape.
        p.spawn((
            ObjectiveText,
            text("", 17.0, Color::srgba(1.0, 0.95, 0.75, 0.95)),
            Node { position_type: PositionType::Absolute, top: Val::Px(50.0), left: Val::Percent(50.0), width: Val::Px(700.0), margin: UiRect::left(Val::Px(-350.0)), justify_content: JustifyContent::Center, ..default() },
            TextLayout { justify: Justify::Center, ..default() },
        ));

        // Top right: score and the haul (the world clock sits under them, from `world`).
        p.spawn((ScoreText, text("", 14.0, DIM), Node { position_type: PositionType::Absolute, top: Val::Px(14.0), right: Val::Px(24.0), ..default() }));
        p.spawn((HaulText, text("", 14.0, DIM), Node { position_type: PositionType::Absolute, top: Val::Px(34.0), right: Val::Px(24.0), ..default() }));

        // Top left: a hint that fades after a few seconds.
        p.spawn((HintText, text("ESC  MENU", 12.0, DIM), Node { position_type: PositionType::Absolute, top: Val::Px(14.0), left: Val::Px(24.0), ..default() }));

        // Crosshair: four lines that open with spread, a dot in the middle.
        for dir in [Vec2::X, Vec2::NEG_X, Vec2::Y, Vec2::NEG_Y] {
            let (w, h) = if dir.x != 0.0 { (8.0, 2.0) } else { (2.0, 8.0) };
            p.spawn((CrosshairLine(dir), Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(w), height: Val::Px(h), ..default() }, BackgroundColor(WHITE)));
        }
        p.spawn((CrosshairDot, Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(2.0), height: Val::Px(2.0), margin: UiRect::all(Val::Px(-1.0)), ..default() }, BackgroundColor(WHITE)));
        // Flight reticle: a ring where the ship is heading, a cross where the nose points.
        p.spawn((VelocityMark, Node { position_type: PositionType::Absolute, width: Val::Px(14.0), height: Val::Px(14.0), border: UiRect::all(Val::Px(2.0)), border_radius: BorderRadius::all(Val::Px(7.0)), ..default() }, BorderColor::all(AMBER), Visibility::Hidden));
        p.spawn((NoseMark, Node { position_type: PositionType::Absolute, width: Val::Px(18.0), height: Val::Px(2.0), ..default() }, BackgroundColor(WHITE), Visibility::Hidden))
            .with_child((Node { position_type: PositionType::Absolute, left: Val::Px(8.0), top: Val::Px(-8.0), width: Val::Px(2.0), height: Val::Px(18.0), ..default() }, BackgroundColor(WHITE)));
        // Horizon: a long thin line where the horizon lies ahead, tilted with the ship's bank.
        p.spawn((Horizon, Node { position_type: PositionType::Absolute, width: Val::Px(240.0), height: Val::Px(1.0), ..default() }, BackgroundColor(DIM), UiTransform::default(), Visibility::Hidden));
        // Grapple power, a thin bar under the crosshair that only shows while charging or pulling.
        p.spawn((GrappleBar, Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(40.0), height: Val::Px(3.0), margin: UiRect { left: Val::Px(-20.0), top: Val::Px(18.0), ..default() }, ..default() }, BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.35))))
            .with_child((GrappleFill, fill(AMBER)));

        // Bottom left: health.
        let (node, bg, border) = plate();
        p.spawn((Node { left: Val::Px(24.0), bottom: Val::Px(24.0), width: Val::Px(280.0), ..node }, bg, border)).with_children(|h| {
            h.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Baseline, column_gap: Val::Px(10.0), ..default() }).with_children(|r| {
                r.spawn((HealthText, text("100", 30.0, WHITE)));
                r.spawn((HealthTag, text("HP", 12.0, DIM)));
            });
            h.spawn(bar(256.0, 8.0)).with_child((HealthFill, fill(WHITE)));
        });

        // Bottom centre: movement, or the vehicle's dials.
        let (node, bg, border) = plate();
        p.spawn((Node { left: Val::Percent(50.0), bottom: Val::Px(24.0), width: Val::Px(300.0), margin: UiRect::left(Val::Px(-150.0)), align_items: AlignItems::Center, ..node }, bg, border)).with_children(|m| {
            m.spawn((StateText, text("", 13.0, AMBER)));
            m.spawn((SpeedText, text("", 16.0, WHITE)));
            m.spawn((VehicleBars, Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(8.0), display: Display::None, ..default() })).with_children(|v| {
                v.spawn(bar(160.0, 5.0)).with_child((RpmFill, fill(AMBER)));
                v.spawn(bar(100.0, 5.0)).with_child((FuelFill, fill(DIM)));
            });
        });

        // Bottom right: weapon.
        let (node, bg, border) = plate();
        p.spawn((WeaponPlate, Node { right: Val::Px(24.0), bottom: Val::Px(24.0), width: Val::Px(280.0), align_items: AlignItems::FlexEnd, ..node }, bg, border)).with_children(|w| {
            w.spawn(Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(4.0), ..default() }).with_children(|pips| {
                for i in 0..WEAPONS.len() {
                    pips.spawn((SlotPip(i), Node { width: Val::Px(16.0), height: Val::Px(5.0), ..default() }, BackgroundColor(FAINT)));
                }
            });
            w.spawn((WeaponText, text("", 22.0, WHITE)));
            w.spawn((PartsText, text("", 11.0, DIM)));
            w.spawn(bar(256.0, 4.0)).with_child((HeatFill, fill(AMBER)));
        });
    });
}

fn update_speed(
    player: Single<(&Player, Option<&crate::vehicle::Driving>)>,
    vehicles: Query<(&crate::vehicle::Vehicle, &avian3d::prelude::LinearVelocity)>,
    flight: Res<FlightHud>,
    mut texts: ParamSet<(Single<&mut Text, With<SpeedText>>, Single<&mut Text, With<StateText>>)>,
    mut nodes: ParamSet<(Single<&mut Node, With<VehicleBars>>, Single<&mut Node, With<RpmFill>>, Single<&mut Node, With<FuelFill>>)>,
) {
    let (player, driving) = *player;
    // Flying: total and vertical speed, height over the gear, the assist and the boost tank.
    if flight.active {
        let assist = match flight.assist {
            a if a >= 1.0 => "ASSIST",
            a if a > 0.0 => "ASSIST FADING",
            _ => "FREE FLIGHT",
        };
        let doing = if flight.stopping {
            "   STOPPING"
        } else if flight.boosting {
            "   BOOST"
        } else if flight.boost <= 0.0 {
            "   BOOST EMPTY"
        } else {
            ""
        };
        texts.p1().0 = format!("{assist}{doing}   PITCH {:+.0}", flight.pitch.to_degrees());
        let alt = flight.altitude.map_or(String::new(), |a| if a < 1000.0 { format!("   ALT {a:.0} m") } else { format!("   ALT {:.1} km", a / 1000.0) });
        texts.p0().0 = format!("{:.0} m/s   VS {:+.1}{alt}", flight.speed, flight.climb);
        nodes.p0().display = Display::Flex;
        nodes.p1().width = Val::Percent(flight.boost.clamp(0.0, 1.0) * 100.0);
        nodes.p2().width = Val::Percent(flight.throttle.abs().clamp(0.0, 1.0) * 100.0);
        return;
    }
    if let Some((v, vel)) = driving.and_then(|d| vehicles.get(d.0).ok()) {
        let gear = if v.gear < 0 { "R".to_string() } else { v.gear.to_string() };
        let fuel = if v.fuel <= 0.0 { "OUT OF FUEL" } else { "" };
        texts.p1().0 = format!("{}   GEAR {gear}   HULL {:.0}%   {fuel}", v.spec.name.to_uppercase(), v.health / v.spec.hp * 100.0);
        texts.p0().0 = format!("{:4.0} km/h", vel.0.length() * 3.6);
        nodes.p0().display = Display::Flex;
        nodes.p1().width = Val::Percent((v.rpm / v.spec.redline.max(1.0) * 100.0).clamp(0.0, 100.0));
        nodes.p2().width = Val::Percent((v.fuel / v.spec.tank.max(1.0) * 100.0).clamp(0.0, 100.0));
        return;
    }
    nodes.p0().display = Display::None;
    let speed = player.horizontal_speed();
    let state = match player.state {
        MoveState::Ground if player.crouched => "CROUCH",
        MoveState::Ground => "",
        MoveState::Air => "AIR",
        MoveState::Slide => "SLIDE",
        MoveState::WallRun => "WALLRUN",
        MoveState::Mantle => "MANTLE",
    };
    texts.p1().0 = state.into();
    // Hammer units per second shown too, for comparing against TF2 numbers.
    texts.p0().0 = format!("{speed:5.1} m/s   {:4.0} u/s", speed / 0.022);
}

fn update_weapon(
    flight: Res<FlightHud>,
    mut plate: Single<&mut Node, (With<WeaponPlate>, Without<HeatFill>)>,
    arsenal: Res<Arsenal>,
    tuning: Res<Tuning>,
    loadout: Res<Loadout>,
    recoil: Option<Res<Recoil>>,
    score: Res<Score>,
    mut weapon_text: Single<&mut Text, With<WeaponText>>,
    mut parts_text: Single<&mut Text, (With<PartsText>, Without<WeaponText>)>,
    mut score_text: Single<&mut Text, (With<ScoreText>, Without<WeaponText>, Without<PartsText>)>,
    mut pips: Query<(&SlotPip, &mut BackgroundColor)>,
    mut heat: Single<(&mut Node, &mut BackgroundColor), (With<HeatFill>, Without<SlotPip>)>,
) {
    plate.display = if flight.active { Display::None } else { Display::Flex };
    let kind = arsenal.kind();
    weapon_text.0 = match arsenal.rounds(&tuning) {
        _ if arsenal.reload > 0.0 => format!("{}   RELOADING", kind.name()),
        Some((left, mag)) => format!("{}   {left} / {mag}", kind.name()),
        None => kind.name().into(),
    };
    parts_text.0 = if !crate::gunsmith::customizable(kind) {
        match kind {
            WeaponKind::RocketLauncher => "SPLASH   ROCKET JUMP READY",
            WeaponKind::Grenade => "BOUNCES   BURSTS ON A FUSE OR A HIT",
            WeaponKind::Harpoon => "YANKS YOU TO WALLS   YANKS THINGS TO YOU",
            WeaponKind::Knife => "QUICK SLASH   X TO PUT IT AWAY",
            _ => "PUNCH ANY SURFACE TO LAUNCH OFF IT",
        }
        .into()
    } else {
        let fitted: Vec<&str> = (0..SLOTS.len()).filter(|s| loadout.part(kind, *s) != 0).map(|s| PARTS[s][loadout.part(kind, s)].name).collect();
        if fitted.is_empty() { "NO PARTS".into() } else { fitted.join("   ") }
    };
    for (pip, mut color) in &mut pips {
        color.0 = if pip.0 == arsenal.current { AMBER } else { FAINT };
    }
    let h = recoil.map_or(0.0, |r| r.heat);
    let (node, color) = &mut *heat;
    node.width = Val::Percent(h * 100.0);
    color.0 = if h > 0.7 { RED } else { AMBER };
    if score.is_changed() {
        score_text.0 = format!("HITS {}   KILLS {}", score.hits, score.kills);
    }
}

/// The crosshair opens with heat and movement, closes crouched or aiming, and flashes red on a hit.
fn update_crosshair(
    time: Res<Time>,
    tuning: Res<Tuning>,
    arsenal: Res<Arsenal>,
    loadout: Res<Loadout>,
    recoil: Option<Res<Recoil>>,
    aim: Option<Res<Aim>>,
    score: Res<Score>,
    flight: Res<FlightHud>,
    player: Single<(&Player, Has<crate::vehicle::Driving>)>,
    mut lines: Query<(&CrosshairLine, &mut Node, &mut BackgroundColor)>,
    mut dot: Single<&mut BackgroundColor, (With<CrosshairDot>, Without<CrosshairLine>)>,
    mut flash: Local<f32>,
) {
    let (p, driving) = *player;
    if score.is_changed() && score.hits > 0 {
        *flash = 0.12;
    }
    *flash -= time.delta_secs();
    let kind = arsenal.kind();
    let heat = recoil.as_ref().map_or(0.0, |r| r.heat);
    let ads = aim.as_ref().map_or(0.0, |a| a.level);
    let moving = (p.horizontal_speed() / tuning.max_speed).clamp(0.0, 1.0);
    // Mirrors the spread in `weapon::fire`, scaled to pixels.
    let mut spread = tuning.gun(kind).map_or(1.0, |g| {
        let g = loadout.gun(kind, g);
        g.spread_degrees * (1.0 + heat * g.heat_spread) * (1.0 + moving * 0.8) * if p.crouched { 0.7 } else { 1.0 } * (1.0 - ads * (1.0 - g.ads_spread))
    });
    if driving {
        spread *= 2.0;
    }
    let gap = 5.0 + spread * 6.0 + if *flash > 0.0 { 3.0 } else { 0.0 };
    let mut color = if *flash > 0.0 { RED } else if ads > 0.5 { AMBER } else { WHITE };
    // A fitted red dot or scope is the aim point while aiming: the crosshair fades out of its way.
    if crate::gunsmith::customizable(kind) && loadout.part(kind, 0) > 0 {
        color.set_alpha(color.alpha() * (1.0 - ads));
    }
    // Flying, the flight reticle takes over.
    if flight.active {
        color = Color::NONE;
    }
    for (line, mut node, mut bg) in &mut lines {
        let d = line.0;
        let (w, h) = if d.x != 0.0 { (8.0, 2.0) } else { (2.0, 8.0) };
        // Lines start `gap` px from the centre, pointing outward.
        let x = if d.x > 0.0 { gap } else if d.x < 0.0 { -gap - w } else { -w / 2.0 };
        let y = if d.y > 0.0 { gap } else if d.y < 0.0 { -gap - h } else { -h / 2.0 };
        node.margin = UiRect { left: Val::Px(x), top: Val::Px(y), ..default() };
        bg.0 = color;
    }
    dot.0 = color;
}

fn update_objective(
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
            line = format!("{line}   {d:.0} m");
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

/// Slide the compass ticks past the notch; yaw 0 looks down -Z, which is north.
fn update_compass(view: Res<ViewAngles>, flight: Res<FlightHud>, objective: Option<Res<ObjectiveHud>>, mut ticks: Query<(&CompassTick, &mut Node)>, mut mark: Single<(&mut Node, &mut Visibility), (With<ObjectiveMark>, Without<CompassTick>)>) {
    // Flying, the tape follows the nose.
    let yaw = if flight.active { flight.heading } else { view.yaw };
    let heading = (-yaw.to_degrees()).rem_euclid(360.0);
    let centre = TAPE_HALF * TAPE_PX;
    let place = |offset: f32, node: &mut Node, width: f32| {
        let visible = offset.abs() < TAPE_HALF;
        node.left = Val::Px(centre + offset * TAPE_PX - width / 2.0);
        node.display = if visible { Display::Flex } else { Display::None };
    };
    for (tick, mut node) in &mut ticks {
        let offset = (tick.0 - heading + 540.0).rem_euclid(360.0) - 180.0;
        place(offset, &mut node, 8.0);
    }
    let (node, vis) = &mut *mark;
    match objective.as_ref().and_then(|o| o.distance.map(|_| o.bearing)) {
        Some(bearing) => {
            let offset = bearing.to_degrees().clamp(-TAPE_HALF + 3.0, TAPE_HALF - 3.0);
            place(offset, node, 7.0);
            **vis = Visibility::Inherited;
        }
        None => **vis = Visibility::Hidden,
    }
}

fn update_health(
    time: Res<Time>,
    health: Res<PlayerHealth>,
    mut fill: Single<(&mut Node, &mut BackgroundColor), With<HealthFill>>,
    mut texts: ParamSet<(Single<&mut Text, With<HealthText>>, Single<(&mut Text, &mut TextColor), With<HealthTag>>)>,
    mut flash: Single<&mut BackgroundColor, (With<HitFlash>, Without<HealthFill>)>,
    mut level: Local<f32>,
) {
    let frac = (health.hp / health.max.max(1.0)).clamp(0.0, 1.0);
    let (node, color) = &mut *fill;
    node.width = Val::Percent(frac * 100.0);
    color.0 = if frac < 0.3 { RED } else if frac < 0.6 { AMBER } else { WHITE };
    texts.p0().0 = format!("{:.0}", health.hp.max(0.0));
    let (tag, color) = if !health.alive() { ("RESPAWNING", RED) } else if health.bleeding > 0.0 { ("BLEEDING", RED) } else if frac < 0.3 { ("CRITICAL", AMBER) } else { ("HP", DIM) };
    let mut t = texts.p1();
    t.0.0 = tag.into();
    t.1.0 = color;
    if health.hit_this_tick {
        *level = 0.45;
    }
    *level = (*level - time.delta_secs() * 1.5).max(if health.alive() { 0.0 } else { 0.35 });
    flash.0 = Color::srgba(0.8, 0.0, 0.0, *level);
}

fn update_grapple(tuning: Res<Tuning>, grapple: Option<Res<crate::abilities::GrappleState>>, mut bar: Single<&mut Visibility, With<GrappleBar>>, mut fill: Single<&mut Node, With<GrappleFill>>) {
    let Some(g) = grapple else {
        **bar = Visibility::Hidden;
        return;
    };
    fill.width = Val::Percent(100.0 * g.power / tuning.grapple.power_max.max(1.0));
    **bar = if g.enabled && (g.hooked() || g.power < tuning.grapple.power_max) { Visibility::Inherited } else { Visibility::Hidden };
}

/// The menu hint fades out over the first seconds of play.
fn update_hint(time: Res<Time>, mut hint: Single<&mut TextColor, With<HintText>>, mut shown: Local<f32>) {
    *shown += time.delta_secs();
    let a = ((12.0 - *shown) / 3.0).clamp(0.0, 1.0) * 0.55;
    hint.0 = Color::srgba(1.0, 1.0, 1.0, a);
}

/// Places the flight reticle: the velocity ring and nose cross where they fall on screen, and the
/// horizon line banked and shifted with the ship.
#[allow(clippy::type_complexity)]
fn update_reticle(
    flight: Res<FlightHud>,
    camera: Option<Single<(&Camera, &GlobalTransform), With<crate::camera::PlayerCamera>>>,
    mut velocity: Single<(&mut Node, &mut Visibility), (With<VelocityMark>, Without<NoseMark>, Without<Horizon>)>,
    mut nose: Single<(&mut Node, &mut Visibility), (With<NoseMark>, Without<VelocityMark>, Without<Horizon>)>,
    mut horizon: Single<(&mut Node, &mut Visibility, &mut UiTransform), (With<Horizon>, Without<VelocityMark>, Without<NoseMark>)>,
) {
    let hide = |v: &mut Mut<Visibility>| {
        v.set_if_neq(Visibility::Hidden);
    };
    let Some(camera) = camera.filter(|_| flight.active) else {
        hide(&mut velocity.1);
        hide(&mut nose.1);
        hide(&mut horizon.1);
        return;
    };
    let (camera, eye) = *camera;
    let place = |dir: Vec3, size: Vec2, node: &mut Node, vis: &mut Mut<Visibility>| match camera.world_to_viewport(eye, eye.translation() + dir * 1000.0) {
        Ok(at) if dir != Vec3::ZERO => {
            node.left = Val::Px(at.x - size.x / 2.0);
            node.top = Val::Px(at.y - size.y / 2.0);
            vis.set_if_neq(Visibility::Inherited);
        }
        _ => {
            vis.set_if_neq(Visibility::Hidden);
        }
    };
    let moving = if flight.speed > 3.0 { flight.velocity.normalize_or_zero() } else { Vec3::ZERO };
    let (node, vis) = &mut *velocity;
    place(moving, Vec2::splat(14.0), node, vis);
    let (node, vis) = &mut *nose;
    place(flight.nose, Vec2::new(18.0, 2.0), node, vis);
    // The horizon ahead: where the nose's heading meets it, and which way it runs across the screen.
    let (node, vis, transform) = &mut *horizon;
    let ahead = (flight.nose - flight.up * flight.nose.dot(flight.up)).normalize_or_zero();
    let across = ahead.cross(flight.up);
    let ends = (camera.world_to_viewport(eye, eye.translation() + ahead * 1000.0), camera.world_to_viewport(eye, eye.translation() + (ahead + across * 0.1) * 1000.0));
    match ends {
        (Ok(a), Ok(b)) if flight.altitude.is_some() && ahead != Vec3::ZERO => {
            node.left = Val::Px(a.x - 120.0);
            node.top = Val::Px(a.y);
            node.margin = UiRect::ZERO;
            let d = b - a;
            transform.rotation = Rot2::radians(d.y.atan2(d.x));
            vis.set_if_neq(Visibility::Inherited);
        }
        _ => {
            vis.set_if_neq(Visibility::Hidden);
        }
    }
}
