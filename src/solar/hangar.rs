//! Faction fighters for sale (stage D of `docs/superpowers/specs/2026-10-29-economy-design.md`).
//!
//! At Allied standing a faction's job board sells you one of its own patrol fighters
//! (`[economy] hulls`: the PMC's Sentry, the Scrappers' Welder, the Regime's Censer), priced by
//! that standing like anything else it sells. What you own is in `Save::hulls`. Each one parks in
//! the hangar row at Haven, south-west of the pad (`HANGAR`), nose west, and comes back there
//! whenever it is missing while you are on Haven: bought far away, shot down (the rebuy fee is the
//! same as the Kestrel's), or left on another world when the game was closed.
//!
//! An owned fighter flies as your side (`Faction::Deserters`), whatever it was built for, so it
//! changes nothing about how the factions treat you. Your engine tune, ship parts and modules are
//! your kit, not the Kestrel's: they land on whichever of your ships you fly (`salvage::refit`).
//! A fighter has no cabin: E beside it climbs in, and stepping out puts you beside it again.

use bevy::prelude::*;

use super::combat::Faction;
use super::ship::{self, Ship, Ships};
use super::{standing, Fixture, Solar};
use crate::save::Save;
use crate::surface::{Origin, Surface};
use crate::tuning::{Economy, ShipCombat};

/// A ship of yours that is not the Kestrel: a fighter bought from a faction.
#[derive(Component, Debug, Clone, Copy)]
pub struct Owned;

/// The hangar row at Haven: where each fighter you own parks, in the order you bought them, in
/// metres east and south of the pad's centre.
pub const HANGAR: [[f32; 2]; 3] = [[-20.0, 60.0], [-36.0, 60.0], [-52.0, 60.0]];

/// What a faction's board says about its fighter.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Offer {
    /// It sells none (the Roost, a faction with no fighter listed).
    None,
    /// For sale to you at this price.
    Price { ship: String, price: u32 },
    /// Not until you are Allied; at this price then.
    Allied { ship: String, price: u32 },
    /// You have one.
    Owned { ship: String },
}

/// Why no fighter was bought.
#[derive(Debug, PartialEq, Eq)]
pub enum Refusal {
    NotForSale,
    NotAllied,
    Owned,
    /// Short of money by this much.
    Poor(u32),
    /// Every hangar slot is taken.
    HangarFull,
}

/// What the board of a base of `faction` offers you in fighters.
pub fn offer(save: &Save, faction: Faction, e: &Economy, t: &ShipCombat) -> Offer {
    let Some(sale) = e.hulls.get(faction.id()) else { return Offer::None };
    let ship = sale.ship.clone();
    if save.hulls.contains(&ship) {
        return Offer::Owned { ship };
    }
    let price = standing::price(sale.price, faction, save, t);
    if standing::get(save, faction, t) < standing::ALLIED {
        // What it will cost once you are Allied, which is Friendly or better.
        return Offer::Allied { ship, price: (sale.price as f32 * (1.0 - t.standing_discount)).round() as u32 };
    }
    Offer::Price { ship, price }
}

/// Buys the fighter a base of `faction` sells, if you are Allied and can pay; returns its id and
/// the price.
pub fn buy(save: &mut Save, faction: Faction, e: &Economy, t: &ShipCombat) -> Result<(String, u32), Refusal> {
    match offer(save, faction, e, t) {
        Offer::None => Err(Refusal::NotForSale),
        Offer::Owned { .. } => Err(Refusal::Owned),
        Offer::Allied { .. } => Err(Refusal::NotAllied),
        Offer::Price { price, .. } if save.banked < price => Err(Refusal::Poor(price - save.banked)),
        Offer::Price { .. } if save.hulls.len() >= HANGAR.len() => Err(Refusal::HangarFull),
        Offer::Price { ship, price } => {
            save.banked -= price;
            save.hulls.push(ship.clone());
            Ok((ship, price))
        }
    }
}

/// A ship's name from its id, for the board (`sentry` is `Sentry`).
pub fn title(id: &str) -> String {
    let mut c = id.chars();
    c.next().map_or(String::new(), |f| f.to_uppercase().chain(c).collect())
}

/// Where hangar slot `slot` is: the slab's deck and the parked ship's spot and turn, in Haven's
/// body coordinates. `None` off Haven.
fn slot_at(solar: &Solar, slot: usize) -> Option<(f32, Vec3, Quat)> {
    let [x, z] = *HANGAR.get(slot)?;
    let sphere = solar.spheres.get("home")?;
    let pad = solar.pad;
    let frame = Surface::Sphere(sphere.clone()).frame(pad);
    let deck = super::slab_deck(sphere, pad, Vec2::new(x, z));
    Some((deck, pad + frame * Vec3::new(x, deck, z), frame * Quat::from_rotation_y(std::f32::consts::FRAC_PI_2)))
}

/// The hangar row's slabs, with the rest of Haven's fixtures.
pub fn slabs(world: &mut World) {
    let solar = world.resource::<Solar>();
    if solar.anchor != "home" {
        return;
    }
    let spots: Vec<(Vec3, Quat)> = (0..HANGAR.len()).filter_map(|i| slot_at(solar, i)).map(|(_, at, _)| (at, Surface::Sphere(solar.spheres["home"].clone()).frame(solar.pad))).collect();
    let origin = *world.resource::<Origin>();
    let size = Vec3::new(super::FIGHTER_PAD, 14.0, super::FIGHTER_PAD);
    let material = world.get_resource_mut::<Assets<StandardMaterial>>().map(|mut m| m.add(StandardMaterial { base_color: Color::srgb(0.32, 0.33, 0.35), perceptual_roughness: 0.8, ..default() }));
    for (at, frame) in spots {
        let transform = Transform::from_translation(origin.world(at - frame * Vec3::Y * (size.y / 2.0))).with_rotation(frame);
        let mesh = world.get_resource_mut::<Assets<Mesh>>().map(|mut m| m.add(Cuboid::from_size(size)));
        let mut e = world.spawn((Name::new("Hangar slab"), Fixture, avian3d::prelude::RigidBody::Static, avian3d::prelude::Collider::cuboid(size.x, size.y, size.z), transform));
        if let (Some(mesh), Some(material)) = (mesh, material.clone()) {
            e.insert((Mesh3d(mesh), MeshMaterial3d(material)));
        }
    }
}

/// On Haven, every fighter you own that is not anywhere in the game stands in its hangar slot.
pub fn park_owned(world: &mut World) {
    let Some(save) = world.get_resource::<Save>() else { return };
    if save.hulls.is_empty() || world.resource::<Solar>().anchor != "home" {
        return;
    }
    let hulls = save.hulls.clone();
    let specs = world.resource::<Ships>().clone();
    let have: Vec<usize> = world.query_filtered::<&Ship, With<Owned>>().iter(world).map(|s| s.spec).collect();
    for (slot, id) in hulls.iter().enumerate() {
        let Some(spec) = specs.ship.iter().position(|s| s.id == *id) else { continue };
        if have.contains(&spec) {
            continue;
        }
        let Some((_, at, turn)) = slot_at(world.resource::<Solar>(), slot) else { continue };
        let at = world.resource::<Origin>().world(at + turn * Vec3::Y * (specs.ship[spec].rest + 0.05));
        let e = ship::spawn(world, spec, Transform::from_translation(at).with_rotation(turn));
        // After the spawn's own faction from its spec: it flies as yours.
        world.commands().entity(e).insert((Owned, Faction::Deserters));
        world.flush();
        info!("{} parked in hangar slot {}", specs.ship[spec].name, slot + 1);
    }
}

pub fn build(app: &mut App) {
    app.add_systems(Update, park_owned.run_if(resource_exists::<Save>));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_allied_faction_sells_its_fighter_once_at_the_friends_price() {
        let (e, t) = (Economy::default(), ShipCombat::default());
        let mut save = Save { banked: 20_000, ..default() };
        assert_eq!(offer(&save, Faction::Deserters, &e, &t), Offer::None, "the Roost sells none");
        assert_eq!(offer(&save, Faction::Pmc, &e, &t), Offer::Allied { ship: "sentry".into(), price: 5100 });
        assert_eq!(buy(&mut save, Faction::Pmc, &e, &t), Err(Refusal::NotAllied));
        save.standing.insert("pmc".into(), 80);
        assert_eq!(buy(&mut save, Faction::Pmc, &e, &t), Ok(("sentry".to_string(), 5100)));
        assert_eq!((save.banked, save.hulls.clone()), (14_900, vec!["sentry".to_string()]));
        assert_eq!(buy(&mut save, Faction::Pmc, &e, &t), Err(Refusal::Owned));
        save.standing.insert("regime".into(), 90);
        save.banked = 100;
        assert_eq!(buy(&mut save, Faction::Regime, &e, &t), Err(Refusal::Poor(7650 - 100)));
        assert_eq!(title("welder"), "Welder");
    }
}
