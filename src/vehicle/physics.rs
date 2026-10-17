//! Force models ported from Regolith Rally (`rust/src/physics`: tyre.rs, suspension.rs, gearbox.rs):
//! the combined-slip tyre curve, the coil-over with bump and rebound knees and its stops, and the engine
//! torque curve with engine braking. The constants are Regolith's params.json values. Rust Regime runs one
//! explicit raycast step per wheel at 66 Hz instead of Regolith's implicit soft-body solve, so these are the
//! curves and not the integrator; see `vehicle::drive` for how they are stepped.

/// A surface's tyre curve (Regolith `TYRE_SURF`): peak slip ratio `kp`, peak slip angle `ap` (rad), and the
/// Pacejka-like shape `c` and stiffness `b` (`bc` = b * c, the slope at zero slip).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TyreCurve {
    pub kp: f32,
    pub ap: f32,
    pub c: f32,
    pub b: f32,
}

impl TyreCurve {
    /// Regolith's tarmac curve, for roads later.
    #[allow(dead_code)]
    pub const TARMAC: TyreCurve = TyreCurve { kp: 0.10, ap: 0.12, c: 1.42, b: 1.9952384 };
    /// Regolith's gravel curve: softer, with a longer, flatter peak. The island's grass and sand use it.
    pub const GRAVEL: TyreCurve = TyreCurve { kp: 0.16, ap: 0.19, c: 1.25, b: 3.0776835 };

}

/// Tyre forces: `fx` along the wheel (forward), `fy` across it (to the left), `s` the combined slip (1 at the peak).
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct TyreForce {
    pub fx: f32,
    pub fy: f32,
    pub s: f32,
}

/// Regolith `tyreForce`: the force a tyre with peak grip `fmax` gives at slip ratio `kappa` and slip angle
/// `alpha` (rad, positive when the contact patch slides to the left, so the force pushes right).
pub fn tyre_force(curve: &TyreCurve, fmax: f32, kappa: f32, alpha: f32) -> TyreForce {
    let sx = kappa / curve.kp;
    let sy = alpha / curve.ap;
    let s = sx.hypot(sy);
    if s < 1e-6 || fmax <= 0.0 {
        return TyreForce { s, ..Default::default() };
    }
    let f = (curve.c * (curve.b * s).atan()).sin();
    TyreForce { fx: fmax * f * sx / s, fy: -fmax * f * sy / s, s }
}

/// Regolith `SUSP`: the damper's knees and the stops, as fractions of the base stiffness and damping.
#[derive(Clone, Copy, Debug)]
pub struct Susp {
    pub bump: f32,
    pub rebound: f32,
    pub bump_knee: f32,
    pub bump_hi: f32,
    pub reb_knee: f32,
    pub reb_hi: f32,
    pub stop_len: f32,
    pub stop_k: f32,
    pub stop_c: f32,
    pub stop_r: f32,
    pub deep_at: f32,
    pub deep_r: f32,
    pub hard_k: f32,
    pub arb: f32,
}

pub const SUSP: Susp = Susp {
    bump: 0.85,
    rebound: 1.2,
    bump_knee: 0.7,
    bump_hi: 0.4,
    reb_knee: 0.5,
    reb_hi: 0.35,
    stop_len: 0.06,
    stop_k: 6.0,
    stop_c: 12.0,
    stop_r: 0.4,
    deep_at: 0.4,
    deep_r: 3.0,
    hard_k: 10.0,
    arb: 0.8,
};

/// Regolith `coilover(x, v, kS, cB, cR, cD, mS)`: the force (N) of a coil-over compressed `x` m and closing at
/// `v` m/s, with spring rate `k_s`, bump and rebound damping `c_b` and `c_r` (N·s/m), critical damping `c_d`,
/// the sprung mass `m_s` it carries, its static `sag` and full `travel`. Digressive damping, firmer rebound deep
/// in the stroke, a rising-rate hydraulic bump stop over the last `stop_len`, and a stiff damped hard stop.
#[allow(clippy::too_many_arguments)]
pub fn coilover(s: &Susp, x: f32, v: f32, k_s: f32, c_b: f32, c_r: f32, c_d: f32, m_s: f32, sag: f32, travel: f32) -> f32 {
    let mut f = k_s * x;
    if v >= 0.0 {
        f += c_b * if v > s.bump_knee { s.bump_knee + (v - s.bump_knee) * s.bump_hi } else { v };
    } else {
        let a = -v;
        f -= c_r * if a > s.reb_knee { s.reb_knee + (a - s.reb_knee) * s.reb_hi } else { a };
        let x0 = sag + s.deep_at * (travel - sag);
        let e = ((x - x0) / (travel - x0).max(1e-3)).clamp(0.0, 1.0);
        f -= c_r * s.deep_r * e * a;
    }
    let on = x - (travel - s.stop_len);
    if on > 0.0 {
        let e = on / s.stop_len;
        f += k_s * s.stop_k * on * e;
        let c_s = c_d * s.stop_c;
        f += if v > 0.0 { c_s } else { c_s * s.stop_r } * e * v;
    }
    let past = x - travel;
    if past > 0.0 {
        let k_h = k_s * s.hard_k;
        let c_h = 2.0 * (k_h * m_s).sqrt();
        f += (k_h * past + c_h * v).max(0.0);
    }
    f
}

/// Regolith `engineTorque`: full-throttle torque (N·m) from a `(rpm, torque)` curve, interpolated linearly.
pub fn engine_torque(curve: &[(f32, f32)], rpm: f32) -> f32 {
    if rpm <= curve[0].0 {
        return curve[0].1;
    }
    for k in 1..curve.len() {
        if rpm <= curve[k].0 {
            let t = (rpm - curve[k - 1].0) / (curve[k].0 - curve[k - 1].0);
            return curve[k - 1].1 + (curve[k].1 - curve[k - 1].1) * t;
        }
    }
    curve[curve.len() - 1].1
}

/// Regolith `engineNet`: net crank torque at `rpm` for throttle `th` (0..1), with the driveline's efficiency
/// `eta`; off the throttle the engine brakes by its displacement `disp` (litres), more the faster it turns.
pub fn engine_net(curve: &[(f32, f32)], rpm: f32, th: f32, disp: f32, redline: f32, eta: f32) -> f32 {
    th * engine_torque(curve, rpm) * eta - (1.0 - th) * disp * (9.0 + 21.0 * rpm / redline) / eta
}

/// Regolith `damp`: exponential approach of `a` to `b` at `rate` per second.
pub fn damp(a: f32, b: f32, rate: f32, dt: f32) -> f32 {
    a + (b - a) * (1.0 - (-rate * dt).exp())
}
