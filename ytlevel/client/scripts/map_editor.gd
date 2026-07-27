extends Node3D
## Level editor for map scenes.
## Tab = toggle Edit mode. [/] = cycle props. Click = select.
## Arrows = move XZ, PgUp/PgDn = Y, R/T = rotate, N = flip normals, F = flip lighting.
## M = mirror left-right, Delete = reset prop, +/- = step size, Ctrl+S = save overrides.

# --- State ---
var edit_mode := false
var selected_index := -1
var step_sizes := [0.1, 0.25, 0.5, 1.0, 5.0]
var step_index := 2
var save_dirty := false

# Per-prop override data: node_name -> { position, rotation_y, flip_normals, flip_object }
var overrides: Dictionary = {}

var _props_node: Node3D
var _camera: Camera3D
var _hud_control: Control
var _prop_children: Array[Node3D] = []
var _map_code: String

# Selection highlight
var _highlight_box: MeshInstance3D
var _highlight_mat: StandardMaterial3D

# Prop list panel
var show_prop_list := false
var filter_text := ""
var filter_category := ""
var filtered_props: Array[int] = []
var prop_list_scroll := 0


func _ready() -> void:
	_map_code = name
	_props_node = get_node_or_null("Props")
	_camera = get_node_or_null("Camera3D")

	if _props_node:
		for child in _props_node.get_children():
			if child is Node3D:
				_prop_children.append(child)

	# Selection highlight box
	_highlight_box = MeshInstance3D.new()
	_highlight_mat = StandardMaterial3D.new()
	_highlight_mat.albedo_color = Color(1, 1, 0, 0.3)
	_highlight_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_highlight_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_highlight_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_highlight_box.material_override = _highlight_mat
	_highlight_box.visible = false
	add_child(_highlight_box)

	# Build HUD overlay
	var canvas := CanvasLayer.new()
	canvas.name = "EditorHUD"
	canvas.layer = 100
	add_child(canvas)

	_hud_control = _HUDControl.new()
	_hud_control.editor = self
	_hud_control.anchors_preset = Control.PRESET_FULL_RECT
	_hud_control.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(_hud_control)

	# Load existing overrides
	_load_overrides()
	# Eval measures the raw pipeline: skip applying overrides (still load the data above)
	# so the eval capture sees unfixed-up props, not runtime fix-ups.
	if not get_meta("eval_skip_overrides", false):
		_apply_all_overrides()


func _unhandled_input(event: InputEvent) -> void:
	# Tab toggles edit mode
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_TAB:
			edit_mode = not edit_mode
			_update_highlight()
			_refresh_hud()
			get_viewport().set_input_as_handled()
			return
		# L cycles day/night light sets (works outside edit mode too):
		# base .plt sun -> dir_light_set[0..n-1] -> back. Mirrors the
		# original client's sun-change message, which gameplay scripts
		# used e.g. to switch on the lights of the
		# authored-black maze maps (FD014402/FD014403/FD015101).
		if event.keycode == KEY_L:
			_cycle_light_set()
			get_viewport().set_input_as_handled()
			return

	if not edit_mode:
		return

	# Click to select
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_select_by_click(event.position)
		get_viewport().set_input_as_handled()
		return

	if event is InputEventKey and event.pressed:
		var handled := true
		match event.keycode:
			KEY_BRACKETLEFT:
				_cycle_selection(-1)
			KEY_BRACKETRIGHT:
				_cycle_selection(1)
			KEY_UP:
				_move_selected(Vector3(0, 0, -_step()))
			KEY_DOWN:
				_move_selected(Vector3(0, 0, _step()))
			KEY_LEFT:
				_move_selected(Vector3(-_step(), 0, 0))
			KEY_RIGHT:
				_move_selected(Vector3(_step(), 0, 0))
			KEY_PAGEUP:
				_move_selected(Vector3(0, _step(), 0))
			KEY_PAGEDOWN:
				_move_selected(Vector3(0, -_step(), 0))
			KEY_R:
				_rotate_selected(15.0)
			KEY_T:
				_rotate_selected(-15.0)
			KEY_N:
				_toggle_flip_normals()
			KEY_F:
				_toggle_flip_object()
			KEY_M:
				_toggle_mirror()
			KEY_DELETE:
				_reset_selected()
			KEY_EQUAL:  # + key
				step_index = mini(step_index + 1, step_sizes.size() - 1)
			KEY_MINUS:
				step_index = maxi(step_index - 1, 0)
			KEY_P:
				show_prop_list = not show_prop_list
				if show_prop_list:
					_update_filtered_props()
			KEY_C:
				if show_prop_list:
					var cats := ["", "track", "stand", "nature", "building", "modified"]
					var idx := cats.find(filter_category)
					filter_category = cats[(idx + 1) % cats.size()]
					_update_filtered_props()
				else:
					handled = false
			KEY_S:
				if event.ctrl_pressed:
					_save_overrides()
				else:
					handled = false
			_:
				handled = false

		if handled:
			_refresh_hud()
			get_viewport().set_input_as_handled()

	# Prop list text filter input
	if show_prop_list and edit_mode and event is InputEventKey and event.pressed:
		if event.keycode == KEY_BACKSPACE and filter_text.length() > 0:
			filter_text = filter_text.substr(0, filter_text.length() - 1)
			_update_filtered_props()
			_refresh_hud()
			get_viewport().set_input_as_handled()


# --- Helpers ---

func _step() -> float:
	return step_sizes[step_index]


func _get_selected() -> Node3D:
	if selected_index >= 0 and selected_index < _prop_children.size():
		return _prop_children[selected_index]
	return null


func _cycle_selection(dir: int) -> void:
	if _prop_children.is_empty():
		return
	if selected_index < 0:
		selected_index = 0 if dir > 0 else _prop_children.size() - 1
	else:
		selected_index = (selected_index + dir) % _prop_children.size()
		if selected_index < 0:
			selected_index += _prop_children.size()
	_update_highlight()


func _select_by_click(screen_pos: Vector2) -> void:
	if not _camera or _prop_children.is_empty():
		return

	var ray_origin: Vector3 = _camera.project_ray_origin(screen_pos)
	var ray_dir: Vector3 = _camera.project_ray_normal(screen_pos)

	var best_idx := -1
	var best_dist := 1e18

	for i in _prop_children.size():
		var node: Node3D = _prop_children[i]
		var aabb: AABB = _get_world_aabb(node)
		if aabb.size == Vector3.ZERO:
			continue
		var hit: float = _ray_intersects_aabb(ray_origin, ray_dir, aabb)
		if hit >= 0.0 and hit < best_dist:
			best_dist = hit
			best_idx = i

	if best_idx >= 0:
		selected_index = best_idx
		_update_highlight()


func _get_world_aabb(node: Node3D) -> AABB:
	var result := AABB()
	var first := true
	for child in node.get_children():
		if child is VisualInstance3D:
			var child_aabb: AABB = child.get_aabb()
			var t: Transform3D = child.global_transform
			# Transform the 8 corners
			for corner_i in 8:
				var corner: Vector3 = child_aabb.get_endpoint(corner_i)
				var world_pt: Vector3 = t * corner
				if first:
					result = AABB(world_pt, Vector3.ZERO)
					first = false
				else:
					result = result.expand(world_pt)
	# Also check the node itself
	if node is VisualInstance3D:
		var node_aabb: AABB = node.get_aabb()
		var t: Transform3D = node.global_transform
		for corner_i in 8:
			var corner: Vector3 = node_aabb.get_endpoint(corner_i)
			var world_pt: Vector3 = t * corner
			if first:
				result = AABB(world_pt, Vector3.ZERO)
				first = false
			else:
				result = result.expand(world_pt)
	# If no visual children, use position with a small box
	if first:
		result = AABB(node.global_position - Vector3(0.5, 0.5, 0.5), Vector3(1, 1, 1))
	return result


func _ray_intersects_aabb(origin: Vector3, dir: Vector3, aabb: AABB) -> float:
	## Returns distance to intersection or -1.0 if no hit.
	var tmin := -1e18
	var tmax := 1e18
	var aabb_pos: Vector3 = aabb.position
	var aabb_end: Vector3 = aabb.position + aabb.size

	for axis in 3:
		if absf(dir[axis]) < 1e-9:
			if origin[axis] < aabb_pos[axis] or origin[axis] > aabb_end[axis]:
				return -1.0
		else:
			var t1 := (aabb_pos[axis] - origin[axis]) / dir[axis]
			var t2 := (aabb_end[axis] - origin[axis]) / dir[axis]
			if t1 > t2:
				var tmp := t1
				t1 = t2
				t2 = tmp
			tmin = maxf(tmin, t1)
			tmax = minf(tmax, t2)
			if tmin > tmax:
				return -1.0

	if tmax < 0.0:
		return -1.0
	return maxf(tmin, 0.0)


func _move_selected(offset: Vector3) -> void:
	var node: Node3D = _get_selected()
	if not node:
		return
	node.position += offset
	_record_override(node)
	_update_highlight()


func _rotate_selected(degrees: float) -> void:
	var node: Node3D = _get_selected()
	if not node:
		return
	node.rotation_degrees.y += degrees
	_record_override(node)
	_update_highlight()


func _toggle_flip_normals() -> void:
	var node: Node3D = _get_selected()
	if not node:
		return
	var ov: Dictionary = _get_or_create_override(node.name)
	ov["flip_normals"] = not ov.get("flip_normals", false)
	save_dirty = true
	# flip_normals is a flag only -- applied via material at save/load time
	# For now just record it


func _toggle_flip_object() -> void:
	var node: Node3D = _get_selected()
	if not node:
		return
	# Toggle material cull mode to fix lighting on dark flat props.
	# CULL_DISABLED shows both faces but the visible-from-above face may be dark.
	# CULL_FRONT shows only the back face, which gets its normal flipped by Godot
	# → correctly lit from above. No geometry movement.
	var key: String = String(node.name)
	if key not in overrides:
		overrides[key] = {}
	var cur: bool = overrides[key].get("flip_object", false)
	overrides[key]["flip_object"] = !cur
	_apply_cull_flip(node, !cur)
	save_dirty = true
	_update_highlight()


func _apply_cull_flip(node: Node3D, flip: bool) -> void:
	for child in node.get_children():
		if child is MeshInstance3D:
			_set_flip_on_mesh(child as MeshInstance3D, flip)
		for grandchild in child.get_children():
			if grandchild is MeshInstance3D:
				_set_flip_on_mesh(grandchild as MeshInstance3D, flip)


# Lazy-created shared shader for normal flipping
var _flip_shader: Shader

func _get_flip_shader() -> Shader:
	if not _flip_shader:
		_flip_shader = Shader.new()
		_flip_shader.code = """
shader_type spatial;
render_mode cull_disabled;
uniform sampler2D albedo_texture : source_color, filter_linear_mipmap;
uniform float alpha_scissor_threshold = 0.0;
void fragment() {
	vec4 tex = texture(albedo_texture, UV);
	ALBEDO = tex.rgb;
	if (alpha_scissor_threshold > 0.0 && tex.a < alpha_scissor_threshold) {
		discard;
	}
	NORMAL = -NORMAL;
}
"""
	return _flip_shader


func _set_flip_on_mesh(mi: MeshInstance3D, flip: bool) -> void:
	if not mi.mesh:
		return
	for surf_idx in mi.mesh.get_surface_count():
		if flip:
			# Get the original material (from mesh, not override)
			var orig_mat: Material = mi.mesh.surface_get_material(surf_idx)
			if orig_mat is StandardMaterial3D:
				var std: StandardMaterial3D = orig_mat as StandardMaterial3D
				var shader_mat := ShaderMaterial.new()
				shader_mat.shader = _get_flip_shader()
				if std.albedo_texture:
					shader_mat.set_shader_parameter("albedo_texture", std.albedo_texture)
				if std.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
					shader_mat.set_shader_parameter("alpha_scissor_threshold", std.alpha_scissor_threshold)
				mi.set_surface_override_material(surf_idx, shader_mat)
		else:
			# Remove override to restore original shared material
			mi.set_surface_override_material(surf_idx, null)


func _toggle_mirror() -> void:
	var node: Node3D = _get_selected()
	if not node:
		return
	# Mirror left-right by flipping scale.x.
	# Compensate position for off-center meshes using world AABB.
	var aabb_before: AABB = _get_world_aabb(node)
	var center_before: Vector3 = aabb_before.position + aabb_before.size * 0.5

	node.scale.x *= -1.0

	var aabb_after: AABB = _get_world_aabb(node)
	var center_after: Vector3 = aabb_after.position + aabb_after.size * 0.5

	# Shift position to keep visual center in the same place
	node.global_position += center_before - center_after

	_record_override(node)
	var ov: Dictionary = _get_or_create_override(node.name)
	ov["mirror"] = node.scale.x < 0.0
	save_dirty = true
	_update_highlight()


func _reset_selected() -> void:
	var node: Node3D = _get_selected()
	if not node:
		return
	if overrides.has(node.name):
		overrides.erase(node.name)
		save_dirty = true
	# Note: we cannot restore original transform without storing it.
	# Reset to identity-ish: just zero out our edits.


func _record_override(node: Node3D) -> void:
	var ov: Dictionary = _get_or_create_override(node.name)
	ov["position"] = [snapped(node.position.x, 0.001), snapped(node.position.y, 0.001), snapped(node.position.z, 0.001)]
	ov["rotation_y"] = snapped(node.rotation_degrees.y, 0.01)
	save_dirty = true


func _get_or_create_override(node_name: String) -> Dictionary:
	if not overrides.has(node_name):
		overrides[node_name] = {}
	return overrides[node_name]


# --- Prop list panel ---

func _update_filtered_props() -> void:
	filtered_props.clear()
	for i in range(_prop_children.size()):
		var pname: String = String(_prop_children[i].name).to_lower()
		if filter_category == "modified":
			if String(_prop_children[i].name) not in overrides:
				continue
		elif filter_category != "":
			if filter_category not in pname:
				continue
		if filter_text != "" and filter_text.to_lower() not in pname:
			continue
		filtered_props.append(i)
	prop_list_scroll = 0


# --- Selection highlight ---

func _update_highlight() -> void:
	if selected_index < 0 or not edit_mode:
		_highlight_box.visible = false
		return
	var prop: Node3D = _prop_children[selected_index]
	var aabb: AABB = _get_world_aabb(prop)
	if aabb.size == Vector3.ZERO:
		_highlight_box.visible = false
		return
	var box := BoxMesh.new()
	box.size = aabb.size * 1.05  # slightly larger than prop
	_highlight_box.mesh = box
	# Use world AABB center directly — mesh vertices may be offset from node origin
	_highlight_box.global_position = aabb.position + aabb.size * 0.5
	_highlight_box.visible = true


func _get_prop_aabb(node: Node3D) -> AABB:
	var result := AABB()
	var first := true
	for child in node.get_children():
		if child is MeshInstance3D:
			var mesh_aabb: AABB = child.get_aabb()
			if first:
				result = mesh_aabb
				first = false
			else:
				result = result.merge(mesh_aabb)
		# Check grandchildren too (GLB scenes have nested structure)
		for grandchild in child.get_children():
			if grandchild is MeshInstance3D:
				var mesh_aabb2: AABB = grandchild.get_aabb()
				if first:
					result = mesh_aabb2
					first = false
				else:
					result = result.merge(mesh_aabb2)
	if first:
		result = AABB(Vector3(-1, -1, -1), Vector3(2, 2, 2))
	return result


# --- Save / Load ---

func _overrides_path() -> String:
	return "res://assets/maps/" + _map_code + "/overrides.yaml"


func _save_overrides() -> void:
	var path: String = _overrides_path()

	# Ensure directory exists
	var dir_path: String = path.get_base_dir()
	DirAccess.make_dir_recursive_absolute(dir_path)

	var f: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	if not f:
		push_error("Cannot write overrides to " + path)
		return

	f.store_line("map_code: " + _map_code)
	f.store_line("props:")

	var keys: Array = overrides.keys()
	keys.sort()
	for key in keys:
		var ov: Dictionary = overrides[key]
		f.store_line("  " + key + ":")
		if ov.has("position"):
			var p: Array = ov["position"]
			f.store_line("    position: [" + str(p[0]) + ", " + str(p[1]) + ", " + str(p[2]) + "]")
		if ov.has("rotation_y"):
			f.store_line("    rotation_y: " + str(ov["rotation_y"]))
		if ov.get("flip_normals", false):
			f.store_line("    flip_normals: true")
		if ov.get("flip_object", false):
			f.store_line("    flip_object: true")
		if ov.get("mirror", false):
			f.store_line("    mirror: true")

	f.close()
	save_dirty = false
	print("[MapEditor] Saved overrides to ", path)


func _load_overrides() -> void:
	var path: String = _overrides_path()
	if not FileAccess.file_exists(path):
		return

	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if not f:
		return

	overrides.clear()
	var current_prop := ""
	var current_ov: Dictionary = {}

	while not f.eof_reached():
		var line: String = f.get_line()
		var stripped: String = line.strip_edges()
		if stripped.is_empty() or stripped.begins_with("#"):
			continue

		if stripped.begins_with("map_code:"):
			continue

		if stripped == "props:":
			continue

		# Indentation level determines if this is a prop name or a property
		var indent: int = line.length() - line.strip_edges(true, false).length()

		if indent == 2 and stripped.ends_with(":"):
			# New prop entry
			if not current_prop.is_empty() and not current_ov.is_empty():
				overrides[current_prop] = current_ov
			current_prop = stripped.trim_suffix(":")
			current_ov = {}

		elif indent >= 4 and ":" in stripped:
			var parts: PackedStringArray = stripped.split(":", true, 1)
			var prop_key: String = parts[0].strip_edges()
			var prop_val: String = parts[1].strip_edges()

			match prop_key:
				"position":
					var arr: Array = _parse_float_array(prop_val)
					if arr.size() == 3:
						current_ov["position"] = arr
				"rotation_y":
					current_ov["rotation_y"] = prop_val.to_float()
				"flip_normals":
					current_ov["flip_normals"] = prop_val == "true"
				"flip_object":
					current_ov["flip_object"] = prop_val == "true"
				"mirror":
					current_ov["mirror"] = prop_val == "true"

	# Don't forget the last entry
	if not current_prop.is_empty() and not current_ov.is_empty():
		overrides[current_prop] = current_ov

	f.close()
	print("[MapEditor] Loaded ", overrides.size(), " overrides from ", path)


func _parse_float_array(text: String) -> Array:
	var inner: String = text.trim_prefix("[").trim_suffix("]")
	var parts: PackedStringArray = inner.split(",")
	var result: Array = []
	for p in parts:
		result.append(p.strip_edges().to_float())
	return result


func _apply_all_overrides() -> void:
	for node_name in overrides:
		var node: Node3D = _props_node.get_node_or_null(NodePath(node_name)) if _props_node else null
		if not node or not (node is Node3D):
			continue
		var ov: Dictionary = overrides[node_name]
		if ov.has("position"):
			var p: Array = ov["position"]
			node.position = Vector3(p[0], p[1], p[2])
		if ov.has("rotation_y"):
			node.rotation_degrees.y = ov["rotation_y"]
		if ov.get("flip_object", false):
			_apply_cull_flip(node, true)
		if ov.get("mirror", false):
			# Mirror: flip scale.x and compensate position
			var aabb_before: AABB = _get_world_aabb(node)
			var center_before: Vector3 = aabb_before.position + aabb_before.size * 0.5
			node.scale.x *= -1.0
			var aabb_after: AABB = _get_world_aabb(node)
			var center_after: Vector3 = aabb_after.position + aabb_after.size * 0.5
			node.global_position += center_before - center_after


# --- HUD refresh ---

var _light_set_idx := 0


func _cycle_light_set() -> void:
	var terrain := find_child("Terrain", true, false)
	if terrain == null:
		return
	var count: int = terrain.get_meta("dir_light_count", 0)
	if count <= 0:
		print("map_editor: no alternative light sets in this map's .plt")
		return
	_light_set_idx = (_light_set_idx + 1) % (count + 1)

	var dir: Vector3
	var diffuse: Vector3
	var ambient: Vector3
	if _light_set_idx == 0:
		dir = terrain.get_meta("sun_direction", Vector3(0, -1, 0))
		var d: Color = terrain.get_meta("sun_diffuse", Color(1, 1, 1))
		var a: Color = terrain.get_meta("sun_ambient", Color(1, 1, 1))
		diffuse = Vector3(d.r, d.g, d.b)
		ambient = Vector3(a.r, a.g, a.b)
		print("map_editor: light set -> base sun")
	else:
		var packed: PackedFloat32Array = terrain.get_meta("dir_light_set")
		var o := (_light_set_idx - 1) * 9
		dir = Vector3(packed[o], packed[o + 1], packed[o + 2])
		diffuse = Vector3(packed[o + 3], packed[o + 4], packed[o + 5])
		ambient = Vector3(packed[o + 6], packed[o + 7], packed[o + 8])
		print("map_editor: light set -> alt %d/%d" % [_light_set_idx, count])
	_apply_sun(dir, diffuse, ambient)


func _apply_sun(dir: Vector3, diffuse: Vector3, ambient: Vector3) -> void:
	# Instant switch (the original supports a fade; 0 ms here). Reaches the
	# terrain material_override and every FF prop override material; the
	# additive self-illum materials have no sun uniforms and ignore this.
	var mats: Array[ShaderMaterial] = []
	var terrain := find_child("Terrain", true, false)
	if terrain is MeshInstance3D and terrain.material_override is ShaderMaterial:
		mats.append(terrain.material_override)
	var props := find_child("Props", true, false)
	if props:
		for mi: MeshInstance3D in props.find_children("*", "MeshInstance3D", true, false):
			if mi.mesh == null:
				continue
			for s in range(mi.mesh.get_surface_count()):
				var om := mi.get_surface_override_material(s)
				if om is ShaderMaterial and not mats.has(om):
					mats.append(om)
	for m in mats:
		m.set_shader_parameter("sun_direction", dir)
		m.set_shader_parameter("sun_diffuse", diffuse)
		m.set_shader_parameter("sun_ambient", ambient)


func _refresh_hud() -> void:
	if _hud_control:
		_hud_control.queue_redraw()


func _process(_delta: float) -> void:
	if edit_mode and _hud_control:
		_hud_control.queue_redraw()


# --- Inner HUD class ---

class _HUDControl extends Control:
	var editor: Node  # map_editor.gd instance

	func _draw() -> void:
		if not editor or not editor.edit_mode:
			return

		var font: Font = ThemeDB.fallback_font
		var font_size := 14
		var color := Color.WHITE
		var shadow := Color(0, 0, 0, 0.7)
		var y := 30
		var x := 16
		var line_h := 20

		# Background panel
		var panel_rect := Rect2(8, 8, 420, 260)
		draw_rect(panel_rect, Color(0, 0, 0, 0.6))

		# Mode
		draw_string(font, Vector2(x, y), "-- EDIT MODE --", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.YELLOW)
		y += line_h

		# Selected prop info
		var sel: Node3D = editor._get_selected()
		if sel:
			draw_string(font, Vector2(x, y), "Prop: " + sel.name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.CYAN)
			y += line_h
			var pos: Vector3 = sel.position
			draw_string(font, Vector2(x, y), "Pos: (%.2f, %.2f, %.2f)" % [pos.x, pos.y, pos.z], HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)
			y += line_h
			draw_string(font, Vector2(x, y), "RotY: %.1f" % sel.rotation_degrees.y, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)
			y += line_h

			var ov: Dictionary = editor.overrides.get(sel.name, {})
			var flags := ""
			if ov.get("flip_normals", false):
				flags += " [N]"
			if ov.get("flip_object", false):
				flags += " [F]"
			if ov.get("mirror", false):
				flags += " [M]"
			if not flags.is_empty():
				draw_string(font, Vector2(x, y), "Flags:" + flags, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.ORANGE)
				y += line_h

			draw_string(font, Vector2(x, y), "Index: %d / %d" % [editor.selected_index + 1, editor._prop_children.size()], HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.GRAY)
			y += line_h
		else:
			draw_string(font, Vector2(x, y), "No prop selected (use [ ] or click)", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.GRAY)
			y += line_h

		y += 4

		# Step size
		draw_string(font, Vector2(x, y), "Step: " + str(editor._step()) + "  (+/- to change)", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)
		y += line_h

		# Save status
		var save_str: String = "Unsaved changes" if editor.save_dirty else "Clean"
		var save_col: Color = Color.YELLOW if editor.save_dirty else Color.GREEN
		draw_string(font, Vector2(x, y), "Save: " + save_str + "  (Ctrl+S)", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, save_col)
		y += line_h + 4

		# Controls reference
		draw_string(font, Vector2(x, y), "Controls:", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.GRAY)
		y += line_h
		var controls := [
			"Arrows=move XZ  PgUp/Dn=Y  R/T=rot",
			"N=flip normals  F=flip light  M=mirror  Del=reset",
			"[/]=cycle  Click=select  Tab=fly mode",
			"P=prop list  C=category filter",
		]
		for line in controls:
			draw_string(font, Vector2(x + 8, y), line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size - 1, Color.GRAY)
			y += line_h - 2

		# --- Prop list panel ---
		if editor.show_prop_list:
			var vp_size: Vector2 = get_viewport_rect().size
			var panel_w := 260.0
			var panel_x := vp_size.x - panel_w - 8
			var panel_y2 := 8.0
			var panel_h := vp_size.y - 16.0

			# Dark background
			draw_rect(Rect2(panel_x, panel_y2, panel_w, panel_h), Color(0, 0, 0, 0.75))

			var px := panel_x + 8.0
			var py := panel_y2 + 20.0
			var small := font_size - 1

			# Title
			draw_string(font, Vector2(px, py), "PROP LIST", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color.YELLOW)
			py += line_h

			# Filter text
			var filter_display: String = "> " + editor.filter_text + "_"
			draw_string(font, Vector2(px, py), filter_display, HORIZONTAL_ALIGNMENT_LEFT, -1, small, Color.GREEN)
			py += line_h

			# Category pills
			var cats := ["all", "track", "stand", "nature", "building", "modified"]
			var cat_x := px
			for cat in cats:
				var is_active: bool = false
				if cat == "all" and editor.filter_category == "":
					is_active = true
				elif cat == editor.filter_category:
					is_active = true
				var cat_col: Color = Color.YELLOW if is_active else Color.GRAY
				draw_string(font, Vector2(cat_x, py), "[" + cat + "]", HORIZONTAL_ALIGNMENT_LEFT, -1, small - 1, cat_col)
				cat_x += (cat.length() + 2) * 7.0 + 4.0
			py += line_h

			# Separator
			draw_line(Vector2(panel_x + 4, py - 6), Vector2(panel_x + panel_w - 4, py - 6), Color(1, 1, 1, 0.2), 1.0)

			# Prop entries
			var max_visible := int((panel_h - (py - panel_y2) - 30) / (line_h - 2))
			var scroll: int = editor.prop_list_scroll
			var total: int = editor.filtered_props.size()
			var end_idx: int = mini(scroll + max_visible, total)

			for fi in range(scroll, end_idx):
				var prop_idx: int = editor.filtered_props[fi]
				var prop_name: String = String(editor._prop_children[prop_idx].name)
				var prefix := ""
				if prop_idx == editor.selected_index:
					prefix = "> "
				var is_modified: bool = prop_name in editor.overrides
				if is_modified:
					prefix += "* "
				var entry_col: Color = Color.CYAN if prop_idx == editor.selected_index else (Color(1, 0.8, 0.3) if is_modified else Color(0.7, 0.7, 0.7))
				var display_name: String = prefix + prop_name
				if display_name.length() > 30:
					display_name = display_name.substr(0, 27) + "..."
				draw_string(font, Vector2(px, py), display_name, HORIZONTAL_ALIGNMENT_LEFT, -1, small, entry_col)
				py += line_h - 2

			# Count at bottom
			var count_str: String = "%d / %d props" % [total, editor._prop_children.size()]
			if editor.filter_category != "":
				count_str += "  [" + editor.filter_category + "]"
			draw_string(font, Vector2(px, panel_y2 + panel_h - 8), count_str, HORIZONTAL_ALIGNMENT_LEFT, -1, small, Color.GRAY)

		# --- Bottom-left axis widget ---
		var vp_sz: Vector2 = get_viewport_rect().size
		var ax_x := 50.0
		var ax_y := vp_sz.y - 50.0
		var ax_len := 30.0
		draw_line(Vector2(ax_x, ax_y), Vector2(ax_x + ax_len, ax_y), Color.RED, 2.0)
		draw_string(font, Vector2(ax_x + ax_len + 2, ax_y + 4), "X", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.RED)
		draw_line(Vector2(ax_x, ax_y), Vector2(ax_x, ax_y - ax_len), Color.GREEN, 2.0)
		draw_string(font, Vector2(ax_x - 4, ax_y - ax_len - 2), "Y", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.GREEN)
		draw_line(Vector2(ax_x, ax_y), Vector2(ax_x - ax_len * 0.7, ax_y + ax_len * 0.5), Color.BLUE, 2.0)
		draw_string(font, Vector2(ax_x - ax_len * 0.7 - 12, ax_y + ax_len * 0.5 + 4), "Z", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.BLUE)
