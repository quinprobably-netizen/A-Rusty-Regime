//! `RUST_REGIME_COMIC_DEMO=1`: one board over the game showing every widget, for checking the kit
//! by eye before the HUD and menus move onto it.

use bevy::prelude::*;

use super::halftone::{halftone_layer, Halftone};
use super::sfx::sfx_pop;
use super::theme::{display_text, ComicTheme};
use super::widgets::{bubble, caption, hint_strip, panel, pip_row, segment_bar, stat_bar, Tail};

pub(super) fn spawn(mut commands: Commands, theme: Res<ComicTheme>, mut halftones: ResMut<Assets<Halftone>>) {
    let t = theme.clone();
    let dots = halftone_layer(&mut halftones, t.paper, t.red.with_alpha(0.18), 10.0, 2.0);
    commands
        .spawn((Node { position_type: PositionType::Absolute, width: Val::Percent(100.0), height: Val::Percent(100.0), flex_direction: FlexDirection::Column, ..default() }, GlobalZIndex(40)))
        .with_children(|root| {
            root.spawn(Node { flex_grow: 1.0, padding: UiRect::all(Val::Px(56.0)), column_gap: Val::Px(48.0), ..default() }).with_children(|row| {
                row.spawn(Node { width: Val::Px(420.0), flex_direction: FlexDirection::Column, row_gap: Val::Px(24.0), ..default() }).with_children(|col| {
                    col.spawn(display_text("RUST REGIME", 96.0, t.red, &t));
                    caption(col, &t, "MEANWHILE… reach the Roost quartermaster and bank your haul.");
                    bubble(col, &t, "Drop back in at Haven. Your ship is fuelled and the Roost is open.", Tail::Left);
                });
                let t2 = t.clone();
                panel(row, &t, t.paper, 1.5, move |p| {
                    p.spawn(dots);
                    p.spawn(display_text("MA-14 STATS", 26.0, t2.ink, &t2));
                    stat_bar(p, &t2, "CONTROL", 0.52, 0.70);
                    stat_bar(p, &t2, "ACCURACY", 0.64, 0.58);
                    stat_bar(p, &t2, "RANGE", 0.60, 0.60);
                    segment_bar(p, &t2, 62.0, 100.0, 10);
                });
                let t3 = t.clone();
                panel(row, &t, t.ink, -1.5, move |p| {
                    p.spawn(display_text("WARDEN", 24.0, t3.yellow, &t3));
                    pip_row(p, &t3, 4, 6);
                    pip_row(p, &t3, 45, 60);
                });
            });
            hint_strip(root, &t, &[("A", "SELECT"), ("B", "BACK"), ("LB", "SLOT")], Some(2450));
        });
}

pub(super) fn blam(mut commands: Commands, time: Res<Time<Real>>, theme: Res<ComicTheme>, mut next: Local<f32>) {
    if time.elapsed_secs() >= *next {
        *next = time.elapsed_secs() + 2.0;
        sfx_pop(&mut commands, &theme, "BLAM!", Vec2::new(900.0, 420.0), -12.0);
    }
}
