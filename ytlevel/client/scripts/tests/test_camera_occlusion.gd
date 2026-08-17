extends SceneTree
## Run: GODOT_BIN --headless --path client --script scripts/tests/test_camera_occlusion.gd

var _fails := 0


func _init() -> void:
	await process_frame   # nodes added below need a live tree
	# --- _segment_crossing: slab-method overlap length (broad phase) ---
	var box := AABB(Vector3(-1, 0, -1), Vector3(2, 2, 2))  # x/z -1..1, y 0..2

	# Straight through the middle: crossing == box depth.
	var c := CameraOcclusion._segment_crossing(box, Vector3(0, 1, -5), Vector3(0, 1, 5))
	_check(absf(c - 2.0) < 1e-5, "through-crossing is the box depth (%f)" % c)

	# Miss entirely.
	c = CameraOcclusion._segment_crossing(box, Vector3(5, 1, -5), Vector3(5, 1, 5))
	_check(c == 0.0, "parallel miss is zero")

	# Segment ends before the box.
	c = CameraOcclusion._segment_crossing(box, Vector3(0, 1, -5), Vector3(0, 1, -2))
	_check(c == 0.0, "segment stopping short is zero")

	# Segment starting INSIDE the box (avatar under an archway).
	c = CameraOcclusion._segment_crossing(box, Vector3(0, 1, 0), Vector3(0, 1, 5))
	_check(absf(c - 1.0) < 1e-5, "inside-out crossing measured from start (%f)" % c)

	# Degenerate axis: segment lying in a plane crossing the box.
	c = CameraOcclusion._segment_crossing(box, Vector3(-5, 1, 0), Vector3(5, 1, 0))
	_check(absf(c - 2.0) < 1e-5, "axis-aligned crossing (%f)" % c)

	# --- target selection: narrow phase + knee-height exclusion ---
	var occ := CameraOcclusion.new()
	var runner := AvatarRunner.new()
	runner.active = true
	runner.avatar_position = Vector3(0, 10, 0)
	var cam := Camera3D.new()
	root.add_child(runner)
	root.add_child(cam)
	root.add_child(occ)
	cam.global_position = Vector3(0, 11.5, 6)
	occ.setup(cam, runner)

	var props := Node3D.new()
	root.add_child(props)
	var wall := _box_mesh(props, "wall", Vector3(0, 11, 3), Vector3(4, 3, 0.3))
	var floor_plate := _box_mesh(props, "floor", Vector3(0, 9.95, 3), Vector3(4, 0.1, 4))
	var far_tree := _box_mesh(props, "tree", Vector3(30, 11, 3), Vector3(1, 4, 1))
	# THE s_SEmain REGRESSION (2026-08-10): a mesh whose custom AABB swallows
	# camera AND avatar, with its actual geometry off to the side. AABB-only
	# logic fades it; the triangle narrow phase must NOT.
	var big := _quad_mesh(props, "big_aabb", Vector3(20, 8, 3),
			AABB(Vector3(-40, -2, -40), Vector3(80, 20, 80)))
	occ.rebuild(props)
	_check(occ._index.size() == 4, "index sees 4 meshes")

	occ.set_active(true)
	occ._update_targets()
	var wall_entry: Dictionary = occ._fading.get(wall, {})
	_check(wall_entry.get("target", 0.0) == CameraOcclusion.FADED_ALPHA, "wall fades")
	_check(not occ._fading.has(floor_plate), "floor plate below knees never fades")
	_check(not occ._fading.has(far_tree), "off-axis tree never fades")
	_check(not occ._fading.has(big),
			"big-AABB mesh with off-sightline geometry never fades (s_SEmain)")

	# Move the quad geometry onto the sightline: now it must fade.
	big.position = Vector3(0, 11, 3)
	occ.rebuild(props)
	occ._update_targets()
	_check(occ._fading.has(big), "quad on the sightline fades")

	# Sliver hits must NOT fade (the 2026-08-11 "distant stairs ghosted"
	# fix): a thin bar crossing ONLY the waist ray fails the 2-of-3
	# consensus. Bar at z=3 spans y 11.20-11.30: the waist ray passes it at
	# y=11.25 (hit); feet ray at 10.85 and head ray at 11.5 both miss.
	var bar := _box_mesh(props, "bar", Vector3(0, 11.25, 3), Vector3(4, 0.1, 0.1))
	occ.rebuild(props)
	occ._update_targets()
	_check(not occ._fading.has(bar), "waist-only sliver never fades (consensus)")
	bar.get_parent().remove_child(bar)
	bar.queue_free()

	# Near-camera exclusion: a plate hugging the lens (0.3 m ahead, inside
	# RAY_START_OFFSET) crosses every ray mathematically but must not fade.
	var lens_plate := _box_mesh(props, "lens", Vector3(0, 11.4, 5.75),
			Vector3(2, 2, 0.05))
	occ.rebuild(props)
	occ._update_targets()
	_check(not occ._fading.has(lens_plate),
			"lens-hugging geometry never fades (ray start offset)")
	lens_plate.get_parent().remove_child(lens_plate)
	lens_plate.queue_free()
	occ.rebuild(props)
	occ._update_targets()

	# Hysteresis (the 2026-08-11 flicker fix): a faded prop whose sightline
	# clears only BRIEFLY must keep its faded target — restore begins only
	# after RESTORE_DELAY of continuously clear time.
	occ._update_targets(0.016)
	_check(occ._fading[wall]["target"] == CameraOcclusion.FADED_ALPHA,
			"wall target faded while blocked")
	cam.global_position = Vector3(0, 30, 6)   # look from above: wall clears
	occ._update_targets(0.1)
	_check(occ._fading[wall]["target"] == CameraOcclusion.FADED_ALPHA,
			"brief clear keeps the faded target (hysteresis)")
	occ._update_targets(0.1)
	occ._update_targets(0.15)                 # cumulative 0.35 > RESTORE_DELAY
	_check(occ._fading[wall]["target"] == 1.0,
			"sustained clear eases the wall back")
	# Re-block resets the hysteresis clock and the target.
	cam.global_position = Vector3(0, 11.5, 6)
	occ._update_targets(0.016)
	_check(occ._fading[wall]["target"] == CameraOcclusion.FADED_ALPHA
			and occ._fading[wall]["clear"] == 0.0,
			"re-block resets target and clear clock")

	# Wall clears once it no longer blocks.
	wall.get_parent().remove_child(wall)
	occ.rebuild(props)
	occ._update_targets()
	_check(not occ._fading.has(floor_plate), "still no floor fade after rebuild")

	# --- _occ_variant: scissor strip (the "school vanishes" fix) ---
	# A masked FF-style shader: the variant must DROP the scissor write (it
	# would keep the material in the alpha-scissor opaque pass, where the
	# reduced ALPHA discards every pixel) and carry the occ_alpha uniform.
	var masked := Shader.new()
	masked.code = "shader_type spatial;\nrender_mode unshaded, cull_back;\nuniform float alpha_scissor = 0.5;\nvoid fragment() {\n\tvec4 tex = vec4(1.0);\n\tALBEDO = tex.rgb;\n\tif (alpha_scissor >= 0.0) {\n\t\tALPHA = tex.a;\n\t\tALPHA_SCISSOR_THRESHOLD = alpha_scissor;\n\t}\n}\n"
	var variant := occ._occ_variant(masked)
	_check(not variant.code.contains("ALPHA_SCISSOR_THRESHOLD"),
			"occ variant strips the scissor write")
	_check(variant.code.contains("uniform float occ_alpha"),
			"occ variant carries occ_alpha")
	_check(variant.code.contains("ALPHA = tex.a * occ_alpha;"),
			"occ variant writes the ghost alpha")

	print("PASS" if _fails == 0 else "FAIL (%d)" % _fails)
	quit(1 if _fails else 0)


func _box_mesh(parent: Node3D, name_: String, center: Vector3, size: Vector3) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = name_
	var box := BoxMesh.new()
	box.size = size
	mi.mesh = box
	_attach_ff_material(mi)
	parent.add_child(mi)
	mi.global_position = center
	return mi


func _quad_mesh(parent: Node3D, name_: String, center: Vector3, custom_aabb: AABB) -> MeshInstance3D:
	## A 2x2 vertical quad at `center`, with an oversized custom AABB — the
	## miniature of a building whose bounds swallow its forecourt.
	var mi := MeshInstance3D.new()
	mi.name = name_
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for v: Vector3 in [
			Vector3(-1, -1, 0), Vector3(1, -1, 0), Vector3(1, 1, 0),
			Vector3(-1, -1, 0), Vector3(1, 1, 0), Vector3(-1, 1, 0)]:
		st.add_vertex(v)
	var mesh := st.commit()
	mesh.custom_aabb = custom_aabb
	mi.mesh = mesh
	_attach_ff_material(mi)
	parent.add_child(mi)
	mi.position = center
	return mi


func _attach_ff_material(mi: MeshInstance3D) -> void:
	# Minimal FF-shaped material: production surfaces are always
	# ShaderMaterials whose fragment defines `tex` (prop_lighting swap).
	var sh := Shader.new()
	sh.code = "shader_type spatial;\nrender_mode unshaded, cull_back;\nvoid fragment() {\n\tvec4 tex = vec4(1.0);\n\tALBEDO = tex.rgb;\n}\n"
	var mat := ShaderMaterial.new()
	mat.shader = sh
	mi.set_surface_override_material(0, mat)


func _check(ok: bool, what: String) -> void:
	print(("ok: " if ok else "FAIL: ") + what)
	if not ok:
		_fails += 1
