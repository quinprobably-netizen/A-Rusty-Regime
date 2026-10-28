// The pause menu's space screens (comic redesign piece 4): STARMAP (the worlds around the star,
// their bases, where you are), SHIP (each ship's state and engine tune) and CONTRACTS (the
// courier job you carry). They read live state and draw nothing when the level has none.

use bevy::ecs::system::SystemParam;
use bevy::math::DVec3;

use super::*;
use super::draw::LEFT;
use crate::comic::{body_text, caption, display_text, panel, segment_bar, stat_bar, ComicTheme};
use crate::solar::base::Bases;
use crate::solar::orbit::STAR;
use crate::solar::ship::{Ship, Ships};
use crate::solar::Solar;

/// The starmap disc's diameter and the radii its worlds sit between, px.
const DISC: f32 = 520.0;
pub(super) const MAP_MIN: f32 = 50.0;
pub(super) const MAP_MAX: f32 = 220.0;
/// How far a moon sits from its world on the map, px.
const MOON_RING: f32 = 30.0;

#[derive(SystemParam)]
pub(super) struct Space<'w, 's> {
    solar: Option<Res<'w, Solar>>,
    bases: Option<Res<'w, Bases>>,
    ships: Option<Res<'w, Ships>>,
    parked: Query<'w, 's, &'static Ship>,
}

/// A world's distance from the star on the map: a log scale, so moons-close and far worlds both fit.
pub(super) fn map_radius(distance: f64, nearest: f64, farthest: f64) -> f32 {
    if farthest <= nearest || distance <= 0.0 {
        return MAP_MIN;
    }
    let f = ((distance.max(nearest) / nearest).ln() / (farthest / nearest).ln()).clamp(0.0, 1.0) as f32;
    MAP_MIN + f * (MAP_MAX - MAP_MIN)
}

pub(super) fn draw(p: &mut ChildSpawnerCommands, t: &ComicTheme, panel_kind: Panel, space: &Space, save: Option<&Save>) {
    match panel_kind {
        Panel::Starmap => starmap(p, t, space),
        Panel::Ship => ships(p, t, space, save),
        Panel::Contracts => contracts(p, t, space, save),
        _ => {}
    }
}

fn starmap(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space) {
    let Some(solar) = &space.solar else { return };
    let bodies = &solar.bodies;
    let star_frame = |id: &str| bodies.convert(id, STAR, solar.epoch, DVec3::ZERO, DVec3::ZERO).0;
    // Worlds circle the star; moons circle a world.
    let planets: Vec<String> = bodies.ids().into_iter().filter(|id| bodies.get(id).orbit.as_ref().is_some_and(|o| o.parent == STAR)).collect();
    let distances: Vec<f64> = planets.iter().map(|id| star_frame(id).length()).collect();
    let nearest = distances.iter().copied().fold(f64::MAX, f64::min);
    let farthest = distances.iter().copied().fold(0.0, f64::max);
    let mut spots: Vec<(String, Vec2)> = vec![];
    for (id, d) in planets.iter().zip(&distances) {
        let at = star_frame(id);
        let r = map_radius(*d, nearest, farthest);
        spots.push((id.clone(), Vec2::new(at.x as f32, at.z as f32).normalize_or(Vec2::X) * r));
    }
    for id in bodies.ids() {
        let Some(orbit) = &bodies.get(&id).orbit else { continue };
        let Some(parent) = spots.iter().find(|(p, _)| *p == orbit.parent).map(|s| s.1) else { continue };
        let rel = star_frame(&id) - star_frame(&orbit.parent);
        spots.push((id.clone(), parent + Vec2::new(rel.x as f32, rel.z as f32).normalize_or(Vec2::Y) * MOON_RING));
    }

    p.spawn((
        Node { position_type: PositionType::Absolute, left: Val::Percent(50.0), top: Val::Px(110.0), margin: UiRect::left(Val::Px(-DISC / 2.0 + 120.0)), width: Val::Px(DISC), height: Val::Px(DISC), border: UiRect::all(Val::Px(t.ink_px)), border_radius: BorderRadius::all(Val::Percent(50.0)), ..default() },
        BackgroundColor(t.navy),
        BorderColor::all(t.ink),
        BoxShadow(vec![ShadowStyle { color: t.ink, x_offset: Val::Px(t.shadow_px), y_offset: Val::Px(t.shadow_px), spread_radius: Val::ZERO, blur_radius: Val::ZERO }]),
    ))
    .with_children(|disc| {
        let c = DISC / 2.0 - t.ink_px;
        let dot = |disc: &mut ChildSpawnerCommands, at: Vec2, size: f32, fill: Color| {
            disc.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(c + at.x - size / 2.0), top: Val::Px(c + at.y - size / 2.0), width: Val::Px(size), height: Val::Px(size), border: UiRect::all(Val::Px(3.0)), border_radius: BorderRadius::all(Val::Percent(50.0)), ..default() }, BackgroundColor(fill), BorderColor::all(t.ink)));
        };
        for (id, d) in planets.iter().zip(&distances) {
            let _ = id;
            let r = map_radius(*d, nearest, farthest);
            disc.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(c - r), top: Val::Px(c - r), width: Val::Px(2.0 * r), height: Val::Px(2.0 * r), border: UiRect::all(Val::Px(2.0)), border_radius: BorderRadius::all(Val::Percent(50.0)), ..default() }, BorderColor::all(t.paper.with_alpha(0.25))));
        }
        dot(disc, Vec2::ZERO, 34.0, t.yellow);
        for (id, at) in &spots {
            let body = bodies.get(id);
            let moon = body.orbit.as_ref().is_some_and(|o| o.parent != STAR);
            dot(disc, *at, if moon { 12.0 } else { 20.0 }, if *id == solar.anchor { t.red } else { t.paper });
            let x = at.x + 14.0;
            let tag = |disc: &mut ChildSpawnerCommands, x: f32, y: f32, text: String, fill: Color, ink: Color| {
                disc.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(c + x), top: Val::Px(c + y), padding: UiRect::axes(Val::Px(5.0), Val::Px(0.0)), ..default() }, BackgroundColor(fill)))
                    .with_child(body_text(text, 13.0, ink, true, t));
            };
            tag(disc, x, at.y - 10.0, body.name.to_uppercase(), t.ink, t.paper);
            if *id == solar.anchor {
                tag(disc, at.x - 46.0, at.y - 10.0, "YOU".into(), t.red, t.paper);
            }
            if let Some(bases) = &space.bases {
                for (n, base) in bases.base.iter().filter(|b| b.body == *id).enumerate() {
                    let [r, g, b] = base.color;
                    disc.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(c + x + n as f32 * 14.0), top: Val::Px(c + at.y + 12.0), width: Val::Px(9.0), height: Val::Px(9.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BackgroundColor(Color::srgb(r, g, b)), BorderColor::all(t.ink), UiTransform::from_rotation(Rot2::degrees(45.0))));
                }
            }
        }
    });
}

fn ships(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space, save: Option<&Save>) {
    let (Some(specs), Some(solar)) = (&space.ships, &space.solar) else { return };
    let level = save.map_or(0, |s| s.ship_level);
    let world = solar.anchor_body().name.to_uppercase();
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT + 380.0), right: Val::Px(LEFT), top: Val::Px(120.0), flex_wrap: FlexWrap::Wrap, column_gap: Val::Px(18.0), row_gap: Val::Px(18.0), ..default() }).with_children(|grid| {
        let mut list: Vec<&Ship> = space.parked.iter().collect();
        list.sort_by_key(|s| s.spec);
        for ship in list {
            let Some(spec) = specs.ship.get(ship.spec) else { continue };
            let (t2, name, heat) = (t.clone(), spec.name.to_uppercase(), ship.heat);
            let status = if ship.pilot.is_some() { "FLYING".to_string() } else { format!("PARKED ON {world}") };
            grid.spawn(Node { width: Val::Px(300.0), ..default() }).with_children(|w| {
                panel(w, t, if ship.pilot.is_some() { t.yellow } else { t.paper }, -1.0, move |c| {
                    c.spawn(display_text(name, 30.0, t2.ink, &t2));
                    c.spawn(body_text(status, 15.0, t2.red, true, &t2));
                    c.spawn(body_text(format!("ENGINE TUNE  MK{level}"), 15.0, t2.ink, true, &t2));
                    segment_bar(c, &t2, level as f32, 3.0, 3);
                    stat_bar(c, &t2, "HEAT", heat, heat);
                });
            });
        }
    });
}

fn contracts(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space, save: Option<&Save>) {
    let money = crate::comic::widgets::money;
    let job = save.and_then(|s| s.contract.as_ref());
    let line = match job {
        Some(c) => {
            let to = space.bases.as_ref().and_then(|b| b.base.iter().find(|b| b.id == c.to)).map_or(c.to.to_uppercase(), |b| b.name.to_uppercase());
            format!("DELIVER TO {to}  ·  PAYS {}", money(c.pay))
        }
        None => "No job. Contract desks at any base hand them out.".to_string(),
    };
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT + 380.0), top: Val::Px(130.0), width: Val::Px(520.0), flex_direction: FlexDirection::Column, row_gap: Val::Px(22.0), align_items: AlignItems::FlexStart, ..default() }).with_children(|col| {
        caption(col, t, &line);
        let (t2, done, banked) = (t.clone(), save.map_or(0, |s| s.contracts_done), save.map_or(0, |s| s.banked));
        panel(col, t, t.paper, 1.0, move |c| {
            c.spawn(display_text("COURIER LOG", 26.0, t2.ink, &t2));
            c.spawn(body_text(format!("Contracts done  {done}"), 17.0, t2.ink, true, &t2));
            c.spawn(body_text(format!("Banked  {}", money(banked)), 17.0, t2.ink, true, &t2));
        });
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn map_radius_is_monotonic_and_bounded() {
        let (n, f) = (2.0e6, 9.0e7);
        assert_eq!(map_radius(n, n, f), MAP_MIN);
        assert_eq!(map_radius(f, n, f), MAP_MAX);
        let mut last = MAP_MIN;
        for i in 1..20 {
            let r = map_radius(n + (f - n) * i as f64 / 20.0, n, f);
            assert!(r > last && r <= MAP_MAX);
            last = r;
        }
        assert_eq!(map_radius(5.0, 5.0, 5.0), MAP_MIN, "one world sits on the inner ring");
    }
}
