//! Ink outlines for the toon world (piece 2): one post-process pass on the player camera that
//! reads the depth and normal prepasses and draws ink where depth jumps or normals fold.
//! It follows `Toon`, adding and removing its prepasses with it.

use bevy::anti_alias::taa::TemporalAntiAliasing;
use bevy::core_pipeline::prepass::{DepthPrepass, NormalPrepass, ViewPrepassTextures};
use bevy::core_pipeline::{schedule::Core3d, tonemapping::tonemapping, Core3dSystems, FullscreenShader};
use bevy::prelude::*;
use bevy::render::extract_component::{ComponentUniforms, DynamicUniformIndex, ExtractComponent, ExtractComponentPlugin, UniformComponentPlugin};
use bevy::render::render_resource::binding_types::{sampler, texture_2d, texture_depth_2d, uniform_buffer};
use bevy::render::render_resource::*;
use bevy::render::renderer::{RenderContext, RenderDevice, ViewQuery};
use bevy::render::view::ViewTarget;
use bevy::render::{RenderApp, RenderStartup};

use super::toon::Toon;
use crate::camera::PlayerCamera;

/// The pass's settings; on a camera, it turns the pass on.
#[derive(Component, Clone, Copy, ExtractComponent, ShaderType, Debug)]
pub struct InkEdges {
    pub ink: Vec4,
    /// Second difference of reverse-Z depth over the local depth: 0 on any plane, 1 at a silhouette.
    pub depth_threshold: f32,
    /// 1 - cos of the fold between neighbouring normals that draws a line.
    pub normal_threshold: f32,
    /// Pixels from the centre to each sample.
    pub width: f32,
    /// Normal folds only draw nearer than this (reverse-Z depth: near / distance).
    pub normal_min_depth: f32,
}

impl Default for InkEdges {
    fn default() -> Self {
        let ink = super::ComicTheme::look_a().ink.to_linear();
        Self { ink: Vec4::new(ink.red, ink.green, ink.blue, 1.0), depth_threshold: 0.08, normal_threshold: 0.4, width: 1.0, normal_min_depth: 0.02 / 150.0 }
    }
}

pub struct EdgesPlugin;

impl Plugin for EdgesPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Toon>().add_systems(Update, follow_toon);
        if app.get_sub_app(RenderApp).is_none() {
            return;
        }
        app.add_plugins((ExtractComponentPlugin::<InkEdges>::default(), UniformComponentPlugin::<InkEdges>::default()));
        let render_app = app.sub_app_mut(RenderApp);
        render_app
            .add_systems(RenderStartup, init_pipeline)
            .add_systems(Core3d, ink_edges.in_set(Core3dSystems::PostProcess).before(tonemapping));
    }
}

/// Puts the pass and its prepasses on the player camera while `Toon` is on, and takes them off
/// after. The depth prepass stays while anti-aliasing needs it.
fn follow_toon(mut commands: Commands, toon: Res<Toon>, cameras: Query<(Entity, Has<InkEdges>, Has<TemporalAntiAliasing>), With<PlayerCamera>>) {
    for (entity, has, taa) in &cameras {
        if toon.0 && !has {
            commands.entity(entity).insert((InkEdges::default(), DepthPrepass, NormalPrepass));
        } else if !toon.0 && has {
            let mut e = commands.entity(entity);
            e.remove::<(InkEdges, NormalPrepass)>();
            if !taa {
                e.remove::<DepthPrepass>();
            }
        }
    }
}

#[derive(Resource)]
struct EdgesPipeline {
    layout: BindGroupLayoutDescriptor,
    sampler: Sampler,
    hdr: CachedRenderPipelineId,
    sdr: CachedRenderPipelineId,
}

fn init_pipeline(mut commands: Commands, device: Res<RenderDevice>, server: Res<AssetServer>, fullscreen: Res<FullscreenShader>, cache: Res<PipelineCache>) {
    let layout = BindGroupLayoutDescriptor::new(
        "ink_edges_layout",
        &BindGroupLayoutEntries::sequential(
            ShaderStages::FRAGMENT,
            (
                texture_2d(TextureSampleType::Float { filterable: true }),
                sampler(SamplerBindingType::Filtering),
                texture_depth_2d(),
                texture_2d(TextureSampleType::Float { filterable: false }),
                uniform_buffer::<InkEdges>(true),
            ),
        ),
    );
    let shader = server.load("shaders/ink_edges.wgsl");
    let queue = |format: TextureFormat| {
        cache.queue_render_pipeline(RenderPipelineDescriptor {
            label: Some("ink_edges_pipeline".into()),
            layout: vec![layout.clone()],
            vertex: fullscreen.to_vertex_state(),
            fragment: Some(FragmentState { shader: shader.clone(), targets: vec![Some(ColorTargetState { format, blend: None, write_mask: ColorWrites::ALL })], ..default() }),
            ..default()
        })
    };
    let hdr = queue(TextureFormat::Rgba16Float);
    let sdr = queue(TextureFormat::Rgba8UnormSrgb);
    commands.insert_resource(EdgesPipeline { layout, sampler: device.create_sampler(&SamplerDescriptor::default()), hdr, sdr });
}

fn ink_edges(
    view: ViewQuery<(&ViewTarget, &ViewPrepassTextures, &DynamicUniformIndex<InkEdges>)>,
    pipeline: Option<Res<EdgesPipeline>>,
    cache: Res<PipelineCache>,
    uniforms: Res<ComponentUniforms<InkEdges>>,
    mut ctx: RenderContext,
) {
    let Some(pipeline) = pipeline else { return };
    let (target, prepass, index) = view.into_inner();
    let (Some(depth), Some(normal)) = (prepass.depth_view(), prepass.normal_view()) else { return };
    let id = if target.main_texture_format() == TextureFormat::Rgba16Float { pipeline.hdr } else { pipeline.sdr };
    let (Some(render_pipeline), Some(binding)) = (cache.get_render_pipeline(id), uniforms.uniforms().binding()) else { return };
    let post = target.post_process_write();
    let bind_group = ctx.render_device().create_bind_group(
        "ink_edges_bind_group",
        &cache.get_bind_group_layout(&pipeline.layout),
        &BindGroupEntries::sequential((post.source, &pipeline.sampler, depth, normal, binding.clone())),
    );
    let mut pass = ctx.command_encoder().begin_render_pass(&RenderPassDescriptor {
        label: Some("ink_edges_pass"),
        color_attachments: &[Some(RenderPassColorAttachment { view: post.destination, depth_slice: None, resolve_target: None, ops: Operations::default() })],
        depth_stencil_attachment: None,
        timestamp_writes: None,
        occlusion_query_set: None,
        multiview_mask: None,
    });
    pass.set_pipeline(render_pipeline);
    pass.set_bind_group(0, &bind_group, &[index.index()]);
    pass.draw(0..3, 0..1);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edges_follow_the_setting() {
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, EdgesPlugin));
        let camera = app.world_mut().spawn(PlayerCamera::default()).id();
        app.update();
        let has = |app: &App| {
            let e = app.world().entity(camera);
            (e.contains::<InkEdges>(), e.contains::<DepthPrepass>(), e.contains::<NormalPrepass>())
        };
        assert_eq!(has(&app), (true, true, true));
        app.world_mut().resource_mut::<Toon>().0 = false;
        app.update();
        assert_eq!(has(&app), (false, false, false));
    }

    #[test]
    fn depth_prepass_stays_for_anti_aliasing() {
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, EdgesPlugin));
        let camera = app.world_mut().spawn((PlayerCamera::default(), TemporalAntiAliasing::default())).id();
        app.update();
        app.world_mut().resource_mut::<Toon>().0 = false;
        app.update();
        let e = app.world().entity(camera);
        assert!(!e.contains::<InkEdges>() && !e.contains::<NormalPrepass>());
        assert!(e.contains::<DepthPrepass>());
    }
}
