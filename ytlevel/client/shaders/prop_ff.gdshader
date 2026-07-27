shader_type spatial;
render_mode unshaded, cull_back;
// Port of the original fixed-function prop lighting, applied at runtime by
// prop_lighting.gd in place of the GLB-imported StandardMaterial3D.
//
// Original path (D3D9 fixed function, GAMMA space, per-VERTEX/Gouraud):
//   stage0 default MODULATE(TEXTURE, vertex diffuse)
//   vertex diffuse = clamp(mat.Ambient * (sun.Ambient + sum pt.Ambient*atten)
//                        + mat.Diffuse * (sun.Diffuse*max(N.L,0)
//                                         + sum pt.Diffuse*max(N.Li,0)*atten))
//   world ambient is black; sun + point lights come
//   from the map .plt.
// EVERY prop material is force-set to Ambient=0.7 / Diffuse=1.0 by the
// original TMD loader (a default-on override;
// only the skydome opts out) — so the constants below apply to all props.
// Self-illuminated materials (fSelfIllumination > 0) render via
// prop_ff_additive.gdshader instead (lights off in that pass).

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, hint_default_white;
uniform vec4 albedo_factor : source_color = vec4(1.0);
uniform float alpha_scissor = -1.0; // < 0 disables the alpha test

uniform vec3 sun_direction = vec3(0.0, -1.0, 0.0);
uniform vec3 sun_diffuse = vec3(1.0, 1.0, 1.0);
uniform vec3 sun_ambient = vec3(1.0, 1.0, 1.0);
const float MATERIAL_AMBIENT = 0.7; // the loader's forced material ambient

// D3D fixed-function point lights (PointLightData in the .plt; slotted as
// standard D3D point lights). 15 = the original renderer's slot cap.
// pl_params: x = max_range (light skipped beyond it), yzw = attenuation
// a0/a1/a2 with atten = 1/(a0 + a1*d + a2*d^2). Positions are Godot-space.
uniform int point_light_count = 0;
uniform vec3 pl_position[15];
uniform vec3 pl_diffuse[15];
uniform vec3 pl_ambient[15];
uniform vec4 pl_params[15];

// Per-vertex (Gouraud) like the fixed-function pipeline; the rasterizer
// interpolates the clamped vertex color.
varying vec3 ff_diffuse;

vec3 srgb_encode(vec3 c) {
    return mix(c * 12.92, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055,
            greaterThan(c, vec3(0.0031308)));
}

vec3 srgb_decode(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
            greaterThan(c, vec3(0.04045)));
}

void vertex() {
    vec3 world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    vec3 n = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);

    vec3 amb = sun_ambient;
    vec3 diff = sun_diffuse * max(dot(n, -normalize(sun_direction)), 0.0);
    for (int i = 0; i < point_light_count; i++) {
        vec3 to_light = pl_position[i] - world_pos;
        float d = length(to_light);
        if (d > pl_params[i].x) {
            continue;
        }
        float atten = 1.0 / max(
                pl_params[i].y + pl_params[i].z * d + pl_params[i].w * d * d,
                1e-4);
        amb += pl_ambient[i] * atten;
        diff += pl_diffuse[i] * max(dot(n, to_light / max(d, 1e-6)), 0.0) * atten;
    }
    ff_diffuse = clamp(MATERIAL_AMBIENT * amb + diff, 0.0, 1.0);
}

void fragment() {
    vec4 tex = texture(albedo_tex, UV) * albedo_factor;
    // source_color gives linear values; the FF modulate happens in gamma
    // space, so re-encode, modulate, and decode once for ALBEDO (the
    // renderer's final encode then restores the gamma-space result).
    ALBEDO = srgb_decode(srgb_encode(tex.rgb) * ff_diffuse);
    if (alpha_scissor >= 0.0) {
        ALPHA = tex.a;
        ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
    }
}
