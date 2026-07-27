shader_type spatial;
render_mode unshaded, blend_mix, cull_back, depth_draw_never;
// Port of the original client's beach shore-wave pass, drawn
// after the water surface with states inherited from it:
//   lighting off, alpha blend SRCALPHA/INVSRCALPHA, z-write OFF,
//   z-test on, cull restored to CCW backface culling — beach quads ARE
//   backface-culled, unlike the water surface.
// Stage 1's texture is unset, so the effective fragment is stage 0
// only: color = tex.rgb, alpha = tex.a * vertex.a. No modulate chain, so
// no gamma round-trip is needed — the sampler's source_color decode is
// exactly inverted by the renderer's final sRGB encode.

uniform sampler2D tex : source_color, filter_linear_mipmap, repeat_enable, hint_default_white;

void fragment() {
    vec4 t = texture(tex, UV);
    ALBEDO = t.rgb;
    ALPHA = t.a * COLOR.a;
}
