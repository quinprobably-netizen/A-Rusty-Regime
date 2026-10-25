//! One terrain chunk: a `GRID` by `GRID` vertex grid over a quadtree node, sampled from the
//! surface function, with a skirt hanging from its rim to hide cracks against coarser
//! neighbours, a triangle-mesh collider and an exact ground lookup on the same triangles.

use avian3d::prelude::*;
use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;

use super::quadtree::{dir_face, face_dir, NodeId, CHUNK};
use crate::surface::{Ground, Sphere};
#[cfg(test)]
use crate::surface::Origin;
#[cfg(test)]
use std::sync::Arc;

/// Vertices per chunk side.
pub const GRID: usize = CHUNK + 1;

/// The grid indices of the border, each corner once: bottom row left to right, right column
/// bottom to top, top row right to left, left column top to bottom.
pub fn rim_order() -> Vec<usize> {
    let last = GRID - 1;
    let at = |i: usize, j: usize| j * GRID + i;
    let bottom = (0..last).map(|i| at(i, 0));
    let right = (0..last).map(|j| at(last, j));
    let top = (1..=last).rev().map(|i| at(i, last));
    let left = (1..=last).rev().map(|j| at(0, j));
    bottom.chain(right).chain(top).chain(left).collect()
}

/// How far the skirt hangs below the rim of a node `arc` meters across.
pub fn skirt_depth(arc: f32) -> f32 {
    (0.05 * arc).max(1.0)
}

/// A built chunk: plain data, made on a worker thread and turned into a mesh and a collider on
/// the main one.
pub struct ChunkMesh {
    pub node: NodeId,
    /// The surface point under the node's centre direction, in body coordinates.
    pub center: Vec3,
    /// Relative to `center`: the grid row-major (`v` outer, `u` inner), then one skirt vertex
    /// per `rim_order()` entry.
    pub positions: Vec<Vec3>,
    pub normals: Vec<Vec3>,
    #[allow(dead_code)] // splat weights for the terrain shader, not drawn yet
    pub weights: Vec<[f32; 4]>,
    pub indices: Vec<[u32; 3]>,
}

/// Samples the surface over `node` and builds its chunk.
pub fn build_chunk(sphere: &Sphere, node: NodeId) -> ChunkMesh {
    let center = sphere.surface_point(node.center_dir());
    let step = node.uv_size() / CHUNK as f32;
    // The grid plus a one-cell apron on each side, so edge normals see their neighbours.
    let side = GRID + 2;
    let apron: Vec<Vec3> = (0..side * side)
        .map(|k| {
            let (i, j) = ((k % side) as f32 - 1.0, (k / side) as f32 - 1.0);
            sphere.surface_point(face_dir(node.face, node.uv_min() + Vec2::new(i, j) * step)) - center
        })
        .collect();
    let p = |i: usize, j: usize| apron[(j + 1) * side + i + 1];
    let mut positions = Vec::with_capacity(GRID * GRID + 4 * (GRID - 1));
    let mut normals = Vec::with_capacity(positions.capacity());
    for j in 0..GRID {
        for i in 0..GRID {
            // Apron coordinates are offset by one, so (i, j) - 1 never underflows.
            let a = |di: usize, dj: usize| apron[(j + dj) * side + i + di];
            let n = (a(1, 2) - a(1, 0)).cross(a(2, 1) - a(0, 1)).normalize();
            let up = center + p(i, j);
            positions.push(p(i, j));
            normals.push(if n.dot(up) < 0.0 { -n } else { n });
        }
    }
    let rim = rim_order();
    let depth = skirt_depth(node.arc(sphere.sea_radius()));
    for &r in &rim {
        let down = (center + positions[r]).normalize() * depth;
        positions.push(positions[r] - down);
        normals.push(normals[r]);
    }
    let mut indices = Vec::with_capacity(2 * CHUNK * CHUNK + 2 * rim.len());
    let g = GRID as u32;
    for j in 0..CHUNK as u32 {
        for i in 0..CHUNK as u32 {
            // Diagonal from (i + 1, j) to (i, j + 1); u × v points out of the body.
            let k = j * g + i;
            indices.push([k, k + 1, k + g]);
            indices.push([k + 1, k + g + 1, k + g]);
        }
    }
    // The rim runs counterclockwise seen from outside; each wall quad lies in a plane through
    // the body centre, wound to face away from the chunk, so a crack seen from a neighbour
    // shows the wall under back-face culling.
    let skirt = (GRID * GRID) as u32;
    for k in 0..rim.len() {
        let next = (k + 1) % rim.len();
        let (a, b) = (rim[k] as u32, rim[next] as u32);
        let (sa, sb) = (skirt + k as u32, skirt + next as u32);
        indices.push([a, sa, b]);
        indices.push([b, sa, sb]);
    }
    let weights = vec![[1.0, 0.0, 0.0, 0.0]; positions.len()];
    ChunkMesh { node, center, positions, normals, weights, indices }
}

impl ChunkMesh {
    pub fn mesh(&self) -> Mesh {
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.positions.clone())
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.normals.clone())
            .with_inserted_indices(Indices::U32(self.indices.iter().flatten().copied().collect()))
    }

    pub fn collider(&self) -> Collider {
        Collider::trimesh(self.positions.clone(), self.indices.clone())
    }

    /// Where the ray from the body centre along unit `dir` meets this chunk's grid, on the
    /// same triangles the mesh and collider use; `None` if `dir` is outside the node.
    pub fn ground_on(&self, dir: Vec3) -> Option<Ground> {
        let (face, uv) = dir_face(dir);
        if face != self.node.face {
            return None;
        }
        let g = (uv - self.node.uv_min()) / self.node.uv_size() * CHUNK as f32;
        // A hair of slack so the far rim, rounded either way, still counts.
        let (lo, hi) = (-1e-3, CHUNK as f32 + 1e-3);
        if g.x < lo || g.y < lo || g.x > hi || g.y > hi {
            return None;
        }
        let cell = g.clamp(Vec2::ZERO, Vec2::splat(CHUNK as f32)).floor().min(Vec2::splat(CHUNK as f32 - 1.0));
        let k = cell.y as usize * GRID + cell.x as usize;
        // Cell edges are great circles, so the cell is exact; across the diagonal, take the
        // triangle the ray actually passes through.
        let first = [k, k + 1, k + GRID];
        let second = [k + 1, k + GRID + 1, k + GRID];
        let (tri, hit, w) = [first, second]
            .into_iter()
            .map(|tri| {
                let (hit, w) = self.hit(tri, dir);
                (tri, hit, w)
            })
            .max_by(|a, b| a.2.min_element().total_cmp(&b.2.min_element()))?;
        let normal = (self.normals[tri[0]] * w.x + self.normals[tri[1]] * w.y + self.normals[tri[2]] * w.z).normalize();
        Some(Ground { point: hit, normal })
    }

    /// The body-space point where the ray along `dir` meets the plane of triangle `tri`, and
    /// its barycentric weights there.
    fn hit(&self, tri: [usize; 3], dir: Vec3) -> (Vec3, Vec3) {
        let [a, b, c] = tri.map(|i| self.positions[i]);
        let n = (b - a).cross(c - a);
        let t = n.dot(self.center + a) / n.dot(dir);
        let p = dir * t - self.center;
        let (e0, e1, ep) = (b - a, c - a, p - a);
        let (d00, d01, d11) = (e0.dot(e0), e0.dot(e1), e1.dot(e1));
        let (d20, d21) = (ep.dot(e0), ep.dot(e1));
        let den = d00 * d11 - d01 * d01;
        let (wb, wc) = ((d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den);
        (dir * t, Vec3::new(1.0 - wb - wc, wb, wc))
    }
}

/// The leaves at `depth` whose centre on the ground is within `reach` of `around` (body
/// coordinates), found by descending only into nodes that could hold one.
pub fn leaves_near(sphere: &Sphere, depth: u8, around: Vec3, reach: f32) -> Vec<NodeId> {
    use std::f32::consts::FRAC_PI_4;
    // A leaf can only qualify if its centre direction is within this angle of `around`'s.
    let lowest = (sphere.sea_radius() - sphere.body.height.abs()).max(1.0);
    let spread = 2.0 * (reach / (2.0 * lowest)).min(1.0).asin();
    let toward = around.normalize();
    let mut leaves = Vec::new();
    let mut stack = NodeId::roots().to_vec();
    while let Some(node) = stack.pop() {
        if node.depth < depth {
            // Directions in a node lie within π/4 per uv unit along each axis of its centre.
            let extent = FRAC_PI_4 * node.uv_size();
            if node.center_dir().dot(toward).clamp(-1.0, 1.0).acos() <= extent + spread {
                stack.extend(node.children());
            }
        } else if sphere.surface_point(node.center_dir()).distance(around) <= reach {
            leaves.push(node);
        }
    }
    leaves
}

/// Static colliders for every finest-depth leaf (cells no bigger than `cell`) whose centre is
/// within `radius` plus a chunk side of `around` (body coordinates), for headless tests.
#[cfg(test)]
pub fn spawn_ground(world: &mut World, sphere: &Sphere, origin: &Origin, cell: f32, around: Vec3, radius: f32) -> Vec<Arc<ChunkMesh>> {
    let depth = super::quadtree::finest_depth(sphere.sea_radius(), cell);
    let reach = radius + NodeId::leaf_at(around, depth).arc(sphere.sea_radius());
    let mut meshes = Vec::new();
    for node in leaves_near(sphere, depth, around, reach) {
        let chunk = Arc::new(build_chunk(sphere, node));
        world.spawn((RigidBody::Static, chunk.collider(), Transform::from_translation(origin.world(chunk.center))));
        meshes.push(chunk);
    }
    meshes
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::system::Body;

    #[test]
    fn chunk_vertices_lie_on_the_surface_and_face_out() {
        let s = Sphere::new(Body::test_moon());
        let node = NodeId::leaf_at(Vec3::new(0.3, 0.9, 0.3).normalize(), 5);
        let c = build_chunk(&s, node);
        assert_eq!(c.positions.len(), GRID * GRID + 4 * (GRID - 1));
        for (i, p) in c.positions.iter().take(GRID * GRID).enumerate() {
            let world = c.center + *p;
            let dir = world.normalize();
            assert!((world.length() - (s.sea_radius() + s.height(dir))).abs() < 1e-2, "vertex {i}");
            assert!(c.normals[i].dot(dir) > 0.5);
        }
        for tri in &c.indices {
            let [a, b, d] = tri.map(|i| c.positions[i as usize]);
            if tri.iter().any(|&i| i as usize >= GRID * GRID) {
                // Skirt walls face away from the chunk; positions are chunk-local.
                assert!((b - a).cross(d - a).dot((a + b + d) / 3.0) >= -1e-3, "skirt wound away from the chunk");
            } else {
                assert!((b - a).cross(d - a).dot(c.center) >= -1e-3, "wound outward");
            }
        }
    }

    #[test]
    fn skirt_hangs_below_the_rim() {
        let s = Sphere::new(Body::test_moon());
        let node = NodeId::leaf_at(Vec3::X, 5);
        let c = build_chunk(&s, node);
        let depth = skirt_depth(node.arc(2000.0));
        for (k, rim) in rim_order().into_iter().enumerate() {
            let (top, skirt) = (c.center + c.positions[rim], c.center + c.positions[GRID * GRID + k]);
            assert!((top.length() - skirt.length() - depth).abs() < 1e-3 && top.normalize().dot(skirt.normalize()) > 0.999999);
        }
    }

    #[test]
    fn ground_on_interpolates_the_grid() {
        let s = Sphere::new(Body::test_moon());
        let node = NodeId::leaf_at(Vec3::Z, 5);
        let c = build_chunk(&s, node);
        for i in [0usize, 17, GRID * GRID - 1] {
            let v = c.center + c.positions[i];
            assert!(c.ground_on(v.normalize()).unwrap().point.distance(v) < 1e-3);
        }
        let (a, b) = (c.center + c.positions[5], c.center + c.positions[6]);
        assert!(c.ground_on((a + b).normalize()).unwrap().point.distance((a + b) / 2.0) < 1e-2);
        assert!(c.ground_on(Vec3::NEG_Z).is_none());
    }
}
