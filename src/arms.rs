//! First-person arms: a second copy of the worn character under the camera that shows only its arms
//! (`ArmsOnly`). Every frame a two-bone IK puts each palm frame (`prop_hand.R` / `.L`) where the
//! character's solved pose for the current viewmodel weapon puts it (`fingers::Solved`: the right
//! hand on the grip, the left on the handguard or foregrip, riding the shotgun's pump), so the arms
//! follow every weapon clip. One-handed weapons drop the left arm out of view.

use std::collections::HashMap;
use std::f32::consts::PI;

use bevy::math::Affine3A;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;

use crate::abilities::Class;
use crate::camera::{PlayerCamera, Widen};
use crate::character::{self, ArmsOnly, CharacterAssets, Characters, GRIP_L, GRIP_R, Rig, grip_rotation, hands};
use crate::fingers::{FingerBones, Solved, left_pose};
use crate::gunsmith::Loadout;
use crate::controller::Player;
use crate::vehicle::Driving;
use crate::viewmodel::{ViewModel, WeaponModel, model_space};
use crate::weapon::{Aim, Arsenal, WEAPONS};

/// Where the shoulders' midpoint sits, in camera space: under the eye with the head forward over
/// the gun, a little lower when aiming (the cheek comes down to the stock).
const SHOULDERS: Vec3 = Vec3::new(-0.05, -0.23, 0.0);
const SHOULDERS_AIMED: Vec3 = Vec3::new(-0.04, -0.25, 0.02);
/// The torso turns so the left shoulder leads, like a rifle stance (radians), a little more when
/// aiming.
const BLADE: f32 = -0.3;
const BLADE_AIMED: f32 = -0.45;
/// Where the elbows point, in camera space: right, left. The left elbow flares out to the left so the
/// forearm rises from the lower left corner to the handguard, seen from its side rather than end
/// on, aimed or not.
const POLE: [Vec3; 2] = [Vec3::new(0.5, -1.0, 0.3), Vec3::new(-1.0, -0.3, 0.2)];
const POLE_AIMED: Vec3 = Vec3::new(-0.5, -1.0, 0.0);
/// Where the left wrist waits, out of view, when the weapon takes one hand.
const LEFT_REST: Vec3 = Vec3::new(-0.2, -0.7, 0.05);
/// How far an arm may stretch to reach a far support point.
const MAX_STRETCH: f32 = 1.25;
/// The first-person arms are drawn this much slimmer than the character's: a sleeve a hand's
/// breadth from the eye fills the view otherwise.
const SLIM: f32 = 0.65;

pub struct ArmsPlugin;

impl Plugin for ArmsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(PostStartup, spawn).add_systems(PostUpdate, pose.after(TransformSystems::Propagate)).add_observer(on_weapon_ready);
    }
}

#[derive(Component)]
pub struct Arms;

/// The arms rig's bones for its current model, right side first.
#[derive(Component)]
struct ArmBones {
    model: Entity,
    sides: [[Entity; 5]; 2],
}

/// A weapon model's bones the hands ride, with the inverse of each one's rest transform in model
/// space.
#[derive(Component)]
struct Grips(HashMap<String, (Entity, Affine3A)>);

fn spawn(mut commands: Commands, assets: Option<Res<CharacterAssets>>, characters: Res<Characters>, class: Res<Class>, view: Single<Entity, With<Widen>>) {
    // No render assets in headless tests: no arms.
    if assets.is_none() {
        return;
    }
    let outfit = characters.class.get(&class.0).map_or("runner", |c| c.character.as_str());
    let at = Transform::from_translation(SHOULDERS - Vec3::Y * 1.4).with_rotation(Quat::from_rotation_y(PI + BLADE));
    commands.entity(*view).with_child((Name::new("First-person arms"), Arms, ArmsOnly, character::bundle(outfit, at)));
}

/// Note where a weapon model's grip bones rest, before its clips move them.
fn on_weapon_ready(ready: On<WorldInstanceReady>, mut commands: Commands, models: Query<&WeaponModel>, children: Query<&Children>, parents: Query<&ChildOf>, transforms: Query<&Transform>, names: Query<&Name>) {
    let Ok(model) = models.get(ready.entity) else { return };
    let h = hands(WEAPONS[model.index]);
    let wanted = ["root"].into_iter().chain(h.left.as_ref().map(|l| l.1.as_str()));
    let mut grips = HashMap::new();
    for e in children.iter_descendants(ready.entity) {
        if let Ok(name) = names.get(e)
            && wanted.clone().any(|w| w == name.as_str())
        {
            grips.insert(name.as_str().to_string(), (e, model_space(e, ready.entity, &parents, &transforms).compute_affine().inverse()));
        }
    }
    commands.entity(ready.entity).insert(Grips(grips));
}

/// Pose both arms onto the current weapon, after transforms have propagated so they follow this
/// frame's camera, sway and clips.
#[allow(clippy::too_many_arguments)]
fn pose(
    mut commands: Commands,
    arsenal: Option<Res<Arsenal>>,
    camera: Single<Entity, With<PlayerCamera>>,
    widened: Single<Entity, With<Widen>>,
    vm: Single<(&ViewModel, &Visibility)>,
    driving: Query<(), (With<Player>, With<Driving>)>,
    weapons: Query<(&WeaponModel, &Grips)>,
    arms: Single<(Entity, &Rig, &mut Transform, &mut Visibility, Option<&ArmBones>, Option<&FingerBones>), (With<Arms>, Without<ViewModel>)>,
    solved: Option<Res<Solved>>,
    loadout: Option<Res<Loadout>>,
    aim: Option<Res<Aim>>,
    children: Query<&Children>,
    names: Query<&Name>,
    locals: Query<&Transform, Without<Arms>>,
    mut globals: Query<&mut GlobalTransform>,
) {
    let (entity, rig, mut tf, mut vis, bones, fingers) = arms.into_inner();
    let (view, view_vis) = *vm;
    let grips = arsenal.and_then(|a| weapons.iter().find(|(m, _)| m.index == a.current));
    let shown = *view_vis != Visibility::Hidden && view.presented() < 0.05 && driving.is_empty() && grips.is_some() && rig.model().is_some();
    let want = if shown { Visibility::Inherited } else { Visibility::Hidden };
    if *vis != want {
        *vis = want;
    }
    let (Some((model, Grips(grips))), Some(root)) = (grips, rig.model()) else { return };
    if !shown {
        return;
    }
    let Some(bones) = bones.filter(|b| b.model == root) else {
        let find = |name: String| children.iter_descendants(root).find(|e| names.get(*e).is_ok_and(|n| n.as_str() == name));
        let side = |s: &str, grip: &str| -> Option<[Entity; 5]> {
            Some([find(format!("shoulder.{s}"))?, find(format!("upper_arm.{s}"))?, find(format!("forearm.{s}"))?, find(format!("hand.{s}"))?, find(grip.into())?])
        };
        if let (Some(r), Some(l)) = (side("R", GRIP_R), side("L", GRIP_L)) {
            commands.entity(entity).insert(ArmBones { model: root, sides: [r, l] });
        }
        return;
    };
    let Ok(cam) = globals.get(*camera).map(|g| g.compute_transform()) else { return };
    // The arms ride the widened view like the gun: solve in the camera's plain view and widen
    // what's written back.
    let Ok(widen) = globals.get(*widened).map(|g| g.affine() * cam.compute_affine().inverse()) else { return };
    let plain = widen.inverse();

    // The palm frames on the weapon: its model space carried along by the bone each hand rides,
    // where this character's solved poses put them. A right hand with no pose takes the shared grip
    // point the way the third-person weapon hangs; a left hand with none stays out of view.
    let kind = WEAPONS[model.index];
    let h = hands(kind);
    let pose = |p: &str| solved.as_ref().zip(rig.character()).and_then(|(s, c)| s.get(c, kind, p));
    let frame = |bone: &str, local: Option<Transform>| -> Option<Transform> {
        let (e, rest_inv) = grips.get(bone)?;
        let now = plain * globals.get(*e).ok()?.affine() * *rest_inv;
        Some(Transform::from_matrix(Mat4::from(now)) * local?)
    };
    let placed = |p: &crate::fingers::HandPose| Transform::from_translation(p.at).with_rotation(p.rot);
    let right = frame("root", pose("R").map(placed).or(Some(Transform::from_translation(h.right).with_rotation(grip_rotation().inverse()))));
    let left = h.left.as_ref().and_then(|(_, bone)| frame(bone, pose(left_pose(kind, loadout.as_deref())).or_else(|| pose("L")).map(placed)));
    let targets = [right, left];

    // Keep the shoulders where they belong under the eye, whatever the character's height, and
    // square the stance behind the gun as it comes up to the eye.
    let ads = aim.as_ref().map_or(0.0, |a| a.level);
    tf.rotation = Quat::from_rotation_y(PI + BLADE.lerp(BLADE_AIMED, ads));
    let rest = |side: &[Entity; 5]| -> Option<Transform> { Some(Transform::from_matrix(Mat4::from(plain * globals.get(side[0]).ok()?.affine())) * *locals.get(side[1]).ok()?) };
    let (Some(r), Some(l)) = (rest(&bones.sides[0]), rest(&bones.sides[1])) else { return };
    let rests = [r, l];
    let mid = cam.compute_affine().inverse().transform_point3((r.translation + l.translation) * 0.5);
    let fix = SHOULDERS.lerp(SHOULDERS_AIMED, ads) - mid;
    if fix.length() > 1e-3 {
        tf.translation += fix;
    }

    for (i, side) in bones.sides.iter().enumerate() {
        let [_, upper, fore, hand, prop] = *side;
        let (Ok(fore_l), Ok(hand_l), Ok(prop_l)) = (locals.get(fore), locals.get(hand), locals.get(prop)) else { continue };
        let upper_rest = rests[i];
        let s = upper_rest.translation + cam.rotation * fix;
        let (wrist, hand_rot) = match targets[i] {
            Some(f) => {
                let rot = f.rotation * prop_l.rotation.inverse();
                (f.translation - rot * prop_l.translation, Some(rot))
            }
            None => (cam.transform_point(LEFT_REST), None),
        };
        let pole = cam.rotation * if i == 1 { POLE[1].lerp(POLE_AIMED, ads) } else { POLE[0] };
        let (elbow, end, k) = solve(s, wrist, fore_l.translation.length(), hand_l.translation.length(), pole);
        let upper_rot = Quat::from_rotation_arc(upper_rest.rotation * Vec3::Y, (elbow - s).normalize()) * upper_rest.rotation;
        let fore_rest = upper_rot * fore_l.rotation;
        let mut fore_rot = Quat::from_rotation_arc(fore_rest * Vec3::Y, (end - elbow).normalize()) * fore_rest;
        let hand_rot = hand_rot.unwrap_or(fore_rot * hand_l.rotation);
        // Half the wrist's twist goes into the forearm so the wrist doesn't pinch.
        let x = fore_rot.inverse() * hand_rot * hand_l.rotation.inverse();
        let twist = Quat::from_xyzw(0.0, x.y, 0.0, x.w);
        if twist.length() > 1e-4 {
            fore_rot = fore_rot * Quat::IDENTITY.slerp(twist.normalize(), 0.5);
        }
        let stretch = Vec3::new(SLIM, k, SLIM);
        let hand_g = Transform { translation: end, rotation: hand_rot, scale: Vec3::ONE };
        for (e, t) in [
            (upper, Transform { translation: s, rotation: upper_rot, scale: stretch }),
            (fore, Transform { translation: elbow, rotation: fore_rot, scale: stretch }),
            (hand, hand_g),
            (prop, hand_g * *prop_l),
        ] {
            if let Ok(mut g) = globals.get_mut(e) {
                *g = GlobalTransform::from(widen * t.compute_affine());
            }
        }
        // The fingers ride the moved hand, each joint on its parent.
        if let Some(f) = fingers {
            for chain in f.joints[i].chunks(3) {
                let mut parent = hand_g;
                for e in chain {
                    let Ok(local) = locals.get(*e) else { break };
                    parent = parent * *local;
                    if let Ok(mut g) = globals.get_mut(*e) {
                        *g = GlobalTransform::from(widen * parent.compute_affine());
                    }
                }
            }
        }
    }
}

/// Two-bone IK from shoulder `s` toward `wrist` with bone lengths `a` and `b`, the elbow bending
/// toward `pole`. Arms stretch up to `MAX_STRETCH` for far targets. Returns the elbow, where the
/// forearm ends, and the stretch.
pub fn solve(s: Vec3, wrist: Vec3, a: f32, b: f32, pole: Vec3) -> (Vec3, Vec3, f32) {
    let to = wrist - s;
    let d = to.length().max(1e-4);
    let n = to / d;
    let k = (d / (a + b)).clamp(1.0, MAX_STRETCH);
    let (a, b) = (a * k, b * k);
    let d = d.clamp((a - b).abs() + 1e-4, a + b);
    let along = (a * a - b * b + d * d) / (2.0 * d);
    let up = (a * a - along * along).max(0.0).sqrt();
    let side = (pole - n * pole.dot(n)).try_normalize().unwrap_or_else(|| n.any_orthonormal_vector());
    let elbow = s + n * along + side * up;
    (elbow, elbow + (s + n * d - elbow).normalize() * b, k)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ik_reaches_and_bends_toward_the_pole() {
        let s = Vec3::ZERO;
        let wrist = Vec3::new(0.1, -0.1, -0.4);
        let (elbow, end, k) = solve(s, wrist, 0.3, 0.27, Vec3::NEG_Y);
        assert!(end.distance(wrist) < 1e-4, "reaches: {end}");
        assert!((elbow.distance(s) - 0.3).abs() < 1e-4 && (end.distance(elbow) - 0.27).abs() < 1e-4, "bones keep their length");
        assert!(elbow.y < -0.1, "elbow drops toward the pole: {elbow}");
        assert_eq!(k, 1.0);
        // Too far: stretched, still pointing at the target.
        let far = Vec3::new(0.0, 0.0, -0.66);
        let (_, end, k) = solve(s, far, 0.3, 0.27, Vec3::NEG_Y);
        assert!(k > 1.0 && end.distance(far) < 1e-3, "stretches to {end}");
    }
}
