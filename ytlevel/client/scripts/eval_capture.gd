# client/scripts/eval_capture.gd
# Standalone capture harness:
#   godot --path client --script res://scripts/eval_capture.gd -- MAP OUT_DIR PX_PER_CELL
# Captures: terrain_topdown.png (orthographic, PX_PER_CELL px per terrain cell),
# terrain_closeup.png (orthographic, fixed 64 px/cell over a 16x16 cell window
# centered at world (75, -75), for sampler-level seam detection),
# scene_topdown.png (same full-map framing as terrain_topdown but with props
# visible -- a human-review artifact for prop orientation bugs, e.g.
# misrotations/mirrors, that the dark-ratio detector cannot see), and
# prop_{model}.png per unique prop model (4 angles composited side by side).
extends SceneTree

const BG := Color(30.0 / 255.0, 30.0 / 255.0, 200.0 / 255.0)

var _out_dir: String
var _px_per_cell: int


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 3:
		push_error("usage: -- MAP OUT_DIR PX_PER_CELL")
		quit(2)
		return
	var map_code: String = args[0]
	_out_dir = args[1]
	_px_per_cell = int(args[2])
	DirAccess.make_dir_recursive_absolute(_out_dir)
	_run(map_code)


func _run(map_code: String) -> void:
	var scene: PackedScene = load("res://scenes/maps/%s.tscn" % map_code)
	if scene == null:
		push_error("map scene not found: " + map_code)
		quit(2)
		return
	var map_root := scene.instantiate()
	# Eval measures the raw pipeline: tell map_editor.gd (map root's script) to
	# load-but-not-apply overrides.yaml, so runtime prop fix-ups don't contaminate the capture.
	map_root.set_meta("eval_skip_overrides", true)
	root.add_child(map_root)

	# Wait for terrain_loader deferred generation + prop GLB instancing.
	for i in range(20):
		await process_frame

	var vp := root.get_viewport()
	vp.transparent_bg = false
	RenderingServer.set_default_clear_color(BG)

	await _capture_terrain(map_root)
	await _capture_props(map_root)
	quit(0)


func _capture_terrain(map_root: Node) -> void:
	var terrain := map_root.get_node_or_null("Terrain") as MeshInstance3D
	if terrain == null:
		push_error("no Terrain node")
		return
	var aabb := terrain.get_aabb()
	var cells := int(round(max(aabb.size.x, aabb.size.z)))
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	# One world unit == one cell; size = full extent so px/cell is exact.
	cam.size = float(cells)
	cam.position = aabb.get_center() + Vector3(0, 100, 0)
	cam.rotation_degrees = Vector3(-90, 0, 0)
	cam.current = true
	map_root.add_child(cam)
	var win := root.get_window()
	win.size = Vector2i(cells * _px_per_cell, cells * _px_per_cell)
	# Hide props so the seam detector sees pure terrain.
	var props := map_root.get_node_or_null("Props")
	if props:
		props.visible = false
	for i in range(5):
		await process_frame
	root.get_viewport().get_texture().get_image().save_png(_out_dir + "/terrain_topdown.png")

	# Close-up shot at 64 px/cell: the top-down capture (8 px/cell) minifies
	# 128px tiles ~16x, so the 1-texel cell-border bleed the clamp/inset/mipmap
	# shader fix targets is sub-resolution there. This shot is high-res enough
	# to see it. Cell-boundary-aligned center (75, -75) with size=16 spans
	# world x in [67,83], z in [-83,-67] -- 16 cells, boundaries land exactly
	# on multiples of 64px in the 1024x1024 frame.
	cam.size = 16.0
	cam.position = Vector3(75.0, 100.0, -75.0)
	win.size = Vector2i(1024, 1024)
	for i in range(5):
		await process_frame
	root.get_viewport().get_texture().get_image().save_png(_out_dir + "/terrain_closeup.png")

	if props:
		props.visible = true

	# Props-visible view for human orientation review -- dark-ratio detectors
	# cannot see misrotated/mirrored props. Same full-map framing as terrain_topdown.
	cam.size = float(cells)
	cam.position = aabb.get_center() + Vector3(0, 100, 0)
	win.size = Vector2i(cells * _px_per_cell, cells * _px_per_cell)
	for i in range(5):
		await process_frame
	root.get_viewport().get_texture().get_image().save_png(_out_dir + "/scene_topdown.png")

	cam.queue_free()


func _capture_props(map_root: Node) -> void:
	# One capture per unique model: isolate instance, 4 yaw angles side by side.
	var props := map_root.get_node_or_null("Props")
	if props == null:
		return
	var seen := {}
	var originals := props.get_children()
	map_root.visible = false
	# WorldEnvironment is not a Node3D, so map_root.visible = false above does NOT
	# disable it -- its constant ambient light would flood these isolated prop
	# captures and mask dark-pixel defects (e.g. inverted-normal props reading as
	# lit). Kill it for the prop stage; terrain capture already ran and doesn't
	# need it restored since the script quits after this function.
	var world_env := map_root.get_node_or_null("WorldEnvironment") as WorldEnvironment
	if world_env:
		world_env.environment = null
	var stage := Node3D.new()
	root.add_child(stage)
	var cam := Camera3D.new()
	cam.current = true
	stage.add_child(cam)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	stage.add_child(light)
	root.get_window().size = Vector2i(4 * 256, 256)

	for prop in originals:
		# node names look like obj_a_SEtrack02_4 → model key strips uid suffix
		var key := String(prop.name).trim_prefix("obj_").trim_prefix("portal_").trim_prefix("trigger_")
		key = key.substr(0, key.rfind("_"))
		if seen.has(key):
			continue
		seen[key] = true
		var dup := prop.duplicate()
		dup.transform = Transform3D.IDENTITY
		stage.add_child(dup)
		await process_frame
		var strip := Image.create(4 * 256, 256, false, Image.FORMAT_RGB8)
		for a in range(4):
			dup.rotation_degrees = Vector3(0, 90.0 * a, 0)
			# Recompute AABB after rotating: many props have their local origin
			# offset from their geometric center, so a fixed pre-rotation AABB
			# would badly misframe (or near-clip) some yaw angles.
			var aabb := _world_aabb(dup)
			# Fit the AABB's bounding sphere in frame: distance = radius / sin(fov/2).
			var radius: float = max(aabb.size.length() / 2.0, 0.05)
			var dist := radius / sin(deg_to_rad(cam.fov) * 0.5) * 1.15
			cam.position = aabb.get_center() + Vector3(0, radius * 0.25, dist)
			cam.look_at(aabb.get_center())
			for i in range(3):
				await process_frame
			# Window is 4*256 wide by 256 tall (KEEP_HEIGHT), so the prop occupies
			# a square in the center of a 1024x256 frame. Crop that centered
			# square instead of resizing the whole frame, which would squish it
			# 4:1. Only resize afterward if the crop isn't already 256x256.
			var shot := root.get_viewport().get_texture().get_image()
			var side := shot.get_height()
			var crop_x := (shot.get_width() - side) / 2
			shot = shot.get_region(Rect2i(crop_x, 0, side, side))
			if side != 256:
				shot.resize(256, 256)
			shot.convert(Image.FORMAT_RGB8)
			strip.blit_rect(shot, Rect2i(0, 0, 256, 256), Vector2i(a * 256, 0))
		strip.save_png(_out_dir + "/prop_" + key + ".png")
		dup.queue_free()
	map_root.visible = true


func _world_aabb(node: Node) -> AABB:
	var aabb := AABB()
	var first := true
	for mi in node.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = (mi as MeshInstance3D).global_transform * (mi as MeshInstance3D).get_aabb()
		aabb = b if first else aabb.merge(b)
		first = false
	return aabb
