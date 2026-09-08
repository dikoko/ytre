class_name SfxObject
extends Node3D
## One playing .sfd effect — a faithful CPU port of the original particle
## library (spec §4.3): billboard (single camera-facing quad) or polygon
## emitter (world-space particles). All quads of one effect render through
## ONE MultiMeshInstance3D (global back-to-front order for non-additive
## effects) over the per-effect atlas SfxLibrary built; the render child is
## top_level so world-space particles never inherit this node's motion.
##
## Per-frame contract: the owner calls tick(dt, camera_transform) once per
## frame with the REAL delta (the original simulated on wall-clock dt).
## Emitter matrix = this node's global_transform at tick time (rotation
## included — direction graphs live in emitter space).

const SHADER_ADD: Shader = preload("res://shaders/sfx_additive.gdshader")
const SHADER_MIX: Shader = preload("res://shaders/sfx_alpha.gdshader")

const TEX_NONE := 0
const TEX_TOP := 1
const TEX_BOTTOM := 2
const TEX_LEFT := 4
const TEX_RIGHT := 8

## Corner UV tables (spec §4.3.6/§4.3.7), corner order (-U-V, -U+V, +U+V, +U-V).
const PARTICLE_UV := {
	TEX_TOP: [Vector2(1, 1), Vector2(0, 1), Vector2(0, 0), Vector2(1, 0)],
	TEX_BOTTOM: [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)],
	TEX_LEFT: [Vector2(1, 0), Vector2(1, 1), Vector2(0, 1), Vector2(0, 0)],
	TEX_RIGHT: [Vector2(0, 1), Vector2(0, 0), Vector2(1, 0), Vector2(1, 1)],
	TEX_NONE: [Vector2(0, 1), Vector2(0, 0), Vector2(1, 0), Vector2(1, 1)],
}
const BILLBOARD_UV := {
	TEX_TOP: [Vector2(0, 1), Vector2(0, 0), Vector2(1, 0), Vector2(1, 1)],
	TEX_BOTTOM: [Vector2(1, 0), Vector2(1, 1), Vector2(0, 1), Vector2(0, 0)],
	TEX_LEFT: [Vector2(1, 1), Vector2(0, 1), Vector2(0, 0), Vector2(1, 0)],
	TEX_RIGHT: [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)],
	TEX_NONE: [Vector2(0, 1), Vector2(0, 0), Vector2(1, 0), Vector2(1, 1)],  # spec §8: treated as TOP
}

## Per-particle state (spec §4.3.4). Angles are 16-bit integer units.
class Particle:
	var position: Vector3
	var velocity: Vector3
	var total_life: float
	var life := 0.0
	var deg := 0
	var ang_vel := 0
	var color := Color(1, 1, 1, 1)
	var base_opacity := 255.0
	var opacity := 255.0
	var scale_t := 0.0
	var scale_n := 0.0
	var texture_id := -1
	var dist2 := 0.0

var kind := "billboard"
var name_key := ""
var additive := true
var total_time := 1.0
var relative_time := 0.0
var playing := false
var cam_offset := 0.0
var texture_direction := TEX_NONE
var alignment := 0

var _graphs: Dictionary = {}
var _rects: Array = []
var _white_rect := Rect2(0, 0, 1, 1)

# emitter state (Task 8)
var _particles: Array = []
var _rate_dt := 0.0
var _first_tick := true
var _prev_emitter := Transform3D.IDENTITY
var _emitter := Transform3D.IDENTITY
var _net_force := Vector3.ZERO
var _blackhole_pos := Vector3.ZERO
var _blackhole_force := 0.0
var _drag := 0.0

# billboard state
var _bb_transform := Transform3D.IDENTITY
var _bb_color := Color(1, 1, 1, 1)
var _bb_texture_id := -1

# render
var _mmi: MultiMeshInstance3D
var _mm: MultiMesh
var _drawn := 0
## Shadow copy of what was written to the MultiMesh this tick — the
## headless test renderer cannot read instance data back, so tests (and
## the eval's NaN screen) inspect these instead.
var _inst_transforms: Array = []
var _inst_colors: Array = []


func setup(config: Dictionary) -> void:
	kind = String(config.get("kind", "billboard"))
	name_key = String(config.get("name_key", ""))
	additive = bool(config.get("additive", true))
	total_time = float(config.get("total_time", 1.0))
	texture_direction = int(config.get("texture_direction", TEX_NONE))
	alignment = int(config.get("alignment", 0))
	_graphs = config.get("graphs", {})
	_rects = config.get("rects", [])
	_white_rect = config.get("white_rect", Rect2(0, 0, 1, 1))
	_build_renderer(config.get("atlas"))


func _g(key: String) -> SfxGraph:
	var g: Variant = _graphs.get(key)
	return g if g is SfxGraph else SfxGraph.constant(0.0)


func _build_renderer(atlas: Variant) -> void:
	if _mmi != null:
		_mmi.queue_free()
	_mm = MultiMesh.new()
	_mm.transform_format = MultiMesh.TRANSFORM_3D
	_mm.use_colors = true
	_mm.use_custom_data = true
	_mm.mesh = _make_quad()
	_mm.instance_count = 0
	_mmi = MultiMeshInstance3D.new()
	_mmi.name = "Quads"
	_mmi.multimesh = _mm
	_mmi.top_level = true
	var mat := ShaderMaterial.new()
	mat.shader = SHADER_ADD if additive else SHADER_MIX
	if atlas is Texture2D:
		mat.set_shader_parameter("atlas", atlas)
	_mmi.material_override = mat
	add_child(_mmi)
	_mmi.global_transform = Transform3D.IDENTITY


func _make_quad() -> ArrayMesh:
	## Unit quad: corners (-1,-1) (-1,+1) (+1,+1) (+1,-1) in the instance's
	## U/V basis, UVs from the per-object direction table. Cull is off in
	## the shader, so winding is irrelevant.
	var table: Dictionary = BILLBOARD_UV if kind == "billboard" else PARTICLE_UV
	var uvs: Array = table.get(texture_direction, table[TEX_NONE])
	var verts := PackedVector3Array([Vector3(-1, -1, 0), Vector3(-1, 1, 0), Vector3(1, 1, 0), Vector3(1, -1, 0)])
	var uv := PackedVector2Array([uvs[0], uvs[1], uvs[2], uvs[3]])
	var idx := PackedInt32Array([0, 1, 2, 0, 2, 3])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


# === playback control (the skill component's PLAY/STOP/SETSFXREALTIME/seek) ===

func play() -> void:
	playing = true
	relative_time = 0.0
	_first_tick = true


func stop() -> void:
	playing = false
	relative_time = 0.0
	_particles.clear()
	_rate_dt = 0.0
	_first_tick = true
	_drawn = 0
	_inst_transforms.clear()
	_inst_colors.clear()
	if _mm != null:
		_mm.visible_instance_count = 0


func restart() -> void:
	stop()
	play()


func set_total_time(v: float) -> void:
	total_time = v


func set_time(t_seconds: float) -> void:
	if total_time != 0.0:
		relative_time = minf(t_seconds / total_time, 1.0)


func particle_count() -> int:
	return _particles.size()


func particles() -> Array:
	return _particles


func drawn_instances() -> int:
	return _drawn


func billboard_transform() -> Transform3D:
	return _bb_transform


func billboard_color() -> Color:
	return _bb_color


func instance_transform(i: int) -> Transform3D:
	return _inst_transforms[i] if i < _inst_transforms.size() else Transform3D.IDENTITY


func instance_color(i: int) -> Color:
	return _inst_colors[i] if i < _inst_colors.size() else Color()


func _write_instance(i: int, xf: Transform3D, col: Color, rect: Rect2) -> void:
	_mm.set_instance_transform(i, xf)
	_mm.set_instance_color(i, col)
	_mm.set_instance_custom_data(i, _rect_custom(rect))
	if i < _inst_transforms.size():
		_inst_transforms[i] = xf
		_inst_colors[i] = col
	else:
		_inst_transforms.append(xf)
		_inst_colors.append(col)


# === per-frame ===

func tick(dt: float, cam: Transform3D) -> void:
	if not playing or not is_finite(dt):
		return
	if total_time != 0.0:
		relative_time = minf(relative_time + dt / total_time, 1.0)
	if kind == "billboard":
		_tick_billboard(cam)
	else:
		_tick_emitter(dt)
		_render_emitter(cam)


static func _byte(x: float) -> int:
	## D3DCOLOR_COLORVALUE / the alpha cast: truncate to int, keep 8 bits.
	return int(x * 255.0) & 0xFF


func _rect_for(texture_id: int) -> Rect2:
	if texture_id >= 0 and texture_id < _rects.size():
		return _rects[texture_id]
	return _white_rect


func _rect_custom(r: Rect2) -> Color:
	return Color(r.position.x, r.position.y, r.size.x, r.size.y)


func _ensure_capacity(n: int) -> void:
	if _mm.instance_count < n:
		var cap := 64
		while cap < n:
			cap *= 2
		_mm.instance_count = cap  # reallocates; every visible instance is rewritten each frame


# --- billboard (spec §4.3.7) ---

func _tick_billboard(cam: Transform3D) -> void:
	var t := relative_time
	_bb_color = Color(
			_byte(_g("color_r").value(t)) / 255.0,
			_byte(_g("color_g").value(t)) / 255.0,
			_byte(_g("color_b").value(t)) / 255.0,
			_byte(_g("opacity").value(t)) / 255.0)
	var hw := _g("width").value(t) * 0.5
	var hh := _g("height").value(t) * 0.5
	_bb_texture_id = int(_g("texture_frame").discrete(t)) - 1
	var pos := global_position
	var u: Vector3
	var v: Vector3
	var n: Vector3
	var offset: Vector3
	if alignment == 0:
		# VIEWPLANE: copy the camera's U/V/N; offset toward the camera.
		u = cam.basis.x
		v = cam.basis.y
		n = -cam.basis.z
		var to_cam := cam.origin - pos
		offset = cam_offset * (to_cam.normalized() if to_cam.length() > 0.0 else Vector3.ZERO)
	else:
		# VIEWPOINT, verbatim (spec §4.3.7): the quaternion is built from
		# (axis*sin, cos) — not half-angle, not unit — and applied as q v q*.
		# Kept as the original computed it; no shipped billboard uses it.
		var cam_n := -cam.basis.z
		var d := pos - cam.origin
		n = d.normalized() if d.length() > 0.0 else cam_n
		var axis := cam_n.cross(n)
		var c := cam_n.dot(n)
		var s := sqrt(maxf(0.0, 1.0 - c * c))
		var q := Quaternion(axis.x * s, axis.y * s, axis.z * s, c)
		u = _quat_rotate(q, cam.basis.x)
		v = _quat_rotate(q, cam.basis.y)
		offset = -cam_offset * n
	_bb_transform = Transform3D(Basis(u * hw, v * hh, n), pos + offset)
	_ensure_capacity(1)
	_write_instance(0, _bb_transform, _bb_color, _rect_for(_bb_texture_id))
	_mm.visible_instance_count = 1
	_drawn = 1


static func _quat_rotate(q: Quaternion, v: Vector3) -> Vector3:
	## q * (v, 0) * conj(q) with plain Hamilton products — valid for a
	## NON-unit q (Godot's Quaternion*Vector3 asserts normalization, and so
	## does Quaternion.inverse() in 4.7: it errors and returns IDENTITY for
	## a non-unit q, so the conjugate is spelled out here — that is the
	## product the original computed).
	var conj := Quaternion(-q.x, -q.y, -q.z, q.w)
	var r := q * Quaternion(v.x, v.y, v.z, 0.0) * conj
	return Vector3(r.x, r.y, r.z)


# --- emitter (spec §4.3.3–§4.3.6) ---

func _tick_emitter(dt: float) -> void:
	# Emitter matrix handoff (the skill component's Action): on the first
	# tick after PLAY prev = cur (no trail); afterwards prev = last tick's.
	var cur := global_transform
	_prev_emitter = cur if _first_tick else _emitter
	_emitter = cur
	_first_tick = false

	var t := relative_time
	# dynamic state at the object's relative time
	_net_force = Vector3(0, -1, 0) * _g("gravity").value(t) \
			+ Vector3(_g("wind_x").value(t), _g("wind_y").value(t), _g("wind_z").value(t)) * _g("wind_force").value(t)
	_blackhole_pos = Vector3(_g("blackhole_x").value(t), _g("blackhole_y").value(t), _g("blackhole_z").value(t))
	_blackhole_force = _g("blackhole_force").value(t) * 0.01
	_drag = _g("drag").value(t) * 0.01

	# age existing particles (before spawning — the original's order)
	var keep: Array = []
	for p in _particles:
		if _age_particle(p, dt):
			keep.append(p)
	_particles = keep

	# emission: accumulator resets only when it yields >= 1
	_rate_dt += dt
	var n := int(_g("rate").value(t) * _rate_dt)
	if n >= 1:
		_rate_dt = 0.0
	var base_pos := _prev_emitter.origin
	var delta_pos := _emitter.origin - base_pos
	for i in n:
		var speed := _g("speed").value(t)
		var vel := Vector3(_g("dir_x").value(t), _g("dir_y").value(t), _g("dir_z").value(t)) * speed
		var color := Color(_byte(_g("color_r").value(t)) / 255.0, _byte(_g("color_g").value(t)) / 255.0,
				_byte(_g("color_b").value(t)) / 255.0, 1.0)
		var alpha := _g("opacity").value(t)
		var pos := base_pos + delta_pos * (float(i) / float(n))
		var dir := SfxRandom.random_direction(vel, _g("spread").value(t))
		dir = _emitter.basis * dir
		# the original's draw order: ang_vel, init_deg, life
		var ang_vel := SfxRandom.deg_units(SfxRandom.random_float(_g("ang_vel").value(t), _g("ang_vel_random").value(t)))
		var init_deg := SfxRandom.deg_units(SfxRandom.random_float(_g("init_deg").value(t), _g("init_deg_random").value(t)))
		var life := SfxRandom.random_life(_g("life").value(t), _g("life_random").value(t))
		_particles.append(_spawn(pos, dir, life, init_deg, ang_vel, color, alpha))


func _spawn(pos: Vector3, vel: Vector3, life: float, init_deg: int, ang_vel: int,
		color: Color, opacity: float) -> Particle:
	var p := Particle.new()
	p.position = pos
	p.velocity = vel
	p.total_life = life
	p.deg = init_deg
	p.ang_vel = ang_vel
	p.color = color
	p.base_opacity = opacity * 255.0
	p.scale_t = _g("scale_t").value(0.0)
	p.scale_n = _g("scale_n").value(0.0)
	p.opacity = p.base_opacity * _g("particle_opacity").value(0.0)
	p.texture_id = int(_g("texture_frame").discrete(0.0)) - 1
	return p


func _age_particle(p: Particle, dt: float) -> bool:
	p.life += dt
	if p.life > p.total_life:
		return false
	var net := _net_force - p.velocity * _drag
	p.velocity += net * dt
	p.position += p.velocity * dt
	if _blackhole_force != 0.0:
		p.position += _blackhole_force * (_blackhole_pos - p.position) * dt
	var delta := p.life / p.total_life
	p.scale_t = _g("scale_t").value(delta)
	p.opacity = p.base_opacity * _g("particle_opacity").value(delta)
	# 16-bit angle arithmetic: (u16)(ang_vel * dt) added, wrapped to 16 bits
	p.deg = (p.deg + (int(float(p.ang_vel) * dt) & 0xFFFF)) & 0xFFFF
	p.texture_id = int(_g("texture_frame").discrete(delta)) - 1
	p.scale_n = _g("scale_n").value(delta)
	return true


func _render_emitter(cam: Transform3D) -> void:
	var n := _particles.size()
	if n == 0:
		_drawn = 0
		if _mm.instance_count > 0:
			_mm.visible_instance_count = 0
		return
	var u := cam.basis.x
	var v := cam.basis.y
	if not additive:
		# back-to-front by squared distance (farther first)
		for p in _particles:
			(p as Particle).dist2 = (cam.origin - (p as Particle).position).length_squared()
		_particles.sort_custom(func(a, b): return (a as Particle).dist2 > (b as Particle).dist2)
	_ensure_capacity(n)
	for i in n:
		var p: Particle = _particles[i]
		var U: Vector3
		var V: Vector3
		if texture_direction != TEX_NONE:
			var c1 := p.velocity.dot(u)
			var c2 := p.velocity.dot(v)
			if c1 == 0.0 and c2 == 0.0:
				U = u * p.scale_t
				V = v * p.scale_n
			else:
				U = (c1 * u + c2 * v).normalized() * p.scale_t
				V = (-c2 * u + c1 * v).normalized() * p.scale_n
		else:
			U = u * p.scale_t
			V = v * p.scale_n
		if p.deg != 0:
			var c := SfxRandom.cos_units(p.deg)
			var s := SfxRandom.sin_units(p.deg)
			var U2 := U
			var V2 := V
			U = c * U2 + s * V2
			V = c * V2 - s * U2
		_write_instance(i, Transform3D(Basis(U, V, U.cross(V)), p.position),
				Color(p.color.r, p.color.g, p.color.b, float(int(p.opacity) & 0xFF) / 255.0),
				_rect_for(p.texture_id))
	_mm.visible_instance_count = n
	_drawn = n
