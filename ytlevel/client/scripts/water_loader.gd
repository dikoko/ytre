extends Node3D
## Builds the map's water surfaces from water.json (written by
## 32_export_water.py from the original .wtr) and assigns the
## fixed-function water shader with per-region animation params.
## Vertex colors carry the baked D3D diffuse (the original renders water
## with lighting OFF — no FF sun/point terms here).

const WATER_SHADER_PATH := "res://shaders/water_ff.gdshader"


func _ready() -> void:
	var json_path: String = get_meta("water_json", "")
	if json_path == "":
		return
	var f := FileAccess.open(json_path, FileAccess.READ)
	if f == null:
		push_warning("water_loader: cannot open %s" % json_path)
		return
	var data: Dictionary = JSON.parse_string(f.get_as_text())
	var shader: Shader = load(WATER_SHADER_PATH)

	var built := 0
	for obj in data["objects"]:
		var mat := ShaderMaterial.new()
		mat.shader = shader
		var textures: Array = data["textures"]
		if obj["texture0"] < textures.size():
			mat.set_shader_parameter("tex_stage0", load(textures[obj["texture0"]]))
		if obj["texture1"] < textures.size():
			mat.set_shader_parameter("tex_stage1", load(textures[obj["texture1"]]))
		mat.set_shader_parameter("anim_type", int(obj["type"]))
		mat.set_shader_parameter("mat0", PackedFloat32Array(obj["mat_info"][0]))
		mat.set_shader_parameter("mat1", PackedFloat32Array(obj["mat_info"][1]))

		for mesh_id in obj["mesh_ids"]:
			var m: Dictionary = data["meshes"][int(mesh_id)]
			var mi := MeshInstance3D.new()
			mi.mesh = _build_mesh(m)
			mi.material_override = mat
			add_child(mi)
			built += 1
	if built:
		print("water_loader: built %d water surfaces" % built)

	var beach_points := 0
	for obj in data["objects"]:
		var pts: Dictionary = obj.get("beach_points", {})
		beach_points += pts.get("positions", []).size() / 3
	if beach_points > 0 and data.has("beach"):
		var beach := BeachSprites.new()
		beach.name = "BeachSprites"
		beach.setup(data)
		add_child(beach)
		print("water_loader: beach emitter with %d shore points" % beach_points)


func _build_mesh(m: Dictionary) -> ArrayMesh:
	var positions := PackedVector3Array()
	var normals := PackedVector3Array()
	var colors := PackedColorArray()
	var uvs := PackedVector2Array()
	var pos: Array = m["positions"]
	var nrm: Array = m["normals"]
	var col: Array = m["colors"]
	var uv: Array = m["uvs"]
	for i in range(pos.size() / 3):
		positions.append(Vector3(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]))
		normals.append(Vector3(nrm[i * 3], nrm[i * 3 + 1], nrm[i * 3 + 2]))
		colors.append(Color(col[i * 4], col[i * 4 + 1], col[i * 4 + 2], col[i * 4 + 3]))
		uvs.append(Vector2(uv[i * 2], uv[i * 2 + 1]))
	var indices := PackedInt32Array()
	for idx in m["indices"]:
		indices.append(int(idx))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = positions
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
