class_name PortalMarkers
extends Node3D
## Portal markers from catalog data. Instances the real gate model when
## model_file resolves to an exported prop GLB, else a glowing ring.
## Explore-mode click travel + run-mode proximity queries.

const CLICK_RADIUS_PX := 24.0
const TRAVEL_RADIUS := 1.5

var _portals: Array = []   # [{pos: Vector3, dest: String, label: String}]


func build(level: Dictionary, catalog: LevelCatalog, hs: HeightService) -> void:
	for c in get_children():
		c.queue_free()
	_portals.clear()
	for p: Dictionary in level.get("portals", []):
		var pos_arr: Array = p.get("pos", [0, 0, 0])
		var pos := Vector3(pos_arr[0], pos_arr[1], pos_arr[2])
		if hs.in_bounds(pos.x, pos.z):
			pos.y = maxf(pos.y, hs.sample(pos.x, pos.z))
		var dest: String = str(p.get("dest", ""))
		var label := catalog.display_name(dest) if not dest.is_empty() \
				else "(destination unknown)"
		var uid: int = int(p.get("uid", -1))
		_portals.append({"pos": pos, "dest": dest, "label": label, "uid": uid})
		add_child(_make_marker(p, pos, label, not dest.is_empty()))


func _make_marker(p: Dictionary, pos: Vector3, label: String, known: bool) -> Node3D:
	var root := Node3D.new()
	root.position = pos
	var model_file: String = str(p.get("model_file", ""))
	var mesh_added := false
	if not model_file.is_empty():
		for cat in ["portal", "artificial", "active", "structure"]:
			var glb := "res://assets/props/models/%s/%s.glb" % [cat, model_file]
			if ResourceLoader.exists(glb):
				var packed := load(glb) as PackedScene
				if packed != null:
					root.add_child(packed.instantiate())
					mesh_added = true
					break
				# Corrupt/unimportable GLB: fall through to the ring below
				# instead of crashing on a null instantiate().
	if not mesh_added:
		var ring := MeshInstance3D.new()
		var torus := TorusMesh.new()
		torus.inner_radius = 0.7
		torus.outer_radius = 1.0
		ring.mesh = torus
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = Color(0.3, 0.8, 1.0, 0.8) if known else Color(1.0, 0.7, 0.2, 0.8)
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		ring.material_override = mat
		ring.position.y = 0.1
		root.add_child(ring)
	var tag := Label3D.new()
	tag.text = label
	tag.font_size = 48
	tag.pixel_size = 0.01
	tag.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	tag.position.y = 2.2
	tag.modulate = Color(1, 1, 1) if known else Color(1, 0.85, 0.6)
	tag.outline_size = 12
	root.add_child(tag)
	return root


func check_click(camera: Camera3D, screen_pos: Vector2) -> String:
	for p: Dictionary in _portals:
		if p["dest"].is_empty():
			continue
		if camera.is_position_behind(p["pos"]):
			continue
		if camera.unproject_position(p["pos"]).distance_to(screen_pos) < CLICK_RADIUS_PX:
			return p["dest"]
	return ""


func check_proximity(world_pos: Vector3) -> Dictionary:
	for p: Dictionary in _portals:
		if not p["dest"].is_empty() \
				and world_pos.distance_to(p["pos"]) < TRAVEL_RADIUS:
			return {"dest": p["dest"], "name": p["label"], "uid": p["uid"]}
	return {}
