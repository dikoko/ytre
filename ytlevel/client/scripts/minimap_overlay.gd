class_name MinimapOverlay
extends Control
## Bottom-right minimap from the shipped per-map image + world rect.
## Rect is D3D-space [left, top, right, bottom]; world x maps to u across
## [l, r], world -z (D3D z) maps to v across [t, b].

const MAP_SIZE := 200.0

signal minimap_clicked(world_pos: Vector3)

var _rect: Array = []
var _tex_rect: TextureRect
var _marker: ColorRect


func _ready() -> void:
	custom_minimum_size = Vector2(MAP_SIZE, MAP_SIZE)
	set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	offset_left = -MAP_SIZE - 12
	offset_top = -MAP_SIZE - 12
	offset_right = -12
	offset_bottom = -12
	_tex_rect = TextureRect.new()
	_tex_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	_tex_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_tex_rect.stretch_mode = TextureRect.STRETCH_SCALE
	add_child(_tex_rect)
	_marker = ColorRect.new()
	_marker.color = Color(1.0, 0.25, 0.2)
	_marker.size = Vector2(6, 6)
	_marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_marker)


func show_map(code: String, level: Dictionary) -> void:
	_rect = level.get("minimap_rect", [])
	var img_path := "res://assets/maps/%s/minimap.jpg" % code
	if _rect.size() != 4 or not FileAccess.file_exists(img_path):
		visible = false
		return
	var img := Image.new()
	if img.load(ProjectSettings.globalize_path(img_path)) != OK:
		visible = false
		return
	_tex_rect.texture = ImageTexture.create_from_image(img)
	visible = true


func set_marker(world_pos: Vector3) -> void:
	if not visible or _rect.size() != 4:
		return
	var u := inverse_lerp(_rect[0], _rect[2], world_pos.x)
	var v := inverse_lerp(_rect[1], _rect[3], -world_pos.z)
	_marker.visible = u >= 0.0 and u <= 1.0 and v >= 0.0 and v <= 1.0
	_marker.position = Vector2(u, v) * size - _marker.size * 0.5


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed \
			and event.button_index == MOUSE_BUTTON_LEFT and _rect.size() == 4:
		var uv := (event as InputEventMouseButton).position / size
		var wx := lerpf(_rect[0], _rect[2], uv.x)
		var wz := -lerpf(_rect[1], _rect[3], uv.y)
		minimap_clicked.emit(Vector3(wx, 0.0, wz))
