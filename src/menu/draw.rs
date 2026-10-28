// ----------------------------------------------------------------------------------------- ui
//
// The menus in the comic look (`crate::comic`, look A): a tilted paper slab down the left with a
// red halftone, a red title, rows as ink lettering with the highlighted one in a yellow box, a
// speech bubble saying what the highlighted main-menu row does, and the ink hint strip along the
// bottom with banked money. Rebuilt from scratch whenever the menu state changes.

use bevy::prelude::*;

use super::*;
use crate::comic::{body_text, bubble, display_text, halftone_layer, hint_strip, panel, stat_bar, ComicTheme, Halftone, Tail};

const LEFT: f32 = 72.0;

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
    }
}

/// The hint strip for a panel: (pad glyph, keyboard key, what it does).
pub(super) fn hints(panel: Panel, screen: Screen) -> &'static [(&'static str, &'static str, &'static str)] {
    match panel {
        Panel::Main if screen == Screen::Paused => &[("A", "ENTER", "SELECT"), ("B", "ESC", "RESUME")],
        Panel::Main => &[("A", "ENTER", "SELECT"), ("UP DN", "W S", "MOVE")],
        Panel::Settings => &[("L R", "A D", "ADJUST"), ("A", "ENTER", "TOGGLE"), ("B", "ESC", "BACK")],
        Panel::Quartermaster => &[("LB RB", "Q E", "WEAPON"), ("L R", "A D", "PART / TUNE"), ("A", "ENTER", "BUY"), ("B", "ESC", "BACK")],
        Panel::Wardrobe => &[("UP DN", "W S", "SLOT"), ("L R", "A D", "CHANGE"), ("B", "ESC", "BACK")],
        Panel::Controls => &[("B", "ESC", "BACK")],
        Panel::Maps => &[("A", "ENTER", "PLAY"), ("B", "ESC", "BACK")],
    }
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
) {
    let wardrobe_changed = closet.wardrobe.as_ref().is_some_and(|w| w.is_changed());
    let gun_changed = menu.panel == Panel::Quartermaster && (arsenal.is_changed() || save.as_ref().is_some_and(|s| s.is_changed()));
    if !(menu.is_changed() || screen.is_changed() || settings.is_changed() || loadout.is_changed() || gun_changed || wardrobe_changed) {
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
    let width = match menu.panel {
        Panel::Main => 360.0,
        Panel::Wardrobe => 620.0,
        _ => 560.0,
    };
    let dots = halftones.map(|mut h| halftone_layer(&mut h, t.paper, t.red.with_alpha(0.16), 10.0, 2.0));

    let mut root = commands.spawn((MenuRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), overflow: Overflow::clip(), ..default() }, ZIndex(10)));
    root.with_children(|p| {
        // The paper slab, taller than the screen and tilted so its right edge slants.
        p.spawn((
            Node { position_type: PositionType::Absolute, left: Val::Px(-80.0), top: Val::Percent(-15.0), width: Val::Px(LEFT + width + 140.0), height: Val::Percent(130.0), border: UiRect::right(Val::Px(8.0)), overflow: Overflow::clip(), ..default() },
            BackgroundColor(t.paper),
            BorderColor::all(t.ink),
            UiTransform::from_rotation(Rot2::degrees(3.0)),
        ))
        .with_children(|slab| {
            if let Some(dots) = dots {
                slab.spawn(dots);
            }
        });

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
                Panel::Wardrobe => ("RUST REGIME".to_string(), "WARDROBE"),
            };
            h.spawn((display_text(big, 60.0, t.red, &t), TextShadow { offset: Vec2::splat(4.0), color: t.ink }, UiTransform::from_rotation(Rot2::degrees(-2.0))));
            h.spawn((body_text(small, 17.0, t.ink, true, &t), Node { margin: UiRect::top(Val::Px(4.0)), ..default() }));
        });

        // Rows.
        let top = if menu.panel == Panel::Main && screen == Screen::Title { 250.0 } else { 150.0 };
        p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(LEFT), top: Val::Px(top), bottom: Val::Px(64.0), width: Val::Px(width), flex_direction: FlexDirection::Column, row_gap: Val::Px(2.0), overflow: Overflow::clip_y(), ..default() }).with_children(|list| {
            if menu.panel == Panel::Wardrobe {
                let preset = save.as_ref().map_or(0, |s| s.preset);
                list.spawn(Node { display: Display::Grid, grid_template_columns: RepeatedGridTrack::px(4, 146.0), row_gap: Val::Px(10.0), column_gap: Val::Px(8.0), padding: UiRect::all(Val::Px(6.0)), ..default() }).with_children(|grid| {
                    let mut index = 0;
                    for row in &rows {
                        if let Row::Preset | Row::Look(_) = row {
                            tile(grid, &t, *row, index, index == menu.cursor, outfit.as_ref(), closet.characters.as_deref(), preset);
                            index += 1;
                        }
                    }
                });
                list.spawn(Node { height: Val::Px(10.0), ..default() });
                let mut index = selectable(&rows).filter(|r| matches!(r, Row::Preset | Row::Look(_))).count();
                for row in &rows {
                    if let Row::Action(label, _) = row {
                        action_row(list, &t, label, index, menu.cursor == index, 26.0);
                        index += 1;
                    }
                }
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
                        action_row(list, &t, label, index, index == menu.cursor, if big { 44.0 } else { 26.0 });
                        index += 1;
                    }
                    Row::Field(i) => {
                        let f = fields().nth(i).unwrap();
                        let (value, fill) = field_value(f, &settings);
                        let label = if f.restart { format!("{} *", f.label) } else { f.label.to_string() };
                        value_row(list, &t, &label, &value, fill, None, index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Weapon => {
                        let value = match (quartermaster::owns_weapon(save.as_deref(), kind), quartermaster::price(kind)) {
                            (false, Some(cost)) => format!("{}  {}", kind.name(), crate::comic::widgets::money(cost)),
                            _ => format!("{}  OWNED", kind.name()),
                        };
                        let note = (!quartermaster::owns_weapon(save.as_deref(), kind)).then_some("ENTER / A buys it");
                        value_row(list, &t, "WEAPON", &value, None, note, index, index == menu.cursor, true);
                        list.spawn(Node { height: Val::Px(10.0), ..default() });
                        index += 1;
                    }
                    Row::Slot(slot) => {
                        let at = loadout.part(kind, slot);
                        let part = &PARTS[slot][at];
                        let owned = quartermaster::owns_part(save.as_deref(), slot, at);
                        let value = if owned { part.name.to_string() } else { format!("{}  {}", part.name, crate::comic::widgets::money(quartermaster::PART_PRICES[slot][at])) };
                        let note = if owned { part.desc.to_string() } else { format!("{}.  ENTER / A buys it", part.desc) };
                        value_row(list, &t, SLOTS[slot], &value, None, Some(&note), index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Tune(slot) => {
                        let v = loadout.tuning(kind, slot);
                        let (l, r) = TUNES[slot];
                        value_row(list, &t, &format!("  TUNE  {l} / {r}"), &format!("{v:+}"), Some((v + TUNE_MAX) as f32 / (2 * TUNE_MAX) as f32), None, index, index == menu.cursor, true);
                        index += 1;
                    }
                    Row::Map(i) => {
                        let m = &MAPS[i];
                        value_row(list, &t, m.name, if i == current_map() { "LOADED" } else { "" }, None, Some(m.desc), index, index == menu.cursor, false);
                        index += 1;
                    }
                    Row::Preset | Row::Look(_) => {}
                }
            }
            if menu.panel == Panel::Quartermaster && !menu.note.is_empty() {
                list.spawn((body_text(menu.note.clone(), 17.0, t.red, true, &t), Node { margin: UiRect::top(Val::Px(10.0)), ..default() }));
            }
            if menu.panel == Panel::Settings {
                list.spawn((body_text("* takes effect after a restart.  Saved to settings.toml.", 14.0, t.muted, false, &t), Node { margin: UiRect::top(Val::Px(4.0)), ..default() }));
            }
            if menu.panel == Panel::Controls {
                list.spawn((body_text(controls_sheet(), 16.0, t.ink, false, &t), Node { margin: UiRect::vertical(Val::Px(8.0)), ..default() }));
            }
        });

        // What the highlighted main-menu row does, in a bubble beside it.
        if menu.panel == Panel::Main {
            if let Some(Row::Action(_, action)) = selectable(&rows).nth(menu.cursor) {
                let row_h = 64.0;
                p.spawn(abs(Some(LEFT + 330.0), None, Some(top + menu.cursor as f32 * row_h - 6.0), None)).with_children(|b| {
                    bubble(b, &t, blurb(action), Tail::Left);
                });
            }
        }

        // The gun's stat bars, right: owned setup (base) against what's fitted now.
        if let (Panel::Quartermaster, Some(base), Some(fitted)) = (menu.panel, &base, &fitted) {
            let name = kind.name();
            let base_stats = gunsmith::stats(base);
            let fitted_stats = gunsmith::stats(fitted);
            p.spawn(Node { width: Val::Px(320.0), ..abs(None, Some(LEFT), Some(140.0), None) }).with_children(|c| {
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

        // The hint strip along the bottom, with the bank on the main menu and at the counter.
        let money = matches!(menu.panel, Panel::Main | Panel::Quartermaster).then_some(banked);
        let labels: Vec<(String, String)> = hints(menu.panel, screen).iter().map(|(pad, key, what)| (pad.to_string(), format!("{what}  {key}"))).collect();
        let pairs: Vec<(&str, &str)> = labels.iter().map(|(a, b)| (a.as_str(), b.as_str())).collect();
        p.spawn(Node { position_type: PositionType::Absolute, left: Val::Px(0.0), right: Val::Px(0.0), bottom: Val::Px(0.0), ..default() }).with_children(|b| {
            hint_strip(b, &t, &pairs, money);
        });
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

    #[test]
    fn every_panel_has_hints_and_a_way_back() {
        for panel in [Panel::Main, Panel::Maps, Panel::Settings, Panel::Controls, Panel::Quartermaster, Panel::Wardrobe] {
            let h = hints(panel, Screen::Paused);
            assert!(!h.is_empty(), "{panel:?}");
            assert!(h.iter().all(|(pad, key, what)| !pad.is_empty() && !key.is_empty() && !what.is_empty()), "{panel:?}");
            assert!(h.iter().any(|(pad, ..)| *pad == "B"), "{panel:?} shows how to go back");
        }
    }
}
