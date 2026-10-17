//! The player's own body: Kenney's soldier standing under the first-person
//! camera, so you see your legs when you look down and cast a shadow. It is
//! driven by the controller's move state (idle, walk, sprint, jump, fall,
//! crouch/slide). The head is rendered only into shadow maps so it never
//! fills the screen.

use std::f32::consts::PI;
use std::time::Duration;

use bevy::camera::visibility::RenderLayers;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAssetRoot, WorldInstanceReady};

use crate::controller::{MoveState, Player};
use crate::input::ViewAngles;
use crate::tuning::Tuning;

/// Render layer the camera does not see but the shadow-casting light does.
pub const SHADOW_ONLY_LAYER: usize = 1;
/// Kenney's soldier is 0.84 units tall with its origin at the feet.
pub const MODEL_HEIGHT: f32 = 0.84;
const MODEL: &str = "models/arena/character-soldier.glb";
/// How far behind the eyes the body stands, so the camera sits in the head.
const BACK: f32 = 0.12;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Pose {
    Idle,
    Walk,
    Sprint,
    Jump,
    Fall,
    Crouch,
}

impl Pose {
    const ALL: [Pose; 6] = [Pose::Idle, Pose::Walk, Pose::Sprint, Pose::Jump, Pose::Fall, Pose::Crouch];

    /// Index of the clip inside `character-soldier.glb`.
    fn clip_index(self) -> usize {
        match self {
            Pose::Idle => 1,
            Pose::Walk => 2,
            Pose::Sprint => 3,
            Pose::Jump => 4,
            Pose::Fall => 5,
            Pose::Crouch => 6,
        }
    }
}

/// Which clip fits the current movement.
pub fn pose_for(state: MoveState, crouched: bool, speed: f32, vertical: f32, max_speed: f32) -> Pose {
    match state {
        MoveState::Mantle => Pose::Jump,
        MoveState::WallRun => Pose::Sprint,
        MoveState::Air => {
            if vertical > 0.5 {
                Pose::Jump
            } else {
                Pose::Fall
            }
        }
        MoveState::Slide => Pose::Crouch,
        MoveState::Ground => {
            if crouched {
                Pose::Crouch
            } else if speed < 0.3 {
                Pose::Idle
            } else if speed < max_speed * 0.6 {
                Pose::Walk
            } else {
                Pose::Sprint
            }
        }
    }
}

/// Playback rate so the feet roughly keep up with the ground speed.
pub fn playback_rate(pose: Pose, speed: f32, max_speed: f32) -> f32 {
    match pose {
        Pose::Walk => (speed / (max_speed * 0.4)).clamp(0.7, 1.6),
        Pose::Sprint => (speed / max_speed).clamp(0.7, 1.8),
        _ => 1.0,
    }
}

pub struct BodyPlugin;

impl Plugin for BodyPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn)
            .add_systems(Update, animate)
            .add_systems(PostUpdate, follow.before(TransformSystems::Propagate))
            .add_observer(on_ready);
    }
}

#[derive(Component)]
struct Body {
    pose: Option<Pose>,
    nodes: [AnimationNodeIndex; 6],
    graph: Handle<AnimationGraph>,
    /// The glTF's `AnimationPlayer`, once the model has spawned.
    player: Option<Entity>,
}

fn spawn(mut commands: Commands, server: Res<AssetServer>, graphs: Option<ResMut<Assets<AnimationGraph>>>) {
    // No render assets in headless tests: no body.
    let Some(mut graphs) = graphs else { return };
    let clips = Pose::ALL.map(|p| server.load(GltfAssetLabel::Animation(p.clip_index()).from_asset(MODEL)));
    let (graph, nodes) = AnimationGraph::from_clips(clips);
    let nodes: [AnimationNodeIndex; 6] = nodes.try_into().expect("one node per pose");
    commands.spawn((
        Name::new("Player body"),
        Body { pose: None, nodes, graph: graphs.add(graph), player: None },
        WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(MODEL))),
        Transform::default(),
        Visibility::default(),
    ));
}

/// Hook up the animation player and move the head to the shadow-only layer.
fn on_ready(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    mut bodies: Query<&mut Body>,
    children: Query<&Children>,
    names: Query<&Name>,
    players: Query<(), With<AnimationPlayer>>,
) {
    let Ok(mut body) = bodies.get_mut(ready.entity) else { return };
    for e in children.iter_descendants(ready.entity) {
        if players.contains(e) {
            body.player = Some(e);
            commands.entity(e).insert((AnimationGraphHandle(body.graph.clone()), AnimationTransitions::new()));
        }
        // The glTF puts the mesh primitives on children of the named node.
        if names.get(e).is_ok_and(|n| n.as_str() == "head-mesh") {
            for e in std::iter::once(e).chain(children.iter_descendants(e)) {
                commands.entity(e).insert(RenderLayers::layer(SHADOW_ONLY_LAYER));
            }
        }
    }
}

/// Stand at the interpolated feet position, facing the view yaw.
fn follow(
    fixed: Res<Time<Fixed>>,
    view: Res<ViewAngles>,
    tuning: Res<Tuning>,
    player: Single<(&Player, &Transform)>,
    mut body: Single<&mut Transform, (With<Body>, Without<Player>)>,
) {
    let (p, player_tf) = *player;
    let center = p.prev_pos.lerp(player_tf.translation, fixed.overstep_fraction());
    let (forward, _) = view.flat_basis();
    body.translation = center - Vec3::Y * p.half_height(&tuning) - forward * BACK;
    // The model faces +Z; the camera looks down -Z at yaw 0.
    body.rotation = Quat::from_rotation_y(view.yaw + PI);
    body.scale = Vec3::splat(tuning.stand_height / MODEL_HEIGHT);
}

fn animate(
    tuning: Res<Tuning>,
    player: Single<&Player>,
    mut body: Single<&mut Body>,
    mut anims: Query<(&mut AnimationPlayer, &mut AnimationTransitions)>,
) {
    let Some(e) = body.player else { return };
    let Ok((mut anim, mut transitions)) = anims.get_mut(e) else { return };
    let speed = player.horizontal_speed();
    let pose = pose_for(player.state, player.crouched, speed, player.velocity.y, tuning.max_speed);
    let node = body.nodes[Pose::ALL.iter().position(|p| *p == pose).unwrap()];
    if body.pose != Some(pose) {
        body.pose = Some(pose);
        transitions.play(&mut anim, node, Duration::from_millis(150)).repeat();
    }
    if let Some(a) = anim.animation_mut(node) {
        a.set_speed(playback_rate(pose, speed, tuning.max_speed));
    }
}
