extends SceneTree
## Camera-occlusion eval: pixel-measured scenario checks on SF001001.
## Run WINDOWED (viewport capture needs a real window):
##   "$GODOT_BIN" --path client --script scripts/tests/occl_eval.gd --position 4000,4000
##
## Scenarios:
##  1. front_of_school — the 2026-08-10 report: avatar + camera on the plaza in
##     front of s_SEmain, INSIDE its AABB but with no geometry between them.
##     The school must NOT fade (AABB-only logic fades it; only a mesh-accurate
##     narrow phase passes).
##  2. through_school — camera south of the building, avatar north: real
##     geometry blocks the sightline. Must fade to a GHOST, not vanish:
##     measured as 0 < |on-off| << |off-hidden| within the prop's screen rect.
##  3. through_tree — same, through a masked-foliage tree: the alpha-scissor
##     regression detector (a scissor write in the occ variant discards every
##     masked pixel, which reads as the prop vanishing outright).

const SHOT_DIR := "res://../reports/occl_eval"
## Two independent conditions on the region diffs (a=off, b=on, c=hidden):
## the ghost FADED (|a-b| is a real fraction of the full |a-c| swing) and it
## is STILL VISIBLE (|b-c| nonzero — vanishing makes b == c). A no-op fails
## the first; the alpha-scissor discard bug fails the second.
const FADE_MIN := 0.15
const VISIBLE_MIN := 0.08
## Max mean inter-frame diff inside the prop rect while everything is
## static — the flicker detector (a bit-stable render measures 0.0; the
## allowance is for TIME-driven shaders that may clip the rect).
const IDLE_MAX := 0.003

var _fails := 0


func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	var tool: Node = (load("res://scenes/level_tool.tscn") as PackedScene).instantiate()
	root.add_child(tool)
	await process_frame
	tool.load_level("SF001001")
	for i in 40:
		await process_frame
	tool._toggle_run()
	for i in 20:
		await process_frame
	var runner: AvatarRunner = tool.runner
	runner.set_process(false)
	var occ: CameraOcclusion = tool.occlusion
	var cam: Camera3D = tool._camera

	var school := _find_mesh(occ, "SEmain")
	var tree := _find_mesh(occ, "tree")
	_check(school != null, "found school mesh")
	_check(tree != null, "found a tree mesh")

	# --- Scenario 1: reported spot, no geometry between camera and avatar ---
	var spot := Vector3(75.4, 0.0, -106.5)
	_place(runner, cam, spot, spot + Vector3(-1.5, 2.2, 6.0))
	occ._update_targets()
	var faded_names: Array = []
	for mi in occ._fading:
		faded_names.append(mi.name)
	_check(occ._fading.is_empty(),
			"front_of_school: nothing fades (faded=%s)" % [faded_names])
	_settle(occ)
	await _shot("1_front_of_school")

	# --- Scenario 2: sightline through the school building ---
	if school != null:
		await _ghost_scenario(occ, runner, cam, school, "2_through_school")

	# --- Scenario 3: sightline through a masked-foliage tree ---
	if tree != null:
		await _ghost_scenario(occ, runner, cam, tree, "3_through_tree")

	print("OCCL EVAL FAILED: %d" % _fails if _fails else "OCCL EVAL ALL OK")
	quit(1 if _fails else 0)


func _ghost_scenario(occ: CameraOcclusion, runner: AvatarRunner, cam: Camera3D,
		mi: MeshInstance3D, label: String) -> void:
	var aabb: AABB = mi.global_transform * mi.mesh.get_aabb()
	var c := aabb.get_center()
	# Camera south of the prop at mid-height, avatar just past the north face:
	# the segment passes through the prop's actual geometry.
	var avatar_pos := Vector3(c.x, 0.0, c.z - aabb.size.z * 0.5 - 1.5)
	var cam_pos := Vector3(c.x, c.y + aabb.size.y * 0.1,
			c.z + aabb.size.z * 0.5 + maxf(6.0, aabb.size.z * 0.3))
	_place(runner, cam, avatar_pos, cam_pos)

	# A: occlusion off.
	occ.set_active(false)
	await _frames(3)
	var shot_a := await _shot("%s_a_off" % label)
	# B: occlusion on, alpha forced to target (no animation wait — keeps the
	# A/B/C captures close in time so water/TIME drift stays in the noise).
	occ.set_active(true)
	occ._update_targets()
	_check(occ._fading.has(mi), "%s: prop fades when geometry blocks" % label)
	# Everything that faded participates in the C reference: in dense areas
	# (a grove) hiding only the target mesh proves nothing — the other
	# faded trees fill the same pixels.
	var faded_mis: Array = occ._fading.keys()
	_settle(occ)
	await _frames(3)
	var shot_b := await _shot("%s_b_on" % label)
	# C: every faded prop hidden entirely (the "vanished" reference).
	occ.set_active(false)
	await _frames(1)
	for f in faded_mis:
		f.visible = false
	await _frames(3)
	var shot_c := await _shot("%s_c_hidden" % label)
	for f in faded_mis:
		f.visible = true

	var rect := _screen_rect(cam, aabb)
	var d_ab := _region_diff(shot_a, shot_b, rect)
	var d_ac := _region_diff(shot_a, shot_c, rect)
	var d_bc := _region_diff(shot_b, shot_c, rect)
	if d_ac < 1e-4:
		_check(false, "%s: hidden reference shows no change (bad rect?)" % label)
		return
	_check(d_ab / d_ac >= FADE_MIN,
			"%s: ghost faded (%.3f >= %.2f; ab=%.4f ac=%.4f)"
			% [label, d_ab / d_ac, FADE_MIN, d_ab, d_ac])
	_check(d_bc / d_ac >= VISIBLE_MIN,
			"%s: ghost still visible (%.3f >= %.2f; bc=%.4f ac=%.4f)"
			% [label, d_bc / d_ac, VISIBLE_MIN, d_bc, d_ac])

	# Idle stability: with everything static and the ghost active, consecutive
	# frames must not differ inside the prop's rect — the 2026-08-11 "walls
	# flicker on and off" detector. (Avatar hidden: its idle anim moves.)
	occ.set_active(true)
	occ._update_targets()
	_settle(occ)
	if runner._avatar != null:
		runner._avatar.visible = false
	await _frames(3)
	var prev: Image = null
	var worst := 0.0
	for f in 8:
		await _frames(1)
		var img := root.get_viewport().get_texture().get_image()
		if prev != null:
			worst = maxf(worst, _region_diff(prev, img, rect))
		prev = img
	if runner._avatar != null:
		runner._avatar.visible = true
	occ.set_active(false)
	_check(worst <= IDLE_MAX,
			"%s: idle frames stable (worst %.5f <= %.4f)" % [label, worst, IDLE_MAX])


func _place(runner: AvatarRunner, cam: Camera3D, avatar_pos: Vector3,
		cam_pos: Vector3) -> void:
	avatar_pos.y = runner.ground_height(avatar_pos.x, avatar_pos.z)
	if is_nan(avatar_pos.y):
		avatar_pos.y = 0.0
	runner.avatar_position = avatar_pos
	if runner._avatar != null:
		runner._avatar.position = avatar_pos
	cam.global_position = cam_pos
	cam.look_at(avatar_pos + Vector3(0, 1.0, 0))


func _settle(occ: CameraOcclusion) -> void:
	# Force every fade to its target instantly — deterministic captures.
	for mi in occ._fading:
		var entry: Dictionary = occ._fading[mi]
		entry["alpha"] = entry["target"]
		for mat in entry["mats"]:
			(mat as ShaderMaterial).set_shader_parameter("occ_alpha", entry["alpha"])


func _find_mesh(occ: CameraOcclusion, needle: String) -> MeshInstance3D:
	for entry in occ._index:
		var mi: MeshInstance3D = entry["mi"]
		if str(mi.get_path()).containsn(needle):
			return mi
	return null


func _screen_rect(cam: Camera3D, aabb: AABB) -> Rect2i:
	var vp := root.get_visible_rect().size
	var lo := Vector2.INF
	var hi := -Vector2.INF
	for i in 8:
		var corner := aabb.position + Vector3(
				aabb.size.x * float(i & 1),
				aabb.size.y * float((i >> 1) & 1),
				aabb.size.z * float((i >> 2) & 1))
		if cam.is_position_behind(corner):
			continue
		var p := cam.unproject_position(corner)
		lo = lo.min(p)
		hi = hi.max(p)
	lo = lo.clamp(Vector2.ZERO, vp)
	hi = hi.clamp(Vector2.ZERO, vp)
	return Rect2i(Vector2i(lo), Vector2i(hi - lo))


func _region_diff(a: Image, b: Image, rect: Rect2i) -> float:
	## Mean |a-b| over the rect, RGB, 0..1. Sampled on a grid for speed.
	var total := 0.0
	var n := 0
	var step := maxi(1, mini(rect.size.x, rect.size.y) / 200)
	for y in range(rect.position.y, rect.end.y, step):
		for x in range(rect.position.x, rect.end.x, step):
			var ca := a.get_pixel(x, y)
			var cb := b.get_pixel(x, y)
			total += absf(ca.r - cb.r) + absf(ca.g - cb.g) + absf(ca.b - cb.b)
			n += 1
	return total / (3.0 * maxf(1.0, float(n)))


func _check(cond: bool, label: String) -> void:
	if not cond:
		printerr("FAIL: " + label)
		_fails += 1
	else:
		print("ok: " + label)


func _frames(n: int) -> void:
	for i in n:
		await process_frame


func _shot(name: String) -> Image:
	await process_frame
	await process_frame
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/%s.png" % [SHOT_DIR, name]))
	return img
