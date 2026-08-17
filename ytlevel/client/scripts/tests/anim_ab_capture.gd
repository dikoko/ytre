extends SceneTree
## A/B capture for every animated prop: A = FF lighting only (identical to
## the pre-animation origin/main look — the raw GLB frame-0 pose renders
## byte-for-byte the same), B = lighting + PropAnimator (clips + fades).
## The mapeval driver diffs the pairs and flags props whose runtime look
## broke, rather than merely moved.
##
## Run: GODOT_BIN --path client --script scripts/tests/anim_ab_capture.gd \
##          -- <OUT_DIR> [prop_id ...]      (no ids = every prop with a sidecar)

const BG := Color(0.12, 0.12, 0.78)
const MODELS_ROOT := "res://assets/props/models"
const SETTLE_SECONDS := 0.5


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 1:
		push_error("usage: -- <OUT_DIR> [prop_id ...]")
		quit(2)
		return
	_run(args[0], args.slice(1))


func _discover() -> Array:
	## [ [prop_id, glb_path], ... ] for every prop with an .anim.json sidecar.
	var out: Array = []
	var root_dir := DirAccess.open(MODELS_ROOT)
	for cat in root_dir.get_directories():
		var dir := DirAccess.open(MODELS_ROOT.path_join(cat))
		for f in dir.get_files():
			if f.ends_with(".anim.json"):
				var pid := f.trim_suffix(".anim.json")
				# Capture name carries the category: 23 prop ids ship in two
				# categories and a bare-id filename silently overwrites one.
				out.append(["%s.%s" % [cat, pid],
						MODELS_ROOT.path_join(cat).path_join(pid + ".glb")])
	return out


func _run(out_dir: String, only: Array) -> void:
	DirAccess.make_dir_recursive_absolute(out_dir)
	RenderingServer.set_default_clear_color(BG)
	root.size = Vector2i(512, 512)
	var todo := _discover()
	if only.size() > 0:
		todo = todo.filter(func(e): return e[0] in only)
	print("anim_ab: %d props" % todo.size())
	for entry in todo:
		await _capture_pair(entry[0], entry[1], out_dir)
	print("anim_ab: done")
	quit(0)


func _capture_pair(prop_id: String, glb: String, out_dir: String) -> void:
	if not ResourceLoader.exists(glb):
		print("anim_ab: MISSING %s" % glb)
		return
	var packed := load(glb) as PackedScene
	if packed == null:
		print("anim_ab: UNLOADABLE %s" % glb)
		return
	for side in ["a", "b"]:
		var wrapper := Node3D.new()
		wrapper.set_meta("sun_direction", Vector3(0, -1, 0))
		wrapper.set_meta("sun_diffuse", Color(0.5, 0.5, 0.5))
		wrapper.set_meta("sun_ambient", Color(1, 1, 1))
		if side == "a":
			wrapper.set_meta("anim_disabled", true)
		wrapper.set_script(load("res://scripts/prop_lighting.gd"))
		wrapper.add_child(packed.instantiate())
		root.add_child(wrapper)
		await process_frame
		await process_frame
		var aabb := _scene_aabb(wrapper)
		var cam := Camera3D.new()
		root.add_child(cam)
		var center := aabb.get_center()
		var r: float = maxf(aabb.size.length() * 0.75, 0.5)
		cam.global_position = center + Vector3(r * 0.7, r * 0.45, r * 0.7)
		cam.look_at(center, Vector3.UP)
		cam.near = 0.05
		cam.current = true
		# Let clips advance and fades settle onto their curves.
		var t := 0.0
		while t < SETTLE_SECONDS:
			await process_frame
			t += root.get_process_delta_time()
		root.get_texture().get_image().save_png(
				out_dir.path_join("%s_%s.png" % [prop_id, side]))
		wrapper.queue_free()
		cam.queue_free()
		await process_frame


func _scene_aabb(n: Node) -> AABB:
	var out := AABB()
	var first := true
	for mi in n.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		if m.mesh == null:
			continue
		var ab: AABB = m.global_transform * m.mesh.get_aabb()
		out = ab if first else out.merge(ab)
		first = false
	return out
