//! Contacts: while you fly, a diamond in its faction's colour (the base colours in `bases.toml`)
//! on each enemy ship within 4 km, the nearest eight, with its type and distance, clamped to the
//! screen edge when it is off-screen or behind you like the waypoints (`waypoint::project`). The
//! ship your missiles are locking on gets a ring of ticks round its diamond that light up as the
//! lock comes on, and a solid ring once it is locked. A patrol that will not shoot you (your
//! standing with its faction is 0 or more, and you have not shot it) is a hollow diamond, its
//! outline in the faction's colour. They hide on foot and under the menus.

use std::f32::consts::TAU;

use bevy::prelude::*;
use bevy::window::PrimaryWindow;

use super::ai::Enemy;
use super::base::Bases;
use super::combat::{Faction, Hull};
use super::missile::Missiles;
use super::ship::{Ship, Ships};
use super::waypoint::{km, project, MARGIN};
use crate::camera::PlayerCamera;
use crate::hud::{FlightHud, HudRoot};
use crate::save::Save;
use crate::tuning::Tuning;

/// Enemy ships further off than this are not marked, metres.
pub const RANGE: f32 = 4000.0;
/// The most marked at once: the nearest.
pub const MOST: usize = 8;
/// Ticks round the lock ring.
pub const TICKS: usize = 12;
const SIZE: f32 = 12.0;
const RING: f32 = 19.0;
/// The raiders have no base, so no colour in `bases.toml`: theirs is a rust orange.
const RAIDERS: Color = Color::srgb(1.0, 0.45, 0.12);

pub fn build(app: &mut App) {
    app.init_resource::<crate::comic::ComicTheme>().add_systems(Startup, spawn_contacts).add_systems(Update, update_contacts);
}

/// Contact slot `n`'s pieces: the pin that is moved, its diamond, its label, the ticks of its lock
/// ring and the solid ring.
#[derive(Component)]
struct Pin(usize);
#[derive(Component)]
struct Diamond(usize);
#[derive(Component)]
struct Label(usize);
#[derive(Component)]
pub struct Tick(pub usize, pub usize);
#[derive(Component)]
struct Solid(usize);

/// A faction's colour: its base's in `bases.toml`.
pub fn faction_color(faction: Faction, bases: &Bases) -> Color {
    bases.base.iter().find(|b| b.faction == faction.id()).map_or(RAIDERS, |b| Color::srgb(b.color[0], b.color[1], b.color[2]))
}

/// The ships to mark from `from`: those within `RANGE`, nearest first, at most `MOST`, with how
/// far each is. `keep` (the ship being locked) is never the one dropped.
pub fn nearest(from: Vec3, ships: impl Iterator<Item = (Entity, Vec3)>, keep: Option<Entity>) -> Vec<(Entity, f32)> {
    let mut near: Vec<(Entity, f32)> = ships.map(|(e, at)| (e, at.distance(from))).filter(|(_, d)| *d <= RANGE).collect();
    near.sort_by(|a, b| (Some(b.0) == keep).cmp(&(Some(a.0) == keep)).then(a.1.total_cmp(&b.1)));
    near.truncate(MOST);
    near.sort_by(|a, b| a.1.total_cmp(&b.1));
    near
}

/// How many of the ring's ticks are lit at `lock` (0 to 1); all of them once it is locked.
pub fn lit(lock: f32) -> usize {
    if lock >= 1.0 { TICKS } else { ((lock.clamp(0.0, 1.0) * TICKS as f32).floor() as usize).min(TICKS - 1) }
}

fn spawn_contacts(mut commands: Commands, theme: Res<crate::comic::ComicTheme>) {
    let root = commands.spawn((HudRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() })).id();
    let outline = Outline { width: Val::Px(1.5), offset: Val::ZERO, color: theme.ink };
    for n in 0..MOST {
        let pin = commands
            .spawn((Pin(n), Node { position_type: PositionType::Absolute, width: Val::Px(0.0), height: Val::Px(0.0), ..default() }, Visibility::Hidden))
            .with_children(|p| {
                // Ticks round the clock face from twelve o'clock, then the solid ring over them.
                for i in 0..TICKS {
                    let a = i as f32 / TICKS as f32 * TAU;
                    let at = Vec2::new(a.sin(), -a.cos()) * RING;
                    p.spawn((
                        Tick(n, i),
                        Node { position_type: PositionType::Absolute, left: Val::Px(at.x - 2.0), top: Val::Px(at.y - 4.5), width: Val::Px(4.0), height: Val::Px(9.0), ..default() },
                        BackgroundColor(theme.paper.with_alpha(0.35)),
                        outline,
                        UiTransform::from_rotation(Rot2::radians(a)),
                        Visibility::Hidden,
                    ));
                }
                p.spawn((
                    Solid(n),
                    Node { position_type: PositionType::Absolute, left: Val::Px(-RING - 3.0), top: Val::Px(-RING - 3.0), width: Val::Px(RING * 2.0 + 6.0), height: Val::Px(RING * 2.0 + 6.0), border: UiRect::all(Val::Px(4.0)), border_radius: BorderRadius::all(Val::Percent(50.0)), ..default() },
                    BorderColor::all(theme.yellow),
                    Outline { width: Val::Px(2.0), offset: Val::ZERO, color: theme.ink },
                    Visibility::Hidden,
                ));
                p.spawn((
                    Diamond(n),
                    Node { position_type: PositionType::Absolute, left: Val::Px(-SIZE / 2.0), top: Val::Px(-SIZE / 2.0), width: Val::Px(SIZE), height: Val::Px(SIZE), border: UiRect::all(Val::Px(3.0)), ..default() },
                    BackgroundColor(RAIDERS),
                    BorderColor::all(theme.ink),
                    Outline { width: Val::Px(1.5), offset: Val::ZERO, color: Color::NONE },
                    UiTransform::from_rotation(Rot2::degrees(45.0)),
                ));
                p.spawn((
                    Label(n),
                    Node { position_type: PositionType::Absolute, left: Val::Px(RING + 6.0), top: Val::Px(-12.0), padding: UiRect::axes(Val::Px(5.0), Val::Px(1.0)), ..default() },
                    crate::comic::body_text("", 13.0, RAIDERS, true, &theme),
                    BackgroundColor(theme.ink),
                    TextLayout::no_wrap(),
                ));
            })
            .id();
        commands.entity(root).add_child(pin);
    }
}

/// Marks the nearest enemy ships of the one being flown, and the lock on the one in its nose.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn update_contacts(
    hud: Res<FlightHud>,
    bases: Res<Bases>,
    specs: Res<Ships>,
    tuning: Res<Tuning>,
    save: Option<Res<Save>>,
    theme: Res<crate::comic::ComicTheme>,
    camera: Query<(&Transform, &Projection), With<PlayerCamera>>,
    window: Query<&Window, With<PrimaryWindow>>,
    ships: Query<(Entity, &Ship, &Faction, &Transform, Option<&Missiles>), With<Hull>>,
    pilots: Query<&Enemy>,
    mut pins: Query<(&Pin, &mut Node, &mut Visibility), (Without<Label>, Without<Tick>, Without<Solid>)>,
    mut diamonds: Query<(&Diamond, &mut BackgroundColor, &mut BorderColor, &mut Outline), Without<Tick>>,
    mut labels: Query<(&Label, &mut Node, &mut Text, &mut TextColor), (Without<Pin>, Without<Tick>, Without<Solid>)>,
    mut ticks: Query<(&Tick, &mut Visibility, &mut BackgroundColor), (Without<Pin>, Without<Solid>, Without<Diamond>)>,
    mut solids: Query<(&Solid, &mut Visibility), (Without<Pin>, Without<Tick>)>,
) {
    let me = ships.iter().find(|(_, s, ..)| s.pilot.is_some());
    let view = camera.single().ok().zip(window.single().ok());
    let (Some((_, _, mine, from, missiles)), Some(((cam, projection), window)), true) = (me, view, hud.active) else {
        for (_, _, mut v) in &mut pins {
            v.set_if_neq(Visibility::Hidden);
        }
        return;
    };
    let Projection::Perspective(p) = projection else { return };
    let size = Vec2::new(window.width(), window.height());
    let tan_half = (p.fov / 2.0).tan();
    let inverse = cam.rotation.inverse();
    let target = missiles.and_then(|m| m.target);
    let lock = missiles.map_or(0.0, |m| m.lock);
    let enemies = ships.iter().filter(|(_, s, f, ..)| *f != mine && s.pilot.is_none()).map(|(e, _, _, tf, _)| (e, tf.translation));
    let marked = nearest(from.translation, enemies, target);
    // What each slot shows this frame: where, in what colour, what it says, how far the lock is,
    // and whether it will shoot you.
    let slots: Vec<(Vec2, Color, String, Option<f32>, bool)> = marked
        .iter()
        .filter_map(|(e, d)| {
            let (_, ship, faction, tf, _) = ships.get(*e).ok()?;
            let (point, _) = project(inverse * (tf.translation - cam.translation), tan_half, size, MARGIN);
            let locked = (Some(*e) == target).then_some(lock);
            let name = specs.ship[ship.spec].name.to_uppercase();
            let line = if locked.is_some_and(|l| l >= 1.0) { format!("{name}  LOCKED\n{}", km(*d)) } else { format!("{name}\n{}", km(*d)) };
            let hostile = pilots.get(*e).ok().is_none_or(|enemy| super::standing::attacks(enemy, *faction, save.as_deref(), &tuning.ship_combat));
            Some((point, faction_color(*faction, &bases), line, locked, hostile))
        })
        .collect();
    for (pin, mut node, mut v) in &mut pins {
        let Some((point, ..)) = slots.get(pin.0) else {
            v.set_if_neq(Visibility::Hidden);
            continue;
        };
        node.left = Val::Px(point.x);
        node.top = Val::Px(point.y);
        v.set_if_neq(Visibility::Inherited);
    }
    // Solid in its colour and ringed in ink when it will shoot; hollow, its outline in its colour
    // over a thin ink one, when it will not.
    for (d, mut bg, mut border, mut outline) in &mut diamonds {
        if let Some((_, color, _, _, hostile)) = slots.get(d.0) {
            bg.0 = if *hostile { *color } else { Color::NONE };
            border.set_all(if *hostile { theme.ink } else { *color });
            outline.color = if *hostile { Color::NONE } else { theme.ink };
        }
    }
    for (label, mut node, mut text, mut color) in &mut labels {
        let Some((point, c, line, ..)) = slots.get(label.0) else { continue };
        if text.0 != *line {
            text.0.clone_from(line);
        }
        color.0 = *c;
        // Past 70% of the way across, the label goes to the left of the diamond.
        let right_side = point.x > size.x * 0.7;
        node.left = if right_side { Val::Auto } else { Val::Px(RING + 6.0) };
        node.right = if right_side { Val::Px(RING + 6.0) } else { Val::Auto };
    }
    let locks = |n: usize| slots.get(n).and_then(|s| s.3);
    for (tick, mut v, mut bg) in &mut ticks {
        let shown = locks(tick.0).is_some_and(|l| l < 1.0);
        v.set_if_neq(if shown { Visibility::Inherited } else { Visibility::Hidden });
        bg.0 = if tick.1 < lit(locks(tick.0).unwrap_or(0.0)) { theme.yellow } else { theme.paper.with_alpha(0.35) };
    }
    for (solid, mut v) in &mut solids {
        let shown = locks(solid.0).is_some_and(|l| l >= 1.0);
        v.set_if_neq(if shown { Visibility::Inherited } else { Visibility::Hidden });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(n: u32, d: f32) -> (Entity, Vec3) {
        (Entity::from_raw_u32(n).unwrap(), Vec3::X * d)
    }

    #[test]
    fn only_the_nearest_eight_within_four_km_are_marked() {
        let ships = (1..=12).map(|n| at(n, n as f32 * 300.0)).chain([at(20, 4100.0)]);
        let marked = nearest(Vec3::ZERO, ships, None);
        assert_eq!(marked.len(), MOST);
        assert!(marked.windows(2).all(|w| w[0].1 <= w[1].1), "nearest first");
        assert_eq!(marked.last().unwrap().1, 2400.0, "the eighth nearest; the four past it and the one past 4 km are dropped");
        // The ship being locked is never the one left out, even as the ninth nearest.
        let ships = (1..=12).map(|n| at(n, n as f32 * 300.0));
        let marked = nearest(Vec3::ZERO, ships, Some(Entity::from_raw_u32(9).unwrap()));
        assert_eq!(marked.len(), MOST);
        assert!(marked.iter().any(|(e, _)| *e == Entity::from_raw_u32(9).unwrap()), "the locked ship stays marked");
        assert!(nearest(Vec3::ZERO, [at(1, 4001.0)].into_iter(), None).is_empty(), "nothing past 4 km");
    }

    #[test]
    fn the_lock_ring_fills_with_the_lock_and_is_whole_once_locked() {
        assert_eq!(lit(0.0), 0);
        assert_eq!(lit(0.5), TICKS / 2);
        assert_eq!(lit(0.999), TICKS - 1, "not whole until it is locked");
        assert_eq!(lit(1.0), TICKS);
        assert!((0..=100).map(|i| lit(i as f32 / 100.0)).collect::<Vec<_>>().windows(2).all(|w| w[0] <= w[1]), "it only ever fills");
    }

    #[test]
    fn each_faction_has_its_base_colour_and_the_raiders_their_own() {
        let bases = Bases::load();
        let regime = bases.base.iter().find(|b| b.faction == "regime").unwrap().color;
        assert_eq!(faction_color(Faction::Regime, &bases), Color::srgb(regime[0], regime[1], regime[2]));
        assert_eq!(faction_color(Faction::Raiders, &bases), RAIDERS);
    }
}
