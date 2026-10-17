// Terrain splat: four PBR layers (grass, dirt, rock, sand) blended by the vertex color
// (r, g, b, a = weights), planar for the soft layers and triplanar for rock, with a
// macro sample to hide tiling. The lighting is Bevy's standard PBR.
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

struct Splat {
    // Tiles per metre for grass, dirt, rock, sand.
    scale: vec4<f32>,
    // Roughness of each layer.
    rough: vec4<f32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var grass_c: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(101) var grass_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(102) var grass_n: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(103) var grass_ns: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(104) var dirt_c: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(105) var dirt_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(106) var dirt_n: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(107) var dirt_ns: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(108) var rock_c: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(109) var rock_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(110) var rock_n: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(111) var rock_ns: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(112) var sand_c: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(113) var sand_s: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(114) var sand_n: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(115) var sand_ns: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(116) var<uniform> splat: Splat;

// A planar layer seen from above: detail tile mixed with a 1/19 scale macro tile.
fn planar_color(t: texture_2d<f32>, s: sampler, p: vec2<f32>, scale: f32) -> vec3<f32> {
    let detail = textureSample(t, s, p * scale).rgb;
    let macro_ = textureSample(t, s, p * scale / 19.0).rgb;
    return detail * mix(vec3(1.0), macro_ / max(vec3(0.05), vec3(0.5)), 0.45);
}

fn planar_normal(t: texture_2d<f32>, s: sampler, p: vec2<f32>, scale: f32) -> vec2<f32> {
    return textureSample(t, s, p * scale).xy * 2.0 - 1.0;
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);

    let p = in.world_position.xyz;
    let ng = normalize(in.world_normal);
#ifdef VERTEX_COLORS
    var w = in.color;
#else
    var w = vec4(1.0, 0.0, 0.0, 0.0);
#endif
    w = w / max(w.x + w.y + w.z + w.w, 1e-3);

    // Soft layers, planar from above.
    var color = planar_color(grass_c, grass_s, p.xz, splat.scale.x) * w.x
        + planar_color(dirt_c, dirt_s, p.xz, splat.scale.y) * w.y
        + planar_color(sand_c, sand_s, p.xz, splat.scale.w) * w.w;
    var n2 = planar_normal(grass_n, grass_ns, p.xz, splat.scale.x) * w.x
        + planar_normal(dirt_n, dirt_ns, p.xz, splat.scale.y) * w.y
        + planar_normal(sand_n, sand_ns, p.xz, splat.scale.w) * w.w;
    var normal = normalize(ng + vec3(n2.x, 0.0, n2.y) * 0.8);

    // Rock, triplanar.
    if w.z > 0.001 {
        var bw = abs(ng);
        bw = bw * bw * bw * bw;
        bw = bw / (bw.x + bw.y + bw.z);
        let rs = splat.scale.z;
        let cx = textureSample(rock_c, rock_s, p.zy * rs).rgb;
        let cy = textureSample(rock_c, rock_s, p.xz * rs).rgb;
        let cz = textureSample(rock_c, rock_s, p.xy * rs).rgb;
        let rock = cx * bw.x + cy * bw.y + cz * bw.z;
        let tx = textureSample(rock_n, rock_ns, p.zy * rs).xyz * 2.0 - 1.0;
        let ty = textureSample(rock_n, rock_ns, p.xz * rs).xyz * 2.0 - 1.0;
        let tz = textureSample(rock_n, rock_ns, p.xy * rs).xyz * 2.0 - 1.0;
        // UDN blend of the three projections.
        let nx = vec3(tx.z, tx.y + ng.y, tx.x + ng.x);
        let ny = vec3(ty.x + ng.x, ty.z, ty.y + ng.z);
        let nz = vec3(tz.x + ng.x, tz.y + ng.y, tz.z);
        var rn = normalize(nx * bw.x + ny * bw.y + nz * bw.z);
        rn = normalize(vec3(rn.x, abs(rn.y) * sign(ng.y + 1e-3), rn.z) * vec3(1.0) + ng * 0.3);
        color = color + rock * w.z;
        normal = normalize(mix(normal, rn, w.z));
    }

    pbr_input.material.base_color = vec4(color, 1.0);
    pbr_input.material.perceptual_roughness = dot(splat.rough, w);
    pbr_input.N = normal;
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
