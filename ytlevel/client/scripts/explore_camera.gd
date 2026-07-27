class_name ExploreCamera
extends Camera3D
## Fly-style explore camera. W/S move along the view direction (pitch down
## and W dives INTO the field — that is the zoom), A/D strafe, Q/E vertical,
## right-drag looks around, wheel / two-finger scroll / pinch dolly, T
## top-down ortho, Home resets to a whole-map overview, double-click flies
## to the clicked ground point. The camera is clamped above the gameplay
## terrain (the original client clamps its own camera the same way).
##
## History note: this replaced an orbit-around-focus design whose pivot
## clamp ratcheted the view upward and whose W/S went dead in top-down —
## the fly model matches how the tool is actually driven.

const PITCH_MIN := -89.0
const PITCH_MAX := 70.0
const CLAMP_MARGIN := 0.5
const ORTHO_SIZE_MIN := 5.0
const ORTHO_SIZE_MAX := 500.0
const SPEED_MIN := 4.0
const SPEED_MAX := 90.0

var active := true
var yaw := 0.0          # degrees
var pitch := -45.0      # degrees (negative = looking down)
var top_down := false

var _hs: HeightService = null
var _looking := false
var _panning := false


func setup(height_service: HeightService) -> void:
	_hs = height_service


func reset_view() -> void:
	top_down = false
	projection = PROJECTION_PERSPECTIVE
	if _hs == null:
		return
	var b := _hs.get_bounds()
	var center := b.get_center()
	var d := clampf(maxf(b.size.x, b.size.z) * 1.05, 10.0, 400.0)
	yaw = 0.0
	pitch = -45.0
	position = center + Vector3(0.0, d * 0.707, d * 0.707)
	_apply()


func focus_on(point: Vector3) -> void:
	# Fly to a comfortable vantage above/behind the point, looking at it.
	top_down = false
	projection = PROJECTION_PERSPECTIVE
	var yr := deg_to_rad(yaw)
	var back := Vector3(sin(yr), 0.0, cos(yr))
	position = point + back * 12.0 + Vector3(0.0, 8.0, 0.0)
	_look_at_point(point)
	_apply()


func set_top_down(on: bool) -> void:
	top_down = on
	if on:
		projection = PROJECTION_ORTHOGONAL
		if _hs != null:
			var b := _hs.get_bounds()
			var center := b.get_center()
			size = clampf(maxf(b.size.x, b.size.z) * 1.05, ORTHO_SIZE_MIN, ORTHO_SIZE_MAX)
			position = Vector3(center.x, maxf(position.y, center.y + 100.0), center.z)
		pitch = -89.0
	else:
		projection = PROJECTION_PERSPECTIVE
		pitch = clampf(pitch, PITCH_MIN, PITCH_MAX)
	_apply()


func clamp_now() -> void:
	## Public so the probe can force an underground position and assert
	## recovery without reaching into internals.
	_clamp_position()
	_apply()


func _speed() -> float:
	# Altitude-scaled: fast when high above the field, precise near the ground.
	var alt := 20.0
	if _hs != null and _hs.in_bounds(position.x, position.z):
		alt = maxf(position.y - _hs.sample(position.x, position.z), 1.0)
	var s := clampf(alt * 1.5, SPEED_MIN, SPEED_MAX)
	if Input.is_key_pressed(KEY_SHIFT):
		s *= 3.0
	return s


func _ground_axes() -> Array:
	# Screen-relative forward/right on the ground plane (top-down safe).
	var fwd := -basis.z
	fwd.y = 0.0
	if fwd.length_squared() < 0.001:
		fwd = basis.y
		fwd.y = 0.0
	var right := basis.x
	right.y = 0.0
	return [fwd.normalized(), right.normalized()]


func _process(delta: float) -> void:
	if not active:
		return
	var move := Vector3.ZERO
	if top_down:
		var axes := _ground_axes()
		if Input.is_key_pressed(KEY_W): move += axes[0]
		if Input.is_key_pressed(KEY_S): move -= axes[0]
		if Input.is_key_pressed(KEY_A): move -= axes[1]
		if Input.is_key_pressed(KEY_D): move += axes[1]
	else:
		# Fly: W/S along the full view direction — pitching down and holding
		# W is the "zoom into the field" gesture.
		if Input.is_key_pressed(KEY_W): move -= basis.z
		if Input.is_key_pressed(KEY_S): move += basis.z
		if Input.is_key_pressed(KEY_A): move -= basis.x
		if Input.is_key_pressed(KEY_D): move += basis.x
	if Input.is_key_pressed(KEY_E): move += Vector3.UP
	if Input.is_key_pressed(KEY_Q): move -= Vector3.UP
	if move.length_squared() > 0.0:
		position += move.normalized() * _speed() * delta
	_apply()


func _unhandled_input(event: InputEvent) -> void:
	if not active:
		return
	if event is InputEventMouseButton:
		match event.button_index:
			MOUSE_BUTTON_RIGHT:
				_looking = event.pressed
			MOUSE_BUTTON_MIDDLE:
				_panning = event.pressed
			MOUSE_BUTTON_WHEEL_UP:
				if event.pressed: _dolly(1.0)
			MOUSE_BUTTON_WHEEL_DOWN:
				if event.pressed: _dolly(-1.0)
			MOUSE_BUTTON_LEFT:
				if event.pressed and event.double_click:
					_focus_cursor(event.position)
	elif event is InputEventMouseMotion:
		if _looking and not top_down:
			yaw -= event.relative.x * 0.25
			pitch = clampf(pitch - event.relative.y * 0.25, PITCH_MIN, PITCH_MAX)
			_apply()
		elif _panning:
			var axes := _ground_axes()
			position -= (axes[1] * event.relative.x - axes[0] * event.relative.y) \
					* 0.0125 * maxf(_speed(), 8.0)
			_apply()
	elif event is InputEventPanGesture:
		# macOS trackpad two-finger scroll: vertical = dolly, horizontal = strafe.
		_dolly(-event.delta.y * 0.35)
		if absf(event.delta.x) > 0.01:
			position += basis.x * event.delta.x * 0.02 * _speed()
			_apply()
	elif event is InputEventMagnifyGesture:
		_dolly((event.factor - 1.0) * 8.0)
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_HOME: reset_view()
			KEY_T: set_top_down(not top_down)


func _dolly(amount: float) -> void:
	if top_down:
		size = clampf(size * (1.0 - amount * 0.08), ORTHO_SIZE_MIN, ORTHO_SIZE_MAX)
		_apply()
		return
	position += -basis.z * amount * clampf(_speed() * 0.25, 1.0, 25.0)
	_apply()


func _focus_cursor(cursor: Vector2) -> void:
	var hit := _ray_ground(cursor)
	if hit != Vector3.INF:
		focus_on(hit)


func _ray_ground(cursor: Vector2) -> Vector3:
	# March the pick ray against the height field (no physics in map scenes).
	if _hs == null:
		return Vector3.INF
	var origin := project_ray_origin(cursor)
	var dir := project_ray_normal(cursor)
	var t := 0.0
	while t < 600.0:
		var p := origin + dir * t
		if _hs.in_bounds(p.x, p.z):
			var h := _hs.sample(p.x, p.z)
			if p.y <= h:
				return Vector3(p.x, h, p.z)
		t += 0.5
	return Vector3.INF


func _look_at_point(point: Vector3) -> void:
	var to := point - position
	var horiz := Vector2(to.x, to.z).length()
	yaw = rad_to_deg(atan2(-to.x, -to.z))
	pitch = clampf(rad_to_deg(atan2(to.y, horiz)), PITCH_MIN, PITCH_MAX)


func _clamp_position() -> void:
	if _hs != null and _hs.in_bounds(position.x, position.z):
		position.y = maxf(position.y, _hs.sample(position.x, position.z) + CLAMP_MARGIN)


func _apply() -> void:
	_clamp_position()
	if top_down:
		rotation_degrees = Vector3(-90.0, 0.0, 0.0)
		return
	rotation_degrees = Vector3(pitch, yaw, 0.0)
