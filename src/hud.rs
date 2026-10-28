//! The in-game HUD in the comic look (`crate::comic`, look A): a paper compass strip with the
//! objective marked on it, the objective in a yellow caption top left, a paper health card bottom
//! left (segments, grapple meter under the crosshair), a movement readout bottom centre (speedo
//! while driving), an ink weapon card bottom right with slot pips, ammo pips, fitted parts and the
//! heat bar, an ink-outlined crosshair that opens with spread, a halftone hit vignette and comic
//! pops on hits. Everything hangs off `HudRoot` so the menus can hide it.

use bevy::prelude::*;
use bevy::window::PrimaryWindow;

use crate::bots::MatchState;
use crate::comic::widgets::{filled_segments, pips, MAX_PIPS};
use crate::comic::{body_text, display_text, panel, sfx_pop, ComicTheme, Halftone};
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
            .init_resource::<ComicTheme>()
            .add_systems(Startup, spawn_hud)
            .add_systems(Update, (update_speed, update_weapon, update_crosshair, update_health, update_objective, update_compass, update_grapple, update_hint, pop_on_hits));
    }
}

/// Every HUD element hangs off this, so menus can hide it in one go. Other modules put it on
/// their own in-game text (the world clock) for the same reason.
#[derive(Component)]
pub struct HudRoot;

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
struct AmmoText;
#[derive(Component)]
struct MagText;
#[derive(Component)]
struct AmmoPip(u32);
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
#[derive(Component)]
struct CrosshairDot;
#[derive(Component)]
struct HealthSeg(usize);
#[derive(Component)]
struct HealthText;
#[derive(Component)]
struct HealthTag;
/// The red halftone vignette on a hit; the handle when the halftone material is available (it
/// isn't in headless tests), else a plain tint.
#[derive(Component)]
struct HitFlash(Option<Handle<Halftone>>);
#[derive(Component)]
struct ObjectiveText;
#[derive(Component)]
struct ObjectiveBox;
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

const TAPE_PX: f32 = 2.4;
const TAPE_HALF: f32 = 70.0;
const HEALTH_SEGMENTS: usize = 10;

/// The comic word for what the last frame's score change was: a kill beats a hit.
pub(crate) fn pop_word(hits: u32, kills: u32, prev: (u32, u32)) -> Option<&'static str> {
    if kills > prev.1 {
        Some("KO!")
    } else if hits > prev.0 {
        Some("HIT!")
    } else {
        None
    }
}

fn abs_node(left: Option<f32>, right: Option<f32>, top: Option<f32>, bottom: Option<f32>, width: f32) -> Node {
    let v = |o: Option<f32>| o.map_or(Val::Auto, Val::Px);
    Node { position_type: PositionType::Absolute, left: v(left), right: v(right), top: v(top), bottom: v(bottom), width: Val::Px(width), flex_direction: FlexDirection::Column, ..default() }
}

/// A bar with an ink border holding one fill child tagged `tag`.
fn ink_bar(p: &mut ChildSpawnerCommands, theme: &ComicTheme, width: Val, height: f32, fill: Color, tag: impl Bundle) {
    p.spawn((Node { width, height: Val::Px(height), border: UiRect::all(Val::Px(2.0)), ..default() }, BorderColor::all(theme.ink), BackgroundColor(theme.paper)))
        .with_child((tag, Node { width: Val::Percent(0.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(fill)));
}

fn spawn_hud(mut commands: Commands, theme: Res<ComicTheme>, halftones: Option<ResMut<Assets<Halftone>>>) {
    let t = theme.clone();
    let flash = halftones.map(|mut h| {
        let mut m = Halftone { fill: Color::NONE.into(), dot: t.red.with_alpha(0.0).into(), params: crate::comic::halftone::halftone_params(13.0, 4.5) };
        m.params.w = 1.0;
        h.add(m)
    });
    let root = commands.spawn((HudRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() })).id();
    let mut root = commands.entity(root);
    root.with_children(|p| {
        // Red halftone vignette that flashes on a hit and stays while dead.
        let full = Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() };
        match &flash {
            Some(h) => p.spawn((HitFlash(Some(h.clone())), full, bevy::ui_render::prelude::MaterialNode(h.clone()), ZIndex(-1))),
            None => p.spawn((HitFlash(None), full, BackgroundColor(Color::NONE), ZIndex(-1))),
        };

        // Compass strip, top centre: cardinal letters slide past an ink notch; the objective rides on it.
        let tape_w = TAPE_HALF * 2.0 * TAPE_PX;
        p.spawn((
            Node { position_type: PositionType::Absolute, top: Val::Px(14.0), left: Val::Percent(50.0), width: Val::Px(tape_w), height: Val::Px(34.0), margin: UiRect::left(Val::Px(-tape_w / 2.0)), overflow: Overflow::clip(), border: UiRect::all(Val::Px(t.ink_px)), ..default() },
            BackgroundColor(t.paper),
            BorderColor::all(t.ink),
            BoxShadow(vec![ShadowStyle { color: t.ink, x_offset: Val::Px(4.0), y_offset: Val::Px(4.0), spread_radius: Val::ZERO, blur_radius: Val::ZERO }]),
        ))
        .with_children(|c| {
            for i in 0..24 {
                let angle = i as f32 * 15.0;
                let label = match i {
                    0 => Some(("N", 24.0, t.red)),
                    6 => Some(("E", 20.0, t.ink)),
                    12 => Some(("S", 20.0, t.ink)),
                    18 => Some(("W", 20.0, t.ink)),
                    3 | 9 | 15 | 21 => Some((["NE", "SE", "SW", "NW"][(i / 6) as usize], 14.0, t.muted)),
                    _ => None,
                };
                match label {
                    Some((s, px, col)) => {
                        c.spawn((CompassTick(angle), display_text(s, px, col, &t), Node { position_type: PositionType::Absolute, top: Val::Px(0.0), ..default() }));
                    }
                    None => {
                        c.spawn((CompassTick(angle), Node { position_type: PositionType::Absolute, top: Val::Px(16.0), width: Val::Px(2.0), height: Val::Px(8.0), ..default() }, BackgroundColor(t.muted)));
                    }
                }
            }
            c.spawn((ObjectiveMark, Node { position_type: PositionType::Absolute, top: Val::Px(18.0), width: Val::Px(8.0), height: Val::Px(8.0), ..default() }, BackgroundColor(t.red), UiTransform::from_rotation(Rot2::degrees(45.0)), Visibility::Hidden));
            c.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(tape_w / 2.0 - t.ink_px - 1.5), top: Val::Px(0.0), width: Val::Px(3.0), height: Val::Px(26.0), ..default() }, BackgroundColor(t.ink)));
        });

        // Objective: a yellow caption top left, hidden while there is nothing to say.
        p.spawn((ObjectiveBox, abs_node(Some(24.0), None, Some(20.0), None, 340.0), Visibility::Hidden)).with_children(|b| {
            let t2 = t.clone();
            panel(b, &t, t.yellow, -2.0, move |c| {
                c.spawn((ObjectiveText, body_text("", 18.0, t2.ink, true, &t2)));
            });
        });

        // Top right: score, the haul (the world clock sits under them, from `world`), the menu hint.
        let shadow = TextShadow { offset: Vec2::splat(2.0), color: t.ink };
        p.spawn((ScoreText, body_text("", 16.0, t.paper, true, &t), shadow, Node { position_type: PositionType::Absolute, top: Val::Px(14.0), right: Val::Px(24.0), ..default() }));
        p.spawn((HaulText, body_text("", 16.0, t.paper, true, &t), shadow, Node { position_type: PositionType::Absolute, top: Val::Px(34.0), right: Val::Px(24.0), ..default() }));
        p.spawn((HintText, body_text("ESC  MENU", 14.0, t.paper, true, &t), shadow, Node { position_type: PositionType::Absolute, top: Val::Px(54.0), right: Val::Px(24.0), ..default() }));

        // Crosshair: four white lines with an ink outline that open with spread, a dot in the middle.
        let outline = Outline { width: Val::Px(1.5), offset: Val::ZERO, color: t.ink };
        for dir in [Vec2::X, Vec2::NEG_X, Vec2::Y, Vec2::NEG_Y] {
            let (w, h) = if dir.x != 0.0 { (10.0, 3.0) } else { (3.0, 10.0) };
            p.spawn((CrosshairLine(dir), Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(w), height: Val::Px(h), ..default() }, BackgroundColor(Color::WHITE), outline));
        }
        p.spawn((CrosshairDot, Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(3.0), height: Val::Px(3.0), margin: UiRect::all(Val::Px(-1.5)), ..default() }, BackgroundColor(Color::WHITE), outline));
        // Grapple power, a blue bar under the crosshair that only shows while charging or pulling.
        p.spawn((GrappleBar, Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(56.0), margin: UiRect { left: Val::Px(-28.0), top: Val::Px(22.0), ..default() }, ..default() })).with_children(|g| {
            ink_bar(g, &t, Val::Percent(100.0), 9.0, t.blue, GrappleFill);
        });

        // Bottom left: health card.
        p.spawn(abs_node(Some(24.0), None, None, Some(24.0), 300.0)).with_children(|b| {
            let t2 = t.clone();
            panel(b, &t, t.paper, -1.5, move |c| {
                c.spawn(Node { justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, ..default() }).with_children(|r| {
                    r.spawn((HealthTag, display_text("HP", 22.0, t2.ink, &t2)));
                    r.spawn((HealthText, display_text("100", 40.0, t2.red, &t2)));
                });
                c.spawn(Node { column_gap: Val::Px(4.0), ..default() }).with_children(|r| {
                    for i in 0..HEALTH_SEGMENTS {
                        r.spawn((HealthSeg(i), Node { flex_grow: 1.0, height: Val::Px(16.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BackgroundColor(t2.red), BorderColor::all(t2.ink)));
                    }
                });
            });
        });

        // Bottom centre: movement, or the vehicle's dials.
        p.spawn(Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), bottom: Val::Px(24.0), width: Val::Px(300.0), margin: UiRect::left(Val::Px(-150.0)), flex_direction: FlexDirection::Column, ..default() }).with_children(|b| {
            let t2 = t.clone();
            panel(b, &t, t.paper, 0.0, move |c| {
                c.spawn((StateText, display_text("", 18.0, t2.red, &t2)));
                c.spawn((SpeedText, body_text("", 18.0, t2.ink, true, &t2)));
                c.spawn((VehicleBars, Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(8.0), display: Display::None, ..default() })).with_children(|v| {
                    ink_bar(v, &t2, Val::Px(150.0), 10.0, t2.orange, RpmFill);
                    ink_bar(v, &t2, Val::Px(90.0), 10.0, t2.blue, FuelFill);
                });
            });
        });

        // Bottom right: weapon card.
        p.spawn(abs_node(None, Some(24.0), None, Some(24.0), 300.0)).with_children(|b| {
            let t2 = t.clone();
            panel(b, &t, t.ink, 1.5, move |c| {
                c.spawn(Node { column_gap: Val::Px(4.0), ..default() }).with_children(|r| {
                    for i in 0..WEAPONS.len() {
                        r.spawn((SlotPip(i), Node { width: Val::Px(14.0), height: Val::Px(5.0), ..default() }, BackgroundColor(t2.muted)));
                    }
                });
                c.spawn((WeaponText, display_text("", 26.0, t2.yellow, &t2)));
                c.spawn(Node { align_items: AlignItems::Baseline, column_gap: Val::Px(8.0), ..default() }).with_children(|r| {
                    r.spawn((AmmoText, display_text("", 52.0, t2.paper, &t2)));
                    r.spawn((MagText, body_text("", 22.0, t2.paper, true, &t2)));
                });
                c.spawn(Node { column_gap: Val::Px(4.0), flex_wrap: FlexWrap::Wrap, row_gap: Val::Px(4.0), ..default() }).with_children(|r| {
                    for i in 0..MAX_PIPS {
                        r.spawn((AmmoPip(i), Node { width: Val::Px(10.0), height: Val::Px(10.0), border: UiRect::all(Val::Px(2.0)), border_radius: BorderRadius::all(Val::Percent(50.0)), display: Display::None, ..default() }, BackgroundColor(t2.yellow), BorderColor::all(t2.yellow)));
                    }
                });
                c.spawn((PartsText, body_text("", 14.0, t2.paper.with_alpha(0.75), false, &t2)));
                ink_bar(c, &t2, Val::Percent(100.0), 8.0, t2.orange, HeatFill);
            });
        });
    });
}

fn update_speed(
    player: Single<(&Player, Option<&crate::vehicle::Driving>)>,
    vehicles: Query<(&crate::vehicle::Vehicle, &avian3d::prelude::LinearVelocity)>,
    mut texts: ParamSet<(Single<&mut Text, With<SpeedText>>, Single<&mut Text, With<StateText>>)>,
    mut nodes: ParamSet<(Single<&mut Node, With<VehicleBars>>, Single<&mut Node, With<RpmFill>>, Single<&mut Node, With<FuelFill>>)>,
) {
    let (player, driving) = *player;
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

#[allow(clippy::too_many_arguments)]
fn update_weapon(
    arsenal: Res<Arsenal>,
    tuning: Res<Tuning>,
    loadout: Res<Loadout>,
    recoil: Option<Res<Recoil>>,
    score: Res<Score>,
    theme: Res<ComicTheme>,
    mut texts: ParamSet<(Single<&mut Text, With<WeaponText>>, Single<&mut Text, With<AmmoText>>, Single<&mut Text, With<MagText>>, Single<&mut Text, With<PartsText>>, Single<&mut Text, With<ScoreText>>)>,
    mut slot_pips: Query<(&SlotPip, &mut BackgroundColor), Without<AmmoPip>>,
    mut ammo: Query<(&AmmoPip, &mut Node, &mut BackgroundColor), Without<SlotPip>>,
    mut heat: Single<(&mut Node, &mut BackgroundColor), (With<HeatFill>, Without<SlotPip>, Without<AmmoPip>)>,
) {
    let kind = arsenal.kind();
    texts.p0().0 = kind.name().into();
    let rounds = arsenal.rounds(&tuning);
    let (big, small) = match rounds {
        _ if arsenal.reload > 0.0 => (String::new(), "RELOADING".to_string()),
        Some((left, mag)) => {
            let (_, _, over) = pips(left, mag);
            (left.to_string(), if over > 0 { format!("/ {mag}  +{over}") } else { format!("/ {mag}") })
        }
        None => (String::new(), String::new()),
    };
    texts.p1().0 = big;
    texts.p2().0 = small;
    let (filled, empty, _) = match rounds {
        Some((left, mag)) if arsenal.reload <= 0.0 => pips(left, mag),
        _ => (0, 0, 0),
    };
    for (pip, mut node, mut color) in &mut ammo {
        node.display = if pip.0 < filled + empty { Display::Flex } else { Display::None };
        color.0 = if pip.0 < filled { theme.yellow } else { Color::NONE };
    }
    texts.p3().0 = if !crate::gunsmith::customizable(kind) {
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
    for (pip, mut color) in &mut slot_pips {
        color.0 = if pip.0 == arsenal.current { theme.yellow } else { theme.muted };
    }
    let h = recoil.map_or(0.0, |r| r.heat);
    let (node, color) = &mut *heat;
    node.width = Val::Percent(h.clamp(0.0, 1.0) * 100.0);
    color.0 = if h > 0.7 { theme.red } else { theme.orange };
    if score.is_changed() {
        texts.p4().0 = format!("HITS {}   KILLS {}", score.hits, score.kills);
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
    theme: Res<ComicTheme>,
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
    let mut color = if *flash > 0.0 { theme.red } else if ads > 0.5 { theme.yellow } else { Color::WHITE };
    // A fitted red dot or scope is the aim point while aiming: the crosshair fades out of its way.
    if crate::gunsmith::customizable(kind) && loadout.part(kind, 0) > 0 {
        color.set_alpha(color.alpha() * (1.0 - ads));
    }
    for (line, mut node, mut bg) in &mut lines {
        let d = line.0;
        let (w, h) = if d.x != 0.0 { (10.0, 3.0) } else { (3.0, 10.0) };
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
    mut objective_box: Single<&mut Visibility, With<ObjectiveBox>>,
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
    **objective_box = if line.is_empty() { Visibility::Hidden } else { Visibility::Inherited };
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
fn update_compass(view: Res<ViewAngles>, objective: Option<Res<ObjectiveHud>>, mut ticks: Query<(&CompassTick, &mut Node)>, mut mark: Single<(&mut Node, &mut Visibility), (With<ObjectiveMark>, Without<CompassTick>)>) {
    let heading = (-view.yaw.to_degrees()).rem_euclid(360.0);
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
    theme: Res<ComicTheme>,
    mut segments: Query<(&HealthSeg, &mut BackgroundColor)>,
    mut texts: ParamSet<(Single<&mut Text, With<HealthText>>, Single<(&mut Text, &mut TextColor), With<HealthTag>>)>,
    mut flash: Single<(&HitFlash, Option<&mut BackgroundColor>), Without<HealthSeg>>,
    mut halftones: Option<ResMut<Assets<Halftone>>>,
    mut level: Local<f32>,
) {
    let frac = (health.hp / health.max.max(1.0)).clamp(0.0, 1.0);
    let filled = filled_segments(health.hp, health.max, HEALTH_SEGMENTS);
    for (seg, mut color) in &mut segments {
        color.0 = if seg.0 < filled { theme.red } else { theme.paper };
    }
    texts.p0().0 = format!("{:.0}", health.hp.max(0.0));
    let (tag, color) = if !health.alive() { ("RESPAWNING", theme.red) } else if health.bleeding > 0.0 { ("BLEEDING", theme.red) } else if frac < 0.3 { ("CRITICAL", theme.orange) } else { ("HP", theme.ink) };
    let mut t = texts.p1();
    t.0.0 = tag.into();
    t.1.0 = color;
    if health.hit_this_tick {
        *level = 0.9;
    }
    let before = *level;
    *level = (*level - time.delta_secs() * 2.5).max(if health.alive() { 0.0 } else { 0.6 });
    if *level == before && !health.hit_this_tick {
        return;
    }
    let (hit, bg) = &mut *flash;
    match (&hit.0, halftones.as_mut()) {
        (Some(h), Some(assets)) => {
            if let Some(mut m) = assets.get_mut(h) {
                m.dot = theme.red.with_alpha(*level).into();
            }
        }
        _ => {
            if let Some(bg) = bg {
                bg.0 = theme.red.with_alpha(*level * 0.5);
            }
        }
    }
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
    let a = ((12.0 - *shown) / 3.0).clamp(0.0, 1.0) * 0.9;
    hint.0.set_alpha(a);
}

/// A comic word ("HIT!", "KO!") pops beside the crosshair when the score goes up, at most one a
/// frame, tilting left and right in turn.
fn pop_on_hits(mut commands: Commands, score: Res<Score>, theme: Res<ComicTheme>, window: Option<Single<&Window, With<PrimaryWindow>>>, mut prev: Local<(u32, u32)>, mut flip: Local<bool>) {
    if !score.is_changed() {
        return;
    }
    let word = pop_word(score.hits, score.kills, *prev);
    *prev = (score.hits, score.kills);
    let Some(word) = word else { return };
    let size = window.map_or(Vec2::new(1280.0, 720.0), |w| w.size());
    *flip = !*flip;
    sfx_pop(&mut commands, &theme, word, size / 2.0 + Vec2::new(60.0, -110.0), if *flip { -12.0 } else { 10.0 });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pop_word_prefers_kills() {
        assert_eq!(pop_word(5, 1, (4, 0)), Some("KO!"));
        assert_eq!(pop_word(5, 0, (4, 0)), Some("HIT!"));
        assert_eq!(pop_word(4, 0, (4, 0)), None);
        assert_eq!(pop_word(0, 0, (4, 1)), None, "a reset score is not a hit");
    }

    #[test]
    fn hud_spawns_without_the_comic_plugin() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).init_resource::<ComicTheme>().add_systems(Startup, spawn_hud);
        app.update();
        let w = app.world_mut();
        assert_eq!(w.query::<&AmmoPip>().iter(w).count(), MAX_PIPS as usize);
        assert_eq!(w.query::<&HealthSeg>().iter(w).count(), HEALTH_SEGMENTS);
        assert_eq!(w.query::<&HitFlash>().iter(w).count(), 1);
    }
}
