shader_type spatial;
render_mode unshaded;
// Unshaded: the original terrain is fixed-function-lit in GAMMA space —
// MODULATE(TEXTURE, DIFFUSE) with a terrain material of Ambient=0.7 /
// Diffuse=1.0. Godot's PBR/linear
// pipeline cannot reproduce that; we port the exact formula below instead.

uniform sampler2D tilemap : filter_nearest;
uniform sampler2D visibility_map : filter_nearest, hint_default_white;
uniform sampler2DArray tile_textures : filter_linear_mipmap, repeat_disable;
uniform int palette_count = 318;
uniform float tile_texel_inset = 0.00390625; // 0.5/128 — half-texel inset,
// replicating the original renderer's CLAMP sampler + half-texel
// inset. Prevents linear-filter bleeding across cell borders.

// D3D fixed-function sun (loaded from the per-map .plt).
// Direction is the D3D light direction converted to Godot (z negated).
// Defaults reproduce "no .plt": straight-down white sun that saturates
// the vertex diffuse to 1.0 (pure texture).
uniform vec3 sun_direction = vec3(0.0, -1.0, 0.0);
uniform vec3 sun_diffuse = vec3(1.0, 1.0, 1.0);
uniform vec3 sun_ambient = vec3(1.0, 1.0, 1.0);
const float MATERIAL_AMBIENT = 0.7; // the original terrain material's Ambient

// D3D fixed-function point lights (PointLightData in the .plt; slotted as
// standard D3D point lights). 15 = the original renderer's slot cap;
// map data maxes at 12. Positions are Godot-space.
// pl_params: x = max_range (light skipped beyond it), yzw = attenuation
// a0/a1/a2 with atten = 1/(a0 + a1*d + a2*d^2).
uniform int point_light_count = 0;
uniform vec3 pl_position[15];
uniform vec3 pl_diffuse[15];
uniform vec3 pl_ambient[15];
uniform vec4 pl_params[15];

// D3D FF lighting is per-VERTEX (Gouraud): compute the clamped vertex
// diffuse here and let the rasterizer interpolate the color, exactly as
// the fixed-function pipeline did. Fragment-side lighting would render
// point-light falloff visibly differently on the 1m terrain grid.
varying vec3 ff_diffuse;

vec3 srgb_decode(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
            greaterThan(c, vec3(0.04045)));
}

void vertex() {
    vec3 world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    // Terrain tile vertices carry a CONSTANT up normal (0,1,0) — the
    // original never shades slopes.
    vec3 n = vec3(0.0, 1.0, 0.0);

    // World ambient is black in the original; sun + point sums below.
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
    // Per-cell visibility: the original renderer gathers only cells flagged
    // visible into the tile vertex buffer.
    // Cells under props (track, buildings — 3,725 on SF001001)
    // are authored invisible; skipping them is what hides heightmap
    // artifacts like the 2m spike under the west track.
    if (texture(visibility_map, UV).r < 0.5) {
        discard;
    }

    vec2 rg = texture(tilemap, UV).rg;
    int combo_idx = int(round(rg.r * 255.0)) + int(round(rg.g * 255.0)) * 256;
    combo_idx = clamp(combo_idx, 0, palette_count - 1);

    vec2 grid_size = vec2(textureSize(tilemap, 0));
    vec2 cell_uv = fract(UV * grid_size);
    // V-flip is CORRECT, not a hack: original tile geometry assigns
    // v = 1 - frac(worldZ).
    // Corner masks: RU(0x01)->uv(1,0) LU(0x02)->(0,0) LD(0x04)->(0,1) RD(0x08)->(1,1).
    cell_uv.y = 1.0 - cell_uv.y;
    cell_uv = clamp(cell_uv, vec2(tile_texel_inset), vec2(1.0 - tile_texel_inset));

    // No `source_color` hint on tile_textures: the runtime-built
    // Texture2DArray is sampled RAW, i.e. these are the PNG's gamma-space
    // (sRGB) values — exactly what the original engine multiplied against.
    vec3 tex_srgb = texture(tile_textures, vec3(cell_uv, float(combo_idx))).rgb;

    // MODULATE(TEXTURE, interpolated vertex diffuse) in gamma space, then
    // srgb_decode once so the renderer's final linear->sRGB encode restores
    // the gamma-space result on screen.
    ALBEDO = srgb_decode(tex_srgb * ff_diffuse);
}
