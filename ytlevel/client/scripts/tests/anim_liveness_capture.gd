extends SceneTree
## Captures frame pairs ~2 s apart so a detector can prove the animated
## props actually move — a single screenshot cannot tell "animated" from
## "exported but frozen".
##
## Two pairs, same camera, same gap:
##   anim_a/anim_b       props visible  -> must differ
##   control_a/control_b props hidden   -> must not differ
## The control is what makes the measurement mean something: it catches
## camera drift, temporal AA, and any other per-frame churn that would
## otherwise read as animation.
##
## Run: GODOT_BIN --path client --script scripts/tests/anim_liveness_capture.gd \
##          -- <MAP_CODE> <OUT_DIR>

const SETTLE_FRAMES := 30
const GAP_SECONDS := 2.0
const FRAME_SIZE := Vector2i(1024, 1024)
const BG := Color(30.0 / 255.0, 30.0 / 255.0, 200.0 / 255.0)


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		push_error("usage: -- <MAP_CODE> <OUT_DIR>")
		quit(2)
		return
	_run(args[0], args[1])


func _run(map_code: String, out_dir: String) -> void:
	var packed := load("res://scenes/maps/%s.tscn" % map_code) as PackedScene
	if packed == null:
		push_error("no scene for %s" % map_code)
		quit(3)
		return
	var map := packed.instantiate()
	# The map root's script is the legacy prop editor; the level tool strips it
	# when hosting, and so do we — its key handling has no place in a capture.
	map.set_script(null)
	root.add_child(map)

	DirAccess.make_dir_recursive_absolute(out_dir)
	# `root` IS the window/viewport in a SceneTree script; get_viewport() on
	# it returns null, which silently aborted _run and hung the process.
	root.transparent_bg = false
	RenderingServer.set_default_clear_color(BG)
	root.size = FRAME_SIZE

	for i in range(SETTLE_FRAMES):
		await process_frame

	var terrain := map.get_node_or_null("Terrain") as MeshInstance3D
	if terrain == null:
		push_error("no Terrain node in %s" % map_code)
		quit(3)
		return
	var aabb := terrain.get_aabb()
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = float(int(round(max(aabb.size.x, aabb.size.z))))
	cam.position = aabb.get_center() + Vector3(0, 100, 0)
	cam.rotation_degrees = Vector3(-90, 0, 0)
	cam.current = true
	map.add_child(cam)

	var props := map.get_node_or_null("Props")
	if props == null:
		push_error("no Props node in %s" % map_code)
		quit(3)
		return

	# Water scrolls its UVs every frame and beach sprites spawn continuously.
	# Both are real motion and both are somebody else's system — left visible
	# they would show up in the animated measure AND in the control, which is
	# exactly how SF002008 first failed. Hide them for the whole capture.
	var water := map.get_node_or_null("Water") as Node3D
	if water != null:
		water.visible = false

	await _pair(out_dir, "anim")
	props.visible = false
	await _pair(out_dir, "control")

	print("anim_liveness: captured %s" % map_code)
	quit(0)


func _pair(out_dir: String, prefix: String) -> void:
	for i in range(5):
		await process_frame
	await _shot(out_dir.path_join("%s_a.png" % prefix))
	var t := 0.0
	while t < GAP_SECONDS:
		t += await _tick()
	await _shot(out_dir.path_join("%s_b.png" % prefix))


func _tick() -> float:
	await process_frame
	return root.get_process_delta_time()


func _shot(path: String) -> void:
	await process_frame
	root.get_texture().get_image().save_png(path)
