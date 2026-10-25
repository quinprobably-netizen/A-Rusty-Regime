//! Sound (hyper-realism stage R2), all synthesized at startup so the download stays small:
//! gunshots with a crack, a thump and a tail; footsteps, landings and hits; looping engines
//! pitched by rpm on each vehicle; wind that grows with height and speed; surf by the shore;
//! and short jingles for loot, extraction and missions. Drop CC0 samples in `assets/sounds/`
//! later and `load` picks them over the synthesis.

use std::f32::consts::{PI, TAU};
use std::sync::Arc;

use bevy::audio::{AudioSink, AudioSinkPlayback, GlobalVolume, PlaybackMode, SpatialAudioSink, SpatialListener, Volume};
use bevy::prelude::*;

use crate::camera::PlayerCamera;
use crate::controller::{MoveState, Player};
use crate::health::{PlayerHealth, PlayerHit};
use crate::loot::Inventory;
use crate::mission::Missions;
use crate::targets::{Shot, Target};
use crate::terrain::Heightmap;
use crate::tuning::Tuning;
use crate::vehicle::{Kind, Vehicle};
use crate::weapon::{Arsenal, Damage, Explosion, WeaponFired, WEAPONS};

pub struct SoundPlugin;

impl Plugin for SoundPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load).add_systems(
            Update,
            (listener, weapons, soldier_shots, explosions, hits, steps, engines, ambience, jingles).run_if(resource_exists::<Sounds>),
        );
    }
}

/// Every clip, by name.
#[derive(Resource)]
pub struct Sounds {
    rocket: Handle<AudioSource>,
    rifle: Handle<AudioSource>,
    shotgun: Handle<AudioSource>,
    pistol: Handle<AudioSource>,
    explosion: Handle<AudioSource>,
    steps: [Handle<AudioSource>; 4],
    land: Handle<AudioSource>,
    jump: Handle<AudioSource>,
    hit: Handle<AudioSource>,
    hurt: Handle<AudioSource>,
    engine_big: Handle<AudioSource>,
    engine_small: Handle<AudioSource>,
    engine_bike: Handle<AudioSource>,
    wind: Handle<AudioSource>,
    surf: Handle<AudioSource>,
    rain: Handle<AudioSource>,
    pickup: Handle<AudioSource>,
    extract: Handle<AudioSource>,
    mission: Handle<AudioSource>,
}

const RATE: u32 = 22050;

/// 16-bit mono WAV bytes from float samples.
fn wav(samples: &[f32]) -> AudioSource {
    let n = samples.len() as u32;
    let mut b = Vec::with_capacity(44 + n as usize * 2);
    b.extend_from_slice(b"RIFF");
    b.extend_from_slice(&(36 + n * 2).to_le_bytes());
    b.extend_from_slice(b"WAVEfmt ");
    b.extend_from_slice(&16u32.to_le_bytes());
    b.extend_from_slice(&1u16.to_le_bytes());
    b.extend_from_slice(&1u16.to_le_bytes());
    b.extend_from_slice(&RATE.to_le_bytes());
    b.extend_from_slice(&(RATE * 2).to_le_bytes());
    b.extend_from_slice(&2u16.to_le_bytes());
    b.extend_from_slice(&16u16.to_le_bytes());
    b.extend_from_slice(b"data");
    b.extend_from_slice(&(n * 2).to_le_bytes());
    for s in samples {
        b.extend_from_slice(&((s.clamp(-1.0, 1.0) * 32767.0) as i16).to_le_bytes());
    }
    AudioSource { bytes: Arc::from(b) }
}

struct Rng(u64);

impl Rng {
    fn next(&mut self) -> f32 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 40) as f32 / (1u64 << 24) as f32 * 2.0 - 1.0
    }
}

/// One-pole low-pass: `cutoff` Hz.
struct LowPass {
    y: f32,
    a: f32,
}

impl LowPass {
    fn new(cutoff: f32) -> Self {
        let a = (TAU * cutoff / RATE as f32).min(1.0);
        Self { y: 0.0, a }
    }
    fn run(&mut self, x: f32) -> f32 {
        self.y += self.a * (x - self.y);
        self.y
    }
}

fn soft(x: f32) -> f32 {
    x.tanh()
}

/// A gunshot: a noise crack decaying over `crack` s, a pitched thump, and a low tail of `tail` s.
fn gunshot(seconds: f32, crack: f32, thump_hz: f32, thump: f32, tail: f32, cutoff: f32, seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(cutoff);
    let mut tail_lp = LowPass::new(500.0);
    let n = (seconds * RATE as f32) as usize;
    (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let noise = rng.next();
            let body = lp.run(noise) * (-t / crack).exp() * 1.4;
            let th = (TAU * thump_hz * t * (1.0 - 0.35 * t.min(1.0))).sin() * (-t / (crack * 4.0)).exp() * thump;
            let tl = tail_lp.run(noise) * (-t / tail).exp() * 0.5;
            soft(body + th + tl)
        })
        .collect()
}

/// The rocket leaving: a noise whoosh whose filter opens, then a thump.
fn whoosh(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let n = (0.7 * RATE as f32) as usize;
    let mut lp = LowPass::new(300.0);
    (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            lp.a = (TAU * (300.0 + 4000.0 * t) / RATE as f32).min(1.0);
            let env = (t / 0.05).min(1.0) * (-t / 0.25).exp();
            let th = (TAU * 55.0 * t).sin() * (-t / 0.12).exp() * 0.8;
            soft(lp.run(rng.next()) * env * 1.2 + th)
        })
        .collect()
}

fn thud(seconds: f32, cutoff: f32, tau: f32, hz: f32, amount: f32, seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(cutoff);
    let n = (seconds * RATE as f32) as usize;
    (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let env = (-t / tau).exp();
            soft(lp.run(rng.next()) * env * 1.2 + (TAU * hz * t).sin() * (-t / (tau * 1.5)).exp() * amount)
        })
        .collect()
}

/// A looping engine note: harmonics of `f0` plus a little filtered noise, cut to whole cycles.
fn engine(f0: f32, harmonics: usize, grit: f32, seed: u64) -> Vec<f32> {
    let cycles = (f0 * 1.0).round().max(1.0);
    let n = (cycles / f0 * RATE as f32).round() as usize;
    let f = cycles / (n as f32 / RATE as f32);
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(f0 * 6.0);
    (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let phase = TAU * f * t;
            let mut v = 0.0;
            for k in 1..=harmonics {
                v += (phase * k as f32).sin() / (k as f32).powf(1.1);
            }
            // The exhaust pulse: a sharp peak once per cycle.
            let p = (phase / TAU).fract();
            let q = p.min(1.0 - p);
            v += (-(q * q) / 0.004).exp() * 1.2;
            soft(v * 0.45 + lp.run(rng.next()) * grit)
        })
        .collect()
}

/// A seamless loop: the last `fade` seconds cross-fade into the start.
fn looped(mut v: Vec<f32>, fade: f32) -> Vec<f32> {
    let f = (fade * RATE as f32) as usize;
    let n = v.len() - f;
    for i in 0..f {
        let k = i as f32 / f as f32;
        v[i] = v[i] * k + v[n + i] * (1.0 - k);
    }
    v.truncate(n);
    v
}

fn wind(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(400.0);
    let mut lp2 = LowPass::new(120.0);
    let n = (4.0 * RATE as f32) as usize;
    let v = (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let gust = 0.55 + 0.45 * (TAU * t / 4.0).sin() * (TAU * t / 1.3).sin();
            let x = rng.next();
            (lp.run(x) * 0.7 + lp2.run(x) * 1.5) * gust
        })
        .collect();
    looped(v, 0.5)
}

/// Rain: bright noise with scattered drop ticks.
fn rain(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(5000.0);
    let mut lp2 = LowPass::new(300.0);
    let n = (3.0 * RATE as f32) as usize;
    let mut v: Vec<f32> = (0..n)
        .map(|_| {
            let x = rng.next();
            let hi = lp.run(x) - lp2.run(x);
            hi * 0.5
        })
        .collect();
    for _ in 0..300 {
        let at = ((rng.next() * 0.5 + 0.5) * (n - 200) as f32) as usize;
        let amp = 0.2 + 0.3 * rng.next().abs();
        for k in 0..120 {
            v[at + k] += amp * (-(k as f32) / 18.0).exp() * rng.next();
        }
    }
    looped(v.into_iter().map(soft).collect(), 0.3)
}

fn surf(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(900.0);
    let n = (9.0 * RATE as f32) as usize;
    let v = (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let swell = (0.5 + 0.5 * (TAU * t / 8.5 - PI / 2.0).sin()).powf(2.5);
            lp.run(rng.next()) * (0.15 + 0.85 * swell) * 1.3
        })
        .collect();
    looped(v, 0.5)
}

/// Sine notes in a row, each `len` s with a soft decay.
fn jingle(notes: &[f32], len: f32) -> Vec<f32> {
    let per = (len * RATE as f32) as usize;
    let mut v = Vec::with_capacity(per * notes.len() + per);
    for (k, hz) in notes.iter().enumerate() {
        for i in 0..per + per / 2 {
            let t = i as f32 / RATE as f32;
            let s = ((TAU * hz * t).sin() + 0.3 * (TAU * hz * 2.0 * t).sin()) * (-t / (len * 0.6)).exp() * 0.4;
            let at = k * per + i;
            if at >= v.len() {
                v.push(s);
            } else {
                v[at] += s;
            }
        }
    }
    v
}

fn load(mut commands: Commands, tuning: Res<Tuning>, server: Res<AssetServer>, mut sources: ResMut<Assets<AudioSource>>) {
    let start = std::time::Instant::now();
    let mut clip = |name: &str, synth: Vec<f32>| -> Handle<AudioSource> {
        let path = format!("assets/sounds/{name}.ogg");
        if std::fs::metadata(&path).is_ok() {
            server.load(format!("sounds/{name}.ogg"))
        } else {
            sources.add(wav(&synth))
        }
    };
    let sounds = Sounds {
        rocket: clip("rocket", whoosh(11)),
        rifle: clip("rifle", gunshot(0.4, 0.018, 130.0, 0.7, 0.14, 6000.0, 21)),
        shotgun: clip("shotgun", gunshot(0.55, 0.035, 75.0, 1.0, 0.2, 3500.0, 31)),
        pistol: clip("pistol", gunshot(0.28, 0.011, 160.0, 0.45, 0.08, 7000.0, 41)),
        explosion: clip("explosion", gunshot(1.8, 0.09, 42.0, 1.1, 0.7, 500.0, 51)),
        steps: [
            clip("step1", thud(0.1, 900.0, 0.022, 95.0, 0.3, 61)),
            clip("step2", thud(0.1, 1100.0, 0.02, 85.0, 0.3, 62)),
            clip("step3", thud(0.1, 800.0, 0.025, 100.0, 0.3, 63)),
            clip("step4", thud(0.1, 1000.0, 0.021, 90.0, 0.3, 64)),
        ],
        land: clip("land", thud(0.25, 600.0, 0.06, 60.0, 0.7, 71)),
        jump: clip("jump", thud(0.12, 2500.0, 0.04, 200.0, 0.1, 81)),
        hit: clip("hit", thud(0.14, 700.0, 0.035, 110.0, 0.5, 91)),
        hurt: clip("hurt", thud(0.3, 400.0, 0.08, 70.0, 0.8, 101)),
        engine_big: clip("engine_big", engine(24.0, 12, 0.25, 111)),
        engine_small: clip("engine_small", engine(36.0, 10, 0.2, 121)),
        engine_bike: clip("engine_bike", engine(58.0, 8, 0.3, 131)),
        wind: clip("wind", wind(141)),
        surf: clip("surf", surf(151)),
        rain: clip("rain", rain(161)),
        pickup: clip("pickup", jingle(&[660.0, 880.0], 0.09)),
        extract: clip("extract", jingle(&[523.0, 659.0, 784.0, 1047.0], 0.13)),
        mission: clip("mission", jingle(&[392.0, 523.0, 659.0, 784.0, 1047.0], 0.12)),
    };
    commands.insert_resource(GlobalVolume { volume: Volume::Linear(tuning.sound.master) });
    commands.insert_resource(sounds);
    info!("sound: clips synthesized in {:.0} ms", start.elapsed().as_secs_f32() * 1000.0);
}

fn oneshot(commands: &mut Commands, clip: &Handle<AudioSource>, volume: f32, speed: f32) {
    commands.spawn((AudioPlayer(clip.clone()), PlaybackSettings::DESPAWN.with_volume(Volume::Linear(volume)).with_speed(speed)));
}

fn at(commands: &mut Commands, clip: &Handle<AudioSource>, pos: Vec3, volume: f32, speed: f32) {
    commands.spawn((
        AudioPlayer(clip.clone()),
        PlaybackSettings::DESPAWN.with_volume(Volume::Linear(volume)).with_speed(speed).with_spatial(true),
        Transform::from_translation(pos),
    ));
}

/// The camera hears.
fn listener(mut commands: Commands, camera: Query<Entity, (With<PlayerCamera>, Without<SpatialListener>)>) {
    for e in &camera {
        commands.entity(e).insert(SpatialListener::new(0.2));
    }
}

fn weapons(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, arsenal: Res<Arsenal>, mut fired: MessageReader<WeaponFired>, mut n: Local<u32>) {
    use crate::weapon::WeaponKind::*;
    for _ in fired.read() {
        *n += 1;
        let speed = 0.95 + (*n % 5) as f32 * 0.025;
        let clip = match WEAPONS[arsenal.current] {
            RocketLauncher | Grenade | Harpoon => &s.rocket,
            Rifle | Smg | Dmr => &s.rifle,
            Shotgun | Fist => &s.shotgun,
            Pistol | Revolver => &s.pistol,
        };
        oneshot(&mut commands, clip, tuning.sound.guns, speed);
    }
}

fn soldier_shots(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, mut shots: MessageReader<Shot>) {
    for shot in shots.read() {
        at(&mut commands, &s.rifle, shot.pos, tuning.sound.guns * 0.8, 0.9);
    }
}

fn explosions(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, blasts: Query<&Transform, Added<Explosion>>) {
    for tf in &blasts {
        at(&mut commands, &s.explosion, tf.translation, tuning.sound.guns * 1.2, 1.0);
    }
}

fn hits(
    mut commands: Commands,
    s: Res<Sounds>,
    tuning: Res<Tuning>,
    mut damage: MessageReader<Damage>,
    mut player_hits: MessageReader<PlayerHit>,
    targets: Query<&Transform, With<Target>>,
) {
    for d in damage.read() {
        if let Ok(tf) = targets.get(d.entity) {
            at(&mut commands, &s.hit, tf.translation, tuning.sound.effects, 1.0);
        }
    }
    for _ in player_hits.read() {
        oneshot(&mut commands, &s.hurt, tuning.sound.effects, 1.0);
    }
}

#[derive(Default)]
struct StepState {
    was: Option<MoveState>,
    dist: f32,
    n: usize,
}

/// A footstep every stride on the ground, a thud on landing, a swish on jumping.
fn steps(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, time: Res<Time>, health: Res<PlayerHealth>, player: Single<(&Player, Option<&crate::vehicle::Driving>)>, mut st: Local<StepState>) {
    let (p, driving) = *player;
    let v = tuning.sound.effects;
    if driving.is_some() || !health.alive() {
        st.was = Some(p.state);
        return;
    }
    let ground = matches!(p.state, MoveState::Ground | MoveState::Slide);
    if let Some(was) = st.was {
        let was_ground = matches!(was, MoveState::Ground | MoveState::Slide | MoveState::WallRun | MoveState::Mantle);
        if ground && !was_ground {
            oneshot(&mut commands, &s.land, v * 0.9, 1.0);
        }
        if was_ground && p.state == MoveState::Air && p.vertical() > 2.0 {
            oneshot(&mut commands, &s.jump, v * 0.5, 1.0);
        }
    }
    st.was = Some(p.state);
    if ground || p.state == MoveState::WallRun {
        let speed = p.velocity.xz().length();
        st.dist += speed * time.delta_secs();
        let stride = if p.crouched { 1.4 } else { 2.2 };
        if st.dist > stride && speed > 1.0 {
            st.dist = 0.0;
            st.n += 1;
            oneshot(&mut commands, &s.steps[st.n % 4], v * 0.6, 0.9 + (st.n % 3) as f32 * 0.07);
        }
    } else {
        st.dist = stride_reset(st.dist);
    }
}

fn stride_reset(d: f32) -> f32 {
    d.min(1.5)
}

#[derive(Component)]
struct EngineSound;

/// Every vehicle idles; the loop's speed follows rpm and its volume the throttle.
fn engines(
    mut commands: Commands,
    s: Res<Sounds>,
    tuning: Res<Tuning>,
    mut vehicles: Query<(Entity, &Vehicle, Option<&mut SpatialAudioSink>, Has<EngineSound>)>,
) {
    for (e, v, sink, has) in &mut vehicles {
        if !has {
            let clip = match v.spec.kind {
                Kind::Humvee => &s.engine_big,
                Kind::Jeep => &s.engine_small,
                Kind::DirtBike => &s.engine_bike,
            };
            commands.entity(e).insert((EngineSound, AudioPlayer(clip.clone()), PlaybackSettings::LOOP.with_spatial(true).with_volume(Volume::Linear(0.0))));
            continue;
        }
        let Some(mut sink) = sink else { continue };
        let base = (v.spec.idle * 1.6).max(500.0);
        sink.set_speed((v.rpm / base).clamp(0.4, 4.0));
        let load = 0.35 + 0.65 * v.throttle.abs();
        let running = if v.driver.is_some() { 1.0 } else { 0.25 };
        sink.set_volume(Volume::Linear(tuning.sound.engine * load * running));
    }
}

#[derive(Component)]
struct Wind;
#[derive(Component)]
struct Surf;
#[derive(Component)]
struct RainSound;

/// Wind grows with height and speed; surf is heard near the water line.
fn ambience(
    mut commands: Commands,
    s: Res<Sounds>,
    tuning: Res<Tuning>,
    hm: Option<Res<Heightmap>>,
    player: Single<(&Transform, &Player)>,
    mut wind: Query<&mut AudioSink, (With<Wind>, Without<Surf>, Without<RainSound>)>,
    mut surf: Query<&mut AudioSink, (With<Surf>, Without<Wind>, Without<RainSound>)>,
    mut rain: Query<&mut AudioSink, (With<RainSound>, Without<Wind>, Without<Surf>)>,
    weather: Option<Res<crate::world::Weather>>,
    mut started: Local<bool>,
) {
    if !*started {
        *started = true;
        commands.spawn((Wind, AudioPlayer(s.wind.clone()), PlaybackSettings::LOOP.with_volume(Volume::Linear(0.0))));
        commands.spawn((Surf, AudioPlayer(s.surf.clone()), PlaybackSettings::LOOP.with_volume(Volume::Linear(0.0))));
        commands.spawn((RainSound, AudioPlayer(s.rain.clone()), PlaybackSettings::LOOP.with_volume(Volume::Linear(0.0))));
        return;
    }
    let (tf, p) = *player;
    let a = tuning.sound.ambience;
    let water = tuning.island.water_level;
    let height = tf.translation.y - water;
    let speed = p.velocity.length();
    for mut sink in &mut wind {
        let storm = weather.as_ref().map_or(0.0, |w| w.cloud * 0.3 + w.rain * 0.3);
        let v = 0.15 + storm + (height / 120.0).clamp(0.0, 1.0) * 0.5 + (speed / 25.0).clamp(0.0, 1.0) * 0.6;
        sink.set_volume(Volume::Linear(a * v.min(1.2)));
        sink.set_speed(0.9 + (speed / 30.0).min(0.6));
    }
    // How close the sea is: the ground falls to the water line within a short walk.
    let shore = hm.as_ref().map_or(0.0, |hm| {
        let (x, z) = (tf.translation.x, tf.translation.z);
        let lowest = [(60.0, 0.0), (-60.0, 0.0), (0.0, 60.0), (0.0, -60.0), (0.0, 0.0)].iter().map(|(dx, dz)| hm.height_at(x + dx, z + dz) - water).fold(f32::MAX, f32::min);
        (1.0 - lowest / 12.0).clamp(0.0, 1.0)
    });
    for mut sink in &mut surf {
        sink.set_volume(Volume::Linear(a * shore * 0.9));
    }
    let wet = weather.as_ref().map_or(0.0, |w| w.rain);
    for mut sink in &mut rain {
        sink.set_volume(Volume::Linear(a * wet));
    }
}

#[derive(Default)]
struct JingleState {
    carried: u32,
    mission: usize,
}

fn jingles(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, inv: Option<Res<Inventory>>, missions: Option<Res<Missions>>, mut st: Local<JingleState>) {
    let v = tuning.sound.effects;
    if let Some(inv) = inv {
        if inv.just_extracted {
            oneshot(&mut commands, &s.extract, v, 1.0);
        } else if inv.carried > st.carried {
            oneshot(&mut commands, &s.pickup, v * 0.8, 1.0);
        }
        st.carried = inv.carried;
    }
    if let Some(m) = missions {
        if m.current > st.mission && st.mission > 0 || (m.current > st.mission && m.flash > 0.0) {
            oneshot(&mut commands, &s.mission, v, 1.0);
        }
        st.mission = m.current;
    }
}

#[allow(dead_code)]
fn _unused(_: PlaybackMode) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clips_are_bounded_and_decay() {
        for clip in [gunshot(0.4, 0.018, 130.0, 0.7, 0.14, 6000.0, 21), whoosh(11), thud(0.25, 600.0, 0.06, 60.0, 0.7, 71)] {
            assert!(clip.iter().all(|s| s.abs() <= 1.0));
            let head: f32 = clip[..clip.len() / 10].iter().map(|s| s.abs()).sum::<f32>() / (clip.len() / 10) as f32;
            let tail: f32 = clip[clip.len() * 9 / 10..].iter().map(|s| s.abs()).sum::<f32>() / (clip.len() / 10) as f32;
            assert!(head > 0.05 && tail < head * 0.2, "loud start {head}, quiet end {tail}");
        }
    }

    #[test]
    fn loops_are_seamless() {
        let e = engine(24.0, 12, 0.0, 1);
        let n = e.len();
        assert!((n as f32 / RATE as f32 - 1.0).abs() < 0.05, "about a second long");
        assert!((e[0] - e[n - 1]).abs() < 0.2, "the cycle closes: {} vs {}", e[0], e[n - 1]);
        let w = wind(3);
        assert_eq!(w.len(), (4.0 * RATE as f32) as usize - (0.5 * RATE as f32) as usize);
        let s = surf(5);
        assert!(s.iter().all(|x| x.abs() <= 1.0));
    }

    #[test]
    fn wav_has_a_valid_header() {
        let src = wav(&[0.0, 0.5, -0.5, 1.0]);
        assert_eq!(src.bytes.len(), 44 + 8);
        assert_eq!(&src.bytes[0..4], b"RIFF");
        assert_eq!(&src.bytes[36..40], b"data");
        assert_eq!(i16::from_le_bytes([src.bytes[50], src.bytes[51]]), 32767);
    }
}
