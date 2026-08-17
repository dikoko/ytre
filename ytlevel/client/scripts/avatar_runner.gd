class_name AvatarRunner
extends Node3D
## Run mode: WASD avatar + free-look camera (the only run camera).
## WASD moves the avatar relative to the camera yaw; right-drag or trackpad
## two-finger drag orbits the camera around the character (slight upward
## look allowed, never below the ground — navmesh-aware clamp). Distance/FOV
## base comes from the map's authored back-view framing (.env via catalog);
## wheel/pinch zoom factor clamped [0.33, 1.0]; damped height tracking
## (dt*gap*5.0) kept from the original follow-cam port.

const STEP_LIMIT := 1.0        # block steps with |Δh| > 1 m (original step rule)
const ZOOM_MIN := 0.33
const ZOOM_MAX := 1.0
const TRAVEL_DWELL := 0.6
const PITCH_MIN := -15.0       # slight upward look at the avatar allowed...
const PITCH_MAX := 85.0        # ...up to almost straight overhead
const TURN_SPEED := 2.2        # rad/s — A/D keyboard turn rate

signal portal_entered(dest: String)
## Fires once when the avatar first enters a live portal's dwell radius
## (dest non-empty), and again with "" if the dwell is cancelled (avatar
## leaves the radius, or switches portals) before it reaches TRAVEL_DWELL.
## Lets the UI show the "about to travel" toast during the grace window,
## not just at the moment of travel.
signal portal_dwelling(dest: String)

var active := false
var avatar_position := Vector3.ZERO

var _hs: HeightService
var _nav: NavService = null
var _cam: Camera3D
var _cfg: Dictionary = {}
var _avatar: Node3D = null
var _gender := "female"
var _speed := 4.0
var _cam_params := {}          # level "camera" dict
var _zoom := 1.0
var _cam_height := 0.0         # damped target height
## Free-look is the ONLY run camera (user decision 2026-07-26): WASD moves
## the avatar camera-relative, drag/two-finger drag orbits the camera around
## the character; no auto-align, no follow/framing toggles.
var _yaw := 0.0                # camera yaw around avatar (radians)
var _pitch := -20.0            # degrees; camera elevation angle
var _portals: PortalMarkers = null
## Map FF sun (from the Terrain node metadata, same source as prop/terrain
## shaders) — fed into the avatar shader's light uniforms so the character
## is lit like the world around her instead of the dim portrait rig.
var _sun_dir := Vector3(0, -1, 0)
var _sun_diffuse := Color(1, 1, 1)
var _sun_ambient := Color(1, 1, 1)
var _has_sun := false
var _shadow: MeshInstance3D = null
var _dwell := 0.0
var _dwell_dest := ""
var _suppressed_uid := -1    # just-arrived guard: portal (by uid) ignored until avatar leaves its radius
var _anim := ""


func setup(hs: HeightService, cam: Camera3D, runner_cfg: Dictionary,
		nav: NavService = null) -> void:
	_hs = hs
	_cam = cam
	_cfg = runner_cfg
	_nav = nav
	_speed = float(runner_cfg.get("move_speed", 4.0))


func step_blocked(next_x: float, next_z: float) -> bool:
	## Walkability authority: the ported .map movement grid — the SAME data
	## the original's A* pathfinder walks (its only movement authority; the
	## wall grid is line-of-sight data and every wall cell is also unmovable
	## in .map, so the LOS path below is strictly a fallback for a map
	## shipping no .map). Escape hatch in both paths: a spawn can land in a
	## blocked cell (the default spawn is portals[0], which on some maps sits
	## inside a building) — movement within that cell and OUT to open ground
	## stays free, but never into a NEW blocked cell; the original has the
	## same concept (its negative-start mode).
	if _nav == null:
		return false
	if _nav.has_move_grid():
		var same_cell := int(next_x) == int(avatar_position.x) \
				and int(-next_z) == int(-avatar_position.z)
		if not _nav.movable(avatar_position.x, avatar_position.z):
			return not same_cell and not _nav.movable(next_x, next_z)
		if not _nav.movable(next_x, next_z):
			return true
		# Diagonal corner rule (the original applies it to path steps): a
		# step entering a diagonally-adjacent cell must have BOTH orthogonal
		# neighbor cells open — no squeezing through touching corners.
		var cx := int(avatar_position.x)
		var cz := int(-avatar_position.z)
		var nx := int(next_x)
		var nz := int(-next_z)
		if cx != nx and cz != nz:
			if not _nav.movable(float(nx) + 0.5, -(float(cz) + 0.5)) \
					or not _nav.movable(float(cx) + 0.5, -(float(nz) + 0.5)):
				return true
		return false
	# LOS-wall fallback. The original client's wall line-cross test is
	# endpoint-EXCLUSIVE — correct for its own purpose (long-segment line of
	# sight) but blind to a per-frame step that simply enters a wall cell
	# (~0.067 m at speed 4), so movement also tests the destination cell.
	if not is_nan(_nav.sample(next_x, next_z)):
		return false
	if _nav.crosses_wall(avatar_position.x, avatar_position.z, next_x, next_z):
		return true
	if _nav.is_wall(avatar_position.x, avatar_position.z):
		var same_cell := int(next_x) == int(avatar_position.x) \
				and int(-next_z) == int(-avatar_position.z)
		return not same_cell and _nav.is_wall(next_x, next_z)
	return _nav.is_wall(next_x, next_z)


func ground_height(x: float, z: float) -> float:
	## Original client priority: the navmesh is consulted for every
	## position and the heightfield is the fallback.
	## Both are raw authored heights; the renderer draws terrain raw too.
	if _nav != null:
		var ny := _nav.sample(x, z)
		if not is_nan(ny):
			return ny
	return _hs.surface_height(x, z)


func set_portal_markers(pm: PortalMarkers) -> void:
	_portals = pm


func set_sun(direction: Vector3, diffuse: Color, ambient: Color) -> void:
	_sun_dir = direction
	_sun_diffuse = diffuse
	_sun_ambient = ambient
	_has_sun = true
	if _avatar != null:
		_apply_sun()


func _apply_sun() -> void:
	## The avatar shader's portrait-rig uniforms (light_direction/diffuse/
	## ambient, world_ambient) are overridden with the map's FF sun so the
	## character matches the prop formula 0.7*sunAmbient + sunDiffuse*(N·L).
	## Setting a uniform a shader doesn't declare is a harmless no-op.
	if not _has_sun or _avatar == null:
		return
	for mat in _collect_shader_materials(_avatar):
		mat.set_shader_parameter("light_direction", _sun_dir)
		mat.set_shader_parameter("light_diffuse", Vector3(
				_sun_diffuse.r, _sun_diffuse.g, _sun_diffuse.b))
		mat.set_shader_parameter("light_ambient", Vector3.ZERO)
		mat.set_shader_parameter("world_ambient", Vector3(
				_sun_ambient.r, _sun_ambient.g, _sun_ambient.b))


func _collect_shader_materials(node: Node) -> Array:
	var found := []
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		if mi.material_override is ShaderMaterial:
			found.append(mi.material_override)
		for s in mi.get_surface_override_material_count():
			if mi.get_surface_override_material(s) is ShaderMaterial:
				found.append(mi.get_surface_override_material(s))
		if mi.mesh != null:
			for s in mi.mesh.get_surface_count():
				if mi.mesh.surface_get_material(s) is ShaderMaterial:
					found.append(mi.mesh.surface_get_material(s))
	for child in node.get_children():
		found.append_array(_collect_shader_materials(child))
	return found


func avatar_transform() -> Transform3D:
	## World transform of the avatar (position + facing) — the anchor for
	## warp effects, which inherit the character's frame in the original.
	if _avatar != null:
		return _avatar.global_transform
	return Transform3D(Basis.IDENTITY, avatar_position)


func enter(level: Dictionary, spawn: Vector3) -> void:
	_cam_params = level.get("camera", {})
	active = true
	_zoom = 1.0
	_yaw = 0.0
	# Comfortable over-the-shoulder default; the authored back-view angle
	# (often -20°) ends up terrain-clamped at ground level with the camera
	# peering up over the slope. Drag down for the upward look instead.
	_pitch = 15.0
	_dwell = 0.0
	_dwell_dest = ""
	_suppressed_uid = -1
	if _avatar == null:
		_spawn_avatar()
	avatar_position = spawn
	avatar_position.y = ground_height(spawn.x, spawn.z)
	_cam_height = avatar_position.y
	_avatar.position = avatar_position
	_play("stand")
	# Just-arrived guard: if we spawned inside a known-dest portal's radius
	# (e.g. the link-back portal after a travel), suppress it so walking
	# through doesn't immediately bounce us back. Lifted once the avatar
	# leaves that portal's radius (or enters a different one).
	if _portals != null:
		var hit := _portals.check_proximity(avatar_position)
		if not hit.is_empty():
			_suppressed_uid = int(hit.get("uid", -1))


func exit() -> void:
	active = false
	_dwell = 0.0
	_dwell_dest = ""
	_suppressed_uid = -1
	if _avatar != null:
		_avatar.queue_free()
		_avatar = null
	if _shadow != null:
		_shadow.queue_free()
		_shadow = null


func set_gender(g: String) -> void:
	if g == _gender:
		return
	_gender = g
	if _avatar != null:
		_avatar.queue_free()
		_avatar = null
		_spawn_avatar()
		_avatar.position = avatar_position


func _spawn_avatar() -> void:
	# Sanctioned deviation from the brief (Task 12 finding): AvatarCharacter.new()
	# directly — load("res://addons/ytavatar/avatar_character.gd").new() collides
	# with the class_name registration.
	_avatar = AvatarCharacter.new()
	_avatar.gender = _gender
	_avatar.default_animation = ""
	add_child(_avatar)
	var prefix := "male_" if _gender == "male" else "female_"
	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		var code: String = str(_cfg.get(prefix + slot, ""))
		if not code.is_empty():
			_avatar.set_part(slot, code)
	_anim = ""
	_play("stand")
	# Sun + blob shadow: apply now and once more next frame — some part
	# materials are built deferred inside the addon.
	_apply_sun()
	call_deferred("_apply_sun")
	if _shadow == null:
		_make_shadow()


func _make_shadow() -> void:
	## Era-authentic soft blob shadow. Godot's real-time shadows cannot land
	## on the unshaded FF terrain/prop shaders, so a radial-gradient quad at
	## the feet is the correct tool here (and what 2005 MMOs did anyway).
	## Procedural falloff in-shader (no texture). Wide full-strength core:
	## a narrow one reads as invisible because it hides under the character
	## sprite itself — pixel-measured, not guessed.
	var shader := Shader.new()
	shader.code = """
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never;
void fragment() {
	float r = length(UV - vec2(0.5)) * 2.0;
	ALBEDO = vec3(0.0);
	ALPHA = (1.0 - smoothstep(0.55, 0.95, r)) * 0.5;
}
"""
	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.render_priority = 1
	var plane := PlaneMesh.new()
	plane.size = Vector2(0.9, 0.9)
	_shadow = MeshInstance3D.new()
	_shadow.mesh = plane
	_shadow.material_override = mat
	_shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_shadow)


func _play(kind: String) -> void:
	if _anim == kind or _avatar == null:
		return
	_anim = kind
	var name := ("basic_" if _gender == "male" else "febasic_") + \
			("run" if kind == "run" else "stand")
	_avatar.play_animation(name)


func _move_step(dir: Vector3, delta: float) -> bool:
	## One frame of steering movement. The original never dead-stopped on a
	## blocked cell — its click-to-move A* routed around it — so keyboard
	## steer needs two graces on top of the raw grid test:
	## 1. Wall slide: if the straight step is blocked, try each axis alone
	##    (glide along block boundaries instead of freezing).
	## 2. Corner rounding: on a dead head-on block, shimmy one lane sideways
	##    — but ONLY toward a lane that is open both beside the avatar and
	##    diagonally ahead, so 1-cell obstacles (balustrade posts, the
	##    plaza strays) are walked around while a solid wall still stops
	##    cleanly with no endless lateral drift.
	var next := avatar_position + dir * _speed * delta
	if _try_step(next):
		return true
	if _try_step(Vector3(next.x, 0.0, avatar_position.z)):
		return true
	if _try_step(Vector3(avatar_position.x, 0.0, next.z)):
		return true
	return _corner_round(dir, delta)


func _corner_round(dir: Vector3, delta: float) -> bool:
	if _nav == null or not _nav.has_move_grid():
		return false
	var step := _speed * delta
	var next := avatar_position + dir * step
	# Forward cell row/column (original-space cell coords of the block).
	var fz := int(-next.z)
	var fx := int(next.x)
	if absf(dir.z) >= absf(dir.x):
		# Moving mostly along Z: lanes are X columns.
		var lane := int(avatar_position.x)
		var frac := avatar_position.x - float(lane)
		for side: int in ([-1, 1] if frac < 0.5 else [1, -1]):
			var l := lane + side
			# The lane must be open beside the avatar AND diagonally ahead.
			if _nav.movable(float(l) + 0.5, avatar_position.z) \
					and _nav.movable(float(l) + 0.5, -(float(fz) + 0.5)):
				return _try_step(avatar_position + Vector3(float(side) * step, 0.0, 0.0))
	else:
		var lane := int(-avatar_position.z)
		var frac := -avatar_position.z - float(lane)
		for side: int in ([-1, 1] if frac < 0.5 else [1, -1]):
			var l := lane + side
			if _nav.movable(avatar_position.x, -(float(l) + 0.5)) \
					and _nav.movable(float(fx) + 0.5, -(float(l) + 0.5)):
				return _try_step(avatar_position + Vector3(0.0, 0.0, float(-side) * step))
	return false


func _try_step(next: Vector3) -> bool:
	## One movement attempt: bounds + walkability grid + the STEP_LIMIT
	## height rule. On success the avatar advances (y snapped to ground).
	if not _hs.in_bounds(next.x, next.z) or step_blocked(next.x, next.z):
		return false
	# No-op steps (an axis-slide candidate can equal the current position)
	# must not count as movement.
	if next.x == avatar_position.x and next.z == avatar_position.z:
		return false
	var h := ground_height(next.x, next.z)
	if absf(h - avatar_position.y) > STEP_LIMIT:
		return false
	avatar_position = Vector3(next.x, h, next.z)
	return true


func _process(delta: float) -> void:
	if not active or _avatar == null:
		return
	var input := Vector2.ZERO
	if Input.is_key_pressed(KEY_W): input.y += 1.0
	if Input.is_key_pressed(KEY_S): input.y -= 1.0
	# A/D turn (classic MMO keyboard steer) — camera-relative strafe read as
	# "running sideways" because the avatar always faces her movement
	# direction and there is no strafe animation. W+A curves left.
	if Input.is_key_pressed(KEY_A): _yaw += TURN_SPEED * delta
	if Input.is_key_pressed(KEY_D): _yaw -= TURN_SPEED * delta
	if input != Vector2.ZERO:
		var fwd := Vector3(sin(_yaw), 0, cos(_yaw))    # camera sits at -fwd
		var dir := fwd * input.y
		if _move_step(dir, delta):
			# Face steering direction (model faces -Z ⇒ rotate to dir):
			_avatar.rotation.y = atan2(dir.x, dir.z) + PI
		_play("run")
	else:
		_play("stand")
	_avatar.position = avatar_position
	if _shadow != null:
		_shadow.position = avatar_position + Vector3(0.0, 0.03, 0.0)
	_update_camera(delta)
	_check_portals(delta)


func _unhandled_input(event: InputEvent) -> void:
	if not active:
		return
	if event is InputEventMouseButton and event.pressed:
		match event.button_index:
			MOUSE_BUTTON_WHEEL_UP: _zoom = clampf(_zoom - 0.07, ZOOM_MIN, ZOOM_MAX)
			MOUSE_BUTTON_WHEEL_DOWN: _zoom = clampf(_zoom + 0.07, ZOOM_MIN, ZOOM_MAX)
	elif event is InputEventMouseMotion \
			and event.button_mask & MOUSE_BUTTON_MASK_RIGHT:
		_yaw -= event.relative.x * 0.006
		_pitch = clampf(_pitch + event.relative.y * 0.25, PITCH_MIN, PITCH_MAX)
	elif event is InputEventPanGesture:
		# macOS trackpad two-finger drag orbits the camera around the avatar.
		_yaw -= event.delta.x * 0.02
		_pitch = clampf(_pitch + event.delta.y * 0.8, PITCH_MIN, PITCH_MAX)
	elif event is InputEventMagnifyGesture:
		_zoom = clampf(_zoom / event.factor, ZOOM_MIN, ZOOM_MAX)


func _update_camera(delta: float) -> void:
	# Distance/FOV base = the map's authored close (back-view) framing;
	# elevation comes from the user's drag pitch.
	var dist: float = float(_cam_params.get("dn_dist", 8.0)) * _zoom
	var fov: float = float(_cam_params.get("dn_fov", 30.0))
	# Damped height tracking so stairs don't jolt (original: dt * gap * 5.0).
	_cam_height += (avatar_position.y - _cam_height) * clampf(delta * 5.0, 0.0, 1.0)
	var target := Vector3(avatar_position.x, _cam_height + 1.0, avatar_position.z)
	var back := Vector3(sin(_yaw), 0, cos(_yaw))
	var pitched := back.rotated(Vector3(back.z, 0, -back.x).normalized(),
			deg_to_rad(_pitch))
	var pos := target - pitched * dist
	# Never below the ground — navmesh-aware, so the camera also stays on
	# top of porches/platforms instead of dipping through them.
	if _hs.in_bounds(pos.x, pos.z):
		pos.y = maxf(pos.y, ground_height(pos.x, pos.z) + 0.3)
	_cam.position = pos
	_cam.fov = fov
	_cam.look_at(target, Vector3.UP)


func _check_portals(delta: float) -> void:
	if _portals == null:
		return
	var hit := _portals.check_proximity(avatar_position)
	var hit_dest := str(hit.get("dest", ""))
	var hit_uid := int(hit.get("uid", -1))
	if _suppressed_uid != -1:
		if hit_uid == _suppressed_uid:
			return  # still inside the just-arrived portal's radius; ignore
		_suppressed_uid = -1  # left it (or entered a different one): re-arm
	if hit.is_empty() or hit_dest != _dwell_dest:
		if _dwell > 0.0:
			portal_dwelling.emit("")   # cancel: left the dwell before travel
		_dwell = 0.0
		_dwell_dest = hit_dest
		return
	if _dwell == 0.0:
		portal_dwelling.emit(hit_dest)   # entered the dwell radius: show the toast
	_dwell += delta
	if _dwell >= TRAVEL_DWELL:
		_dwell = 0.0
		portal_entered.emit(_dwell_dest)
