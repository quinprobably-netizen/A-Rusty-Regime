//! Comic sound-effect words ("BLAM!", "HIT!") that pop up, overshoot, settle and fade. They run on
//! real time, so a pop fired just before a menu pauses the game still finishes.

use bevy::prelude::*;

use super::theme::{display_text, ComicTheme};

#[derive(Component, Debug, Clone, Copy)]
pub struct SfxPop {
    pub age: f32,
    pub life: f32,
    pub tilt: f32,
}

/// (scale, alpha) at `t` = age / life: scale 0.6 to 1.15 over the first 15%, back to 1.0 by 30%,
/// then held; alpha full until 70%, then linear to 0.
pub fn pop_curve(t: f32) -> (f32, f32) {
    let t = t.clamp(0.0, 1.0);
    let scale = if t < 0.15 {
        0.6 + 0.55 * (t / 0.15)
    } else if t < 0.3 {
        1.15 - 0.15 * ((t - 0.15) / 0.15)
    } else {
        1.0
    };
    let alpha = if t < 0.7 { 1.0 } else { 1.0 - (t - 0.7) / 0.3 };
    (scale, alpha.clamp(0.0, 1.0))
}

/// Spawns `word` in big yellow lettering with an ink drop shadow at screen px `at`.
pub fn sfx_pop(commands: &mut Commands, theme: &ComicTheme, word: &str, at: Vec2, tilt_deg: f32) -> Entity {
    let (scale, _) = pop_curve(0.0);
    commands
        .spawn((
            Node { position_type: PositionType::Absolute, left: Val::Px(at.x), top: Val::Px(at.y), ..default() },
            display_text(word, 54.0, theme.yellow, theme),
            TextShadow { offset: Vec2::splat(4.0), color: theme.ink },
            UiTransform { scale: Vec2::splat(scale), rotation: Rot2::degrees(tilt_deg), ..default() },
            GlobalZIndex(50),
            SfxPop { age: 0.0, life: 0.6, tilt: tilt_deg },
        ))
        .id()
}

pub(super) fn animate_pops(mut commands: Commands, time: Res<Time<Real>>, mut pops: Query<(Entity, &mut SfxPop, &mut UiTransform, &mut TextColor, &mut TextShadow)>) {
    for (entity, mut pop, mut transform, mut color, mut shadow) in &mut pops {
        pop.age += time.delta_secs();
        if pop.age >= pop.life {
            commands.entity(entity).despawn();
            continue;
        }
        let (scale, alpha) = pop_curve(pop.age / pop.life);
        transform.scale = Vec2::splat(scale);
        transform.rotation = Rot2::degrees(pop.tilt);
        color.0.set_alpha(alpha);
        shadow.color.set_alpha(alpha);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::time::TimeUpdateStrategy;
    use std::time::Duration;

    #[test]
    fn curve_overshoots_settles_and_fades() {
        assert!((pop_curve(0.0).0 - 0.6).abs() < 1e-5);
        assert!((pop_curve(0.15).0 - 1.15).abs() < 1e-5);
        assert_eq!(pop_curve(0.5), (1.0, 1.0));
        assert_eq!(pop_curve(1.0).1, 0.0);
    }

    #[test]
    fn pop_finishes_while_paused() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        app.insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_millis(50)));
        app.add_systems(Update, animate_pops);
        app.world_mut().resource_mut::<Time<Virtual>>().pause();
        let theme = ComicTheme::look_a();
        sfx_pop(&mut app.world_mut().commands(), &theme, "BLAM!", Vec2::new(100.0, 100.0), -12.0);
        app.world_mut().flush();
        for _ in 0..12 {
            app.update();
        }
        let shadow = app.world_mut().query::<&TextShadow>().single(app.world()).unwrap().color.alpha();
        assert!(shadow < 0.5, "the ink shadow fades with the word, {shadow}");
        for _ in 0..4 {
            app.update();
        }
        let left = app.world_mut().query::<&SfxPop>().iter(app.world()).count();
        assert_eq!(left, 0);
    }
}
