extends Node3D
## Replaces GLB-imported StandardMaterial3D on all prop surfaces with the
## fixed-function port shader (prop_ff.gdshader), reproducing the original
## engine's gamma-space MODULATE lighting. Sun values come from node
## metadata written by 30_export_map.py (parsed from the map's .plt).

const FF_SHADER_PATH := "res://shaders/prop_ff.gdshader"
const FF_ADDITIVE_SHADER_PATH := "res://shaders/prop_ff_additive.gdshader"

## Viewer-side dim for street-lamp glow quads (every lamp model carries
## "lamp" in its name, e.g. a_SWElamp01). The authored sfx glows render
## additively at full strength day and night; at 1.0 they read as
## spotlights in daylight (SF002001 report, 2026-07-26). Scales the
## additive src*alpha, so it dims AND shrinks the visible halo.
const LAMP_GLOW_SCALE := 0.4

var _ff_shader: Shader
var _ff_shader_twosided: Shader
var _ff_shader_additive: Shader
var _converted: Dictionary = {}  # source material RID -> ShaderMaterial


func _ready() -> void:
	_ff_shader = load(FF_SHADER_PATH) as Shader
	if _ff_shader == null:
		push_warning("prop_lighting: shader not found at %s" % FF_SHADER_PATH)
		return
	# cull mode is a render_mode, not a uniform — derive a two-sided variant
	_ff_shader_twosided = Shader.new()
	_ff_shader_twosided.code = _ff_shader.code.replace(
			"render_mode unshaded, cull_back;",
			"render_mode unshaded, cull_disabled;")
	_ff_shader_additive = load(FF_ADDITIVE_SHADER_PATH) as Shader
	if _ff_shader_additive == null:
		push_warning("prop_lighting: shader not found at %s" % FF_ADDITIVE_SHADER_PATH)
		return

	var sun_direction: Vector3 = get_meta("sun_direction", Vector3(0, -1, 0))
	var sun_diffuse: Color = get_meta("sun_diffuse", Color(1, 1, 1))
	var sun_ambient: Color = get_meta("sun_ambient", Color(1, 1, 1))

	var swapped := 0
	for node in find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null:
			continue
		var is_lamp := _owning_prop_name(mi).containsn("lamp")
		for s in range(mi.mesh.get_surface_count()):
			var src := mi.get_active_material(s)
			if src is StandardMaterial3D:
				mi.set_surface_override_material(
						s, _ff_material(src, sun_direction, sun_diffuse, sun_ambient, is_lamp))
				swapped += 1
	print("prop_lighting: swapped %d surfaces to fixed-function materials" % swapped)

	# Animation runs AFTER the material swap — prop_animator binds uniforms on
	# the ShaderMaterials created above, which do not exist until now.
	# `anim_disabled` meta is the eval harness's A-side switch: lighting only,
	# which is exactly the pre-animation (origin/main) look.
	if get_meta("anim_disabled", false):
		return
	var animator := PropAnimator.new()
	animator.name = "PropAnimator"
	add_child(animator)
	animator.build(self)


func _owning_prop_name(node: Node) -> String:
	# Name of the direct child of this Props node the mesh belongs to
	# (e.g. obj_a_SWElamp01_57).
	var n := node
	while n != null and n.get_parent() != self:
		n = n.get_parent()
	return n.name if n != null else ""


func _ff_material(src: StandardMaterial3D, sun_direction: Vector3,
		sun_diffuse: Color, sun_ambient: Color, is_lamp: bool = false) -> ShaderMaterial:
	# Lamp-ness changes the additive glow_scale, so cache per (material, lamp).
	var key := "%d|%d" % [src.get_rid().get_id(), int(is_lamp)]
	if _converted.has(key):
		return _converted[key]

	# Self-illuminated materials (exported as emissiveFactor from the TMD's
	# self-illumination field) render additively full-bright in the original
	# client — their ONLY pass. No sun involved.
	# NOTE: Godot's GLTF importer sets emission_enabled=true on EVERY
	# material — only a non-black emission color marks real self-illum.
	var self_illum: bool = src.emission.get_luminance() > 0.0
	if self_illum:
		var add_mat := ShaderMaterial.new()
		add_mat.shader = _ff_shader_additive
		if src.albedo_texture != null:
			add_mat.set_shader_parameter("albedo_tex", src.albedo_texture)
		add_mat.set_shader_parameter("albedo_factor", src.albedo_color)
		if is_lamp:
			add_mat.set_shader_parameter("glow_scale", LAMP_GLOW_SCALE)
		_converted[key] = add_mat
		return add_mat

	var two_sided := src.cull_mode == BaseMaterial3D.CULL_DISABLED
	var mat := ShaderMaterial.new()
	mat.shader = _ff_shader_twosided if two_sided else _ff_shader
	if src.albedo_texture != null:
		mat.set_shader_parameter("albedo_tex", src.albedo_texture)
	mat.set_shader_parameter("albedo_factor", src.albedo_color)
	if src.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
		mat.set_shader_parameter("alpha_scissor", src.alpha_scissor_threshold)
	mat.set_shader_parameter("sun_direction", sun_direction)
	mat.set_shader_parameter("sun_diffuse",
			Vector3(sun_diffuse.r, sun_diffuse.g, sun_diffuse.b))
	mat.set_shader_parameter("sun_ambient",
			Vector3(sun_ambient.r, sun_ambient.g, sun_ambient.b))
	PointLights.apply(self, mat)
	_converted[key] = mat
	return mat
