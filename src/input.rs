use bevy::ecs::system::SystemParam;
use bevy::input::gamepad::{GamepadRumbleIntensity, GamepadRumbleRequest};
use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::prelude::*;
use bevy::window::{CursorGrabMode, CursorOptions};
use std::time::Duration;

use crate::controls::{Action, ActionState, Ctx, Devices, Timers};
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
    /// Flip first / third person (T / R3), latched.
    pub view_pressed: bool,
    /// Camera to the other shoulder in third person (Z), latched.
    pub shoulder_pressed: bool,
    /// The ship's stick, -1..1 each, while flying: thrust, lift, roll left.
    pub thrust: f32,
    pub lift: f32,
    pub roll: f32,
    pub boost: bool,
    /// The pad's flight stick, -1..1: pitch up (x, left stick) and yaw left (y, bumpers). It does
    /// not pass through the view, so it is a true stick rather than a mouse imitation.
    pub ship_stick: Vec2,
    /// Held: kill the ship's speed (X / Y).
    pub stop: bool,
    /// Held: look around instead of steering (Alt / B).
    pub free_look: bool,
    /// How far the pad's right stick turned the view this frame (yaw, pitch; radians, view-space sign as applied), for aim assist. Zero without a pad.
    pub pad_look: Vec2,
}

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
            .init_resource::<ActionState>()
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

/// The mouse and its cursor.
#[derive(SystemParam)]
pub(crate) struct Pointer<'w, 's> {
    buttons: Res<'w, ButtonInput<MouseButton>>,
    motion: Res<'w, AccumulatedMouseMotion>,
    scroll: Res<'w, AccumulatedMouseScroll>,
    cursors: Query<'w, 's, &'static CursorOptions>,
}

/// Where the player is: in a menu, flying the ship, driving, or on foot.
fn context(screen: Option<&State<crate::menu::Screen>>, driving: &Query<&crate::vehicle::Driving, With<crate::controller::Player>>, ships: &Query<(), With<crate::solar::ship::Ship>>) -> Ctx {
    if screen.is_some_and(|s| *s.get() != crate::menu::Screen::Playing) {
        return Ctx::Menu;
    }
    match driving.single() {
        Ok(d) if ships.contains(d.0) => Ctx::Ship,
        Ok(_) => Ctx::Foot,
        Err(_) => Ctx::Foot,
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn gather(
    keys: Res<ButtonInput<KeyCode>>,
    pointer: Pointer,
    gamepads: Query<&Gamepad>,
    tuning: Res<Tuning>,
    time: Res<Time>,
    mut input: ResMut<PlayerInput>,
    mut view: ResMut<ViewAngles>,
    mut state: ResMut<ActionState>,
    mut timers: Local<Timers>,
    aim: Option<Res<crate::weapon::Aim>>,
    scoped: Option<Res<crate::scope::Scoped>>,
    screen: Option<Res<State<crate::menu::Screen>>>,
    driving: Query<&crate::vehicle::Driving, With<crate::controller::Player>>,
    ships: Query<(), With<crate::solar::ship::Ship>>,
) {
    let t = &*tuning;
    let dt = time.delta_secs();
    let mouse_live = pointer.cursors.iter().any(|c| c.grab_mode != CursorGrabMode::None);
    let pads: Vec<&Gamepad> = gamepads.iter().collect();

    let ctx = context(screen.as_deref(), &driving, &ships);
    crate::controls::read(&mut state, &mut timers, ctx, &Devices { keys: &keys, mouse: &pointer.buttons, scroll: &pointer.scroll, mouse_live, pads: &pads, dead_zone: t.stick_deadzone, dt });

    // A menu is up: nothing reaches the player, and a held key is not a latched press later.
    if ctx == Ctx::Menu {
        *input = PlayerInput::default();
        return;
    }
    let held = |a: Action| state.held(a);
    let pressed = |a: Action| state.pressed(a);

    // Looking: the mouse while the cursor is locked, and the right stick (every pad drives the
    // same player).
    // Looking: the mouse while the cursor is locked, and the right stick unless it is flying.
    let invert = if t.invert_y { -1.0 } else { 1.0 };
    let steering = ctx == Ctx::Ship && !held(Action::FreeLook);
    let mut look = Vec2::ZERO;
    let mut pad_look = Vec2::ZERO;
    if mouse_live {
        look += pointer.motion.delta * t.mouse_sensitivity * Vec2::new(1.0, invert);
    }
    for pad in &pads {
        // Flying, the right stick lifts (through the bindings) unless the pilot is looking round.
        if steering {
            continue;
        }
        let r = radial_deadzone(pad.right_stick(), t.stick_deadzone);
        // Response curve: fine aim near center, fast turns at full tilt.
        let curved = r.normalize_or_zero() * r.length().powf(t.stick_look_curve);
        look.x += curved.x * t.stick_yaw_speed * dt;
        look.y -= curved.y * t.stick_pitch_speed * dt * invert;
        pad_look += Vec2::new(curved.x * t.stick_yaw_speed * dt, -curved.y * t.stick_pitch_speed * dt * invert);
    }
    // Aiming down sights narrows the view (or a scope magnifies it), so the mouse turns it less.
    if let Some(aim) = aim.as_ref() {
        let scale = crate::scope::look_scale(aim.level, t.ads_fov, scoped.as_ref().and_then(|s| s.0));
        look *= scale;
        pad_look *= scale;
    }
    input.pad_look = pad_look;
    view.yaw -= look.x;
    view.pitch = (view.pitch - look.y).clamp(-1.54, 1.54);

    input.movement = state.movement;
    input.jump_held = held(Action::Jump);
    input.jump_pressed |= pressed(Action::Jump);
    input.crouch_held = held(Action::Crouch);
    input.fire_held = held(Action::Fire);
    // Flying, right mouse is the missile trigger, read from the same field (`solar::ship`).
    input.aim_held = held(Action::Aim) || held(Action::Missile);
    input.fire_pressed |= pressed(Action::Fire);
    input.reset_pressed |= pressed(Action::Respawn);
    input.reload_pressed |= pressed(Action::Reload);
    input.inspect_pressed |= pressed(Action::Inspect);
    if let Some(slot) = (0..10u8).find(|i| pressed(Action::Slot(*i))) {
        input.weapon_select = Some(slot as usize);
    }
    if pressed(Action::Knife) {
        input.weapon_select = Some(crate::weapon::KNIFE);
    }
    input.weapon_step += pressed(Action::NextWeapon) as i32 - pressed(Action::PrevWeapon) as i32;
    input.weapon_last |= pressed(Action::LastWeapon);
    input.interact_pressed |= pressed(Action::Use);
    input.ability_pressed |= pressed(Action::Ability);
    input.view_pressed |= pressed(Action::ToggleView);
    input.shoulder_pressed |= pressed(Action::SwapShoulder);
    input.thrust = state.value(Action::Thrust);
    input.lift = state.value(Action::Lift);
    // The left stick is a flight joystick (pitch and roll) with the look curve, so small
    // corrections are fine and full tilt is full rate; Invert Y flips the pitch.
    let joystick = Vec2::new(state.value(Action::Pitch) * invert, state.value(Action::Roll));
    let joystick = joystick.normalize_or_zero() * joystick.length().min(1.0).powf(t.stick_look_curve) * t.flight_stick;
    input.ship_stick = Vec2::new(joystick.x, state.value(Action::Yaw) * t.flight_stick).clamp(Vec2::NEG_ONE, Vec2::ONE);
    input.roll = joystick.y.clamp(-1.0, 1.0);
    input.boost = held(Action::Boost);
    input.stop = held(Action::Stop);
    input.free_look = held(Action::FreeLook);
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
