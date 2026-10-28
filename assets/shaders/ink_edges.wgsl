// Ink outlines (comic look, piece 2): ink where reverse-Z depth bends (silhouettes, steps) or
// where neighbouring normals fold. Reverse-Z depth is linear across a plane in screen space,
// so its second difference is 0 on any flat face, however steeply it is seen.
#import bevy_core_pipeline::fullscreen_vertex_shader::FullscreenVertexOutput

@group(0) @binding(0) var screen: texture_2d<f32>;
@group(0) @binding(1) var screen_sampler: sampler;
@group(0) @binding(2) var depth: texture_depth_2d;
@group(0) @binding(3) var normals: texture_2d<f32>;

struct InkEdges {
    ink: vec4<f32>,
    depth_threshold: f32,
    normal_threshold: f32,
    width: f32,
    normal_min_depth: f32,
    min_depth: f32,
    /// Share of the one-sided depth step the second difference must reach to count as a jump.
    jump: f32,
}
@group(0) @binding(4) var<uniform> settings: InkEdges;

fn d_at(p: vec2<i32>, size: vec2<i32>) -> f32 {
    return textureLoad(depth, clamp(p, vec2<i32>(0), size - 1), 0);
}

fn n_at(p: vec2<i32>, size: vec2<i32>) -> vec3<f32> {
    return textureLoad(normals, clamp(p, vec2<i32>(0), size - 1), 0).xyz * 2.0 - 1.0;
}

@fragment
fn fragment(in: FullscreenVertexOutput) -> @location(0) vec4<f32> {
    let color = textureSample(screen, screen_sampler, in.uv);
    let size = vec2<i32>(textureDimensions(depth));
    let c = vec2<i32>(in.uv * vec2<f32>(size));
    let w = max(i32(settings.width), 1);
    let dx = vec2<i32>(w, 0);
    let dy = vec2<i32>(0, w);

    let dc = d_at(c, size);
    let dl = d_at(c - dx, size);
    let dr = d_at(c + dx, size);
    let du = d_at(c - dy, size);
    let dd = d_at(c + dy, size);
    let near = max(max(max(dc, dl), max(dr, du)), dd);
    // A silhouette is a jump: the second difference is about as big as the step into it. A crease
    // or LOD fold in one continuous surface bends the depth by far less than its slope, so it stays clean.
    let lap_x = abs(dl + dr - 2.0 * dc);
    let lap_y = abs(du + dd - 2.0 * dc);
    let lap = select(0.0, lap_x, lap_x > settings.jump * max(abs(dl - dc), abs(dr - dc))) + select(0.0, lap_y, lap_y > settings.jump * max(abs(du - dc), abs(dd - dc)));
    let depth_edge = smoothstep(settings.depth_threshold, settings.depth_threshold * 1.5, lap / max(near, 1e-7));

    var normal_edge = 0.0;
    if dc > settings.normal_min_depth {
        let nc = n_at(c, size);
        let fold = max(max(1.0 - dot(nc, n_at(c + dx, size)), 1.0 - dot(nc, n_at(c - dx, size))), max(1.0 - dot(nc, n_at(c + dy, size)), 1.0 - dot(nc, n_at(c - dy, size))));
        normal_edge = smoothstep(settings.normal_threshold, settings.normal_threshold * 1.5, fold);
    }

    let edge = max(depth_edge, normal_edge) * settings.ink.a * step(settings.min_depth, near);
    return vec4<f32>(mix(color.rgb, settings.ink.rgb, edge), color.a);
}
