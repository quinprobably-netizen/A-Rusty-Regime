//! The vehicles' bodies, built from scaled unit cubes and cylinders in the body frame (origin at the centre of
//! mass, ground at `-cg_h`). Wheels are `WheelVisual` children that `wheel_visuals` moves each frame.

use std::f32::consts::FRAC_PI_2;

use bevy::prelude::*;

use super::spec::{Kind, VehicleSpec};
use super::{VehicleAssets, WheelVisual};

struct Parts<'a, 'b> {
    spawner: &'a mut ChildSpawnerCommands<'b>,
    assets: &'a VehicleAssets,
}

impl Parts<'_, '_> {
    fn boxed(&mut self, size: Vec3, at: Vec3, rot: Quat, mat: &Handle<StandardMaterial>) {
        self.spawner.spawn((
            Mesh3d(self.assets.cube.clone()),
            MeshMaterial3d(mat.clone()),
            Transform { translation: at, rotation: rot, scale: size },
        ));
    }

    /// A cylinder of `radius` and `length` along `axis` (unit X, Y or Z), centred at `at`.
    fn tube(&mut self, radius: f32, length: f32, at: Vec3, axis: Vec3, mat: &Handle<StandardMaterial>) {
        let rot = Quat::from_rotation_arc(Vec3::Y, axis);
        self.spawner.spawn((
            Mesh3d(self.assets.cylinder.clone()),
            MeshMaterial3d(mat.clone()),
            Transform { translation: at, rotation: rot, scale: Vec3::new(radius * 2.0, length, radius * 2.0) },
        ));
    }

    fn wheel(&mut self, k: usize, radius: f32, width: f32, mount: Vec3) {
        let assets = self.assets.clone();
        self.spawner.spawn((WheelVisual(k), Transform::from_translation(mount), Visibility::default())).with_children(|w| {
            let axle = Quat::from_rotation_z(FRAC_PI_2);
            w.spawn((
                Mesh3d(assets.cylinder.clone()),
                MeshMaterial3d(assets.rubber.clone()),
                Transform { rotation: axle, scale: Vec3::new(radius * 2.0, width, radius * 2.0), ..default() },
            ));
            w.spawn((
                Mesh3d(assets.cylinder.clone()),
                MeshMaterial3d(assets.steel.clone()),
                Transform { rotation: axle, scale: Vec3::new(radius * 1.1, width * 1.05, radius * 1.1), ..default() },
            ));
            // Tread lugs, so the spin reads.
            for i in 0..8 {
                let a = i as f32 * std::f32::consts::TAU / 8.0;
                w.spawn((
                    Mesh3d(assets.cube.clone()),
                    MeshMaterial3d(assets.dark.clone()),
                    Transform {
                        translation: Vec3::new(0.0, a.cos() * radius * 0.92, a.sin() * radius * 0.92),
                        rotation: Quat::from_rotation_x(-a),
                        scale: Vec3::new(width * 1.08, radius * 0.25, radius * 0.1),
                    },
                ));
            }
        });
    }
}

pub fn build(commands: &mut Commands, assets: &VehicleAssets, entity: Entity, spec: &VehicleSpec, mounts: &[Vec3]) {
    commands.entity(entity).with_children(|spawner| {
        let mut p = Parts { spawner, assets };
        for (k, w) in spec.wheels.iter().enumerate() {
            p.wheel(k, w.radius, w.width, mounts[k]);
        }
        match spec.kind {
            Kind::Humvee => humvee(&mut p),
            Kind::Jeep => jeep(&mut p),
            Kind::DirtBike => dirt_bike(&mut p),
        }
    });
}

fn humvee(p: &mut Parts) {
    let a = p.assets.clone();
    let id = Quat::IDENTITY;
    p.boxed(Vec3::new(1.8, 0.55, 4.8), Vec3::new(0.0, -0.15, 0.0), id, &a.olive);
    p.boxed(Vec3::new(2.0, 0.35, 1.5), Vec3::new(0.0, 0.3, -1.55), id, &a.olive);
    p.boxed(Vec3::new(2.1, 0.75, 2.0), Vec3::new(0.0, 0.5, 0.0), id, &a.olive);
    p.boxed(Vec3::new(1.9, 0.55, 0.06), Vec3::new(0.0, 0.5, -0.98), Quat::from_rotation_x(-0.3), &a.glass);
    p.boxed(Vec3::new(0.06, 0.5, 1.6), Vec3::new(-1.04, 0.5, 0.1), id, &a.glass);
    p.boxed(Vec3::new(0.06, 0.5, 1.6), Vec3::new(1.04, 0.5, 0.1), id, &a.glass);
    p.boxed(Vec3::new(2.1, 0.5, 1.2), Vec3::new(0.0, 0.35, 1.7), id, &a.olive);
    p.boxed(Vec3::new(2.2, 0.25, 0.3), Vec3::new(0.0, -0.35, -2.5), id, &a.dark);
    p.boxed(Vec3::new(2.2, 0.25, 0.3), Vec3::new(0.0, -0.35, 2.5), id, &a.dark);
    for (x, z) in [(-1.0, -1.65), (1.0, -1.65), (-1.0, 1.65), (1.0, 1.65)] {
        p.boxed(Vec3::new(0.4, 0.3, 1.3), Vec3::new(x, 0.08, z), id, &a.dark);
    }
    p.boxed(Vec3::new(1.4, 0.3, 0.08), Vec3::new(0.0, 0.05, -2.4), id, &a.dark);
    p.boxed(Vec3::new(0.2, 0.2, 0.06), Vec3::new(-0.75, 0.1, -2.42), id, &a.light);
    p.boxed(Vec3::new(0.2, 0.2, 0.06), Vec3::new(0.75, 0.1, -2.42), id, &a.light);
    // Turret ring and a pintle gun.
    p.tube(0.5, 0.12, Vec3::new(0.0, 0.93, 0.1), Vec3::Y, &a.dark);
    p.tube(0.04, 0.6, Vec3::new(0.0, 1.0, 0.1), Vec3::Y, &a.steel);
    p.tube(0.05, 1.1, Vec3::new(0.0, 1.3, -0.3), Vec3::Z, &a.dark);
    p.boxed(Vec3::new(0.2, 0.2, 0.5), Vec3::new(0.0, 1.3, 0.15), id, &a.dark);
    // Antenna and jerry cans.
    p.tube(0.015, 1.8, Vec3::new(1.0, 1.6, 1.9), Vec3::Y, &a.dark);
    p.boxed(Vec3::new(0.2, 0.45, 0.35), Vec3::new(-0.9, 0.8, 2.1), id, &a.olive);
    p.boxed(Vec3::new(0.2, 0.45, 0.35), Vec3::new(-0.65, 0.8, 2.1), id, &a.olive);
}

fn jeep(p: &mut Parts) {
    let a = p.assets.clone();
    let id = Quat::IDENTITY;
    p.boxed(Vec3::new(1.4, 0.45, 2.2), Vec3::new(0.0, -0.05, 0.4), id, &a.olive);
    p.boxed(Vec3::new(1.3, 0.4, 1.1), Vec3::new(0.0, 0.0, -0.95), id, &a.olive);
    p.boxed(Vec3::new(1.0, 0.4, 0.06), Vec3::new(0.0, 0.0, -1.52), id, &a.dark);
    for i in 0..7 {
        p.boxed(Vec3::new(0.05, 0.3, 0.03), Vec3::new(-0.36 + i as f32 * 0.12, 0.0, -1.55), id, &a.olive);
    }
    p.tube(0.09, 0.05, Vec3::new(-0.52, 0.05, -1.55), Vec3::Z, &a.light);
    p.tube(0.09, 0.05, Vec3::new(0.52, 0.05, -1.55), Vec3::Z, &a.light);
    for (x, z, l) in [(-0.8, -1.0, 1.2), (0.8, -1.0, 1.2), (-0.8, 1.05, 1.0), (0.8, 1.05, 1.0)] {
        p.boxed(Vec3::new(0.3, 0.1, l), Vec3::new(x, 0.15, z), id, &a.olive);
    }
    p.boxed(Vec3::new(1.5, 0.12, 0.1), Vec3::new(0.0, -0.2, -1.62), id, &a.dark);
    // Windshield on its frame, folded up.
    let lean = Quat::from_rotation_x(0.15);
    p.boxed(Vec3::new(1.3, 0.45, 0.03), Vec3::new(0.0, 0.5, -0.35), lean, &a.glass);
    p.boxed(Vec3::new(1.4, 0.05, 0.05), Vec3::new(0.0, 0.74, -0.39), lean, &a.olive);
    p.boxed(Vec3::new(0.05, 0.5, 0.05), Vec3::new(-0.68, 0.5, -0.35), lean, &a.olive);
    p.boxed(Vec3::new(0.05, 0.5, 0.05), Vec3::new(0.68, 0.5, -0.35), lean, &a.olive);
    // Seats, wheel, spare and a can.
    for x in [-0.35, 0.35] {
        p.boxed(Vec3::new(0.5, 0.25, 0.5), Vec3::new(x, 0.25, 0.2), id, &a.tan);
        p.boxed(Vec3::new(0.5, 0.45, 0.1), Vec3::new(x, 0.5, 0.42), id, &a.tan);
    }
    p.tube(0.18, 0.03, Vec3::new(-0.35, 0.45, -0.25), Vec3::new(0.0, 0.5, -0.87).normalize(), &a.dark);
    p.tube(0.36, 0.2, Vec3::new(0.3, 0.15, 1.62), Vec3::Z, &a.rubber);
    p.boxed(Vec3::new(0.2, 0.4, 0.3), Vec3::new(-0.45, 0.15, 1.65), id, &a.olive);
}

fn dirt_bike(p: &mut Parts) {
    let a = p.assets.clone();
    let id = Quat::IDENTITY;
    p.boxed(Vec3::new(0.3, 0.3, 0.35), Vec3::new(0.0, -0.15, 0.05), id, &a.dark);
    p.boxed(Vec3::new(0.3, 0.22, 0.45), Vec3::new(0.0, 0.12, -0.15), id, &a.olive);
    p.boxed(Vec3::new(0.25, 0.1, 0.6), Vec3::new(0.0, 0.2, 0.3), id, &a.dark);
    p.boxed(Vec3::new(0.04, 0.04, 0.9), Vec3::new(-0.1, 0.0, 0.1), id, &a.steel);
    p.boxed(Vec3::new(0.04, 0.04, 0.9), Vec3::new(0.1, 0.0, 0.1), id, &a.steel);
    p.boxed(Vec3::new(0.06, 0.5, 0.06), Vec3::new(0.0, -0.1, -0.3), Quat::from_rotation_x(0.3), &a.steel);
    p.boxed(Vec3::new(0.05, 0.05, 0.6), Vec3::new(0.0, -0.25, 0.45), id, &a.steel);
    p.boxed(Vec3::new(0.2, 0.04, 0.5), Vec3::new(0.0, 0.14, 0.65), Quat::from_rotation_x(0.2), &a.olive);
    p.boxed(Vec3::new(0.16, 0.04, 0.45), Vec3::new(0.0, 0.1, -0.78), id, &a.olive);
    let fork = Quat::from_rotation_x(0.45);
    p.tube(0.02, 0.7, Vec3::new(-0.1, 0.05, -0.62), fork * Vec3::Y, &a.steel);
    p.tube(0.02, 0.7, Vec3::new(0.1, 0.05, -0.62), fork * Vec3::Y, &a.steel);
    p.tube(0.015, 0.7, Vec3::new(0.0, 0.45, -0.45), Vec3::X, &a.dark);
    p.tube(0.04, 0.9, Vec3::new(0.17, 0.05, 0.3), Vec3::Z, &a.steel);
    p.boxed(Vec3::new(0.14, 0.14, 0.05), Vec3::new(0.0, 0.4, -0.6), id, &a.light);
    // Panniers.
    p.boxed(Vec3::new(0.12, 0.25, 0.35), Vec3::new(-0.25, 0.0, 0.5), id, &a.tan);
    p.boxed(Vec3::new(0.12, 0.25, 0.35), Vec3::new(0.25, 0.0, 0.5), id, &a.tan);
}
