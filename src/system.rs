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
            home: None,
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
