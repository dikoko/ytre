class_name PropAnimator
extends Node
## Drives the keyframe animation exported into prop GLBs, plus the alpha
## fade curves carried in each prop's {prop}.anim.json sidecar.
##
## Spawned by prop_lighting.gd at the END of its _ready(), so it always runs
## after the StandardMaterial3D -> ShaderMaterial swap. Binding uniforms
## before that swap would target materials about to be discarded.

## Stagger identical props so a row of them does not flicker in lockstep.
## NOT a port — the original had no phase offset. Off by default.
@export var phase_offset := false

var _sidecars: Dictionary = {}      # glb path -> parsed sidecar (per-prop, not per-placement)
var _fades: Array = []              # [{mats, curve, player, fps}]
var _fade_shaders: Dictionary = {}  # source shader RID -> fade variant Shader


func build(props_root: Node3D) -> void:
	var looping := 0
	var held := 0
	var index := 0
	for child in props_root.get_children():
		var sidecar := _sidecar_for(child)
		if sidecar.is_empty():
			continue
		var player := _find_player(child)
		if player == null:
			continue
		var names := player.get_animation_list()
		var clip_name := "default" if player.has_animation("default") \
				else (names[0] if names.size() > 0 else "")
		if clip_name.is_empty():
			continue
		var clips: Dictionary = sidecar.get("clips", {})
		var has_ranges := false
		for k in clips.keys():
			if String(k) != "default":
				has_ranges = true
		var anim := player.get_animation(clip_name)
		if has_ranges:
			# Ranges are a state machine driven by game logic the viewer does
			# not run (day/night, doors, triggers). Until a range is selected
			# the original holds such objects at frame 0 — force-looping the
			# whole timeline would play every state back to back (a street
			# lamp cycling off->on->off in daylight). Hold the idle pose; the
			# fade curves still apply at the held frame via _process.
			if anim != null:
				anim.loop_mode = Animation.LOOP_NONE
			player.play(clip_name)
			player.seek(0.0, true)
			player.pause()
			held += 1
		else:
			# No ANIMATION property -> the whole timeline force-loops.
			# `anim_one_shot` meta (warp_effects.gd) overrides: play the
			# timeline once — the owner frees the node on animation_finished.
			var one_shot: bool = props_root.get_meta("anim_one_shot", false)
			if anim != null:
				anim.loop_mode = Animation.LOOP_NONE if one_shot \
						else Animation.LOOP_LINEAR
			player.play(clip_name)
			if phase_offset and not one_shot and anim != null and anim.length > 0.0:
				player.seek(fmod(float(index) * 0.37, anim.length), true)
			looping += 1
		_register_fades(child, sidecar, player)
		index += 1
	print("prop_animator: %d looping, %d held at idle, %d fade curves"
			% [looping, held, _fades.size()])


func set_day_night(is_day: bool) -> void:
	## Placeholder until the day/night range tables are ported: which authored
	## range means "day" vs "night" is map logic, not prop data. Day holds the
	## idle pose; night loops the full timeline.
	for entry in _fades:
		var player: AnimationPlayer = entry["player"]
		if player == null or player.current_animation == "":
			continue
		var anim := player.get_animation(player.current_animation)
		if anim == null:
			continue
		if is_day:
			anim.loop_mode = Animation.LOOP_NONE
			player.seek(0.0, true)
			player.pause()
		else:
			anim.loop_mode = Animation.LOOP_LINEAR
			player.play(player.current_animation)


func _find_player(node: Node) -> AnimationPlayer:
	for c in node.find_children("*", "AnimationPlayer", true, false):
		return c as AnimationPlayer
	return null


func _sidecar_for(placement: Node) -> Dictionary:
	## Resolve the sidecar from the placement's OWN scene path.
	##
	## Not by prop id + a category search order: 23 prop ids ship in two
	## categories, and three of those (c_SWGchair02A_b01/_b02, c_SWGchair05A_b)
	## are animated in one and static in the other with different bytes. A
	## first-match-wins category walk would hand a placement the wrong prop's
	## clip table. scene_file_path is exactly the GLB this node instantiates.
	var scene_path := placement.scene_file_path
	if scene_path.is_empty() or not scene_path.ends_with(".glb"):
		return {}
	if _sidecars.has(scene_path):
		return _sidecars[scene_path]
	var path := scene_path.substr(0, scene_path.length() - 4) + ".anim.json"
	var found := {}
	if FileAccess.file_exists(path):
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Dictionary:
			found = parsed
	_sidecars[scene_path] = found
	return found


func _register_fades(placement: Node, sidecar: Dictionary,
		player: AnimationPlayer) -> void:
	var curves: Dictionary = sidecar.get("visibility", {})
	if curves.is_empty():
		return
	var fps: float = float(sidecar.get("fps", 30.0))
	for node_name in curves.keys():
		var target := placement.find_child(String(node_name), true, false)
		if target == null:
			continue
		var candidates := _meshes_owned_by(target)
		var mats: Array = []
		for mi_node in candidates:
			var m := mi_node as MeshInstance3D
			if m == null or m.mesh == null:
				continue
			for s in range(m.mesh.get_surface_count()):
				var src := m.get_active_material(s) as ShaderMaterial
				if src == null:
					continue
				var faded: ShaderMaterial = src.duplicate()
				faded.shader = _fade_variant(src.shader)
				faded.set_shader_parameter("anim_alpha", 1.0)
				m.set_surface_override_material(s, faded)
				mats.append(faded)
		if mats.is_empty():
			continue
		_fades.append({
			"mats": mats,
			"curve": curves[node_name],
			"player": player,
			"fps": fps,
		})


func _meshes_owned_by(node: Node) -> Array:
	## Meshes this animated node fades — itself plus descendants, but NOT
	## those belonging to a nested animated object.
	##
	## The animated node usually IS the MeshInstance3D; only the scale-axis
	## factor chain puts the mesh on a descendant. Nested animated objects
	## hang under their own `*_pivot`, so that name ends the walk: without it
	## a parent's curve claims its children's surfaces, they get faded twice,
	## and the second pass tries to derive a fade variant OF a fade variant
	## ("Redefinition of 'anim_alpha'").
	var out: Array = []
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		if String(child.name).ends_with("_pivot"):
			continue
		out.append_array(_meshes_owned_by(child))
	return out


func _fade_variant(src: Shader) -> Shader:
	## Derive an alpha-carrying variant of a prop shader.
	##
	## Adding the uniform to prop_ff.gdshader directly would make EVERY prop
	## material write ALPHA and land in the transparent pass; only the ~3% of
	## surfaces that actually fade should pay that cost.
	var key := src.get_rid().get_id()
	if _fade_shaders.has(key):
		return _fade_shaders[key]
	var code := src.code
	if code.contains("uniform float anim_alpha"):
		return src   # already a fade variant — deriving again would redefine it
	var variant := Shader.new()
	code = code.replace("shader_type spatial;",
			"shader_type spatial;\nuniform float anim_alpha : hint_range(0.0, 1.0) = 1.0;")
	if code.contains("blend_add"):
		# Additive pass (prop_ff_additive): ALPHA is already written and
		# scales the added contribution — multiply the fade in so glow_scale
		# survives. PITFALL: never write ALPHA_SCISSOR_THRESHOLD here — any
		# scissor write moves the material to the opaque pass, the blend_add
		# is lost, and the glow geometry renders as an opaque dark crystal
		# (the 2026-08-08 street-lamp regression, round two).
		var idx := code.rfind("}")
		code = code.substr(0, idx) + "\tALPHA *= anim_alpha;\n" + code.substr(idx)
	else:
		# Opaque FF pass: keep z-write while fading so the prop does not
		# reveal its own backfaces mid-dissolve, and append the alpha write.
		code = code.replace("render_mode unshaded, cull_back;",
				"render_mode unshaded, cull_back, depth_draw_opaque;")
		code = code.replace("render_mode unshaded, cull_disabled;",
				"render_mode unshaded, cull_disabled, depth_draw_opaque;")
		var idx := code.rfind("}")
		code = code.substr(0, idx) + "\tALPHA = tex.a * anim_alpha;\n" + code.substr(idx)
	variant.code = code
	_fade_shaders[key] = variant
	return variant


func _process(_delta: float) -> void:
	for entry in _fades:
		var player: AnimationPlayer = entry["player"]
		# Held (paused) props still need their curve applied at the held
		# frame — is_playing() is false there but the position is valid.
		if player == null or player.current_animation == "":
			continue
		var frame: float = player.current_animation_position * float(entry["fps"])
		var alpha := _sample_curve(entry["curve"], frame)
		for mat in entry["mats"]:
			(mat as ShaderMaterial).set_shader_parameter("anim_alpha", alpha)


func _sample_curve(curve: Array, frame: float) -> float:
	## Linear sample: a single key is constant; outside the authored range
	## the endpoints clamp.
	if curve.is_empty():
		return 1.0
	if curve.size() == 1:
		return float(curve[0][1])
	if frame <= float(curve[0][0]):
		return float(curve[0][1])
	var last: int = curve.size() - 1
	if frame >= float(curve[last][0]):
		return float(curve[last][1])
	for i in range(last):
		var f0 := float(curve[i][0])
		var f1 := float(curve[i + 1][0])
		if frame < f0 or frame > f1:
			continue
		if f1 - f0 <= 0.0:
			return float(curve[i][1])
		var t := (frame - f0) / (f1 - f0)
		return lerpf(float(curve[i][1]), float(curve[i + 1][1]), t)
	return 1.0
