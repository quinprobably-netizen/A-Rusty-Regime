//! The in-game HUD in the comic look (`crate::comic`, look A): a paper compass strip with the
//! objective marked on it, the objective in a yellow caption top left, a paper health card bottom
//! left (segments, grapple meter under the crosshair), a movement readout bottom centre (speedo
//! while driving), an ink weapon card bottom right with slot pips, ammo pips, fitted parts and the
//! heat bar, an ink-outlined crosshair that opens with spread, a halftone hit vignette and comic
//! pops on hits. Flying, the flight dials take the bottom centre, and a paper ship card (hull and
//! shield) and an ink guns card (heat, missiles) take the places of the health and weapon cards,
//! with a hit marker round the nose and a warning when an enemy missile is on you; the on-foot
//! cards stay hidden until you are on your feet again, through the SHOT DOWN pause and card.
//! Everything hangs off `HudRoot` so the menus can hide it.

use bevy::prelude::*;

use crate::comic::widgets::{filled_segments, pips, MAX_PIPS};
use crate::comic::{body_text, display_text, panel, ComicTheme, Halftone};
use crate::controller::{MoveState, Player};
use crate::gunsmith::{Loadout, PARTS, SLOTS};
use crate::health::PlayerHealth;
use crate::input::ViewAngles;
use crate::save::Save;
use crate::tuning::Tuning;
use crate::weapon::{Aim, Arsenal, Recoil, WEAPONS, WeaponKind};

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PlayerHealth>()
            .init_resource::<ComicTheme>()
            .init_resource::<FlightHud>()
            .add_systems(Startup, spawn_hud)
            .add_systems(Update, (update_speed, update_weapon, update_crosshair, update_health, update_haul, update_compass, update_grapple, update_hint, update_reticle, update_ship_cards, update_hit_mark, update_threat));
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
    /// The ship's side of a fight (`solar::cockpit` fills it).
    pub fight: Fight,
}

/// The flown ship's hull, guns and missiles, and what the fight around it is doing.
#[derive(Default, Debug, Clone, PartialEq)]
pub struct Fight {
    /// Hull points and shield left, and what each is when whole.
    pub hull: f32,
    pub max_hull: f32,
    pub shield: f32,
    pub max_shield: f32,
    /// Nose gun heat, 0 to 1, and whether they have overheated and are cooling off.
    pub heat: f32,
    pub overheated: bool,
    /// Missiles on the rails, the most it carries, and how far the next one is back, 0 to 1.
    pub missiles: u32,
    pub max_missiles: u32,
    pub reload: f32,
    /// How far the lock on the ship in the nose has come, 0 to 1 (0 with nothing there).
    pub lock: f32,
    /// Seconds left of the hit marker, and whether it marks a kill.
    pub hit: f32,
    pub kill: bool,
    /// An enemy missile coming for this ship.
    pub threat: Threat,
}

/// How close an enemy's missile is to the ship: a Sentry holding a lock, or one in the air.
#[derive(Default, Debug, Clone, Copy, PartialEq, Eq)]
pub enum Threat {
    #[default]
    None,
    Locked,
    Missile,
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
struct CrosshairLine(Vec2);
#[derive(Component)]
pub(crate) struct CrosshairDot;
/// The weapon card, hidden while flying.
#[derive(Component)]
pub(crate) struct WeaponPlate;
/// Flight reticle: where the ship is going, where its nose points, and a horizon line.
#[derive(Component)]
struct VelocityMark;
#[derive(Component)]
struct NoseMark;
#[derive(Component)]
struct Horizon;
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
struct HaulText;
#[derive(Component)]
struct GrappleBar;
#[derive(Component)]
struct GrappleFill;
#[derive(Component)]
struct CompassTick(f32);
#[derive(Component)]
struct HintText;
/// The on-foot health card, and the flying ship's cards in its and the weapon card's places.
#[derive(Component)]
pub(crate) struct HealthCard;
#[derive(Component)]
pub(crate) struct ShipCard;
#[derive(Component)]
struct GunsCard;
#[derive(Component)]
struct HullSeg(usize);
#[derive(Component)]
struct HullText;
#[derive(Component)]
struct ShieldFill;
#[derive(Component)]
struct GunText;
#[derive(Component)]
struct GunHeatFill;
#[derive(Component)]
struct MissileText;
#[derive(Component)]
struct MissilePip(u32);
#[derive(Component)]
struct ReloadFill;
/// Four ticks round the nose that flash when your shots land; bigger and red on a kill.
#[derive(Component)]
struct HitMark;
#[derive(Component)]
struct HitTick(Vec2);
#[derive(Component)]
struct ThreatText;

const TAPE_PX: f32 = 2.4;
const TAPE_HALF: f32 = 70.0;
const HEALTH_SEGMENTS: usize = 10;
/// Most missile pips the guns card draws.
const MISSILE_PIPS: u32 = 8;

/// Whether the on-foot cards (health, weapon, crosshair) show: not while flying, nor while the
/// SHOT DOWN card is up, though nobody is flying then.
pub fn on_foot(flight: &FlightHud, downed: Option<&crate::solar::loss::Downed>) -> bool {
    !flight.active && !downed.is_some_and(|d| d.showing())
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

        // Compass strip, top centre: cardinal letters slide past an ink notch.
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
            c.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(tape_w / 2.0 - t.ink_px - 1.5), top: Val::Px(0.0), width: Val::Px(3.0), height: Val::Px(26.0), ..default() }, BackgroundColor(t.ink)));
        });

        // Top right: the haul (the bank and your scrap) and the menu hint.
        let shadow = TextShadow { offset: Vec2::splat(2.0), color: t.ink };
        p.spawn((HaulText, body_text("", 16.0, t.paper, true, &t), shadow, Node { position_type: PositionType::Absolute, top: Val::Px(34.0), right: Val::Px(24.0), ..default() }));
        p.spawn((HintText, body_text("ESC  MENU", 14.0, t.paper, true, &t), shadow, Node { position_type: PositionType::Absolute, top: Val::Px(54.0), right: Val::Px(24.0), ..default() }));

        // Crosshair: four white lines with an ink outline that open with spread, a dot in the middle.
        let outline = Outline { width: Val::Px(1.5), offset: Val::ZERO, color: t.ink };
        for dir in [Vec2::X, Vec2::NEG_X, Vec2::Y, Vec2::NEG_Y] {
            let (w, h) = if dir.x != 0.0 { (10.0, 3.0) } else { (3.0, 10.0) };
            p.spawn((CrosshairLine(dir), Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(w), height: Val::Px(h), ..default() }, BackgroundColor(Color::WHITE), outline));
        }
        // Flight reticle: a yellow ink-ringed circle where the ship is heading, an ink-outlined
        // cross where the nose points, and an ink horizon tilted with the ship's bank.
        p.spawn((VelocityMark, Node { position_type: PositionType::Absolute, width: Val::Px(16.0), height: Val::Px(16.0), border: UiRect::all(Val::Px(3.0)), border_radius: BorderRadius::all(Val::Px(8.0)), ..default() }, BorderColor::all(t.yellow), Outline { width: Val::Px(2.0), offset: Val::ZERO, color: t.ink }, Visibility::Hidden));
        p.spawn((NoseMark, Node { position_type: PositionType::Absolute, width: Val::Px(20.0), height: Val::Px(3.0), ..default() }, BackgroundColor(Color::WHITE), outline, Visibility::Hidden))
            .with_child((Node { position_type: PositionType::Absolute, left: Val::Px(8.5), top: Val::Px(-8.5), width: Val::Px(3.0), height: Val::Px(20.0), ..default() }, BackgroundColor(Color::WHITE), outline));
        p.spawn((Horizon, Node { position_type: PositionType::Absolute, width: Val::Px(240.0), height: Val::Px(3.0), ..default() }, BackgroundColor(t.ink.with_alpha(0.7)), UiTransform::default(), Visibility::Hidden));
        p.spawn((CrosshairDot, Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(3.0), height: Val::Px(3.0), margin: UiRect::all(Val::Px(-1.5)), ..default() }, BackgroundColor(Color::WHITE), outline));
        // Grapple power, a blue bar under the crosshair that only shows while charging or pulling.
        p.spawn((GrappleBar, Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Percent(50.0), width: Val::Px(56.0), margin: UiRect { left: Val::Px(-28.0), top: Val::Px(22.0), ..default() }, ..default() })).with_children(|g| {
            ink_bar(g, &t, Val::Percent(100.0), 9.0, t.blue, GrappleFill);
        });

        // Bottom left: health card.
        p.spawn((HealthCard, abs_node(Some(24.0), None, None, Some(24.0), 300.0))).with_children(|b| {
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
        p.spawn((WeaponPlate, abs_node(None, Some(24.0), None, Some(24.0), 300.0))).with_children(|b| {
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

        // Flying, bottom left: the ship card, hull in segments like health and the shield bar.
        let mut card = abs_node(Some(24.0), None, None, Some(24.0), 300.0);
        card.display = Display::None;
        p.spawn((ShipCard, card)).with_children(|b| {
            let t2 = t.clone();
            panel(b, &t, t.paper, -1.5, move |c| {
                c.spawn(Node { justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, ..default() }).with_children(|r| {
                    r.spawn(display_text("HULL", 22.0, t2.ink, &t2));
                    r.spawn((HullText, display_text("", 40.0, t2.red, &t2)));
                });
                c.spawn(Node { column_gap: Val::Px(4.0), ..default() }).with_children(|r| {
                    for i in 0..HEALTH_SEGMENTS {
                        r.spawn((HullSeg(i), Node { flex_grow: 1.0, height: Val::Px(16.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BackgroundColor(t2.red), BorderColor::all(t2.ink)));
                    }
                });
                c.spawn(Node { align_items: AlignItems::Center, column_gap: Val::Px(8.0), ..default() }).with_children(|r| {
                    r.spawn(body_text("SHIELD", 14.0, t2.ink, true, &t2));
                    r.spawn(Node { flex_grow: 1.0, ..default() }).with_children(|g| ink_bar(g, &t2, Val::Percent(100.0), 12.0, t2.blue, ShieldFill));
                });
            });
        });
        // Flying, bottom right: the guns card, nose gun heat and the missiles on the rails.
        let mut card = abs_node(None, Some(24.0), None, Some(24.0), 300.0);
        card.display = Display::None;
        p.spawn((GunsCard, card)).with_children(|b| {
            let t2 = t.clone();
            panel(b, &t, t.ink, 1.5, move |c| {
                c.spawn((GunText, display_text("NOSE GUNS", 26.0, t2.yellow, &t2)));
                ink_bar(c, &t2, Val::Percent(100.0), 8.0, t2.orange, GunHeatFill);
                c.spawn(Node { align_items: AlignItems::Center, column_gap: Val::Px(8.0), ..default() }).with_children(|r| {
                    r.spawn((MissileText, display_text("", 40.0, t2.paper, &t2)));
                    r.spawn(body_text("MISSILES", 16.0, t2.paper, true, &t2));
                    r.spawn(Node { column_gap: Val::Px(5.0), ..default() }).with_children(|r| {
                        for i in 0..MISSILE_PIPS {
                            r.spawn((MissilePip(i), Node { width: Val::Px(10.0), height: Val::Px(18.0), border: UiRect::all(Val::Px(2.0)), display: Display::None, ..default() }, BackgroundColor(t2.yellow), BorderColor::all(t2.yellow)));
                        }
                    });
                });
                ink_bar(c, &t2, Val::Percent(100.0), 6.0, t2.blue, ReloadFill);
            });
        });
        // Round the nose: the hit marker, four ticks on the diagonals pointing in.
        p.spawn((HitMark, Node { position_type: PositionType::Absolute, width: Val::Px(0.0), height: Val::Px(0.0), ..default() }, Visibility::Hidden)).with_children(|h| {
            for d in [Vec2::new(1.0, 1.0), Vec2::new(-1.0, 1.0), Vec2::new(1.0, -1.0), Vec2::new(-1.0, -1.0)] {
                h.spawn((HitTick(d), Node { position_type: PositionType::Absolute, width: Val::Px(10.0), height: Val::Px(3.0), ..default() }, BackgroundColor(Color::WHITE), outline, UiTransform::from_rotation(Rot2::radians(d.y.atan2(d.x)))));
            }
        });
        // Under the compass: an enemy missile on you.
        p.spawn((ThreatText, display_text("", 34.0, t.red, &t), TextShadow { offset: Vec2::splat(3.0), color: t.ink }, Node { position_type: PositionType::Absolute, top: Val::Px(62.0), left: Val::Percent(50.0), width: Val::Px(400.0), margin: UiRect::left(Val::Px(-200.0)), justify_content: JustifyContent::Center, ..default() }, TextLayout::justify(Justify::Center), Visibility::Hidden));
    });
}

fn update_speed(
    player: Single<&Player>,
    flight: Res<FlightHud>,
    mut texts: ParamSet<(Single<&mut Text, With<SpeedText>>, Single<&mut Text, With<StateText>>)>,
    mut nodes: ParamSet<(Single<&mut Node, With<VehicleBars>>, Single<&mut Node, With<RpmFill>>, Single<&mut Node, With<FuelFill>>)>,
) {
    let player = *player;
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
    flight: Res<FlightHud>,
    downed: Option<Res<crate::solar::loss::Downed>>,
    mut plate: Single<&mut Node, (With<WeaponPlate>, Without<HeatFill>, Without<AmmoPip>)>,
    arsenal: Res<Arsenal>,
    tuning: Res<Tuning>,
    loadout: Res<Loadout>,
    recoil: Option<Res<Recoil>>,
    theme: Res<ComicTheme>,
    mut texts: ParamSet<(Single<&mut Text, With<WeaponText>>, Single<&mut Text, With<AmmoText>>, Single<&mut Text, With<MagText>>, Single<&mut Text, With<PartsText>>)>,
    mut slot_pips: Query<(&SlotPip, &mut BackgroundColor), Without<AmmoPip>>,
    mut ammo: Query<(&AmmoPip, &mut Node, &mut BackgroundColor), Without<SlotPip>>,
    mut heat: Single<(&mut Node, &mut BackgroundColor), (With<HeatFill>, Without<SlotPip>, Without<AmmoPip>)>,
) {
    plate.display = if on_foot(&flight, downed.as_deref()) { Display::Flex } else { Display::None };
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
}

/// The crosshair opens with heat and movement, and closes crouched or aiming.
fn update_crosshair(
    tuning: Res<Tuning>,
    arsenal: Res<Arsenal>,
    loadout: Res<Loadout>,
    recoil: Option<Res<Recoil>>,
    aim: Option<Res<Aim>>,
    theme: Res<ComicTheme>,
    flight: Res<FlightHud>,
    downed: Option<Res<crate::solar::loss::Downed>>,
    player: Single<(&Player, Has<crate::vehicle::Driving>)>,
    mut lines: Query<(&CrosshairLine, &mut Node, &mut BackgroundColor, Option<&mut Outline>)>,
    mut dot: Single<(&mut BackgroundColor, Option<&mut Outline>), (With<CrosshairDot>, Without<CrosshairLine>)>,
) {
    let (p, driving) = *player;
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
    let gap = 5.0 + spread * 6.0;
    let mut color = if ads > 0.5 { theme.yellow } else { Color::WHITE };
    // A fitted red dot or scope is the aim point while aiming: the crosshair fades out of its way.
    if crate::gunsmith::customizable(kind) && loadout.part(kind, 0) > 0 {
        color.set_alpha(color.alpha() * (1.0 - ads));
    }
    // Flying, the flight reticle takes over; shot down, nothing.
    if !on_foot(&flight, downed.as_deref()) {
        color = Color::NONE;
    }
    let ink = theme.ink.with_alpha(color.alpha());
    for (line, mut node, mut bg, outline) in &mut lines {
        if let Some(mut o) = outline {
            o.color = ink;
        }
        let d = line.0;
        let (w, h) = if d.x != 0.0 { (10.0, 3.0) } else { (3.0, 10.0) };
        // Lines start `gap` px from the centre, pointing outward.
        let x = if d.x > 0.0 { gap } else if d.x < 0.0 { -gap - w } else { -w / 2.0 };
        let y = if d.y > 0.0 { gap } else if d.y < 0.0 { -gap - h } else { -h / 2.0 };
        node.margin = UiRect { left: Val::Px(x), top: Val::Px(y), ..default() };
        bg.0 = color;
    }
    dot.0.0 = color;
    if let Some(o) = dot.1.as_mut() {
        o.color = ink;
    }
}

fn update_haul(save: Option<Res<Save>>, tuning: Res<crate::tuning::Tuning>, mut haul_text: Single<&mut Text, With<HaulText>>) {
    let s = save.map_or(String::new(), |save| haul(&save, &tuning.economy));
    if haul_text.0 != s {
        haul_text.0 = s;
    }
}

/// The top right's haul: the bank and what is in your pocket, and the scrap in the hold.
pub fn haul(save: &Save, e: &crate::tuning::Economy) -> String {
    let pocket = if save.pocket > 0 { format!(" +{}", save.pocket) } else { String::new() };
    format!("BANK {}{pocket}   SCRAP {}/{}", save.banked, save.scrap, crate::solar::economy::hold_cap(save, e))
}

/// Slide the compass ticks past the notch; yaw 0 looks down -Z, which is north.
fn update_compass(view: Res<ViewAngles>, flight: Res<FlightHud>, mut ticks: Query<(&CompassTick, &mut Node)>) {
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
}

#[allow(clippy::too_many_arguments)]
fn update_health(
    time: Res<Time>,
    health: Res<PlayerHealth>,
    theme: Res<ComicTheme>,
    flight: Res<FlightHud>,
    downed: Option<Res<crate::solar::loss::Downed>>,
    mut card: Single<&mut Node, With<HealthCard>>,
    mut segments: Query<(&HealthSeg, &mut BackgroundColor)>,
    mut texts: ParamSet<(Single<&mut Text, With<HealthText>>, Single<(&mut Text, &mut TextColor), With<HealthTag>>)>,
    mut flash: Single<(&HitFlash, Option<&mut BackgroundColor>), Without<HealthSeg>>,
    mut halftones: Option<ResMut<Assets<Halftone>>>,
    mut level: Local<f32>,
) {
    let shown = if on_foot(&flight, downed.as_deref()) { Display::Flex } else { Display::None };
    if card.display != shown {
        card.display = shown;
    }
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
fn update_hint(time: Res<Time>, actions: Option<Res<crate::controls::ActionState>>, mut hint: Single<(&mut TextColor, &mut Text), With<HintText>>, mut shown: Local<f32>) {
    // Names the pad's button or the key, whichever was touched last.
    let pad = actions.is_some_and(|a| a.pad_last);
    let text = format!("{}  MENU", crate::controls::hint(crate::controls::Ctx::Foot, crate::controls::Action::Pause, pad).to_uppercase());
    if hint.1.0 != text {
        hint.1.0 = text;
        *shown = 0.0;
    }
    let hint = &mut hint.0;
    *shown += time.delta_secs();
    let a = ((12.0 - *shown) / 3.0).clamp(0.0, 1.0) * 0.9;
    hint.0.set_alpha(a);
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
    place(moving, Vec2::splat(16.0), node, vis);
    let (node, vis) = &mut *nose;
    place(flight.nose, Vec2::new(20.0, 3.0), node, vis);
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

/// Flying, the ship card and the guns card in place of the health and weapon cards: hull in
/// segments, the shield bar, gun heat (red and OVERHEATED while they cool off), the missiles on
/// the rails and the next one coming back.
#[allow(clippy::type_complexity)]
fn update_ship_cards(
    flight: Res<FlightHud>,
    theme: Res<ComicTheme>,
    mut texts: ParamSet<(Single<&mut Text, With<HullText>>, Single<(&mut Text, &mut TextColor), With<GunText>>, Single<&mut Text, With<MissileText>>)>,
    mut segments: Query<(&HullSeg, &mut BackgroundColor), (Without<MissilePip>, Without<GunHeatFill>)>,
    mut fills: ParamSet<(Single<&mut Node, With<ShieldFill>>, Single<(&mut Node, &mut BackgroundColor), With<GunHeatFill>>, Single<&mut Node, With<ReloadFill>>, Query<&mut Node, Or<(With<ShipCard>, With<GunsCard>)>>)>,
    mut missile_pips: Query<(&MissilePip, &mut Node, &mut BackgroundColor), (Without<HullSeg>, Without<GunHeatFill>, Without<ShipCard>, Without<GunsCard>, Without<ShieldFill>, Without<ReloadFill>)>,
) {
    let shown = if flight.active { Display::Flex } else { Display::None };
    for mut card in &mut fills.p3() {
        if card.display != shown {
            card.display = shown;
        }
    }
    if !flight.active {
        return;
    }
    let f = &flight.fight;
    texts.p0().0 = format!("{:.0}", f.hull.max(0.0).ceil());
    let filled = filled_segments(f.hull, f.max_hull, HEALTH_SEGMENTS);
    for (seg, mut color) in &mut segments {
        color.0 = if seg.0 < filled { theme.red } else { theme.paper };
    }
    fills.p0().width = Val::Percent((f.shield / f.max_shield.max(1.0)).clamp(0.0, 1.0) * 100.0);
    {
        let mut heat = fills.p1();
        let (node, color) = &mut *heat;
        node.width = Val::Percent(f.heat.clamp(0.0, 1.0) * 100.0);
        color.0 = if f.overheated || f.heat > 0.7 { theme.red } else { theme.orange };
    }
    fills.p2().width = Val::Percent(f.reload.clamp(0.0, 1.0) * 100.0);
    {
        let mut gun = texts.p1();
        let (text, color) = &mut *gun;
        let (say, c) = if f.overheated { ("OVERHEATED", theme.red) } else { ("NOSE GUNS", theme.yellow) };
        if text.0 != say {
            text.0 = say.into();
        }
        color.0 = c;
    }
    texts.p2().0 = f.missiles.to_string();
    for (pip, mut node, mut color) in &mut missile_pips {
        node.display = if pip.0 < f.max_missiles.min(MISSILE_PIPS) { Display::Flex } else { Display::None };
        color.0 = if pip.0 < f.missiles { theme.yellow } else { Color::NONE };
    }
}

/// The hit marker round where the nose points: four white ticks for a hit, spread wider and red
/// for a kill, fading as it runs out.
#[allow(clippy::type_complexity)]
fn update_hit_mark(
    flight: Res<FlightHud>,
    theme: Res<ComicTheme>,
    camera: Option<Single<(&Camera, &GlobalTransform), With<crate::camera::PlayerCamera>>>,
    mut mark: Single<(&mut Node, &mut Visibility), (With<HitMark>, Without<HitTick>)>,
    mut ticks: Query<(&HitTick, &mut Node, &mut BackgroundColor, &mut Outline)>,
) {
    let f = &flight.fight;
    let at = camera.filter(|_| flight.active && f.hit > 0.0).and_then(|c| c.0.world_to_viewport(c.1, c.1.translation() + flight.nose * 1000.0).ok());
    let (node, vis) = &mut *mark;
    let Some(at) = at else {
        vis.set_if_neq(Visibility::Hidden);
        return;
    };
    node.left = Val::Px(at.x);
    node.top = Val::Px(at.y);
    vis.set_if_neq(Visibility::Inherited);
    let (gap, len, color, life) = if f.kill { (14.0, 16.0, theme.red, crate::solar::cockpit::KILL_MARK) } else { (9.0, 10.0, Color::WHITE, crate::solar::cockpit::HIT_MARK) };
    let alpha = (f.hit / life * 2.0).clamp(0.0, 1.0);
    for (tick, mut node, mut bg, mut outline) in &mut ticks {
        // Each tick's middle sits `gap` px out along its diagonal.
        let mid = tick.0.normalize() * (gap + len / 2.0);
        node.width = Val::Px(len);
        node.left = Val::Px(mid.x - len / 2.0);
        node.top = Val::Px(mid.y - 1.5);
        bg.0 = color.with_alpha(alpha);
        outline.color = theme.ink.with_alpha(alpha);
    }
}

/// MISSILE LOCK while an enemy holds a lock on you, a blinking MISSILE once one is in the air.
fn update_threat(time: Res<Time>, flight: Res<FlightHud>, mut text: Single<(&mut Text, &mut Visibility), With<ThreatText>>) {
    let (say, blink) = match flight.fight.threat {
        _ if !flight.active => ("", false),
        Threat::None => ("", false),
        Threat::Locked => ("MISSILE LOCK", false),
        Threat::Missile => ("MISSILE!", true),
    };
    let (t, vis) = &mut *text;
    if t.0 != say {
        t.0 = say.into();
    }
    let on = !say.is_empty() && (!blink || time.elapsed_secs().fract() < 0.6);
    vis.set_if_neq(if on { Visibility::Inherited } else { Visibility::Hidden });
}

#[cfg(test)]
mod tests {
    use super::*;

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
