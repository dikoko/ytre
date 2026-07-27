shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled, depth_draw_always;
// Port of the original client's fixed-function water pass:
//   lighting OFF (vertex diffuse is BAKED in the .wtr mesh), alpha blend
//   SRCALPHA/INVSRCALPHA, cull none, z-write ON.
//   stage0: color = tex0, alpha = tex0.a * vertex.a
//   stage1: color = tex1 * current
//           alpha  = current * current   <- shipped quirk: ALPHAARG1 is set
//           twice (TEXTURE then CURRENT); with ARG2 defaulting to CURRENT
//           the final alpha is (tex0.a * vertex.a)^2 and tex1.a is unused.
//   Both stages sample UV SET 0 (stage1 TEXCOORDINDEX = PASSTHRU|0) with
//   independent animated texture matrices; sampler is WRAP.
// UV animation (t = accumulated seconds):
//   flowing (type 0): offset_i = -(t * a) wrapped
//   still   (type 1): offset_u = a0*cos(t*b0+c0) + d0*sin(t*e0+f0)  (radians:
//           the original's degree-based trig wrappers compose with its
//           rad-to-deg pre-convert to plain cos/sin of the radian argument)

uniform sampler2D tex_stage0 : source_color, filter_linear_mipmap, repeat_enable, hint_default_white;
uniform sampler2D tex_stage1 : source_color, filter_linear_mipmap, repeat_enable, hint_default_white;
uniform int anim_type = 1; // .wtr material anim type: 0 flowing, 1 still/harmonic
// MatInfo rows for stages 0 and 1 packed as 12 floats each:
// a0,a1,b0,b1,c0,c1,d0,d1,e0,e1,f0,f1
uniform float mat0[12];
uniform float mat1[12];

vec3 srgb_encode(vec3 c) {
    return mix(c * 12.92, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055,
            greaterThan(c, vec3(0.0031308)));
}

vec3 srgb_decode(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
            greaterThan(c, vec3(0.04045)));
}

vec2 stage_offset(float coeff[12], float t) {
    if (anim_type == 0) {
        return vec2(-fract(t * coeff[0]), -fract(t * coeff[1]));
    }
    float u = coeff[0] * cos(t * coeff[2] + coeff[4])
            + coeff[6] * sin(t * coeff[8] + coeff[10]);
    float v = coeff[1] * cos(t * coeff[3] + coeff[5])
            + coeff[7] * sin(t * coeff[9] + coeff[11]);
    return vec2(u, v);
}

void fragment() {
    vec4 t0 = texture(tex_stage0, UV + stage_offset(mat0, TIME));
    vec4 t1 = texture(tex_stage1, UV + stage_offset(mat1, TIME));
    // Gamma-space modulate chain, decoded once for the renderer's final
    // linear->sRGB encode (same convention as prop_ff/terrain shaders).
    ALBEDO = srgb_decode(srgb_encode(t0.rgb) * srgb_encode(t1.rgb));
    float a = t0.a * COLOR.a;
    ALPHA = a * a;
}
