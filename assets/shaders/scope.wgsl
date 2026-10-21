// Sight pictures (src/scope.rs). A scope's eyepiece shows the scope camera's magnified picture with
// its reticle, dark at the rim and as the eye leaves the scope's axis (the exit pupil), and dark glass
// while the scope camera is off. A red dot's window draws the dot where the view ray meets the sight
// line at infinity, so it stays on target while the gun sways.
#import bevy_pbr::{forward_io::VertexOutput, mesh_view_bindings::view}
#ifdef TONEMAP_IN_SHADER
#import bevy_core_pipeline::tonemapping::tone_mapping
#endif

struct Lens {
    // Reticle (1 mil-dot, 2 chevron, 3 red dot), aim level (0: camera off), the eye's offset from
    // the axis in lens radii.
    a: vec4<f32>,
    // The sight line in world space, the dot's radius in radians.
    b: vec4<f32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(0) var<uniform> lens: Lens;
@group(#{MATERIAL_BIND_GROUP}) @binding(1) var picture: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(2) var picture_sampler: sampler;

fn finish(c: vec4<f32>) -> vec4<f32> {
#ifdef TONEMAP_IN_SHADER
    return tone_mapping(c, view.color_grading);
#else
    return c;
#endif
}

// 1 inside a stroke `d` from its centre line, `w` wide, softened over a pixel.
fn stroke(d: f32, w: f32, px: f32) -> f32 {
    return 1.0 - smoothstep(w - px, w + px, d);
}

fn segment(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let ab = b - a;
    let t = clamp(dot(p - a, ab) / dot(ab, ab), 0.0, 1.0);
    return length(p - a - ab * t);
}

// Mil-dot crosshair: fine lines, heavy posts toward the rim, a dot every tenth of the radius.
fn mil_dot(p: vec2<f32>, px: f32) -> f32 {
    let q = abs(p);
    var ink = max(stroke(q.y, select(0.004, 0.02, q.x > 0.6), px), stroke(q.x, select(0.004, 0.02, q.y > 0.6), px));
    for (var i = 1; i <= 5; i++) {
        let d = f32(i) * 0.1;
        ink = max(ink, max(stroke(length(vec2(q.x - d, q.y)), 0.011, px), stroke(length(vec2(q.x, q.y - d)), 0.011, px)));
    }
    return ink;
}

// The 3x's lit chevron, its tip on the aim point.
fn chevron(p: vec2<f32>, px: f32) -> f32 {
    let d = min(segment(p, vec2(0.0), vec2(-0.07, -0.08)), segment(p, vec2(0.0), vec2(0.07, -0.08)));
    return stroke(d, 0.008, px);
}

// The 3x's black stadia: side bars and a post from below.
fn stadia(p: vec2<f32>, px: f32) -> f32 {
    let q = abs(p);
    let side = stroke(q.y, 0.005, px) * step(0.3, q.x);
    let post = stroke(q.x, 0.006, px) * step(0.25, -p.y);
    return max(side, post);
}

@fragment
fn fragment(in: VertexOutput) -> @location(0) vec4<f32> {
    let kind = u32(lens.a.x + 0.5);
    if kind == 3u {
        let ray = normalize(in.world_position.xyz - view.world_position.xyz);
        let fwd = normalize(lens.b.xyz);
        let off = select(1.0, length(cross(ray, fwd)), dot(ray, fwd) > 0.0);
        let r = lens.b.w;
        let core = 1.0 - smoothstep(r * 0.5, r, off);
        let glow = (1.0 - smoothstep(r, r * 3.0, off)) * 0.3;
        let glass = vec3(0.02, 0.03, 0.025);
        let col = vec3(1.0, 0.06, 0.03) * 2.5 * (core + glow) + glass * 0.05;
        return finish(vec4(col, clamp(core + glow, 0.05, 1.0)));
    }

    let p = vec2(in.uv.x * 2.0 - 1.0, 1.0 - in.uv.y * 2.0);
    let px = max(fwidth(p.x), 1e-4);
    let level = lens.a.y;
    let rim = 1.0 - smoothstep(0.88, 1.0, length(p));
    if level <= 0.0 {
        // Off: coated glass, near black, with a soft sheen up and left.
        let sheen = 0.004 * (1.0 - smoothstep(0.0, 0.7, length(p - vec2(-0.35, 0.35))));
        return finish(vec4(vec3(0.0015, 0.002, 0.003) + vec3(sheen), 1.0));
    }
    let eye = lens.a.zw;
    let pupil = 1.0 - smoothstep(0.5, 0.95, length(p + eye * 1.6));
    let shade = rim * pupil * smoothstep(0.35, 1.0, level);
    let uv = vec2(0.5 + p.x * 0.5, 0.5 - p.y * 0.5) - vec2(eye.x, -eye.y) * 0.04;
    var col = textureSample(picture, picture_sampler, uv).rgb * shade;
    if kind == 1u {
        col = mix(col, vec3(0.0), mil_dot(p, px));
    } else {
        col = mix(col, vec3(0.0), stadia(p, px));
        col = col + vec3(1.0, 0.22, 0.04) * 1.5 * chevron(p, px) * shade;
    }
    return finish(vec4(col, 1.0));
}
