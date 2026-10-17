// Sea: four moving wave sets give the normal, the depth prepass gives the water depth under
// each pixel for the shoreline foam and the shallow-to-deep tint. Forward only (it blends).
#import bevy_pbr::{
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    forward_io::{VertexOutput, FragmentOutput},
    mesh_view_bindings::globals,
    view_transformations::depth_ndc_to_view_z,
}
#ifdef DEPTH_PREPASS
#import bevy_pbr::prepass_utils::prepass_depth
#endif

struct Sea {
    shallow: vec4<f32>,
    deep: vec4<f32>,
    // Wave amplitude, wavelength, speed, foam depth.
    params: vec4<f32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var<uniform> sea: Sea;

// Gradient of a sum of directional sine waves at `p`, for the normal.
fn wave_slope(p: vec2<f32>, t: f32) -> vec2<f32> {
    let a = sea.params.x;
    let l = sea.params.y;
    let s = sea.params.z;
    var g = vec2(0.0);
    let dirs = array<vec2<f32>, 4>(vec2(1.0, 0.2), vec2(-0.4, 1.0), vec2(0.7, -0.7), vec2(-1.0, -0.3));
    let scales = vec4(1.0, 0.53, 0.31, 0.17);
    let amps = vec4(1.0, 0.6, 0.35, 0.2);
    for (var i = 0; i < 4; i++) {
        let d = normalize(dirs[i]);
        let k = 6.2831853 / (l * scales[i]);
        let phase = dot(d, p) * k + t * s * sqrt(k);
        g += d * (a * amps[i] * k * cos(phase));
    }
    return g;
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    let p = in.world_position.xyz;
    let t = globals.time;
    let slope = wave_slope(p.xz, t) + 0.35 * wave_slope(p.xz * 3.1 + vec2(17.0, 5.0), t * 1.3);
    let n = normalize(vec3(-slope.x, 1.0, -slope.y));

    // Depth of water under this pixel, along the view ray.
    var depth = 20.0;
#ifdef DEPTH_PREPASS
    let scene_z = depth_ndc_to_view_z(prepass_depth(in.position, 0u));
    let frag_z = depth_ndc_to_view_z(in.position.z);
    depth = max(frag_z - scene_z, 0.0);
#endif
    let foam = 1.0 - smoothstep(0.0, sea.params.w, depth + 0.6 * sin(p.x * 0.7 + t * 1.5) * sin(p.z * 0.9 - t));
    let shallow = smoothstep(0.0, 12.0, depth);
    var color = mix(sea.shallow.rgb, sea.deep.rgb, shallow);
    color = mix(color, vec3(0.9, 0.93, 0.95), foam * 0.8);
    let alpha = mix(0.55, 0.96, smoothstep(0.0, 4.0, depth));

    pbr_input.material.base_color = vec4(color, max(alpha, foam));
    pbr_input.material.perceptual_roughness = mix(0.08, 0.6, foam);
    pbr_input.N = n;
    pbr_input.material.base_color = alpha_discard(pbr_input.material, pbr_input.material.base_color);

    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr_input);
    out.color = main_pass_post_lighting_processing(pbr_input, out.color);
    return out;
}
