extends Node3D
## Level tool — main scene. Hierarchical level selection over MapHost.
## UI is built in code (avatar-tool pattern): one top bar + status line,
## _sync_gui() renders all state after every mutation.

const START_LEVEL := "SF001001"

var catalog := LevelCatalog.new()
var map_host: MapHost
var height_service := HeightService.new()
var nav_service := NavService.new()

var mode := "schools"          # "schools" | "episodes"
var group_index := 0
var level_code := ""

var runner: AvatarRunner
var run_mode := false
var _run_gender := "female"
var _toast_serial := 0

# Explore camera state saved across an Explore->Run round-trip (F1): the
# runner drives _camera.fov directly, and top-down uses PROJECTION_ORTHOGONAL
# with a `size` — none of that is restored by ExploreCamera itself.
var _saved_cam_fov := 75.0
var _saved_cam_projection := Camera3D.PROJECTION_PERSPECTIVE
var _saved_cam_size := 1.0
var _saved_cam_top_down := false

# UI nodes (built in _build_gui)
var mode_select: OptionButton
var group_select: OptionButton
var level_select: OptionButton
var prev_btn: Button
var next_btn: Button
var reset_btn: Button
var run_btn: Button
var gender_btn: Button
var status_label: Label
var toast_label: Label
var minimap: MinimapOverlay

var _camera: Camera3D
var portal_markers: PortalMarkers

# Deferred portal-click travel: the FIRST press of a double-click sequence
# also reports double_click == false, so a plain "pressed and not double_click"
# check would travel instantly and pre-empt ExploreCamera's double-click zoom.
# We hold the destination for one double-click window (~0.3s) and only travel
# if a second press doesn't arrive; the serial lets a stale timer no-op.
const PORTAL_CLICK_WINDOW := 0.3
var _pending_portal_dest := ""
var _portal_click_serial := 0

const TOAST_DURATION := 2.0


func _ready() -> void:
	_apply_theme()
	if not catalog.load_catalog():
		push_warning("level_tool: catalog missing — run 33_export_levels.py")
	map_host = MapHost.new()
	map_host.name = "MapHost"
	add_child(map_host)
	_camera = ExploreCamera.new()
	_camera.name = "ExploreCamera"
	_camera.far = 500.0
	add_child(_camera)
	_camera.current = true
	portal_markers = PortalMarkers.new()
	portal_markers.name = "PortalMarkers"
	add_child(portal_markers)
	runner = AvatarRunner.new()
	runner.name = "AvatarRunner"
	add_child(runner)
	runner.setup(height_service, _camera, catalog.load_runner_config(), nav_service)
	runner.set_portal_markers(portal_markers)
	runner.portal_entered.connect(_on_portal_travel)
	runner.portal_dwelling.connect(_on_portal_dwelling)
	_build_gui()
	load_level(START_LEVEL)


func _apply_theme() -> void:
	var theme := Theme.new()
	var font := load("res://assets/fonts/NotoSansKR.ttf") as Font
	if font != null:
		theme.default_font = font
		theme.default_font_size = 13
	get_window().theme = theme


func load_level(code: String) -> void:
	# Any navigation cancels a pending portal-click travel.
	_portal_click_serial += 1
	_pending_portal_dest = ""
	if code.is_empty() or not catalog.is_available(code):
		return
	var from_code := level_code
	if map_host.load_map(code):
		level_code = code
		height_service.load_map(code)
		nav_service.load_map(code)
		# Feed the map's FF sun (Terrain metadata, same source the prop and
		# terrain shaders use) to the runner so the avatar is lit to match.
		var terrain := map_host.get_terrain()
		if terrain != null and terrain.has_meta("sun_direction"):
			runner.set_sun(terrain.get_meta("sun_direction"),
					terrain.get_meta("sun_diffuse", Color(1, 1, 1)),
					terrain.get_meta("sun_ambient", Color(1, 1, 1)))
		(_camera as ExploreCamera).setup(height_service)
		(_camera as ExploreCamera).reset_view()
		portal_markers.build(catalog.get_level(code), catalog, height_service)
		minimap.show_map(code, catalog.get_level(code))
		_select_containing_group(code)
		_prefetch_neighbors()
		if run_mode:
			var spawn := _linkback_spawn(code, from_code)
			if spawn == Vector3.INF:
				spawn = _default_spawn(code)
			runner.enter(catalog.get_level(code), spawn)
		_sync_gui()


func _default_spawn(code: String) -> Vector3:
	var level := catalog.get_level(code)
	if level.has("spawn"):
		var s: Array = level["spawn"]
		return Vector3(s[0], s[1], s[2])
	var portals: Array = level.get("portals", [])
	if not portals.is_empty():
		var pos_arr: Array = portals[0].get("pos", [0, 0, 0])
		return Vector3(pos_arr[0], pos_arr[1], pos_arr[2])
	return height_service.get_bounds().get_center()


func _linkback_spawn(code: String, from_code: String) -> Vector3:
	# Prefer the destination's portal that links back to the map we came
	# from, offset 2u toward the map center so the avatar doesn't spawn
	# standing inside the portal trigger and immediately bounce back.
	if from_code.is_empty():
		return Vector3.INF
	var level := catalog.get_level(code)
	for p: Dictionary in level.get("portals", []):
		if str(p.get("dest", "")) == from_code:
			var pos_arr: Array = p.get("pos", [0, 0, 0])
			var pos := Vector3(pos_arr[0], pos_arr[1], pos_arr[2])
			var center := height_service.get_bounds().get_center()
			var dir := center - pos
			dir.y = 0.0
			if dir.length() > 0.001:
				pos += dir.normalized() * 2.0
			return pos
	return Vector3.INF


func _select_containing_group(code: String) -> void:
	# Keep mode/group dropdowns honest when travel (portals) crosses groups.
	for m in ["schools", "episodes"]:
		var groups := catalog.get_groups(m)
		for i in groups.size():
			if code in groups[i].get("levels", []):
				mode = m
				group_index = i
				return


func _current_levels() -> Array:
	var groups := catalog.get_groups(mode)
	if groups.is_empty():
		return []
	group_index = clampi(group_index, 0, groups.size() - 1)
	return groups[group_index].get("levels", [])


func _prefetch_neighbors() -> void:
	var lvls := _current_levels()
	var i := lvls.find(level_code)
	var neighbors: Array = []
	if i >= 0:
		if i > 0: neighbors.append(lvls[i - 1])
		if i < lvls.size() - 1: neighbors.append(lvls[i + 1])
	var avail := neighbors.filter(catalog.is_available)
	map_host.prefetch(avail)
	map_host.release_except(avail)


func _step_level(dir: int) -> void:
	if run_mode:
		return
	var lvls := _current_levels().filter(catalog.is_available)
	if lvls.is_empty():
		return
	var i := lvls.find(level_code)
	load_level(lvls[wrapi(i + dir, 0, lvls.size())])


# --- GUI ---

func _build_gui() -> void:
	var canvas := CanvasLayer.new()
	canvas.layer = 10
	add_child(canvas)

	minimap = MinimapOverlay.new()
	minimap.minimap_clicked.connect(_on_minimap_clicked)
	canvas.add_child(minimap)

	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(root)

	var bar := PanelContainer.new()
	root.add_child(bar)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	bar.add_child(row)

	mode_select = OptionButton.new()
	mode_select.add_item("Schools")
	mode_select.add_item("Episodes")
	mode_select.item_selected.connect(_on_mode_selected)
	mode_select.focus_mode = Control.FOCUS_NONE
	row.add_child(mode_select)

	group_select = OptionButton.new()
	group_select.custom_minimum_size.x = 220
	group_select.item_selected.connect(_on_group_selected)
	group_select.focus_mode = Control.FOCUS_NONE
	row.add_child(group_select)

	prev_btn = Button.new()
	prev_btn.text = "<"
	prev_btn.pressed.connect(_step_level.bind(-1))
	prev_btn.focus_mode = Control.FOCUS_NONE
	row.add_child(prev_btn)

	level_select = OptionButton.new()
	level_select.custom_minimum_size.x = 320
	level_select.item_selected.connect(_on_level_selected)
	level_select.focus_mode = Control.FOCUS_NONE
	row.add_child(level_select)

	next_btn = Button.new()
	next_btn.text = ">"
	next_btn.pressed.connect(_step_level.bind(1))
	next_btn.focus_mode = Control.FOCUS_NONE
	row.add_child(next_btn)

	reset_btn = Button.new()
	reset_btn.text = "Reset view"
	reset_btn.pressed.connect(_on_reset_view)
	reset_btn.focus_mode = Control.FOCUS_NONE
	row.add_child(reset_btn)

	run_btn = Button.new()
	run_btn.text = "Run"
	run_btn.pressed.connect(_toggle_run)
	run_btn.focus_mode = Control.FOCUS_NONE
	row.add_child(run_btn)

	gender_btn = Button.new()
	gender_btn.text = "♀"
	gender_btn.visible = false
	gender_btn.pressed.connect(_on_gender_pressed)
	gender_btn.focus_mode = Control.FOCUS_NONE
	row.add_child(gender_btn)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(spacer)

	status_label = Label.new()
	status_label.add_theme_color_override("font_color", Color(1, 1, 1, 0.85))
	status_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	status_label.add_theme_constant_override("outline_size", 4)
	root.add_child(status_label)

	toast_label = Label.new()
	toast_label.add_theme_color_override("font_color", Color(1, 1, 1, 0.95))
	toast_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	toast_label.add_theme_constant_override("outline_size", 4)
	toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast_label.set_anchors_preset(Control.PRESET_CENTER_TOP)
	toast_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	toast_label.offset_top = 50
	toast_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toast_label.visible = false
	canvas.add_child(toast_label)
	_sync_gui()


func _on_mode_selected(idx: int) -> void:
	mode = "schools" if idx == 0 else "episodes"
	group_index = 0
	_load_group_first()


func _on_group_selected(idx: int) -> void:
	group_index = idx
	_load_group_first()


func _load_group_first() -> void:
	# Changing school/episode loads that group's first available map. Without
	# this the cleared level dropdown auto-shows item 0 while the OLD map stays
	# loaded — and re-clicking the shown item emits no item_selected signal.
	var lvls := _current_levels().filter(catalog.is_available)
	if lvls.is_empty() or level_code in lvls:
		_sync_gui()
		return
	load_level(lvls[0])


func _on_level_selected(idx: int) -> void:
	var lvls := _current_levels()
	if idx >= 0 and idx < lvls.size():
		load_level(lvls[idx])


func _on_reset_view() -> void:
	(_camera as ExploreCamera).reset_view()


func _on_minimap_clicked(p: Vector3) -> void:
	(_camera as ExploreCamera).focus_on(Vector3(p.x, height_service.sample(p.x, p.z), p.z))


func _toggle_run() -> void:
	run_mode = not run_mode
	var cam := _camera as ExploreCamera
	if run_mode:
		_saved_cam_fov = _camera.fov
		_saved_cam_projection = _camera.projection
		_saved_cam_size = _camera.size
		_saved_cam_top_down = cam.top_down
		cam.set_top_down(false)   # never hand the runner an ortho projection
		cam.active = false
		runner.enter(catalog.get_level(level_code), _default_spawn(level_code))
	else:
		runner.exit()
		if _saved_cam_top_down:
			cam.set_top_down(true)   # restores projection + recomputes size...
		_camera.fov = _saved_cam_fov
		_camera.projection = _saved_cam_projection
		_camera.size = _saved_cam_size   # ...then pin the exact prior size
		cam.active = true
	_sync_gui()


func _on_gender_pressed() -> void:
	_run_gender = "female" if _run_gender == "male" else "male"
	runner.set_gender(_run_gender)
	_sync_gui()


func _on_portal_dwelling(dest: String) -> void:
	# Toast during the dwell grace window, before travel actually fires —
	# "walk away to cancel" needs to be visible, not just the travel flash.
	if dest.is_empty():
		toast_label.visible = false
		return
	toast_label.text = "→ " + catalog.display_name(dest)
	toast_label.visible = true


func _on_portal_travel(dest: String) -> void:
	toast_label.text = "→ " + catalog.display_name(dest)
	toast_label.visible = true
	_toast_serial += 1
	var serial := _toast_serial
	get_tree().create_timer(TOAST_DURATION).timeout.connect(func():
		if serial == _toast_serial:
			toast_label.visible = false
	)
	load_level(dest)


func _sync_gui() -> void:
	if mode_select == null:
		return
	mode_select.selected = 0 if mode == "schools" else 1
	# Map selection is explore-only: in Run mode you travel through portals.
	mode_select.disabled = run_mode
	group_select.disabled = run_mode
	level_select.disabled = run_mode
	prev_btn.disabled = run_mode
	next_btn.disabled = run_mode
	var groups := catalog.get_groups(mode)
	group_select.clear()
	for g in groups:
		var gname: String = str(g.get("name", g.get("id", "?")))
		if g.has("name_en"):
			gname += " / " + str(g["name_en"])
		group_select.add_item(gname)
	if not groups.is_empty():
		group_select.selected = clampi(group_index, 0, groups.size() - 1)
	level_select.clear()
	var lvls := _current_levels()
	for i in lvls.size():
		level_select.add_item(catalog.display_name(lvls[i]))
		level_select.set_item_disabled(i, not catalog.is_available(lvls[i]))
	var sel := lvls.find(level_code)
	if sel >= 0:
		level_select.selected = sel
	status_label.text = catalog.display_name(level_code) if not level_code.is_empty() else ""
	run_btn.text = "Exit Run" if run_mode else "Run"
	gender_btn.visible = run_mode
	gender_btn.text = "♂" if _run_gender == "male" else "♀"


func _process(_delta: float) -> void:
	# Explore mode: feed the camera position (fly camera — the eye IS the
	# point of interest). Run mode: the avatar.
	minimap.set_marker(runner.avatar_position if run_mode else _camera.position)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_TAB: _toggle_run()
			KEY_BRACKETLEFT: _step_level(-1)
			KEY_BRACKETRIGHT: _step_level(1)
	elif event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			if event.double_click:
				# Second press of the sequence: cancel any pending single-click
				# travel and let ExploreCamera's double-click zoom take over.
				_portal_click_serial += 1
				_pending_portal_dest = ""
			else:
				var dest := portal_markers.check_click(_camera, event.position)
				if not dest.is_empty() and catalog.is_available(dest):
					_schedule_portal_travel(dest)


func _schedule_portal_travel(dest: String) -> void:
	_pending_portal_dest = dest
	_portal_click_serial += 1
	var serial := _portal_click_serial
	get_tree().create_timer(PORTAL_CLICK_WINDOW).timeout.connect(
		func(): _on_portal_travel_timeout(serial)
	)


func _on_portal_travel_timeout(serial: int) -> void:
	if serial != _portal_click_serial:
		return
	var dest := _pending_portal_dest
	_pending_portal_dest = ""
	if not dest.is_empty():
		load_level(dest)
