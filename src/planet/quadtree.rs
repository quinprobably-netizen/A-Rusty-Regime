//! The planet's terrain quadtree: a cube projected onto the sphere, each face a quadtree of
//! chunks `CHUNK` cells on a side. Pure geometry; the chunk meshes and streaming build on it.

use bevy::prelude::*;
use std::collections::HashSet;
use std::f32::consts::{FRAC_PI_4, PI};

/// Cells per chunk side.
pub const CHUNK: usize = 32;

/// The deepest a tree goes, whatever the cell size asks for.
const MAX_DEPTH: u8 = 20;

/// One chunk: face `0..6` (+X, -X, +Y, -Y, +Z, -Z), `depth` 0 for the whole face, and its column
/// `x` and row `y` among the `2^depth` per side, counted from the face's (-1, -1) corner.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct NodeId {
    pub face: u8,
    pub depth: u8,
    pub x: u32,
    pub y: u32,
}

/// The face's outward normal, tangent (u) and bitangent (v); tangent × bitangent = normal.
fn face_axes(face: u8) -> (Vec3, Vec3, Vec3) {
    match face {
        0 => (Vec3::X, Vec3::NEG_Z, Vec3::Y),
        1 => (Vec3::NEG_X, Vec3::Z, Vec3::Y),
        2 => (Vec3::Y, Vec3::X, Vec3::NEG_Z),
        3 => (Vec3::NEG_Y, Vec3::X, Vec3::Z),
        4 => (Vec3::Z, Vec3::X, Vec3::Y),
        _ => (Vec3::NEG_Z, Vec3::NEG_X, Vec3::Y),
    }
}

/// The unit direction at `uv` (each in [-1, 1]) on `face`. The tangent warp spreads cells
/// evenly over the sphere instead of bunching them at the face centres.
pub fn face_dir(face: u8, uv: Vec2) -> Vec3 {
    let (n, t, b) = face_axes(face);
    (n + t * (uv.x * FRAC_PI_4).tan() + b * (uv.y * FRAC_PI_4).tan()).normalize()
}

/// The face a direction falls on (its dominant axis; ties go to X, then Y) and its uv there.
pub fn dir_face(dir: Vec3) -> (u8, Vec2) {
    let a = dir.abs();
    let face = if a.x >= a.y && a.x >= a.z {
        if dir.x >= 0.0 { 0 } else { 1 }
    } else if a.y >= a.z {
        if dir.y >= 0.0 { 2 } else { 3 }
    } else if dir.z >= 0.0 {
        4
    } else {
        5
    };
    let (n, t, b) = face_axes(face);
    let out = dir.dot(n);
    let uv = Vec2::new(dir.dot(t) / out, dir.dot(b) / out);
    (face, Vec2::new(uv.x.atan(), uv.y.atan()) / FRAC_PI_4)
}

impl NodeId {
    pub fn roots() -> [NodeId; 6] {
        std::array::from_fn(|f| NodeId { face: f as u8, depth: 0, x: 0, y: 0 })
    }

    pub fn children(self) -> [NodeId; 4] {
        std::array::from_fn(|i| NodeId { face: self.face, depth: self.depth + 1, x: self.x * 2 + (i as u32 & 1), y: self.y * 2 + (i as u32 >> 1) })
    }

    pub fn parent(self) -> Option<NodeId> {
        (self.depth > 0).then(|| NodeId { face: self.face, depth: self.depth - 1, x: self.x >> 1, y: self.y >> 1 })
    }

    /// The corner of this node nearest the face's (-1, -1).
    pub fn uv_min(self) -> Vec2 {
        Vec2::new(self.x as f32, self.y as f32) * self.uv_size() - Vec2::ONE
    }

    /// The node's side in uv: 2 / 2^depth.
    pub fn uv_size(self) -> f32 {
        2.0 / (1u32 << self.depth) as f32
    }

    pub fn center_dir(self) -> Vec3 {
        face_dir(self.face, self.uv_min() + Vec2::splat(self.uv_size() * 0.5))
    }

    /// The node's side along the ground on a sphere of `radius` (exact at the face centre line).
    pub fn arc(self, radius: f32) -> f32 {
        PI / 2.0 * radius / (1u32 << self.depth) as f32
    }

    pub fn cell(self, radius: f32) -> f32 {
        self.arc(radius) / CHUNK as f32
    }

    pub fn contains(self, dir: Vec3) -> bool {
        NodeId::leaf_at(dir, self.depth) == self
    }

    /// Strictly: a node is not its own ancestor.
    #[allow(dead_code)] // only the tests ask
    pub fn is_ancestor_of(self, other: NodeId) -> bool {
        let up = other.depth.wrapping_sub(self.depth);
        other.depth > self.depth && other.face == self.face && other.x >> up == self.x && other.y >> up == self.y
    }

    /// The node at `depth` holding `dir`. Every direction lands in exactly one node per depth:
    /// cells are half-open, and the far edge of a face belongs to its last row and column.
    pub fn leaf_at(dir: Vec3, depth: u8) -> NodeId {
        let (face, uv) = dir_face(dir);
        let n = 1u32 << depth;
        let cell = |t: f32| (((t + 1.0) * 0.5 * n as f32).floor().max(0.0) as u32).min(n - 1);
        NodeId { face, depth, x: cell(uv.x), y: cell(uv.y) }
    }
}

/// The shallowest depth whose cells are no bigger than `cell`, capped at 20.
pub fn finest_depth(radius: f32, cell: f32) -> u8 {
    let root = NodeId { face: 0, depth: 0, x: 0, y: 0 };
    (0..MAX_DEPTH).find(|&d| NodeId { depth: d, ..root }.cell(radius) <= cell).unwrap_or(MAX_DEPTH)
}

/// How far `focus` (body space) is from the node, roughly: its distance from the node's centre
/// on the ground less three quarters of the node's side, never below zero.
pub fn node_distance(node: NodeId, radius: f32, focus: Vec3) -> f32 {
    (focus.distance(node.center_dir() * radius) - 0.75 * node.arc(radius)).max(0.0)
}

/// The leaves to draw around `focus`. A node splits when it is nearer than `split` of its own
/// sides; one that was split in `previous` stays split until it is farther than `merge`, so a
/// focus wandering at a boundary does not rebuild chunks every frame. Nodes at `max_depth` are
/// always leaves.
pub fn select_leaves(radius: f32, max_depth: u8, focus: Vec3, split: f32, merge: f32, previous: &HashSet<NodeId>) -> HashSet<NodeId> {
    let mut was_split = HashSet::new();
    for leaf in previous {
        let mut node = *leaf;
        while let Some(parent) = node.parent() {
            if !was_split.insert(parent) {
                break;
            }
            node = parent;
        }
    }
    let mut leaves = HashSet::new();
    let mut stack = NodeId::roots().to_vec();
    while let Some(node) = stack.pop() {
        let (near, arc) = (node_distance(node, radius, focus), node.arc(radius));
        let splits = node.depth < max_depth && if was_split.contains(&node) { near <= merge * arc } else { near < split * arc };
        if splits {
            stack.extend(node.children());
        } else {
            leaves.insert(node);
        }
    }
    leaves
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::surface::testing::random_dirs;

    #[test]
    fn face_mapping_round_trips() {
        let seams = [Vec3::new(1.0, 1.0, 0.0), Vec3::ONE, Vec3::new(-1.0, 1.0, 1.0)].map(Vec3::normalize);
        for dir in random_dirs(500).into_iter().chain(seams) {
            let (face, uv) = dir_face(dir);
            assert!(uv.abs().max_element() <= 1.0 + 1e-6);
            assert!(face_dir(face, uv).dot(dir) > 1.0 - 1e-6, "{dir}");
        }
    }

    #[test]
    fn children_tile_their_parent() {
        let n = NodeId { face: 2, depth: 3, x: 5, y: 1 };
        let kids = n.children();
        assert!(kids.iter().all(|k| k.parent() == Some(n) && (k.uv_size() - n.uv_size() / 2.0).abs() < 1e-9));
        for i in 0..200 {
            let uv = n.uv_min() + Vec2::new(((i * 7) % 23) as f32 / 23.0, ((i * 11) % 19) as f32 / 19.0) * n.uv_size();
            assert_eq!(kids.iter().filter(|k| k.contains(face_dir(2, uv))).count(), 1);
        }
    }

    #[test]
    fn every_direction_has_exactly_one_leaf() {
        let focus = Vec3::new(0.0, 0.6, 0.8).normalize() * 2000.0;
        let leaves = select_leaves(2000.0, 8, focus, 2.5, 3.0, &HashSet::new());
        let seams = [Vec3::new(1.0, 1.0, 0.0), Vec3::new(1.0, 0.0, 1.0), Vec3::ONE, Vec3::new(1.0, -1.0, 1.0), Vec3::new(0.0, 1.0, 1.0)].map(Vec3::normalize);
        for dir in random_dirs(2000).into_iter().chain(seams) {
            assert_eq!(leaves.iter().filter(|l| l.contains(dir)).count(), 1, "{dir}");
            let finest = NodeId::leaf_at(dir, 8);
            assert!(leaves.iter().any(|l| *l == finest || l.is_ancestor_of(finest)));
        }
    }

    #[test]
    fn splitting_follows_the_focus_with_hysteresis() {
        let focus = Vec3::X * 2000.0;
        let a = select_leaves(2000.0, 8, focus, 2.5, 3.0, &HashSet::new());
        assert!(a.contains(&NodeId::leaf_at(Vec3::X, 8)), "the leaf under the focus is finest");
        assert!(a.len() < 800, "{}", a.len());
        let high = select_leaves(2000.0, 8, Vec3::X * 12000.0, 2.5, 3.0, &HashSet::new());
        assert!(high.iter().all(|l| l.depth <= 2) && high.len() <= 96, "{}", high.len());
        // 3 m is inside the hysteresis band of every depth (half an arc, 6 m at the finest), so going back changes nothing.
        let nudged = select_leaves(2000.0, 8, focus + Vec3::Z * 3.0, 2.5, 3.0, &a);
        assert_eq!(select_leaves(2000.0, 8, focus, 2.5, 3.0, &nudged), nudged);
        // 10 m swaps a handful of finest leaves, not the whole ring.
        let moved = select_leaves(2000.0, 8, focus + Vec3::Z * 10.0, 2.5, 3.0, &a);
        assert!(moved.symmetric_difference(&a).count() <= 60, "{}", moved.symmetric_difference(&a).count());
    }

    /// Walks the focus along the equator from +X through `path` (metres along the ground, one
    /// selection per entry). Returns the total leaves added and removed, and how often each
    /// node was added.
    /// Walks the focus along the equator from +X through `path` (metres along the ground, one
    /// selection per entry). Returns the total leaves added and removed, and how often each
    /// node was added.
    fn walk(path: &[f32], merge: f32) -> (usize, std::collections::HashMap<NodeId, usize>) {
        let at = |s: f32| Quat::from_rotation_y(-s / 2000.0) * Vec3::X * 2000.0;
        let mut leaves = select_leaves(2000.0, 8, at(0.0), 2.5, merge, &HashSet::new());
        let (mut churn, mut added) = (0, std::collections::HashMap::new());
        for &s in path {
            let next = select_leaves(2000.0, 8, at(s), 2.5, merge, &leaves);
            assert!(next.len() < 1000, "{} leaves at {s} m", next.len());
            churn += next.symmetric_difference(&leaves).count();
            for n in next.difference(&leaves) {
                *added.entry(*n).or_insert(0) += 1;
            }
            leaves = next;
        }
        (churn, added)
    }

    #[test]
    fn a_kilometre_walk_splits_and_merges_a_bounded_number_of_times() {
        // Straight on in 1 m steps, and the same kilometre wobbling 3 m on and 2 m back.
        let straight: Vec<f32> = (1..=1000).map(|i| i as f32).collect();
        let wobble: Vec<f32> = (0..1000).flat_map(|i| [i as f32 + 3.0, i as f32 + 1.0]).collect();
        let (churn, added) = walk(&straight, 3.0);
        // A node is added at most twice: when its parent splits, and when its children merge
        // back into it behind the focus. Nothing is rebuilt more often than that.
        assert!(added.values().all(|&n| n <= 2), "a node added {:?} times", added.values().max());
        // The 2 m steps back are inside the hysteresis band, so wobbling costs nothing...
        let (wobble_churn, _) = walk(&wobble, 3.0);
        assert_eq!(wobble_churn, churn, "wobbling churned {wobble_churn} leaves, walking straight {churn}");
        // ...where with no band it would rebuild the edges over and over.
        let (no_band, _) = walk(&wobble, 2.5);
        assert!(no_band > 3 * churn, "{no_band} without the band, {churn} with it");
    }

    #[test]
    fn finest_depth_matches_the_cell() {
        assert_eq!(finest_depth(17500.0, 0.5), 11);
        assert_eq!(finest_depth(2000.0, 0.5), 8);
        assert_eq!(finest_depth(2000.0, 4.0), 5);
        assert_eq!(finest_depth(2000.0, 1e9), 0);
        assert!((NodeId::leaf_at(Vec3::X, 11).cell(17500.0) - 0.42).abs() < 0.01);
    }
}
