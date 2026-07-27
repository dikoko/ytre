extends Camera3D
## Simple fly camera for map inspection.
## WASD/QE = move, Right-click drag = look, Scroll = speed, Shift = fast

var speed := 20.0
var sensitivity := 0.003
var _dragging := false

func _ready() -> void:
	current = true

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			_dragging = event.pressed
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if _dragging else Input.MOUSE_MODE_VISIBLE
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			speed = min(speed * 1.2, 200.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			speed = max(speed / 1.2, 1.0)

	if event is InputEventMouseMotion and _dragging:
		rotate_y(-event.relative.x * sensitivity)
		rotate_object_local(Vector3.RIGHT, -event.relative.y * sensitivity)

func _process(delta: float) -> void:
	# Skip movement when Ctrl is held (Ctrl+S = save in editor) or in edit mode
	if Input.is_key_pressed(KEY_CTRL) or Input.is_key_pressed(KEY_META):
		return
	var editor: Node = get_parent()
	if editor and editor.get("edit_mode"):
		return

	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): dir -= transform.basis.z
	if Input.is_key_pressed(KEY_S): dir += transform.basis.z
	if Input.is_key_pressed(KEY_A): dir -= transform.basis.x
	if Input.is_key_pressed(KEY_D): dir += transform.basis.x
	if Input.is_key_pressed(KEY_E): dir += Vector3.UP
	if Input.is_key_pressed(KEY_Q): dir -= Vector3.UP

	var mult := 3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0
	if dir.length() > 0:
		position += dir.normalized() * speed * mult * delta
