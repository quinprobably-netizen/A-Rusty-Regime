// ----------------------------------------------------------------------------------------- ui
//
// The menus in the comic look (`crate::comic`, look A): a tilted paper slab down the left with a
// red halftone, a red title, rows as ink lettering with the highlighted one in a yellow box, a
// speech bubble saying what the highlighted main-menu row does, and the ink hint strip along the
// bottom with banked money. Rebuilt from scratch whenever the menu state changes.


use super::*;
use crate::comic::{body_text, bubble, display_text, halftone_layer, hint_strip, panel, stat_bar, ComicTheme, Halftone, Tail};

pub(super) const LEFT: f32 = 72.0;

#[derive(Component)]
pub(super) struct MenuRoot;

/// What a main-menu row does, said in the bubble beside it.
pub(super) fn blurb(action: Action) -> &'static str {
    match action {
        Action::Play => "Drop in at Haven. Your ship is fuelled and the Roost is open.",
        Action::Resume => "Back into it. Nothing moved while you were away.",
        Action::Maps => "Pick another world to drop onto.",
        Action::Wardrobe => "Heads, camo, kit and lights. Three presets to keep.",
        Action::Settings => "Sound, picture and how the controls feel.",
        Action::Controls => "Every binding, keyboard and pad.",
        Action::Quit => "Close the game. Your bank and kit are saved.",
        Action::Randomize => "Roll a random look.",
        Action::Back => "Back to the main menu.",
        Action::Starmap => "The worlds, their bases, and where you are.",
        Action::Ship => "Your ships: where they are and how they're tuned.",
        Action::Contracts => "The courier job you're carrying.",
        Action::Standing => "Where you stand with each faction, and what it gets you.",
    }
}

/// The hint strip for a panel: (pad glyph, keyboard key, what it does).
pub(super) fn hints(panel: Panel, screen: Screen) -> &'static [(&'static str, &'static str, &'static str)] {
    match panel {
        Panel::Main if screen == Screen::Paused => &[("A", "ENTER", "SELECT"), ("B", "ESC", "RESUME")],
        Panel::Main => &[("A", "ENTER", "SELECT"), ("UP DN", "W S", "MOVE")],
        Panel::Settings => &[("L R", "A D", "ADJUST"), ("A", "ENTER", "TOGGLE"), ("B", "ESC", "BACK")],
        Panel::Quartermaster => &[("LB RB", "Q E", "WEAPON"), ("L R", "A D", "PART / TUNE"), ("A", "ENTER", "BUY"), ("B", "ESC", "BACK")],
        Panel::Parts => &[("UP DN", "W S", "PART"), ("A", "ENTER", "BUY"), ("B", "ESC", "BACK")],
        Panel::Wardrobe => &[("UP DN", "W S", "SLOT"), ("L R", "A D", "CHANGE"), ("B", "ESC", "BACK")],
        Panel::Ship => &[("UP DN", "W S", "SLOT"), ("L R", "A D", "FIT MODULE"), ("B", "ESC", "BACK")],
        Panel::Controls | Panel::Starmap | Panel::Contracts | Panel::Standing => &[("B", "ESC", "BACK")],
        Panel::Maps => &[("A", "ENTER", "PLAY"), ("B", "ESC", "BACK")],
    }
}

/// Roughly how tall each kind of row draws in the list, px (with its gap and margins).
fn row_height(row: Row) -> f32 {
    match row {
        Row::Section(_) => 36.0,
        Row::Action(..) => 60.0,
        _ => 34.0,
    }
}

/// Where selectable row `cursor` starts and ends down the list, px.
fn row_span(rows: &[Row], cursor: usize) -> (f32, f32) {
    let mut y = 0.0;
    let mut index = 0;
    for &row in rows {
        let h = row_height(row);
        if !matches!(row, Row::Section(_)) {
            if index == cursor {
                return (y, y + h);
            }
            index += 1;
        }
        y += h;
    }
    (y, y)
}

/// How far the list scrolls so the highlighted row sits mid-box (0 while it fits from the top).
fn list_scroll(rows: &[Row], cursor: usize, visible: f32) -> f32 {
    let (top, bottom) = row_span(rows, cursor);
    (top - (visible - (bottom - top)) / 2.0).max(0.0)
}

/// The hint strip's (glyph, what) pairs: pad buttons or keys, whichever was touched last.
pub(super) fn hint_labels(panel: Panel, screen: Screen, pad: bool) -> Vec<(String, String)> {
    hints(panel, screen).iter().map(|(p, k, what)| ((if pad { *p } else { *k }).to_string(), what.to_string())).collect()
}

fn abs(left: Option<f32>, right: Option<f32>, top: Option<f32>, bottom: Option<f32>) -> Node {
    let v = |o: Option<f32>| o.map_or(Val::Auto, Val::Px);
    Node { position_type: PositionType::Absolute, left: v(left), right: v(right), top: v(top), bottom: v(bottom), flex_direction: FlexDirection::Column, ..default() }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn rebuild(
    mut commands: Commands,
    roots: Query<Entity, With<MenuRoot>>,
    menu: Res<Menu>,
    screen: Res<State<Screen>>,
    settings: Res<Settings>,
    loadout: Res<Loadout>,
    arsenal: Res<Arsenal>,
    tuning: Res<Tuning>,
    closet: Closet,
    save: Option<Res<Save>>,
    theme: Res<ComicTheme>,
    halftones: Option<ResMut<Assets<Halftone>>>,
    window: Option<Single<&Window>>,
    space: super::space::Space,
    actions: Option<Res<crate::controls::ActionState>>,
    mut was_pad: Local<Option<bool>>,
) {
    // The hints follow the device in hand, so switching between pad and keys redraws.
    let pad = actions.is_some_and(|a| a.pad_last);
    let device_changed = *was_pad != Some(pad);
    *was_pad = Some(pad);
    let wardrobe_changed = closet.wardrobe.as_ref().is_some_and(|w| w.is_changed());
    let gun_changed = menu.panel == Panel::Quartermaster && (arsenal.is_changed() || save.as_ref().is_some_and(|s| s.is_changed()));
    let salvage_changed = matches!(menu.panel, Panel::Parts | Panel::Ship) && save.as_ref().is_some_and(|s| s.is_changed());
    if !(device_changed || menu.is_changed() || screen.is_changed() || settings.is_changed() || loadout.is_changed() || gun_changed || salvage_changed || wardrobe_changed) {
        return;
    }
    for e in &roots {
        commands.entity(e).despawn();
    }
    let screen = *screen.get();
    if screen == Screen::Playing {
        return;
    }
    let t = theme.into_inner().clone();
    let kind = arsenal.kind();
    let rows = rows(menu.panel, screen, tuned(&loadout, kind), gunsmith::customizable(kind));
    let outfit = closet.outfit();
    let base = tuning.gun(kind).cloned();
    let fitted = base.as_ref().map(|g| loadout.gun(kind, g));
    let banked = save.as_ref().map_or(0, |s| s.banked);
    let scrap = save.as_ref().map_or(0, |s| s.scrap);
    let width = match menu.panel {
        Panel::Main => 360.0,
        Panel::Wardrobe => 620.0,
        Panel::Ship => 420.0,
        Panel::Starmap | Panel::Contracts | Panel::Standing => 300.0,
        _ => 560.0,
    };
    let mut halftones = halftones;
    let dots = halftones.as_mut().map(|h| halftone_layer(h, t.paper, t.red.with_alpha(0.16), 10.0, 2.0));
    // The paused list on the solar level runs to ten rows, so its lettering shrinks to fit.
    let (main_px, row_h) = if selectable(&rows).count() > 6 { (34.0, 50.0) } else { (44.0, 64.0) };
    let screen_px = window.map_or(Vec2::new(1280.0, 720.0), |w| w.size());
    // The bench and the wardrobe put the gun or the body in the middle, with no slab over them.
    let slab = !matches!(menu.panel, Panel::Quartermaster | Panel::Wardrobe);

    let mut root = commands.spawn((MenuRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), overflow: Overflow::clip(), ..default() }, ZIndex(10)));
    root.with_children(|p| {
        // The paper slab, taller than the screen and tilted so its right edge slants.
        if slab { p.spawn((
            Node { position_type: PositionType::Absolute, left: Val::Px(-80.0), top: Val::Percent(-15.0), width: Val::Px(LEFT + width + 140.0), height: Val::Percent(130.0), border: UiRect::right(Val::Px(8.0)), overflow: Overflow::clip(), ..default() },
            BackgroundColor(t.paper),
            BorderColor::all(t.ink),
            UiTransform::from_rotation(Rot2::degrees(3.0)),
        ))
        .with_children(|slab| {
            if let Some(dots) = dots {
                slab.spawn(dots);
            }
        }); }

        // Header.
        p.spawn(abs(Some(LEFT), None, Some(36.0), None)).with_children(|h| {
            let title_shadow = TextShadow { offset: Vec2::splat(6.0), color: t.ink };
            if menu.panel == Panel::Main && screen == Screen::Title {
                h.spawn((display_text("RUST REGIME", 104.0, t.red, &t), title_shadow, UiTransform::from_rotation(Rot2::degrees(-3.0))));
                h.spawn(Node { height: Val::Px(8.0), ..default() });
                let sub = t.clone();
                h.spawn(Node { align_self: AlignSelf::FlexStart, ..default() }).with_children(|c| {
                    panel(c, &t, t.yellow, -3.0, move |b| {
                        b.spawn(body_text("ISSUE #1  ·  THE HAVEN RUN", 18.0, sub.ink, true, &sub));
                    });
                });
                return;
            }
            let (small, big) = match menu.panel {
                Panel::Main => ("RUST REGIME".to_string(), "PAUSED"),
                Panel::Settings => ("RUST REGIME".to_string(), "SETTINGS"),
                Panel::Controls => ("RUST REGIME".to_string(), "CONTROLS"),
                Panel::Maps => ("RUST REGIME".to_string(), "MAPS"),
                Panel::Quartermaster => (format!("BANKED  {}", crate::comic::widgets::money(banked)), "THE ROOST · QUARTERMASTER"),
                Panel::Parts => (format!("SCRAP  {scrap}"), "THE YARD · PARTS RACK"),
                Panel::Wardrobe => ("RUST REGIME".to_string(), "WARDROBE"),
                Panel::Starmap => ("THE HAVEN SYSTEM".to_string(), "STARMAP"),
                Panel::Ship => ("THE HANGAR".to_string(), "SHIPS"),
                Panel::Contracts => ("COURIER WORK".to_string(), "CONTRACTS"),
                Panel::Standing => ("THE FACTIONS".to_string(), "STANDING"),
            };
            h.spawn((display_text(big, 60.0, t.red, &t), TextShadow { offset: Vec2::splat(4.0), color: t.ink }, UiTransform::from_rotation(Rot2::degrees(-2.0))));
            h.spawn((body_text(small, 17.0, t.ink, true, &t), Node { margin: UiRect::top(Val::Px(4.0)), ..default() }));
        });

        // Rows.
        let top = if menu.panel == Panel::Main && screen == Screen::Title { 250.0 } else { 150.0 };
        // Settings runs longer than the screen: the list scrolls to keep the highlight in view.
        let scroll = list_scroll(&rows, menu.cursor, screen_px.y - top - 64.0);
        p.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(LEFT), top: Val::Px(top), bottom: Val::Px(64.0), width: Val::Px(width), flex_direction: FlexDirection::Column, row_gap: Val::Px(2.0), overflow: Overflow::scroll_y(), ..default() }, ScrollPosition(Vec2::new(0.0, scroll)))).with_children(|list| {
            if matches!(menu.panel, Panel::Wardrobe | Panel::Quartermaster) {
                return;
            }
            let mut index = 0;
            for row in &rows {
                match *row {
                    Row::Section(name) => {
                        list.spawn((display_text(name, 20.0, t.red, &t), Node { margin: UiRect::top(Val::Px(10.0)), ..default() }));
                    }
                    Row::Action(label, _) => {
                        let big = menu.panel == Panel::Main;
                        if !big {
                            list.spawn(Node { height: Val::Px(6.0), ..default() });
                        }
                        action_row(list, &t, label, index, index == menu.cursor, if big { main_px } else { 26.0 });
                        index += 1;
                    }
                    Row::Field(i) => {
                        let f = fields().nth(i).unwrap();
                        let (value, fill) = field_value(f, &settings);
                        let label = if f.restart { format!("{} *", f.label) } else { f.label.to_string() };
                        value_row(list, &t, &label, &value, fill, None, index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Map(i) => {
                        let m = &MAPS[i];
                        value_row(list, &t, m.name, if i == current_map() { "LOADED" } else { "" }, None, Some(m.desc), index, index == menu.cursor, false);
                        index += 1;
                    }
                    Row::Part(i) => {
                        let (value, fill, note) = super::space::part_row(i, menu.rack, &space, save.as_deref());
                        value_row(list, &t, &value.0, &value.1, Some(fill), Some(&note), index, index == menu.cursor, false);
                        index += 1;
                    }
                    Row::Sell => {
                        let scrap = save.as_ref().map_or(0, |s| s.scrap);
                        let each = save.as_deref().map_or(tuning.economy.scrap_value, |s| crate::solar::standing::buys(tuning.economy.scrap_value, menu.rack, s, &tuning.ship_combat));
                        let note = format!("${each} a scrap, into the bank");
                        value_row(list, &t, &format!("SELL {scrap} SCRAP"), &format!("${}", scrap * each), None, Some(&note), index, index == menu.cursor, false);
                        index += 1;
                    }
                    Row::Fit(slot) => {
                        let (value, note) = super::space::fit_row(slot, &space, save.as_deref());
                        value_row(list, &t, &format!("SLOT {}", slot + 1), &value, None, Some(&note), index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Weapon | Row::Slot(_) | Row::Tune(_) | Row::Preset | Row::Look(_) => {}
                }
            }
            if menu.panel == Panel::Settings {
                list.spawn((body_text("* takes effect after a restart.  Saved to settings.toml.", 14.0, t.muted, false, &t), Node { margin: UiRect::top(Val::Px(4.0)), ..default() }));
            }
            if menu.panel == Panel::Controls {
                list.spawn((body_text(controls_sheet(), 16.0, t.ink, false, &t), Node { margin: UiRect::vertical(Val::Px(8.0)), ..default() }));
            }
            if menu.panel == Panel::Parts && !menu.note.is_empty() {
                list.spawn((body_text(menu.note.clone(), 18.0, t.red, true, &t), Node { margin: UiRect::top(Val::Px(10.0)), ..default() }));
            }
        });

        // What the highlighted main-menu row does, in a bubble beside it.
        if menu.panel == Panel::Main {
            if let Some(Row::Action(_, action)) = selectable(&rows).nth(menu.cursor) {
                p.spawn(abs(Some(LEFT + 330.0), None, Some(top + menu.cursor as f32 * row_h - 6.0), None)).with_children(|b| {
                    bubble(b, &t, blurb(action), Tail::Left);
                });
            }
        }

        if menu.panel == Panel::Quartermaster {
            bench(p, &t, &rows, menu.cursor, kind, &loadout, save.as_deref(), &menu.note, screen_px, &tuning.economy);
        }
        if menu.panel == Panel::Parts {
            super::space::refit_card(p, &t, &space, save.as_deref(), LEFT + 600.0);
        }
        if matches!(menu.panel, Panel::Starmap | Panel::Ship | Panel::Contracts | Panel::Standing) {
            super::space::draw(p, &t, menu.panel, &space, save.as_deref());
        }
        if menu.panel == Panel::Wardrobe {
            let preset = save.as_ref().map_or(0, |s| s.preset);
            spotlight(p, &t, &rows, menu.cursor, outfit.as_ref(), closet.characters.as_deref(), preset);
        }

        // The gun's stat bars, right: owned setup (base) against what's fitted now.
        if let (Panel::Quartermaster, Some(base), Some(fitted)) = (menu.panel, &base, &fitted) {
            let name = kind.name();
            let base_stats = gunsmith::stats(base);
            let fitted_stats = gunsmith::stats(fitted);
            p.spawn(Node { width: Val::Px(300.0), ..abs(None, Some(40.0), Some(36.0), None) }).with_children(|c| {
                let t2 = t.clone();
                panel(c, &t, t.paper, 1.5, move |s| {
                    s.spawn(display_text(format!("{name} STATS"), 26.0, t2.ink, &t2));
                    for ((label, b), (_, f)) in base_stats.into_iter().zip(fitted_stats) {
                        stat_bar(s, &t2, label, b, f);
                    }
                    s.spawn(body_text("blue: better with parts   red: worse", 14.0, t2.muted, false, &t2));
                });
            });
        }

        // The hint strip along the bottom, with the bank on the main menu and at the counter, and
        // your scrap on the main menu, at the parts rack and on the Ship screen.
        let money = matches!(menu.panel, Panel::Main | Panel::Quartermaster | Panel::Parts).then_some(banked);
        let scrap = matches!(menu.panel, Panel::Main | Panel::Parts | Panel::Ship).then_some(scrap);
        let labels = hint_labels(menu.panel, screen, pad);
        let pairs: Vec<(&str, &str)> = labels.iter().map(|(a, b)| (a.as_str(), b.as_str())).collect();
        p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(0.0), right: Val::Px(0.0), bottom: Val::Px(0.0), ..default() }).with_children(|b| {
            hint_strip(b, &t, &pairs, money, scrap);
        });
    });
}

/// Where wardrobe tile `n` sits in its grid, (column, row), filling down each column first.
pub(super) fn tile_cell(n: usize, rows: usize) -> (usize, usize) {
    (n / rows.max(1), n % rows.max(1))
}

/// Tiles in the wardrobe's left and right grids, left first and holding the odd one.
pub(super) fn wardrobe_columns(tiles: usize) -> (usize, usize) {
    (tiles.div_ceil(2), tiles / 2)
}

/// What a wardrobe tile changes, said in the bubble beside it.
pub(super) fn slot_blurb(row: Row) -> &'static str {
    use wardrobe::Slot;
    match row {
        Row::Look(i) => match wardrobe::SLOTS[i] {
            Slot::Character => "Who you are under the kit.",
            Slot::Head => "Borrow another character's head.",
            Slot::Primary => "The main cloth colour.",
            Slot::Secondary => "The second cloth colour.",
            Slot::Accent => "Trim, straps and patches.",
            Slot::Camo => "A printed pattern over the cloth.",
            Slot::Skin => "Skin tone.",
            Slot::Gloves => "Glove colour.",
            Slot::Boots => "Boot colour.",
            Slot::Webbing => "Belts, pouches and webbing.",
            Slot::Metal => "Buckles, plates and hardware.",
            Slot::Glow => "Kit lights, on or off, and their colour.",
            Slot::Glass => "The visor's tint.",
            Slot::Wear => "Fresh from the locker, or seen some runs.",
        },
        Row::Preset => "Three looks to keep. Changes save to this one.",
        _ => "",
    }
}

/// The wardrobe: the character in the middle of the dressing room, slot tiles in a grid
/// either side, a bubble on the selected one, and RANDOMISE and BACK at the bottom right.
#[allow(clippy::too_many_arguments)]
fn spotlight(p: &mut ChildSpawnerCommands, t: &ComicTheme, rows: &[Row], cursor: usize, outfit: Option<&OutfitDef>, characters: Option<&Characters>, preset: usize) {
    let tiles: Vec<Row> = selectable(rows).filter(|r| matches!(r, Row::Preset | Row::Look(_))).collect();
    let (left, _) = wardrobe_columns(tiles.len());
    let grid_rows = left.div_ceil(2);
    let grid = |right: bool| Node {
        position_type: PositionType::Absolute,
        left: if right { Val::Auto } else { Val::Px(LEFT - 40.0) },
        right: if right { Val::Px(LEFT - 40.0) } else { Val::Auto },
        top: Val::Px(150.0),
        display: Display::Grid,
        // Down each column first, so the D-pad walks the tiles top to bottom.
        grid_auto_flow: GridAutoFlow::Column,
        grid_template_rows: RepeatedGridTrack::px(grid_rows as u16, 66.0),
        grid_template_columns: RepeatedGridTrack::px(2, 150.0),
        row_gap: Val::Px(10.0),
        column_gap: Val::Px(8.0),
        ..default()
    };
    for (right, range) in [(false, 0..left), (true, left..tiles.len())] {
        p.spawn(grid(right)).with_children(|g| {
            for i in range {
                tile(g, t, tiles[i], i, i == cursor, outfit, characters, preset);
            }
        });
    }
    // The bubble beside the selected tile: right of the left grid, left of the right grid.
    if let Some(&row) = tiles.get(cursor) {
        let (right, n) = if cursor < left { (false, cursor) } else { (true, cursor - left) };
        let top = 150.0 + tile_cell(n, grid_rows).1 as f32 * 76.0;
        let node = if right { Node { width: Val::Px(240.0), ..abs(None, Some(LEFT - 40.0 + 316.0), Some(top), None) } } else { Node { width: Val::Px(240.0), ..abs(Some(LEFT - 40.0 + 316.0), None, Some(top), None) } };
        p.spawn(node).with_children(|b| {
            bubble(b, t, slot_blurb(row), if right { Tail::Right } else { Tail::Left });
        });
    }
    p.spawn(Node { align_items: AlignItems::FlexEnd, ..abs(None, Some(LEFT - 40.0), None, Some(70.0)) }).with_children(|list| {
        let mut index = tiles.len();
        for row in rows {
            if let Row::Action(label, _) = row {
                // On paper, so the ink lettering reads over the dark room.
                list.spawn((Node { margin: UiRect::top(Val::Px(4.0)), ..default() }, BackgroundColor(t.paper.with_alpha(0.85))))
                    .with_children(|b| action_row(b, t, label, index, cursor == index, 30.0));
                index += 1;
            }
        }
    });
}

/// Where each slot's callout sits on the bench, as a fraction of the screen, in `SLOTS` order.
pub(super) const CALLOUTS: [(f32, f32); 4] = [(0.50, 0.22), (0.36, 0.46), (0.80, 0.76), (0.84, 0.50)];
/// Where the showcased gun sits on screen, as a fraction: the leader lines end near it.
const GUN_AT: (f32, f32) = (0.56, 0.60);
const CALLOUT_W: f32 = 230.0;

/// The quartermaster's bench (The Division / Delta Force): the gun turning in the middle, a
/// callout per slot on an ink leader line, the weapon list down the left, and the selected slot's
/// parts as cards along the bottom.
#[allow(clippy::too_many_arguments)]
fn bench(p: &mut ChildSpawnerCommands, t: &ComicTheme, rows: &[Row], cursor: usize, kind: crate::weapon::WeaponKind, loadout: &Loadout, save: Option<&Save>, note: &str, screen: Vec2, e: &crate::tuning::Economy) {
    let money = crate::comic::widgets::money;
    let mut index_of = std::collections::HashMap::new();
    for (i, row) in selectable(rows).enumerate() {
        index_of.insert(format!("{row:?}"), i);
    }
    let at = |row: Row| index_of.get(&format!("{row:?}")).copied();
    let cursor_slot = match selectable(rows).nth(cursor) {
        Some(Row::Slot(s) | Row::Tune(s)) => Some(s),
        _ => None,
    };

    // Left: the picker, then every gun on sale with OWNED or its price.
    p.spawn(Node { width: Val::Px(300.0), row_gap: Val::Px(2.0), ..abs(Some(LEFT - 40.0), None, Some(150.0), None) }).with_children(|list| {
        if let Some(i) = at(Row::Weapon) {
            let note = (!quartermaster::owns_weapon(save, kind)).then_some("ENTER / A buys it");
            value_row(list, t, "WEAPON", kind.name(), None, note, i, i == cursor, true);
        }
        list.spawn(Node { height: Val::Px(8.0), ..default() });
        for w in crate::weapon::WEAPONS {
            let owned = quartermaster::owns_weapon(save, w);
            let Some(cost) = quartermaster::price(w, e).or(owned.then_some(0)) else { continue };
            let here = w == kind;
            list.spawn((Node { justify_content: JustifyContent::SpaceBetween, padding: UiRect::axes(Val::Px(10.0), Val::Px(1.0)), border: UiRect::all(Val::Px(if here { 2.0 } else { 0.0 })), ..default() }, BorderColor::all(t.ink), BackgroundColor(if here { t.yellow } else { t.paper.with_alpha(0.85) })))
                .with_children(|r| {
                    r.spawn(display_text(w.name(), 17.0, t.ink, t));
                    r.spawn(body_text(if owned { "OWNED".to_string() } else { money(cost) }, 15.0, if owned { t.muted } else { t.red }, true, t));
                });
        }
        if !note.is_empty() {
            list.spawn((body_text(note, 17.0, t.red, true, t), Node { margin: UiRect::top(Val::Px(10.0)), ..default() }));
        }
        list.spawn(Node { height: Val::Px(8.0), ..default() });
        for &row in rows {
            if let (Row::Action(label, _), Some(i)) = (row, at(row)) {
                // On paper, so the ink lettering reads over the dark room.
                list.spawn((Node { align_self: AlignSelf::FlexStart, ..default() }, BackgroundColor(t.paper.with_alpha(0.85))))
                    .with_children(|b| action_row(b, t, label, i, i == cursor, 26.0));
            }
        }
    });

    if !gunsmith::customizable(kind) {
        return;
    }
    // Leader lines first, so the callouts sit on top of their ends.
    let centre = Vec2::new(GUN_AT.0, GUN_AT.1) * screen;
    for &(x, y) in &CALLOUTS {
        let from = Vec2::new(x, y) * screen;
        let to = centre + (from - centre) * 0.22;
        let (mid, len) = ((from + to) * 0.5, from.distance(to));
        let angle = (to - from).to_angle();
        p.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(mid.x - len / 2.0), top: Val::Px(mid.y - 1.5), width: Val::Px(len), height: Val::Px(3.0), ..default() }, BackgroundColor(t.ink), UiTransform::from_rotation(Rot2::radians(angle))));
        p.spawn((Node { position_type: PositionType::Absolute, left: Val::Px(to.x - 5.0), top: Val::Px(to.y - 5.0), width: Val::Px(10.0), height: Val::Px(10.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BackgroundColor(t.yellow), BorderColor::all(t.ink), UiTransform::from_rotation(Rot2::degrees(45.0))));
    }
    for (slot, &(x, y)) in CALLOUTS.iter().enumerate() {
        let Some(i) = at(Row::Slot(slot)) else { continue };
        let fitted = loadout.part(kind, slot);
        let part = &PARTS[slot][fitted];
        let owned = quartermaster::owns_part(save, slot, fitted);
        let on = cursor_slot == Some(slot);
        let pos = Vec2::new(x, y) * screen;
        let mut card = p.spawn((
            Button,
            RowId(i),
            Node { position_type: PositionType::Absolute, left: Val::Px(pos.x - CALLOUT_W / 2.0), top: Val::Px(pos.y - 34.0), width: Val::Px(CALLOUT_W), flex_direction: FlexDirection::Column, padding: UiRect::axes(Val::Px(10.0), Val::Px(4.0)), border: UiRect::all(Val::Px(t.ink_px)), ..default() },
            BackgroundColor(if on { t.yellow } else { t.paper }),
            BorderColor::all(t.ink),
            BoxShadow(vec![ShadowStyle { color: t.ink, x_offset: Val::Px(t.shadow_px), y_offset: Val::Px(t.shadow_px), spread_radius: Val::ZERO, blur_radius: Val::ZERO }]),
        ));
        if on {
            card.insert(UiTransform::from_rotation(Rot2::degrees(-2.0)));
        }
        let t2 = t.clone();
        let tune = at(Row::Tune(slot)).map(|ti| (ti, loadout.tuning(kind, slot)));
        card.with_children(|c| {
            c.spawn(Node { justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, ..default() }).with_children(|r| {
                r.spawn(body_text(SLOTS[slot], 14.0, t2.muted, true, &t2));
                if !owned {
                    r.spawn((body_text("TRYING ON", 12.0, t2.paper, true, &t2), Node { padding: UiRect::axes(Val::Px(5.0), Val::Px(0.0)), ..default() }, BackgroundColor(t2.red)));
                }
            });
            c.spawn(Node { justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, column_gap: Val::Px(6.0), ..default() }).with_children(|r| {
                arrow(r, &t2, i, -1);
                r.spawn(display_text(part.name, 22.0, t2.ink, &t2));
                arrow(r, &t2, i, 1);
            });
            c.spawn(body_text(if owned { "OWNED".to_string() } else { money(e.attachments[slot][fitted]) }, 14.0, if owned { t2.muted } else { t2.red }, true, &t2));
            if let Some((ti, v)) = tune {
                let (l, r) = TUNES[slot];
                let fill = (v + TUNE_MAX) as f32 / (2 * TUNE_MAX) as f32;
                c.spawn((Button, RowId(ti), Node { flex_direction: FlexDirection::Column, margin: UiRect::top(Val::Px(4.0)), padding: UiRect::all(Val::Px(3.0)), border: UiRect::all(Val::Px(if ti == cursor { 2.0 } else { 0.0 })), ..default() }, BorderColor::all(t2.ink), BackgroundColor(if ti == cursor { t2.paper } else { Color::NONE })))
                    .with_children(|tr| {
                        tr.spawn(body_text(format!("TUNE  {l} / {r}  {v:+}"), 13.0, t2.ink, true, &t2));
                        tr.spawn(Node { align_items: AlignItems::Center, column_gap: Val::Px(6.0), ..default() }).with_children(|b| {
                            arrow(b, &t2, ti, -1);
                            b.spawn((Node { flex_grow: 1.0, height: Val::Px(12.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BorderColor::all(t2.ink), BackgroundColor(t2.paper)))
                                .with_child((Node { width: Val::Percent(fill * 100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(t2.red)));
                            arrow(b, &t2, ti, 1);
                        });
                    });
            }
        });
    }

    // The slot under the cursor: its three parts as cards along the bottom.
    let Some(slot) = cursor_slot else { return };
    let fitted = loadout.part(kind, slot);
    p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT - 40.0), bottom: Val::Px(70.0), column_gap: Val::Px(14.0), ..default() }).with_children(|row| {
        for (n, part) in PARTS[slot].iter().enumerate() {
            let owned = quartermaster::owns_part(save, slot, n);
            let t2 = t.clone();
            row.spawn(Node { width: Val::Px(220.0), ..default() }).with_children(|w| {
                panel(w, t, if n == fitted { t.yellow } else { t.paper }, if n == fitted { -1.5 } else { 0.0 }, move |c| {
                    c.spawn(display_text(part.name, 20.0, t2.ink, &t2));
                    c.spawn(body_text(if owned { "OWNED".to_string() } else { money(e.attachments[slot][n]) }, 14.0, if owned { t2.muted } else { t2.red }, true, &t2));
                    c.spawn(body_text(part.desc, 14.0, t2.ink, false, &t2));
                });
            });
        }
    });
}

fn action_row(p: &mut ChildSpawnerCommands, t: &ComicTheme, label: &str, index: usize, selected: bool, px: f32) {
    let mut row = p.spawn((
        Button,
        RowId(index),
        Node { align_self: AlignSelf::FlexStart, align_items: AlignItems::Center, column_gap: Val::Px(14.0), padding: UiRect::axes(Val::Px(18.0), Val::Px(2.0)), border: UiRect::all(Val::Px(if selected { t.ink_px + 1.0 } else { 0.0 })), margin: UiRect::vertical(Val::Px(if selected { 4.0 } else { 0.0 })), ..default() },
        BorderColor::all(t.ink),
        BackgroundColor(if selected { t.yellow } else { Color::NONE }),
    ));
    if selected {
        row.insert((BoxShadow(vec![ShadowStyle { color: t.ink, x_offset: Val::Px(6.0), y_offset: Val::Px(6.0), spread_radius: Val::ZERO, blur_radius: Val::ZERO }]), UiTransform::from_rotation(Rot2::degrees(-2.0))));
    }
    let t = t.clone();
    let label = label.to_string();
    row.with_children(|r| {
        if selected {
            r.spawn((Node { width: Val::Px(px * 0.36), height: Val::Px(px * 0.36), ..default() }, BackgroundColor(t.red), UiTransform::from_rotation(Rot2::degrees(45.0))));
        }
        r.spawn(display_text(label, px, t.ink, &t));
    });
}

/// A label on the left, `<` value `>` on the right, an optional bar and a note underneath.
/// `arrows` shows the < > steppers; a row that only launches something leaves them off.
#[allow(clippy::too_many_arguments)]
fn value_row(p: &mut ChildSpawnerCommands, t: &ComicTheme, label: &str, value: &str, fill: Option<f32>, note: Option<&str>, index: usize, selected: bool, arrows: bool) {
    p.spawn((
        Button,
        RowId(index),
        Node { flex_direction: FlexDirection::Column, padding: UiRect::axes(Val::Px(14.0), Val::Px(3.0)), border: UiRect::all(Val::Px(if selected { 3.0 } else { 0.0 })), ..default() },
        BorderColor::all(t.ink),
        BackgroundColor(if selected { t.yellow } else { Color::NONE }),
    ))
    .with_children(|row| {
        row.spawn(Node { flex_direction: FlexDirection::Row, justify_content: JustifyContent::SpaceBetween, align_items: AlignItems::Center, width: Val::Percent(100.0), ..default() }).with_children(|r| {
            r.spawn(body_text(label, 19.0, t.ink, true, t));
            r.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: Val::Px(10.0), ..default() }).with_children(|v| {
                if arrows {
                    arrow(v, t, index, -1);
                }
                if let Some(fill) = fill {
                    v.spawn((Node { width: Val::Px(130.0), height: Val::Px(12.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BorderColor::all(t.ink), BackgroundColor(t.paper)))
                        .with_child((Node { width: Val::Percent(fill.clamp(0.0, 1.0) * 100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(t.red)));
                    v.spawn((display_text(value, 20.0, t.ink, t), Node { width: Val::Px(52.0), justify_content: JustifyContent::FlexEnd, ..default() }, TextLayout { justify: Justify::Right, ..default() }));
                } else {
                    v.spawn((display_text(value, 20.0, if selected { t.red } else { t.ink }, t), Node { width: Val::Px(190.0), justify_content: JustifyContent::Center, ..default() }, TextLayout { justify: Justify::Center, ..default() }));
                }
                if arrows {
                    arrow(v, t, index, 1);
                }
            });
        });
        if let Some(note) = note {
            row.spawn(body_text(note, 14.0, t.muted, false, t));
        }
    });
}

fn arrow(p: &mut ChildSpawnerCommands, t: &ComicTheme, index: usize, dir: i32) {
    p.spawn((Button, Arrow(index, dir), Node { width: Val::Px(26.0), height: Val::Px(26.0), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() }, BackgroundColor(t.ink)))
        .with_child(display_text(if dir < 0 { "<" } else { ">" }, 18.0, t.paper, t));
}

/// A wardrobe tile: the preset in use, or one slot's value (with a swatch when it is a colour).
#[allow(clippy::too_many_arguments)]
fn tile(p: &mut ChildSpawnerCommands, t: &ComicTheme, row: Row, index: usize, selected: bool, outfit: Option<&OutfitDef>, characters: Option<&Characters>, preset: usize) {
    let (name, worn, swatch) = match row {
        Row::Preset => ("PRESET".to_string(), format!("{} / {}", preset + 1, wardrobe::PRESETS), None),
        Row::Look(i) => {
            let slot = wardrobe::SLOTS[i];
            let (worn, swatch) = match (outfit, characters) {
                (Some(o), Some(c)) => (slot.value(o, c), slot.swatch(o)),
                _ => ("none".into(), None),
            };
            (slot.label().to_string(), worn, swatch)
        }
        _ => return,
    };
    let mut tile = p.spawn((
        Button,
        RowId(index),
        Node { height: Val::Px(66.0), padding: UiRect::axes(Val::Px(10.0), Val::Px(6.0)), flex_direction: FlexDirection::Column, justify_content: JustifyContent::SpaceBetween, border: UiRect::all(Val::Px(3.0)), overflow: Overflow::clip(), ..default() },
        BorderColor::all(t.ink),
        BackgroundColor(if selected { t.yellow } else { t.paper }),
    ));
    if selected {
        tile.insert((BoxShadow(vec![ShadowStyle { color: t.ink, x_offset: Val::Px(4.0), y_offset: Val::Px(4.0), spread_radius: Val::ZERO, blur_radius: Val::ZERO }]), UiTransform::from_rotation(Rot2::degrees(-2.0))));
    }
    let t = t.clone();
    tile.with_children(|c| {
        c.spawn(body_text(name, 13.0, t.muted, true, &t));
        c.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: Val::Px(8.0), ..default() }).with_children(|r| {
            if let Some(col) = swatch {
                r.spawn((Node { width: Val::Px(18.0), height: Val::Px(18.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BackgroundColor(col), BorderColor::all(t.ink)));
            }
            r.spawn(display_text(worn, 20.0, t.ink, &t));
        });
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every selectable bench row, BACK included, is drawn as a clickable `RowId` in cursor order.
    #[test]
    fn the_bench_draws_every_row() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        let t = ComicTheme::look_a();
        let kind = crate::weapon::WeaponKind::Revolver;
        let rows = rows(Panel::Quartermaster, Screen::Paused, [true, false, false, false], gunsmith::customizable(kind));
        let root = app.world_mut().spawn(Node::default()).id();
        let loadout = Loadout::default();
        app.world_mut().commands().entity(root).with_children(|p| bench(p, &t, &rows, 0, kind, &loadout, None, "", Vec2::new(1280.0, 720.0), &crate::tuning::Economy::default()));
        app.world_mut().flush();
        let w = app.world_mut();
        let mut ids: Vec<usize> = w.query_filtered::<&RowId, With<Button>>().iter(w).map(|r| r.0).collect();
        ids.sort();
        assert_eq!(ids, (0..selectable(&rows).count()).collect::<Vec<_>>());
    }

    /// The long Settings list scrolls so the highlighted row is always inside the visible box.
    #[test]
    fn the_settings_list_scrolls_to_the_cursor() {
        let rows = rows(Panel::Settings, Screen::Paused, [false; 4], false);
        let n = selectable(&rows).count();
        let visible = 500.0;
        assert_eq!(list_scroll(&rows, 0, visible), 0.0);
        let mut last = 0.0;
        for cursor in 0..n {
            let s = list_scroll(&rows, cursor, visible);
            let (top, bottom) = row_span(&rows, cursor);
            assert!(s >= last && top >= s && bottom <= s + visible, "row {cursor}: {top}..{bottom} not in {s}..{}", s + visible);
            last = s;
        }
        assert!(last > 0.0, "the list is longer than the box");
    }

    #[test]
    fn wardrobe_columns_split_left_heavy() {
        assert_eq!(wardrobe_columns(15), (8, 7));
        assert_eq!(wardrobe_columns(14), (7, 7));
        assert_eq!(wardrobe_columns(0), (0, 0));
    }

    #[test]
    fn every_wardrobe_slot_has_a_blurb() {
        assert!(!slot_blurb(Row::Preset).is_empty());
        for i in 0..wardrobe::SLOTS.len() {
            assert!(!slot_blurb(Row::Look(i)).is_empty(), "{}", wardrobe::SLOTS[i].label());
        }
    }

    #[test]
    fn callouts_stay_on_screen_and_apart() {
        for (i, &(x, y)) in CALLOUTS.iter().enumerate() {
            assert!((0.1..=0.9).contains(&x) && (0.1..=0.9).contains(&y), "{}", SLOTS[i]);
            for &(x2, y2) in &CALLOUTS[i + 1..] {
                assert!(Vec2::new(x, y).distance(Vec2::new(x2, y2)) >= 0.2);
            }
        }
    }

    #[test]
    fn every_main_action_has_a_blurb() {
        for screen in [Screen::Title, Screen::Paused] {
            for row in selectable(&rows(Panel::Main, screen, [false; 4], false)) {
                if let Row::Action(name, action) = row {
                    assert!(!blurb(action).is_empty(), "{name}");
                }
            }
        }
    }

    /// D-pad down walks a wardrobe grid down its first column, then the next.
    #[test]
    fn wardrobe_tiles_run_down_each_column() {
        let cells: Vec<(usize, usize)> = (0..8).map(|n| tile_cell(n, 4)).collect();
        assert_eq!(cells, [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)]);
    }

    #[test]
    fn hints_name_the_pad_or_the_keys() {
        let pad = hint_labels(Panel::Settings, Screen::Paused, true);
        let keys = hint_labels(Panel::Settings, Screen::Paused, false);
        assert_eq!(pad[0], ("L R".to_string(), "ADJUST".to_string()));
        assert_eq!(keys[0], ("A D".to_string(), "ADJUST".to_string()));
        assert!(pad.iter().any(|(g, _)| g == "B") && keys.iter().any(|(g, _)| g == "ESC"));
    }

    #[test]
    fn every_panel_has_hints_and_a_way_back() {
        for panel in [Panel::Main, Panel::Maps, Panel::Settings, Panel::Controls, Panel::Quartermaster, Panel::Wardrobe, Panel::Starmap, Panel::Ship, Panel::Contracts, Panel::Standing] {
            let h = hints(panel, Screen::Paused);
            assert!(!h.is_empty(), "{panel:?}");
            assert!(h.iter().all(|(pad, key, what)| !pad.is_empty() && !key.is_empty() && !what.is_empty()), "{panel:?}");
            assert!(h.iter().any(|(pad, ..)| *pad == "B"), "{panel:?} shows how to go back");
        }
    }
}
