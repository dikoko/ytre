extends SceneTree
# Framing probe: drives the REAL avatar_tool through every monster/NPC and
# reports each model's initial camera framing as JSON — the projected
# screen-space bbox of the model AABB (coverage fraction, center offset,
# behind-camera corners). Driven by scripts/45_framingeval.py:
#   godot --path client -s .../framing_probe.gd -- <out_json> <mode>
# mode: "monster" | "npc"

func _init() -> void:
	_run()

func _run() -> void:
	await process_frame
	var args := OS.get_cmdline_user_args()
	var out_path: String = args[0]
	var mode_name: String = args[1] if args.size() > 1 else "monster"

	var tool_scene := (load("res://scenes/avatar_tool.tscn") as PackedScene).instantiate()
	root.add_child(tool_scene)
	await process_frame
	await process_frame

	var mode: int = tool_scene.CharacterMode.MONSTER if mode_name == "monster" \
			else tool_scene.CharacterMode.NPC
	tool_scene._enter_model_viewer(mode)
	for i in 10:
		await process_frame

	# Chroma-key setup for PIXEL metrics: hide the GUI and ground plane and
	# clear to magenta so the rendered model silhouette is measurable
	# directly — geometric proxies (mesh AABBs, bone clouds) each lie for
	# some rig class, pixels never do.
	if tool_scene.gui_layer:
		tool_scene.gui_layer.visible = false
	var ground: Node = tool_scene.get_node_or_null("GroundPlane")
	if ground:
		ground.visible = false
	RenderingServer.set_default_clear_color(Color(1, 0, 1))

	var results := []
	var cam: Camera3D = tool_scene.camera
	var vp_size: Vector2 = root.get_viewport().get_visible_rect().size
	for idx in tool_scene.monster_list.size():
		tool_scene._load_monster(idx)
		for i in 8:
			await process_frame
		var mid: String = tool_scene.monster_list[idx]
		var model = tool_scene._model_char
		if model == null:
			results.append({"id": mid, "error": "no model"})
			continue
		# PIXEL metrics: measure the rendered silhouette against the
		# magenta chroma key. Geometric proxies each lie for some rig
		# class (bind-pose mesh AABBs sit beside the body; bone clouds
		# collapse on blob rigs) — pixels never do.
		var img := root.get_viewport().get_texture().get_image()
		var w := img.get_width()
		var h := img.get_height()
		var min_x := w
		var max_x := -1
		var min_y := h
		var max_y := -1
		for y in range(0, h, 2):
			for x in range(0, w, 2):
				var c := img.get_pixel(x, y)
				# non-background = anything not close to pure magenta
				if absf(c.r - 1.0) + c.g + absf(c.b - 1.0) > 0.25:
					if x < min_x: min_x = x
					if x > max_x: max_x = x
					if y < min_y: min_y = y
					if y > max_y: max_y = y
		var entry := {"id": mid, "zoom": tool_scene.camera_distance}
		if max_x < 0:
			entry["error"] = "nothing rendered"
		else:
			var bw := float(max_x - min_x)
			var bh := float(max_y - min_y)
			entry["width_frac"] = bw / w
			entry["height_frac"] = bh / h
			entry["center_off"] = [
				((min_x + max_x) * 0.5 - w * 0.5) / w,
				((min_y + max_y) * 0.5 - h * 0.5) / h,
			]
			entry["touches_edge"] = (min_x <= 2 or min_y <= 2
					or max_x >= w - 3 or max_y >= h - 3)
		results.append(entry)
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	f.store_string(JSON.stringify(results))
	f.close()
	print("FRAMING PROBE DONE ", results.size())
	quit(0)
