//! What the player can do, and which keys, mouse buttons and pad inputs do it, in one table.
//!
//! `BINDINGS` is the only place a button is tied to an `Action`. `read` turns the devices into an
//! `ActionState` each frame (for the context the player is in: on foot, driving, flying or in a
//! menu), `input::gather` turns that into the `PlayerInput` the game reads, the menu reads it for
//! navigation, and the Controls screen and README table are written from the same list. A test
//! fails when two actions in one context share a button.

use bevy::input::mouse::AccumulatedMouseScroll;
use bevy::prelude::*;
use std::collections::HashMap;

/// How long a pad button must be held to count as a hold rather than a tap.
pub const HOLD_SECONDS: f32 = 0.3;

/// Where the player is, which decides what the buttons do.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Ctx {
    Foot,
    Vehicle,
    Ship,
    Menu,
}

impl Ctx {
    pub const GAME: [Ctx; 3] = [Ctx::Foot, Ctx::Vehicle, Ctx::Ship];

    pub fn label(self) -> &'static str {
        match self {
            Ctx::Foot => "On foot",
            Ctx::Vehicle => "Driving",
            Ctx::Ship => "Flying",
            Ctx::Menu => "Menus",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Action {
    /// Two axes: strafe and forward (WASD, left stick). Steering and forward / back when driving.
    Move,
    // On foot
    Jump,
    Crouch,
    Fire,
    Aim,
    Reload,
    /// Board or leave a vehicle or the ship.
    Use,
    Ability,
    LastWeapon,
    NextWeapon,
    PrevWeapon,
    /// Draw the knife; again to put it away.
    Knife,
    /// A weapon slot, 0-based.
    Slot(u8),
    Flashlight,
    Inspect,
    ToggleView,
    Respawn,
    Pause,
    // Driving
    Gas,
    Brake,
    Handbrake,
    // Flying (roll left is positive)
    Thrust,
    Lift,
    Roll,
    Boost,
    /// Kill the ship's speed over the ground.
    Stop,
    /// Hold to look around the cockpit or the hull; let go and the view swings back.
    FreeLook,
    // Menus
    Up,
    Down,
    Left,
    Right,
    Select,
    Back,
    TabNext,
    TabPrev,
}

impl Action {
    pub fn label(self) -> &'static str {
        match self {
            Action::Move => "Move / steer",
            Action::Jump => "Jump / wall jump / double jump",
            Action::Crouch => "Crouch / slide",
            Action::Fire => "Fire",
            Action::Aim => "Aim down sights",
            Action::Reload => "Reload",
            Action::Use => "Enter / leave a vehicle or ship",
            Action::Ability => "Grapple",
            Action::LastWeapon => "Last weapon",
            Action::NextWeapon => "Next weapon",
            Action::PrevWeapon => "Previous weapon",
            Action::Knife => "Knife (draw / put away)",
            Action::Slot(_) => "Weapon 1-10",
            Action::Flashlight => "Flashlight",
            Action::Inspect => "Inspect weapon",
            Action::ToggleView => "First / third person",
            Action::Respawn => "Respawn",
            Action::Pause => "Menu",
            Action::Gas => "Gas",
            Action::Brake => "Brake / reverse",
            Action::Handbrake => "Handbrake",
            Action::Thrust => "Thrust / reverse",
            Action::Lift => "Lift / sink",
            Action::Roll => "Roll",
            Action::Boost => "Boost",
            Action::Stop => "Stop (match ground speed)",
            Action::FreeLook => "Look around (hold)",
            Action::Up => "Up",
            Action::Down => "Down",
            Action::Left => "Left / decrease",
            Action::Right => "Right / increase",
            Action::Select => "Select",
            Action::Back => "Back",
            Action::TabNext => "Next weapon (quartermaster)",
            Action::TabPrev => "Previous weapon (quartermaster)",
        }
    }
}

/// A physical input.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Source {
    Key(KeyCode),
    Mouse(MouseButton),
    WheelUp,
    WheelDown,
    /// A pad button; the triggers read as analog 0..1.
    Pad(GamepadButton),
    /// One pad stick axis, signed, after the dead zone.
    PadAxis(GamepadAxis),
    /// The left stick as a pair (only for `Action::Move`); the right stick looks, see `input`.
    LeftStick,
}

/// When an input counts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// While it is down.
    Held,
    /// Once, when it is let go before `HOLD_SECONDS`.
    Tap,
    /// Once, when it has been down `HOLD_SECONDS`.
    Hold,
}

#[derive(Clone, Copy, Debug)]
pub struct Bind {
    pub ctx: Ctx,
    pub action: Action,
    pub source: Source,
    /// Multiplies the input; -1 makes a key or axis count the other way.
    pub scale: f32,
    pub mode: Mode,
    /// For `Move` on keys: the direction (x strafe right, y forward) this key adds.
    pub dir: Vec2,
}

const fn bind(ctx: Ctx, action: Action, source: Source) -> Bind {
    Bind { ctx, action, source, scale: 1.0, mode: Mode::Held, dir: Vec2::ZERO }
}
const fn key(ctx: Ctx, action: Action, k: KeyCode) -> Bind {
    bind(ctx, action, Source::Key(k))
}
const fn pad(ctx: Ctx, action: Action, b: GamepadButton) -> Bind {
    bind(ctx, action, Source::Pad(b))
}
const fn mode(b: Bind, mode: Mode) -> Bind {
    Bind { mode, ..b }
}
const fn scaled(b: Bind, scale: f32) -> Bind {
    Bind { scale, ..b }
}
const fn moves(ctx: Ctx, k: KeyCode, x: f32, y: f32) -> Bind {
    Bind { dir: Vec2::new(x, y), ..key(ctx, Action::Move, k) }
}

use Action::*;
use Ctx::{Foot, Menu, Ship as Fly, Vehicle as Drive};
use GamepadButton as P;
use KeyCode as K;

/// Every binding. Titanfall 2 style on a pad: A jump, B or L3 crouch, X reload (hold to use),
/// Y last weapon, LT aim, RT fire, LB grapple, RB next weapon, R3 view.
pub const BINDINGS: &[Bind] = &[
    // ---- On foot
    moves(Foot, K::KeyW, 0.0, 1.0),
    moves(Foot, K::KeyA, -1.0, 0.0),
    moves(Foot, K::KeyS, 0.0, -1.0),
    moves(Foot, K::KeyD, 1.0, 0.0),
    bind(Foot, Move, Source::LeftStick),
    key(Foot, Jump, K::Space),
    pad(Foot, Jump, P::South),
    key(Foot, Crouch, K::ControlLeft),
    key(Foot, Crouch, K::ShiftLeft),
    key(Foot, Crouch, K::KeyC),
    pad(Foot, Crouch, P::East),
    pad(Foot, Crouch, P::LeftThumb),
    bind(Foot, Fire, Source::Mouse(MouseButton::Left)),
    pad(Foot, Fire, P::RightTrigger2),
    bind(Foot, Aim, Source::Mouse(MouseButton::Right)),
    pad(Foot, Aim, P::LeftTrigger2),
    key(Foot, Reload, K::KeyR),
    mode(pad(Foot, Reload, P::West), Mode::Tap),
    key(Foot, Use, K::KeyE),
    mode(pad(Foot, Use, P::West), Mode::Hold),
    key(Foot, Ability, K::KeyG),
    bind(Foot, Ability, Source::Mouse(MouseButton::Back)),
    pad(Foot, Ability, P::LeftTrigger),
    key(Foot, LastWeapon, K::KeyQ),
    pad(Foot, LastWeapon, P::North),
    bind(Foot, NextWeapon, Source::WheelDown),
    pad(Foot, NextWeapon, P::RightTrigger),
    pad(Foot, NextWeapon, P::DPadRight),
    bind(Foot, PrevWeapon, Source::WheelUp),
    pad(Foot, PrevWeapon, P::DPadLeft),
    key(Foot, Knife, K::KeyX),
    key(Foot, Slot(0), K::Digit1),
    key(Foot, Slot(1), K::Digit2),
    key(Foot, Slot(2), K::Digit3),
    key(Foot, Slot(3), K::Digit4),
    key(Foot, Slot(4), K::Digit5),
    key(Foot, Slot(5), K::Digit6),
    key(Foot, Slot(6), K::Digit7),
    key(Foot, Slot(7), K::Digit8),
    key(Foot, Slot(8), K::Digit9),
    key(Foot, Slot(9), K::Digit0),
    key(Foot, Flashlight, K::KeyF),
    pad(Foot, Flashlight, P::DPadUp),
    key(Foot, Inspect, K::KeyV),
    pad(Foot, Inspect, P::DPadDown),
    key(Foot, ToggleView, K::KeyT),
    mode(pad(Foot, ToggleView, P::RightThumb), Mode::Tap),
    mode(pad(Foot, Knife, P::RightThumb), Mode::Hold),
    key(Foot, Respawn, K::Backspace),
    pad(Foot, Respawn, P::Select),
    key(Foot, Pause, K::Escape),
    pad(Foot, Pause, P::Start),
    // ---- Driving
    moves(Drive, K::KeyW, 0.0, 1.0),
    moves(Drive, K::KeyA, -1.0, 0.0),
    moves(Drive, K::KeyS, 0.0, -1.0),
    moves(Drive, K::KeyD, 1.0, 0.0),
    bind(Drive, Move, Source::LeftStick),
    pad(Drive, Gas, P::RightTrigger2),
    pad(Drive, Brake, P::LeftTrigger2),
    key(Drive, Handbrake, K::Space),
    pad(Drive, Handbrake, P::South),
    key(Drive, Use, K::KeyE),
    mode(pad(Drive, Use, P::West), Mode::Hold),
    key(Drive, Flashlight, K::KeyF),
    pad(Drive, Flashlight, P::DPadUp),
    key(Drive, ToggleView, K::KeyT),
    pad(Drive, ToggleView, P::RightThumb),
    key(Drive, Respawn, K::Backspace),
    pad(Drive, Respawn, P::Select),
    key(Drive, Pause, K::Escape),
    pad(Drive, Pause, P::Start),
    // ---- Flying: the mouse or right stick pitches and yaws
    key(Fly, Thrust, K::KeyW),
    scaled(key(Fly, Thrust, K::KeyS), -1.0),
    pad(Fly, Thrust, P::RightTrigger2),
    scaled(pad(Fly, Thrust, P::LeftTrigger2), -1.0),
    key(Fly, Lift, K::Space),
    scaled(key(Fly, Lift, K::ControlLeft), -1.0),
    bind(Fly, Lift, Source::PadAxis(GamepadAxis::LeftStickY)),
    key(Fly, Roll, K::KeyA),
    scaled(key(Fly, Roll, K::KeyD), -1.0),
    pad(Fly, Roll, P::LeftTrigger),
    scaled(pad(Fly, Roll, P::RightTrigger), -1.0),
    key(Fly, Boost, K::ShiftLeft),
    pad(Fly, Boost, P::South),
    key(Fly, Stop, K::KeyX),
    pad(Fly, Stop, P::North),
    key(Fly, FreeLook, K::AltLeft),
    pad(Fly, FreeLook, P::East),
    key(Fly, Use, K::KeyE),
    mode(pad(Fly, Use, P::West), Mode::Hold),
    key(Fly, ToggleView, K::KeyT),
    mode(pad(Fly, ToggleView, P::RightThumb), Mode::Tap),
    key(Fly, Respawn, K::Backspace),
    pad(Fly, Respawn, P::Select),
    key(Fly, Pause, K::Escape),
    pad(Fly, Pause, P::Start),
    // ---- Menus
    key(Menu, Up, K::ArrowUp),
    key(Menu, Up, K::KeyW),
    pad(Menu, Up, P::DPadUp),
    key(Menu, Down, K::ArrowDown),
    key(Menu, Down, K::KeyS),
    pad(Menu, Down, P::DPadDown),
    key(Menu, Left, K::ArrowLeft),
    key(Menu, Left, K::KeyA),
    pad(Menu, Left, P::DPadLeft),
    key(Menu, Right, K::ArrowRight),
    key(Menu, Right, K::KeyD),
    pad(Menu, Right, P::DPadRight),
    key(Menu, Select, K::Enter),
    key(Menu, Select, K::Space),
    pad(Menu, Select, P::South),
    key(Menu, Back, K::Escape),
    pad(Menu, Back, P::East),
    pad(Menu, Back, P::Start),
    key(Menu, TabNext, K::KeyE),
    pad(Menu, TabNext, P::RightTrigger),
    key(Menu, TabPrev, K::KeyQ),
    pad(Menu, TabPrev, P::LeftTrigger),
];

/// What each action is doing this frame, for the current context.
#[derive(Resource, Default, Debug)]
pub struct ActionState {
    pub ctx: Option<Ctx>,
    value: HashMap<Action, f32>,
    before: HashMap<Action, f32>,
    /// The inputs that were down last frame, whatever they did.
    down: Vec<Source>,
    /// `Move`, after the dead zone (sticks) and normalising (keys), length <= 1.
    pub movement: Vec2,
    /// Whether the pad was the last thing touched, so prompts name its buttons.
    pub pad_last: bool,
}

impl ActionState {
    /// The action's value: 0..1 for buttons and triggers, -1..1 for axes.
    pub fn value(&self, a: Action) -> f32 {
        self.value.get(&a).copied().unwrap_or(0.0)
    }
    pub fn held(&self, a: Action) -> bool {
        self.value(a).abs() > 0.5
    }
    /// Went down this frame (a tap or hold counts the frame it fires).
    pub fn pressed(&self, a: Action) -> bool {
        self.held(a) && self.before.get(&a).is_none_or(|v| v.abs() <= 0.5)
    }
}

/// How far a trigger must be pulled for a button action.
fn radial_deadzone(v: Vec2, dz: f32) -> Vec2 {
    let len = v.length();
    if len <= dz { Vec2::ZERO } else { v / len * ((len - dz) / (1.0 - dz)).min(1.0) }
}

/// One axis of a pad stick after that stick's round dead zone.
fn stick_axis(g: &Gamepad, a: GamepadAxis, dz: f32) -> f32 {
    match a {
        GamepadAxis::LeftStickX => radial_deadzone(g.left_stick(), dz).x,
        GamepadAxis::LeftStickY => radial_deadzone(g.left_stick(), dz).y,
        GamepadAxis::RightStickX => radial_deadzone(g.right_stick(), dz).x,
        GamepadAxis::RightStickY => radial_deadzone(g.right_stick(), dz).y,
        _ => {
            let v = g.get(a).unwrap_or(0.0);
            if v.abs() <= dz { 0.0 } else { v.signum() * ((v.abs() - dz) / (1.0 - dz)).min(1.0) }
        }
    }
}

/// One frame of devices.
pub struct Devices<'a> {
    pub keys: &'a ButtonInput<KeyCode>,
    pub mouse: &'a ButtonInput<MouseButton>,
    pub scroll: &'a AccumulatedMouseScroll,
    /// Whether the cursor is locked to the window, which is when the mouse plays the game.
    pub mouse_live: bool,
    pub pads: &'a [&'a Gamepad],
    pub dead_zone: f32,
    pub dt: f32,
}

/// Held time of each tap / hold binding, by index into `BINDINGS`.
#[derive(Default)]
pub struct Timers(HashMap<usize, f32>);

/// Read the devices into `state` for `ctx`.
pub fn read(state: &mut ActionState, timers: &mut Timers, ctx: Ctx, d: &Devices) {
    state.before = std::mem::take(&mut state.value);
    let changed = state.ctx != Some(ctx);
    state.ctx = Some(ctx);
    let before_down = std::mem::take(&mut state.down);
    let mut carried: Vec<Action> = Vec::new();
    let mut movement = Vec2::ZERO;
    for (i, b) in BINDINGS.iter().enumerate().filter(|(_, b)| b.ctx == ctx) {
        // The raw value this input gives, before the mode.
        let raw = match b.source {
            Source::Key(k) => d.keys.pressed(k) as u8 as f32,
            Source::Mouse(m) if d.mouse_live => d.mouse.pressed(m) as u8 as f32,
            Source::Mouse(_) => 0.0,
            Source::WheelUp => (d.mouse_live && d.scroll.delta.y > 0.0) as u8 as f32,
            Source::WheelDown => (d.mouse_live && d.scroll.delta.y < 0.0) as u8 as f32,
            // A pressed button counts at least 0.75, so a pad that reports only the digital state works.
            Source::Pad(p) => d.pads.iter().map(|g| if g.pressed(p) { g.get(p).unwrap_or(0.0).max(0.75) } else { g.get(p).unwrap_or(0.0) }).fold(0.0, f32::max),
            // A stick axis goes through its stick's round dead zone and is rescaled past it, so
            // it starts from zero and a push straight up does not also count a little sideways.
            Source::PadAxis(a) => d.pads.iter().map(|g| stick_axis(g, a, d.dead_zone)).fold(0.0, |acc: f32, v| if v.abs() > acc.abs() { v } else { acc }),
            Source::LeftStick => {
                for g in d.pads {
                    movement += radial_deadzone(g.left_stick(), d.dead_zone);
                }
                0.0
            }
        };
        if raw.abs() > 0.5 {
            state.down.push(b.source);
            if before_down.contains(&b.source) {
                carried.push(b.action);
            }
        }
        if b.action == Move && b.dir != Vec2::ZERO {
            movement += b.dir * raw;
            continue;
        }
        let value = match b.mode {
            Mode::Held => raw,
            Mode::Tap | Mode::Hold => {
                let held = timers.0.entry(i).or_insert(0.0);
                let mut fire = 0.0;
                if raw > 0.5 {
                    if b.mode == Mode::Hold && *held < HOLD_SECONDS && *held + d.dt >= HOLD_SECONDS {
                        fire = 1.0;
                    }
                    *held += d.dt;
                } else {
                    if b.mode == Mode::Tap && *held > 0.0 && *held < HOLD_SECONDS {
                        fire = 1.0;
                    }
                    *held = 0.0;
                }
                fire
            }
        } * b.scale;
        let v = state.value.entry(b.action).or_insert(0.0);
        // The strongest input wins, so a key and a stick do not add up past 1.
        if value.abs() > v.abs() {
            *v = value;
        }
    }
    state.movement = movement.clamp_length_max(1.0);
    if d.keys.get_just_pressed().next().is_some() || d.mouse.get_just_pressed().next().is_some() {
        state.pad_last = false;
    }
    let pad_touched = d.pads.iter().any(|g| g.get_just_pressed().next().is_some() || g.left_stick().length() > 0.5 || g.right_stick().length() > 0.5);
    if pad_touched {
        state.pad_last = true;
    }
    // Entering a new context (pause, boarding): an input that was already down in the last one is
    // not a fresh press here, or Esc would pause and un-pause in the same breath.
    if changed {
        for a in carried {
            if let Some(v) = state.value.get(&a).copied() {
                state.before.insert(a, v);
            }
        }
        timers.0.clear();
    }
}

// ------------------------------------------------------------------------------------ names

fn key_name(k: KeyCode) -> String {
    let s = format!("{k:?}");
    match s.as_str() {
        "ControlLeft" => "Ctrl".into(),
        "ShiftLeft" => "Shift".into(),
        "AltLeft" => "Alt".into(),
        "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" => s.replace("Arrow", "") + " arrow",
        _ => s.strip_prefix("Key").or_else(|| s.strip_prefix("Digit")).unwrap_or(&s).to_string(),
    }
}

fn pad_name(b: GamepadButton) -> &'static str {
    match b {
        P::South => "A",
        P::East => "B",
        P::West => "X",
        P::North => "Y",
        P::LeftTrigger => "LB",
        P::RightTrigger => "RB",
        P::LeftTrigger2 => "LT",
        P::RightTrigger2 => "RT",
        P::LeftThumb => "L3",
        P::RightThumb => "R3",
        P::DPadUp => "D-pad up",
        P::DPadDown => "D-pad down",
        P::DPadLeft => "D-pad left",
        P::DPadRight => "D-pad right",
        P::Start => "Start",
        P::Select => "View",
        _ => "?",
    }
}

impl Bind {
    /// What this input is called, with " (tap)" or " (hold)" for those modes.
    pub fn name(&self) -> String {
        let base = match self.source {
            Source::Key(k) => key_name(k),
            Source::Mouse(MouseButton::Left) => "Left mouse".into(),
            Source::Mouse(MouseButton::Right) => "Right mouse".into(),
            Source::Mouse(MouseButton::Back) => "Mouse 4".into(),
            Source::Mouse(_) => "Mouse".into(),
            Source::WheelUp => "Wheel up".into(),
            Source::WheelDown => "Wheel down".into(),
            Source::Pad(p) => pad_name(p).into(),
            Source::PadAxis(GamepadAxis::LeftStickX) => "Left stick left / right".into(),
            Source::PadAxis(GamepadAxis::LeftStickY) => "Left stick up / down".into(),
            Source::PadAxis(_) => "Stick".into(),
            Source::LeftStick => "Left stick".into(),
        };
        match self.mode {
            Mode::Held => base,
            Mode::Tap => base + " (tap)",
            Mode::Hold => base + " (hold)",
        }
    }

    pub fn on_pad(&self) -> bool {
        matches!(self.source, Source::Pad(_) | Source::PadAxis(_) | Source::LeftStick)
    }
}

/// What to press for `action` in `ctx` on the pad or the keyboard, every binding joined with "/"
/// ("W/S", "RT/LT"), for on-screen prompts.
pub fn hint(ctx: Ctx, action: Action, pad: bool) -> String {
    let names: Vec<String> = BINDINGS.iter().filter(|b| b.ctx == ctx && b.action == action && b.on_pad() == pad).map(|b| b.name()).collect();
    names.join("/")
}

/// The Controls screen and README rows for a context: (action, keyboard and mouse, pad). Slots
/// are one row, "1 - 9, 0".
pub fn rows(ctx: Ctx) -> Vec<(&'static str, String, String)> {
    let mut out: Vec<(&'static str, String, String)> = Vec::new();
    for b in BINDINGS.iter().filter(|b| b.ctx == ctx) {
        let label = b.action.label();
        let at = match out.iter().position(|(l, ..)| *l == label) {
            Some(at) => at,
            None => {
                out.push((label, String::new(), String::new()));
                out.len() - 1
            }
        };
        let name = if matches!(b.action, Slot(_)) {
            if matches!(b.action, Slot(0)) { "1 - 9, 0".to_string() } else { continue }
        } else {
            b.name()
        };
        let cell = if b.on_pad() { &mut out[at].2 } else { &mut out[at].1 };
        if !cell.is_empty() {
            cell.push_str(", ");
        }
        cell.push_str(&name);
    }
    out
}

/// The README's controls table, one section per context, from `BINDINGS`.
pub fn markdown() -> String {
    let mut out = String::new();
    for ctx in Ctx::GAME {
        out.push_str(&format!("**{}**\n\n| Action | Keyboard / mouse | Gamepad |\n|---|---|---|\n", ctx.label()));
        for (action, keys, pad) in rows(ctx) {
            out.push_str(&format!("| {action} | {keys} | {pad} |\n"));
        }
        out.push('\n');
    }
    out.push_str("**Menus** follow the same buttons: arrows or WASD (d-pad) move, Enter or Space (A) select, Esc (B or Start) backs out, Q / E (LB / RB) change weapon at the quartermaster.\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Two actions on one button in one context is a double mapping, the bug a pad hits as "B
    /// slides and pauses". The same button may be a tap for one action and a hold for another.
    #[test]
    fn no_button_does_two_things_in_one_context() {
        for ctx in [Foot, Drive, Fly, Menu] {
            let bound: Vec<&Bind> = BINDINGS.iter().filter(|b| b.ctx == ctx).collect();
            for (i, a) in bound.iter().enumerate() {
                for b in &bound[i + 1..] {
                    if a.source == b.source && a.action != b.action {
                        assert!(a.mode != b.mode, "{ctx:?}: {} and {} share {}", a.action.label(), b.action.label(), a.name());
                    }
                }
            }
        }
    }

    #[test]
    fn every_game_context_can_pause_use_and_respawn() {
        for ctx in Ctx::GAME {
            for action in [Pause, Respawn, Use] {
                assert!(BINDINGS.iter().any(|b| b.ctx == ctx && b.action == action && !b.on_pad()), "{ctx:?} has no key for {}", action.label());
                assert!(BINDINGS.iter().any(|b| b.ctx == ctx && b.action == action && b.on_pad()), "{ctx:?} has no pad button for {}", action.label());
            }
        }
    }

    #[test]
    fn a_pad_can_do_everything_a_keyboard_can_on_foot() {
        for b in BINDINGS.iter().filter(|b| b.ctx == Foot && !b.on_pad()) {
            if matches!(b.action, Slot(_) | Move) {
                continue; // slots are cycled with the d-pad, and the stick moves
            }
            assert!(BINDINGS.iter().any(|p| p.ctx == Foot && p.action == b.action && p.on_pad()), "{} has no pad button", b.action.label());
        }
    }

    /// The README table is written from `BINDINGS`. `UPDATE_README=1 cargo test readme` rewrites it.
    #[test]
    fn readme_table_matches_the_bindings() {
        const START: &str = "<!-- controls:start -->\n";
        const END: &str = "<!-- controls:end -->";
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/README.md");
        let readme = std::fs::read_to_string(path).unwrap();
        let (a, b) = (readme.find(START).expect("controls:start marker") + START.len(), readme.find(END).expect("controls:end marker"));
        let table = markdown();
        if std::env::var_os("UPDATE_README").is_some() {
            std::fs::write(path, format!("{}{}{}", &readme[..a], table, &readme[b..])).unwrap();
        } else {
            assert_eq!(&readme[a..b], table, "README controls are out of date: UPDATE_README=1 cargo test readme");
        }
    }

    #[test]
    fn prompts_name_the_keys_or_the_pad() {
        assert_eq!(hint(Fly, Thrust, false), "W/S");
        assert_eq!(hint(Fly, Thrust, true), "RT/LT");
        assert_eq!(hint(Fly, Roll, true), "LB/RB");
        assert_eq!(hint(Fly, FreeLook, false), "Alt");
    }

    #[test]
    fn rows_name_what_is_bound() {
        let foot = rows(Foot);
        let reload = foot.iter().find(|(l, ..)| *l == "Reload").unwrap();
        assert_eq!(reload.1, "R");
        assert_eq!(reload.2, "X (tap)");
        let slots = foot.iter().find(|(l, ..)| *l == "Weapon 1-10").unwrap();
        assert_eq!(slots.1, "1 - 9, 0");
    }

    #[test]
    fn a_tap_fires_on_release_and_a_hold_fires_once() {
        let keys = ButtonInput::<KeyCode>::default();
        let mouse = ButtonInput::<MouseButton>::default();
        let scroll = AccumulatedMouseScroll::default();
        let mut pad = Gamepad::default();
        let mut state = ActionState::default();
        let mut timers = Timers::default();
        let frame = |pad: &Gamepad, state: &mut ActionState, timers: &mut Timers| {
            let pads = [pad];
            read(state, timers, Foot, &Devices { keys: &keys, mouse: &mouse, scroll: &scroll, mouse_live: false, pads: &pads, dead_zone: 0.15, dt: 1.0 / 60.0 });
        };
        frame(&pad, &mut state, &mut timers); // the first frame in a context is not a press
        // A short press and release: the tap fires on release, the hold does not.
        pad.digital_mut().press(GamepadButton::West);
        for _ in 0..5 {
            frame(&pad, &mut state, &mut timers);
            assert!(!state.held(Reload) && !state.held(Use), "nothing fires while it is down");
        }
        pad.digital_mut().release(GamepadButton::West);
        frame(&pad, &mut state, &mut timers);
        assert!(state.pressed(Reload), "released after a short press: a tap");
        assert!(!state.held(Use));
        // Held past the threshold: the hold fires once, and releasing it is not a tap.
        pad.digital_mut().press(GamepadButton::West);
        let mut used = 0;
        for _ in 0..60 {
            frame(&pad, &mut state, &mut timers);
            used += state.pressed(Use) as u32;
            assert!(!state.held(Reload));
        }
        pad.digital_mut().release(GamepadButton::West);
        frame(&pad, &mut state, &mut timers);
        assert_eq!(used, 1, "use fires once while held");
        assert!(!state.held(Reload), "a long hold is not a tap");
    }

    /// A frame of `pad` in `ctx` through the real reader.
    fn read_pad(ctx: Ctx, pad: &Gamepad, state: &mut ActionState) {
        let keys = ButtonInput::<KeyCode>::default();
        let mouse = ButtonInput::<MouseButton>::default();
        let scroll = AccumulatedMouseScroll::default();
        let pads = [pad];
        let mut timers = Timers::default();
        read(state, &mut timers, ctx, &Devices { keys: &keys, mouse: &mouse, scroll: &scroll, mouse_live: false, pads: &pads, dead_zone: 0.15, dt: 1.0 / 60.0 });
    }

    #[test]
    fn the_pad_flies_and_drives_with_the_triggers_and_left_stick() {
        let mut pad = Gamepad::default();
        pad.analog_mut().set(GamepadButton::RightTrigger2, 0.6);
        pad.analog_mut().set(GamepadAxis::LeftStickX, 0.8);
        pad.analog_mut().set(GamepadAxis::LeftStickY, -0.5);
        pad.analog_mut().set(GamepadButton::RightTrigger, 1.0);
        let mut state = ActionState::default();
        read_pad(Fly, &pad, &mut state);
        assert!((state.value(Thrust) - 0.6).abs() < 1e-4, "RT thrusts: {}", state.value(Thrust));
        assert!(state.value(Roll) < -0.5, "RB rolls right: {}", state.value(Roll));
        assert!(state.value(Lift) < -0.2, "stick down sinks: {}", state.value(Lift));
        // Sideways on the stick no longer rolls: with RB let go, roll stays still.
        pad.analog_mut().set(GamepadButton::RightTrigger, 0.0);
        let mut state = ActionState::default();
        read_pad(Fly, &pad, &mut state);
        assert_eq!(state.value(Roll), 0.0, "the stick does not roll");
        let mut state = ActionState::default();
        read_pad(Drive, &pad, &mut state);
        assert!((state.value(Gas) - 0.6).abs() < 1e-4, "RT is gas: {}", state.value(Gas));
        assert!(state.movement.x > 0.5, "the stick steers: {}", state.movement);
    }

    #[test]
    fn an_input_held_across_a_context_change_is_not_a_new_press() {
        let mut keys = ButtonInput::<KeyCode>::default();
        let mouse = ButtonInput::<MouseButton>::default();
        let scroll = AccumulatedMouseScroll::default();
        let mut state = ActionState::default();
        let mut timers = Timers::default();
        let mut frame = |ctx: Ctx, keys: &ButtonInput<KeyCode>, state: &mut ActionState| {
            read(state, &mut timers, ctx, &Devices { keys, mouse: &mouse, scroll: &scroll, mouse_live: false, pads: &[], dead_zone: 0.15, dt: 1.0 / 60.0 });
        };
        frame(Foot, &keys, &mut state);
        keys.press(KeyCode::Escape);
        frame(Foot, &keys, &mut state);
        assert!(state.pressed(Pause), "Esc pauses");
        // The menu comes up with Esc still down: it must not read as Back.
        frame(Menu, &keys, &mut state);
        assert!(!state.pressed(Back), "Esc was already down");
        keys.release(KeyCode::Escape);
        frame(Menu, &keys, &mut state);
        keys.press(KeyCode::Escape);
        frame(Menu, &keys, &mut state);
        assert!(state.pressed(Back), "a fresh press backs out");
    }
}
