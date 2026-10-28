// Comic halftone for UI nodes: round dots of `dot` colour on `fill`, `params.x` px apart with
// radius `params.y`, the grid turned by `params.z` radians, and with `params.w` > 0 only towards
// the edges. Edges are smoothed over 1.5 px.
#import bevy_ui::ui_vertex_output::UiVertexOutput

struct Halftone {
    fill: vec4<f32>,
    dot: vec4<f32>,
    params: vec4<f32>,
}

@group(1) @binding(0) var<uniform> material: Halftone;

@fragment
fn fragment(in: UiVertexOutput) -> @location(0) vec4<f32> {
    let c = cos(material.params.z);
    let s = sin(material.params.z);
    let p = in.uv * in.size;
    let q = vec2<f32>(c * p.x - s * p.y, s * p.x + c * p.y);
    let pitch = max(material.params.x, 1.0);
    let d = length(fract(q / pitch) - 0.5) * pitch;
    let r = material.params.y;
    // Dots composite over the fill by their own alpha; the node keeps the fill's alpha.
    var cover = material.dot.a * (1.0 - smoothstep(r - 0.75, r + 0.75, d));
    // params.w > 0: a vignette, dots only towards the edges (the HUD's hit flash).
    if material.params.w > 0.0 {
        cover *= smoothstep(0.55, 0.85, length(in.uv - 0.5) * 2.0);
    }
    // Dots stay solid over a see-through fill.
    return vec4<f32>(mix(material.fill.rgb, material.dot.rgb, cover), max(material.fill.a, cover));
}
