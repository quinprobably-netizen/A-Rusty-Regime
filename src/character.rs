//! Our own character: one glTF (`character.glb`, built by `tools/character/build.py`) with a shared
//! 22-bone skeleton, every clothing part as a named node, and procedural clips. A `Rig` names an
//! outfit from `assets/characters.toml`, which picks the parts that show and tints the cloth; the
//! owner of the rig sets a `RigPose` every frame and this module plays the matching clip.

use std::collections::HashMap;
use std::time::Duration;

use bevy::camera::visibility::RenderLayers;
use bevy::gltf::GltfMaterialName;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAsset, WorldAssetRoot, WorldInstanceReady};
use serde::{Deserialize, Serialize};

pub const MODEL: &str = "models/character/character.glb";
/// Height of the model in metres, origin at the feet. It faces +Z.
pub const MODEL_HEIGHT: f32 = 1.80;
/// Render layer the camera does not see but the shadow-casting light does.
pub const SHADOW_ONLY_LAYER: usize = 1;
const DATA_PATH: &str = "assets/characters.toml";
const DEFAULT_DATA: &str = include_str!("../assets/characters.toml");

/// Every toggleable node in the glb, as `slot.style`. `build.py --check` keeps the file in step.
pub const PARTS: [&str; 22] = [
    "body", "body.head",
    "head.hood", "head.beanie", "head.cap", "head.helmet",
    "face.mask", "face.goggles",
    "torso.jacket", "torso.shirt", "torso.carrier",
    "hands.gloves", "hands.bare",
    "legs.cargo", "legs.kneepads",
    "feet.boots", "feet.sneakers",
    "back.rope", "back.pack",
    "gear.launcher", "gear.chalkbag",
    "weapon.rifle",
];
const ALWAYS: [&str; 2] = ["body", "body.head"];
pub const SLOTS: [&str; 9] = ["head", "face", "torso", "hands", "legs", "feet", "back", "gear", "weapon"];
/// Slots the wardrobe lets the player change; the weapon follows the class.
pub const WEARABLE: [&str; 8] = ["head", "face", "torso", "hands", "legs", "feet", "back", "gear"];

/// The styles the model has for `slot`, in glb order.
pub fn styles_for(slot: &str) -> Vec<&'static str> {
    PARTS.iter().filter_map(|p| p.strip_prefix(slot).and_then(|r| r.strip_prefix('.'))).filter(|_| slot != "body").collect()
}

/// Parts around the head, plus the held weapon (the first-person viewmodel stands in for it).
/// The player's own go on the shadow-only layer so they never fill the screen.
pub fn is_head_part(name: &str) -> bool {
    name == "body.head" || name.starts_with("head.") || name.starts_with("face.") || name.starts_with("weapon.")
}

/// Animation clips, in the order they sit in the glb.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Pose {
    Idle,
    Walk,
    Run,
    Sprint,
    Jump,
    Fall,
    Crouch,
    Slide,
    WallRunL,
    WallRunR,
    Mantle,
    Grapple,
}

impl Pose {
    pub const ALL: [Pose; 12] = [
        Pose::Idle, Pose::Walk, Pose::Run, Pose::Sprint, Pose::Jump, Pose::Fall, Pose::Crouch,
        Pose::Slide, Pose::WallRunL, Pose::WallRunR, Pose::Mantle, Pose::Grapple,
    ];

    fn index(self) -> usize {
        Pose::ALL.iter().position(|p| *p == self).unwrap()
    }
}

// ------------------------------------------------------------------------------------------- data

/// One style or a stack of styles in a slot.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
#[serde(untagged)]
pub enum Styles {
    One(String),
    Many(Vec<String>),
}

impl Styles {
    pub fn list(&self) -> Vec<&str> {
        match self {
            Styles::One(s) => vec![s.as_str()],
            Styles::Many(v) => v.iter().map(String::as_str).collect(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
#[serde(default)]
pub struct OutfitDef {
    pub head: Option<Styles>,
    pub face: Option<Styles>,
    pub torso: Option<Styles>,
    pub hands: Option<Styles>,
    pub legs: Option<Styles>,
    pub feet: Option<Styles>,
    pub back: Option<Styles>,
    pub gear: Option<Styles>,
    pub weapon: Option<Styles>,
    pub primary: String,
    pub secondary: String,
    pub accent: String,
}

impl OutfitDef {
    pub fn slot(&self, slot: &str) -> Option<&Styles> {
        match slot {
            "head" => self.head.as_ref(),
            "face" => self.face.as_ref(),
            "torso" => self.torso.as_ref(),
            "hands" => self.hands.as_ref(),
            "legs" => self.legs.as_ref(),
            "feet" => self.feet.as_ref(),
            "back" => self.back.as_ref(),
            "gear" => self.gear.as_ref(),
            "weapon" => self.weapon.as_ref(),
            _ => None,
        }
    }

    pub fn set_slot(&mut self, slot: &str, styles: Option<Styles>) {
        let field = match slot {
            "head" => &mut self.head,
            "face" => &mut self.face,
            "torso" => &mut self.torso,
            "hands" => &mut self.hands,
            "legs" => &mut self.legs,
            "feet" => &mut self.feet,
            "back" => &mut self.back,
            "gear" => &mut self.gear,
            "weapon" => &mut self.weapon,
            _ => return,
        };
        *field = styles;
    }

    /// Node names to show, base layers before overlays.
    pub fn parts(&self) -> Vec<String> {
        let mut out: Vec<String> = ALWAYS.iter().map(|s| s.to_string()).collect();
        for slot in SLOTS {
            if let Some(styles) = self.slot(slot) {
                out.extend(styles.list().into_iter().map(|s| format!("{slot}.{s}")));
            }
        }
        out
    }

    pub fn tint(&self, material: &str) -> Option<Color> {
        match material {
            "primary" => parse_hex(&self.primary),
            "secondary" => parse_hex(&self.secondary),
            "accent" => parse_hex(&self.accent),
            _ => None,
        }
    }
}

#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct ClassDef {
    pub outfit: String,
    pub ability: String,
    pub health: f32,
    pub sprint_mult: f32,
}

impl Default for ClassDef {
    fn default() -> Self {
        Self { outfit: "runner".into(), ability: "none".into(), health: 100.0, sprint_mult: 1.0 }
    }
}

#[derive(Deserialize, Resource, Clone, Debug, Default, PartialEq)]
#[serde(default)]
pub struct Characters {
    pub outfit: HashMap<String, OutfitDef>,
    pub class: HashMap<String, ClassDef>,
}

impl Characters {
    pub fn parse(text: &str) -> Result<Self, toml::de::Error> {
        toml::from_str(text)
    }

    /// `assets/characters.toml` if it is there and valid, else the copy baked into the binary.
    pub fn load() -> Self {
        let baked = Self::parse(DEFAULT_DATA).expect("baked characters.toml parses");
        match std::fs::read_to_string(DATA_PATH) {
            Ok(text) => match Self::parse(&text) {
                Ok(c) => {
                    for p in c.problems() {
                        warn!("{DATA_PATH}: {p}");
                    }
                    c
                }
                Err(e) => {
                    warn!("{DATA_PATH} is invalid, using the built-in outfits: {e}");
                    baked
                }
            },
            Err(_) => baked,
        }
    }

    /// Unknown parts, outfits and colours. Empty means the file is consistent with the glb.
    pub fn problems(&self) -> Vec<String> {
        let mut out = vec![];
        for (name, outfit) in &self.outfit {
            for part in outfit.parts() {
                if !PARTS.contains(&part.as_str()) {
                    out.push(format!("outfit {name}: no part named {part}"));
                }
            }
            for m in ["primary", "secondary", "accent"] {
                if outfit.tint(m).is_none() {
                    out.push(format!("outfit {name}: {m} is not a #rrggbb colour"));
                }
            }
        }
        for (name, class) in &self.class {
            if !self.outfit.contains_key(&class.outfit) {
                out.push(format!("class {name}: no outfit named {}", class.outfit));
            }
        }
        out
    }
}

pub fn parse_hex(s: &str) -> Option<Color> {
    let s = s.strip_prefix('#')?;
    if s.len() != 6 {
        return None;
    }
    let v = u32::from_str_radix(s, 16).ok()?;
    Some(Color::srgb_u8((v >> 16) as u8, (v >> 8) as u8, v as u8))
}

// ------------------------------------------------------------------------------------------- ecs

/// glTF handles and the shared animation graph; absent in headless tests.
#[derive(Resource)]
pub struct CharacterAssets {
    pub scene: Handle<WorldAsset>,
    graph: Handle<AnimationGraph>,
    nodes: [AnimationNodeIndex; 12],
}

/// A spawned character model wearing `outfit`.
#[derive(Component)]
pub struct Rig {
    pub outfit: String,
    pose: Option<Pose>,
    /// The glTF's `AnimationPlayer`, once the model has spawned.
    player: Option<Entity>,
    dressed: bool,
}

impl Rig {
    pub fn new(outfit: &str) -> Self {
        Self { outfit: outfit.into(), pose: None, player: None, dressed: false }
    }

    /// Change clothes; applied on the next frame.
    pub fn wear(&mut self, outfit: &str) {
        if self.outfit != outfit {
            self.outfit = outfit.into();
        }
        self.dressed = false;
    }
}

/// What the rig's owner wants played this frame.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct RigPose {
    pub pose: Pose,
    pub rate: f32,
}

impl Default for RigPose {
    fn default() -> Self {
        Self { pose: Pose::Idle, rate: 1.0 }
    }
}

/// The player's own rig: head parts render only into shadow maps.
#[derive(Component)]
pub struct FirstPerson;

/// Everything a character model needs; add `FirstPerson` for the player's own.
pub fn bundle(assets: &CharacterAssets, outfit: &str, transform: Transform) -> impl Bundle {
    (Rig::new(outfit), RigPose::default(), WorldAssetRoot(assets.scene.clone()), transform, Visibility::default())
}

pub struct CharacterPlugin;

impl Plugin for CharacterPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Characters::load())
            .add_systems(PreStartup, load)
            .add_systems(Update, (reload.run_if(resource_exists::<ButtonInput<KeyCode>>), dress, animate).chain())
            .add_observer(on_ready);
    }
}

fn load(mut commands: Commands, server: Res<AssetServer>, graphs: Option<ResMut<Assets<AnimationGraph>>>) {
    // No render assets in headless tests: no models.
    let Some(mut graphs) = graphs else { return };
    let clips = Pose::ALL.map(|p| server.load(GltfAssetLabel::Animation(p.index()).from_asset(MODEL)));
    let (graph, nodes) = AnimationGraph::from_clips(clips);
    commands.insert_resource(CharacterAssets {
        scene: server.load(GltfAssetLabel::Scene(0).from_asset(MODEL)),
        graph: graphs.add(graph),
        nodes: nodes.try_into().expect("one node per pose"),
    });
}

fn reload(keys: Res<ButtonInput<KeyCode>>, mut data: ResMut<Characters>, mut rigs: Query<&mut Rig>) {
    if keys.just_pressed(KeyCode::F5) {
        *data = Characters::load();
        for mut rig in &mut rigs {
            rig.dressed = false;
        }
        info!("Reloaded {DATA_PATH}");
    }
}

/// Hook up the animation player; the rig is dressed on the next `dress` run.
fn on_ready(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    mut rigs: Query<&mut Rig>,
    assets: Option<Res<CharacterAssets>>,
    children: Query<&Children>,
    players: Query<(), With<AnimationPlayer>>,
) {
    let (Ok(mut rig), Some(assets)) = (rigs.get_mut(ready.entity), assets) else { return };
    for e in children.iter_descendants(ready.entity) {
        if players.contains(e) {
            rig.player = Some(e);
            commands.entity(e).insert((AnimationGraphHandle(assets.graph.clone()), AnimationTransitions::new()));
        }
    }
    rig.dressed = false;
}

/// Show the outfit's parts, hide the rest, tint the cloth. Runs once per rig and again after F5.
fn dress(
    mut commands: Commands,
    data: Res<Characters>,
    mut rigs: Query<(Entity, &mut Rig, Has<FirstPerson>)>,
    children: Query<&Children>,
    names: Query<&Name>,
    material_names: Query<&GltfMaterialName>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
) {
    for (entity, mut rig, first_person) in &mut rigs {
        if rig.dressed || rig.player.is_none() {
            continue;
        }
        rig.dressed = true;
        let Some(outfit) = data.outfit.get(&rig.outfit) else {
            warn!("no outfit named {}", rig.outfit);
            continue;
        };
        let parts = outfit.parts();
        let mut tints: HashMap<&str, Handle<StandardMaterial>> = HashMap::new();
        for e in children.iter_descendants(entity) {
            if let Ok(name) = names.get(e)
                && PARTS.contains(&name.as_str())
            {
                let shown = parts.iter().any(|p| p == name.as_str());
                commands.entity(e).insert(if shown { Visibility::Inherited } else { Visibility::Hidden });
                if first_person && is_head_part(name.as_str()) {
                    for e in std::iter::once(e).chain(children.iter_descendants(e)) {
                        commands.entity(e).insert(RenderLayers::layer(SHADOW_ONLY_LAYER));
                    }
                }
            }
            if let (Ok(mat), Some(materials)) = (material_names.get(e), materials.as_mut())
                && let Some(color) = outfit.tint(&mat.0)
            {
                let handle = tints.entry(["primary", "secondary", "accent"].iter().find(|m| **m == mat.0).unwrap()).or_insert_with(|| {
                    materials.add(StandardMaterial { base_color: color, perceptual_roughness: 0.85, ..default() })
                });
                commands.entity(e).insert(MeshMaterial3d(handle.clone()));
            }
        }
    }
}

fn animate(
    assets: Option<Res<CharacterAssets>>,
    mut rigs: Query<(&mut Rig, &RigPose)>,
    mut anims: Query<(&mut AnimationPlayer, &mut AnimationTransitions)>,
) {
    let Some(assets) = assets else { return };
    for (mut rig, want) in &mut rigs {
        let Some(e) = rig.player else { continue };
        let Ok((mut anim, mut transitions)) = anims.get_mut(e) else { continue };
        let node = assets.nodes[want.pose.index()];
        if rig.pose != Some(want.pose) {
            rig.pose = Some(want.pose);
            transitions.play(&mut anim, node, Duration::from_millis(150)).repeat();
        }
        if let Some(a) = anim.animation_mut(node) {
            a.set_speed(want.rate);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn baked_outfits_match_the_model() {
        let c = Characters::parse(DEFAULT_DATA).unwrap();
        assert!(c.problems().is_empty(), "{:?}", c.problems());
        assert!(c.outfit.contains_key("runner") && c.class.contains_key("pilot"));
    }

    #[test]
    fn outfit_parts_keep_layer_order() {
        let c = Characters::parse(DEFAULT_DATA).unwrap();
        let parts = c.outfit["runner"].parts();
        assert_eq!(&parts[..2], &["body", "body.head"]);
        let jacket = parts.iter().position(|p| p == "torso.jacket").unwrap();
        let carrier = parts.iter().position(|p| p == "torso.carrier").unwrap();
        assert!(jacket < carrier);
        assert!(parts.contains(&"gear.launcher".to_string()));
        assert!(!c.outfit["soldier"].parts().contains(&"gear.launcher".to_string()));
    }

    #[test]
    fn problems_are_reported() {
        let c = Characters::parse("[outfit.x]\nhead = \"crown\"\nprimary = \"red\"\n[class.y]\noutfit = \"nope\"").unwrap();
        let p = c.problems();
        assert!(p.iter().any(|m| m.contains("head.crown")));
        assert!(p.iter().any(|m| m.contains("primary")));
        assert!(p.iter().any(|m| m.contains("class y")));
    }

    #[test]
    fn styles_per_slot() {
        assert_eq!(styles_for("head"), vec!["hood", "beanie", "cap", "helmet"]);
        assert_eq!(styles_for("hands"), vec!["gloves", "bare"]);
        assert_eq!(styles_for("weapon"), vec!["rifle"]);
        assert!(is_head_part("weapon.rifle") && !is_head_part("torso.jacket"));
        assert!(styles_for("body").is_empty());
        let mut o = OutfitDef::default();
        o.set_slot("feet", Some(Styles::One("boots".into())));
        assert_eq!(o.parts(), vec!["body", "body.head", "feet.boots"]);
    }

    #[test]
    fn hex_colours() {
        assert_eq!(parse_hex("#ff0000"), Some(Color::srgb_u8(255, 0, 0)));
        assert_eq!(parse_hex("ff0000"), None);
        assert_eq!(parse_hex("#fff"), None);
    }
}
