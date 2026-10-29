//! Posts: small faction outposts scattered over each world (docs/superpowers/specs/2026-10-29-living-bases-design.md),
//! from `assets/posts.toml` and `models/posts/<id>.glb` (built by `tools/bases/posts.sh`). Each world
//! has its own faction's post, placed from the world's seed on flat dry ground well clear of the
//! big base, its pad and each other, so they are always in the same places and nothing about where
//! they stand is saved. A post has two of its faction's people and a supply cache at its door.
//! Coming within `FOUND` of one marks it found in the save, and from then on it has a waypoint.

use std::sync::Arc;

use avian3d::prelude::*;
use bevy::prelude::*;
use serde::Deserialize;

use super::base::{self, BaseModel, BaseSpec, Bases, Pending, SLAB_DEPTH};
use super::combat::Faction;
use super::station::{Prompt, Station};
use super::{flat_site, life, Fixture, Solar};
use crate::camera::PlayerCamera;
use crate::save::{Save, SaveFile};
use crate::surface::{Origin, Sphere, Surface};

/// How many posts a world gets: one per this many metres of radius, within these bounds.
const PER_RADIUS: f32 = 500.0;
const FEWEST: usize = 6;
const MOST: usize = 12;
/// Posts keep this far from a base (and its pad), from Haven's apron, and from each other: along
/// the ground, metres.
const BASE_GAP: f32 = 400.0;
const POST_GAP: f32 = 600.0;
/// On Haven they stand on the home continent outside the island region, on dry land.
const DRY: f32 = 5.0;
/// You have found a post once you come this close.
pub const FOUND: f32 = 150.0;

/// Every post in the game, one per world.
#[derive(Resource, Deserialize, Clone, Debug)]
pub struct Posts {
    pub post: Vec<BaseSpec>,
}

impl Posts {
    pub fn load() -> Self {
        toml::from_str(include_str!("../../assets/posts.toml")).expect("assets/posts.toml")
    }
}

/// A post standing on the anchor world: `spec` indexes `Posts`, `key` names it in the save
/// (`<body>.<n>`).
#[derive(Component, Clone, Debug)]
pub struct Post {
    pub spec: usize,
    pub key: String,
}

pub fn build(app: &mut App) {
    app.insert_resource(Posts::load()).add_systems(Update, discover);
}

/// A small, fast, seeded generator.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> f32 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 40) as f32 / (1u64 << 24) as f32
    }
}

/// How many posts a world of `radius` metres gets.
pub fn count(radius: f32) -> usize {
    ((radius / PER_RADIUS).round() as usize).clamp(FEWEST, MOST)
}

/// Where a world's posts stand: ground points (body coordinates) and a yaw each, from its seed,
/// clear of `keep_clear` (bases, pads) by `BASE_GAP` and of each other by `POST_GAP`. On a world
/// with a home continent, only on it, outside its island region and above the sea. Fewer when no
/// good ground is left.
pub fn sites(sphere: &Sphere, keep_clear: &[Vec3]) -> Vec<(Vec3, f32)> {
    let body = &sphere.body;
    let want = count(body.radius);
    let mut rng = Rng(0x9e37_79b9_7f4a_7c15 ^ (body.seed as u64).wrapping_mul(0x2545_f491_4f6c_dd1d) | 1);
    let r = sphere.sea_radius();
    let along = |a: Vec3, b: Vec3| a.normalize().angle_between(b.normalize()) * r;
    let home = body.home.as_ref().map(|h| (super::lat_lon_dir(h.lat, h.lon), h.core, h.continent / 2.0));
    let surface = Surface::Sphere(Arc::new(sphere.clone()));
    let mut out: Vec<(Vec3, f32)> = Vec::new();
    for _ in 0..want * 8 {
        if out.len() == want {
            break;
        }
        // A direction: anywhere on the world, or on a home continent somewhere between its
        // island region and its rim.
        let dir = match &home {
            None => {
                let (z, a) = (rng.next() * 2.0 - 1.0, rng.next() * std::f32::consts::TAU);
                let s = (1.0 - z * z).sqrt();
                Vec3::new(s * a.cos(), z, s * a.sin())
            }
            Some((centre, core, rim)) => {
                let frame = surface.frame(*centre * r);
                let (d, a) = (core + 600.0 + rng.next() * (rim - core - 600.0), rng.next() * std::f32::consts::TAU);
                (*centre * r + frame * Vec3::new(d * a.cos(), 0.0, d * a.sin())).normalize()
            }
        };
        let yaw = rng.next() * 360.0;
        let at = flat_site(sphere, dir);
        if home.is_some() && sphere.height(at.normalize()) < DRY {
            continue;
        }
        if let Some((centre, core, _)) = &home
            && along(at, *centre) < *core
        {
            continue;
        }
        if keep_clear.iter().any(|k| along(at, *k) < BASE_GAP) || out.iter().any(|(p, _)| along(at, *p) < POST_GAP) {
            continue;
        }
        out.push((at, yaw));
    }
    out
}

/// The anchor world's posts: a foundation, the collider, the cache, the crew and the model.
pub fn spawn_posts(world: &mut World) {
    let Some(posts) = world.get_resource::<Posts>().cloned() else { return };
    let solar = world.resource::<Solar>();
    let (anchor, pad) = (solar.anchor.clone(), solar.pad);
    let Some(sphere) = solar.spheres.get(&anchor).cloned() else { return };
    let Some((spec_i, spec)) = posts.post.iter().enumerate().find(|(_, p)| p.body == anchor) else { return };
    let origin = *world.resource::<Origin>();
    let bases = world.resource::<Bases>().clone();
    let mut keep_clear: Vec<Vec3> = bases.base.iter().filter(|b| b.body == anchor).map(|b| base::site(b, &sphere, pad).0).collect();
    if anchor == "home" {
        keep_clear.push(pad);
    }
    let faction = Faction::from_id(&spec.faction).unwrap_or_default();
    let material = world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| m.add(StandardMaterial { base_color: Color::srgb(0.32, 0.33, 0.35), perceptual_roughness: 0.8, ..default() }));
    let surface = Surface::Sphere(sphere.clone());
    for (n, (ground, yaw)) in sites(&sphere, &keep_clear).into_iter().enumerate() {
        let frame = surface.frame(ground) * Quat::from_rotation_y(yaw.to_radians());
        let at = Vec3::new(spec.footprint_at[0], 0.0, spec.footprint_at[1]);
        let deck = base::deck_over(&sphere, ground, frame, at, spec.footprint[0] / 2.0, spec.footprint[1] / 2.0);
        let size = Vec3::new(spec.footprint[0], SLAB_DEPTH, spec.footprint[1]);
        let slab = Transform::from_translation(origin.world(ground + frame * (at + Vec3::Y * (deck - size.y / 2.0)))).with_rotation(frame);
        let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
        let mut e = world.spawn((Name::new("Post foundation"), Fixture, RigidBody::Static, Collider::cuboid(size.x, size.y, size.z), slab));
        if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
            e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
        }
        let transform = Transform::from_translation(origin.world(ground + frame * Vec3::Y * deck)).with_rotation(frame);
        let key = format!("{anchor}.{n}");
        let post = world.spawn((Name::new(format!("{} {n}", spec.name)), Post { spec: spec_i, key }, Fixture, RigidBody::Static, spec.collider(), transform, Visibility::default())).id();
        for st in &spec.stations {
            let s = world.spawn((Name::new(format!("Station {}", st.label)), Station { base: usize::MAX, faction, kind: st.kind, label: st.label.clone() }, Transform::from_translation(Vec3::from(st.at)), Visibility::default())).id();
            world.entity_mut(post).add_child(s);
        }
        let model = world.spawn((BaseModel, Transform::default(), Visibility::default())).id();
        world.entity_mut(post).add_child(model);
        if world.contains_resource::<AssetServer>() {
            world.entity_mut(model).insert(Pending(format!("models/posts/{}.glb", spec.id)));
        }
        life::spawn(world, post, &spec.crew, None, None, 0.0);
    }
}

/// Coming close to a post you have not found marks it found.
fn discover(
    posts: Res<Posts>,
    file: Res<SaveFile>,
    mut save: ResMut<Save>,
    mut prompt: ResMut<Prompt>,
    camera: Query<&GlobalTransform, With<PlayerCamera>>,
    placed: Query<(&GlobalTransform, &Post)>,
) {
    let Some(eye) = camera.iter().next().map(|c| c.translation()) else { return };
    for (at, post) in &placed {
        if at.translation().distance(eye) < FOUND && !save.posts_found.contains(&post.key) {
            save.posts_found.push(post.key.clone());
            file.write(&save);
            prompt.say(format!("Found: {}", posts.post[post.spec].name));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bigger_worlds_get_more_posts_within_bounds() {
        assert_eq!(count(3000.0), 6);
        assert_eq!(count(5000.0), 10);
        assert_eq!(count(17500.0), 12);
    }
}
