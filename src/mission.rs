//! Story missions: a fixed chain of objectives across the island's sites, with the current one shown on the
//! HUD with its distance and bearing. Progress is saved with the extraction loop's save.

use bevy::prelude::*;

use crate::controller::Player;
use crate::input::ViewAngles;
use crate::island::Sites;
use crate::loot::{ExtractPad, Inventory, Loot, LootSet, Save, SaveFile};
use crate::targets::{Killed, TargetKind};
use crate::vehicle::{Driving, Kind, Vehicle};

pub struct MissionPlugin;

impl Plugin for MissionPlugin {
    fn build(&self, app: &mut App) {
        let done = app.world().get_resource::<Save>().map_or(0, |s| s.missions_done);
        app.insert_resource(Missions { current: done.min(missions().len()), kills: 0, flash: 0.0 })
            .init_resource::<ObjectiveHud>()
            .add_systems(FixedUpdate, (advance, describe).chain().after(LootSet));
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Objective {
    /// Stand within `radius` of a site's origin plus `offset`.
    Reach { site: usize, offset: Vec3, radius: f32 },
    /// Kill `count` soldiers within `radius` of a site.
    Kill { site: usize, radius: f32, count: u32 },
    /// Pick up the cache marked `key`.
    Collect { key: usize },
    /// Extract while carrying `key`.
    Extract { key: usize },
    /// Be driving a `kind` within `radius` of a site.
    Drive { kind: Kind, site: usize, radius: f32 },
}

#[derive(Clone, Debug)]
pub struct Mission {
    pub title: &'static str,
    pub text: &'static str,
    pub objective: Objective,
}

/// Site indices as `island::place` orders them.
const TOWER: usize = 1;
const FORT: usize = 2;
const RUINS: usize = 4;
const LIGHTHOUSE: usize = 5;

pub fn missions() -> Vec<Mission> {
    vec![
        Mission { title: "Signal", text: "Climb the radio tower to its top platform", objective: Objective::Reach { site: TOWER, offset: Vec3::new(0.0, 41.4, 0.0), radius: 5.0 } },
        Mission { title: "Garrison", text: "Clear the fort: kill four soldiers", objective: Objective::Kill { site: FORT, radius: 90.0, count: 4 } },
        Mission { title: "Cache", text: "Recover the cache at the bottom of the quarry", objective: Objective::Collect { key: 0 } },
        Mission { title: "Exfil", text: "Carry the cache to an extraction pad and extract", objective: Objective::Extract { key: 0 } },
        Mission { title: "Convoy", text: "Drive a Humvee to the ruins", objective: Objective::Drive { kind: Kind::Humvee, site: RUINS, radius: 70.0 } },
        Mission { title: "Beacon", text: "Reach the top of the lighthouse", objective: Objective::Reach { site: LIGHTHOUSE, offset: Vec3::new(0.0, 25.3, 0.0), radius: 5.0 } },
    ]
}

#[derive(Resource, Debug)]
pub struct Missions {
    pub current: usize,
    /// Kills counted toward the current `Kill` objective.
    pub kills: u32,
    /// Seconds left of the "mission complete" banner.
    pub flash: f32,
}

/// What the HUD shows.
#[derive(Resource, Debug, Default, Clone)]
pub struct ObjectiveHud {
    pub text: String,
    pub distance: Option<f32>,
    /// Bearing of the target relative to the view, radians, positive to the right.
    pub bearing: f32,
}

#[allow(clippy::too_many_arguments)]
fn advance(
    time: Res<Time>,
    sites: Option<Res<Sites>>,
    file: Res<SaveFile>,
    mut save: ResMut<Save>,
    mut missions_res: ResMut<Missions>,
    mut killed: MessageReader<Killed>,
    inv: Res<Inventory>,
    player: Single<(&Transform, Option<&Driving>), With<Player>>,
    vehicles: Query<(&Transform, &Vehicle), Without<Player>>,
) {
    let m = &mut *missions_res;
    m.flash -= time.delta_secs();
    let list = missions();
    let Some(sites) = sites else { return };
    let (ptf, driving) = *player;
    let site = |i: usize| sites.0.get(i).map(|s| s.origin());

    if m.current >= list.len() {
        killed.clear();
        return;
    }
    let done = match list[m.current].objective {
        Objective::Reach { site: s, offset, radius } => site(s).is_some_and(|o| ptf.translation.distance(o + offset) < radius),
        Objective::Kill { site: s, radius, count } => {
            let Some(o) = site(s) else { return };
            for k in killed.read() {
                if k.kind == TargetKind::Soldier && k.pos.xz().distance(o.xz()) < radius {
                    m.kills += 1;
                }
            }
            m.kills >= count
        }
        Objective::Collect { key } => inv.keys.contains(&key),
        Objective::Extract { key } => {
            if inv.just_died || (!inv.keys.contains(&key) && !inv.just_extracted) {
                // Lost the cache: back to collecting it.
                m.current -= 1;
                save.missions_done = m.current;
                file.write(&save);
                return;
            }
            inv.just_extracted && inv.extracted_keys.contains(&key)
        }
        Objective::Drive { kind, site: s, radius } => {
            let Some(o) = site(s) else { return };
            driving.and_then(|d| vehicles.get(d.0).ok()).is_some_and(|(tf, v)| v.spec.kind == kind && tf.translation.xz().distance(o.xz()) < radius)
        }
    };
    if done {
        m.current += 1;
        m.kills = 0;
        m.flash = 4.0;
        save.missions_done = m.current;
        file.write(&save);
    }
}

fn describe(
    sites: Option<Res<Sites>>,
    missions_res: Res<Missions>,
    view: Res<ViewAngles>,
    player: Single<&Transform, With<Player>>,
    loots: Query<(&Loot, &Transform), Without<Player>>,
    pads: Query<&Transform, (With<ExtractPad>, Without<Player>)>,
    mut hud: ResMut<ObjectiveHud>,
) {
    let list = missions();
    let m = &*missions_res;
    if m.flash > 0.0 && m.current > 0 {
        hud.text = format!("MISSION COMPLETE: {}", list[m.current - 1].title);
        hud.distance = None;
        return;
    }
    if m.current >= list.len() {
        hud.text = "All missions complete. Keep extracting.".into();
        hud.distance = None;
        return;
    }
    let mission = &list[m.current];
    let Some(sites) = sites else {
        hud.text = format!("{}: {}", mission.title, mission.text);
        hud.distance = None;
        return;
    };
    let p = player.translation;
    let nearest = |it: &mut dyn Iterator<Item = Vec3>| it.min_by(|a, b| a.distance(p).total_cmp(&b.distance(p)));
    let target = match mission.objective {
        Objective::Reach { site, offset, .. } => sites.0.get(site).map(|s| s.origin() + offset),
        Objective::Kill { site, .. } | Objective::Drive { site, .. } => sites.0.get(site).map(|s| s.origin()),
        Objective::Collect { key } => nearest(&mut loots.iter().filter(|(l, _)| l.key == Some(key)).map(|(_, tf)| tf.translation)),
        Objective::Extract { .. } => nearest(&mut pads.iter().map(|tf| tf.translation)),
    };
    let progress = match mission.objective {
        Objective::Kill { count, .. } => format!(" ({}/{})", m.kills, count),
        _ => String::new(),
    };
    hud.text = format!("{}: {}{}", mission.title, mission.text, progress);
    hud.distance = target.map(|t| t.distance(p));
    if let Some(t) = target {
        let to = (t - p).xz();
        // View yaw 0 looks toward -Z; a target's bearing from that, positive to the right.
        let target_yaw = (-to.x).atan2(-to.y);
        let mut rel = target_yaw - view.yaw;
        while rel > std::f32::consts::PI {
            rel -= std::f32::consts::TAU;
        }
        while rel < -std::f32::consts::PI {
            rel += std::f32::consts::TAU;
        }
        hud.bearing = -rel;
    }
}
