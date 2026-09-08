# client/scripts/sfx_random.gd
class_name SfxRandom
extends RefCounted
## The original particle library's random source (spec §3.3): NOT a PRNG —
## two shipped tables (10,000 ints in [2, 32763], 10,000 floats in (0,1))
## walked by two process-wide cursors that wrap. Deterministic: reset() +
## the same draw sequence reproduces the same particles. Angle helpers are
## the 16-bit integer units of spec §3.4 (65,536 = 360°, 182 units/degree).
## Python mirror + parity fixture: tools/avatar_export/src/sfx_random_ref.py.

const TABLE_PATH := "res://assets/effects/sfx_random.json"
const RAND_MAX := 32767.0
const ANGLE_360 := 65536
const ANGLE_1 := 182  # 65536 / 360, integer division — the original's angle unit

static var _ints: PackedInt32Array = PackedInt32Array()
static var _floats: PackedFloat64Array = PackedFloat64Array()
static var _ii := 0
static var _fi := 0


static func load_tables() -> bool:
	if not _ints.is_empty():
		return true
	if not FileAccess.file_exists(TABLE_PATH):
		push_error("SfxRandom: missing " + TABLE_PATH)
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(TABLE_PATH))
	if not (parsed is Dictionary) or not parsed.has("ints") or not parsed.has("floats"):
		push_error("SfxRandom: malformed " + TABLE_PATH)
		return false
	for v in parsed["ints"]:
		_ints.append(int(v))
	for v in parsed["floats"]:
		_floats.append(float(v))
	reset()
	return not _ints.is_empty() and not _floats.is_empty()


static func reset() -> void:
	_ii = 0
	_fi = 0


static func cursors() -> Vector2i:
	return Vector2i(_ii, _fi)


static func irand() -> int:
	if _ints.is_empty() and not load_tables():
		return 0
	var v := _ints[_ii]
	_ii = (_ii + 1) % _ints.size()
	return v


static func frand() -> float:
	if _floats.is_empty() and not load_tables():
		return 0.0
	var v := _floats[_fi]
	_fi = (_fi + 1) % _floats.size()
	return v


static func deg_units(x: float) -> int:
	## The original's float-to-angle conversion: (unsigned short)(x * 182) —
	## truncate toward zero, wrap to 16 bits. A negative rate wraps to a
	## large positive one (spec §3.4/§8).
	return int(x * ANGLE_1) & 0xFFFF


static func sin_units(u: int) -> float:
	return sin(float(u & 0xFFFF) * TAU / float(ANGLE_360))


static func cos_units(u: int) -> float:
	return cos(float(u & 0xFFFF) * TAU / float(ANGLE_360))


static func random_float(base: float, spread: float) -> float:
	var half := RAND_MAX * 0.5
	return base + spread * ((float(irand()) - half) / half)


static func random_life(life_max: float, life_random: float) -> float:
	life_max = absf(life_max)
	life_random = absf(life_random)
	if life_random > life_max:
		life_random = life_max
	return life_max - frand() * life_random


static func random_direction(dir: Vector3, spread_deg: float) -> Vector3:
	## Cone around `dir`: cos(alpha)·dir + sin(alpha)·|dir|·(random unit
	## tangent ⟂ dir). Draw order: 1 float (alpha), then the tangent's z, y,
	## x (the original's draw order) — 3 ints.
	var alpha := deg_units(frand() * spread_deg)
	var normal := dir * cos_units(alpha)
	var tz := random_float(0.0, 1.0)
	var ty := random_float(0.0, 1.0)
	var tx := random_float(0.0, 1.0)
	var length := dir.length()
	if length != 0.0:
		if dir.z == 0.0:
			if dir.y == 0.0:
				tx = 0.0
			elif dir.x == 0.0:
				ty = 0.0
			else:
				tx = -(dir.y * ty) / dir.x
		else:
			if dir.y == 0.0:
				if dir.x == 0.0:
					tz = 0.0
				else:
					tx = -(dir.z * tz) / dir.x
			else:
				if dir.x == 0.0:
					ty = -(dir.z * tz) / dir.y
				else:
					tx = (-dir.y * ty - dir.z * tz) / dir.x
	var tangent := Vector3(tx, ty, tz)
	if tangent.length() > 0.0:
		tangent = tangent.normalized()
	tangent *= sin_units(alpha) * length
	return normal + tangent
