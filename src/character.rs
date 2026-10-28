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
use bevy::asset::RenderAssetUsages;
use bevy::gltf::{GltfLoaderSettings, GltfMaterialName};
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
/// The palm frames (origin on the palm's skin, +Y wrist to knuckles, +Z out of the palm): the held
/// weapon hangs under the right one.
pub const GRIP_R: &str = "prop_hand.R";
pub const GRIP_L: &str = "prop_hand.L";

pub fn model_path(id: &str) -> String {
    format!("models/character/{id}.glb")
}

/// Animation clips, in the order they sit in every glb (`tools/character/anim.py`). After them come
/// the two overlays, `RELOAD_CLIP` and `FIRE_CLIP`.
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
    CrouchWalk,
    DoubleJump,
    Death,
    DeathBack,
    /// Seated at a car's wheel.
    Drive,
    /// Astride the dirt bike.
    Ride,
}

impl Pose {
    pub const ALL: [Pose; 18] = [
        Pose::Idle, Pose::Walk, Pose::Run, Pose::Sprint, Pose::Jump, Pose::Fall, Pose::Crouch,
        Pose::Slide, Pose::WallRunL, Pose::WallRunR, Pose::Mantle, Pose::Grapple, Pose::CrouchWalk,
        Pose::DoubleJump, Pose::Death, Pose::DeathBack, Pose::Drive, Pose::Ride,
    ];

    fn index(self) -> usize {
        Pose::ALL.iter().position(|p| *p == self).unwrap()
    }

    /// The clip's name in the glb.
    pub fn name(self) -> &'static str {
        ["idle", "walk", "run", "sprint", "jump", "fall", "crouch", "slide", "wallrun_l", "wallrun_r", "mantle", "grapple",
         "crouch_walk", "double_jump", "death", "death_back", "drive", "ride"][self.index()]
    }

    /// Cycles repeat; the rest play once and hold their last frame.
    pub fn loops(self) -> bool {
        !matches!(self, Pose::Jump | Pose::Fall | Pose::Mantle | Pose::DoubleJump | Pose::Death | Pose::DeathBack)
    }
}

/// The magazine change: the arms only, laid over whatever the body does.
const RELOAD_CLIP: usize = Pose::ALL.len();
/// Recoil: torso rotations added on top of the pose.
const FIRE_CLIP: usize = Pose::ALL.len() + 1;
/// The reload clip's length at speed 1 (seconds); it is sped up to fit the weapon's reload.
const RELOAD_SECS: f32 = 2.0;
/// How far the reload clip outweighs the pose on the arms it moves.
const RELOAD_WEIGHT: f32 = 20.0;

/// Where a weapon model's hands go, in the weapon's glTF space (-Z down the barrel, +Y up, the
/// trigger at the origin): the middle of the pistol grip, and the support hand's hold (with the bone
/// it rides, like the shotgun's pump) for weapons held in two hands. The table is
/// `assets/grips.toml`; the solver in `tools/character/grips.py` fits each hold's cylinder round
/// these points and writes every character's palm frames and finger poses (`fingers::Solved`),
/// which the game uses first. The points only place a right hand with no solved pose.
pub struct Hands {
    pub right: Vec3,
    pub left: Option<(Vec3, String)>,
}

/// The table's holds (`cradle`, `vertical`, `angled`) are the solver's; the game only needs these.
#[derive(Deserialize)]
struct GripDef {
    right: [f32; 3],
    left: Option<[f32; 3]>,
    left_bone: Option<String>,
}

pub fn hands(kind: WeaponKind) -> &'static Hands {
    static TABLE: std::sync::OnceLock<HashMap<String, Hands>> = std::sync::OnceLock::new();
    let table = TABLE.get_or_init(|| {
        let defs: HashMap<String, GripDef> = toml::from_str(include_str!("../assets/grips.toml")).expect("assets/grips.toml");
        defs.into_iter()
            .map(|(id, d)| {
                let left = d.left.map(|l| (Vec3::from_array(l), d.left_bone.unwrap_or_else(|| "root".into())));
                (id, Hands { right: Vec3::from_array(d.right), left })
            })
            .collect()
    });
    table.get(kind.id()).unwrap_or_else(|| panic!("assets/grips.toml has no [{}]", kind.id()))
}

/// Weapon space to the right palm frame with no solved pose: the barrel (-Z) runs down the frame's
/// +Y (wrist to knuckles), the gun's left (-X) out of the palm (+Z), and up (+Y) along its +X
/// (toward the thumb).
pub fn grip_rotation() -> Quat {
    Quat::from_mat3(&Mat3::from_cols(Vec3::Y, Vec3::NEG_Z, Vec3::NEG_X)).inverse()
}

/// Where a weapon model sits under the right palm frame so its grip lands in the palm.
pub fn held_transform(kind: WeaponKind) -> Transform {
    let rot = grip_rotation();
    Transform { translation: -(rot * hands(kind).right), rotation: rot, scale: Vec3::ONE }
}

/// The same for a solved right-hand pose: its grip frame at `at`, turned by `rot`, in weapon space.
pub fn held_transform_solved(pose: &crate::fingers::HandPose) -> Transform {
    let rot = pose.rot.inverse();
    Transform { translation: -(rot * pose.at), rotation: rot, scale: Vec3::ONE }
}

// ------------------------------------------------------------------------------------------- data

/// What a rig wears: a character, its three cloth colours, and the optional extras the wardrobe
/// offers. Every optional field keeps the character's own look until an outfit sets it, so an
/// outfit saved before a field existed reads back unchanged.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
#[serde(default)]
pub struct OutfitDef {
    pub character: String,
    pub primary: String,
    pub secondary: String,
    pub accent: String,
    /// Another character whose head (helmet, hood, mask) is worn instead of this one's.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub head: Option<String>,
    /// A `camo::PATTERNS` entry printed over the primary and secondary cloth.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub camo: Option<String>,
    /// Skin tone; replaces the painted skin (pores and such stay in the normal map).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skin: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gloves: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub boots: Option<String>,
    /// Straps, slings and pouches.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub webbing: Option<String>,
    /// Buckles, plates and tools: gunmetal, steel, brass.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metal: Option<String>,
    /// The glowing bits (visor strips, lights); `off` darkens them.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub glow: Option<String>,
    /// Visors and lenses.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub glass: Option<String>,
    /// 0 clean to 3 battered: darker, duller cloth and scuffed metal.
    #[serde(skip_serializing_if = "is_zero")]
    pub wear: u8,
}

fn is_zero(n: &u8) -> bool {
    *n == 0
}

/// Most wear a character can show.
pub const WEAR_MAX: u8 = 3;

/// What an outfit field means for a material: material names end in a kind (`runner.knit.primary`
/// is `primary`), and each kind that the wardrobe can touch belongs to one of these.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Surface {
    Cloth,
    Skin,
    Metal,
    Glow,
    Glass,
}

impl OutfitDef {
    /// The colour the outfit asks for on material kind `kind`, if it sets one.
    pub fn tint(&self, kind: &str) -> Option<Color> {
        let hex = match kind {
            "primary" => Some(&self.primary),
            "secondary" => Some(&self.secondary),
            "accent" => Some(&self.accent),
            "skin" | "zealot_skin" => self.skin.as_ref(),
            "glove" => self.gloves.as_ref(),
            "boot" | "scrap_boot" => self.boots.as_ref(),
            "webbing" => self.webbing.as_ref(),
            "gunmetal" | "steel" | "brass" | "scrap_copper" => self.metal.as_ref(),
            k if k.starts_with("glow_") => self.glow.as_ref(),
            "glass" | "scrap_lens" => self.glass.as_ref(),
            _ => None,
        }?;
        parse_hex(hex)
    }

    fn surface(kind: &str) -> Option<Surface> {
        Some(match kind {
            "primary" | "secondary" | "accent" | "glove" | "boot" | "scrap_boot" | "webbing" => Surface::Cloth,
            "skin" | "zealot_skin" => Surface::Skin,
            "gunmetal" | "steel" | "brass" | "scrap_copper" => Surface::Metal,
            "glass" | "scrap_lens" => Surface::Glass,
            k if k.starts_with("glow_") => Surface::Glow,
            _ => return None,
        })
    }

    /// Whether this outfit prints camo on cloth of kind `kind`.
    pub fn camo_on(&self, kind: &str) -> bool {
        matches!(kind, "primary" | "secondary") && crate::camo::draws(self.camo.as_deref())
    }

    /// Whether the outfit changes a material of kind `kind` at all (so the model's own is kept otherwise).
    pub fn touches(&self, kind: &str) -> bool {
        let wear = self.wear > 0 && matches!(Self::surface(kind), Some(Surface::Cloth | Surface::Metal));
        self.tint(kind).is_some() || self.camo_on(kind) || wear || (kind.starts_with("glow_") && self.glow.as_deref() == Some("off"))
    }

    /// `base` (the model's material of kind `kind`) as this outfit wants it: tinted, printed with
    /// `camo` where it goes, worn down.
    pub fn finish(&self, kind: &str, base: &StandardMaterial, camo: Option<Handle<Image>>) -> StandardMaterial {
        let mut m = base.clone();
        let surface = Self::surface(kind);
        if let Some(c) = self.tint(kind) {
            m.base_color = c;
            match surface {
                // Painted skin is a colour already: show the tone itself over the pore detail.
                Some(Surface::Skin) => m.base_color_texture = None,
                Some(Surface::Glow) => m.emissive = c.to_linear() * 2.0,
                _ => {}
            }
        }
        if kind.starts_with("glow_") && self.glow.as_deref() == Some("off") {
            m.base_color = Color::srgb(0.12, 0.12, 0.13);
            m.emissive = LinearRgba::BLACK;
        }
        if self.camo_on(kind) {
            m.base_color_texture = camo;
            m.base_color = Color::WHITE;
        }
        if self.wear > 0 {
            let w = self.wear as f32 / WEAR_MAX as f32;
            match surface {
                Some(Surface::Cloth) => {
                    let mut c = m.base_color.to_linear();
                    let grey = (c.red + c.green + c.blue) / 3.0;
                    for ch in [&mut c.red, &mut c.green, &mut c.blue] {
                        *ch = (*ch * (1.0 - 0.3 * w) + grey * 0.3 * w) * (1.0 - 0.35 * w);
                    }
                    m.base_color = c.into();
                    m.perceptual_roughness = (m.perceptual_roughness + 0.25 * w).min(1.0);
                }
                Some(Surface::Metal) => {
                    m.perceptual_roughness = (m.perceptual_roughness + 0.4 * w).min(1.0);
                    m.base_color = (m.base_color.to_linear() * (1.0 - 0.2 * w)).with_alpha(1.0).into();
                }
                _ => {}
            }
        }
        m
    }

    /// Normalise what the wardrobe can produce: a head of one's own is no head swap, `none` camo is
    /// no camo.
    pub fn tidy(&mut self) {
        if self.head.as_deref() == Some(self.character.as_str()) {
            self.head = None;
        }
        if self.camo.as_deref() == Some("none") {
            self.camo = None;
        }
        self.wear = self.wear.min(WEAR_MAX);
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
    /// The sidearm the player starts with when playing this character, bare: `pistol` (Smite) or `revolver` (Warden).
    pub start: String,
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
        Some(OutfitDef { character: id.into(), primary: c.primary.clone(), secondary: c.secondary.clone(), accent: c.accent.clone(), ..default() })
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

    /// The sidearm the player starts with as `id`: the Warden or the Smite, the Smite when unsaid.
    pub fn start(&self, id: &str) -> WeaponKind {
        let w = self.character.get(id).map_or("", |c| c.start.as_str());
        [WeaponKind::Revolver, WeaponKind::Pistol].into_iter().find(|k| k.id() == w).unwrap_or(WeaponKind::Pistol)
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
            if !matches!(c.start.as_str(), "pistol" | "revolver") {
                out.push(format!("character {id}: start must be pistol or revolver, not {}", c.start));
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
    nodes: [AnimationNodeIndex; Pose::ALL.len()],
    reload: AnimationNodeIndex,
    fire: AnimationNodeIndex,
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
    /// A second character spawned for its head alone (the outfit's `head`), its scene and player.
    head: Option<String>,
    head_model: Option<Entity>,
    head_player: Option<Entity>,
    pose: Option<Pose>,
    /// The last `RigPose::shots` seen, so each new one kicks once.
    shots: u32,
    /// The glTF's `AnimationPlayer`, once the model has spawned.
    player: Option<Entity>,
    held: Option<(WeaponKind, Entity)>,
    dressed: bool,
}

impl Rig {
    pub fn new(outfit: &str) -> Self {
        Self { outfit: outfit.into(), team: None, weapon: None, character: None, model: None, head: None, head_model: None, head_player: None, pose: None, shots: 0, player: None, held: None, dressed: false }
    }

    /// Wearing its outfit, and holding its weapon if it has one.
    pub fn ready(&self) -> bool {
        self.dressed && self.held.map(|h| h.0) == self.weapon
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

    /// The character whose model is spawned.
    pub fn character(&self) -> Option<&str> {
        self.character.as_deref()
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
    /// The weapon's whole reload time (seconds) while a reload runs, else 0.
    pub reload: f32,
    /// Counts shots fired; each change kicks the torso.
    pub shots: u32,
}

impl RigPose {
    pub fn new(pose: Pose, rate: f32) -> Self {
        Self { pose, rate, reload: 0.0, shots: 0 }
    }
}

impl Default for RigPose {
    fn default() -> Self {
        Self::new(Pose::Idle, 1.0)
    }
}

/// The player's own rig: it renders only into shadow maps (the first-person arms and viewmodel
/// stand in for it).
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

/// The outfit a rig wears: its own, or for a soldier one picked for its team.
fn outfit_of(data: &Characters, rig: &Rig, entity: Entity) -> Option<OutfitDef> {
    let name = match rig.team {
        Some(team) => data.for_team(team, entity.index().index()).unwrap_or("acolyte").to_string(),
        None => rig.outfit.clone(),
    };
    data.outfit(&name).or_else(|| data.default_outfit("runner"))
}

/// Characters keep their meshes and textures on the GPU only: nothing reads them back, and a
/// second copy in RAM cost about 150 MB each.
fn gpu_only(s: &mut GltfLoaderSettings) {
    s.load_meshes = RenderAssetUsages::RENDER_WORLD;
    s.load_materials = RenderAssetUsages::RENDER_WORLD;
}

/// Start the load of a character a rig is wearing (or about to), one at a time. Characters nobody
/// wears are never loaded: each costs hundreds of MB.
fn stream(server: Res<AssetServer>, assets: Option<ResMut<CharacterAssets>>, mut graphs: Option<ResMut<Assets<AnimationGraph>>>, data: Res<Characters>, rigs: Query<(Entity, &Rig)>) {
    let (Some(mut assets), Some(graphs)) = (assets, graphs.as_mut()) else { return };
    let busy = assets.models.values().any(|m| !matches!(server.load_state(&m.scene), LoadState::Loaded | LoadState::Failed(_)));
    if busy || assets.queue.is_empty() {
        return;
    }
    let wanted = |id: &&str| rigs.iter().any(|(e, r)| outfit_of(&data, r, e).is_some_and(|o| o.character == *id || o.head.as_deref() == Some(*id)));
    let Some(at) = assets.queue.iter().position(wanted) else { return };
    let id = assets.queue.remove(at);
    let path = model_path(id);
    let clip = |i: usize| server.load_builder().with_settings(gpu_only).load(GltfAssetLabel::Animation(i).from_asset(path.clone()));
    // The poses blend among themselves (the transitions set their weights) with the reload on the
    // arms; recoil is added on top of the lot.
    let mut graph = AnimationGraph::new();
    let add = graph.add_additive_blend(1.0, graph.root);
    let base = graph.add_blend(1.0, add);
    let nodes = Pose::ALL.map(|p| graph.add_clip(clip(p.index()), 1.0, base));
    let reload = graph.add_clip(clip(RELOAD_CLIP), 1.0, base);
    let fire = graph.add_clip(clip(FIRE_CLIP), 1.0, add);
    let scene = server.load_builder().with_settings(gpu_only).load(GltfAssetLabel::Scene(0).from_asset(path));
    let model = Model { scene, graph: graphs.add(graph), nodes, reload, fire };
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
    let is_head = rig.head_model == Some(ready.entity);
    if rig.model != Some(ready.entity) && !is_head {
        return;
    }
    let character = if is_head { rig.head.as_deref() } else { rig.character.as_deref() };
    let Some(model) = character.and_then(|c| assets.models.get(c)) else { return };
    let mut player = None;
    for e in children.iter_descendants(ready.entity) {
        if players.contains(e) {
            player = Some(e);
            if !arms_only {
                commands.entity(e).insert((AnimationGraphHandle(model.graph.clone()), AnimationTransitions::new()));
            }
        }
    }
    let player = player.unwrap_or(ready.entity);
    if is_head {
        rig.head_player = Some(player);
    } else {
        rig.player = Some(player);
    }
    // Restart the pose so a new part starts its clip in step with the rest.
    rig.pose = None;
    rig.dressed = false;
}

/// Camo textures made so far, by pattern and the two colours printed; a texture is 256 KB.
#[derive(Default)]
struct CamoCache(HashMap<(String, String, String), Handle<Image>>);

/// Spawn the outfit's character (and the one lending its head), show their meshes, tint the cloth.
/// Runs once per rig and again after F5 or a wardrobe change.
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
    mut images: Option<ResMut<Assets<Image>>>,
    mut camos: Local<CamoCache>,
) {
    let Some(assets) = assets else { return };
    for (entity, mut rig, first_person, arms_only) in &mut rigs {
        if rig.dressed {
            continue;
        }
        let Some(outfit) = outfit_of(&data, &rig, entity) else {
            warn!("no outfit for {}", rig.outfit);
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
        // The borrowed head: another character's scene, of which only `mesh.head` shows. The
        // first-person arms have no head to swap.
        let head = outfit.head.clone().filter(|h| !arms_only && *h != outfit.character && CHARACTERS.contains(&h.as_str()));
        if rig.head != head {
            if let Some(old) = rig.head_model.take() {
                commands.entity(old).despawn();
            }
            rig.head_player = None;
            rig.head = None;
            if let Some(h) = &head {
                let Some(model) = assets.models.get(h.as_str()) else { continue };
                let child = commands.spawn((RigModel, WorldAssetRoot(model.scene.clone()), Transform::default(), Visibility::default(), ChildOf(entity))).id();
                rig.head_model = Some(child);
                rig.head = head.clone();
                continue;
            }
        }
        let (Some(root), Some(_)) = (rig.model, rig.player) else { continue };
        if rig.head_model.is_some() && rig.head_player.is_none() {
            continue;
        }
        rig.dressed = true;
        let camo = match (&outfit.camo, images.as_mut()) {
            (Some(p), Some(images)) if crate::camo::draws(Some(p)) => {
                let key = (p.clone(), outfit.primary.clone(), outfit.secondary.clone());
                camos.0.get(&key).cloned().or_else(|| {
                    let img = crate::camo::image(p, parse_hex(&outfit.primary)?, parse_hex(&outfit.secondary)?)?;
                    let handle = images.add(img);
                    camos.0.insert(key, handle.clone());
                    Some(handle)
                })
            }
            _ => None,
        };
        let mut finished: HashMap<(AssetId<StandardMaterial>, String), Handle<StandardMaterial>> = HashMap::new();
        let parts = std::iter::once((root, false)).chain(rig.head_model.map(|h| (h, true)));
        for (root, borrowed_head) in parts {
            for e in children.iter_descendants(root) {
                if let Ok(name) = names.get(e)
                    && MESHES.contains(&name.as_str())
                {
                    let is_head = name.as_str() == "mesh.head";
                    let shown = if borrowed_head { is_head } else { (!arms_only || name.as_str() == "mesh.arms") && !(is_head && rig.head_model.is_some()) };
                    commands.entity(e).insert(if shown { Visibility::Inherited } else { Visibility::Hidden });
                    // The player's own model only casts shadows: its shoulders and chest filled the view.
                    let hidden_in_fp = first_person;
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
                    if outfit.touches(kind) {
                        let key = (handle.id(), kind.to_string());
                        let done = finished.entry(key).or_insert_with(|| {
                            let base = materials.get(&handle.0).cloned().unwrap_or_default();
                            materials.add(outfit.finish(kind, &base, camo.clone()))
                        });
                        commands.entity(e).insert(MeshMaterial3d(done.clone()));
                    }
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
    solved: Option<Res<crate::fingers::Solved>>,
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
        let pose = solved.as_ref().zip(rig.character()).and_then(|(s, c)| s.get(c, kind, "R"));
        let at = pose.map_or_else(|| held_transform(kind), held_transform_solved);
        let held = commands.spawn((Held { first_person }, WorldAssetRoot(scene.clone()), at, Visibility::default(), ChildOf(grip))).id();
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
        // A borrowed head is a second player on the same clips; both get every change in the same
        // frame so they stay in step.
        let parts = [(Some(e), rig.character.clone()), (rig.head_player, rig.head.clone())];
        let changed = rig.pose != Some(want.pose);
        let fired = want.shots != rig.shots;
        for (e, character) in parts {
            let (Some(e), Some(model)) = (e, character.as_deref().and_then(|c| assets.models.get(c))) else { continue };
            let Ok((mut anim, mut transitions)) = anims.get_mut(e) else { continue };
            let node = model.nodes[want.pose.index()];
            if changed {
                let a = transitions.play(&mut anim, node, Duration::from_millis(150));
                a.replay();
                if want.pose.loops() {
                    a.repeat();
                }
            }
            if let Some(a) = anim.animation_mut(node) {
                a.set_speed(want.rate);
            }
            // Overlays: the reload runs once over the weapon's reload time, the recoil once per shot.
            if want.reload > 0.0 && !anim.is_playing_animation(model.reload) {
                anim.start(model.reload).set_weight(RELOAD_WEIGHT).set_speed(RELOAD_SECS / want.reload);
            }
            if anim.animation(model.reload).is_some_and(|a| a.is_finished()) || (want.reload <= 0.0 && anim.is_playing_animation(model.reload)) {
                anim.stop(model.reload);
            }
            if fired {
                anim.start(model.fire).replay();
            }
            if anim.animation(model.fire).is_some_and(|a| a.is_finished()) {
                anim.stop(model.fire);
            }
        }
        if changed && anims.contains(e) {
            rig.pose = Some(want.pose);
        }
        if fired {
            rig.shots = want.shots;
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
            let clips: Vec<&str> = Pose::ALL.iter().map(|p| p.name()).chain(["reload", "fire"]).collect();
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
    fn optional_slots_tint_only_when_set_and_save_only_when_set() {
        let o = OutfitDef { gloves: Some("#ff0000".into()), glow: Some("#00ff00".into()), ..default() };
        assert_eq!(o.tint("glove"), parse_hex("#ff0000"));
        assert_eq!(o.tint("glow_amber"), parse_hex("#00ff00"), "every glow kind follows the glow slot");
        assert_eq!(o.tint("boot"), None, "unset boots keep the character's colour");
        assert!(!o.touches("boot") && o.touches("glove") && !o.touches("rubber"));
        let text = toml::to_string(&OutfitDef { character: "runner".into(), ..default() }).unwrap();
        assert_eq!(text.trim(), "character = \"runner\"\nprimary = \"\"\nsecondary = \"\"\naccent = \"\"", "old saves keep their shape");
        let back: OutfitDef = toml::from_str("character = \"ghost\"\nprimary = \"#101010\"").unwrap();
        assert_eq!((back.head, back.wear), (None, 0));
    }

    #[test]
    fn finish_prints_camo_tones_skin_and_wear() {
        let base = StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.5, ..default() };
        let mut o = OutfitDef { character: "runner".into(), primary: "#ff0000".into(), secondary: "#00ff00".into(), camo: Some("hex".into()), skin: Some("#c68b63".into()), wear: 2, ..default() };
        let tex = Handle::<Image>::default();
        assert!(o.camo_on("primary") && !o.camo_on("accent"));
        let m = o.finish("primary", &base, Some(tex.clone()));
        assert_eq!(m.base_color_texture, Some(tex), "camo replaces the painted cloth");
        assert!(m.base_color.to_linear().red < 1.0, "wear dulls it");
        assert!(m.perceptual_roughness > 0.5);
        let m = o.finish("skin", &base, None);
        assert_eq!((m.base_color, m.base_color_texture), (parse_hex("#c68b63").unwrap(), None));
        o.glow = Some("off".into());
        assert!(o.touches("glow_red"));
        assert_eq!(o.finish("glow_red", &base, None).emissive, LinearRgba::BLACK);
        o.head = Some("runner".into());
        o.camo = Some("none".into());
        o.tidy();
        assert_eq!((o.head, o.camo), (None, None), "own head and no camo are the defaults");
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
    fn grip_points_match_the_old_table() {
        assert_eq!(hands(WeaponKind::Rifle).right, Vec3::new(0.0, -0.038, 0.030));
        assert_eq!(hands(WeaponKind::Shotgun).left.as_ref().map(|l| l.1.as_str()), Some("pump"));
        assert_eq!(hands(WeaponKind::Rifle).left.as_ref().map(|l| l.1.as_str()), Some("root"));
        assert!(hands(WeaponKind::Pistol).left.is_none());
        assert!(hands(WeaponKind::Fist).left.is_none());
    }

    #[test]
    fn weapons_land_in_the_palm() {
        for kind in WEAPONS {
            let t = held_transform(kind);
            assert!(t.transform_point(hands(kind).right).length() < 1e-5, "{kind:?} grip at the frame origin");
            // The barrel (-Z) runs down the frame's +Y, the gun's left out of the palm, up toward the thumb.
            assert!((t.rotation * Vec3::NEG_Z).distance(Vec3::Y) < 1e-5);
            assert!((t.rotation * Vec3::NEG_X).distance(Vec3::Z) < 1e-5);
            assert!((t.rotation * Vec3::Y).distance(Vec3::X) < 1e-5);
        }
    }

    #[test]
    fn solved_hold_matches_the_default_frame() {
        for kind in WEAPONS {
            let pose = crate::fingers::HandPose { at: hands(kind).right, rot: grip_rotation().inverse(), joints: [Quat::IDENTITY; 15] };
            let (a, b) = (held_transform(kind), held_transform_solved(&pose));
            assert!(a.translation.distance(b.translation) < 1e-5 && a.rotation.dot(b.rotation).abs() > 1.0 - 1e-6, "{kind:?}");
        }
    }

    #[test]
    fn hex_colours() {
        assert_eq!(parse_hex("#ff0000"), Some(Color::srgb_u8(255, 0, 0)));
        assert_eq!(parse_hex("ff0000"), None);
        assert_eq!(parse_hex("#fff"), None);
    }
}
