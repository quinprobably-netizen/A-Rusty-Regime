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
    /// Aim down sights (right mouse / LT).
    pub aim_held: bool,
    /// Latched like `jump_pressed`; semi-auto guns fire once per press.
    pub fire_pressed: bool,
    pub reset_pressed: bool,
    /// Reload (R / tap X), latched.
    pub reload_pressed: bool,
    /// Turn the weapon over to look at it (V / d-pad down), latched.
    pub inspect_pressed: bool,
    /// Weapon slot (0-based) picked with the number keys this frame.
    pub weapon_select: Option<usize>,
    /// +1 / -1 steps from the mouse wheel, RB or d-pad left / right, accumulated until a tick reads them.
    pub weapon_step: i32,
    /// Swap to the previous weapon (Q / Y).
    pub weapon_last: bool,
    /// Enter or leave a vehicle (E / hold X), latched like `jump_pressed`.
    pub interact_pressed: bool,
    /// Use the class ability (G / mouse 4 / LB), latched like `jump_pressed`.
    pub ability_pressed: bool,
    /// Toggle the flashlight (F / d-pad up), latched.
    pub flashlight_pressed: bool,
    /// Analog gas minus brake from the triggers (RT - LT), -1..1; only vehicles read it.
    pub throttle: f32,
}

/// How long X must be held to use (enter or leave a vehicle) instead of reloading.
pub const HOLD_TO_USE: f32 = 0.3;

/// SDL mappings newer than the table gilrs ships: the 8BitDo Ultimate 2 over Bluetooth, USB
/// and the 2.4G dongle (from SDL_GameControllerDB, zlib licence, see CREDITS.md). Without
/// them the pad falls back to raw button codes and X / Y swap and the triggers go digital.
const PAD_MAPPINGS: &str = "\
05000000c82d00001260000001000000,8BitDo Ultimate 2,a:b0,b:b1,back:b10,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b12,leftshoulder:b6,leftstick:b13,lefttrigger:a5,leftx:a0,lefty:a1,paddle1:b17,paddle2:b16,paddle3:b2,paddle4:b5,rightshoulder:b7,rightstick:b14,righttrigger:a4,rightx:a2,righty:a3,start:b11,x:b3,y:b4,platform:Linux,
03000000c82d00001260000011010000,8BitDo Ultimate 2,a:b0,b:b1,back:b10,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b12,leftshoulder:b6,leftstick:b13,lefttrigger:a5,leftx:a0,lefty:a1,paddle1:b17,paddle2:b16,paddle3:b2,paddle4:b5,rightshoulder:b7,rightstick:b14,righttrigger:a4,rightx:a2,righty:a3,start:b11,x:b3,y:b4,platform:Linux,
03000000c82d00000b31000014010000,8BitDo Ultimate 2,a:b0,b:b1,back:b6,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b8,leftshoulder:b4,leftstick:b9,lefttrigger:a2,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b10,righttrigger:a5,rightx:a3,righty:a4,start:b7,x:b2,y:b3,platform:Linux,
03000000c82d00001260000000000000,8BitDo Ultimate 2,a:b0,b:b1,back:b10,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b12,leftshoulder:b6,leftstick:b13,lefttrigger:b8,leftx:a0,lefty:a1,paddle1:b17,paddle2:b16,paddle3:b2,paddle4:b5,rightshoulder:b7,rightstick:b14,righttrigger:b9,rightx:a3,righty:a4,start:b11,x:b3,y:b4,platform:Windows,
";

/// Hands `PAD_MAPPINGS` to gilrs through `SDL_GAMECONTROLLERCONFIG`, keeping anything the
/// user put there. Call before the app is built, from the main thread.
pub fn install_pad_mappings() {
    let mut all = std::env::var("SDL_GAMECONTROLLERCONFIG").unwrap_or_default();
    if !all.is_empty() && !all.ends_with('\n') {
        all.push('\n');
    }
    all.push_str(PAD_MAPPINGS);
    // SAFETY: called from `main` before any other thread exists.
    unsafe { std::env::set_var("SDL_GAMECONTROLLERCONFIG", all) };
}

/// Where the player is looking, in radians, relative to the player's local frame.
#[derive(Resource, Default, Debug, Clone, Copy)]
pub struct ViewAngles {
    pub yaw: f32,
    pub pitch: f32,
    /// The player's carried frame (local +Y is up), published by the controller each tick.
    pub frame: Quat,
}

impl ViewAngles {
    pub fn rotation(&self) -> Quat {
        self.frame * Quat::from_euler(EulerRot::YXZ, self.yaw, self.pitch, 0.0)
    }
    /// Horizontal forward and right vectors, in the world.
    pub fn flat_basis(&self) -> (Vec3, Vec3) {
        let (forward, right) = self.local_basis();
        (self.frame * forward, self.frame * right)
    }
    /// Horizontal forward and right vectors in the player's frame.
    pub fn local_basis(&self) -> (Vec3, Vec3) {
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
        // `RUST_REGIME_PAD_DEBUG=1` logs each pad as it connects and every button it presses, to
        // see what Linux makes of a controller (8BitDo pads in D-input mode come out scrambled).
        if std::env::var_os("RUST_REGIME_PAD_DEBUG").is_some() {
            app.add_systems(Update, pad_debug);
        }
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
    scoped: Option<Res<crate::scope::Scoped>>,
    screen: Option<Res<State<crate::menu::Screen>>>,
    mut x_held: Local<f32>,
) {
    // A menu is up: nothing reaches the player, and a held key is not a latched press later.
    if screen.is_some_and(|s| *s.get() != crate::menu::Screen::Playing) {
        *input = PlayerInput::default();
        *x_held = 0.0;
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
    let mut throttle = 0.0;
    let mut inspect = keys.just_pressed(KeyCode::KeyV);
    let mut flashlight = keys.just_pressed(KeyCode::KeyF);
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

        // Titanfall 2 style: A jump, B / L3 crouch and slide, X reload (hold to use), Y swap,
        // LT aim, RT fire, LB grapple, RB next weapon. R3 is the view toggle (see camera).
        jump_held |= pad.pressed(GamepadButton::South);
        jump_pressed |= pad.just_pressed(GamepadButton::South);
        crouch_held |= pad.any_pressed([GamepadButton::East, GamepadButton::LeftThumb]);
        fire_held |= pad.pressed(GamepadButton::RightTrigger2);
        aim_held |= pad.pressed(GamepadButton::LeftTrigger2);
        fire_pressed |= pad.just_pressed(GamepadButton::RightTrigger2);
        throttle += pad.get(GamepadButton::RightTrigger2).unwrap_or(0.0) - pad.get(GamepadButton::LeftTrigger2).unwrap_or(0.0);
        ability |= pad.just_pressed(GamepadButton::LeftTrigger);
        if pad.any_just_pressed([GamepadButton::RightTrigger, GamepadButton::DPadRight]) {
            weapon_step += 1;
        }
        if pad.just_pressed(GamepadButton::DPadLeft) {
            weapon_step -= 1;
        }
        weapon_last |= pad.just_pressed(GamepadButton::North);
        flashlight |= pad.just_pressed(GamepadButton::DPadUp);
        inspect |= pad.just_pressed(GamepadButton::DPadDown);
        reset |= pad.just_pressed(GamepadButton::Select);
    }

    // X: a tap reloads on release, a hold uses once it has been down long enough.
    if gamepads.iter().any(|p| p.pressed(GamepadButton::West)) {
        interact |= *x_held < HOLD_TO_USE && *x_held + dt >= HOLD_TO_USE;
        *x_held += dt;
    } else {
        reload |= *x_held > 0.0 && *x_held < HOLD_TO_USE;
        *x_held = 0.0;
    }

    // Aiming down sights narrows the view (or a scope magnifies it), so the mouse turns it less.
    if let Some(aim) = aim.as_ref() {
        look *= crate::scope::look_scale(aim.level, t.ads_fov, scoped.as_ref().and_then(|s| s.0));
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
    input.inspect_pressed |= inspect;
    if weapon_select.is_some() {
        input.weapon_select = weapon_select;
    }
    input.weapon_step += weapon_step;
    input.weapon_last |= weapon_last;
    input.interact_pressed |= interact;
    input.ability_pressed |= ability;
    input.flashlight_pressed |= flashlight;
    input.throttle = throttle.clamp(-1.0, 1.0);
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

fn pad_debug(pads: Query<(Entity, &Gamepad, Option<&Name>)>, new: Query<Entity, Added<Gamepad>>) {
    for e in &new {
        let (_, pad, name) = pads.get(e).unwrap();
        info!("pad {e}: {:?} vendor {:04x?} product {:04x?}", name.map(|n| n.as_str()), pad.vendor_id(), pad.product_id());
    }
    for (e, pad, _) in &pads {
        for b in pad.get_just_pressed() {
            info!("pad {e}: {b:?} down");
        }
        for b in pad.get_just_released() {
            info!("pad {e}: {b:?} up");
        }
    }
}
