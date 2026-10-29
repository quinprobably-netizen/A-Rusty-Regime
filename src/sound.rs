//! Sound (hyper-realism stage R2), all synthesized at startup so the download stays small:
//! gunshots with a crack, a thump and a tail; footsteps, landings and hits; looping engines
//! pitched by rpm on each vehicle; wind that grows with height and speed; and the ship fight's
//! nose guns, missile launches, wrecks, shield and hull hits, lock tone and missile warning,
//! played as `solar::cockpit` cues them (it has already counted distance and the air).
//! Drop CC0 samples in `assets/sounds/`
//! later and `load` picks them over the synthesis.

use std::f32::consts::{PI, TAU};
use std::sync::Arc;

use bevy::audio::{AudioSink, AudioSinkPlayback, GlobalVolume, SpatialListener, Volume};
use bevy::prelude::*;

use crate::camera::PlayerCamera;
use crate::controller::{MoveState, Player};
use crate::health::{PlayerHealth, PlayerHit};
use crate::hud::FlightHud;
use crate::solar::cockpit::{Cue, Sfx};
use crate::tuning::Tuning;
use crate::weapon::{Arsenal, Bullet, Explosion, WeaponFired, WeaponKind, WEAPONS};

pub struct SoundPlugin;

impl Plugin for SoundPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load).add_systems(
            Update,
            (listener, weapons, explosions, hits, steps, ambience, reload_foley, whizz_by, fight, lock_tone).run_if(resource_exists::<Sounds>),
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
    swish: Handle<AudioSource>,
    explosion: Handle<AudioSource>,
    steps: [Handle<AudioSource>; 4],
    land: Handle<AudioSource>,
    jump: Handle<AudioSource>,
    hurt: Handle<AudioSource>,
    wind: Handle<AudioSource>,
    /// Three takes of each gun's shot, by weapon slot (empty for the rest).
    shots: Vec<Vec<Handle<AudioSource>>>,
    whizz: Handle<AudioSource>,
    draw: Handle<AudioSource>,
    foley: Vec<Handle<AudioSource>>,
    /// The ship fight: takes of a nose gun's shot, a missile launch, shield and hull hits, a lock
    /// beep, the steady locked tone (a loop) and the missile warning.
    ship_gun: Vec<Handle<AudioSource>>,
    launch: Handle<AudioSource>,
    shield_hit: Handle<AudioSource>,
    hull_hit: Handle<AudioSource>,
    lock_beep: Handle<AudioSource>,
    lock_tone: Handle<AudioSource>,
    warning: Handle<AudioSource>,
    /// Salvage: scrap clinking aboard, and the chime of a module found.
    scrap: Handle<AudioSource>,
    module: Handle<AudioSource>,
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

/// How one gun's shot is built: the layers of `shot`.
struct Voice {
    /// Seconds the sharp transient lasts.
    crack: f32,
    /// Seconds the filtered body lasts, and its low-pass cutoff in Hz.
    body: f32,
    cutoff: f32,
    /// The sub thump's pitch (Hz) and level.
    sub_hz: f32,
    sub: f32,
    /// Seconds of low tail.
    tail: f32,
    /// Level of the mechanical click that lands just before the transient.
    click: f32,
}

/// A layered gunshot: a mechanical click, then a bright transient, a body, a sub thump and a tail.
/// `take` nudges the cutoff and tail, so each take of the same gun differs a little.
fn shot(v: &Voice, take: u32, seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let jitter = 1.0 + (take as f32 - 1.0) * 0.08;
    let mut body_lp = LowPass::new(v.cutoff * jitter);
    let mut tail_lp = LowPass::new(450.0);
    let mut hp = LowPass::new(2500.0);
    let mut click_lp = LowPass::new(1500.0);
    let offset = (0.006 * RATE as f32) as usize;
    let seconds = v.tail * 2.2 * (2.0 - jitter) + 0.1;
    let n = (seconds * RATE as f32) as usize;
    (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let noise = rng.next();
            let click = (noise - click_lp.run(noise)) * (-t / 0.003).exp() * v.click;
            let t2 = i.saturating_sub(offset) as f32 / RATE as f32;
            let on = (i >= offset) as u8 as f32;
            let crack = (noise - hp.run(noise)) * (-t2 / v.crack).exp() * 1.1 * on;
            let body = body_lp.run(noise) * (-t2 / v.body).exp() * 1.3 * on;
            let sub = (TAU * v.sub_hz * t2 * (1.0 - 0.4 * t2.min(1.0))).sin() * (-t2 / 0.09).exp() * v.sub * on;
            let tail = tail_lp.run(noise) * (-t2 / (v.tail * (2.0 - jitter))).exp() * 0.45 * on;
            soft((click + crack + body + sub + tail) * 1.2)
        })
        .collect()
}

/// A metallic tick or clack: a noise burst over a few inharmonic partials of `hz`, ringing for `decay` s.
fn clack(len: f32, hz: f32, decay: f32, seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    (0..(len * RATE as f32) as usize)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let burst = rng.next() * (-t / 0.002).exp() * 0.6;
            let ring = ((TAU * hz * t).sin() * 0.5 + (TAU * hz * 2.76 * t).sin() * 0.3 + (TAU * hz * 5.4 * t).sin() * 0.15) * (-t / decay).exp();
            soft(burst + ring)
        })
        .collect()
}

/// A slide or bolt dragging: band-limited noise whose pitch sweeps up.
fn scrape(len: f32, seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(3000.0);
    let mut hp = LowPass::new(700.0);
    (0..(len * RATE as f32) as usize)
        .map(|i| {
            let t = i as f32 / len / RATE as f32;
            let n = rng.next();
            let band = lp.run(n) - hp.run(n);
            band * (t * PI).sin().powf(0.7) * 1.6
        })
        .collect()
}

/// `parts` laid end to end by start time (seconds), summed.
fn mix(parts: &[(f32, Vec<f32>)]) -> Vec<f32> {
    let end = parts.iter().map(|(at, v)| (*at * RATE as f32) as usize + v.len()).max().unwrap_or(0);
    let mut out = vec![0.0; end];
    for (at, v) in parts {
        let start = (*at * RATE as f32) as usize;
        for (i, x) in v.iter().enumerate() {
            out[start + i] += x;
        }
    }
    out
}

/// An incoming round passing close: a sharp crack, then a zip that drops in pitch.
fn whizz(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut hp = LowPass::new(3500.0);
    let mut phase = 0.0;
    (0..(0.2 * RATE as f32) as usize)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let noise = rng.next();
            let crack = (noise - hp.run(noise)) * (-t / 0.006).exp();
            phase += TAU * (1800.0 + 3800.0 * (-t / 0.05).exp()) / RATE as f32;
            let zip = phase.sin() * (1.0 - (-t / 0.004).exp()) * (-t / 0.07).exp() * 0.5;
            soft(crack + zip)
        })
        .collect()
}

/// What the foley sounds are, in `Sounds::foley` order.
#[derive(Clone, Copy)]
enum Foley {
    MagOut,
    MagIn,
    Rack,
    Pump,
    Shell,
    Close,
    Heavy,
}

/// When in a reload (0 to 1 of its length) each sound lands, by weapon.
fn reload_events(kind: WeaponKind) -> &'static [(f32, Foley)] {
    use Foley::*;
    use WeaponKind::*;
    match kind {
        Rifle | Smg | Dmr => &[(0.2, MagOut), (0.55, MagIn), (0.85, Rack)],
        Pistol => &[(0.2, MagOut), (0.6, MagIn), (0.88, Rack)],
        Revolver => &[(0.15, Close), (0.4, Shell), (0.55, Shell), (0.7, Shell), (0.9, Close)],
        Shotgun => &[(0.15, Shell), (0.3, Shell), (0.45, Shell), (0.6, Shell), (0.85, Pump)],
        RocketLauncher | Grenade | Harpoon => &[(0.4, Heavy), (0.85, Close)],
        Fist | Knife => &[],
    }
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

/// A missile leaving its rail: a thump as the motor lights, then a roar whose filter opens and a
/// hiss, trailing off as it pulls away.
fn launch(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut lp = LowPass::new(250.0);
    let mut hp = LowPass::new(4000.0);
    (0..(1.4 * RATE as f32) as usize)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            lp.a = (TAU * (250.0 + 2200.0 * (t / 0.3).min(1.0)) / RATE as f32).min(1.0);
            let n = rng.next();
            let roar = lp.run(n) * (t / 0.04).min(1.0) * (-t / 0.4).exp() * 1.6;
            let hiss = (n - hp.run(n)) * (-t / 0.15).exp() * 0.35;
            let thump = (TAU * 48.0 * t).sin() * (-t / 0.1).exp() * 0.9;
            soft(roar + hiss + thump)
        })
        .collect()
}

/// The shield taking a hit: a fizz and a buzzing zap that drops in pitch.
fn zap(seed: u64) -> Vec<f32> {
    let mut rng = Rng(seed);
    let mut phase = 0.0;
    (0..(0.3 * RATE as f32) as usize)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            phase += TAU * (280.0 + 1400.0 * (-t / 0.05).exp()) / RATE as f32;
            let buzz = (phase.sin().signum() * 0.3 + phase.sin() * 0.4) * (0.65 + 0.35 * (TAU * 55.0 * t).sin());
            let fizz = rng.next() * (-t / 0.015).exp() * 0.6;
            soft((buzz + fizz) * (-t / 0.08).exp() * 1.2)
        })
        .collect()
}

/// A pure tone of `hz` for `seconds`, `edge` seconds of fade in and out (none for a loop, which
/// then wants a whole number of cycles).
fn tone(seconds: f32, hz: f32, level: f32, edge: f32) -> Vec<f32> {
    let n = (seconds * RATE as f32) as usize;
    (0..n)
        .map(|i| {
            let t = i as f32 / RATE as f32;
            let fade = if edge > 0.0 { (t / edge).min((seconds - t) / edge).clamp(0.0, 1.0) } else { 1.0 };
            ((TAU * hz * t).sin() * 0.8 + (TAU * hz * 2.0 * t).sin() * 0.2) * level * fade
        })
        .collect()
}

/// The missile warning: two quick chirps sweeping up.
fn chirp() -> Vec<f32> {
    let one = |len: f32| -> Vec<f32> {
        let mut phase = 0.0;
        (0..(len * RATE as f32) as usize)
            .map(|i| {
                let t = i as f32 / RATE as f32;
                phase += TAU * (1500.0 + 1100.0 * t / len) / RATE as f32;
                phase.sin() * 0.6 * (t / 0.004).min((len - t) / 0.006).clamp(0.0, 1.0)
            })
            .collect()
    };
    mix(&[(0.0, one(0.06)), (0.09, one(0.06))])
}

/// Scrap pulled aboard: a metal clink under two quick rising notes.
fn clink(seed: u64) -> Vec<f32> {
    mix(&[(0.0, clack(0.12, 2400.0, 0.02, seed)), (0.01, tone(0.06, 1320.0, 0.35, 0.004)), (0.06, tone(0.1, 1980.0, 0.35, 0.01))])
}

/// A module found: three notes climbing, the last held and shimmering.
fn chime() -> Vec<f32> {
    let held: Vec<f32> = tone(0.5, 1320.0, 0.4, 0.01).into_iter().enumerate().map(|(i, x)| {
        let t = i as f32 / RATE as f32;
        x * (-t / 0.25).exp() * (0.8 + 0.2 * (TAU * 9.0 * t).sin())
    }).collect();
    mix(&[(0.0, tone(0.1, 660.0, 0.4, 0.008)), (0.09, tone(0.1, 880.0, 0.4, 0.008)), (0.18, held)])
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
    // WEAPONS order: rocket rifle shotgun pistol smg dmr revolver grenade harpoon fist knife.
    let voices: [Option<Voice>; 11] = [
        None,
        Some(Voice { crack: 0.012, body: 0.05, cutoff: 7000.0, sub_hz: 110.0, sub: 0.5, tail: 0.16, click: 0.4 }),
        Some(Voice { crack: 0.02, body: 0.09, cutoff: 4200.0, sub_hz: 70.0, sub: 1.0, tail: 0.28, click: 0.3 }),
        Some(Voice { crack: 0.008, body: 0.035, cutoff: 8000.0, sub_hz: 150.0, sub: 0.4, tail: 0.09, click: 0.35 }),
        Some(Voice { crack: 0.006, body: 0.025, cutoff: 8500.0, sub_hz: 120.0, sub: 0.3, tail: 0.07, click: 0.5 }),
        Some(Voice { crack: 0.015, body: 0.07, cutoff: 5500.0, sub_hz: 90.0, sub: 0.8, tail: 0.3, click: 0.3 }),
        Some(Voice { crack: 0.012, body: 0.06, cutoff: 5000.0, sub_hz: 80.0, sub: 1.0, tail: 0.24, click: 0.25 }),
        Some(Voice { crack: 0.02, body: 0.08, cutoff: 1800.0, sub_hz: 55.0, sub: 1.1, tail: 0.2, click: 0.6 }),
        None,
        None,
        None,
    ];
    let shots: Vec<Vec<Handle<AudioSource>>> = voices
        .iter()
        .enumerate()
        .map(|(slot, voice)| match voice {
            Some(v) => (0..3).map(|take| clip(&format!("shot_{}_{take}", WEAPONS[slot].id()), shot(v, take, 1000 + slot as u64 * 10 + take as u64 * 3))).collect(),
            None => vec![],
        })
        .collect();
    let foley: Vec<Handle<AudioSource>> = vec![
        clip("foley_mag_out", mix(&[(0.0, clack(0.09, 900.0, 0.012, 301)), (0.03, scrape(0.07, 302))])),
        clip("foley_mag_in", mix(&[(0.0, scrape(0.06, 303)), (0.05, clack(0.12, 650.0, 0.02, 304)), (0.1, clack(0.08, 1500.0, 0.01, 305))])),
        clip("foley_rack", mix(&[(0.0, scrape(0.12, 306)), (0.11, clack(0.1, 1400.0, 0.015, 307))])),
        clip("foley_pump", mix(&[(0.0, scrape(0.1, 308)), (0.09, clack(0.1, 1000.0, 0.02, 309)), (0.2, clack(0.12, 800.0, 0.02, 310))])),
        clip("foley_shell", clack(0.07, 3200.0, 0.008, 311)),
        clip("foley_close", clack(0.1, 1200.0, 0.02, 312)),
        clip("foley_heavy", mix(&[(0.0, scrape(0.14, 313)), (0.13, clack(0.15, 380.0, 0.04, 314))])),
    ];
    let sounds = Sounds {
        rocket: clip("rocket", whoosh(11)),
        rifle: clip("rifle", gunshot(0.4, 0.018, 130.0, 0.7, 0.14, 6000.0, 21)),
        shotgun: clip("shotgun", gunshot(0.55, 0.035, 75.0, 1.0, 0.2, 3500.0, 31)),
        pistol: clip("pistol", gunshot(0.28, 0.011, 160.0, 0.45, 0.08, 7000.0, 41)),
        swish: clip("swish", thud(0.16, 5500.0, 0.05, 220.0, 0.05, 141)),
        explosion: clip("explosion", gunshot(1.8, 0.09, 42.0, 1.1, 0.7, 500.0, 51)),
        steps: [
            clip("step1", thud(0.1, 900.0, 0.022, 95.0, 0.3, 61)),
            clip("step2", thud(0.1, 1100.0, 0.02, 85.0, 0.3, 62)),
            clip("step3", thud(0.1, 800.0, 0.025, 100.0, 0.3, 63)),
            clip("step4", thud(0.1, 1000.0, 0.021, 90.0, 0.3, 64)),
        ],
        land: clip("land", thud(0.25, 600.0, 0.06, 60.0, 0.7, 71)),
        jump: clip("jump", thud(0.12, 2500.0, 0.04, 200.0, 0.1, 81)),
        hurt: clip("hurt", thud(0.3, 400.0, 0.08, 70.0, 0.8, 101)),
        wind: clip("wind", wind(141)),
        shots,
        whizz: clip("whizz", whizz(73)),
        draw: clip("draw", mix(&[(0.0, scrape(0.08, 74)), (0.07, clack(0.08, 1100.0, 0.012, 75))])),
        foley,
        ship_gun: (0..3).map(|take| clip(&format!("ship_gun_{take}"), shot(&Voice { crack: 0.008, body: 0.05, cutoff: 3500.0, sub_hz: 62.0, sub: 1.0, tail: 0.14, click: 0.0 }, take, 401 + take as u64 * 3))).collect(),
        launch: clip("missile_launch", launch(411)),
        shield_hit: clip("shield_hit", zap(421)),
        hull_hit: clip("hull_hit", mix(&[(0.0, gunshot(0.3, 0.005, 95.0, 0.6, 0.05, 6500.0, 431)), (0.0, clack(0.45, 280.0, 0.1, 432))]).into_iter().map(|x| x * 0.6).collect()),
        lock_beep: clip("lock_beep", tone(0.07, 1000.0, 0.5, 0.008)),
        lock_tone: clip("lock_tone", tone(1.0, 1250.0, 0.4, 0.0)),
        warning: clip("missile_warning", chirp()),
        scrap: clip("salvage_scrap", clink(441)),
        module: clip("salvage_module", chime()),
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

fn weapons(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, arsenal: Res<Arsenal>, mut fired: MessageReader<WeaponFired>, mut n: Local<(u32, usize)>) {
    use crate::weapon::WeaponKind::*;
    for _ in fired.read() {
        n.0 += 1;
        let speed = 0.985 + (n.0 * 13 % 7) as f32 * 0.005;
        // A gun with its own voice cycles through its takes, never the same one twice running.
        if let Some(takes) = s.shots.get(arsenal.current).filter(|v| !v.is_empty()) {
            let mut take = (n.0 as usize * 7 + 3) % takes.len();
            if take == n.1 {
                take = (take + 1) % takes.len();
            }
            n.1 = take;
            oneshot(&mut commands, &takes[take], tuning.sound.guns, speed);
            continue;
        }
        let clip = match WEAPONS[arsenal.current] {
            RocketLauncher | Grenade | Harpoon => &s.rocket,
            Rifle | Smg | Dmr => &s.rifle,
            Shotgun | Fist => &s.shotgun,
            Knife => &s.swish,
            Pistol | Revolver => &s.pistol,
        };
        oneshot(&mut commands, clip, tuning.sound.guns, speed);
    }
}

/// Mag out, mag in, rack and so on, each at its moment in the reload; a click on drawing a weapon.
fn reload_foley(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, arsenal: Res<Arsenal>, mut last: Local<(usize, f32)>) {
    let kind = arsenal.kind();
    if arsenal.current != last.0 {
        *last = (arsenal.current, 0.0);
        oneshot(&mut commands, &s.draw, tuning.sound.guns * 0.5, 1.0);
        return;
    }
    let total = kind.reload_time(&tuning);
    if arsenal.reload > 0.0 && total > 0.0 {
        let now = 1.0 - arsenal.reload / total;
        let before = if last.1 > 0.0 { 1.0 - last.1 / total } else { -1.0 };
        for (at, foley) in reload_events(kind) {
            if before < *at && *at <= now {
                oneshot(&mut commands, &s.foley[*foley as usize], tuning.sound.guns * 0.55, 1.0);
            }
        }
    }
    last.1 = arsenal.reload;
}

/// A crack and a zip as an enemy round passes close to the camera, at its closest point.
fn whizz_by(
    mut commands: Commands,
    s: Res<Sounds>,
    tuning: Res<Tuning>,
    camera: Single<&Transform, With<PlayerCamera>>,
    player: Single<Entity, With<Player>>,
    bullets: Query<(Entity, &Transform, &Bullet)>,
    mut seen: Local<std::collections::HashSet<Entity>>,
) {
    seen.retain(|e| bullets.contains(*e));
    for (e, tf, b) in &bullets {
        if b.owner == *player || seen.contains(&e) {
            continue;
        }
        let rel = camera.translation - tf.translation;
        let along = rel.dot(b.velocity) / b.velocity.length_squared().max(1.0);
        if !(-0.03..=0.05).contains(&along) {
            continue;
        }
        let closest = tf.translation + b.velocity * along;
        if closest.distance(camera.translation) < 3.5 {
            seen.insert(e);
            at(&mut commands, &s.whizz, closest, tuning.sound.guns * 0.9, 1.0 + (e.to_bits() % 5) as f32 * 0.03);
        }
    }
}

fn explosions(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, blasts: Query<&Transform, Added<Explosion>>) {
    for tf in &blasts {
        at(&mut commands, &s.explosion, tf.translation, tuning.sound.guns * 1.2, 1.0);
    }
}

/// The ship fight's sounds, as `solar::cockpit` cues them. A wreck is the explosion played slower,
/// so deeper and longer than a missile's burst.
fn fight(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, mut cues: MessageReader<Cue>, mut n: Local<usize>) {
    let (guns, effects) = (tuning.sound.guns, tuning.sound.effects);
    for cue in cues.read() {
        let (clip, level) = match cue.sfx {
            Sfx::Gun => {
                *n += 1;
                (&s.ship_gun[*n % s.ship_gun.len()], guns * 0.8)
            }
            Sfx::Launch => (&s.launch, guns),
            Sfx::Wreck => (&s.explosion, guns * 1.3),
            Sfx::Burst => (&s.explosion, guns),
            Sfx::ShieldHit => (&s.shield_hit, effects * 0.8),
            Sfx::HullHit => (&s.hull_hit, effects),
            Sfx::LockBeep => (&s.lock_beep, effects * 0.5),
            Sfx::Warning => (&s.warning, effects * 0.7),
            Sfx::Scrap => (&s.scrap, effects * 0.7),
            Sfx::Module => (&s.module, effects * 0.8),
        };
        oneshot(&mut commands, clip, level * cue.volume, cue.pitch);
    }
}

#[derive(Component)]
struct LockTone;

/// A steady tone while your missiles hold a lock (the beeps before it are cues).
fn lock_tone(mut commands: Commands, s: Res<Sounds>, tuning: Res<Tuning>, flight: Res<FlightHud>, mut tone: Query<&mut AudioSink, With<LockTone>>, mut started: Local<bool>) {
    if !*started {
        *started = true;
        commands.spawn((LockTone, AudioPlayer(s.lock_tone.clone()), PlaybackSettings::LOOP.with_volume(Volume::Linear(0.0))));
        return;
    }
    let locked = flight.active && flight.fight.lock >= 1.0;
    for mut sink in &mut tone {
        sink.set_volume(Volume::Linear(if locked { tuning.sound.effects * 0.35 } else { 0.0 }));
    }
}

fn hits(
    mut commands: Commands,
    s: Res<Sounds>,
    tuning: Res<Tuning>,
    mut player_hits: MessageReader<PlayerHit>,
) {
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
struct Wind;

/// Wind grows with height and speed.
fn ambience(
    mut commands: Commands,
    s: Res<Sounds>,
    tuning: Res<Tuning>,
    player: Single<(&Transform, &Player)>,
    mut wind: Query<&mut AudioSink, With<Wind>>,
    mut started: Local<bool>,
) {
    if !*started {
        *started = true;
        commands.spawn((Wind, AudioPlayer(s.wind.clone()), PlaybackSettings::LOOP.with_volume(Volume::Linear(0.0))));
        return;
    }
    let (tf, p) = *player;
    let a = tuning.sound.ambience;
    let height = tf.translation.y;
    let speed = p.velocity.length();
    for mut sink in &mut wind {
        let v = 0.15 + (height / 120.0).clamp(0.0, 1.0) * 0.5 + (speed / 25.0).clamp(0.0, 1.0) * 0.6;
        sink.set_volume(Volume::Linear(a * v.min(1.2)));
        sink.set_speed(0.9 + (speed / 30.0).min(0.6));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shots_and_foley_are_bounded() {
        let v = Voice { crack: 0.012, body: 0.05, cutoff: 7000.0, sub_hz: 110.0, sub: 0.5, tail: 0.16, click: 0.4 };
        for clip in [shot(&v, 0, 1), shot(&v, 2, 2), clack(0.1, 900.0, 0.015, 3), scrape(0.1, 4), whizz(5), mix(&[(0.0, scrape(0.1, 6)), (0.1, clack(0.1, 900.0, 0.02, 7))]), chirp(), tone(0.07, 1000.0, 0.5, 0.008), clink(5), chime()] {
            assert!(clip.len() > 100 && clip.iter().all(|x| x.is_finite() && x.abs() <= 1.01 * 2.0), "clip stays in range");
        }
        assert!(shot(&v, 0, 1) != shot(&v, 2, 1), "takes differ");
    }

    #[test]
    fn clips_are_bounded_and_decay() {
        for clip in [gunshot(0.4, 0.018, 130.0, 0.7, 0.14, 6000.0, 21), whoosh(11), thud(0.25, 600.0, 0.06, 60.0, 0.7, 71), launch(411), zap(421)] {
            assert!(clip.iter().all(|s| s.abs() <= 1.0));
            let head: f32 = clip[..clip.len() / 10].iter().map(|s| s.abs()).sum::<f32>() / (clip.len() / 10) as f32;
            let tail: f32 = clip[clip.len() * 9 / 10..].iter().map(|s| s.abs()).sum::<f32>() / (clip.len() / 10) as f32;
            assert!(head > 0.05 && tail < head * 0.2, "loud start {head}, quiet end {tail}");
        }
    }

    #[test]
    fn loops_are_seamless() {
        let w = wind(3);
        assert_eq!(w.len(), (4.0 * RATE as f32) as usize - (0.5 * RATE as f32) as usize);
        // The lock tone is whole cycles: its last sample runs on into its first.
        let lock = tone(1.0, 1250.0, 0.4, 0.0);
        let next = (TAU * 1250.0 * lock.len() as f32 / RATE as f32).sin() * 0.8 + (TAU * 2500.0 * lock.len() as f32 / RATE as f32).sin() * 0.2;
        assert!((next * 0.4 - lock[0]).abs() < 0.01 && lock.iter().all(|x| x.abs() <= 0.4));
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
