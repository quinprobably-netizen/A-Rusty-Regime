//! The world (hyper-realism stage R7): a day-night cycle that moves the sun and moon and sets the
//! camera's exposure and the sky's ambient light, vehicle headlights and a flashlight (F) for the
//! dark, and weather that drifts between clear, overcast, rain and fog, with wet ground, falling
//! rain, distance fog and a wind that pushes bullets.

use bevy::camera::Exposure;
use bevy::light::{light_consts::lux, GlobalAmbientLight};
use bevy::prelude::*;

use crate::camera::PlayerCamera;
use crate::input::PlayerInput;
use crate::look::{SurfaceMaterial, TerrainMaterial, Textures};
use crate::tuning::Tuning;
use crate::vehicle::Vehicle;

pub struct WorldPlugin;

impl Plugin for WorldPlugin {
    fn build(&self, app: &mut App) {
        let t = crate::tuning::load().world;
        let held = match t.sky.as_str() {
            "clear" => Some(Sky::Clear),
            "overcast" => Some(Sky::Overcast),
            "rain" => Some(Sky::Rain),
            "fog" => Some(Sky::Fog),
            _ => None,
        };
        let weather = held.map_or_else(Weather::default, Weather::held);
        app.insert_resource(Clock { hour: t.start_hour })
            .insert_resource(weather)
            .init_resource::<Wind>()
            .add_systems(PostStartup, (spawn_moon, spawn_rain, spawn_hud))
            .add_systems(Update, (tick, sun, view, lights, flashlight, rain, wet, fog, hud).chain());
    }
}

/// Hours since midnight, 0..24.
#[derive(Resource, Debug, Clone, Copy)]
pub struct Clock {
    pub hour: f32,
}

impl Clock {
    /// The sun's direction (toward it): rises in the east (+X) at 6, highest at noon toward the south (+Z), sets at 18.
    pub fn sun_dir(&self) -> Vec3 {
        let a = (self.hour - 6.0) / 12.0 * std::f32::consts::PI;
        let tilt = 0.55;
        Vec3::new(a.cos(), a.sin() * (1.0 - tilt * 0.5), a.sin() * tilt).normalize()
    }

    /// 0 at night, 1 in daylight, with a dawn and dusk ramp.
    pub fn daylight(&self) -> f32 {
        let y = self.sun_dir().y;
        ((y + 0.08) / 0.3).clamp(0.0, 1.0)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Sky {
    Clear,
    Overcast,
    Rain,
    Fog,
}

/// The weather now: each value eases toward the current sky's target.
#[derive(Resource, Debug, Clone)]
pub struct Weather {
    pub sky: Sky,
    pub cloud: f32,
    pub rain: f32,
    pub fog: f32,
    /// Ground wetness: rises in rain, dries slowly after.
    pub wet: f32,
    /// Seconds until the sky changes.
    pub next: f32,
    seed: u32,
    /// A sky set in tuning.toml that never changes.
    pub hold: bool,
}

impl Default for Weather {
    fn default() -> Self {
        Weather { sky: Sky::Clear, cloud: 0.0, rain: 0.0, fog: 0.0, wet: 0.0, next: 0.0, seed: 7, hold: false }
    }
}

impl Weather {
    /// One sky, already fully set in.
    pub fn held(sky: Sky) -> Self {
        let (cloud, rain, fog) = Weather::targets(sky);
        Weather { sky, cloud, rain, fog, wet: if rain > 0.3 { 1.0 } else { 0.0 }, next: f32::MAX, seed: 7, hold: true }
    }

    fn targets(sky: Sky) -> (f32, f32, f32) {
        match sky {
            Sky::Clear => (0.05, 0.0, 0.0),
            Sky::Overcast => (0.8, 0.0, 0.15),
            Sky::Rain => (0.95, 1.0, 0.35),
            Sky::Fog => (0.5, 0.0, 1.0),
        }
    }

    /// Advances the weather by `dt` seconds: picks the next sky when it is due, eases toward it.
    pub fn step(&mut self, dt: f32, minutes: f32) {
        self.next -= dt;
        if self.next <= 0.0 && !self.hold {
            self.seed = self.seed.wrapping_mul(1_103_515_245).wrapping_add(12_345);
            let r = (self.seed >> 16) % 100;
            // Mostly fair; rain and fog now and then.
            self.sky = match r {
                0..45 => Sky::Clear,
                45..70 => Sky::Overcast,
                70..88 => Sky::Rain,
                _ => Sky::Fog,
            };
            self.next = minutes * 60.0 * (0.6 + (r % 10) as f32 * 0.08);
        }
        let (c, r, f) = Weather::targets(self.sky);
        let k = 1.0 - (-dt / 40.0).exp();
        self.cloud += (c - self.cloud) * k;
        self.rain += (r - self.rain) * k;
        self.fog += (f - self.fog) * k;
        let wet_to = if self.rain > 0.3 { 1.0 } else { 0.0 };
        let wet_rate = if wet_to > self.wet { 1.0 / 60.0 } else { 1.0 / 300.0 };
        self.wet = (self.wet + (wet_to - self.wet).signum() * wet_rate * dt).clamp(0.0, 1.0);
    }
}

/// Wind at ground level (m/s), gusting; bullets drift with it.
#[derive(Resource, Debug, Default, Clone, Copy)]
pub struct Wind(pub Vec3);

fn tick(time: Res<Time>, tuning: Res<Tuning>, mut clock: ResMut<Clock>, mut weather: ResMut<Weather>, mut wind: ResMut<Wind>) {
    let t = &tuning.world;
    let dt = time.delta_secs();
    if t.day_minutes > 0.0 {
        clock.hour = (clock.hour + dt * 24.0 / (t.day_minutes * 60.0)).rem_euclid(24.0);
    }
    if t.weather {
        weather.step(dt, t.weather_minutes);
    }
    let e = time.elapsed_secs();
    let base = 2.0 + weather.cloud * 3.0 + weather.rain * 4.0;
    let gust = 1.0 + 0.35 * (e * 0.31).sin() * (e * 0.17).cos();
    let dir = Vec3::new((e * 0.01).cos(), 0.0, (e * 0.01).sin() * 0.6 + 0.8).normalize();
    wind.0 = dir * base * gust;
}

#[derive(Component)]
struct Moon;

fn spawn_moon(mut commands: Commands) {
    commands.spawn((Name::new("Moon"), Moon, DirectionalLight { illuminance: 0.0, shadow_maps_enabled: false, color: Color::srgb(0.7, 0.8, 1.0), ..default() }, Transform::default()));
}

/// Sun and moon follow the clock; clouds dim the sun.
fn sun(tuning: Res<Tuning>, clock: Res<Clock>, weather: Res<Weather>, mut suns: Query<(&mut DirectionalLight, &mut Transform), Without<Moon>>, mut moon: Query<(&mut DirectionalLight, &mut Transform), With<Moon>>) {
    let dir = clock.sun_dir();
    let day = clock.daylight();
    let full = if tuning.graphics.atmosphere { lux::RAW_SUNLIGHT } else { 10_000.0 };
    for (mut light, mut tf) in &mut suns {
        *tf = Transform::from_translation(dir * 500.0).looking_at(Vec3::ZERO, Vec3::Y);
        light.illuminance = full * day * (1.0 - 0.75 * weather.cloud);
        light.shadow_maps_enabled = day > 0.05;
    }
    for (mut light, mut tf) in &mut moon {
        let m = -dir + Vec3::Y * 0.3;
        *tf = Transform::from_translation(m.normalize() * 500.0).looking_at(Vec3::ZERO, Vec3::Y);
        let night = 1.0 - day;
        light.illuminance = 0.3 * night * (1.0 - 0.8 * weather.cloud) * if tuning.graphics.atmosphere { 1.0 } else { 300.0 };
    }
}

/// The camera opens up at night, like an eye, and the sky's ambient light falls with the sun.
fn view(tuning: Res<Tuning>, clock: Res<Clock>, weather: Res<Weather>, mut ambient: ResMut<GlobalAmbientLight>, mut exposure: Query<&mut Exposure, With<PlayerCamera>>) {
    let day = clock.daylight();
    let g = &tuning.graphics;
    let light = (day * (1.0 - 0.6 * weather.cloud)).max(0.0);
    for mut e in &mut exposure {
        // Daylight exposure down to about EV 4 on a moonlit night.
        e.ev100 = 4.0 + (g.exposure - 4.0) * light.powf(0.35);
    }
    let base = if g.atmosphere { 2000.0 } else { 450.0 };
    ambient.brightness = base * (0.004 + light) * (1.0 + weather.cloud * 0.3);
}

#[derive(Component)]
struct Headlight;

#[derive(Component)]
struct Flashlight;

/// Every vehicle gets headlights, on after dusk while someone drives.
fn lights(mut commands: Commands, clock: Res<Clock>, weather: Res<Weather>, vehicles: Query<(Entity, &Vehicle, Option<&Children>)>, mut lamps: Query<&mut SpotLight, With<Headlight>>) {
    let dark = clock.daylight() < 0.35 || weather.fog > 0.6 || weather.rain > 0.6;
    for (e, v, children) in &vehicles {
        let has = children.is_some_and(|c| c.iter().any(|c| lamps.contains(c)));
        if !has {
            let front = v.spec.hull_center + Vec3::new(0.0, 0.1, -v.spec.hull.z * 0.5 - 0.05);
            commands.entity(e).with_children(|p| {
                p.spawn((
                    Headlight,
                    SpotLight { intensity: 0.0, range: 90.0, outer_angle: 0.55, inner_angle: 0.35, shadow_maps_enabled: false, color: Color::srgb(1.0, 0.95, 0.85), ..default() },
                    Transform::from_translation(front).looking_to(Vec3::new(0.0, -0.08, -1.0), Vec3::Y),
                ));
            });
            continue;
        }
        let on = dark && v.driver.is_some() && v.wreck.is_none();
        for c in children.into_iter().flatten() {
            if let Ok(mut lamp) = lamps.get_mut(*c) {
                lamp.intensity = if on { 4.0e6 } else { 0.0 };
            }
        }
    }
}

/// F toggles a torch on the camera.
fn flashlight(mut commands: Commands, mut input: ResMut<PlayerInput>, camera: Query<Entity, With<PlayerCamera>>, mut torch: Query<&mut SpotLight, With<Flashlight>>, mut made: Local<bool>) {
    let Ok(cam) = camera.single() else { return };
    if !*made {
        *made = true;
        commands.entity(cam).with_children(|c| {
            c.spawn((
                Flashlight,
                SpotLight { intensity: 0.0, range: 45.0, outer_angle: 0.38, inner_angle: 0.2, shadow_maps_enabled: true, color: Color::srgb(1.0, 0.97, 0.9), ..default() },
                Transform::from_xyz(0.25, -0.2, 0.0),
            ));
        });
        return;
    }
    if std::mem::take(&mut input.flashlight_pressed) {
        for mut l in &mut torch {
            l.intensity = if l.intensity > 0.0 { 0.0 } else { 1.5e6 };
        }
    }
}

#[derive(Component)]
struct Drop(usize);

const DROPS: usize = 700;

fn spawn_rain(mut commands: Commands, meshes: Option<ResMut<Assets<Mesh>>>, materials: Option<ResMut<Assets<StandardMaterial>>>) {
    let (Some(mut meshes), Some(mut materials)) = (meshes, materials) else { return };
    let mesh = meshes.add(Cuboid::new(0.008, 0.5, 0.008));
    let mat = materials.add(StandardMaterial { base_color: Color::srgba(0.75, 0.8, 0.9, 0.35), alpha_mode: AlphaMode::Blend, unlit: true, ..default() });
    for i in 0..DROPS {
        commands.spawn((Drop(i), Mesh3d(mesh.clone()), MeshMaterial3d(mat.clone()), Transform::default(), Visibility::Hidden, bevy::light::NotShadowCaster));
    }
}

/// Streaks falling in a 40 m box around the camera, as many as the rain is heavy, leaning with the wind.
fn rain(time: Res<Time>, weather: Res<Weather>, wind: Res<Wind>, camera: Query<&GlobalTransform, With<PlayerCamera>>, mut drops: Query<(&Drop, &mut Transform, &mut Visibility)>) {
    let Ok(cam) = camera.single() else { return };
    let c = cam.translation();
    let shown = (weather.rain * DROPS as f32) as usize;
    let fall = Vec3::new(-wind.0.x, -9.0, -wind.0.z);
    let lean = Quat::from_rotation_arc(Vec3::NEG_Y, fall.normalize());
    let e = time.elapsed_secs();
    for (d, mut tf, mut vis) in &mut drops {
        if d.0 >= shown {
            *vis = Visibility::Hidden;
            continue;
        }
        *vis = Visibility::Inherited;
        let h = |k: f32| {
            let v = ((d.0 as f32 + 1.0) * k).sin() * 43758.547;
            v - v.floor()
        };
        // Each drop falls through the box on its own phase, at a fixed spot in the world that wraps
        // around the camera, so running through rain looks right.
        let phase = (e * 9.0 / 40.0 + h(3.1)).fract();
        let wrap = |v: f32, centre: f32| centre - 20.0 + (v - (centre - 20.0)).rem_euclid(40.0);
        let drift = wind.0 * phase * 40.0 / 9.0;
        let p = Vec3::new(wrap(h(1.7) * 400.0 + drift.x, c.x), c.y + 20.0 - phase * 40.0, wrap(h(2.3) * 400.0 + drift.z, c.z));
        *tf = Transform::from_translation(p).with_rotation(lean);
    }
}

/// Wet ground and walls shine: their roughness falls as the wetness rises.
fn wet(weather: Res<Weather>, textures: Option<Res<Textures>>, mut terrain: ResMut<Assets<TerrainMaterial>>, mut surfaces: ResMut<Assets<SurfaceMaterial>>, mut last: Local<f32>) {
    let Some(t) = textures else { return };
    if (weather.wet - *last).abs() < 0.04 {
        return;
    }
    *last = weather.wet;
    let k = 1.0 - 0.45 * weather.wet;
    if let Some(mut m) = terrain.get_mut(&t.terrain) {
        m.extension.splat.rough = Vec4::new(0.92, 0.95, 0.85, 0.8) * k;
        m.base.base_color = Color::srgb(1.0 - 0.25 * weather.wet, 1.0 - 0.25 * weather.wet, 1.0 - 0.25 * weather.wet);
    }
    for h in [&t.concrete, &t.wood, &t.metal, &t.rock] {
        if let Some(mut m) = surfaces.get_mut(h) {
            m.extension.params.rough = k;
        }
    }
}

/// Haze always, thick in fog and rain, tinted by the light.
fn fog(mut commands: Commands, clock: Res<Clock>, weather: Res<Weather>, mut cams: Query<(Entity, Option<&mut DistanceFog>), With<PlayerCamera>>) {
    let day = clock.daylight();
    let density = 0.00008 + weather.fog * 0.006 + weather.rain * 0.0015;
    let grey = 0.25 + 0.5 * day * (1.0 - 0.3 * weather.cloud);
    let color = Color::srgb(grey * 0.92, grey * 0.95, grey);
    for (e, f) in &mut cams {
        match f {
            Some(mut f) => {
                f.falloff = FogFalloff::Exponential { density };
                f.color = color;
            }
            None => {
                commands.entity(e).insert(DistanceFog { color, falloff: FogFalloff::Exponential { density }, ..default() });
            }
        }
    }
}

#[derive(Component)]
struct ClockText;

fn spawn_hud(mut commands: Commands) {
    commands.spawn((
        ClockText,
        crate::hud::HudRoot,
        Text::new(""),
        TextFont { font_size: FontSize::Px(14.0), ..default() },
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.55)),
        Node { position_type: PositionType::Absolute, top: Val::Px(54.0), right: Val::Px(24.0), ..default() },
    ));
}

fn hud(clock: Res<Clock>, weather: Res<Weather>, wind: Res<Wind>, mut text: Query<&mut Text, With<ClockText>>) {
    let h = clock.hour.floor();
    let m = ((clock.hour - h) * 60.0).floor();
    let sky = match weather.sky {
        Sky::Clear => "clear",
        Sky::Overcast => "overcast",
        Sky::Rain => "rain",
        Sky::Fog => "fog",
    };
    for mut t in &mut text {
        t.0 = format!("{h:02.0}:{m:02.0}  {sky}  wind {:.0} m/s", wind.0.length());
    }
}
