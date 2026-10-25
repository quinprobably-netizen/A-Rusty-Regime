use bevy::prelude::*;
use serde::Deserialize;
use std::collections::HashMap;

/// One celestial body (table `[body.<id>]` in `assets/system.toml`). Distances are meters,
/// angles degrees. Missing keys fall back to the home world.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Body {
    pub radius: f32,
    /// m/s² at sea level.
    pub gravity: f32,
    /// One rotation in real minutes.
    pub day_minutes: f32,
    /// Axial tilt; the star's declination this far north until orbits exist.
    pub tilt: f32,
    /// Meters above `radius`.
    pub sea_level: f32,
    pub seed: u32,
    /// Tallest peaks above the sea.
    pub height: f32,
    /// Base wavelength of the relief noise.
    pub wavelength: f32,
    /// Fraction of the surface above water.
    pub land: f32,
    /// Where the home continent sits, on the body that has one.
    pub home: Option<Home>,
    /// The body it circles, on a world of the solar system level; none on the debug moon.
    pub orbit: Option<Orbit>,
    /// Radius of its sphere of influence, m: inside it, it is the body physics runs on.
    pub soi: f32,
    /// Ground colours; none draws the plain grey of the debug moon.
    pub palette: Option<Palette>,
    /// Air, on a world that has some.
    pub air: Option<Air>,
    /// The name shown in the flight HUD.
    pub name: String,
}

/// A circular orbit about `parent` (`star` or another body's id). Angles are degrees.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Orbit {
    pub parent: String,
    /// From the parent's centre, m.
    pub distance: f32,
    /// One revolution in real minutes.
    pub minutes: f32,
    /// Where on the orbit it is at epoch 0.
    pub phase: f32,
    /// Tilt of the orbit plane about the parent's +X.
    pub incline: f32,
}

impl Default for Orbit {
    fn default() -> Self {
        Self { parent: "star".into(), distance: 300_000.0, minutes: 240.0, phase: 0.0, incline: 0.0 }
    }
}

/// Ground colours as sRGB: lowland, highland, and the rock of steep slopes.
#[derive(Deserialize, Clone, Debug, PartialEq)]
pub struct Palette {
    pub low: [f32; 3],
    pub high: [f32; 3],
    pub rock: [f32; 3],
    /// The sea, on a world with one.
    #[serde(default = "Palette::default_sea")]
    pub sea: [f32; 3],
}

impl Palette {
    fn default_sea() -> [f32; 3] {
        [0.05, 0.18, 0.3]
    }
}

/// An atmosphere: how thick it is and how dense at the ground relative to Earth's.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Air {
    /// Top of the atmosphere above sea level, m.
    pub height: f32,
    /// Sea-level density over Earth's (1.225 kg/m³).
    pub density: f32,
    /// Scales the scattering per colour channel: (1, 1, 1) is Earth's blue sky.
    pub tint: [f32; 3],
}

impl Default for Air {
    fn default() -> Self {
        Self { height: 12_000.0, density: 1.0, tint: [1.0, 1.0, 1.0] }
    }
}

impl Air {
    /// Density scale height, m: Earth's 8 km over its 60 km shell, kept in proportion.
    pub fn scale_height(&self) -> f32 {
        self.height * 8.0 / 60.0
    }

    /// Air density at `altitude` m, kg/m³.
    pub fn density_at(&self, altitude: f32) -> f32 {
        if altitude >= self.height {
            return 0.0;
        }
        1.225 * self.density * (-altitude.max(0.0) / self.scale_height()).exp()
    }
}

/// The star at the centre of the system, fixed at the origin of the inertial frame.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Star {
    pub radius: f32,
    /// m/s² at its surface. Small: a ship in deep space drifts, it does not fall.
    pub gravity: f32,
    pub color: [f32; 3],
    /// Sphere of influence in deep space, the whole system.
    pub soi: f32,
}

impl Default for Star {
    fn default() -> Self {
        Self { radius: 6_000.0, gravity: 0.5, color: [1.0, 0.9, 0.75], soi: 5_000_000.0 }
    }
}

impl Star {
    /// The star as a body, so it can be the anchor in deep space.
    pub fn body(&self) -> Body {
        Body { radius: self.radius, gravity: self.gravity, day_minutes: 0.0, tilt: 0.0, height: 0.0, land: 1.0, soi: self.soi, name: "Star".into(), ..Body::default() }
    }
}

impl Default for Body {
    fn default() -> Self {
        Self {
            radius: 17500.0,
            gravity: 9.8,
            day_minutes: 48.0,
            tilt: 12.0,
            sea_level: 0.0,
            seed: 7,
            height: 900.0,
            wavelength: 2000.0,
            land: 0.3,
            home: None,
            orbit: None,
            soi: 0.0,
            palette: None,
            air: None,
            name: String::new(),
        }
    }
}

impl Body {
    /// The bare debug moon. It keeps 9.8 gravity so movement tests compare like with like.
    #[cfg(test)]
    pub fn test_moon() -> Body {
        Body {
            radius: 2000.0,
            gravity: 9.8,
            day_minutes: 48.0,
            tilt: 0.0,
            sea_level: 0.0,
            seed: 11,
            height: 10.0,
            wavelength: 2000.0,
            land: 1.0,
            ..Body::default()
        }
    }
}

/// The home continent: centred at `lat`, `lon` (degrees), `continent` meters across, with the
/// `core` meter island region at its heart.
#[derive(Deserialize, Clone, Debug, PartialEq)]
pub struct Home {
    pub lat: f32,
    pub lon: f32,
    pub core: f32,
    pub continent: f32,
}

/// Every body, by id.
#[derive(Deserialize, Clone, Debug, Default)]
pub struct System {
    pub body: HashMap<String, Body>,
    #[serde(default)]
    pub star: Star,
}

const PATH: &str = "assets/system.toml";

impl System {
    pub fn load() -> System {
        match std::fs::read_to_string(PATH) {
            Ok(text) => toml::from_str(&text).unwrap_or_else(|e| {
                warn!("{PATH} is invalid, using defaults: {e}");
                System::default()
            }),
            Err(e) => {
                warn!("{PATH} unreadable, using defaults: {e}");
                System::default()
            }
        }
    }

    pub fn body(&self, id: &str) -> Option<&Body> {
        self.body.get(id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn system_toml_declares_home_and_moon() {
        let s = System::load();
        let home = s.body("home").expect("home");
        assert_eq!((home.radius, home.gravity, home.day_minutes, home.tilt), (17500.0, 9.8, 48.0, 12.0));
        assert_eq!(home.home.as_ref().map(|h| (h.lat, h.lon, h.core, h.continent)), Some((12.0, 40.0, 4000.0, 35000.0)));
        let moon = s.body("moon").expect("moon");
        assert_eq!((moon.radius, moon.gravity, moon.sea_level), (2000.0, 9.8, 0.0));
        assert_eq!(Body::default().radius, 17500.0);
        assert_eq!(Body::test_moon().seed, 11);
    }
}
