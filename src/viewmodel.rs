//! First-person weapon models hanging off the camera: one rigged glTF per weapon
//! (`assets/models/weapons/<id>.glb`, built by `tools/weapons`), only the current one visible.
//! Each model's own clips (idle, fire, reload, draw, inspect) move its slide, bolt, mag and so on;
//! code adds recoil, bob and aim-down-sights on top, shows the fitted gunsmith parts and keeps
//! `weapon::Muzzle` on the model's muzzle so tracers leave the barrel.

use std::collections::HashMap;
use std::time::Duration;

use bevy::gltf::Gltf;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};

use crate::camera::{PlayerCamera, Widen};
use crate::controller::{MoveState, Player};
use crate::gunsmith::{Loadout, MESHES, customizable};
use crate::input::PlayerInput;
use crate::tuning::Tuning;
use crate::weapon::{Arsenal, Muzzle, WEAPONS, WeaponFired, WeaponKind, SWITCH_TIME};

pub struct ViewModelPlugin;

impl Plugin for ViewModelPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(PostStartup, spawn)
            .add_systems(Update, (hook_up, animate, widen, play_clips, show_parts, flash).chain())
            .add_systems(PostUpdate, track_muzzle.after(TransformSystems::Propagate))
            .add_observer(on_ready);
    }
}

#[derive(Component, Default)]
pub struct ViewModel {
    kick: f32,
    kick_vel: f32,
    bob: f32,
    /// 0 in play, 1 presented to the camera by the gunsmith.
    showcase: f32,
    spin: f32,
    flash: f32,
}

impl ViewModel {
    /// How far the gunsmith has turned the weapon to the camera, 0 in play to 1.
    pub fn presented(&self) -> f32 {
        self.showcase
    }
}

/// The clips every weapon model carries, by glTF animation name.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
enum Clip {
    Idle,
    Fire,
    Reload,
    Draw,
    Inspect,
}

impl Clip {
    const ALL: [Clip; 5] = [Clip::Idle, Clip::Fire, Clip::Reload, Clip::Draw, Clip::Inspect];
    fn name(self) -> &'static str {
        match self {
            Clip::Idle => "idle",
            Clip::Fire => "fire",
            Clip::Reload => "reload",
            Clip::Draw => "draw",
            Clip::Inspect => "inspect",
        }
    }
}

#[derive(Component)]
pub(crate) struct WeaponModel {
    pub(crate) index: usize,
    gltf: Handle<Gltf>,
    ready: bool,
    rig: Option<Rig>,
}

/// What a spawned model exposes once its scene is in: the animation player, its clips with their
/// lengths, the gunsmith part meshes, the muzzle and the sight line.
struct Rig {
    player: Entity,
    clips: HashMap<Clip, (AnimationNodeIndex, f32)>,
    playing: Clip,
    parts: Vec<(Entity, usize, usize)>,
    muzzle: Option<Entity>,
    /// The optic rail's top in model space, for lining up aim-down-sights.
    optic: Option<Vec3>,
    /// The harpoon's spear, hidden while it is out on the line.
    spear: Option<Entity>,
    /// The scope's eyepiece and the red dot's window (`scope.eye`, `reddot.lens`), with where each
    /// rests in model space; `scope.rs` draws the sight pictures on them.
    eye: Option<(Entity, Vec3)>,
    dot: Option<(Entity, Vec3)>,
}

impl WeaponModel {
    /// The model's scope eyepiece and red dot window sockets, once its scene is in.
    pub(crate) fn sights(&self) -> (Option<Entity>, Option<Entity>) {
        self.rig.as_ref().map_or((None, None), |r| (r.eye.map(|e| e.0), r.dot.map(|d| d.0)))
    }
}

/// The muzzle flash on a model: a small hot sphere shown for a few frames after each shot.
#[derive(Component)]
struct Flash;

/// Where the trigger sits in front of the camera (before widening); each model's origin is its
/// trigger. Low and right, the gun pointing in past the crosshair, the firing hand in view at the
/// bottom edge and the support arm near straight to the handguard, as shooters frame it.
const REST: Vec3 = Vec3::new(0.15, -0.15, -0.36);
/// Aimed: centred, close to the eye; x and y are replaced by the weapon's own sight line.
const AIMED_DEPTH: f32 = -0.3;
/// Where the gun sits in the gunsmith: right of centre, turned to show its side.
const SHOWCASE: Vec3 = Vec3::new(0.22, -0.02, -0.95);
/// Sight line above the optic rail for the flip-up irons (the red dot and scope use their sockets).
const IRONS_HEIGHT: f32 = 0.012;
/// How far in front of the eye a scope's eyepiece sits when aimed.
const EYE_RELIEF: f32 = 0.13;
/// Aim level past which the stock is hidden.
const STOCK_HIDDEN: f32 = 0.8;

/// Where the viewmodel sits when fully aimed with optic part `optic` fitted (irons, red dot, scope).
fn aimed_at(rig: &Rig, kind: WeaponKind, optic: usize) -> Option<Vec3> {
    let h = hold(kind);
    match (optic, rig.eye, rig.dot) {
        (2, Some((_, e)), _) => Some(-(h + e) - Vec3::Z * EYE_RELIEF),
        (1, _, Some((_, d))) => Some(Vec3::new(-(h + d).x, -(h + d).y, AIMED_DEPTH)),
        _ => rig.optic.map(|o| {
            let s = h + o + Vec3::Y * IRONS_HEIGHT;
            Vec3::new(-s.x, -s.y, AIMED_DEPTH)
        }),
    }
}

/// Per-weapon nudge from `REST` (the launchers ride higher on the shoulder, the fist sits low).
fn hold(kind: WeaponKind) -> Vec3 {
    match kind {
        WeaponKind::RocketLauncher => Vec3::new(0.03, -0.05, 0.02),
        WeaponKind::Pistol | WeaponKind::Revolver => Vec3::new(-0.01, 0.01, -0.04),
        WeaponKind::Grenade => Vec3::new(0.0, -0.02, 0.0),
        WeaponKind::Fist => Vec3::new(0.02, -0.06, -0.06),
        _ => Vec3::ZERO,
    }
}

fn spawn(mut commands: Commands, server: Res<AssetServer>, view: Single<Entity, With<Widen>>, mut meshes: Option<ResMut<Assets<Mesh>>>, mut materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let flash = match (meshes.as_mut(), materials.as_mut()) {
        (Some(meshes), Some(materials)) => Some((
            meshes.add(Sphere::new(0.035)),
            materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.75, 0.35), emissive: LinearRgba::rgb(30.0, 16.0, 4.0), unlit: true, ..default() }),
        )),
        _ => None,
    };
    commands.entity(*view).with_children(|cam| {
        cam.spawn((ViewModel::default(), Transform::from_translation(REST), Visibility::default())).with_children(|vm| {
            for (index, kind) in WEAPONS.iter().enumerate() {
                let path = format!("models/weapons/{}.glb", kind.id());
                vm.spawn((
                    WeaponModel { index, gltf: server.load(path.clone()), ready: false, rig: None },
                    WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(path))),
                    Transform::from_translation(hold(*kind)),
                    Visibility::Hidden,
                ));
            }
        });
    });
    if let Some((mesh, mat)) = flash {
        commands.insert_resource(FlashAssets { mesh, mat });
    }
}

#[derive(Resource)]
struct FlashAssets {
    mesh: Handle<Mesh>,
    mat: Handle<StandardMaterial>,
}

fn on_ready(ready: On<WorldInstanceReady>, mut models: Query<&mut WeaponModel>) {
    if let Ok(mut model) = models.get_mut(ready.entity) {
        model.ready = true;
    }
}

/// Once a model's scene and glTF are in: give its animation player a graph of the five clips,
/// find the part meshes and sockets, and put a flash on the muzzle.
#[allow(clippy::too_many_arguments)]
fn hook_up(
    mut commands: Commands,
    gltfs: Res<Assets<Gltf>>,
    clips: Res<Assets<AnimationClip>>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
    flash: Option<Res<FlashAssets>>,
    mut models: Query<(Entity, &mut WeaponModel)>,
    children: Query<&Children>,
    parents: Query<&ChildOf>,
    transforms: Query<&Transform>,
    names: Query<&Name>,
    players: Query<(), With<AnimationPlayer>>,
) {
    for (root, mut model) in &mut models {
        if !model.ready || model.rig.is_some() {
            continue;
        }
        let Some(gltf) = gltfs.get(&model.gltf) else { continue };
        let Some(player) = children.iter_descendants(root).find(|e| players.contains(*e)) else {
            warn!("weapon model {} has no animation player", WEAPONS[model.index].id());
            model.rig = Some(Rig { player: root, clips: HashMap::new(), playing: Clip::Idle, parts: vec![], muzzle: None, optic: None, spear: None, eye: None, dot: None });
            continue;
        };
        let mut graph = AnimationGraph::new();
        let mut nodes = HashMap::new();
        for clip in Clip::ALL {
            if let Some(handle) = gltf.named_animations.get(clip.name()) {
                let length = clips.get(handle).map_or(1.0, |c| c.duration()).max(0.01);
                nodes.insert(clip, (graph.add_clip(handle.clone(), 1.0, graph.root), length));
            }
        }
        commands.entity(player).insert((AnimationGraphHandle(graphs.add(graph)), AnimationTransitions::new()));
        let mut parts = vec![];
        let (mut muzzle, mut optic, mut spear, mut eye, mut dot) = (None, None, None, None, None);
        for e in children.iter_descendants(root) {
            let Ok(name) = names.get(e) else { continue };
            for (slot, meshes) in MESHES.iter().enumerate() {
                if let Some(part) = meshes.iter().position(|m| *m == name.as_str()) {
                    parts.push((e, slot, part));
                }
            }
            match name.as_str() {
                "muzzle" => muzzle = Some(e),
                "mesh.spear" => spear = Some(e),
                "optic" => optic = Some(model_space(e, root, &parents, &transforms).translation),
                // The sight sockets show with their optic part.
                "scope.eye" => {
                    eye = Some((e, model_space(e, root, &parents, &transforms).translation));
                    parts.push((e, 0, 2));
                }
                "reddot.lens" => {
                    dot = Some((e, model_space(e, root, &parents, &transforms).translation));
                    parts.push((e, 0, 1));
                }
                _ => {}
            }
        }
        if let (Some(m), Some(fx)) = (muzzle, &flash) {
            let kind = WEAPONS[model.index];
            if !matches!(kind, WeaponKind::Fist | WeaponKind::Harpoon) {
                commands.entity(m).with_child((Flash, Mesh3d(fx.mesh.clone()), MeshMaterial3d(fx.mat.clone()), Transform::default(), Visibility::Hidden));
            }
        }
        model.rig = Some(Rig { player, clips: nodes, playing: Clip::Idle, parts, muzzle, optic, spear, eye, dot });
    }
}

/// `e`'s transform relative to `root`, from local transforms (works before propagation).
pub(crate) fn model_space(mut e: Entity, root: Entity, parents: &Query<&ChildOf>, transforms: &Query<&Transform>) -> Transform {
    let mut acc = Transform::IDENTITY;
    while e != root {
        let Ok(tf) = transforms.get(e) else { break };
        acc = *tf * acc;
        let Ok(parent) = parents.get(e) else { break };
        e = parent.parent();
    }
    acc
}

fn animate(
    time: Res<Time>,
    tuning: Res<Tuning>,
    arsenal: Res<Arsenal>,
    loadout: Res<Loadout>,
    mut fired: MessageReader<WeaponFired>,
    player: Single<&Player>,
    mut vm: Single<(&mut Transform, &mut ViewModel, &mut Visibility), Without<WeaponModel>>,
    mut models: Query<(&WeaponModel, &mut Visibility)>,
    aim: Option<Res<crate::weapon::Aim>>,
    menu: Option<Res<crate::menu::Menu>>,
    driving: Query<(), With<crate::vehicle::Driving>>,
    real: Res<Time<Real>>,
) {
    let dt = time.delta_secs();
    let (tf, vm, vis) = &mut *vm;
    // Menus pause game time, so the presentation runs on real time.
    let showcase = menu.as_ref().map_or(crate::menu::Showcase::None, |m| m.showcase());
    let want = if showcase == crate::menu::Showcase::Gun { 1.0 } else { 0.0 };
    vm.showcase += (want - vm.showcase) * (1.0 - (-8.0 * real.delta_secs()).exp());
    vm.spin += real.delta_secs();
    // Out of sight on the title and pause screens, in third person and while driving, unless the gunsmith is showing it.
    let in_game = menu.as_ref().is_none_or(|m| m.playing) && !tuning.third_person && driving.is_empty();
    let want_vis = if in_game || showcase == crate::menu::Showcase::Gun { Visibility::Inherited } else { Visibility::Hidden };
    if **vis != want_vis {
        **vis = want_vis;
    }

    for f in fired.read() {
        // The model's fire clip carries most of the kick; the spring adds weight to it.
        vm.kick_vel += f.kick * 1.5;
        vm.flash = 0.04;
    }
    vm.flash -= dt;
    // Damped spring back to rest.
    let accel = -160.0 * vm.kick - 16.0 * vm.kick_vel;
    vm.kick_vel += accel * dt;
    vm.kick += vm.kick_vel * dt;

    // Walk bob scales with ground speed and stops in the air.
    let speed = player.horizontal_speed();
    let grounded = matches!(player.state, MoveState::Ground | MoveState::Slide);
    let amount = if grounded { (speed / tuning.max_speed).min(1.5) } else { 0.0 };
    vm.bob += dt * speed * 1.7;
    let bob = Vec3::new(vm.bob.cos(), -(vm.bob * 2.0).sin().abs() * 0.6, 0.0) * 0.012 * amount;

    // Aimed: the current weapon's sight line on the screen centre, a scope's eyepiece close to the eye.
    let kind = arsenal.kind();
    let optic = if customizable(kind) { loadout.part(kind, 0) } else { 0 };
    let aimed = models.iter().find(|(m, _)| m.index == arsenal.current).and_then(|(m, _)| aimed_at(m.rig.as_ref()?, kind, optic));
    let aimed = aimed.unwrap_or(Vec3::new(0.0, -0.08, AIMED_DEPTH));

    let ads = aim.as_ref().map_or(0.0, |a| a.level);
    let rest = REST.lerp(aimed, ads);
    let play_pos = rest + bob * (1.0 - 0.8 * ads) + Vec3::Z * vm.kick * 0.04;
    let play_rot = Quat::from_rotation_x(vm.kick * 0.08);
    let show_rot = Quat::from_rotation_y(1.25 + 0.3 * (vm.spin * 0.7).sin()) * Quat::from_rotation_x(0.08);
    tf.translation = play_pos.lerp(SHOWCASE, vm.showcase);
    tf.rotation = play_rot.slerp(show_rot, vm.showcase);

    for (model, mut vis) in &mut models {
        let want = if model.index == arsenal.current { Visibility::Inherited } else { Visibility::Hidden };
        if *vis != want {
            *vis = want;
        }
    }
}

/// Plays the current model's clips: draw on a swap, fire per shot (sped up to the fire rate),
/// reload stretched to the reload time, inspect on V, idle the rest of the time.
#[allow(clippy::too_many_arguments)]
fn play_clips(
    tuning: Res<Tuning>,
    arsenal: Res<Arsenal>,
    loadout: Res<Loadout>,
    mut input: ResMut<PlayerInput>,
    mut fired: MessageReader<WeaponFired>,
    mut models: Query<&mut WeaponModel>,
    mut anims: Query<(&mut AnimationPlayer, &mut AnimationTransitions)>,
    mut last: Local<Option<usize>>,
    mut was_reloading: Local<bool>,
) {
    let shots = fired.read().count();
    let inspect = std::mem::take(&mut input.inspect_pressed);
    let kind = arsenal.kind();
    let swapped = *last != Some(arsenal.current);
    let reloading = arsenal.reload > 0.0;
    let reload_started = reloading && !*was_reloading;
    *was_reloading = reloading;
    for mut model in &mut models {
        if model.index != arsenal.current {
            continue;
        }
        let Some(rig) = model.rig.as_mut() else { return };
        let Ok((mut anim, mut transitions)) = anims.get_mut(rig.player) else { return };
        *last = Some(arsenal.current);
        let want = if swapped {
            Some((Clip::Draw, SWITCH_TIME.max(0.2)))
        } else if reload_started {
            Some((Clip::Reload, kind.reload_time(&tuning)))
        } else if shots > 0 {
            Some((Clip::Fire, kind.cooldown(&tuning, &loadout)))
        } else if inspect && rig.playing == Clip::Idle {
            Some((Clip::Inspect, 0.0))
        } else {
            None
        };
        if let Some((clip, fit)) = want
            && let Some(&(node, length)) = rig.clips.get(&clip)
        {
            // Never slower than authored; faster when the game's timing is shorter than the clip.
            let speed = if fit > 0.0 { (length / fit).max(1.0) } else { 1.0 };
            let speed = if clip == Clip::Reload && fit > 0.0 { length / fit } else { speed };
            transitions.play(&mut anim, node, Duration::from_millis(if clip == Clip::Fire { 10 } else { 60 })).set_speed(speed);
            rig.playing = clip;
            continue;
        }
        let done = rig.clips.get(&rig.playing).is_none_or(|(node, _)| anim.animation(*node).is_none_or(|a| a.is_finished()));
        if rig.playing != Clip::Idle && done || anim.playing_animations().next().is_none() {
            if let Some(&(node, _)) = rig.clips.get(&Clip::Idle) {
                transitions.play(&mut anim, node, Duration::from_millis(120)).repeat();
            }
            rig.playing = Clip::Idle;
        }
    }
}

/// Show exactly the fitted part per slot on the current gunsmith weapon. Aimed, the stock is
/// hidden: it runs back past the eye and would fill the bottom of the view.
fn show_parts(
    loadout: Res<Loadout>,
    arsenal: Res<Arsenal>,
    aim: Option<Res<crate::weapon::Aim>>,
    models: Query<&WeaponModel>,
    mut vis: Query<&mut Visibility>,
) {
    let aimed = aim.is_some_and(|a| a.level > STOCK_HIDDEN);
    for model in &models {
        let Some(rig) = &model.rig else { continue };
        let kind = WEAPONS[model.index];
        // After a shot the spear is gone until the reload brings it back in.
        if let Some(e) = rig.spear
            && let Ok(mut v) = vis.get_mut(e)
        {
            let out = arsenal.spent[model.index] > 0 && !(arsenal.current == model.index && arsenal.reload > 0.0);
            let want = if out { Visibility::Hidden } else { Visibility::Inherited };
            if *v != want {
                *v = want;
            }
        }
        for &(e, slot, part) in &rig.parts {
            let fitted = customizable(kind) && loadout.part(kind, slot) == part && !(slot == 3 && aimed && model.index == arsenal.current);
            let want = if fitted { Visibility::Inherited } else { Visibility::Hidden };
            if let Ok(mut v) = vis.get_mut(e)
                && *v != want
            {
                *v = want;
            }
        }
    }
}

fn flash(vm: Single<&ViewModel>, mut flashes: Query<(&mut Visibility, &mut Transform), With<Flash>>, mut n: Local<u32>) {
    let on = vm.flash > 0.0;
    *n = n.wrapping_add(1);
    for (mut v, mut tf) in &mut flashes {
        let want = if on { Visibility::Inherited } else { Visibility::Hidden };
        if *v != want {
            *v = want;
        }
        if on {
            // A different size and twist each shot so it never looks stamped.
            tf.scale = Vec3::new(1.0, 1.0, 1.6) * (0.8 + (*n % 3) as f32 * 0.2);
            tf.rotation = Quat::from_rotation_z(*n as f32 * 1.3);
        }
    }
}

/// Keep `Muzzle` on the current model's muzzle socket, in the camera's frame.
/// How much wider than the camera's own the gun and arms are drawn, as a scale across the view:
/// the camera's field of view over the viewmodel's, back to 1 when aimed (the sights were set up
/// for the true view) and in the gunsmith.
pub fn widening(fov: f32, viewmodel_fov: f32, settled: f32) -> f32 {
    let k = (fov.to_radians() * 0.5).tan() / (viewmodel_fov.to_radians() * 0.5).tan();
    k + (1.0 - k) * settled.clamp(0.0, 1.0)
}

fn widen(tuning: Res<Tuning>, aim: Option<Res<crate::weapon::Aim>>, vm: Single<&ViewModel>, mut view: Single<&mut Transform, With<Widen>>) {
    let ads = aim.as_ref().map_or(0.0, |a| a.level);
    let k = widening(tuning.fov_degrees, tuning.viewmodel_fov_degrees, ads.max(vm.showcase));
    let scale = Vec3::new(k, k, 1.0);
    if view.scale != scale {
        view.scale = scale;
    }
}

fn track_muzzle(
    arsenal: Res<Arsenal>,
    mut muzzle: ResMut<Muzzle>,
    models: Query<&WeaponModel>,
    camera: Single<&GlobalTransform, With<PlayerCamera>>,
    globals: Query<&GlobalTransform>,
) {
    let Some(rig) = models.iter().find(|m| m.index == arsenal.current).and_then(|m| m.rig.as_ref()) else { return };
    let Some(Ok(at)) = rig.muzzle.map(|m| globals.get(m)) else { return };
    let local = camera.affine().inverse().transform_point3(at.translation());
    // Keep shots sane if the model is mid-swap or off in the gunsmith.
    if local.z < -0.1 && local.length() < 2.0 {
        muzzle.0 = local;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn widening_matches_the_viewmodel_fov_and_settles_when_aimed() {
        let k = widening(75.0, 65.0, 0.0);
        assert!((k - 37.5f32.to_radians().tan() / 32.5f32.to_radians().tan()).abs() < 1e-5 && k > 1.15, "{k}");
        assert!((widening(75.0, 55.0, 1.0) - 1.0).abs() < 1e-6);
        assert!((widening(75.0, 75.0, 0.3) - 1.0).abs() < 1e-6);
    }
}
