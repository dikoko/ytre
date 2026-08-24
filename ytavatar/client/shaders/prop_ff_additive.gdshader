shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never;
// Additive full-bright pass for self-illuminated materials
// (fSelfIllumination > 0), applied at runtime by prop_lighting.gd.
//
// Original client path (self-illum meshes go through the alpha-mesh
// queue and get this dedicated pass):
//   all lights disabled, world ambient forced white
//     -> vertex diffuse = mat.Ambient (forced 0.7) * white = 0.7
//   MODULATE(TEXTURE, DIFFUSE), SRCBLEND=SRCALPHA, DESTBLEND=ONE,
//   CULLMODE=NONE, ZWRITEENABLE=FALSE (z-test stays on)
//   -> framebuffer += 0.7 * tex.rgb * tex.a   (gamma space)
// Godot's blend_add is src.rgb * src.a + dst in LINEAR space — the addition
// happens pre-encode rather than in gamma space, a documented approximation.

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, hint_default_white;
uniform vec4 albedo_factor : source_color = vec4(1.0);
const float MATERIAL_AMBIENT = 0.7; // the loader's forced material ambient
// Viewer-side taste knob (NOT a port): scales the additive contribution.
// Since the add is src*alpha, this both dims the glow and shrinks its
// apparent halo radius (the falloff drops below visibility sooner).
// prop_lighting.gd sets it < 1 for street-lamp glow quads (user feedback
// 2026-07-26: daylight lamp glows read as spotlights); 1.0 = faithful.
uniform float glow_scale : hint_range(0.0, 1.0) = 1.0;

vec3 srgb_encode(vec3 c) {
    return mix(c * 12.92, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055,
            greaterThan(c, vec3(0.0031308)));
}

vec3 srgb_decode(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
            greaterThan(c, vec3(0.04045)));
}

void fragment() {
    vec4 tex = texture(albedo_tex, UV) * albedo_factor;
    ALBEDO = srgb_decode(srgb_encode(tex.rgb) * MATERIAL_AMBIENT);
    ALPHA = tex.a * glow_scale;
}
