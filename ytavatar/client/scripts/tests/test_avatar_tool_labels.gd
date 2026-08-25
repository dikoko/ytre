extends SceneTree
## Headless regression checks for the avatar tool's equipment slot labels.
## 2026-08-24 report: equipping a glorb left the Glorb row reading "None" —
## the label branch read current_part_names["glorb"], which nothing ever
## populates on equip (only cleared on unequip). Labels must derive from
## the variant arrays, like blade/mura/spirit do.
## Run: "$GODOT_BIN" --path client --headless --script scripts/tests/test_avatar_tool_labels.gd

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok - ", label)
	else:
		_fails += 1
		printerr("FAIL - ", label)


func _init() -> void:
	var scene := load("res://scenes/avatar_tool.tscn") as PackedScene
	var tool_node = scene.instantiate()
	get_root().add_child(tool_node)
	for i in 5:
		await process_frame        # _ready builds avatar + GUI

	# Equip one weapon per class; each row label must show the variant.
	tool_node._set_equipment(tool_node.EquipmentType.GLORB)
	await process_frame
	var glorb_text: String = tool_node.slot_name_labels["glorb"].text
	_check(glorb_text != "None" and glorb_text.begins_with("glorb_"),
			"glorb label shows the equipped variant (got %s)" % glorb_text)

	# Cycling the glorb variant must update the label too.
	tool_node._set_equipment(tool_node.EquipmentType.GLORB)
	await process_frame
	var glorb_text2: String = tool_node.slot_name_labels["glorb"].text
	_check(glorb_text2.begins_with("glorb_") and glorb_text2 != glorb_text,
			"glorb label follows variant cycling (got %s -> %s)" % [glorb_text, glorb_text2])

	tool_node._set_equipment(tool_node.EquipmentType.BLADE)
	await process_frame
	_check(tool_node.slot_name_labels["blade"].text.begins_with("blade_"),
			"blade label shows the equipped variant")
	_check(tool_node.slot_name_labels["glorb"].text == "None",
			"glorb label resets when another class is equipped")

	tool_node._unequip()
	await process_frame
	_check(tool_node.slot_name_labels["blade"].text == "None",
			"blade label resets on unequip")

	if _fails == 0:
		print("ALL OK")
	else:
		printerr("%d FAILURES" % _fails)
	quit(1 if _fails else 0)
