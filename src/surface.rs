//! Where "up" is. Every system that needs up, altitude, gravity, a tangent frame or the ground
//! asks `Surface`, so the same code runs on the flat island and on a round body. `Origin` is
//! the sliding origin: body-space positions minus a quantized offset give world positions near
//! the player, where f32 stays precise.

use bevy::prelude::*;
use fastnoise_lite::{FastNoiseLite, FractalType, NoiseType};
use std::sync::Arc;

use crate::system::Body;

/// The ground the world stands on.
#[derive(Resource, Clone, Default)]
pub enum Surface {
    /// The old world: up is +Y, sea level is y = 0.
    #[default]
    Flat,
    /// A round body centred at the body-space origin, spinning about +Y.
    Sphere(Arc<Sphere>),
}

/// A round body's shape: plain data, shareable with worker threads.
pub struct Sphere {
    pub body: Body,
    relief: FastNoiseLite,
    rubble: FastNoiseLite,
}

impl Clone for Sphere {
    // The noise generators are rebuilt from the body's seed, so the clone is identical.
    fn clone(&self) -> Self {
        Sphere::new(self.body.clone())
    }
}

/// Amplitude of the small rubble layer, in meters.
const RUBBLE: f32 = 0.15;

impl Sphere {
    pub fn new(body: Body) -> Sphere {
        let mut relief = FastNoiseLite::with_seed(body.seed as i32);
        relief.set_noise_type(Some(NoiseType::OpenSimplex2));
        relief.set_fractal_type(Some(FractalType::FBm));
        relief.set_fractal_octaves(Some(8));
        relief.set_fractal_gain(Some(0.55));
        relief.set_frequency(Some(1.0 / body.wavelength));
        let mut rubble = FastNoiseLite::with_seed(body.seed.wrapping_add(1) as i32);
        rubble.set_noise_type(Some(NoiseType::OpenSimplex2));
        rubble.set_fractal_type(Some(FractalType::FBm));
        rubble.set_fractal_octaves(Some(2));
        rubble.set_frequency(Some(1.0 / 1.6));
        Sphere { body, relief, rubble }
    }

    /// Radius of the sea surface, altitude 0.
    pub fn sea_radius(&self) -> f32 {
        self.body.radius + self.body.sea_level
    }

    /// Terrain height in meters above sea level along the unit direction `dir`. A pure
    /// function of the body's seed and `dir`.
    pub fn height(&self, dir: Vec3) -> f32 {
        let s = dir * self.body.radius;
        // Clamped so the power below never sees a negative base.
        let n = self.relief.get_noise_3d(s.x, s.y, s.z).clamp(-1.0, 1.0);
        // Raised to a power so valleys stay low and the peaks stand out.
        let h = ((0.5 + 0.5 * n).powf(1.6) - 0.3) * self.body.height;
        h + RUBBLE * self.rubble.get_noise_3d(s.x, s.y, s.z)
    }

    /// The point `altitude` meters above sea level along unit `dir`.
    pub fn point(&self, dir: Vec3, altitude: f32) -> Vec3 {
        dir * (self.sea_radius() + altitude)
    }

    /// The terrain surface along unit `dir`.
    pub fn surface_point(&self, dir: Vec3) -> Vec3 {
        self.point(dir, self.height(dir))
    }

    /// The terrain directly below (or above) `p`, from the height function.
    pub fn ground(&self, p: Vec3) -> Ground {
        let (east, up, north) = sphere_basis(p);
        let point = self.surface_point(up);
        // Neighbours 1 m away along each tangent.
        let step = 1.0 / point.length().max(1.0);
        let e = self.surface_point((up + east * step).normalize()) - point;
        let n = self.surface_point((up + north * step).normalize()) - point;
        let normal = e.cross(n).normalize();
        Ground { point, normal: if normal.dot(up) < 0.0 { -normal } else { normal } }
    }
}

/// A point on the ground and the outward normal there.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Ground {
    pub point: Vec3,
    pub normal: Vec3,
}

/// Closer than this to the spin axis there is no north.
const POLE: f32 = 5.0;

impl Surface {
    pub fn up(&self, p: Vec3) -> Vec3 {
        match self {
            Surface::Flat => Vec3::Y,
            Surface::Sphere(_) => p.try_normalize().unwrap_or(Vec3::Y),
        }
    }

    /// Meters above sea level.
    pub fn altitude(&self, p: Vec3) -> f32 {
        match self {
            Surface::Flat => p.y,
            Surface::Sphere(s) => p.length() - s.sea_radius(),
        }
    }

    /// Gravitational acceleration at `p`. `flat_g` is the flat world's strength; a sphere uses
    /// its body's gravity at sea level, falling off with the inverse square.
    pub fn gravity(&self, p: Vec3, flat_g: f32) -> Vec3 {
        match self {
            Surface::Flat => Vec3::NEG_Y * flat_g,
            Surface::Sphere(s) => {
                let r = s.sea_radius() / p.length().max(1.0);
                -self.up(p) * s.body.gravity * r * r
            }
        }
    }

    /// The local tangent frame at `p`: local +Y up, local -Z north (toward the spin axis +Y),
    /// local +X east.
    pub fn frame(&self, p: Vec3) -> Quat {
        match self {
            Surface::Flat => Quat::IDENTITY,
            Surface::Sphere(_) => {
                let (east, up, north) = sphere_basis(p);
                Quat::from_mat3(&Mat3::from_cols(east, up, -north))
            }
        }
    }

    /// The tangent direction toward the north pole, `None` within `POLE` meters of the axis.
    #[allow(dead_code)] // only the tests read it so far
    pub fn north(&self, p: Vec3) -> Option<Vec3> {
        match self {
            Surface::Flat => Some(Vec3::NEG_Z),
            Surface::Sphere(_) if Vec2::new(p.x, p.z).length() < POLE => None,
            Surface::Sphere(_) => Some(sphere_basis(p).2),
        }
    }

    /// The terrain directly below (or above) `p`, from the height function.
    #[allow(dead_code)] // only the tests read it so far
    pub fn ground(&self, p: Vec3) -> Ground {
        match self {
            Surface::Flat => Ground { point: Vec3::new(p.x, 0.0, p.z), normal: Vec3::Y },
            Surface::Sphere(s) => s.ground(p),
        }
    }
}

/// Orthonormal `(east, up, north)` at `p` on a sphere. East is `up` turned a quarter about the
/// spin axis, flattened: no cancellation, so it stays precise close to the poles.
///
/// Within `POLE` metres of the axis there is no north, and north falls back to the +X meridian
/// so the frame stays defined. That fallback is a yaw snap against the frame just outside it.
/// The player only meets it when spawned or respawned there through `Surface::frame`: once
/// moving they carry their own frame across the pole instead.
fn sphere_basis(p: Vec3) -> (Vec3, Vec3, Vec3) {
    let up = p.try_normalize().unwrap_or(Vec3::Y);
    if Vec2::new(p.x, p.z).length() < POLE {
        let north = (Vec3::X - up * up.x).normalize();
        return (north.cross(up), up, north);
    }
    let east = Vec3::new(up.z, 0.0, -up.x).normalize();
    (east, up, up.cross(east))
}

/// Origin offsets are multiples of this many meters.
pub const QUANTUM: f32 = 36.0;

/// The sliding origin: world position = body position - `offset`.
#[derive(Resource, Clone, Copy, Default, Debug)]
pub struct Origin {
    pub offset: Vec3,
}

impl Origin {
    /// The origin nearest `body` whose components are multiples of `quantum`.
    pub fn at(body: Vec3, quantum: f32) -> Origin {
        Origin { offset: (body / quantum).round() * quantum }
    }

    pub fn world(&self, body: Vec3) -> Vec3 {
        body - self.offset
    }

    pub fn body(&self, world: Vec3) -> Vec3 {
        world + self.offset
    }
}

#[cfg(test)]
pub mod testing {
    use bevy::prelude::*;

    /// `n` deterministic, roughly uniform unit vectors from a fixed-seed LCG.
    pub fn random_dirs(n: usize) -> Vec<Vec3> {
        let mut state: u64 = 0x2545_f491_4f6c_dd1d;
        let mut next = move || {
            state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
            (state >> 40) as f32 / (1u64 << 24) as f32
        };
        (0..n)
            .map(|_| {
                let z = 2.0 * next() - 1.0;
                let phi = std::f32::consts::TAU * next();
                let r = (1.0 - z * z).max(0.0).sqrt();
                Vec3::new(r * phi.cos(), z, r * phi.sin())
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sphere_height_is_deterministic_and_bounded() {
        let (a, b) = (Sphere::new(Body::test_moon()), Sphere::new(Body::test_moon()));
        let other = Sphere::new(Body { seed: 12, ..Body::test_moon() });
        let mut differs = false;
        for dir in testing::random_dirs(1000) {
            assert_eq!(a.height(dir), b.height(dir));
            differs |= a.height(dir) != other.height(dir);
            assert!((-3.2..=7.2).contains(&a.height(dir)), "{}", a.height(dir));
        }
        assert!(differs);
    }

    #[test]
    fn frames_are_orthonormal_with_up_outward() {
        let s = Surface::Sphere(Arc::new(Sphere::new(Body::test_moon())));
        for dir in testing::random_dirs(200) {
            let p = dir * 2000.0;
            let f = s.frame(p);
            assert!((f.length() - 1.0).abs() < 1e-5);
            assert!((f * Vec3::Y).dot(s.up(p)) > 0.99999);
            if let Some(n) = s.north(p) { assert!((f * Vec3::NEG_Z).dot(n) > 0.9999 && n.dot(s.up(p)).abs() < 1e-4); }
        }
        assert!(s.north(Vec3::Y * 2000.0).is_none());
        assert!(s.north(Vec3::X * 2000.0).is_some());
    }

    #[test]
    fn the_basis_keeps_its_orientation_and_stays_precise_near_the_poles() {
        assert_eq!(sphere_basis(Vec3::X * 2000.0), (Vec3::NEG_Z, Vec3::X, Vec3::Y), "east is -Z and north +Y at +X");
        // Just outside the fallback, 6 m from the axis on a 2 km body, either pole, any longitude.
        for lon in 0..12 {
            let a = lon as f32 * std::f32::consts::TAU / 12.0;
            for pole in [1.0, -1.0] {
                let p = Vec3::new(6.0 * a.cos(), pole * 2000.0, 6.0 * a.sin());
                let (east, up, north) = sphere_basis(p);
                for (u, v) in [(east, up), (up, north), (north, east)] {
                    assert!(u.dot(v).abs() < 1e-6 && (u.length() - 1.0).abs() < 1e-6, "{p}");
                }
                assert!(east.cross(up).dot(-north) > 0.999999, "right-handed with north at local -Z, at {p}");
                // Toward the north pole: across the axis near it, away from the axis near the south pole.
                assert!(north.dot(p.with_y(0.0).normalize() * -pole) > 0.9999, "north {north} at {p}");
            }
        }
    }

    #[test]
    fn gravity_points_at_the_centre_and_falls_off() {
        let s = Surface::Sphere(Arc::new(Sphere::new(Body::test_moon())));
        let g = s.gravity(Vec3::X * 2000.0, 1.0);
        assert!((g.length() - 9.8).abs() < 1e-4 && g.normalize().dot(Vec3::NEG_X) > 0.99999);
        assert!((s.gravity(Vec3::X * 4000.0, 1.0).length() - 2.45).abs() < 1e-4);
        assert_eq!(s.altitude(Vec3::X * 2000.0), 0.0); // the test moon's sea radius is its radius, 2000 m
    }

    #[test]
    fn flat_surface_matches_the_old_world() {
        let s = Surface::Flat;
        let p = Vec3::new(3.0, 4.5, -2.0);
        assert_eq!((s.up(p), s.altitude(p), s.frame(p), s.gravity(p, 9.8)), (Vec3::Y, 4.5, Quat::IDENTITY, Vec3::NEG_Y * 9.8));
        assert_eq!(s.ground(p).point, Vec3::new(3.0, 0.0, -2.0));
        assert_eq!(s.north(p), Some(Vec3::NEG_Z));
    }

    #[test]
    fn analytic_ground_sits_on_the_surface() {
        let sphere = Sphere::new(Body::test_moon());
        let s = Surface::Sphere(Arc::new(sphere.clone()));
        for dir in testing::random_dirs(200) {
            let g = s.ground(sphere.surface_point(dir) + dir * 50.0);
            assert!((g.point.length() - (sphere.sea_radius() + sphere.height(dir))).abs() < 1e-2);
            assert!(g.normal.dot(dir) > 0.7 && (g.normal.length() - 1.0).abs() < 1e-4);
        }
    }

    #[test]
    fn origin_quantizes_and_converts_both_ways() {
        let o = Origin::at(Vec3::new(1000.0, -77.0, 3.0), QUANTUM);
        for c in o.offset.to_array() { assert_eq!(c.rem_euclid(QUANTUM), 0.0); }
        assert!(o.offset.distance(Vec3::new(1000.0, -77.0, 3.0)) < QUANTUM);
        let x = Vec3::new(5.0, 6.0, 7.0);
        assert_eq!(o.world(o.body(x)), x);
    }
}
