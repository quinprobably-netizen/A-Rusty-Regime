use bevy::input::gamepad::{GamepadRumbleIntensity, GamepadRumbleRequest};
use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::prelude::*;
use bevy::window::{CursorGrabMode, CursorOptions};
use std::time::Duration;

use crate::tuning::Tuning;

/// Device-agnostic input, written every frame and read by the fixed-tick
/// controller. `*_pressed` flags latch until a tick consumes them, so a tap
/// between two physics ticks is never lost.
#[derive(Resource, Default, Debug)]
pub struct PlayerInput {
    /// x = strafe right, y = forward. Analog, length <= 1.
    pub movement: Vec2,
    pub jump_held: bool,
    pub jump_pressed: bool,
    pub crouch_held: bool,
    pub fire_held: bool,
    /// Aim down sights (right mouse / left trigger).
    pub aim_held: bool,
    /// Latched like `jump_pressed`; semi-auto guns fire once per press.
    pub fire_pressed: bool,
    pub reset_pressed: bool,
    /// Reload (R / R3), latched.
    pub reload_pressed: bool,
    /// Turn the weapon over to look at it (V), latched.
    pub inspect_pressed: bool,
    /// Weapon slot (0-based) picked with the number keys this frame.
    pub weapon_select: Option<usize>,
    /// +1 / -1 steps from the mouse wheel, bumpers or d-pad, accumulated until a tick reads them.
    pub weapon_step: i32,
    /// Swap to the previous weapon (Q / Y).
    pub weapon_last: bool,
    /// Enter or leave a vehicle (E / X), latched like `jump_pressed`.
    pub interact_pressed: bool,
    /// Use the class ability (G / mouse 4 / L3), latched like `jump_pressed`.
    pub ability_pressed: bool,
    /// Toggle the flashlight (F), latched.
    pub flashlight_pressed: bool,
}

/// Where the player is looking, in radians.
#[derive(Resource, Default, Debug, Clone, Copy)]
pub struct ViewAngles {
    pub yaw: f32,
    pub pitch: f32,
}

impl ViewAngles {
    pub fn rotation(&self) -> Quat {
        Quat::from_euler(EulerRot::YXZ, self.yaw, self.pitch, 0.0)
    }
    /// Horizontal forward and right vectors.
    pub fn flat_basis(&self) -> (Vec3, Vec3) {
        let (s, c) = self.yaw.sin_cos();
        (Vec3::new(-s, 0.0, -c), Vec3::new(c, 0.0, -s))
    }
}

/// Ask for a rumble on every connected gamepad.
#[derive(Message)]
pub struct Rumble {
    pub strength: f32,
    pub seconds: f32,
}

pub struct InputPlugin;

impl Plugin for InputPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PlayerInput>()
            .init_resource::<ViewAngles>()
            .add_message::<Rumble>()
            .add_systems(PreUpdate, gather.after(bevy::input::InputSystems))
            .add_systems(Update, (grab_cursor, rumble));
    }
}

fn radial_deadzone(v: Vec2, dz: f32) -> Vec2 {
    let len = v.length();
    if len <= dz {
        Vec2::ZERO
    } else {
        v / len * ((len - dz) / (1.0 - dz)).min(1.0)
    }
}

fn gather(
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    cursor: Single<&CursorOptions>,
    gamepads: Query<&Gamepad>,
    tuning: Res<Tuning>,
    time: Res<Time>,
    mut input: ResMut<PlayerInput>,
    mut view: ResMut<ViewAngles>,
    aim: Option<Res<crate::weapon::Aim>>,
    screen: Option<Res<State<crate::menu::Screen>>>,
) {
    // A menu is up: nothing reaches the player, and a held key is not a latched press later.
    if screen.is_some_and(|s| *s.get() != crate::menu::Screen::Playing) {
        *input = PlayerInput::default();
        return;
    }
    let t = &*tuning;
    let dt = time.delta_secs();

    // Keyboard + mouse
    let mut movement = Vec2::ZERO;
    if keys.pressed(KeyCode::KeyW) { movement.y += 1.0; }
    if keys.pressed(KeyCode::KeyS) { movement.y -= 1.0; }
    if keys.pressed(KeyCode::KeyD) { movement.x += 1.0; }
    if keys.pressed(KeyCode::KeyA) { movement.x -= 1.0; }
    let mut jump_held = keys.pressed(KeyCode::Space);
    let mut jump_pressed = keys.just_pressed(KeyCode::Space);
    let mut crouch_held = keys.any_pressed([KeyCode::ControlLeft, KeyCode::ShiftLeft, KeyCode::KeyC]);
    let mut fire_held = false;
    let mut aim_held = false;
    let mut fire_pressed = false;
    let mut reset = keys.just_pressed(KeyCode::Backspace);
    let mut reload = keys.just_pressed(KeyCode::KeyR);
    let mut weapon_select = None;
    let digits = [
        KeyCode::Digit1,
        KeyCode::Digit2,
        KeyCode::Digit3,
        KeyCode::Digit4,
        KeyCode::Digit5,
        KeyCode::Digit6,
        KeyCode::Digit7,
        KeyCode::Digit8,
        KeyCode::Digit9,
        KeyCode::Digit0,
    ];
    for (i, key) in digits.into_iter().enumerate() {
        if keys.just_pressed(key) {
            weapon_select = Some(i);
        }
    }
    let mut weapon_step = 0;
    let mut weapon_last = keys.just_pressed(KeyCode::KeyQ);
    let mut interact = keys.just_pressed(KeyCode::KeyE);
    let mut ability = keys.just_pressed(KeyCode::KeyG) || mouse.just_pressed(MouseButton::Back);

    let mut look = Vec2::ZERO;
    if cursor.grab_mode != CursorGrabMode::None {
        look += motion.delta * t.mouse_sensitivity;
        fire_held |= mouse.pressed(MouseButton::Left);
        aim_held |= mouse.pressed(MouseButton::Right);
        fire_pressed |= mouse.just_pressed(MouseButton::Left);
        // Wheel up = previous weapon, wheel down = next (Source convention).
        if scroll.delta.y > 0.0 {
            weapon_step -= 1;
        } else if scroll.delta.y < 0.0 {
            weapon_step += 1;
        }
    }

    // Gamepads: every connected pad drives the same player.
    for pad in &gamepads {
        let stick = radial_deadzone(pad.left_stick(), t.stick_deadzone);
        movement += stick;

        let r = radial_deadzone(pad.right_stick(), t.stick_deadzone);
        // Response curve: fine aim near center, fast turns at full tilt.
        let curved = r.normalize_or_zero() * r.length().powf(t.stick_look_curve);
        let invert = if t.invert_y { -1.0 } else { 1.0 };
        look.x += curved.x * t.stick_yaw_speed * dt;
        look.y -= curved.y * t.stick_pitch_speed * dt * invert;

        jump_held |= pad.pressed(GamepadButton::South);
        jump_pressed |= pad.just_pressed(GamepadButton::South);
        crouch_held |= pad.any_pressed([
            GamepadButton::East,
            GamepadButton::LeftThumb,
            GamepadButton::LeftTrigger2,
        ]);
        fire_held |= pad.pressed(GamepadButton::RightTrigger2);
        aim_held |= pad.pressed(GamepadButton::LeftTrigger);
        fire_pressed |= pad.just_pressed(GamepadButton::RightTrigger2);
        // RB = next weapon, LB = previous, Y = last weapon, d-pad = pick a slot.
        if pad.just_pressed(GamepadButton::RightTrigger) {
            weapon_step += 1;
        }
        if pad.just_pressed(GamepadButton::LeftTrigger) {
            weapon_step -= 1;
        }
        weapon_last |= pad.just_pressed(GamepadButton::North);
        interact |= pad.just_pressed(GamepadButton::West);
        ability |= pad.just_pressed(GamepadButton::LeftThumb);
        for (i, button) in [GamepadButton::DPadUp, GamepadButton::DPadRight, GamepadButton::DPadDown, GamepadButton::DPadLeft].into_iter().enumerate() {
            if pad.just_pressed(button) {
                weapon_select = Some(i);
            }
        }
        reset |= pad.just_pressed(GamepadButton::Select);
        reload |= pad.just_pressed(GamepadButton::RightThumb);
    }

    // Aiming down sights narrows the view, so the mouse turns it less.
    if let Some(aim) = aim.as_ref() {
        look *= 1.0 - aim.level * (1.0 - t.ads_fov);
    }
    view.yaw -= look.x;
    view.pitch = (view.pitch - look.y).clamp(-1.54, 1.54);

    input.movement = movement.clamp_length_max(1.0);
    input.jump_held = jump_held;
    input.jump_pressed |= jump_pressed;
    input.crouch_held = crouch_held;
    input.fire_held = fire_held;
    input.aim_held = aim_held;
    input.fire_pressed |= fire_pressed;
    input.reset_pressed |= reset;
    input.reload_pressed |= reload;
    input.inspect_pressed |= keys.just_pressed(KeyCode::KeyV);
    if weapon_select.is_some() {
        input.weapon_select = weapon_select;
    }
    input.weapon_step += weapon_step;
    input.weapon_last |= weapon_last;
    input.interact_pressed |= interact;
    input.ability_pressed |= ability;
    input.flashlight_pressed |= keys.just_pressed(KeyCode::KeyF);
}

fn grab_cursor(
    mut cursor: Single<&mut CursorOptions>,
    mouse: Res<ButtonInput<MouseButton>>,
    screen: Option<Res<State<crate::menu::Screen>>>,
) {
    // Esc is the menu's (see `menu`), which releases the cursor itself.
    let playing = screen.is_none_or(|s| *s.get() == crate::menu::Screen::Playing);
    if playing && mouse.just_pressed(MouseButton::Left) {
        cursor.grab_mode = CursorGrabMode::Locked;
        cursor.visible = false;
    }
}

fn rumble(
    mut requests: MessageReader<Rumble>,
    mut out: MessageWriter<GamepadRumbleRequest>,
    gamepads: Query<Entity, With<Gamepad>>,
    tuning: Res<Tuning>,
) {
    for r in requests.read() {
        if !tuning.rumble {
            continue;
        }
        let s = r.strength.clamp(0.0, 1.0);
        for gamepad in &gamepads {
            out.write(GamepadRumbleRequest::Add {
                gamepad,
                duration: Duration::from_secs_f32(r.seconds),
                intensity: GamepadRumbleIntensity { strong_motor: s, weak_motor: s },
            });
        }
    }
}
