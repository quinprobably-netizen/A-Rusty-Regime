//! Waypoints: a coloured diamond with a name and a distance for each faction base and for your
//! parked ship, over the world and clamped to the screen edge when it is off-screen or behind
//! you, so you can find them from anywhere in the system. A base on the world you are on is
//! marked at the building; a base on another world is marked at that world's centre, which is
//! where it is. A post you have found on the world you are on (`post`) gets a smaller one.
//! Markers hide when you are standing at them and under the menus, with the HUD.

use bevy::prelude::*;
use bevy::window::PrimaryWindow;

use super::base::{Base, Bases};
use super::post::{Post, Posts};
use super::ship::Ship;
use super::Solar;
use crate::camera::PlayerCamera;
use crate::hud::HudRoot;
use crate::surface::Origin;

/// Closer than this to a waypoint it hides: you are there.
const ARRIVED: f32 = 30.0;
/// How far inside the screen edge a clamped marker sits, pixels: clear of the compass above and
/// the plates below.
pub(super) const MARGIN: Vec2 = Vec2::new(36.0, 105.0);
/// Past this fraction of the screen width a label goes to the left of its diamond.
const FLIP_AT: f32 = 0.7;
/// How high over a base the marker floats, metres.
const HOVER: f32 = 14.0;
const SIZE: f32 = 14.0;
/// A post's marker: smaller, and lower over it.
const POST_SIZE: f32 = 10.0;
const POST_HOVER: f32 = 9.0;

pub fn build(app: &mut App) {
    app.init_resource::<crate::comic::ComicTheme>().add_systems(Startup, spawn_markers).add_systems(Update, (post_pins, update_markers).chain());
}

/// What a marker points at.
#[derive(Component, Clone, Debug)]
pub enum Target {
    /// Index into `Bases`.
    Base(usize),
    /// The player's own ship, spec 0.
    Ship,
    /// A post you have found, standing on the anchor world.
    Post(Entity),
}

/// The node every marker hangs off.
#[derive(Resource)]
struct MarkerRoot(Entity);

/// A marker's pieces: the diamond, and the label with its side.
#[derive(Component)]
struct Diamond;
#[derive(Component)]
struct Label;

/// Where `local` (camera space, -Z forward) lands on a screen of `size` pixels for a camera
/// whose vertical half-angle has tangent `tan_half`: the point itself when it is in front and
/// inside `margin` (x, y) of the edges, otherwise the point on that rectangle toward it, so a marker
/// behind you sits on the side it is on. Returns the position and whether it is really on screen.
pub fn project(local: Vec3, tan_half: f32, size: Vec2, margin: Vec2) -> (Vec2, bool) {
    let half = size / 2.0 - margin;
    let centre = size / 2.0;
    let dir = if local.z < -1e-3 {
        let ndc = Vec2::new(local.x / (-local.z * tan_half * size.x / size.y), local.y / (-local.z * tan_half));
        let p = Vec2::new(ndc.x * size.x / 2.0, -ndc.y * size.y / 2.0);
        if p.x.abs() <= half.x && p.y.abs() <= half.y {
            return (centre + p, true);
        }
        p
    } else {
        // Behind (or edge-on): which side of the screen it is on, straight down when dead behind.
        let d = Vec2::new(local.x, -local.y);
        if d.length() < 1e-3 { Vec2::new(0.0, 1.0) } else { d }
    };
    let k = (half.x / dir.x.abs().max(1e-6)).min(half.y / dir.y.abs().max(1e-6));
    (centre + dir * k, false)
}

pub(super) fn km(m: f32) -> String {
    if m >= 10_000.0 { format!("{:.0} km", m / 1000.0) } else if m >= 1000.0 { format!("{:.1} km", m / 1000.0) } else { format!("{m:.0} m") }
}

/// One marker per base and one for the ship, hung off a root the menus can hide.
fn spawn_markers(mut commands: Commands, bases: Res<Bases>, theme: Res<crate::comic::ComicTheme>) {
    let root = commands.spawn((HudRoot, Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() })).id();
    let mut pins: Vec<(Target, Color, String)> = bases.base.iter().enumerate().map(|(i, b)| (Target::Base(i), Color::srgb(b.color[0], b.color[1], b.color[2]), b.name.to_uppercase())).collect();
    pins.push((Target::Ship, Color::WHITE, "KESTREL".into()));
    for (target, color, name) in pins {
        let pin = pin(&mut commands, &theme, target, color, name, SIZE, 16.0);
        commands.entity(root).add_child(pin);
    }
    commands.insert_resource(MarkerRoot(root));
}

/// A marker: a diamond `size` pixels across in `color`, and its label.
fn pin(commands: &mut Commands, theme: &crate::comic::ComicTheme, target: Target, color: Color, name: String, size: f32, text: f32) -> Entity {
    commands
        .spawn((target, Node { position_type: PositionType::Absolute, width: Val::Px(0.0), height: Val::Px(0.0), ..default() }, Visibility::Hidden))
        .with_children(|p| {
            p.spawn((
                Diamond,
                Node { position_type: PositionType::Absolute, left: Val::Px(-size / 2.0), top: Val::Px(-size / 2.0), width: Val::Px(size), height: Val::Px(size), border: UiRect::all(Val::Px(3.0)), ..default() },
                BackgroundColor(color),
                BorderColor::all(theme.ink),
                UiTransform::from_rotation(Rot2::degrees(45.0)),
            ));
            p.spawn((
                Label,
                // A black comic tag in the faction's colour.
                Node { position_type: PositionType::Absolute, left: Val::Px(size), top: Val::Px(-size), padding: UiRect::axes(Val::Px(6.0), Val::Px(1.0)), ..default() },
                crate::comic::body_text(name, text, color, true, theme),
                BackgroundColor(theme.ink),
                TextLayout::no_wrap(),
            ));
        })
        .id()
}

/// A marker for each found post standing on the anchor world; a post's marker goes with it.
fn post_pins(
    mut commands: Commands,
    root: Option<Res<MarkerRoot>>,
    theme: Res<crate::comic::ComicTheme>,
    posts: Res<Posts>,
    save: Option<Res<crate::save::Save>>,
    placed: Query<(Entity, &Post)>,
    pins: Query<(Entity, &Target)>,
) {
    let Some(root) = root else { return };
    let pinned: Vec<Entity> = pins.iter().filter_map(|(_, t)| if let Target::Post(e) = t { Some(*e) } else { None }).collect();
    for (pin, target) in &pins {
        if let Target::Post(e) = target
            && !placed.contains(*e)
        {
            commands.entity(pin).despawn();
        }
    }
    let found = |key: &str| save.as_ref().is_some_and(|s| s.posts_found.iter().any(|k| k == key));
    for (e, post) in &placed {
        if !pinned.contains(&e) && found(&post.key) {
            let spec = &posts.post[post.spec];
            let p = pin(&mut commands, &theme, Target::Post(e), Color::srgb(spec.color[0], spec.color[1], spec.color[2]), spec.name.to_uppercase(), POST_SIZE, 13.0);
            commands.entity(root.0).add_child(p);
        }
    }
}

/// Places every marker: projects its target through the player's camera, clamps it to the
/// screen, writes its name, world and distance, and hides it when you are there.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn update_markers(
    solar: Res<Solar>,
    origin: Res<Origin>,
    bases: Res<Bases>,
    save: Option<Res<crate::save::Save>>,
    camera: Query<(&Transform, &Projection), With<PlayerCamera>>,
    window: Query<&Window, With<PrimaryWindow>>,
    placed: Query<(&Transform, &Base)>,
    ships: Query<(&Transform, &Ship)>,
    posts: (Res<Posts>, Query<(&Transform, &Post)>),
    mut pins: Query<(&Target, &mut Node, &mut Visibility, &Children), (Without<Diamond>, Without<Label>)>,
    mut labels: Query<(&mut Node, &mut Text), With<Label>>,
) {
    let (Ok((cam, projection)), Ok(window)) = (camera.single(), window.single()) else { return };
    let Projection::Perspective(p) = projection else { return };
    let size = Vec2::new(window.width(), window.height());
    let tan_half = (p.fov / 2.0).tan();
    let inverse = cam.rotation.inverse();
    let flying = ships.iter().any(|(_, s)| s.pilot.is_some());
    for (target, mut node, mut visibility, children) in &mut pins {
        // Where it is (the camera's frame, origin-relative), what to call it and how far.
        let (at, world, distance) = match target {
            Target::Base(i) => {
                let spec = &bases.base[*i];
                if spec.body == solar.anchor {
                    let Some((tf, _)) = placed.iter().find(|(_, b)| b.spec == *i) else { continue };
                    (tf.translation + tf.rotation * Vec3::Y * HOVER, String::new(), tf.translation.distance(cam.translation))
                } else {
                    let (c, _) = solar.placement(&spec.body);
                    let at = origin.world(c);
                    (at, solar.bodies.get(&spec.body).name.clone(), (at.distance(cam.translation) - solar.bodies.get(&spec.body).radius).max(0.0))
                }
            }
            Target::Ship => {
                let Some((tf, _)) = ships.iter().find(|(_, s)| s.spec == 0 && s.pilot.is_none()) else {
                    visibility.set_if_neq(Visibility::Hidden);
                    continue;
                };
                (tf.translation + Vec3::Y * 6.0, String::new(), tf.translation.distance(cam.translation))
            }
            Target::Post(e) => {
                let Ok((tf, _)) = posts.1.get(*e) else { continue };
                (tf.translation + tf.rotation * Vec3::Y * POST_HOVER, String::new(), tf.translation.distance(cam.translation))
            }
        };
        let (point, _) = project(inverse * (at - cam.translation), tan_half, size, MARGIN);
        let shown = distance > ARRIVED && !(flying && matches!(target, Target::Ship));
        visibility.set_if_neq(if shown { Visibility::Inherited } else { Visibility::Hidden });
        node.left = Val::Px(point.x);
        node.top = Val::Px(point.y);
        for child in children.iter() {
            let Ok((mut label_node, mut text)) = labels.get_mut(child) else { continue };
            let name = match target {
                Target::Base(i) => bases.base[*i].name.to_uppercase(),
                Target::Ship => "KESTREL".to_string(),
                Target::Post(e) => posts.1.get(*e).map_or(String::new(), |(_, p)| posts.0.post[p.spec].name.to_uppercase()),
            };
            // The base a parcel is bound for says so.
            let parcel = match (target, save.as_ref().and_then(|s| s.contract.as_ref())) {
                (Target::Base(i), Some(c)) if bases.base[*i].id == c.to => format!("\nDELIVER HERE +${}", c.pay),
                _ => String::new(),
            };
            let line = if world.is_empty() { format!("{name}\n{}", km(distance)) } else { format!("{name}\n{} - {}", world.to_uppercase(), km(distance)) } + &parcel;
            if text.0 != line {
                text.0 = line;
            }
            let right_side = point.x > size.x * FLIP_AT;
            label_node.left = if right_side { Val::Auto } else { Val::Px(SIZE) };
            label_node.right = if right_side { Val::Px(SIZE) } else { Val::Auto };
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TAN: f32 = 0.7;
    const SCREEN: Vec2 = Vec2::new(1600.0, 900.0);

    #[test]
    fn straight_ahead_is_the_middle_of_the_screen() {
        let (p, on) = project(Vec3::new(0.0, 0.0, -50.0), TAN, SCREEN, MARGIN);
        assert!(on && p.distance(SCREEN / 2.0) < 0.5, "{p}");
    }

    #[test]
    fn off_to_the_right_and_up_sits_right_and_above_the_middle() {
        let (p, on) = project(Vec3::new(10.0, 10.0, -50.0), TAN, SCREEN, MARGIN);
        assert!(on && p.x > SCREEN.x / 2.0 && p.y < SCREEN.y / 2.0, "{p}");
    }

    #[test]
    fn off_screen_clamps_to_the_edge_on_its_side() {
        let (p, on) = project(Vec3::new(100.0, 0.0, -10.0), TAN, SCREEN, MARGIN);
        assert!(!on && (p.x - (SCREEN.x - MARGIN.x)).abs() < 0.5 && (p.y - SCREEN.y / 2.0).abs() < 0.5, "{p}");
        let (p, on) = project(Vec3::new(0.0, 100.0, -10.0), TAN, SCREEN, MARGIN);
        assert!(!on && (p.y - MARGIN.y).abs() < 0.5, "straight up, {p}");
    }

    #[test]
    fn behind_you_sits_on_the_side_it_is_on_and_never_in_the_middle() {
        let (p, on) = project(Vec3::new(-20.0, 0.0, 30.0), TAN, SCREEN, MARGIN);
        assert!(!on && (p.x - MARGIN.x).abs() < 0.5, "behind left, {p}");
        let (p, on) = project(Vec3::new(0.0, 0.0, 30.0), TAN, SCREEN, MARGIN);
        assert!(!on && (p.y - (SCREEN.y - MARGIN.y)).abs() < 0.5, "dead behind goes to the bottom, {p}");
        let (p, _) = project(Vec3::new(0.0, 0.0, 0.0), TAN, SCREEN, MARGIN);
        assert!(p.y > SCREEN.y / 2.0, "at the camera: {p}");
    }

    #[test]
    fn distances_read_in_metres_and_kilometres() {
        assert_eq!((km(420.0), km(1500.0), km(25_000.0)), ("420 m".to_string(), "1.5 km".to_string(), "25 km".to_string()));
    }
}
