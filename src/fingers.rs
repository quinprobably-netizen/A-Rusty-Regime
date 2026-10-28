//! Fingers on the held weapon. `tools/character/grips.py` solves, for every character and weapon, how
//! each finger wraps that gun's real grip, the right index on its trigger and the left hand round
//! the handguard or the fitted foregrip, and writes `assets/models/character/<id>.grips.toml` with
//! where each palm frame sits on the gun. Every frame, after the clips, the finger joints of each
//! armed rig take their weapon's pose (each joint's rest rotation times the solved one); `arms`
//! puts the first-person palms on the same frames. The player's trigger finger pulls on each shot.
//! A character or weapon with no solved pose keeps the open, relaxed rest hand the rigs are built
//! with.

use std::collections::HashMap;

use bevy::app::AnimationSystems;
use bevy::prelude::*;
use serde::Deserialize;

use crate::character::{ArmsOnly, CHARACTERS, FirstPerson, Rig};
use crate::gunsmith::{Loadout, customizable};
use crate::weapon::{Arsenal, WeaponFired, WeaponKind};

pub const FINGERS: [&str; 5] = ["thumb", "index", "middle", "ring", "pinky"];
/// How long the trigger finger stays pulled after a shot (seconds).
const PULL_TIME: f32 = 0.07;

pub struct FingersPlugin;

impl Plugin for FingersPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Solved::load())
            .init_resource::<Trigger>()
            .add_systems(Update, pull)
            .add_systems(PostUpdate, pose.after(AnimationSystems).before(TransformSystems::Propagate));
    }
}

/// One hand on one weapon: where the grip frame sits in weapon space, how it is turned, and each
/// finger joint's rotation over the rest fist (thumb to pinky, root to tip).
#[derive(Clone, Debug, PartialEq)]
pub struct HandPose {
    pub at: Vec3,
    pub rot: Quat,
    pub joints: [Quat; 15],
}

#[derive(Deserialize)]
struct PoseDef {
    at: [f32; 3],
    rot: [f32; 4],
    thumb: [[f32; 4]; 3],
    index: [[f32; 4]; 3],
    middle: [[f32; 4]; 3],
    ring: [[f32; 4]; 3],
    pinky: [[f32; 4]; 3],
}

/// Every character's solved poses, keyed `<weapon id>.<pose>` (pose `R`, `R_fire`, `L`,
/// `L_vertical`, `L_angled`).
#[derive(Resource, Default)]
pub struct Solved(pub HashMap<String, HashMap<String, HandPose>>);

impl Solved {
    fn load() -> Self {
        let mut all = HashMap::new();
        for id in CHARACTERS {
            let path = format!("assets/models/character/{id}.grips.toml");
            let Ok(text) = std::fs::read_to_string(&path) else { continue };
            match parse(&text) {
                Ok(poses) => {
                    all.insert(id.to_string(), poses);
                }
                Err(e) => warn!("{path}: {e}"),
            }
        }
        Solved(all)
    }

    pub fn get(&self, character: &str, kind: WeaponKind, pose: &str) -> Option<&HandPose> {
        let poses = self.0.get(character)?;
        // The knife sits in the pistol grip's place, so a character with no solved knife hold yet
        // takes the pistol's; one with its own never borrows the pistol's trigger finger.
        let own = poses.get(&format!("{}.{pose}", kind.id()));
        if kind == WeaponKind::Knife && !poses.contains_key("knife.R") { poses.get(&format!("pistol.{pose}")) } else { own }
    }
}

pub fn parse(text: &str) -> Result<HashMap<String, HandPose>, toml::de::Error> {
    let defs: HashMap<String, PoseDef> = toml::from_str(text)?;
    let q = |v: [f32; 4]| Quat::from_array(v).normalize();
    Ok(defs
        .into_iter()
        .map(|(key, d)| {
            let mut joints = [Quat::IDENTITY; 15];
            for (f, chain) in [d.thumb, d.index, d.middle, d.ring, d.pinky].into_iter().enumerate() {
                for (i, v) in chain.into_iter().enumerate() {
                    joints[f * 3 + i] = q(v);
                }
            }
            (key, HandPose { at: Vec3::from_array(d.at), rot: q(d.rot), joints })
        })
        .collect())
}

/// The support hand's pose for `kind` with the gunsmith's grip part fitted.
pub fn left_pose(kind: WeaponKind, loadout: Option<&Loadout>) -> &'static str {
    let part = loadout.filter(|_| customizable(kind)).map_or(0, |l| l.part(kind, 2));
    match part {
        1 => "L_vertical",
        2 => "L_angled",
        _ => "L",
    }
}

/// The player's trigger finger: 1 just after a shot, easing back to 0.
#[derive(Resource, Default)]
pub struct Trigger(pub f32);

fn pull(time: Res<Time>, mut fired: MessageReader<WeaponFired>, mut trigger: ResMut<Trigger>) {
    trigger.0 = (trigger.0 - time.delta_secs() / PULL_TIME).max(0.0);
    if fired.read().count() > 0 {
        trigger.0 = 1.0;
    }
}

/// A rig model's finger joints, right hand then left, with their rest rotations.
#[derive(Component)]
pub struct FingerBones {
    model: Entity,
    pub joints: [[Entity; 15]; 2],
    rest: [[Quat; 15]; 2],
}

/// The 15 finger joints of `side` ("R" or "L"), thumb to pinky, root to tip, under `root`.
pub fn find_joints(root: Entity, side: &str, children: &Query<&Children>, names: &Query<&Name>) -> Option<[Entity; 15]> {
    let mut out = [Entity::PLACEHOLDER; 15];
    for (f, finger) in FINGERS.iter().enumerate() {
        for i in 0..3 {
            let want = format!("f_{finger}.{}.{side}", i + 1);
            out[f * 3 + i] = children.iter_descendants(root).find(|e| names.get(*e).is_ok_and(|n| n.as_str() == want))?;
        }
    }
    Some(out)
}

/// Joint rotations for one hand: the pose over each rest rotation, or the rest fist without one.
/// `fire` blends the index finger toward its pulled pose by `pull`.
pub fn hand_rotations(rest: &[Quat; 15], pose: Option<&HandPose>, fire: Option<&HandPose>, pull: f32) -> [Quat; 15] {
    let mut out = *rest;
    if let Some(p) = pose {
        for (i, q) in out.iter_mut().enumerate() {
            let mut d = p.joints[i];
            if let Some(f) = fire
                && (3..6).contains(&i)
            {
                d = d.slerp(f.joints[i], pull);
            }
            *q = rest[i] * d;
        }
    }
    out
}

#[allow(clippy::too_many_arguments)]
fn pose(
    mut commands: Commands,
    solved: Res<Solved>,
    trigger: Res<Trigger>,
    arsenal: Option<Res<Arsenal>>,
    loadout: Option<Res<Loadout>>,
    rigs: Query<(Entity, &Rig, Has<ArmsOnly>, Has<FirstPerson>, Option<&FingerBones>)>,
    children: Query<&Children>,
    names: Query<&Name>,
    mut transforms: Query<&mut Transform>,
) {
    for (entity, rig, arms_only, first_person, bones) in &rigs {
        let Some(root) = rig.model() else { continue };
        let Some(bones) = bones.filter(|b| b.model == root) else {
            if let (Some(r), Some(l)) = (find_joints(root, "R", &children, &names), find_joints(root, "L", &children, &names)) {
                let rest = |js: &[Entity; 15]| js.map(|e| transforms.get(e).map_or(Quat::IDENTITY, |t| t.rotation));
                commands.entity(entity).insert(FingerBones { model: root, rest: [rest(&r), rest(&l)], joints: [r, l] });
            }
            continue;
        };
        // The first-person arms hold the current weapon; everyone else what their rig carries.
        let kind = if arms_only { arsenal.as_ref().map(|a| a.kind()) } else { rig.weapon };
        let character = rig.character();
        let get = |p: &str| kind.zip(character).and_then(|(k, c)| solved.get(c, k, p));
        let ours = arms_only || first_person;
        // The player's support hand follows the foregrip the gunsmith fitted; everyone else's the bare gun.
        let left = kind.map_or("L", |k| if ours { left_pose(k, loadout.as_deref()) } else { "L" });
        let sides = [
            hand_rotations(&bones.rest[0], get("R"), get("R_fire").filter(|_| ours), trigger.0),
            hand_rotations(&bones.rest[1], get(left).or_else(|| get("L")), None, 0.0),
        ];
        for (s, rots) in sides.iter().enumerate() {
            for (i, e) in bones.joints[s].iter().enumerate() {
                if let Ok(mut t) = transforms.get_mut(*e)
                    && t.rotation != rots[i]
                {
                    t.rotation = rots[i];
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"
["rifle.R"]
at = [0.0, -0.04, 0.03]
rot = [-0.70711, 0.0, 0.0, 0.70711]
thumb = [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0]]
index = [[0.1, 0.0, 0.0, 0.99499], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0]]
middle = [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0]]
ring = [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0]]
pinky = [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 2.0]]
"#;

    #[test]
    fn parses_solved_grips() {
        let poses = parse(SAMPLE).unwrap();
        let p = &poses["rifle.R"];
        assert_eq!(p.at, Vec3::new(0.0, -0.04, 0.03));
        assert!((p.rot * Vec3::Y).distance(Vec3::NEG_Z) < 1e-3, "frame +Y runs down the barrel");
        assert!((p.joints[3].x - 0.1).abs() < 1e-4, "index root");
        assert!((p.joints[14].length() - 1.0).abs() < 1e-5, "normalised");
    }

    #[test]
    fn the_knife_borrows_the_pistol_hand_only_until_it_has_its_own() {
        let pose = |at: f32| HandPose { at: Vec3::splat(at), rot: Quat::IDENTITY, joints: [Quat::IDENTITY; 15] };
        let mut poses = HashMap::from([("pistol.R".to_string(), pose(1.0)), ("pistol.R_fire".to_string(), pose(2.0))]);
        let mut solved = Solved::default();
        solved.0.insert("runner".into(), poses.clone());
        assert_eq!(solved.get("runner", WeaponKind::Knife, "R").unwrap().at, Vec3::splat(1.0));
        poses.insert("knife.R".into(), pose(3.0));
        solved.0.insert("runner".into(), poses);
        assert_eq!(solved.get("runner", WeaponKind::Knife, "R").unwrap().at, Vec3::splat(3.0));
        assert!(solved.get("runner", WeaponKind::Knife, "R_fire").is_none(), "no trigger finger on a knife");
    }

    #[test]
    fn missing_pose_falls_back_to_rest() {
        let rest = [Quat::from_rotation_x(0.3); 15];
        assert_eq!(hand_rotations(&rest, None, None, 1.0), rest);
        let solved = Solved::default();
        assert!(solved.get("runner", WeaponKind::Rifle, "R").is_none());
    }

    #[test]
    fn trigger_pull_moves_only_the_index() {
        let rest = [Quat::IDENTITY; 15];
        let pose = HandPose { at: Vec3::ZERO, rot: Quat::IDENTITY, joints: [Quat::IDENTITY; 15] };
        let fire = HandPose { joints: [Quat::from_rotation_x(0.4); 15], ..pose.clone() };
        let r = hand_rotations(&rest, Some(&pose), Some(&fire), 1.0);
        assert!(r[4].angle_between(Quat::from_rotation_x(0.4)) < 1e-4);
        assert_eq!(r[0], Quat::IDENTITY);
        assert_eq!(r[6], Quat::IDENTITY);
    }

    #[test]
    fn support_hand_follows_the_foregrip() {
        let mut l = Loadout::default();
        assert_eq!(left_pose(WeaponKind::Rifle, Some(&l)), "L");
        l.cycle(WeaponKind::Rifle, 2, 1);
        assert_eq!(left_pose(WeaponKind::Rifle, Some(&l)), "L_vertical");
        l.cycle(WeaponKind::Rifle, 2, 1);
        assert_eq!(left_pose(WeaponKind::Rifle, Some(&l)), "L_angled");
        assert_eq!(left_pose(WeaponKind::Rifle, None), "L");
    }

    #[test]
    fn shipped_grip_files_parse() {
        for id in CHARACTERS {
            if let Ok(text) = std::fs::read_to_string(format!("assets/models/character/{id}.grips.toml")) {
                let poses = parse(&text).unwrap_or_else(|e| panic!("{id}: {e}"));
                assert!(poses.contains_key("rifle.R") && poses.contains_key("rifle.L"), "{id}");
                assert!(poses.contains_key("knife.R"), "{id} has no solved knife hold");
            }
        }
    }
}
