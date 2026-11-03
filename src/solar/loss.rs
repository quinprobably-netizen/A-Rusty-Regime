//! What a fight pays and costs (sections 9 and 10 of
//! `docs/superpowers/specs/2026-10-29-ship-combat-stage-1-design.md`), read from `combat`'s
//! `ShipDestroyed` messages.
//!
//! **Bounty:** an enemy ship shot down by the ship the player flies pays its `[ship_combat]
//! bounty` into the pocket (banked at a base's door, `economy`), counts in `Save::kills` and its faction's tally, and puts a
//! `+$120 BOUNTY` line over the HUD for a few seconds. A kill by anyone else pays nothing.
//!
//! **The loss rule:** when the ship the player flies is shot down, it blows apart and the camera
//! hangs where it was for `downed` seconds while a SHOT DOWN card says what it cost: what was
//! aboard (the unbanked pocket, the hold's scrap and any courier parcels, each costing standing
//! with whoever gave it) and the rebuy fee for a
//! fresh Kestrel, from the bank (`economy::rebuy_fee`, never more than is there). Then the
//! wreck is gone and the player is back on the Roost's apron at Haven, from anywhere in the
//! system, on the cabin floor of a fresh Kestrel on the pad (and a fresh copy of the ship lost, on
//! its own berth, if it was another of the apron's). Guns, parts, modules and the Yard's engine
//! tune are in the save and are not touched.
//!
//! **A ship lost with nobody aboard:** one of the player's own ships (the apron's, or a fighter
//! from the hangar) blown apart while they are out of it is not a death: the pocket and the
//! parcels were with them and stay. The ship is still gone, so the rebuy fee is paid, the hold
//! goes with it if it was the ship they last stepped out of, a `KESTREL LOST` line says so, and
//! a fresh one stands where they can reach it (`replace`): on Haven on its own berth, anywhere
//! else on the nearest base pad of their world, so a lost ship never strands them.
//!
//! **Never without a ship:** if somehow none of the player's ships is left while they are on
//! foot, a fresh Kestrel stands for them the same way (`never_stranded`).
//!
//! Kill rewards (`Rewards`: the bounty, a cull's pay, salvage taken aboard) are settled before
//! the player's own loss in the same tick, so what a dying ship earned is lost with it.

use avian3d::prelude::*;
use bevy::prelude::*;

use super::base::{pad_top, Bases};
use super::combat::{wreck, Faction, Hull, ShipDestroyed};
use super::hangar::Owned;
use super::ship::{berth, spawn, Ship, Ships};
use super::Solar;
use crate::camera::ChaseCam;
use crate::comic::{body_text, display_text, panel, ComicTheme};
use crate::controller::{ControllerSet, Player, WorldBounds};
use crate::input::{PlayerInput, ViewAngles};
use crate::planet::bubble::KeepAwake;
use crate::save::{Save, SaveFile};
use crate::surface::Origin;
use crate::tuning::{Economy, ShipCombat, Tuning};
use crate::vehicle::Driving;

/// Shot down further than this from the pad, even on Haven, the respawn restarts the origin and
/// the ground there instead of carrying the far-off world across (m).
const FAR: f32 = 20_000.0;
/// Seconds on foot with no ship of yours anywhere before a fresh Kestrel stands for you.
const STRANDED: f32 = 1.0;

/// What a kill pays into the pocket or the hold (`bounty`, `board::cull`, `salvage::gather`):
/// settled before the player's own ship is taken through the loss rule in the same tick, so a
/// kill made as it blew up is lost with it instead of riding over into the fresh one.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct Rewards;

/// What being shot down cost.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Loss {
    /// Unbanked money lost with the ship.
    pub pocket: u32,
    /// Scrap lost from the hold.
    pub scrap: u32,
    /// The parcels lost (courier jobs; culls and supply runs are not cargo and stay).
    pub parcels: Vec<super::board::Contract>,
    /// The rebuy fee taken from the bank for a fresh Kestrel.
    pub fee: u32,
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
                bounty.after(wreck).in_set(Rewards),
                (shot_down, empty_lost).after(wreck).after(Rewards),
                never_stranded.after(shot_down).after(empty_lost),
            ),
        );
}

/// Takes what being shot down costs from `save`: the pocket, the hold and the parcel, and the
/// rebuy fee from the bank (as much of it as is there). The guns, parts, modules and engine tune
/// stay. Counts the death.
pub fn lose(save: &mut Save, e: &Economy, t: &ShipCombat) -> Loss {
    let fee = rebuy(save, e, t);
    save.deaths += 1;
    let (parcels, kept) = std::mem::take(&mut save.contracts).into_iter().partition(|c| c.parcel_for().is_some());
    save.contracts = kept;
    Loss { pocket: std::mem::take(&mut save.pocket), scrap: std::mem::take(&mut save.scrap), parcels, fee }
}

/// Takes what losing a ship with nobody aboard costs from `save`: the rebuy fee from the bank (as
/// much of it as is there), and the hold if it was in that ship (`hold`). The pocket and the
/// parcels were with the player and are kept, and it is not a death.
pub fn lose_empty(save: &mut Save, hold: bool, e: &Economy, t: &ShipCombat) -> Loss {
    let fee = rebuy(save, e, t);
    let scrap = if hold { std::mem::take(&mut save.scrap) } else { 0 };
    Loss { scrap, fee, ..default() }
}

/// Takes the rebuy fee from the bank, never more than is there; returns what was taken.
fn rebuy(save: &mut Save, e: &Economy, t: &ShipCombat) -> u32 {
    let fee = super::economy::rebuy_fee(save, e, t).min(save.banked);
    save.banked -= fee;
    fee
}

/// The line over the HUD for ship `name` lost with nobody aboard.
pub fn lost_line(name: &str, lost: &Loss) -> String {
    let scrap = if lost.scrap > 0 { format!("  -{} SCRAP", lost.scrap) } else { String::new() };
    let rebuy = if lost.fee > 0 { format!("REBUY ${}", lost.fee) } else { "REBUY FREE".into() };
    format!("{} LOST{scrap}  {rebuy}", name.to_uppercase())
}

/// Pays the bounty on ship `id` of `faction` into the pocket in `save`, counting the kill; returns
/// the pay.
pub fn pay(save: &mut Save, id: &str, faction: Faction, t: &ShipCombat) -> u32 {
    let pay = t.bounty.get(id).copied().unwrap_or(0);
    save.pocket = save.pocket.saturating_add(pay);
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
    bases: Res<Bases>,
    mut ships: Query<(&Ship, &mut ChaseCam, &mut LinearVelocity, &mut AngularVelocity)>,
) {
    let t = &tuning.ship_combat;
    for kill in destroyed.read() {
        let Ok((ship, mut chase, mut v, mut w)) = ships.get_mut(kill.ship) else { continue };
        if ship.pilot.is_none() || downed.wreck.is_some() {
            continue;
        }
        let lost = save.as_mut().map_or_else(Loss::default, |s| {
            let lost = lose(s, &tuning.economy, t);
            // A parcel lost costs standing with whoever gave it.
            for c in &lost.parcels {
                super::board::dropped(s, c, &bases, &tuning.economy, t);
            }
            lost
        });
        if let Some(s) = &save {
            file.write(s);
        }
        info!("shot down: {lost:?}");
        *downed = Downed { wreck: Some(kill.ship), spec: kill.spec, left: t.downed, card: 0.0, lost };
        // Held still where it blew up, so the chase camera holds on the blast.
        (chase.step, chase.turn) = (Vec3::ZERO, Quat::IDENTITY);
        (v.0, w.0) = (Vec3::ZERO, Vec3::ZERO);
        commands.entity(kill.ship).remove::<(Ship, KeepAwake)>().insert((RigidBodyDisabled, ColliderDisabled, Visibility::Hidden));
    }
}

/// One of the player's own ships blown apart with nobody aboard: the ship lost (`lose_empty`;
/// the hold with it if it was the one they last stepped out of and they fly no other), the line
/// over the HUD, and a fresh one where they can reach it (`replace`).
#[allow(clippy::too_many_arguments)]
fn empty_lost(
    mut commands: Commands,
    mut destroyed: MessageReader<ShipDestroyed>,
    tuning: Res<Tuning>,
    specs: Res<Ships>,
    file: Res<SaveFile>,
    mut save: Option<ResMut<Save>>,
    mut line: ResMut<BountyLine>,
    ships: Query<(Entity, &Ship, &Faction)>,
    flying: Query<(), (With<Player>, With<Driving>)>,
) {
    for kill in destroyed.read() {
        let Ok((_, ship, _)) = ships.get(kill.ship) else { continue };
        if kill.faction != Faction::Deserters || ship.pilot.is_some() {
            continue;
        }
        // The newest parked of the player's ships is the one they last stepped out of, as for the respawn.
        let newest = |s: &Ship| (s.landed_at, std::cmp::Reverse(s.spec));
        let last = flying.is_empty() && !ships.iter().any(|(e, s, f)| e != kill.ship && *f == Faction::Deserters && newest(s) > newest(ship));
        let lost = save.as_mut().map_or_else(Loss::default, |s| lose_empty(s, last, &tuning.economy, &tuning.ship_combat));
        if let Some(s) = &save {
            file.write(s);
        }
        let name = &specs.ship[kill.spec].name;
        info!("{name} lost with nobody aboard: {lost:?}");
        line.text = lost_line(name, &lost);
        line.left = tuning.ship_combat.loss_card;
        let spec = kill.spec;
        commands.entity(kill.ship).despawn();
        commands.queue(move |world: &mut World| replace(world, spec));
    }
}

/// Where a fresh ship `spec` for the player stands, from body point `near` on the anchor: on
/// Haven its own berth on the apron (`None` for a fighter, which parks in the hangar by itself),
/// elsewhere the nearest base pad on that world, if it has one. Body coordinates and turn.
fn stand(world: &World, spec: usize, near: Vec3) -> Option<(Vec3, Quat)> {
    let solar = world.resource::<Solar>();
    if solar.anchor == "home" {
        return berth(world, spec);
    }
    let sphere = solar.spheres.get(&solar.anchor)?;
    let rest = world.resource::<Ships>().ship.get(spec)?.rest;
    world
        .resource::<Bases>()
        .base
        .iter()
        .filter(|b| b.body == solar.anchor)
        .filter_map(|b| pad_top(b, sphere, solar.pad))
        .map(|(top, frame)| (top + frame * Vec3::Y * (rest + 0.05), frame))
        .min_by(|a, b| a.0.distance(near).total_cmp(&b.0.distance(near)))
}

/// A fresh ship `spec` for the player in place of one of theirs that is gone, where they can
/// reach it (`stand`); a fighter of theirs on Haven parks in its hangar slot by itself
/// (`hangar::park_owned`). On a world with no pad, on foot, there is no getting off it: they are
/// taken back to the Roost as after being shot down (`back_at_the_roost`), without the loss.
pub fn replace(world: &mut World, spec: usize) {
    let Ok((player, tf, flying)) = world.query_filtered::<(Entity, &Transform, Has<Driving>), With<Player>>().single(world).map(|(e, tf, d)| (e, *tf, d)) else { return };
    let near = world.resource::<Origin>().body(tf.translation);
    let home = world.resource::<Solar>().anchor == "home";
    match stand(world, spec, near) {
        Some((at, rotation)) => {
            let at = world.resource::<Origin>().world(at);
            let now = world.resource::<Time>().elapsed_secs_f64();
            let ship = spawn(world, spec, Transform::from_translation(at).with_rotation(rotation));
            // The newest parked ship, so it is where a fall or a reset comes back to.
            world.get_mut::<Ship>(ship).unwrap().landed_at = now;
            if !world.resource::<Ships>().ship[spec].boardable() {
                // After the spawn's own faction from its spec: it flies as yours.
                world.commands().entity(ship).insert((Owned, Faction::Deserters));
                world.flush();
            }
            info!("a fresh {} stands for you", world.resource::<Ships>().ship[spec].name);
        }
        None if home || flying => {}
        None => back_at_the_roost(world, player, spec),
    }
}

/// The safety net: on foot with no ship of theirs anywhere (not aboard one, not watching a wreck
/// burn) for `STRANDED` seconds, the player gets a fresh Kestrel (`replace`). The fleet stands
/// from startup and every ship is carried through a handoff, so this only catches a ship gone in
/// some way nothing else answered for.
fn never_stranded(world: &mut World, mut alone: Local<f32>) {
    let dt = world.resource::<Time>().delta_secs();
    let on_foot = world.query_filtered::<(), (With<Player>, Without<Driving>)>().iter(world).next().is_some();
    let stranded = on_foot && world.resource::<Downed>().wreck.is_none() && !world.query_filtered::<&Faction, With<Ship>>().iter(world).any(|f| *f == Faction::Deserters);
    *alone = if stranded { *alone + dt } else { 0.0 };
    if *alone < STRANDED {
        return;
    }
    *alone = 0.0;
    warn!("no ship of yours anywhere: a fresh Kestrel");
    replace(world, 0);
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

/// What the card says: what was aboard, then the rebuy.
pub fn card_text(lost: &Loss, bases: &Bases) -> String {
    let mut aboard = Vec::new();
    if lost.pocket > 0 {
        aboard.push(format!("${} unbanked", lost.pocket));
    }
    if lost.scrap > 0 {
        aboard.push(format!("{} scrap", lost.scrap));
    }
    match lost.parcels.as_slice() {
        [] => {}
        [c] => aboard.push(format!("the parcel for {}", super::board::name_of(bases, c.parcel_for().unwrap_or("?")))),
        many => aboard.push(format!("{} parcels", many.len())),
    }
    let aboard = match aboard.len() {
        0 => "Nothing aboard lost".to_string(),
        1 => format!("Lost {}", aboard[0]),
        n => format!("Lost {} and {}", aboard[..n - 1].join(", "), aboard[n - 1]),
    };
    let rebuy = if lost.fee > 0 { format!("Rebuy ${}", lost.fee) } else { "Rebuy free: the bank is empty".to_string() };
    format!("{aboard}. {rebuy}")
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
            set(&mut text, format!("Guns, parts, modules and engine tune kept. {back}"));
        }
    }
    for (mut text, mut v) in &mut bounty {
        v.set_if_neq(if line.left > 0.0 { Visibility::Inherited } else { Visibility::Hidden });
        set(&mut text, line.text.clone());
    }
}
