//! Picture-in-picture sights. While you aim through a magnifying scope a second camera renders the
//! magnified view into an image, and the scope's eyepiece (`scope.eye` on the weapon model, scaled by
//! the lens radius) shows it through `shaders/scope.wgsl`, which draws the reticle and darkens the
//! picture as the eye leaves the scope's axis. The red dot's window (`reddot.lens`) draws its dot at
//! infinity, so it stays on target while the gun sways. Each gun's `scope_mag` in `tuning.toml` sets
//! its fixed magnification; the main view zooms only to `ads_fov_scoped` around the scope.

use bevy::camera::visibility::VisibilitySystems;
use bevy::camera::{Exposure, RenderTarget};
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::gltf::GltfMaterialName;
use bevy::light::SimulationLightSystems;
use bevy::pbr::{AtmosphereSettings, DistanceFog};
use bevy::prelude::*;
use bevy::reflect::TypePath;
use bevy::render::render_resource::{AsBindGroup, ShaderType, TextureFormat};
use bevy::shader::ShaderRef;

use crate::camera::PlayerCamera;
use crate::controller::Player;
use crate::gunsmith::{Loadout, customizable};
use crate::tuning::Tuning;
use crate::vehicle::Driving;
use crate::viewmodel::{ViewModel, WeaponModel};
use crate::weapon::{Aim, Arsenal, WEAPONS, WeaponKind};

/// Side of the scope picture in pixels.
const RESOLUTION: u32 = 512;
/// The scope camera clips everything nearer than this: the gun, the arms, the player's own body.
const NEAR: f32 = 1.0;
/// The red dot's radius and its glow, in radians off the sight line.
const DOT: f32 = 0.004;

pub struct ScopePlugin;

impl Plugin for ScopePlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Scoped>()
            .add_plugins(MaterialPlugin::<LensMaterial>::default())
            .add_systems(Startup, spawn)
            .add_systems(Update, (scoped, activate).chain())
            .add_systems(Update, (fit_lenses, hide_modelled_dots))
            .add_systems(
                PostUpdate,
                (follow, match_view)
                    .after(TransformSystems::Propagate)
                    .before(VisibilitySystems::UpdateFrusta)
                    .before(SimulationLightSystems::UpdateDirectionalLightCascades),
            );
    }
}

/// The current weapon's fitted scope magnification, `None` when it has no magnifying optic on.
#[derive(Resource, Default, Clone, Copy, Debug, PartialEq)]
pub struct Scoped(pub Option<f32>);

/// The camera that renders the magnified picture.
#[derive(Component)]
pub struct ScopeCamera;

/// A sight picture on a weapon model's socket.
#[derive(Component)]
struct Lens {
    reticle: Reticle,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Reticle {
    MilDot = 1,
    Chevron = 2,
    RedDot = 3,
}

#[derive(Resource)]
struct ScopeImage(Handle<Image>);

#[derive(Asset, TypePath, AsBindGroup, Debug, Clone)]
pub struct LensMaterial {
    #[uniform(0)]
    params: LensParams,
    #[texture(1)]
    #[sampler(2)]
    image: Option<Handle<Image>>,
}

#[derive(ShaderType, Debug, Clone, Copy, Default)]
struct LensParams {
    /// Reticle kind, aim level (0 hip, 1 aimed; 0 also means the scope camera is off), and the eye's
    /// offset from the scope's axis in lens radii.
    a: Vec4,
    /// The sight line in world space and the red dot's radius in radians.
    b: Vec4,
}

impl Material for LensMaterial {
    fn fragment_shader() -> ShaderRef {
        "shaders/scope.wgsl".into()
    }

    fn alpha_mode(&self) -> AlphaMode {
        if self.params.a.x as u32 == Reticle::RedDot as u32 { AlphaMode::Blend } else { AlphaMode::Opaque }
    }
}

/// The main view's field of view (radians) at aim `level`: `zoom` is `ads_fov`, or `ads_fov_scoped`
/// through a scope.
pub fn main_fov(hip: f32, level: f32, zoom: f32) -> f32 {
    hip * (1.0 - level * (1.0 - zoom))
}

/// The scope camera's field of view so the eyepiece, `lens` radians across in the main view (whose
/// field of view is `main`), shows the world `mag` times larger than the unzoomed `hip` view does.
pub fn scope_fov(lens: f32, hip: f32, main: f32, mag: f32) -> f32 {
    lens * hip / (main * mag.max(1.0))
}

/// How much the mouse turns the view at aim `level`: through a scope its magnification slows it,
/// otherwise the narrower aimed view does.
pub fn look_scale(level: f32, ads_fov: f32, scoped: Option<f32>) -> f32 {
    match scoped {
        Some(mag) => 1.0 + level * (1.0 / mag.max(1.0) - 1.0),
        None => 1.0 - level * (1.0 - ads_fov),
    }
}

/// The scope camera only renders while you are actually looking through a scope in play.
pub fn scope_active(level: f32, scoped: bool, in_game: bool) -> bool {
    level > 0.01 && scoped && in_game
}

/// The magnification of a scope on `kind` with optic part `optic` fitted.
pub fn fitted_mag(tuning: &Tuning, kind: WeaponKind, optic: usize) -> Option<f32> {
    let mag = tuning.gun(kind)?.scope_mag;
    (customizable(kind) && optic == 2 && mag > 1.0).then_some(mag)
}

fn scoped(tuning: Res<Tuning>, arsenal: Res<Arsenal>, loadout: Res<Loadout>, mut scoped: ResMut<Scoped>) {
    let kind = arsenal.kind();
    let now = Scoped(fitted_mag(&tuning, kind, loadout.part(kind, 0)));
    if *scoped != now {
        *scoped = now;
    }
}

fn spawn(mut commands: Commands, mut images: ResMut<Assets<Image>>) {
    let image = images.add(Image::new_target_texture(RESOLUTION, RESOLUTION, TextureFormat::Rgba16Float, None));
    commands.spawn((
        Name::new("Scope camera"),
        ScopeCamera,
        Camera3d::default(),
        Camera { order: -1, is_active: false, ..default() },
        RenderTarget::Image(image.clone().into()),
        bevy::camera::Hdr,
        Tonemapping::None,
        Msaa::Off,
        Projection::from(PerspectiveProjection { fov: 0.1, near: NEAR, aspect_ratio: 1.0, ..default() }),
        Transform::default(),
    ));
    commands.insert_resource(ScopeImage(image));
}

/// Give each weapon model's sight sockets their picture, once the model is in.
fn fit_lenses(
    mut commands: Commands,
    image: Res<ScopeImage>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<LensMaterial>>,
    models: Query<&WeaponModel>,
    children: Query<&Children>,
    lenses: Query<(), With<Lens>>,
) {
    for model in &models {
        let kind = WEAPONS[model.index];
        let (eye, dot) = model.sights();
        let scope = if kind == WeaponKind::Dmr { Reticle::MilDot } else { Reticle::Chevron };
        for (socket, reticle) in [(eye, scope), (dot, Reticle::RedDot)] {
            let Some(socket) = socket else { continue };
            if children.get(socket).is_ok_and(|c| c.iter().any(|e| lenses.contains(e))) {
                continue;
            }
            // The eyepiece socket is scaled by its radius, the window's by its half sizes.
            let mesh = if reticle == Reticle::RedDot { meshes.add(Rectangle::new(2.0, 2.0)) } else { meshes.add(Circle::new(1.0)) };
            let material = materials.add(LensMaterial {
                params: LensParams { a: Vec4::new(reticle as u32 as f32, 0.0, 0.0, 0.0), b: Vec4::new(0.0, 0.0, -1.0, DOT) },
                image: (reticle != Reticle::RedDot).then(|| image.0.clone()),
            });
            // The red dot's window sits a hair in front of the modelled glass (+Z faces the eye).
            let at = if reticle == Reticle::RedDot { Transform::from_xyz(0.0, 0.0, 0.002) } else { Transform::default() };
            commands.entity(socket).with_child((Lens { reticle }, Mesh3d(mesh), MeshMaterial3d(material), at));
        }
    }
}

/// The red dot's own modelled dot gives way to the one drawn at infinity.
fn hide_modelled_dots(
    mut commands: Commands,
    added: Query<(Entity, &GltfMaterialName), Added<GltfMaterialName>>,
    children: Query<&ChildOf>,
    models: Query<(), With<WeaponModel>>,
    names: Query<&Name>,
) {
    for (e, name) in &added {
        if !children.iter_ancestors(e).any(|a| models.contains(a)) {
            continue;
        }
        // The red dot's window glass too: its lens draws the tint, and the modelled glass hid the dot.
        // Materials are named per gun (`rifle.glass`).
        let is = |m: &str| name.0 == m || name.0.ends_with(&format!(".{m}"));
        let window = is("glass") && children.iter_ancestors(e).any(|a| names.get(a).is_ok_and(|n| n.as_str() == "att.optic.reddot"));
        if is("reticle") || window {
            commands.entity(e).insert(Visibility::Hidden);
        }
    }
}

/// Turn the scope camera on while you look through a scope in play. Decided before `PostUpdate`, so
/// the renderer's per-view work (shadow cascades, culling) sees it the same frame. The camera carries
/// the sky only while it is on: an idle camera with `AtmosphereSettings` leaves the main view's
/// pipelines expecting atmosphere bindings its bind group lacks, a validation error that quits.
#[allow(clippy::too_many_arguments)]
fn activate(
    mut commands: Commands,
    scoped: Res<Scoped>,
    arsenal: Res<Arsenal>,
    aim: Res<Aim>,
    menu: Option<Res<crate::menu::Menu>>,
    driving: Query<(), (With<Player>, With<Driving>)>,
    vm: Single<&ViewModel>,
    models: Query<&WeaponModel>,
    player_sky: Query<(), (With<PlayerCamera>, With<AtmosphereSettings>)>,
    camera: Single<(Entity, &mut Camera, Has<AtmosphereSettings>), With<ScopeCamera>>,
) {
    let (e, mut camera, has_sky) = camera.into_inner();
    let in_game = menu.as_ref().is_none_or(|m| m.playing) && vm.presented() < 0.05 && driving.is_empty();
    let eye = models.iter().find(|m| m.index == arsenal.current).and_then(|m| m.sights().0);
    let active = scope_active(aim.level, scoped.0.is_some(), in_game) && eye.is_some();
    if camera.is_active != active {
        camera.is_active = active;
    }
    let sky = active && !player_sky.is_empty();
    if sky && !has_sky {
        commands.entity(e).insert(AtmosphereSettings { aerial_view_lut_max_distance: 6000.0, ..default() });
    } else if !sky && has_sky {
        commands.entity(e).remove::<AtmosphereSettings>();
    }
}

/// Put the scope camera at the current scope's eyepiece, looking down it, sized to its
/// magnification; feed every lens its aim and eye offset. Runs after transforms propagate so it
/// follows this frame's sway and recoil.
#[allow(clippy::too_many_arguments)]
fn follow(
    tuning: Res<Tuning>,
    scoped: Res<Scoped>,
    arsenal: Res<Arsenal>,
    aim: Res<Aim>,
    models: Query<&WeaponModel>,
    player_cam: Single<(&GlobalTransform, &Projection), (With<PlayerCamera>, Without<ScopeCamera>)>,
    scope_cam: Single<(&Camera, &mut GlobalTransform, &mut Projection), With<ScopeCamera>>,
    lenses: Query<(&Lens, &ChildOf, &MeshMaterial3d<LensMaterial>)>,
    globals: Query<&GlobalTransform, (Without<ScopeCamera>, Without<PlayerCamera>)>,
    mut materials: ResMut<Assets<LensMaterial>>,
) {
    let (cam_g, cam_proj) = *player_cam;
    let (camera, mut scope_g, mut scope_proj) = scope_cam.into_inner();
    let active = camera.is_active;
    let eye = models.iter().find(|m| m.index == arsenal.current).and_then(|m| m.sights().0).and_then(|e| globals.get(e).ok());
    if let (true, Some(eye), Some(mag)) = (active, eye, scoped.0) {
        let (scale, rot, at) = eye.to_scale_rotation_translation();
        *scope_g = GlobalTransform::from(Transform::from_translation(at).with_rotation(rot));
        let distance = cam_g.translation().distance(at).max(0.02);
        let lens = 2.0 * (scale.x / distance).atan();
        let main = match cam_proj {
            Projection::Perspective(p) => p.fov,
            _ => tuning.fov_degrees.to_radians(),
        };
        if let Projection::Perspective(p) = &mut *scope_proj {
            p.fov = scope_fov(lens, tuning.fov_degrees.to_radians(), main, mag);
            p.aspect_ratio = 1.0;
            p.near = NEAR;
        }
    }

    // Each lens: its aim (0 shows dark glass), the eye's offset from its axis, and the sight line.
    for (lens, parent, material) in &lenses {
        let Ok(socket) = globals.get(parent.parent()) else { continue };
        let local = socket.affine().inverse().transform_point3(cam_g.translation());
        let level = if lens.reticle == Reticle::RedDot || active { aim.level } else { 0.0 };
        let forward = socket.rotation() * Vec3::NEG_Z;
        let a = Vec4::new(lens.reticle as u32 as f32, level, local.x, local.y);
        let b = forward.extend(DOT);
        // Only touch a material that changed: a mutable borrow re-uploads it.
        if materials.get(&material.0).is_some_and(|m| m.params.a != a || m.params.b != b)
            && let Some(mut m) = materials.get_mut(&material.0)
        {
            m.params.a = a;
            m.params.b = b;
        }
    }
}

/// The scope sees the world the way the main view does: its exposure and fog (the sky is `activate`'s).
fn match_view(
    mut commands: Commands,
    player_cam: Single<(Option<&Exposure>, Option<&DistanceFog>), (With<PlayerCamera>, Without<ScopeCamera>)>,
    scope_cam: Single<(Entity, Option<&mut Exposure>, Option<&mut DistanceFog>), With<ScopeCamera>>,
) {
    let (exposure, fog) = *player_cam;
    let (e, mut my_exposure, mut my_fog) = scope_cam.into_inner();
    match (exposure, my_exposure.as_deref_mut()) {
        (Some(x), Some(mine)) if mine.ev100 != x.ev100 => mine.ev100 = x.ev100,
        (Some(x), None) => {
            commands.entity(e).insert(*x);
        }
        _ => {}
    }
    match (fog, my_fog.as_deref_mut()) {
        (Some(f), Some(mine)) => {
            mine.color = f.color;
            mine.falloff = f.falloff.clone();
        }
        (Some(f), None) => {
            commands.entity(e).insert(f.clone());
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scope_fov_magnifies() {
        let hip = 75f32.to_radians();
        let main = main_fov(hip, 1.0, 0.85);
        let lens = 13f32.to_radians();
        let fov = scope_fov(lens, hip, main, 3.0);
        assert!((fov - lens / (0.85 * 3.0)).abs() < 1e-6, "{fov}");
        // The eyepiece then shows the world three times as large as the hip view does.
        let shown = (lens / fov) * (hip / main);
        assert!((shown - 3.0).abs() < 1e-4, "{shown}");
    }

    #[test]
    fn look_scale_scoped() {
        assert!((look_scale(1.0, 0.7, Some(8.0)) - 0.125).abs() < 1e-6);
        assert_eq!(look_scale(0.0, 0.7, Some(8.0)), 1.0);
    }

    #[test]
    fn look_scale_irons_unchanged() {
        assert!((look_scale(1.0, 0.7, None) - 0.7).abs() < 1e-6);
        assert!((look_scale(0.5, 0.7, None) - 0.85).abs() < 1e-6);
    }

    #[test]
    fn scope_camera_only_while_aiming_through_a_scope() {
        assert!(!scope_active(0.0, true, true));
        assert!(scope_active(0.5, true, true));
        assert!(!scope_active(1.0, false, true));
        assert!(!scope_active(1.0, true, false));
    }

    #[test]
    fn magnification_per_gun() {
        let t = Tuning::default();
        assert_eq!(fitted_mag(&t, WeaponKind::Dmr, 2), Some(8.0));
        assert_eq!(fitted_mag(&t, WeaponKind::Rifle, 2), Some(3.0));
        assert_eq!(fitted_mag(&t, WeaponKind::Smg, 2), Some(3.0));
        // Irons and the red dot don't magnify; neither does a gun with no scope part.
        assert_eq!(fitted_mag(&t, WeaponKind::Rifle, 1), None);
        assert_eq!(fitted_mag(&t, WeaponKind::Pistol, 2), None);
        assert_eq!(fitted_mag(&t, WeaponKind::RocketLauncher, 2), None);
    }

    #[test]
    fn shipped_tuning_magnification() {
        let t: Tuning = toml::from_str(&std::fs::read_to_string("tuning.toml").unwrap()).unwrap();
        assert_eq!(t.dmr.scope_mag, 8.0);
        assert_eq!(t.rifle.scope_mag, 3.0);
        assert_eq!(t.smg.scope_mag, 3.0);
        assert_eq!(t.ads_fov_scoped, 0.85);
    }
}
