shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled, depth_draw_never;
// Particle/billboard quad for the .sfd effects (sub-project C2), alpha
// variant (DESTBLEND=INVSRCALPHA — non-additive effects; particles are
// sorted back-to-front by SfxObject before the instance buffer is filled).
// Original fixed-function pass: MODULATE(TEXTURE, DIFFUSE) for color AND
// alpha, SRCBLEND=SRCALPHA, lighting off, z-test on, z-write off, cull off
// — in GAMMA space.
//
// The atlas is a runtime ImageTexture with NO source_color hint, so
// texture() returns RAW sRGB values (terrain_tiles precedent) — modulate
// in gamma space, decode once for ALBEDO. Per-instance COLOR = the
// original's DIFFUSE vertex color (already 8-bit-truncated gamma values);
// INSTANCE_CUSTOM = this instance's atlas rect (u0, v0, su, sv).

uniform sampler2D atlas : filter_linear, repeat_disable;

varying vec4 v_rect;
varying vec4 v_color;

vec3 srgb_decode(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
            greaterThan(c, vec3(0.04045)));
}

void vertex() {
    v_rect = INSTANCE_CUSTOM;
    v_color = COLOR;
}

void fragment() {
    vec2 uv = v_rect.xy + UV * v_rect.zw;
    vec4 tex = texture(atlas, uv);
    ALBEDO = srgb_decode(clamp(tex.rgb * v_color.rgb, 0.0, 1.0));
    ALPHA = tex.a * v_color.a;
}
