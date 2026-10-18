//! The island's vehicles: a Humvee, a Willys-style jeep and a military dirt bike, as numbers. Real-world
//! masses, wheelbases, torque curves and gearing; the bodies are built in `vehicle::body`.
//!
//! Body frame: origin at the centre of mass, +X right, +Y up, -Z forward (Bevy's convention). The ground is
//! `-cg_h` below the origin when the vehicle sits at rest.

use bevy::prelude::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Humvee,
    Jeep,
    DirtBike,
}

#[derive(Clone, Copy, Debug)]
pub struct WheelSpec {
    /// Where the suspension hangs from, in the body frame (y is derived; see `VehicleSpec::mount`).
    pub x: f32,
    pub z: f32,
    pub steers: bool,
    pub driven: bool,
    pub radius: f32,
    pub width: f32,
}

#[derive(Clone, Debug)]
pub struct VehicleSpec {
    pub name: &'static str,
    pub kind: Kind,
    pub mass: f32,
    /// Collision box (full extents) and its centre in the body frame.
    pub hull: Vec3,
    pub hull_center: Vec3,
    /// Centre of mass height above the ground at rest.
    pub cg_h: f32,
    pub wheels: Vec<WheelSpec>,
    /// Suspension travel (m); the wheel hangs this far below the mount at full droop.
    pub travel: f32,
    /// Ride frequency (Hz): sets the spring rate from the sprung mass.
    pub freq: f32,
    pub unsprung: f32,
    /// `(rpm, N·m)` full-throttle torque curve.
    pub curve: &'static [(f32, f32)],
    pub idle: f32,
    pub redline: f32,
    pub disp: f32,
    pub gears: &'static [f32],
    pub final_drive: f32,
    pub rev: f32,
    /// Brake torque per wheel at full pedal (N·m); the handbrake locks the rear at twice this.
    pub brake_t: f32,
    pub max_steer: f32,
    /// Drag coefficient times frontal area (m²).
    pub drag: f32,
    /// The driver's eye and where they step out, in the body frame.
    pub seat: Vec3,
    pub exit: Vec3,
    /// Chase camera distance and height.
    pub cam: (f32, f32),
    /// Hull points, the fraction of bullet damage that gets through, fuel tank (L) and full-load burn (L/s).
    pub hp: f32,
    pub armor: f32,
    pub tank: f32,
    pub burn: f32,
}

impl VehicleSpec {
    pub fn sprung_mass(&self) -> f32 {
        self.mass - self.unsprung * self.wheels.len() as f32
    }

    /// Spring rate per wheel from the ride frequency.
    pub fn spring_rate(&self) -> f32 {
        let m_s = self.sprung_mass() / self.wheels.len() as f32;
        m_s * (std::f32::consts::TAU * self.freq).powi(2)
    }

    /// Static compression under the sprung weight.
    pub fn sag(&self, g: f32) -> f32 {
        let m_s = self.sprung_mass() / self.wheels.len() as f32;
        (m_s * g / self.spring_rate()).min(self.travel * 0.7)
    }

    /// Where wheel `k` hangs from, in the body frame.
    pub fn mount(&self, k: usize, g: f32) -> Vec3 {
        let w = &self.wheels[k];
        Vec3::new(w.x, self.travel + w.radius - self.sag(g) - self.cg_h, w.z)
    }

    pub fn wheelbase(&self) -> f32 {
        let zs = self.wheels.iter().map(|w| w.z);
        zs.clone().fold(f32::MIN, f32::max) - zs.fold(f32::MAX, f32::min)
    }
}

const HUMVEE_CURVE: &[(f32, f32)] = &[(700.0, 300.0), (1200.0, 380.0), (1700.0, 440.0), (2200.0, 420.0), (2800.0, 380.0), (3400.0, 320.0)];
const JEEP_CURVE: &[(f32, f32)] = &[(600.0, 90.0), (1200.0, 135.0), (2000.0, 145.0), (2800.0, 140.0), (3600.0, 120.0), (4000.0, 100.0)];
const BIKE_CURVE: &[(f32, f32)] = &[(1500.0, 14.0), (3000.0, 20.0), (5000.0, 26.0), (7000.0, 28.0), (8500.0, 25.0), (9500.0, 18.0)];

/// HMMWV: 2.2 m wide, 3.3 m wheelbase, 2.6 t, a 6.5 L diesel through a 4-speed auto to all four wheels.
pub fn humvee() -> VehicleSpec {
    let wheel = |x: f32, z: f32, front: bool| WheelSpec { x, z, steers: front, driven: true, radius: 0.46, width: 0.32 };
    VehicleSpec {
        name: "Humvee",
        kind: Kind::Humvee,
        mass: 2600.0,
        hull: Vec3::new(2.2, 1.1, 4.8),
        hull_center: Vec3::new(0.0, 0.15, 0.0),
        cg_h: 0.95,
        wheels: vec![wheel(-0.92, -1.65, true), wheel(0.92, -1.65, true), wheel(-0.92, 1.65, false), wheel(0.92, 1.65, false)],
        travel: 0.26,
        freq: 1.35,
        unsprung: 90.0,
        curve: HUMVEE_CURVE,
        idle: 700.0,
        redline: 3400.0,
        disp: 6.5,
        gears: &[2.48, 1.48, 1.0, 0.75],
        final_drive: 4.6,
        rev: 2.1,
        brake_t: 2600.0,
        max_steer: 0.5,
        drag: 2.6,
        seat: Vec3::new(-0.5, 0.75, -0.3),
        exit: Vec3::new(-2.0, 0.6, -0.3),
        hp: 800.0, armor: 0.4, tank: 95.0, burn: 0.02,
        cam: (8.0, 3.0),
    }
}

/// Willys MB: 1.57 m wide, 2.03 m wheelbase, 1.1 t, a 2.2 L four through a 3-speed to all four wheels.
pub fn jeep() -> VehicleSpec {
    let wheel = |x: f32, z: f32, front: bool| WheelSpec { x, z, steers: front, driven: true, radius: 0.38, width: 0.2 };
    VehicleSpec {
        name: "Jeep",
        kind: Kind::Jeep,
        mass: 1100.0,
        hull: Vec3::new(1.5, 0.8, 3.3),
        hull_center: Vec3::new(0.0, 0.1, 0.0),
        cg_h: 0.7,
        wheels: vec![wheel(-0.62, -1.0, true), wheel(0.62, -1.0, true), wheel(-0.62, 1.03, false), wheel(0.62, 1.03, false)],
        travel: 0.2,
        freq: 1.5,
        unsprung: 40.0,
        curve: JEEP_CURVE,
        idle: 600.0,
        redline: 4000.0,
        disp: 2.2,
        gears: &[2.67, 1.56, 1.0],
        final_drive: 4.88,
        rev: 3.55,
        brake_t: 1100.0,
        max_steer: 0.55,
        drag: 1.9,
        seat: Vec3::new(-0.35, 0.55, 0.15),
        exit: Vec3::new(-1.6, 0.5, 0.15),
        hp: 400.0, armor: 1.0, tank: 57.0, burn: 0.008,
        cam: (6.5, 2.5),
    }
}

/// A military trail bike: 1.45 m wheelbase, 150 kg, a 250 cc single through a 5-speed to the rear wheel.
pub fn dirt_bike() -> VehicleSpec {
    VehicleSpec {
        name: "Dirt bike",
        kind: Kind::DirtBike,
        mass: 150.0,
        hull: Vec3::new(0.4, 0.5, 1.6),
        hull_center: Vec3::new(0.0, 0.05, 0.0),
        cg_h: 0.62,
        wheels: vec![
            WheelSpec { x: 0.0, z: -0.75, steers: true, driven: false, radius: 0.34, width: 0.1 },
            WheelSpec { x: 0.0, z: 0.7, steers: false, driven: true, radius: 0.3, width: 0.13 },
        ],
        travel: 0.25,
        freq: 1.8,
        unsprung: 12.0,
        curve: BIKE_CURVE,
        idle: 1500.0,
        redline: 9500.0,
        disp: 0.25,
        gears: &[2.8, 1.9, 1.4, 1.1, 0.9],
        final_drive: 3.9,
        rev: 0.0,
        brake_t: 320.0,
        max_steer: 0.6,
        drag: 0.7,
        seat: Vec3::new(0.0, 0.75, 0.15),
        exit: Vec3::new(-1.0, 0.4, 0.0),
        hp: 120.0, armor: 1.0, tank: 8.0, burn: 0.003,
        cam: (5.0, 2.0),
    }
}

pub fn spec(kind: Kind) -> VehicleSpec {
    match kind {
        Kind::Humvee => humvee(),
        Kind::Jeep => jeep(),
        Kind::DirtBike => dirt_bike(),
    }
}
