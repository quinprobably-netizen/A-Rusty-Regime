//! Roads (hyper-realism stage R6): packed tracks from base camp to the other five sites, routed
//! around the steepest ground and carved into the heightmap with a smoothed profile, so vehicles
//! have somewhere to go fast. Tyres grip better on them (the tarmac curve at full grip) than on
//! the grass and dirt around them.

use std::collections::HashMap;

use bevy::prelude::*;

use crate::island::Placed;
use crate::terrain::Heightmap;
use crate::tuning::Island;

/// Half the drivable width, and the bank blended down to the terrain beyond it.
pub const HALF_WIDTH: f32 = 3.5;
pub const BLEND: f32 = 6.0;
/// Steepest a road may climb.
pub const MAX_GRADE: f32 = 0.15;

/// Road centre lines as segments `(a, b)` with heights at each end.
#[derive(Resource, Clone, Debug, Default)]
pub struct Roads {
    pub segments: Vec<(Vec3, Vec3)>,
}

impl Roads {
    /// Distance from `p` (x, z) to the nearest centre line, and the road height there.
    pub fn nearest(&self, p: Vec2) -> Option<(f32, f32)> {
        let mut best: Option<(f32, f32)> = None;
        for (a, b) in &self.segments {
            let (a2, b2) = (a.xz(), b.xz());
            let ab = b2 - a2;
            let t = ((p - a2).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
            let d = p.distance(a2 + ab * t);
            if best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, a.y + (b.y - a.y) * t));
            }
        }
        best
    }

    pub fn on_road(&self, p: Vec2) -> bool {
        self.nearest(p).is_some_and(|(d, _)| d < HALF_WIDTH + 0.5)
    }
}

/// A route from `from` to `to` in 25 m steps, each step turning up to 50° off the straight line to
/// avoid climbing, then smoothed.
fn route(hm: &Heightmap, from: Vec2, to: Vec2) -> Vec<Vec2> {
    const STEP: f32 = 25.0;
    let mut pts = vec![from];
    let mut p = from;
    for _ in 0..400 {
        let to_goal = to - p;
        if to_goal.length() < STEP * 1.5 {
            break;
        }
        let goal_dir = to_goal.normalize();
        let h = hm.height_at(p.x, p.y);
        let mut best = (f32::MAX, p);
        for k in -5..=5 {
            let a = k as f32 * 10f32.to_radians();
            let dir = Vec2::from_angle(a).rotate(goal_dir);
            let q = p + dir * STEP;
            let grade = (hm.height_at(q.x, q.y) - h).abs() / STEP;
            // Steeper than about 8% costs a lot; turning away from the goal costs a little.
            let cost = (grade - 0.08).max(0.0) * 40.0 + grade * 4.0 + (1.0 - dir.dot(goal_dir)) * 2.5;
            if cost < best.0 {
                best = (cost, q);
            }
        }
        p = best.1;
        pts.push(p);
    }
    pts.push(to);
    // Corner cutting: two passes of averaging the inner points.
    for _ in 0..2 {
        let copy = pts.clone();
        for i in 1..pts.len() - 1 {
            pts[i] = (copy[i - 1] + copy[i] * 2.0 + copy[i + 1]) / 4.0;
        }
    }
    pts
}

/// Plans the roads from base camp to each site and carves them in. Ends sit at each site's edge so
/// the pads stay untouched.
pub fn carve(hm: &mut Heightmap, sites: &[Placed], island: &Island) -> Roads {
    let mut roads = Roads::default();
    let Some(camp) = sites.first() else { return roads };
    for site in sites.iter().skip(1).take(5) {
        let dir = (site.center - camp.center).normalize_or_zero();
        let from = camp.center + dir * (camp.radius + 4.0);
        let to = site.center - dir * (site.radius + 4.0);
        let pts = route(hm, from, to);
        // Height profile: the terrain under it, averaged along the road, above the sea.
        let mut hs: Vec<f32> = pts.iter().map(|p| hm.height_at(p.x, p.y)).collect();
        for _ in 0..4 {
            let copy = hs.clone();
            for i in 1..hs.len() - 1 {
                let lo = i.saturating_sub(2);
                let hi = (i + 2).min(hs.len() - 1);
                hs[i] = copy[lo..=hi].iter().sum::<f32>() / (hi - lo + 1) as f32;
            }
        }
        // No steeper than MAX_GRADE: cut the crests and fill the dips, both ways along the road.
        for i in 1..hs.len() {
            let run = pts[i].distance(pts[i - 1]) * MAX_GRADE;
            hs[i] = hs[i].clamp(hs[i - 1] - run, hs[i - 1] + run);
        }
        for i in (0..hs.len() - 1).rev() {
            let run = pts[i].distance(pts[i + 1]) * MAX_GRADE;
            hs[i] = hs[i].clamp(hs[i + 1] - run, hs[i + 1] + run);
        }
        for h in &mut hs {
            *h = h.max(island.water_level + 1.0);
        }
        for i in 0..pts.len() - 1 {
            roads.segments.push((pts[i].extend(hs[i]).xzy(), pts[i + 1].extend(hs[i + 1]).xzy()));
        }
    }
    // Every sample near a road takes the nearest road's height, blended out over the bank.
    let mut touched: HashMap<(usize, usize), (f32, f32)> = HashMap::new();
    let reach = HALF_WIDTH + BLEND;
    let to_index = |v: f32| ((v + hm.size / 2.0) / hm.cell).round() as isize;
    for (a, b) in &roads.segments {
        let lo = a.xz().min(b.xz()) - Vec2::splat(reach);
        let hi = a.xz().max(b.xz()) + Vec2::splat(reach);
        let n = hm.n as isize;
        for zi in to_index(lo.y).max(0)..=to_index(hi.y).min(n - 1) {
            for xi in to_index(lo.x).max(0)..=to_index(hi.x).min(n - 1) {
                let p = hm.sample_pos(xi as usize, zi as usize);
                let ab = b.xz() - a.xz();
                let t = ((p - a.xz()).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
                let d = p.distance(a.xz() + ab * t);
                if d > reach {
                    continue;
                }
                let h = a.y + (b.y - a.y) * t;
                let e = touched.entry((xi as usize, zi as usize)).or_insert((d, h));
                if d < e.0 {
                    *e = (d, h);
                }
            }
        }
    }
    for ((xi, zi), (d, h)) in touched {
        let w = 1.0 - ((d - HALF_WIDTH) / BLEND).clamp(0.0, 1.0);
        let w = w * w * (3.0 - 2.0 * w);
        let i = zi * hm.n + xi;
        hm.heights[i] += (h - hm.heights[i]) * w;
    }
    roads
}
