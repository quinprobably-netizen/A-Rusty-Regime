//! What a fight pays and costs (sections 9 and 10 of
//! `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`), read from `combat`'s
//! `ShipDestroyed` messages.
//!
//! **Bounty:** an enemy ship shot down by the ship the player flies pays its `[ship_combat]
//! bounty` into the bank, counts in `Save::kills` and its faction's tally, and puts a
//! `+$120 BOUNTY` line over the HUD for a few seconds. A kill by anyone else pays nothing.
//!
//! **The loss rule:** when the ship the player flies is shot down, it blows apart and the camera
//! hangs where it was for `downed` seconds while a SHOT DOWN card says what it cost: the courier
//! parcel and a quarter of the bank (rounded down; nothing at all when both are empty). Then the
//! wreck is gone and the player is back on the Roost's apron at Haven, from anywhere in the
//! system, on the cabin floor of a fresh Kestrel on the pad (and a fresh copy of the ship lost, on
//! its own berth, if it was another of the apron's). Guns, parts and the Yard's engine tune are in
//! the save and are not touched.

use avian3d::prelude::*;
use bevy::prelude::*;

use super::base::Bases;
use super::combat::{wreck, Faction, Hull, ShipDestroyed};
use super::ship::{berth, spawn, Ship, Ships};
use super::Solar;
use crate::camera::ChaseCam;
use crate::comic::{body_text, display_text, panel, ComicTheme};
use crate::controller::{ControllerSet, Player, WorldBounds};
use crate::input::{PlayerInput, ViewAngles};
use crate::planet::bubble::KeepAwake;
use crate::save::{Save, SaveFile};
use crate::surface::Origin;
use crate::tuning::{ShipCombat, Tuning};
use crate::vehicle::Driving;

/// Shot down further than this from the pad, even on Haven, the respawn restarts the origin and
/// the ground there instead of carrying the far-off world across (m).
const FAR: f32 = 20_000.0;

/// What being shot down cost.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Loss {
    /// Money taken from the bank.
    pub bank: u32,
    /// The parcel lost, if one was aboard.
    pub parcel: Option<super::station::Contract>,
}

/// The player's ship shot down: the wreck they are still aboard while the camera watches it burn,
/// and what it cost, for the card.
#[derive(Resource, Debug, Default)]
pub struct Downed {
    /// The wreck, until the player is back at the Roost.
    pub wreck: Option<Entity>,
    /// Which ship it was, so a fresh one stands on its berth.
    pub spec: usize,
    /// Seconds until the respawn.
    pub left: f32,
    /// Seconds the card stays up once back at the Roost.
    pub card: f32,
    pub lost: Loss,
}

impl Downed {
    /// Whether the SHOT DOWN card is up.
    pub fn showing(&self) -> bool {
        self.wreck.is_some() || self.card > 0.0
    }
}

/// The last bounty paid, for the line over the HUD.
#[derive(Resource, Debug, Default)]
pub struct BountyLine {
    pub text: String,
    /// Seconds it stays up.
    pub left: f32,
}

#[derive(Component)]
struct LossCard;
#[derive(Component)]
struct LossText;
#[derive(Component)]
struct LossFooter;
#[derive(Component)]
struct BountyText;

pub fn build(app: &mut App) {
    app.init_resource::<Downed>()
        .init_resource::<BountyLine>()
        .add_systems(Startup, spawn_card)
        .add_systems(PreUpdate, hold_input.after(crate::input::gather))
        .add_systems(Update, show)
        .add_systems(
            FixedUpdate,
            (
                respawn.before(ControllerSet),
                die_on_cue.run_if(|| std::env::var_os("RUST_REGIME_DIE").is_some()).before(wreck),
                (shot_down, bounty).after(wreck),
            ),
        );
}

/// Takes what being shot down costs from `save`: the parcel, and `share` of the bank rounded down.
/// The guns, parts and engine tune stay. Counts the death.
pub fn lose(save: &mut Save, share: f32) -> Loss {
    let bank = ((save.banked as f64 * share.clamp(0.0, 1.0) as f64).floor() as u32).min(save.banked);
    save.banked -= bank;
    save.deaths += 1;
    Loss { bank, parcel: save.contract.take() }
}

/// Pays the bounty on ship `id` of `faction` into `save`, counting the kill; returns the pay.
pub fn pay(save: &mut Save, id: &str, faction: Faction, t: &ShipCombat) -> u32 {
    let pay = t.bounty.get(id).copied().unwrap_or(0);
    save.banked = save.banked.saturating_add(pay);
    save.kills += 1;
    *save.faction_kills.entry(faction.id().to_string()).or_default() += 1;
    pay
}

/// A kill by the ship the player flies pays; anyone else's pays nothing.
#[allow(clippy::too_many_arguments)]
fn bounty(
    mut destroyed: MessageReader<ShipDestroyed>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    file: Res<SaveFile>,
    save: Option<ResMut<Save>>,
    mut line: ResMut<BountyLine>,
    ships: Query<&Ship>,
) {
    let Some(mut save) = save else { return };
    let t = &tuning.ship_combat;
    for kill in destroyed.read() {
        let Some(killer) = kill.killer.filter(|k| *k != kill.ship) else { continue };
        if !ships.get(killer).is_ok_and(|s| s.pilot.is_some()) {
            continue;
        }
        let spec = &specs.ship[kill.spec];
        let paid = pay(&mut save, &spec.id, kill.faction, t);
        file.write(&save);
        info!("{} shot down: ${paid} bounty, {} kills", spec.name, save.kills);
        line.text = format!("+${paid} BOUNTY  {}", spec.name.to_uppercase());
        line.left = t.bounty_line;
    }
}

/// The ship the player flies is shot down: the loss is taken and saved, and the wreck stays
/// (hidden, out of the physics) so the camera can watch the blast until the respawn.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn shot_down(
    mut commands: Commands,
    mut destroyed: MessageReader<ShipDestroyed>,
    tuning: Res<Tuning>,
    file: Res<SaveFile>,
    mut save: Option<ResMut<Save>>,
    mut downed: ResMut<Downed>,
    mut ships: Query<(&Ship, &mut ChaseCam, &mut LinearVelocity, &mut AngularVelocity)>,
) {
    let t = &tuning.ship_combat;
    for kill in destroyed.read() {
        let Ok((ship, mut chase, mut v, mut w)) = ships.get_mut(kill.ship) else { continue };
        if ship.pilot.is_none() || downed.wreck.is_some() {
            continue;
        }
        let lost = save.as_mut().map_or_else(Loss::default, |s| lose(s, 0.25));
        if let Some(s) = &save {
            file.write(s);
        }
        info!("shot down: lost ${} and {}", lost.bank, if lost.parcel.is_some() { "the parcel" } else { "no parcel" });
        *downed = Downed { wreck: Some(kill.ship), spec: kill.spec, left: t.downed, card: 0.0, lost };
        // Held still where it blew up, so the chase camera holds on the blast.
        (chase.step, chase.turn) = (Vec3::ZERO, Quat::IDENTITY);
        (v.0, w.0) = (Vec3::ZERO, Vec3::ZERO);
        commands.entity(kill.ship).remove::<(Ship, KeepAwake)>().insert((RigidBodyDisabled, ColliderDisabled, Visibility::Hidden));
    }
}

/// Counts the card and the bounty line down, and once the wreck has burnt for `downed` seconds,
/// takes the player back to the Roost.
fn respawn(world: &mut World) {
    let dt = world.resource::<Time>().delta_secs();
    let card = world.resource::<Tuning>().ship_combat.loss_card;
    let mut line = world.resource_mut::<BountyLine>();
    line.left = (line.left - dt).max(0.0);
    let mut downed = world.resource_mut::<Downed>();
    downed.card = (downed.card - dt).max(0.0);
    let Some(wreck) = downed.wreck else { return };
    downed.left -= dt;
    if downed.left > 0.0 {
        return;
    }
    downed.wreck = None;
    downed.card = card;
    let lost = downed.spec;
    world.try_despawn(wreck).ok();
    let Ok(player) = world.query_filtered::<Entity, With<Player>>().single(world) else { return };
    world.entity_mut(player).remove::<(Driving, ColliderDisabled)>();
    back_at_the_roost(world, player, lost);
}

/// Puts the player on the cabin floor of a fresh Kestrel on Haven's pad, from wherever they are:
/// a handoff back to Haven if they were shot down on another world or far from the pad. Any other
/// Kestrel goes, and ship `lost`, if it was another of the apron's, stands fresh on its berth.
pub fn back_at_the_roost(world: &mut World, player: Entity, lost: usize) {
    let specs = world.resource::<Ships>().clone();
    let Some((pad, facing)) = berth(world, 0) else { return };
    let exit = pad + facing * Vec3::from(specs.ship[0].exit);
    let here = world.get::<Transform>(player).map(|tf| world.resource::<Origin>().body(tf.translation));
    if world.resource::<Solar>().anchor != "home" || here.is_none_or(|p| p.distance(exit) > FAR) {
        super::hand_off(world, "home", Some(exit));
    }
    let stale: Vec<Entity> = world.query::<(Entity, &Ship)>().iter(world).filter(|(_, s)| s.spec == 0 || s.spec == lost).map(|(e, _)| e).collect();
    for e in stale {
        world.despawn(e);
    }
    let now = world.resource::<Time>().elapsed_secs_f64();
    for spec in if lost == 0 { vec![0] } else { vec![0, lost] } {
        let Some((at, rotation)) = berth(world, spec).filter(|_| specs.ship[spec].boardable()) else { continue };
        let at = world.resource::<Origin>().world(at);
        let ship = spawn(world, spec, Transform::from_translation(at).with_rotation(rotation));
        // The Kestrel is the newest parked ship, so it stays the respawn.
        if spec == 0 {
            world.get_mut::<Ship>(ship).unwrap().landed_at = now;
        }
    }
    world.resource_mut::<WorldBounds>().spawn = exit;
    world.resource_mut::<PlayerInput>().reset_pressed = true;
}

/// While the wreck burns nothing the player presses does anything.
fn hold_input(downed: Res<Downed>, mut input: ResMut<PlayerInput>, mut view: ResMut<ViewAngles>) {
    if downed.wreck.is_some() {
        *input = PlayerInput::default();
        view.yaw = 0.0;
        view.pitch = 0.0;
    }
}

/// Dev aid: `RUST_REGIME_DIE=<seconds>` shoots down the ship being flown once it has been flown
/// that long, for screenshots of the loss card.
fn die_on_cue(time: Res<Time>, mut flown: Local<f32>, mut ships: Query<(&Ship, &mut Hull)>) {
    let after: f32 = std::env::var("RUST_REGIME_DIE").ok().and_then(|s| s.trim().parse().ok()).unwrap_or(5.0);
    let Some((_, mut hull)) = ships.iter_mut().find(|(s, _)| s.pilot.is_some()) else { return };
    *flown += time.delta_secs();
    if *flown >= after && *flown - time.delta_secs() < after {
        hull.shield = 0.0;
        hull.hp = 0.0;
        hull.last_hit_by = None;
    }
}

/// The SHOT DOWN card in the middle of the screen, and the bounty line above the crosshair, in
/// the comic HUD's paper and ink. Both hide with the rest of the HUD under the menus.
fn spawn_card(mut commands: Commands, theme: Res<ComicTheme>) {
    let t = theme.clone();
    let full = Node { position_type: PositionType::Absolute, left: Val::Px(0.0), top: Val::Px(0.0), width: Val::Percent(100.0), height: Val::Percent(100.0), justify_content: JustifyContent::Center, ..default() };
    commands.spawn((crate::hud::HudRoot, full.clone(), GlobalZIndex(5))).with_children(|p| {
        p.spawn((LossCard, Node { position_type: PositionType::Absolute, top: Val::Percent(26.0), ..default() }, Visibility::Hidden)).with_children(|c| {
            let inner = t.clone();
            panel(c, &t, t.paper, -2.0, move |c| {
                c.spawn(display_text("SHOT DOWN", 52.0, inner.red, &inner));
                c.spawn((LossText, body_text("", 22.0, inner.ink, true, &inner)));
                c.spawn((LossFooter, body_text("", 18.0, inner.muted, false, &inner)));
            });
        });
        p.spawn((BountyText, display_text("", 34.0, t.yellow, &t), TextShadow { offset: Vec2::splat(3.0), color: t.ink }, Node { position_type: PositionType::Absolute, top: Val::Percent(34.0), ..default() }, Visibility::Hidden));
    });
}

/// What the card says.
pub fn card_text(lost: &Loss, bases: &Bases) -> String {
    let parcel = lost.parcel.as_ref().map(|c| format!("the parcel for {}", bases.base.iter().find(|b| b.id == c.to).map_or(c.to.as_str(), |b| b.name.as_str())));
    match (parcel, lost.bank) {
        (None, 0) => "Nothing lost: no parcel aboard, nothing in the bank".into(),
        (None, bank) => format!("Lost ${bank} of the bank"),
        (Some(parcel), 0) => format!("Lost {parcel}"),
        (Some(parcel), bank) => format!("Lost {parcel} and ${bank} of the bank"),
    }
}

#[allow(clippy::type_complexity)]
fn show(
    downed: Res<Downed>,
    line: Res<BountyLine>,
    bases: Res<Bases>,
    mut card: Query<&mut Visibility, (With<LossCard>, Without<BountyText>)>,
    mut lost: Query<&mut Text, (With<LossText>, Without<LossFooter>, Without<BountyText>)>,
    mut footer: Query<&mut Text, (With<LossFooter>, Without<LossText>, Without<BountyText>)>,
    mut bounty: Query<(&mut Text, &mut Visibility), (With<BountyText>, Without<LossText>, Without<LossFooter>, Without<LossCard>)>,
) {
    let set = |text: &mut Text, s: String| {
        if text.0 != s {
            text.0 = s;
        }
    };
    let up = downed.showing();
    for mut v in &mut card {
        v.set_if_neq(if up { Visibility::Inherited } else { Visibility::Hidden });
    }
    if up {
        for mut text in &mut lost {
            set(&mut text, card_text(&downed.lost, &bases));
        }
        let back = if downed.wreck.is_some() { format!("Back to the Roost in {:.0}...", downed.left.max(0.0).ceil()) } else { "Back at the Roost in a fresh Kestrel".into() };
        for mut text in &mut footer {
            set(&mut text, format!("Guns, parts and engine tune kept. {back}"));
        }
    }
    for (mut text, mut v) in &mut bounty {
        v.set_if_neq(if line.left > 0.0 { Visibility::Inherited } else { Visibility::Hidden });
        set(&mut text, line.text.clone());
    }
}
