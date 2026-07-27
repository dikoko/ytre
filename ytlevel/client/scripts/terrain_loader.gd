@tool
extends MeshInstance3D
## Loads a heightmap image and generates terrain mesh with tile textures.

func _ready() -> void:
	var hwt_path: String = get_meta("heightmap_path", "")
	if hwt_path == "":
		push_warning("terrain_loader: no heightmap_path metadata set")
		return
	print("terrain_loader: starting with heightmap=%s" % hwt_path)
	_generate_terrain(hwt_path)


func _generate_terrain(hwt_path: String) -> void:
	var tex := load(hwt_path) as Texture2D
	if tex == null:
		push_warning("terrain_loader: failed to load heightmap: %s" % hwt_path)
		return
	var img := tex.get_image()
	if img == null:
		return
	img.decompress()

	var width := img.get_width()
	var height := img.get_height()

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for z in range(height):
		for x in range(width):
			var pixel := img.get_pixel(x, z)
			# RG16 heightmap: R=high byte, G=low byte (see height_service.gd).
			# Raw decoded height, no offset: the original renders terrain at
			# the stored heightmap value. A render sink here opens
			# see-through slits under prop edges at grazing camera angles.
			var h: float = (roundf(pixel.r * 255.0) * 256.0
					+ roundf(pixel.g * 255.0)) * 0.1 - 10.0
			var u := float(x) / float(width - 1)
			var v := float(z) / float(height - 1)
			st.set_uv(Vector2(u, v))
			st.set_normal(Vector3.UP)
			st.add_vertex(Vector3(float(x), h, -float(z)))

	# Z negation flips normals, so reverse winding to restore UP normals
	for z in range(height - 1):
		for x in range(width - 1):
			var i := z * width + x
			st.add_index(i)
			st.add_index(i + width)
			st.add_index(i + 1)
			st.add_index(i + 1)
			st.add_index(i + width)
			st.add_index(i + width + 1)

	st.generate_normals()
	mesh = st.commit()

	# Try to load tile material, fall back to green
	var tilemap_path: String = get_meta("tilemap_path", "")
	var tiles_dir: String = get_meta("tiles_dir", "")

	if tilemap_path != "" and tiles_dir != "":
		_apply_tile_material(tilemap_path, tiles_dir)
	else:
		_apply_fallback_material()

	print("terrain_loader: done (%dx%d)" % [width, height])


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_G:
		visible = !visible
		print("terrain_loader: terrain visible=%s" % visible)


func _apply_tile_material(tilemap_path: String, tiles_dir: String) -> void:
	# Load tilemap as raw Image to bypass Godot's lossy VRAM compression.
	# Index values must be exact integers — compression would mangle them.
	var tilemap_img := Image.new()
	var abs_path := ProjectSettings.globalize_path(tilemap_path)
	var err := tilemap_img.load(abs_path)
	if err != OK:
		push_warning("terrain_loader: failed to load tilemap image: %s (err=%d)" % [abs_path, err])
		_apply_fallback_material()
		return
	var tilemap_tex := ImageTexture.create_from_image(tilemap_img)
	print("terrain_loader: tilemap loaded raw %dx%d (bypassing import compression)" % [tilemap_img.get_width(), tilemap_img.get_height()])

	var dir := DirAccess.open(tiles_dir)
	if dir == null:
		push_warning("terrain_loader: failed to open tiles dir: %s" % tiles_dir)
		_apply_fallback_material()
		return

	# Collect all combo_NNN.png files
	var combo_files: Array[String] = []
	dir.list_dir_begin()
	var fname := dir.get_next()
	while fname != "":
		if fname.begins_with("combo_") and fname.ends_with(".png"):
			combo_files.append(fname)
		fname = dir.get_next()
	dir.list_dir_end()
	combo_files.sort()

	if combo_files.is_empty():
		push_warning("terrain_loader: no combo PNGs found in %s" % tiles_dir)
		_apply_fallback_material()
		return

	# Load combos as raw Images (like the tilemap/visibility above): the tiles
	# dirs are .gdignore'd so the editor never scans/imports/thumbnails the
	# ~77k combo PNGs (a full-project preview pass exhausts the renderer's
	# texture RID pool and crashes the editor). We rebuilt RGB8+mipmaps at
	# runtime even when these went through the importer, so nothing is lost.
	var first_img := Image.new()
	if first_img.load(ProjectSettings.globalize_path(tiles_dir.path_join(combo_files[0]))) != OK:
		push_warning("terrain_loader: failed to load first combo texture")
		_apply_fallback_material()
		return
	var tile_size := first_img.get_width()
	print("terrain_loader: loading %d combo textures (%dx%d)..." % [combo_files.size(), tile_size, tile_size])

	# Build Texture2DArray from combo PNGs
	var images: Array[Image] = []
	var load_failed := 0
	for combo_file in combo_files:
		var combo_path: String = ProjectSettings.globalize_path(tiles_dir.path_join(combo_file))
		var combo_img := Image.new()
		if combo_img.load(combo_path) == OK:
			combo_img.convert(Image.FORMAT_RGB8)
			combo_img.generate_mipmaps()
			images.append(combo_img)
		else:
			load_failed += 1
			var fallback := Image.create(tile_size, tile_size, true, Image.FORMAT_RGB8)
			fallback.fill(Color(1, 0, 1))
			fallback.generate_mipmaps()
			images.append(fallback)
	if load_failed > 0:
		push_warning("terrain_loader: %d combo textures failed to load" % load_failed)

	var tex_array := Texture2DArray.new()
	var arr_err := tex_array.create_from_images(images)
	if arr_err != OK:
		push_warning("terrain_loader: Texture2DArray creation failed with error %d" % arr_err)
		_apply_fallback_material()
		return
	print("terrain_loader: Texture2DArray created (%d layers)" % images.size())

	# Load and assign shader
	var shader := load("res://shaders/terrain_tiles.gdshader") as Shader
	if shader == null:
		push_warning("terrain_loader: shader not found at res://shaders/terrain_tiles.gdshader")
		_apply_fallback_material()
		return

	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.set_shader_parameter("tilemap", tilemap_tex)
	mat.set_shader_parameter("tile_textures", tex_array)
	mat.set_shader_parameter("palette_count", images.size())

	# Fixed-function sun from the map's .plt (exported as node metadata by
	# 30_export_map.py). Shader defaults (straight-down white sun) apply when
	# the metadata is absent.
	if has_meta("sun_direction"):
		mat.set_shader_parameter("sun_direction", get_meta("sun_direction"))
	if has_meta("sun_diffuse"):
		var sd: Color = get_meta("sun_diffuse")
		mat.set_shader_parameter("sun_diffuse", Vector3(sd.r, sd.g, sd.b))
	if has_meta("sun_ambient"):
		var sa: Color = get_meta("sun_ambient")
		mat.set_shader_parameter("sun_ambient", Vector3(sa.r, sa.g, sa.b))
	PointLights.apply(self, mat)

	# Load visibility map (also raw to bypass compression)
	var vis_path: String = get_meta("visibility_path", "")
	if vis_path != "":
		var vis_img := Image.new()
		var vis_abs := ProjectSettings.globalize_path(vis_path)
		if vis_img.load(vis_abs) == OK:
			var vis_tex := ImageTexture.create_from_image(vis_img)
			mat.set_shader_parameter("visibility_map", vis_tex)
			print("terrain_loader: loaded visibility map raw from %s" % vis_path)

	material_override = mat
	print("terrain_loader: applied tile shader (%d combos, %dx%d tiles)" % [images.size(), tile_size, tile_size])


func _apply_fallback_material() -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.2, 0.6, 0.1)
	material_override = mat
	print("terrain_loader: applied fallback green material")
