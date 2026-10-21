//! Our characters: one skinned glTF per character (`models/character/<id>.glb`, built by
//! `tools/character`), all on the same 22-bone skeleton names with the same twelve clips, each with
//! its own body and proportions. `assets/characters.toml` holds every character's faction, default
//! colours and bot loadout, the factions, which factions each team draws from, and the classes. A
//! `Rig` wears an outfit (a character plus three colours); the owner sets a `RigPose` every frame and
//! this module plays the matching clip, tints the cloth and hangs the held weapon in the right hand.

use std::collections::HashMap;
use std::time::Duration;

use bevy::asset::LoadState;
use bevy::camera::visibility::{NoFrustumCulling, RenderLayers};
use bevy::gltf::GltfMaterialName;
use bevy::prelude::*;
use bevy::world_serialization::{WorldAsset, WorldAssetRoot, WorldInstanceReady};
use serde::{Deserialize, Serialize};

use crate::weapon::{WEAPONS, WeaponKind};

/// The roster, faction by faction. Every id has `models/character/<id>.glb`.
pub const CHARACTERS: [&str; 12] = [
    "acolyte", "zealot", "choir", "mechanic", "bruiser", "trapper", "runner", "breaker", "ghost", "contractor", "juggernaut", "handler",
];
/// Height of the reference build in metres, origin at the feet. Models face +Z. Characters are
/// taller or shorter than this; all are scaled by the same factor so their heights stay true.
pub const MODEL_HEIGHT: f32 = 1.80;
/// Render layer the camera does not see but the shadow-casting light does.
pub const SHADOW_ONLY_LAYER: usize = 1;
const DATA_PATH: &str = "assets/characters.toml";
const DEFAULT_DATA: &str = include_str!("../assets/characters.toml");
/// The skinned meshes in every character glb.
pub const MESHES: [&str; 3] = ["mesh.body", "mesh.head", "mesh.arms"];
/// The right hand's grip frame: the held weapon hangs here.
pub const GRIP_R: &str = "prop_hand.R";
pub const GRIP_L: &str = "prop_hand.L";

pub fn model_path(id: &str) -> String {
    format!("models/character/{id}.glb")
}

/// Animation clips, in the order they sit in every glb.
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

/// Where a weapon model's hands go, in the weapon's glTF space (-Z down the barrel, +Y up, the
/// trigger at the origin): the right fist's centre, and the support hand's (with the bone it rides,
/// like the shotgun's pump) for weapons held in two hands. Each grip frame in the character rig
/// points down the barrel with the weapon's up as its Z, so only the points are needed.
pub struct Hands {
    pub right: Vec3,
    pub left: Option<(Vec3, &'static str)>,
}

pub fn hands(kind: WeaponKind) -> Hands {
    let two = |r: Vec3, l: Vec3| Hands { right: r, left: Some((l, "root")) };
    match kind {
        WeaponKind::Rifle => two(Vec3::new(0.0, -0.038, 0.030), Vec3::new(0.0, 0.03, -0.20)),
        WeaponKind::Shotgun => Hands { right: Vec3::new(0.0, -0.085, 0.068), left: Some((Vec3::new(0.0, 0.0, -0.30), "pump")) },
        WeaponKind::Pistol => Hands { right: Vec3::new(0.0, -0.05, 0.055), left: None },
        WeaponKind::Smg => two(Vec3::new(0.0, -0.05, 0.045), Vec3::new(0.0, 0.03, -0.15)),
        WeaponKind::Dmr => two(Vec3::new(0.0, -0.045, 0.03), Vec3::new(0.0, 0.025, -0.28)),
        WeaponKind::Revolver => Hands { right: Vec3::new(0.0, -0.058, 0.045), left: None },
        WeaponKind::Grenade => two(Vec3::new(0.0, -0.04, 0.035), Vec3::new(0.0, 0.02, -0.16)),
        WeaponKind::Harpoon => two(Vec3::new(0.0, -0.04, 0.03), Vec3::new(0.0, 0.02, -0.25)),
        WeaponKind::RocketLauncher => two(Vec3::new(0.0, -0.03, 0.03), Vec3::new(0.0, -0.05, -0.28)),
        WeaponKind::Fist => Hands { right: Vec3::ZERO, left: None },
    }
}

/// Weapon space to grip-frame space: the barrel (-Z) runs down the frame's +Y, up (+Y) along its +Z.
pub fn grip_rotation() -> Quat {
    Quat::from_rotation_x(std::f32::consts::FRAC_PI_2)
}

/// Where a weapon model sits under the right grip frame so its grip lands in the fist.
pub fn held_transform(kind: WeaponKind) -> Transform {
    let rot = grip_rotation();
    Transform { translation: -(rot * hands(kind).right), rotation: rot, scale: Vec3::ONE }
}

// ------------------------------------------------------------------------------------------- data

/// What a rig wears: a character and its three cloth colours.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
#[serde(default)]
pub struct OutfitDef {
    pub character: String,
    pub primary: String,
    pub secondary: String,
    pub accent: String,
}

impl OutfitDef {
    pub fn tint(&self, material: &str) -> Option<Color> {
        match material {
            "primary" => parse_hex(&self.primary),
            "secondary" => parse_hex(&self.secondary),
            "accent" => parse_hex(&self.accent),
            _ => None,
        }
    }
}

#[derive(Deserialize, Clone, Debug, Default, PartialEq)]
#[serde(default)]
pub struct CharacterDef {
    pub name: String,
    pub faction: String,
    pub primary: String,
    pub secondary: String,
    pub accent: String,
    /// The weapon bots wearing this character carry.
    pub loadout: String,
}

#[derive(Deserialize, Clone, Debug, Default, PartialEq)]
#[serde(default)]
pub struct FactionDef {
    pub name: String,
    pub characters: Vec<String>,
}

#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct ClassDef {
    pub character: String,
    pub ability: String,
    pub health: f32,
    pub sprint_mult: f32,
}

impl Default for ClassDef {
    fn default() -> Self {
        Self { character: "runner".into(), ability: "none".into(), health: 100.0, sprint_mult: 1.0 }
    }
}

#[derive(Deserialize, Resource, Clone, Debug, Default, PartialEq)]
#[serde(default)]
pub struct Characters {
    pub character: HashMap<String, CharacterDef>,
    pub faction: HashMap<String, FactionDef>,
    /// Factions each team draws its soldiers from, by team number ("0" is the player's side).
    pub teams: HashMap<String, Vec<String>>,
    pub class: HashMap<String, ClassDef>,
    /// Outfits made in the wardrobe, by name (not in the file).
    #[serde(skip)]
    pub custom: HashMap<String, OutfitDef>,
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
                    warn!("{DATA_PATH} is invalid, using the built-in roster: {e}");
                    baked
                }
            },
            Err(_) => baked,
        }
    }

    /// A character's own outfit in its default colours.
    pub fn default_outfit(&self, id: &str) -> Option<OutfitDef> {
        let c = self.character.get(id)?;
        Some(OutfitDef { character: id.into(), primary: c.primary.clone(), secondary: c.secondary.clone(), accent: c.accent.clone() })
    }

    /// The outfit called `name`: a wardrobe outfit, else a character's default.
    pub fn outfit(&self, name: &str) -> Option<OutfitDef> {
        self.custom.get(name).cloned().filter(|o| self.character.contains_key(&o.character)).or_else(|| self.default_outfit(name))
    }

    /// A character for a soldier on `team`; `seed` spreads soldiers over the team's factions and
    /// their characters.
    pub fn for_team(&self, team: u8, seed: u32) -> Option<&str> {
        let factions = self.teams.get(&team.to_string())?;
        let pool: Vec<&String> = factions.iter().filter_map(|f| self.faction.get(f)).flat_map(|f| f.characters.iter()).collect();
        if pool.is_empty() {
            return None;
        }
        let h = seed.wrapping_mul(2654435761).rotate_left(13);
        Some(pool[h as usize % pool.len()].as_str())
    }

    /// "Runner / Deserters", for the wardrobe.
    pub fn label(&self, id: &str) -> String {
        let Some(c) = self.character.get(id) else { return id.to_string() };
        let faction = self.faction.get(&c.faction).map_or(c.faction.as_str(), |f| f.name.as_str());
        format!("{} / {}", c.name, faction)
    }

    pub fn loadout(&self, id: &str) -> Option<WeaponKind> {
        let w = &self.character.get(id)?.loadout;
        WEAPONS.iter().copied().find(|k| k.id() == w)
    }

    /// Unknown characters, factions, weapons and colours. Empty means the file matches the roster.
    pub fn problems(&self) -> Vec<String> {
        let mut out = vec![];
        for id in CHARACTERS {
            if !self.character.contains_key(id) {
                out.push(format!("character {id} is missing"));
            }
        }
        for (id, c) in &self.character {
            if !CHARACTERS.contains(&id.as_str()) {
                out.push(format!("character {id}: no model for it"));
            }
            if !self.faction.contains_key(&c.faction) {
                out.push(format!("character {id}: no faction named {}", c.faction));
            }
            if !WEAPONS.iter().any(|k| k.id() == c.loadout) {
                out.push(format!("character {id}: no weapon named {}", c.loadout));
            }
            for (m, hex) in [("primary", &c.primary), ("secondary", &c.secondary), ("accent", &c.accent)] {
                if parse_hex(hex).is_none() {
                    out.push(format!("character {id}: {m} is not a #rrggbb colour"));
                }
            }
        }
        for (name, f) in &self.faction {
            for id in &f.characters {
                if !self.character.contains_key(id) {
                    out.push(format!("faction {name}: no character named {id}"));
                }
            }
        }
        for (team, factions) in &self.teams {
            for f in factions {
                if !self.faction.contains_key(f) {
                    out.push(format!("team {team}: no faction named {f}"));
                }
            }
        }
        for (name, class) in &self.class {
            if !self.character.contains_key(&class.character) {
                out.push(format!("class {name}: no character named {}", class.character));
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

/// One character's scene and animation graph.
pub struct Model {
    pub scene: Handle<WorldAsset>,
    graph: Handle<AnimationGraph>,
    nodes: [AnimationNodeIndex; 12],
}

/// glTF handles for every character and held weapon; absent in headless tests.
///
/// Characters load one at a time (`stream`): each has three textures, which Bevy's glTF loader
/// decodes in a task scope that runs other pending loads on the same thread, so twelve at once
/// nest twelve deep and overflow the IO thread's stack.
#[derive(Resource)]
pub struct CharacterAssets {
    pub models: HashMap<&'static str, Model>,
    weapons: HashMap<WeaponKind, Handle<WorldAsset>>,
    /// Characters not started yet, next first.
    queue: Vec<&'static str>,
}

/// A character model wearing the outfit called `outfit` (or, for a soldier, one picked for its team),
/// optionally holding `weapon` in its right hand.
#[derive(Component)]
pub struct Rig {
    pub outfit: String,
    /// Soldiers: pick the character from this team's factions, and hold its loadout.
    pub team: Option<u8>,
    pub weapon: Option<WeaponKind>,
    /// The character whose scene is spawned, and that scene's entity.
    character: Option<String>,
    model: Option<Entity>,
    pose: Option<Pose>,
    /// The glTF's `AnimationPlayer`, once the model has spawned.
    player: Option<Entity>,
    held: Option<(WeaponKind, Entity)>,
    dressed: bool,
}

impl Rig {
    pub fn new(outfit: &str) -> Self {
        Self { outfit: outfit.into(), team: None, weapon: None, character: None, model: None, pose: None, player: None, held: None, dressed: false }
    }

    /// A soldier of `team`, dressed and armed from the roster.
    pub fn team(team: u8) -> Self {
        Self { team: Some(team), ..Self::new("") }
    }

    /// Change clothes; applied on the next frame.
    pub fn wear(&mut self, outfit: &str) {
        self.outfit = outfit.into();
        self.dressed = false;
    }

    /// The model's root entity, once spawned.
    pub fn model(&self) -> Option<Entity> {
        self.model.filter(|_| self.player.is_some())
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

/// The player's own rig: head, arms and held weapon render only into shadow maps (the first-person
/// arms and viewmodel stand in for them).
#[derive(Component)]
pub struct FirstPerson;

/// A rig that shows only its arms: the first-person arms (see `arms`). Not animated or armed.
#[derive(Component)]
pub struct ArmsOnly;

/// The spawned character scene under a `Rig`.
#[derive(Component)]
struct RigModel;

/// The weapon model in a rig's hand.
#[derive(Component)]
struct Held {
    first_person: bool,
}

/// Everything a character model needs; add `FirstPerson` for the player's own.
pub fn bundle(outfit: &str, transform: Transform) -> impl Bundle {
    (Rig::new(outfit), RigPose::default(), transform, Visibility::default())
}

pub struct CharacterPlugin;

impl Plugin for CharacterPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Characters::load())
            .add_systems(PreStartup, load)
            .add_systems(Update, (reload.run_if(resource_exists::<ButtonInput<KeyCode>>), stream, dress, hold, animate).chain())
            .add_observer(on_ready)
            .add_observer(on_held_ready);
    }
}

fn load(mut commands: Commands, server: Res<AssetServer>, graphs: Option<Res<Assets<AnimationGraph>>>) {
    // No render assets in headless tests: no models.
    if graphs.is_none() {
        return;
    }
    let weapons = WEAPONS.iter().map(|k| (*k, server.load(GltfAssetLabel::Scene(0).from_asset(format!("models/weapons/{}.glb", k.id()))))).collect();
    commands.insert_resource(CharacterAssets { models: HashMap::new(), weapons, queue: CHARACTERS.to_vec() });
}

/// Start the next character's load once the last one is in, sooner for characters a rig is
/// waiting on.
fn stream(server: Res<AssetServer>, assets: Option<ResMut<CharacterAssets>>, mut graphs: Option<ResMut<Assets<AnimationGraph>>>, data: Res<Characters>, rigs: Query<&Rig>) {
    let (Some(mut assets), Some(graphs)) = (assets, graphs.as_mut()) else { return };
    let busy = assets.models.values().any(|m| !matches!(server.load_state(&m.scene), LoadState::Loaded | LoadState::Failed(_)));
    if busy || assets.queue.is_empty() {
        return;
    }
    let wanted = |id: &&str| rigs.iter().any(|r| r.team.is_none() && data.outfit(&r.outfit).is_some_and(|o| o.character == *id));
    let at = assets.queue.iter().position(wanted).unwrap_or(0);
    let id = assets.queue.remove(at);
    let path = model_path(id);
    let clips = Pose::ALL.map(|p| server.load(GltfAssetLabel::Animation(p.index()).from_asset(path.clone())));
    let (graph, nodes) = AnimationGraph::from_clips(clips);
    let model = Model { scene: server.load(GltfAssetLabel::Scene(0).from_asset(path)), graph: graphs.add(graph), nodes: nodes.try_into().expect("one node per pose") };
    assets.models.insert(id, model);
}

fn reload(keys: Res<ButtonInput<KeyCode>>, mut data: ResMut<Characters>, mut rigs: Query<&mut Rig>) {
    if keys.just_pressed(KeyCode::F5) {
        let custom = std::mem::take(&mut data.custom);
        *data = Characters::load();
        data.custom = custom;
        for mut rig in &mut rigs {
            rig.dressed = false;
        }
        info!("Reloaded {DATA_PATH}");
    }
}

/// Hook up the animation player once a rig's model has spawned; it is dressed on the next `dress`.
#[allow(clippy::too_many_arguments)]
fn on_ready(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    models: Query<&ChildOf, With<RigModel>>,
    mut rigs: Query<(&mut Rig, Has<ArmsOnly>)>,
    assets: Option<Res<CharacterAssets>>,
    children: Query<&Children>,
    players: Query<(), With<AnimationPlayer>>,
) {
    let Ok(parent) = models.get(ready.entity) else { return };
    let (Ok((mut rig, arms_only)), Some(assets)) = (rigs.get_mut(parent.parent()), assets) else { return };
    if rig.model != Some(ready.entity) {
        return;
    }
    let Some(model) = rig.character.as_deref().and_then(|c| assets.models.get(c)) else { return };
    for e in children.iter_descendants(ready.entity) {
        if players.contains(e) {
            rig.player = Some(e);
            if !arms_only {
                commands.entity(e).insert((AnimationGraphHandle(model.graph.clone()), AnimationTransitions::new()));
            }
        }
    }
    if rig.player.is_none() {
        rig.player = Some(ready.entity);
    }
    rig.pose = None;
    rig.dressed = false;
}

/// Spawn the outfit's character, show its meshes, tint the cloth. Runs once per rig and again after
/// F5 or a wardrobe change.
#[allow(clippy::too_many_arguments)]
fn dress(
    mut commands: Commands,
    data: Res<Characters>,
    assets: Option<Res<CharacterAssets>>,
    mut rigs: Query<(Entity, &mut Rig, Has<FirstPerson>, Has<ArmsOnly>)>,
    children: Query<&Children>,
    names: Query<&Name>,
    material_names: Query<(&GltfMaterialName, &MeshMaterial3d<StandardMaterial>)>,
    mut materials: Option<ResMut<Assets<StandardMaterial>>>,
) {
    let Some(assets) = assets else { return };
    for (entity, mut rig, first_person, arms_only) in &mut rigs {
        if rig.dressed {
            continue;
        }
        let name = match rig.team {
            Some(team) => data.for_team(team, entity.index().index()).unwrap_or("acolyte").to_string(),
            None => rig.outfit.clone(),
        };
        let Some(outfit) = data.outfit(&name).or_else(|| data.default_outfit("runner")) else {
            warn!("no outfit named {name}");
            rig.dressed = true;
            continue;
        };
        if rig.team.is_some() && rig.weapon.is_none() {
            rig.weapon = data.loadout(&outfit.character);
        }
        if rig.character.as_deref() != Some(outfit.character.as_str()) {
            let Some(model) = assets.models.get(outfit.character.as_str()) else {
                // Still queued: try again next frame.
                if !assets.queue.contains(&outfit.character.as_str()) {
                    warn!("no model for character {}", outfit.character);
                    rig.dressed = true;
                }
                continue;
            };
            if let Some(old) = rig.model.take() {
                commands.entity(old).despawn();
            }
            let child = commands.spawn((RigModel, WorldAssetRoot(model.scene.clone()), Transform::default(), Visibility::default(), ChildOf(entity))).id();
            rig.model = Some(child);
            rig.character = Some(outfit.character.clone());
            rig.player = None;
            rig.held = None;
            continue;
        }
        let (Some(root), Some(_)) = (rig.model, rig.player) else { continue };
        rig.dressed = true;
        let mut tints: HashMap<(AssetId<StandardMaterial>, &str), Handle<StandardMaterial>> = HashMap::new();
        for e in children.iter_descendants(root) {
            if let Ok(name) = names.get(e)
                && MESHES.contains(&name.as_str())
            {
                let shown = !arms_only || name.as_str() == "mesh.arms";
                commands.entity(e).insert(if shown { Visibility::Inherited } else { Visibility::Hidden });
                let hidden_in_fp = first_person && name.as_str() != "mesh.body";
                for d in std::iter::once(e).chain(children.iter_descendants(e)) {
                    if hidden_in_fp {
                        commands.entity(d).insert(RenderLayers::layer(SHADOW_ONLY_LAYER));
                    }
                    if arms_only {
                        // The arms are posed by hand every frame, away from the mesh's own bounds;
                        // the body's own arms cast the shadow.
                        commands.entity(d).insert((NoFrustumCulling, bevy::light::NotShadowCaster));
                    }
                }
            }
            if let (Ok((mat, handle)), Some(materials)) = (material_names.get(e), materials.as_mut()) {
                let kind = mat.0.rsplit('.').next().unwrap_or("");
                if let Some(color) = outfit.tint(kind) {
                    let key = (handle.id(), ["primary", "secondary", "accent"].into_iter().find(|m| *m == kind).unwrap());
                    let tinted = tints.entry(key).or_insert_with(|| {
                        let mut m = materials.get(&handle.0).cloned().unwrap_or_default();
                        m.base_color = color;
                        materials.add(m)
                    });
                    commands.entity(e).insert(MeshMaterial3d(tinted.clone()));
                }
            }
        }
    }
}

/// Put the rig's weapon in its right hand, at the grip frame.
fn hold(
    mut commands: Commands,
    assets: Option<Res<CharacterAssets>>,
    mut rigs: Query<(&mut Rig, Has<FirstPerson>, Has<ArmsOnly>)>,
    children: Query<&Children>,
    names: Query<&Name>,
) {
    let Some(assets) = assets else { return };
    for (mut rig, first_person, arms_only) in &mut rigs {
        if arms_only || !rig.dressed {
            continue;
        }
        let Some(root) = rig.model() else { continue };
        if rig.held.map(|h| h.0) == rig.weapon {
            continue;
        }
        if let Some((_, old)) = rig.held.take() {
            commands.entity(old).despawn();
        }
        let Some(kind) = rig.weapon else { continue };
        let Some(grip) = children.iter_descendants(root).find(|e| names.get(*e).is_ok_and(|n| n.as_str() == GRIP_R)) else { continue };
        let Some(scene) = assets.weapons.get(&kind) else { continue };
        let held = commands.spawn((Held { first_person }, WorldAssetRoot(scene.clone()), held_transform(kind), Visibility::default(), ChildOf(grip))).id();
        rig.held = Some((kind, held));
    }
}

/// A held weapon's scene is in: show only the bare weapon's own pieces, keep it out of the player's
/// own view, and leave its clips alone.
fn on_held_ready(ready: On<WorldInstanceReady>, mut commands: Commands, held: Query<&Held>, children: Query<&Children>, names: Query<&Name>) {
    let Ok(h) = held.get(ready.entity) else { return };
    for e in children.iter_descendants(ready.entity) {
        if h.first_person {
            commands.entity(e).insert(RenderLayers::layer(SHADOW_ONLY_LAYER));
        }
        if let Ok(name) = names.get(e)
            && name.starts_with("att.")
        {
            let bare = ["att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard"].contains(&name.as_str());
            commands.entity(e).insert(if bare { Visibility::Inherited } else { Visibility::Hidden });
        }
    }
}

fn animate(
    assets: Option<Res<CharacterAssets>>,
    mut rigs: Query<(&mut Rig, &RigPose), Without<ArmsOnly>>,
    mut anims: Query<(&mut AnimationPlayer, &mut AnimationTransitions)>,
) {
    let Some(assets) = assets else { return };
    for (mut rig, want) in &mut rigs {
        let Some(e) = rig.player else { continue };
        let Some(model) = rig.character.as_deref().and_then(|c| assets.models.get(c)) else { continue };
        let Ok((mut anim, mut transitions)) = anims.get_mut(e) else { continue };
        let node = model.nodes[want.pose.index()];
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
    fn baked_roster_is_consistent() {
        let c = Characters::parse(DEFAULT_DATA).unwrap();
        assert!(c.problems().is_empty(), "{:?}", c.problems());
        assert_eq!(c.class["pilot"].character, "runner");
        for id in CHARACTERS {
            assert!(c.loadout(id).is_some(), "{id} has a loadout");
        }
    }

    #[test]
    fn every_character_has_a_model_with_the_shared_rig() {
        for id in CHARACTERS {
            let path = format!("assets/{}", model_path(id));
            let data = std::fs::read(&path).unwrap_or_else(|_| panic!("{path} exists"));
            let text = String::from_utf8_lossy(&data[..data.len().min(400_000)]);
            for name in MESHES.iter().chain(&[GRIP_R, GRIP_L, "hips", "upper_arm.L", "forearm.R", "hand.R"]) {
                assert!(text.contains(&format!("\"{name}\"")), "{id} has {name}");
            }
            let clips = ["idle", "walk", "run", "sprint", "jump", "fall", "crouch", "slide", "wallrun_l", "wallrun_r", "mantle", "grapple"];
            let at: Vec<usize> = clips.iter().map(|c| text.find(&format!("\"name\":\"{c}\"")).unwrap_or_else(|| panic!("{id} has clip {c}"))).collect();
            assert!(at.windows(2).all(|w| w[0] < w[1]), "{id}: clips in Pose order");
        }
    }

    #[test]
    fn teams_draw_from_their_factions() {
        let c = Characters::parse(DEFAULT_DATA).unwrap();
        let mut seen = std::collections::HashSet::new();
        for seed in 0..200 {
            let id = c.for_team(1, seed).unwrap();
            assert!(c.teams["1"].contains(&c.character[id].faction));
            seen.insert(id);
        }
        assert!(seen.len() > 3, "patrols vary: {seen:?}");
        assert_eq!(c.character[c.for_team(0, 5).unwrap()].faction, c.teams["0"][0]);
    }

    #[test]
    fn wardrobe_outfits_override_defaults() {
        let mut c = Characters::parse(DEFAULT_DATA).unwrap();
        assert_eq!(c.outfit("runner").unwrap().primary, c.character["runner"].primary);
        c.custom.insert("custom".into(), OutfitDef { character: "zealot".into(), primary: "#ff0000".into(), ..default() });
        assert_eq!(c.outfit("custom").unwrap().character, "zealot");
        c.custom.insert("bad".into(), OutfitDef { character: "nobody".into(), ..default() });
        assert!(c.outfit("bad").is_none(), "unknown characters fall back");
    }

    #[test]
    fn problems_are_reported() {
        let c = Characters::parse("[character.x]\nfaction = \"f\"\nprimary = \"red\"\nloadout = \"spoon\"\n[class.y]\ncharacter = \"nope\"").unwrap();
        let p = c.problems();
        assert!(p.iter().any(|m| m.contains("character runner is missing")));
        assert!(p.iter().any(|m| m.contains("no faction named f")));
        assert!(p.iter().any(|m| m.contains("spoon")));
        assert!(p.iter().any(|m| m.contains("primary")));
        assert!(p.iter().any(|m| m.contains("class y")));
    }

    #[test]
    fn weapons_land_in_the_fist() {
        for kind in WEAPONS {
            let t = held_transform(kind);
            assert!(t.transform_point(hands(kind).right).length() < 1e-5, "{kind:?} grip at the frame origin");
            // The barrel (-Z) runs down the frame's +Y.
            assert!((t.rotation * Vec3::NEG_Z).distance(Vec3::Y) < 1e-5);
        }
    }

    #[test]
    fn hex_colours() {
        assert_eq!(parse_hex("#ff0000"), Some(Color::srgb_u8(255, 0, 0)));
        assert_eq!(parse_hex("ff0000"), None);
        assert_eq!(parse_hex("#fff"), None);
    }
}
