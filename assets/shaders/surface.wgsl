// Triplanar PBR surface for generated geometry: color, normal and roughness maps projected
// along the world axes, so a 20 m wall tiles instead of stretching. The material's base
// color tints it.
#import bevy_pbr::{
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::alpha_discard,
}
#ifdef PREPASS_PIPELINE
#import bevy_pbr::{
    prepass_io::{VertexOutput, FragmentOutput},
    pbr_deferred_functions::deferred_output,
}
#else
#import bevy_pbr::{
    forward_io::{VertexOutput, FragmentOutput},
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
}
#endif

struct Surface {
    // Tiles per metre.
    scale: f32,
    // Multiplies the roughness map.
    rough: f32,
    normal_strength: f32,
    _pad: f32,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var color_t: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(101) var color_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(102) var normal_t: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(103) var normal_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(104) var rough_t: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(105) var rough_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(106) var<uniform> surface: Surface;

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);

    let p = in.world_position.xyz * surface.scale;
    let ng = normalize(in.world_normal);
    var bw = abs(ng);
    bw = bw * bw * bw * bw;
    bw = bw / (bw.x + bw.y + bw.z);

    let cx = textureSample(color_t, color_s, p.zy).rgb;
    let cy = textureSample(color_t, color_s, p.xz).rgb;
    let cz = textureSample(color_t, color_s, p.xy).rgb;
    let color = cx * bw.x + cy * bw.y + cz * bw.z;

    let rx = textureSample(rough_t, rough_s, p.zy).r;
    let ry = textureSample(rough_t, rough_s, p.xz).r;
    let rz = textureSample(rough_t, rough_s, p.xy).r;
    let rough = (rx * bw.x + ry * bw.y + rz * bw.z) * surface.rough;

    let tx = textureSample(normal_t, normal_s, p.zy).xyz * 2.0 - 1.0;
    let ty = textureSample(normal_t, normal_s, p.xz).xyz * 2.0 - 1.0;
    let tz = textureSample(normal_t, normal_s, p.xy).xyz * 2.0 - 1.0;
    let k = surface.normal_strength;
    let nx = vec3(tx.z, tx.y * k + ng.y, tx.x * k + ng.x);
    let ny = vec3(ty.x * k + ng.x, ty.z, ty.y * k + ng.z);
    let nz = vec3(tz.x * k + ng.x, tz.y * k + ng.y, tz.z);
    // Keep each projection on the geometric normal's side.
    let n = normalize(
        vec3(nx.x * sign(ng.x + 1e-4), nx.y, nx.z) * bw.x
        + vec3(ny.x, ny.y * sign(ng.y + 1e-4), ny.z) * bw.y
        + vec3(nz.x, nz.y, nz.z * sign(ng.z + 1e-4)) * bw.z);

    pbr_input.material.base_color = vec4(color, 1.0) * pbr_input.material.base_color;
    pbr_input.material.perceptual_roughness = clamp(rough, 0.05, 1.0);
    pbr_input.N = normalize(mix(ng, n, 0.9));
    pbr_input.material.base_color = alpha_discard(pbr_input.material, pbr_input.material.base_color);

#ifdef PREPASS_PIPELINE
    let out = deferred_output(in, pbr_input);
#else
    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr_input);
    out.color = main_pass_post_lighting_processing(pbr_input, out.color);
#endif
    return out;
}
