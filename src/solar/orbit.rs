//! Where every body is. Orbits are circles and spins are steady, both analytic in the epoch, so
//! the same epoch always puts every world in the same place. Positions here are in the inertial
//! frame, centred on the star, in f64: they reach hundreds of kilometres and are only turned into
//! f32 once they are relative to the anchor.

use bevy::math::{DQuat, DVec3};
use std::collections::HashMap;
use std::f64::consts::TAU;

use crate::system::{Body, System};

/// The id the star goes by wherever a body id is expected.
pub const STAR: &str = "star";

/// A body's pose in the inertial frame at one epoch: its centre, its turn (body coordinates to
/// inertial), the velocity of its centre and its spin.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Pose {
    pub center: DVec3,
    pub rotation: DQuat,
    pub velocity: DVec3,
    /// Angular velocity, inertial.
    pub spin: DVec3,
}

impl Pose {
    const STILL: Pose = Pose { center: DVec3::ZERO, rotation: DQuat::IDENTITY, velocity: DVec3::ZERO, spin: DVec3::ZERO };

    /// A point and velocity in this body's coordinates, in the inertial frame.
    pub fn to_inertial(self, p: DVec3, v: DVec3) -> (DVec3, DVec3) {
        let r = self.rotation * p;
        (self.center + r, self.velocity + self.spin.cross(r) + self.rotation * v)
    }

    /// An inertial point and velocity in this body's coordinates.
    pub fn body_state(self, p: DVec3, v: DVec3) -> (DVec3, DVec3) {
        let r = p - self.center;
        let inv = self.rotation.inverse();
        (inv * r, inv * (v - self.velocity - self.spin.cross(r)))
    }
}

/// The bodies of the solar system level: the star and every body with an orbit, by id.
#[derive(Clone, Debug)]
pub struct Bodies {
    pub bodies: HashMap<String, Body>,
}

impl Bodies {
    pub fn new(system: &System) -> Bodies {
        let mut bodies: HashMap<String, Body> = system.body.iter().filter(|(_, b)| b.orbit.is_some()).map(|(id, b)| (id.clone(), b.clone())).collect();
        bodies.insert(STAR.into(), system.star.body());
        Bodies { bodies }
    }

    pub fn get(&self, id: &str) -> &Body {
        self.bodies.get(id).unwrap_or_else(|| panic!("no body {id} in the system"))
    }

    /// Every id, in a fixed order.
    pub fn ids(&self) -> Vec<String> {
        let mut ids: Vec<String> = self.bodies.keys().cloned().collect();
        ids.sort();
        ids
    }

    /// The body's pose at `epoch` seconds.
    pub fn pose(&self, id: &str, epoch: f64) -> Pose {
        let body = self.get(id);
        let Some(orbit) = &body.orbit else { return Pose::STILL };
        let parent = self.pose(&orbit.parent, epoch);
        let rate = TAU / (orbit.minutes as f64 * 60.0);
        let angle = (orbit.phase as f64).to_radians() + rate * epoch;
        let plane = DQuat::from_rotation_x((orbit.incline as f64).to_radians());
        let d = orbit.distance as f64;
        // Counter-clockwise seen from +Y, like the spin.
        let offset = plane * DVec3::new(angle.cos(), 0.0, -angle.sin()) * d;
        let velocity = plane * DVec3::new(-angle.sin(), 0.0, -angle.cos()) * d * rate;
        let axis = DQuat::from_rotation_z((body.tilt as f64).to_radians());
        let day = body.day_minutes as f64 * 60.0;
        let turn = if day > 0.0 { TAU / day } else { 0.0 };
        Pose {
            center: parent.center + offset,
            rotation: axis * DQuat::from_rotation_y(turn * epoch),
            velocity: parent.velocity + velocity,
            spin: axis * DVec3::Y * turn,
        }
    }

    /// The body whose sphere of influence holds the inertial point `p` at `epoch`: the smallest
    /// one that does, so a moon wins over the world it circles, and the star when nothing else.
    pub fn anchor_at(&self, p: DVec3, epoch: f64) -> String {
        self.ids()
            .into_iter()
            .filter(|id| id != STAR && self.pose(id, epoch).center.distance(p) < self.get(id).soi as f64)
            .min_by(|a, b| self.get(a).soi.total_cmp(&self.get(b).soi))
            .unwrap_or_else(|| STAR.into())
    }

    /// Body coordinates and velocity on `from` re-expressed on `to`, at `epoch`.
    pub fn convert(&self, from: &str, to: &str, epoch: f64, p: DVec3, v: DVec3) -> (DVec3, DVec3) {
        let (p, v) = self.pose(from, epoch).to_inertial(p, v);
        self.pose(to, epoch).body_state(p, v)
    }

    /// The turn taking `from`'s body coordinates to `to`'s, at `epoch`.
    pub fn turn(&self, from: &str, to: &str, epoch: f64) -> DQuat {
        self.pose(to, epoch).rotation.inverse() * self.pose(from, epoch).rotation
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bodies() -> Bodies {
        Bodies::new(&System::load())
    }

    #[test]
    fn the_system_has_the_star_home_and_the_faction_worlds() {
        let b = bodies();
        assert_eq!(b.ids(), ["ash", "bastion", "cinder", "frost", "home", "star"]);
        assert!(b.bodies.get("moon").is_none(), "the debug moon is not in the system");
        assert_eq!(b.get("home").radius, 17500.0);
    }

    #[test]
    fn orbits_are_circles_at_their_distance_and_repeat_every_period() {
        let b = bodies();
        for id in ["home", "bastion", "cinder", "frost"] {
            let o = b.get(id).orbit.clone().unwrap();
            for epoch in [0.0, 1234.5, 98765.0] {
                assert!((b.pose(id, epoch).center.length() - o.distance as f64).abs() < 1e-6, "{id}");
            }
            let period = o.minutes as f64 * 60.0;
            assert!(b.pose(id, 500.0).center.distance(b.pose(id, 500.0 + period).center) < 1e-3, "{id}");
        }
        let (home, ash) = (b.pose("home", 777.0), b.pose("ash", 777.0));
        assert!((home.center.distance(ash.center) - 60000.0).abs() < 1e-6, "Ash circles Haven");
    }

    #[test]
    fn velocities_and_spins_match_how_poses_change() {
        let b = bodies();
        let h = 0.01;
        for id in ["home", "ash", "bastion"] {
            let (before, now, after) = (b.pose(id, 1000.0 - h), b.pose(id, 1000.0), b.pose(id, 1000.0 + h));
            let v = (after.center - before.center) / (2.0 * h);
            assert!(v.distance(now.velocity) < 1e-3, "{id}: {v} vs {}", now.velocity);
            // A point on the equator moves as the spin says.
            let p = DVec3::X * 1000.0;
            let moved = (after.rotation * p - before.rotation * p) / (2.0 * h);
            assert!(moved.distance(now.spin.cross(now.rotation * p)) < 1e-4, "{id}");
        }
    }

    #[test]
    fn converting_there_and_back_is_exact_and_keeps_the_inertial_state() {
        let b = bodies();
        let (p, v) = (DVec3::new(3000.0, 19000.0, -400.0), DVec3::new(5.0, 80.0, -3.0));
        for (from, to) in [("home", "ash"), ("home", STAR), ("ash", STAR), ("bastion", "home")] {
            let (q, w) = b.convert(from, to, 4321.0, p, v);
            let (p2, v2) = b.convert(to, from, 4321.0, q, w);
            assert!(p2.distance(p) < 1e-6 && v2.distance(v) < 1e-6, "{from} -> {to}");
            let (a, c) = (b.pose(from, 4321.0).to_inertial(p, v), b.pose(to, 4321.0).to_inertial(q, w));
            assert!(a.0.distance(c.0) < 1e-6 && a.1.distance(c.1) < 1e-6, "same inertial state");
        }
    }

    #[test]
    fn standing_still_on_a_spinning_world_moves_in_the_inertial_frame() {
        let b = bodies();
        let home = b.pose("home", 0.0);
        let (_, v) = home.to_inertial(DVec3::X * 17500.0, DVec3::ZERO);
        // 2π × 17.5 km per 48 minutes is 38 m/s of spin on top of the orbit.
        assert!(((v - home.velocity).length() - TAU * 17500.0 / 2880.0).abs() < 0.5, "{}", (v - home.velocity).length());
    }

    #[test]
    fn the_anchor_is_the_smallest_sphere_of_influence_holding_the_point() {
        let b = bodies();
        let epoch = 100.0;
        let (home, ash) = (b.pose("home", epoch), b.pose("ash", epoch));
        assert_eq!(b.anchor_at(home.center + DVec3::Y * 18000.0, epoch), "home");
        assert_eq!(b.anchor_at(ash.center + DVec3::Y * 3000.0, epoch), "ash", "the moon wins inside Haven's sphere");
        assert_eq!(b.anchor_at(home.center + DVec3::Y * 200_000.0, epoch), STAR);
        // The worlds' spheres do not overlap at the start, so every flight has a clean handoff.
        for a in ["home", "bastion", "cinder", "frost"] {
            for c in ["home", "bastion", "cinder", "frost"] {
                if a < c {
                    let gap = b.pose(a, 0.0).center.distance(b.pose(c, 0.0).center);
                    assert!(gap > (b.get(a).soi + b.get(c).soi) as f64, "{a} and {c} are {gap} m apart");
                }
            }
        }
    }
}
