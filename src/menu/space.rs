// The pause menu's space screens (comic redesign piece 4): STARMAP (the worlds around the star,
// their bases, where you are), SHIP (each ship's state and engine tune), CONTRACTS (the courier
// job you carry) and STANDING (where you stand with each faction, and what each level gives).
// They read live state and draw nothing when the level has none. The Yard's PARTS rack draws its
// rows and the Kestrel's refit card from here too.

use bevy::ecs::system::SystemParam;
use bevy::math::DVec3;

use super::*;
use super::draw::LEFT;
use crate::comic::{body_text, caption, display_text, panel, segment_bar, stat_bar, ComicTheme};
use crate::solar::base::Bases;
use crate::solar::combat::Faction;
use crate::solar::orbit::STAR;
use crate::solar::salvage::{self, Part, Refit, KESTREL};
use crate::solar::standing::{self, Level};
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
    tuning: Option<Res<'w, Tuning>>,
    parked: Query<'w, 's, &'static Ship, Without<crate::solar::ship::Autopilot>>,
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
        Panel::Standing => standings(p, t, space, save),
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

/// A Ship screen row for module slot `slot`: what is fitted there, and what it does and costs.
pub(super) fn fit_row(slot: usize, space: &Space, save: Option<&Save>) -> (String, String) {
    let blank = Save::default();
    let save = save.unwrap_or(&blank);
    match (salvage::fitted(save).get(slot), &space.tuning) {
        (Some(m), Some(tuning)) => (m.name().to_uppercase(), format!("{}; {}", m.effect(&tuning.ship_combat), m.cost(&tuning.ship_combat).to_lowercase())),
        (Some(m), None) => (m.name().to_uppercase(), String::new()),
        (None, _) if salvage::owned(save).is_empty() => ("EMPTY".into(), "No modules yet: wrecks drop them now and then".into()),
        (None, _) => ("EMPTY".into(), "Left or right to fit one you own".into()),
    }
}

/// The Kestrel's refit on the Ship screen: each part's level and what it gives, then every
/// module you own, what it does and what it costs, and whether it is fitted.
fn kestrel_card(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space, save: Option<&Save>) {
    let Some(tuning) = &space.tuning else { return };
    let sc = tuning.ship_combat.clone();
    let blank = Save::default();
    let save = save.unwrap_or(&blank).clone();
    let t2 = t.clone();
    p.spawn(Node { width: Val::Px(400.0), ..default() }).with_children(|w| {
        panel(w, t, t.paper, 1.0, move |c| {
            c.spawn(display_text("KESTREL REFIT", 30.0, t2.ink, &t2));
            c.spawn(body_text(format!("{} scrap to spend at the Yard's parts rack", save.scrap), 14.0, t2.muted, false, &t2));
            for (i, part) in Part::ALL.into_iter().enumerate() {
                let level = save.ship_parts[i].min(3);
                c.spawn(Node { justify_content: JustifyContent::SpaceBetween, margin: UiRect::top(Val::Px(4.0)), ..default() }).with_children(|row| {
                    row.spawn(body_text(part.name().to_uppercase(), 15.0, t2.ink, true, &t2));
                    row.spawn(body_text(format!("MK{level}"), 15.0, if level > 0 { t2.red } else { t2.muted }, true, &t2));
                });
                segment_bar(c, &t2, level as f32, 3.0, 3);
                c.spawn(body_text(format!("{} a level", part.gives(&sc)), 13.0, t2.muted, false, &t2));
            }
            c.spawn((display_text("MODULES", 22.0, t2.ink, &t2), Node { margin: UiRect::top(Val::Px(10.0)), ..default() }));
            let fitted = salvage::fitted(&save);
            let owned = salvage::owned(&save);
            if owned.is_empty() {
                c.spawn(body_text(format!("None yet. A wreck drops its hull's own module {:.0}% of the time.", sc.module_chance * 100.0), 14.0, t2.muted, false, &t2));
            }
            for m in owned {
                let on = fitted.contains(&m);
                c.spawn(Node { justify_content: JustifyContent::SpaceBetween, margin: UiRect::top(Val::Px(2.0)), ..default() }).with_children(|row| {
                    row.spawn(body_text(m.name().to_uppercase(), 15.0, t2.ink, true, &t2));
                    row.spawn(body_text(if on { "FITTED" } else { "IN THE HOLD" }, 14.0, if on { t2.red } else { t2.muted }, true, &t2));
                });
                c.spawn(body_text(format!("+ {}", m.effect(&sc)), 13.0, t2.ink, false, &t2));
                c.spawn(body_text(format!("- {}", m.cost(&sc)), 13.0, t2.muted, false, &t2));
            }
        });
    });
}

fn ships(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space, save: Option<&Save>) {
    let (Some(specs), Some(solar)) = (&space.ships, &space.solar) else { return };
    let level = save.map_or(0, |s| s.ship_level);
    let world = solar.anchor_body().name.to_uppercase();
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT + 460.0), right: Val::Px(LEFT), top: Val::Px(120.0), flex_wrap: FlexWrap::Wrap, column_gap: Val::Px(18.0), row_gap: Val::Px(18.0), align_items: AlignItems::FlexStart, ..default() }).with_children(|grid| {
        kestrel_card(grid, t, space, save);
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
    let jobs: Vec<String> = match (save, &space.bases) {
        (Some(s), Some(bases)) => s.contracts.iter().map(|c| crate::solar::board::job_line(c, bases).to_uppercase()).collect(),
        _ => Vec::new(),
    };
    let line = if jobs.is_empty() { "No jobs. Every base has a job board inside its door.".to_string() } else { jobs.join("\n") };
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT + 380.0), top: Val::Px(130.0), width: Val::Px(520.0), flex_direction: FlexDirection::Column, row_gap: Val::Px(22.0), align_items: AlignItems::FlexStart, ..default() }).with_children(|col| {
        caption(col, t, &line);
        let (t2, done, banked, day) = (t.clone(), save.map_or(0, |s| s.contracts_done), save.map_or(0, |s| s.banked), save.map_or(0, |s| s.day));
        panel(col, t, t.paper, 1.0, move |c| {
            c.spawn(display_text("COURIER LOG", 26.0, t2.ink, &t2));
            c.spawn(body_text(format!("Parcels delivered  {done}"), 17.0, t2.ink, true, &t2));
            c.spawn(body_text(format!("Banked  {}", money(banked)), 17.0, t2.ink, true, &t2));
            c.spawn(body_text(format!("Day  {}", day + 1), 17.0, t2.ink, true, &t2));
        });
    });
}

/// The job board's heading: the base's name.
pub(super) fn board_title(base: &str, space: &Space) -> String {
    space.bases.as_ref().map_or(base.to_uppercase(), |b| crate::solar::board::name_of(b, base).to_uppercase())
}

/// What a job asks, for a board row: its label, its pay, and a line of detail.
fn job_text(c: &crate::solar::board::Contract, space: &Space, save: &Save) -> (String, String, String) {
    use crate::solar::board::{name_of, Job};
    let name = |id: &str| space.bases.as_ref().map_or(id.to_string(), |b| name_of(b, id).to_string());
    let pay = format!("${}", c.pay);
    match &c.job {
        Job::Courier { to } => {
            let body = space.bases.as_ref().and_then(|b| b.base.iter().find(|x| x.id == *to)).map(|b| b.body.clone()).unwrap_or_default();
            let world = space.solar.as_ref().map_or(body.clone(), |s| s.bodies.get(&body).name.clone());
            let danger = space.bases.as_ref().zip(space.tuning.as_ref()).is_some_and(|(b, t)| {
                let f = crate::solar::board::faction_of(b, to);
                crate::solar::standing::moves(f) && crate::solar::standing::hostile(save, f, &t.ship_combat)
            });
            (format!("COURIER TO {}", name(to).to_uppercase()), pay, format!("A parcel for its door on {world}.{}", if danger { " Danger pay: its patrols shoot on sight." } else { "" }))
        }
        Job::Cull { need, got } if *got > 0 => (format!("CULL {got}/{need} RAIDERS"), pay, "Raiders your ship shoots down. Bounties pay too.".to_string()),
        Job::Cull { need, .. } => (format!("CULL {need} RAIDERS"), pay, "Raiders your ship shoots down. Bounties pay too.".to_string()),
        Job::Supply { need } => (format!("SUPPLY {need} SCRAP"), pay, format!("Bring it to the board at {}.", name(&c.from))),
    }
}

/// Offer `i` on base `base`'s board.
pub(super) fn offer_row(i: usize, base: &str, space: &Space, save: Option<&Save>) -> (String, String, String) {
    let blank = Save::default();
    let save = save.unwrap_or(&blank);
    match save.boards.get(base).and_then(|b| b.get(i)) {
        Some(c) => {
            let (label, pay, note) = job_text(c, space, save);
            (label, pay, format!("{note} Due by the end of tomorrow."))
        }
        None => ("-".to_string(), String::new(), "Nothing more here today.".to_string()),
    }
}

/// Your job `i`, seen from base `base`'s board.
pub(super) fn job_row(i: usize, base: &str, space: &Space, save: Option<&Save>) -> (String, String, String) {
    use crate::solar::board::Job;
    let blank = Save::default();
    let save = save.unwrap_or(&blank);
    match save.contracts.get(i) {
        Some(c) => {
            let (label, pay, note) = job_text(c, space, save);
            let due = match c.due {
                Some(d) if d <= save.day => " Due today.",
                Some(_) => " Due tomorrow.",
                None => "",
            };
            let label = match c.job {
                Job::Supply { need } if c.from == base && save.scrap >= need => format!("{label}  HAND IN"),
                _ => label,
            };
            (label, pay, format!("{note}{due}"))
        }
        None => ("-".to_string(), String::new(), "A free hand for another job.".to_string()),
    }
}

/// A parts rack row for part `i` at a base of `faction`: its label and level, how far up its three
/// levels it is, and what a level gives with the next one's price.
pub(super) fn part_row(i: usize, faction: Faction, space: &Space, save: Option<&Save>) -> ((String, String), f32, String) {
    let part = Part::ALL[i];
    let blank = Save::default();
    let save = save.unwrap_or(&blank);
    let level = save.ship_parts[i].min(3);
    let Some(tuning) = &space.tuning else { return ((part.name().to_uppercase(), format!("MK{level}")), level as f32 / 3.0, String::new()) };
    let t = &tuning.ship_combat;
    let next = match salvage::price(save, part, faction, t) {
        Some(cost) => format!("Mk{} for {cost} scrap{}", level + 1, standing::price_note(faction, save, t)),
        None => "fully fitted".to_string(),
    };
    ((part.name().to_uppercase(), format!("MK{level}")), level as f32 / 3.0, format!("{} a level  ·  {next}", part.gives(t)))
}

/// What the Kestrel flies with, its parts and modules counted: a card at `left` px from the
/// screen's left edge, beside the parts rack's rows.
pub(super) fn refit_card(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space, save: Option<&Save>, left: f32) {
    let (Some(tuning), Some(ships)) = (&space.tuning, &space.ships) else { return };
    let Some(spec) = ships.ship.iter().find(|s| s.id == KESTREL) else { return };
    let sc = tuning.ship_combat.clone();
    let blank = Save::default();
    let r = Refit::of(save.unwrap_or(&blank), &sc);
    let pct = |k: f32| format!("{:+}%", ((k - 1.0) * 100.0).round() as i32);
    let lines = [
        ("HULL", format!("{:.0}", r.max_hull(spec.hull)), format!("{:.0}", spec.hull)),
        ("SHIELD", format!("{:.0}", r.max_shield(spec.shield)), format!("{:.0}", spec.shield)),
        ("SHIELD REGEN", pct(r.regen), "+0%".to_string()),
        ("GUN HEAT A SHOT", pct(r.heat), "+0%".to_string()),
        ("GUN COOLING", pct(r.cool), "+0%".to_string()),
        ("MISSILES", format!("{}", r.missiles(&sc)), format!("{}", sc.missiles)),
        ("MISSILE RELOAD", format!("{:.1} S", r.reload(&sc)), format!("{:.1} S", sc.missile_reload)),
    ];
    let t2 = t.clone();
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(left), top: Val::Px(150.0), width: Val::Px(360.0), ..default() }).with_children(|col| {
        panel(col, t, t.paper, 1.0, move |c| {
            c.spawn(display_text("THE KESTREL", 28.0, t2.ink, &t2));
            c.spawn(body_text("With its parts and modules; stock in grey", 14.0, t2.muted, false, &t2));
            for (label, now, stock) in lines {
                c.spawn(Node { justify_content: JustifyContent::SpaceBetween, column_gap: Val::Px(16.0), ..default() }).with_children(|row| {
                    row.spawn(body_text(label, 16.0, t2.ink, true, &t2));
                    row.spawn(Node { column_gap: Val::Px(10.0), ..default() }).with_children(|v| {
                        v.spawn(body_text(stock.clone(), 16.0, t2.muted, false, &t2));
                        v.spawn(body_text(now.clone(), 16.0, if now != stock { t2.red } else { t2.ink }, true, &t2));
                    });
                });
            }
        });
    });
}

/// Where on a bar from -100 to 100 standing `v` sits, 0 to 100%.
fn along(v: i32) -> f32 {
    (v - standing::MIN) as f32 / (standing::MAX - standing::MIN) as f32 * 100.0
}

fn standings(p: &mut ChildSpawnerCommands, t: &ComicTheme, space: &Space, save: Option<&Save>) {
    let (Some(tuning), Some(bases)) = (&space.tuning, &space.bases) else { return };
    let sc = tuning.ship_combat.clone();
    let blank = Save::default();
    let save = save.unwrap_or(&blank);
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT + 380.0), right: Val::Px(LEFT), top: Val::Px(120.0), column_gap: Val::Px(28.0), align_items: AlignItems::FlexStart, ..default() }).with_children(|cols| {
        cols.spawn(Node { width: Val::Px(500.0), flex_direction: FlexDirection::Column, row_gap: Val::Px(16.0), ..default() }).with_children(|col| {
            for faction in standing::FACTIONS.into_iter().chain([Faction::Deserters]) {
                let v = standing::get(save, faction, &sc);
                let level = Level::of(v, &sc);
                let own = !standing::moves(faction);
                let color = crate::solar::contacts::faction_color(faction, bases);
                let word = if own { "OWN SIDE".to_string() } else { level.word().to_uppercase() };
                let gives = if own { "Fixed: the Roost is home, and its prices are its own".to_string() } else { level.gives(&sc) };
                let (t2, sc2) = (t.clone(), sc.clone());
                panel(col, t, t.paper, 0.0, move |c| {
                    c.spawn(Node { justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, column_gap: Val::Px(12.0), ..default() }).with_children(|row| {
                        row.spawn(Node { align_items: AlignItems::Center, column_gap: Val::Px(10.0), ..default() }).with_children(|name| {
                            name.spawn((Node { width: Val::Px(14.0), height: Val::Px(14.0), border: UiRect::all(Val::Px(3.0)), ..default() }, BackgroundColor(color), BorderColor::all(t2.ink), UiTransform::from_rotation(Rot2::degrees(45.0))));
                            name.spawn(display_text(faction.name().to_uppercase(), 28.0, t2.ink, &t2));
                        });
                        row.spawn(display_text(format!("{v:+}"), 28.0, if v < 0 { t2.red } else { t2.ink }, &t2));
                    });
                    // The bar from -100 to 100: filled from the middle to where you stand, with ink
                    // ticks where it starts to change something.
                    c.spawn((Node { height: Val::Px(16.0), margin: UiRect::vertical(Val::Px(6.0)), border: UiRect::all(Val::Px(2.0)), ..default() }, BackgroundColor(t2.paper), BorderColor::all(t2.ink))).with_children(|bar| {
                        let (a, b) = (along(v.min(0)), along(v.max(0)));
                        bar.spawn((Node { position_type: PositionType::Absolute, left: Val::Percent(a), width: Val::Percent(b - a), top: Val::Px(0.0), bottom: Val::Px(0.0), ..default() }, BackgroundColor(color)));
                        for mark in [sc2.standing_hunted, sc2.standing_wary, 0, sc2.standing_friendly] {
                            let w = if mark == 0 { 3.0 } else { 2.0 };
                            bar.spawn((Node { position_type: PositionType::Absolute, left: Val::Percent(along(mark)), margin: UiRect::left(Val::Px(-w / 2.0)), width: Val::Px(w), top: Val::Px(0.0), bottom: Val::Px(0.0), ..default() }, BackgroundColor(t2.ink)));
                        }
                    });
                    c.spawn(body_text(word, 16.0, if v < 0 { t2.red } else { t2.ink }, true, &t2));
                    c.spawn(body_text(gives, 15.0, t2.ink, false, &t2));
                    if let Some(note) = standing::note(faction) {
                        c.spawn(body_text(note, 15.0, t2.muted, true, &t2));
                    }
                });
            }
        });
        let (t2, sc2) = (t.clone(), sc.clone());
        cols.spawn(Node { width: Val::Px(380.0), ..default() }).with_children(|col| {
            panel(col, t, t.yellow, 1.0, move |c| {
                c.spawn(display_text("WHAT IT GETS YOU", 26.0, t2.ink, &t2));
                for level in Level::ALL {
                    c.spawn((Node { flex_direction: FlexDirection::Column, margin: UiRect::top(Val::Px(8.0)), ..default() }, children![
                        body_text(format!("{}  ({})", level.word().to_uppercase(), level.range(&sc2)), 16.0, t2.ink, true, &t2),
                        body_text(level.gives(&sc2), 15.0, t2.ink, false, &t2),
                    ]));
                }
                c.spawn((Node { margin: UiRect::top(Val::Px(12.0)), ..default() }, children![body_text(
                    format!(
                        "A parcel to their base {:+}. A raider shot down {:+} with each. One of their ships shot down {:+}, and {:+} with their rivals. Your first hit on one in a fight {:+}. Below where it started it creeps back {} a day.",
                        sc2.standing_delivery, sc2.standing_raider_kill, sc2.standing_kill, sc2.standing_rival_kill, sc2.standing_hit, sc2.standing_recovery
                    ),
                    14.0,
                    t2.muted,
                    false,
                    &t2,
                )]));
            });
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

    #[test]
    fn the_standing_bar_runs_from_minus_a_hundred_to_a_hundred() {
        assert_eq!((along(-100), along(0), along(100)), (0.0, 50.0, 100.0));
    }
}
