//! Comic widgets in look A, as plain spawners like `menu::text` and `hud::plate`. Each takes the
//! parent's child spawner and the theme, and returns the entity it spawned. The pure helpers at
//! the top hold the maths the HUD and quartermaster feed them, so odd inputs clamp rather than
//! drawing negative or overflowing bars.

use bevy::prelude::*;

use super::theme::{body_text, display_text, ComicTheme};

/// Most pips a row draws; the rest show as "+N".
pub const MAX_PIPS: u32 = 30;

fn unit(v: f32) -> f32 {
    if v.is_nan() { 0.0 } else { v.clamp(0.0, 1.0) }
}

/// Splits a stat bar into (ink, gain, loss) widths in 0..=1: ink up to the lower of the two
/// values, then blue gain up to `now` or red loss up to `base`.
pub fn bar_spans(base: f32, now: f32) -> (f32, f32, f32) {
    let (base, now) = (unit(base), unit(now));
    let ink = base.min(now);
    (ink, now - ink, base - ink)
}

/// Segments to fill for `value` out of `max`: rounded down, but at least one while there is any
/// value left, so 1 health never reads as dead.
pub fn filled_segments(value: f32, max: f32, segments: usize) -> usize {
    if !(max > 0.0) || !(value > 0.0) {
        return 0;
    }
    let share = (value / max).min(1.0);
    ((share * segments as f32).floor() as usize).clamp(1, segments)
}

/// (filled, empty, overflow) pips for a magazine: at most `MAX_PIPS` drawn, the rest counted.
pub fn pips(loaded: u32, mag: u32) -> (u32, u32, u32) {
    let shown = mag.min(MAX_PIPS);
    let filled = loaded.min(shown);
    (filled, shown - filled, mag - shown)
}

/// Banked money as the HUD shows it: "¢ 2,450".
pub fn money(c: u32) -> String {
    let digits = c.to_string();
    let mut out = String::new();
    for (i, ch) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    format!("¢ {out}")
}

fn hard_shadow(theme: &ComicTheme) -> BoxShadow {
    BoxShadow(vec![ShadowStyle { color: theme.ink, x_offset: Val::Px(theme.shadow_px), y_offset: Val::Px(theme.shadow_px), spread_radius: Val::ZERO, blur_radius: Val::ZERO }])
}

/// A box with an ink border, a hard ink shadow and a tilt. `content` spawns what goes inside (a
/// `halftone_layer` first, if the panel wants dots).
pub fn panel(p: &mut ChildSpawnerCommands, theme: &ComicTheme, fill: Color, tilt_deg: f32, content: impl FnOnce(&mut ChildSpawnerCommands)) -> Entity {
    p.spawn((
        Node { border: UiRect::all(Val::Px(theme.ink_px)), padding: UiRect::axes(Val::Px(12.0), Val::Px(6.0)), flex_direction: FlexDirection::Column, row_gap: Val::Px(6.0), ..default() },
        BackgroundColor(fill),
        BorderColor::all(theme.ink),
        hard_shadow(theme),
        UiTransform::from_rotation(Rot2::degrees(tilt_deg)),
    ))
    .with_children(content)
    .id()
}

/// The yellow "MEANWHILE…" box: objectives, warnings, issue titles.
pub fn caption(p: &mut ChildSpawnerCommands, theme: &ComicTheme, text: &str) -> Entity {
    let t = theme.clone();
    let text = text.to_string();
    panel(p, theme, theme.yellow, -2.0, move |c| {
        c.spawn(body_text(text, 20.0, t.ink, true, &t));
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tail {
    Left,
    Down,
}

/// A white speech bubble with an ink tail pointing at what it talks about.
pub fn bubble(p: &mut ChildSpawnerCommands, theme: &ComicTheme, text: &str, tail: Tail) -> Entity {
    let (left, top) = match tail {
        Tail::Left => (Val::Px(-18.0), Val::Percent(50.0)),
        Tail::Down => (Val::Px(32.0), Val::Percent(100.0)),
    };
    p.spawn((
        Node { max_width: Val::Px(300.0), border: UiRect::all(Val::Px(theme.ink_px)), padding: UiRect::axes(Val::Px(16.0), Val::Px(12.0)), border_radius: BorderRadius::all(Val::Px(24.0)), ..default() },
        BackgroundColor(Color::WHITE),
        BorderColor::all(theme.ink),
    ))
    .with_children(|b| {
        b.spawn((
            Node { position_type: PositionType::Absolute, left, top, width: Val::Px(20.0), height: Val::Px(20.0), margin: UiRect::top(Val::Px(-10.0)), ..default() },
            BackgroundColor(theme.ink),
            UiTransform::from_rotation(Rot2::degrees(45.0)),
        ));
        b.spawn(body_text(text, 19.0, theme.ink, false, theme));
    })
    .id()
}

fn bar_part(p: &mut ChildSpawnerCommands, share: f32, color: Color) {
    p.spawn((Node { width: Val::Percent(share * 100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(color)));
}

/// Label, value and bar; the bar shows the change from `base` (what you own) to `now` (what you
/// are trying on) as a blue gain or red loss.
pub fn stat_bar(p: &mut ChildSpawnerCommands, theme: &ComicTheme, label: &str, base: f32, now: f32) -> Entity {
    let (ink, gain, loss) = bar_spans(base, now);
    let delta = ((gain - loss) * 100.0).round() as i32;
    let (value, color) = match delta {
        0 => (format!("{}", ((ink + gain) * 100.0).round() as i32), theme.ink),
        d if d > 0 => (format!("+{d}"), theme.blue),
        d => (format!("−{}", -d), theme.red),
    };
    p.spawn(Node { flex_direction: FlexDirection::Column, row_gap: Val::Px(2.0), ..default() })
        .with_children(|r| {
            r.spawn(Node { justify_content: JustifyContent::SpaceBetween, ..default() }).with_children(|row| {
                row.spawn(body_text(label, 15.0, theme.ink, true, theme));
                row.spawn(body_text(value, 15.0, color, true, theme));
            });
            r.spawn((Node { height: Val::Px(12.0), border: UiRect::all(Val::Px(2.0)), ..default() }, BorderColor::all(theme.ink))).with_children(|bar| {
                bar_part(bar, ink, theme.ink);
                bar_part(bar, gain, theme.blue);
                bar_part(bar, loss, theme.red);
            });
        })
        .id()
}

/// The health bar: `segments` ink-outlined blocks, red while full.
pub fn segment_bar(p: &mut ChildSpawnerCommands, theme: &ComicTheme, value: f32, max: f32, segments: usize) -> Entity {
    let filled = filled_segments(value, max, segments);
    p.spawn(Node { column_gap: Val::Px(4.0), ..default() })
        .with_children(|r| {
            for i in 0..segments {
                r.spawn((
                    Node { flex_grow: 1.0, height: Val::Px(16.0), border: UiRect::all(Val::Px(2.0)), ..default() },
                    BackgroundColor(if i < filled { theme.red } else { theme.paper }),
                    BorderColor::all(theme.ink),
                ));
            }
        })
        .id()
}

/// Ammo dots: filled yellow for loaded rounds, rings for empty ones, "+N" past `MAX_PIPS`.
pub fn pip_row(p: &mut ChildSpawnerCommands, theme: &ComicTheme, loaded: u32, mag: u32) -> Entity {
    let (filled, empty, overflow) = pips(loaded, mag);
    p.spawn(Node { column_gap: Val::Px(4.0), align_items: AlignItems::Center, flex_wrap: FlexWrap::Wrap, ..default() })
        .with_children(|r| {
            for i in 0..filled + empty {
                let dot = Node { width: Val::Px(10.0), height: Val::Px(10.0), border: UiRect::all(Val::Px(2.0)), border_radius: BorderRadius::all(Val::Percent(50.0)), ..default() };
                let fill = if i < filled { theme.yellow } else { Color::NONE };
                r.spawn((dot, BackgroundColor(fill), BorderColor::all(theme.yellow)));
            }
            if overflow > 0 {
                r.spawn(body_text(format!("+{overflow}"), 15.0, theme.yellow, true, theme));
            }
        })
        .id()
}

/// The black strip along the bottom: pad glyphs in coloured circles (A green, B red, others
/// paper) with their labels, and banked money at the right.
pub fn hint_strip(p: &mut ChildSpawnerCommands, theme: &ComicTheme, hints: &[(&str, &str)], money_c: Option<u32>) -> Entity {
    p.spawn((
        Node { width: Val::Percent(100.0), height: Val::Px(56.0), padding: UiRect::horizontal(Val::Px(56.0)), column_gap: Val::Px(32.0), align_items: AlignItems::Center, ..default() },
        BackgroundColor(theme.ink),
    ))
    .with_children(|s| {
        for (glyph, label) in hints {
            let ring = match *glyph {
                "A" => theme.green,
                "B" => theme.red,
                _ => theme.paper,
            };
            s.spawn(Node { column_gap: Val::Px(8.0), align_items: AlignItems::Center, ..default() }).with_children(|h| {
                h.spawn((
                    Node { min_width: Val::Px(28.0), height: Val::Px(28.0), padding: UiRect::horizontal(Val::Px(6.0)), justify_content: JustifyContent::Center, align_items: AlignItems::Center, border_radius: BorderRadius::all(Val::Px(14.0)), ..default() },
                    BackgroundColor(ring),
                ))
                .with_children(|g| {
                    g.spawn(body_text(*glyph, 17.0, theme.ink, true, theme));
                });
                h.spawn(body_text(*label, 18.0, theme.paper, true, theme));
            });
        }
        if let Some(c) = money_c {
            s.spawn((Node { margin: UiRect::left(Val::Auto), ..default() },)).with_children(|m| {
                m.spawn(display_text(money(c), 24.0, theme.yellow, theme));
            });
        }
    })
    .id()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bar_spans_clamp_and_split() {
        let close = |a: (f32, f32, f32), b: (f32, f32, f32)| (a.0 - b.0).abs() < 1e-6 && (a.1 - b.1).abs() < 1e-6 && (a.2 - b.2).abs() < 1e-6;
        assert!(close(bar_spans(0.5, 0.7), (0.5, 0.2, 0.0)));
        assert!(close(bar_spans(0.7, 0.5), (0.5, 0.0, 0.2)));
        assert_eq!(bar_spans(-1.0, 2.0), (0.0, 1.0, 0.0));
        assert_eq!(bar_spans(f32::NAN, 0.4), (0.0, 0.4, 0.0));
    }

    #[test]
    fn segments_clamp() {
        assert_eq!(filled_segments(62.0, 100.0, 10), 6);
        assert_eq!(filled_segments(150.0, 100.0, 10), 10);
        assert_eq!(filled_segments(-5.0, 100.0, 10), 0);
        assert_eq!(filled_segments(1.0, 100.0, 10), 1);
        assert_eq!(filled_segments(50.0, 0.0, 10), 0);
        assert_eq!(filled_segments(f32::NAN, 100.0, 10), 0);
    }

    #[test]
    fn pips_cap_at_thirty() {
        assert_eq!(pips(4, 6), (4, 2, 0));
        assert_eq!(pips(0, 0), (0, 0, 0));
        assert_eq!(pips(45, 60), (30, 0, 30));
        assert_eq!(pips(9, 6), (6, 0, 0));
    }

    #[test]
    fn money_has_separators() {
        assert_eq!(money(2450), "¢ 2,450");
        assert_eq!(money(0), "¢ 0");
        assert_eq!(money(1_500_000), "¢ 1,500,000");
    }

    #[test]
    fn every_widget_spawns() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        let theme = ComicTheme::default();
        let root = app.world_mut().spawn(Node::default()).id();
        let mut panel_id = None;
        app.world_mut().commands().entity(root).with_children(|p| {
            panel_id = Some(panel(p, &theme, theme.paper, -2.0, |_| {}));
            caption(p, &theme, "MEANWHILE…");
            bubble(p, &theme, "Drop back in at Haven.", Tail::Left);
            stat_bar(p, &theme, "CONTROL", 0.52, 0.70);
            segment_bar(p, &theme, 62.0, 100.0, 10);
            pip_row(p, &theme, 4, 6);
            hint_strip(p, &theme, &[("A", "SELECT"), ("B", "BACK")], Some(2450));
        });
        app.world_mut().flush();
        assert_eq!(app.world().get::<Children>(root).map(|c| c.len()), Some(7));
        let panel_id = panel_id.unwrap();
        let w = app.world();
        assert!(w.get::<BoxShadow>(panel_id).is_some());
        assert!(w.get::<BorderColor>(panel_id).is_some());
        assert!(w.get::<UiTransform>(panel_id).is_some());
    }
}
