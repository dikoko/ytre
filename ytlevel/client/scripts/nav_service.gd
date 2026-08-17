class_name NavService
extends RefCounted
## Navigation mesh + wall grid + movement grid sampling.
##
## Data stays in ORIGINAL (D3D) space exactly as exported; queries take Godot
## coordinates and convert at the boundary (dz = -z), so the ported lookup
## math is sign-identical to the original and the y it returns is already
## Godot Y. Ports the original client's navmesh height lookup (tile-indexed
## cell walk, plane-equation height), its wall-grid line-cross test, and its
## movement attribute grid (the walkability data its pathfinder walks).
##
## Navmesh heights are true prop surfaces at raw authored heights — the
## terrain renderer also draws at raw decoded heights (no offset), so the
## two agree at handoffs; never add a render offset to either.

## Un-normalized projected cross-product floor: at or below this the cell is
## a near-vertical wall face the original client silently skips.
## ~17% of SF001001's cells are these.
const VERTICAL_EPSILON := 0.0001

var _cells := PackedFloat32Array()   # 13 floats per cell: nx,ny,nz,d, v0,v1,v2
var _cell_count := 0
var _tiles := {}                     # Vector2i(x, z) -> PackedInt32Array
var _wall_w := 0
var _wall_h := 0
var _walls := PackedByteArray()
var _move_w := 0
var _move_h := 0
var _move := PackedByteArray()       # SIGNED movement attributes (stored raw)


func load_map(code: String) -> bool:
	_cells = PackedFloat32Array()
	_cell_count = 0
	_tiles = {}
	_walls = PackedByteArray()
	_wall_w = 0
	_wall_h = 0
	_move = PackedByteArray()
	_move_w = 0
	_move_h = 0
	var any := _load_navmesh("res://assets/maps/%s/navmesh.bin" % code)
	if _load_walls("res://assets/maps/%s/walls.bin" % code):
		any = true
	if _load_move("res://assets/maps/%s/move.bin" % code):
		any = true
	return any


func has_navmesh() -> bool:
	return _cell_count > 0


func has_walls() -> bool:
	return _wall_w > 0


func has_move_grid() -> bool:
	return _move_w > 0


func _load_navmesh(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return false   # no navmesh for this map is normal (49 maps ship none)
	if f.get_buffer(4).get_string_from_ascii() != "YTNV":
		push_warning("nav_service: bad magic in %s" % path)
		return false
	var version := f.get_32()
	if version != 1:
		push_warning("nav_service: %s version %d unsupported" % [path, version])
		return false
	_cell_count = f.get_32()
	_cells = f.get_buffer(_cell_count * 13 * 4).to_float32_array()
	if _cells.size() != _cell_count * 13:
		push_warning("nav_service: %s truncated (expected %d cell floats, got %d)" %
				[path, _cell_count * 13, _cells.size()])
		_cells = PackedFloat32Array()
		_cell_count = 0
		_tiles = {}
		return false
	var tile_count := f.get_32()
	for i in tile_count:
		var tx := f.get_16()
		var tz := f.get_16()
		var n := f.get_16()
		var refs := PackedInt32Array()
		refs.resize(n)
		for j in n:
			refs[j] = f.get_32()
		_tiles[Vector2i(tx, tz)] = refs
	return _cell_count > 0


func _load_walls(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return false
	if f.get_buffer(4).get_string_from_ascii() != "YTWL":
		push_warning("nav_service: bad magic in %s" % path)
		return false
	var version := f.get_32()
	if version != 1:
		push_warning("nav_service: %s version %d unsupported" % [path, version])
		return false
	_wall_w = f.get_16()
	_wall_h = f.get_16()
	_walls = f.get_buffer(_wall_w * _wall_h)
	if _walls.size() != _wall_w * _wall_h:
		push_warning("nav_service: %s truncated (expected %d wall bytes, got %d)" %
				[path, _wall_w * _wall_h, _walls.size()])
		_walls = PackedByteArray()
		_wall_w = 0
		_wall_h = 0
		return false
	return _wall_w > 0


func _load_move(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return false
	if f.get_buffer(4).get_string_from_ascii() != "YTMV":
		push_warning("nav_service: bad magic in %s" % path)
		return false
	var version := f.get_32()
	if version != 1:
		push_warning("nav_service: %s version %d unsupported" % [path, version])
		return false
	_move_w = f.get_16()
	_move_h = f.get_16()
	_move = f.get_buffer(_move_w * _move_h)
	if _move.size() != _move_w * _move_h:
		push_warning("nav_service: %s truncated (expected %d move bytes, got %d)" %
				[path, _move_w * _move_h, _move.size()])
		_move = PackedByteArray()
		_move_w = 0
		_move_h = 0
		return false
	return _move_w > 0


func movable(x: float, z: float) -> bool:
	## The original's walkability authority (its A* pathfinder walks this
	## grid; the wall grid is line-of-sight data). Movable iff the SIGNED
	## attribute byte > 0; out-of-bounds is blocked. Same 1 m
	## truncated-world-coordinate cell convention as the wall grid.
	if _move_w == 0:
		return false
	var cx := int(x)
	var cz := int(-z)
	if cx < 0 or cz < 0 or cx >= _move_w or cz >= _move_h:
		return false
	var v := _move[cz * _move_w + cx]
	return v > 0 and v <= 127   # bytes above 127 are negative attributes


func sample(x: float, z: float) -> float:
	if _cell_count == 0:
		return NAN
	var dz := -z                      # Godot -> original space
	# `int()` truncation (toward zero) is faithful to the original's `(UTint)`
	# cast here — do NOT change this to `floor()` to "match" HeightService,
	# which floors for an unrelated reason (its own pixel-grid lookup).
	var key := Vector2i(int(x), int(dz))
	if not _tiles.has(key):
		return NAN                    # the original has no spatial fallback
	for idx: int in _tiles[key]:
		var y := _height_in_cell(idx, x, dz)
		if not is_nan(y):
			return y                  # FIRST HIT WINS, in file order
	return NAN


func _height_in_cell(idx: int, px: float, pz: float) -> float:
	var b := idx * 13
	var nx := _cells[b]
	var ny := _cells[b + 1]
	var nz := _cells[b + 2]
	var d := _cells[b + 3]
	var x0 := _cells[b + 4]
	var z0 := _cells[b + 6]
	var x1 := _cells[b + 7]
	var z1 := _cells[b + 9]
	var x2 := _cells[b + 10]
	var z2 := _cells[b + 12]
	# Projected (XZ) cross product, UN-normalized — this is both the
	# near-vertical rejection and the winding-independent inside test.
	var n_y := (z1 - z0) * (x2 - x0) - (x1 - x0) * (z2 - z0)
	if absf(n_y) <= VERTICAL_EPSILON:
		return NAN
	# Edges unrolled (0->1, 1->2, 2->0) instead of indexing through small
	# untyped Arrays — this runs per candidate cell on a per-frame path.
	# `< 0` (not `<= 0`): a point exactly on a shared edge still resolves,
	# otherwise cell seams drop through for a frame.
	if n_y * ((z1 - z0) * (px - x0) - (x1 - x0) * (pz - z0)) < 0.0:
		return NAN
	if n_y * ((z2 - z1) * (px - x1) - (x2 - x1) * (pz - z1)) < 0.0:
		return NAN
	if n_y * ((z0 - z2) * (px - x2) - (x0 - x2) * (pz - z2)) < 0.0:
		return NAN
	if ny == 0.0:
		return 0.0
	return -(nx * px + nz * pz + d) / ny


func is_wall(x: float, z: float) -> bool:
	if _wall_w == 0:
		return false
	var cx := int(x)
	var cz := int(-z)
	if cx < 0 or cz < 0 or cx >= _wall_w or cz >= _wall_h:
		return false
	return _walls[cz * _wall_w + cx] == 1


func crosses_wall(from_x: float, from_z: float, to_x: float, to_z: float) -> bool:
	if _wall_w == 0:
		return false
	# Dominant-axis DDA over cell indices, endpoint-exclusive, skipping the
	# origin cell, round-half-up on the minor axis — matching the original
	# client's wall line-cross walk. The original omits bounds checks; we
	# clamp instead of reading out of bounds.
	var px := int(from_x)
	var pz := int(-from_z)
	var tx := int(to_x)
	var tz := int(-to_z)
	var dx := tx - px
	var dz := tz - pz
	var ax := absf(float(dx))
	var az := absf(float(dz))
	if ax > az and ax != 0.0:
		var step := (az / ax) * signf(float(dz))
		for i in int(ax):
			var nz := int(floor(float(pz) + i * step + 0.5))
			var nx := px + (i if dx > 0 else -i)
			if nx == px and nz == pz:
				continue
			if _wall_at(nx, nz):
				return true
	elif az != 0.0:
		var step := (ax / az) * signf(float(dx))
		for i in int(az):
			var nx := int(floor(float(px) + i * step + 0.5))
			var nz := pz + (i if dz > 0 else -i)
			if nx == px and nz == pz:
				continue
			if _wall_at(nx, nz):
				return true
	return false


func _wall_at(cx: int, cz: int) -> bool:
	if cx < 0 or cz < 0 or cx >= _wall_w or cz >= _wall_h:
		return false
	return _walls[cz * _wall_w + cx] == 1
