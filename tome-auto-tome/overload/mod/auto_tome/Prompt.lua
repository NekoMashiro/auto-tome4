-- Describe the top window and apply one of the six answers.
local M = {}

local DIRECTIONS = {
	[1] = {-1, 1}, [2] = {0, 1}, [3] = {1, 1},
	[4] = {-1, 0}, [6] = {1, 0},
	[7] = {-1, -1}, [8] = {0, -1}, [9] = {1, -1},
}

function M.plain(value)
	if value == nil then return "" end
	if type(value) == "string" then return (value:gsub("#[^#]+#", "")) end
	if type(value) == "table" and type(value.toString) == "function" then
		local ok, text = pcall(value.toString, value)
		if ok and type(text) == "string" then return (text:gsub("#[^#]+#", "")) end
	end
	return tostring(value)
end

local function class_name(dialog)
	return type(dialog) == "table" and dialog.__CLASSNAME or ""
end

local function top_dialog(game)
	local dialogs = game.dialogs
	if type(dialogs) ~= "table" then return nil end
	for i = #dialogs, 1, -1 do
		local dialog = dialogs[i]
		-- Dialog skips drawing when __hidden is set. Running uses that for its stop notice.
		-- __showup is only the pop-in animation; a normal window has it too and still needs an answer.
		if type(dialog) == "table" and not dialog.__hidden and not dialog.hidden and not dialog.hide then return dialog end
	end
end

function M.blocking(game)
	if not game or not game.player or not game.level then return false end
	if game.target_co then return true end
	if game.player.resting or game.player.running then return true end
	return top_dialog(game) ~= nil
end

-- Rest and run each register a "press Enter to stop" notice. Neither is a question for the AI.
function M.needs_answer(game)
	if not game or not game.player then return false end
	if game.target_co then return true end
	local dialog = top_dialog(game)
	if not dialog then return false end
	local resting = game.player.resting
	if type(resting) == "table" and resting.dialog == dialog then return false end
	local running = game.player.running
	if type(running) == "table" and running.dialog == dialog then return false end
	return true
end

-- nil while a multi-tick action should keep the current request open.
function M.settled(game)
	local player = game and game.player
	if not player or not player.x or player.dead then return "completed" end
	-- A real window opened during the run still has to be answered. The run itself does not.
	if M.needs_answer(game) then return "awaiting_input" end
	if player.resting or player.running then return nil end
	local enough = false
	pcall(function() enough = player:enoughEnergy() and true or false end)
	if enough then return "completed" end
	return nil
end

local function levelup_dialog(dialog)
	return class_name(dialog):find("LevelupDialog", 1, true) ~= nil
end

local function finish_levelup(dialog)
	local exit = dialog.key and dialog.key.virtuals and dialog.key.virtuals.EXIT
	if type(exit) == "function" then exit() end
end

local function push_option(options, dialog, suffix, label, apply)
	options[#options + 1] = {
		option_id = tostring(dialog) .. ":" .. suffix,
		label = M.plain(label),
		apply = apply,
	}
end

local function seen_list(seen, list)
	if type(list) ~= "table" or seen[list] then return false end
	seen[list] = true
	return list[1] ~= nil
end

local function row_label(item)
	if type(item) ~= "table" then return tostring(item) end
	if item.object and type(item.object.getName) == "function" then
		local ok, name = pcall(item.object.getName, item.object, {do_color = false, no_count = false})
		if ok and name then return name end
	end
	return item.rawname or item.name or item.action or "option"
end

local function collect_rows(dialog, options)
	local seen = {}
	local function add(list)
		if not seen_list(seen, list) or type(dialog.use) ~= "function" then return end
		for index, item in ipairs(list) do
			local row = item
			push_option(options, dialog, "row" .. index, row_label(item), function()
				dialog:use(row)
			end)
		end
	end
	add(dialog.list)
	if type(dialog.c_list) == "table" then add(dialog.c_list.list) end
	if type(dialog.c_inven) == "table" and type(dialog.c_inven.c_inven) == "table" then
		add(dialog.c_inven.c_inven.list)
	end
end

local function collect_buttons(dialog, options)
	if type(dialog.uis) ~= "table" then return end
	local index = 0
	for _, entry in ipairs(dialog.uis) do
		local ui = type(entry) == "table" and entry.ui or nil
		if type(ui) == "table" and type(ui.fct) == "function" and not ui.list and not ui.hidden and not ui.hide and ui.visible ~= false then
			index = index + 1
			local button = ui
			push_option(options, dialog, "button" .. index, ui.text or ("Button " .. index), function()
				button.fct()
			end)
		end
	end
end

local function as_text(value)
	if type(value) == "string" or (type(value) == "table" and type(value.toString) == "function") then
		return M.plain(value)
	end
	return nil
end

local function push_text(parts, seen, value)
	local text = as_text(value)
	if not text then return end
	text = text:gsub("^%s+", ""):gsub("%s+$", "")
	if text == "" or seen[text] then return end
	seen[text] = true
	parts[#parts + 1] = text
end

local function collect_widget_text(ui, parts, seen, visited)
	if type(ui) ~= "table" or visited[ui] then return end
	visited[ui] = true
	local before = #parts
	if type(ui.fct) ~= "function" then push_text(parts, seen, ui.text) end
	if #parts == before and type(ui.list) == "table" then
		for _, item in ipairs(ui.list) do
			if type(item) == "string" then push_text(parts, seen, item)
			elseif type(item) == "table" then push_text(parts, seen, item.text or item.name or item.rawname) end
		end
	end
	if type(ui.uis) == "table" then
		for _, entry in ipairs(ui.uis) do
			if type(entry) == "table" then collect_widget_text(entry.ui or entry, parts, seen, visited) end
		end
	end
end

local function dialog_body(dialog)
	local parts, seen, visited = {}, {}, {}
	push_text(parts, seen, dialog.text)
	collect_widget_text(dialog, parts, seen, visited)
	if #parts == 0 then return nil end
	return table.concat(parts, "\n")
end

local function call_text(fn, ...)
	local ok, text = pcall(fn, ...)
	if ok then return as_text(text) end
	return nil
end

local function stat_definition(actor, stat)
	local defs = actor and actor.stats_def
	if type(defs) ~= "table" then return nil end
	if type(defs[stat]) == "table" then return defs[stat] end
	local number = tonumber(stat)
	if number and type(defs[number]) == "table" then return defs[number] end
end

local function node_desc(item, actor)
	local function text_of(value)
		if type(value) == "function" then
			return call_text(value, item, actor) or call_text(value, actor)
		end
		return as_text(value)
	end
	local desc = text_of(item.desc or item.description)
	if (desc == nil or desc == "") and item.talent and actor and type(actor.getTalentFromId) == "function" and type(actor.getTalentFullDescription) == "function" then
		local talent = actor:getTalentFromId(item.talent)
		if type(talent) == "table" then
			desc = call_text(actor.getTalentFullDescription, actor, talent)
		end
	end
	if (desc == nil or desc == "") and item.stat ~= nil then
		local def = stat_definition(actor, item.stat)
		if type(def) == "table" then desc = text_of(def.description or def.desc) end
	end
	if type(desc) ~= "string" or desc == "" then return nil end
	return desc
end

local function stat_nodes(dialog, actor)
	local nodes = {}
	local function add(item, kind, id)
		if type(item) ~= "table" then return end
		local label_value = item.rawname or item.name or id
		if type(label_value) == "function" then
			local ok, text = pcall(label_value, item)
			if ok and text ~= nil then label_value = text end
		end
		local node = {
			node = kind .. ":" .. id,
			label = M.plain(label_value),
			item = item,
		}
		local desc = node_desc(item, actor)
		if desc then node.desc = desc end
		nodes[#nodes + 1] = node
	end
	for _, category in ipairs(dialog.tree_stats or {}) do
		for _, item in ipairs(category.nodes or {}) do
			if item.stat ~= nil then add(item, "stat", tostring(item.stat)) end
		end
	end
	local function walk(tree)
		for _, category in ipairs(tree or {}) do
			if category.type then add(category, "category", category.type) end
			for _, item in ipairs(category.nodes or {}) do
				if item.talent then add(item, "talent", tostring(item.talent)) end
			end
		end
	end
	walk(dialog.ctree)
	walk(dialog.gtree)
	return nodes
end

local function aim_mode(game)
	local typ = game.target and game.target.target_type
	if type(typ) == "table" and typ.immediate_keys then return "direction" end
	return "grid"
end

function M.describe(game)
	if game.target_co then
		return {kind = "aim", mode = aim_mode(game), options = {}}
	end
	local dialog = top_dialog(game)
	if not dialog then return {kind = "none", options = {}} end
	local name = class_name(dialog)
	if name:find("GetQuantity", 1, true) then
		local max_qty = dialog.c_box and dialog.c_box.max or nil
		return {kind = "quantity", title = M.plain(dialog.title), maximum = max_qty, text = dialog_body(dialog), options = {}}
	end
	if name:find("GetText", 1, true) then
		return {kind = "text", title = M.plain(dialog.title), text = dialog_body(dialog), options = {}}
	end
	local options = {}
	if levelup_dialog(dialog) then
		push_option(options, dialog, "finish", "Finish", function() finish_levelup(dialog) end)
		collect_buttons(dialog, options)
		local full = stat_nodes(dialog, dialog.actor or game.player)
		local nodes = {}
		for _, node in ipairs(full) do
			local public = {node = node.node, label = node.label}
			if node.desc then public.desc = node.desc end
			nodes[#nodes + 1] = public
		end
		return {kind = "adjust", title = M.plain(dialog.title), text = dialog_body(dialog), options = options, nodes = nodes, _nodes = full, _options = options}
	end
	collect_rows(dialog, options)
	collect_buttons(dialog, options)
	return {kind = "choose", title = M.plain(dialog.title), text = dialog_body(dialog), options = options, _options = options}
end

local function public_prompt(prompt)
	local options = {}
	for _, option in ipairs(prompt.options or {}) do
		options[#options + 1] = {option_id = option.option_id, label = option.label}
	end
	local out = {kind = prompt.kind, options = options}
	if prompt.mode then out.mode = prompt.mode end
	if prompt.title and prompt.title ~= "" then out.title = prompt.title end
	if prompt.text and prompt.text ~= "" then out.text = prompt.text end
	if prompt.maximum then out.maximum = prompt.maximum end
	if prompt.nodes then out.nodes = prompt.nodes end
	return out
end

function M.public(game)
	return public_prompt(M.describe(game))
end

function M.option_labels(game)
	local prompt = M.describe(game)
	local options = {}
	for _, option in ipairs(prompt.options or {}) do
		options[#options + 1] = {label = option.label}
	end
	return options
end

-- Sentence for a world command that lost to an open window. Long lists stay in options.
function M.busy_reply(game)
	local player = game and game.player
	if player and player.resting then return "The character is resting.", {} end
	if player and player.running then return "The character is running.", {} end
	local prompt = M.describe(game)
	local options = {}
	for _, option in ipairs(prompt.options or {}) do
		options[#options + 1] = {label = option.label}
	end
	if prompt.kind == "aim" then
		return "A target prompt is open. Answer it with aim or cancel before a world command.", options
	end
	local title = prompt.title or ""
	local text = prompt.text or ""
	local sentence = "A window is open"
	if title ~= "" then sentence = sentence .. ": " .. title end
	sentence = sentence .. "."
	if text ~= "" then sentence = sentence .. " " .. text end
	sentence = sentence .. " Choices are in options."
	return sentence, options
end

local function find_option(prompt, option_id)
	for _, option in ipairs(prompt._options or prompt.options or {}) do
		if option.option_id == option_id then return option end
	end
end

local function actor_by_id(game, target_id)
	local prefix = "actor-"
	if type(target_id) ~= "string" or target_id:sub(1, #prefix) ~= prefix then return nil end
	local uid = tonumber(target_id:sub(#prefix + 1))
	if not uid or not game.level or type(game.level.entities) ~= "table" then return nil end
	local actor = game.level.entities[uid]
	if type(actor) == "table" and actor.x and not actor.dead then return actor end
end

function M.apply(game, action)
	local prompt = M.describe(game)
	local kind = action.type
	if kind == "cancel" then
		if game.target_co and game.targetmode_key and game.targetmode_key.virtuals then
			local exit = game.targetmode_key.virtuals.EXIT
			if type(exit) == "function" then exit() end
			return true
		end
		local dialog = top_dialog(game)
		if not dialog then return false, "nothing_to_cancel" end
		if levelup_dialog(dialog) and type(dialog.cancel) == "function" then
			dialog:cancel()
			game:unregisterDialog(dialog)
			return true
		end
		local exit = dialog.key and dialog.key.virtuals and dialog.key.virtuals.EXIT
		if type(exit) == "function" then
			exit()
			return true
		end
		game:unregisterDialog(dialog)
		return true
	end
	if kind == "choose" then
		if prompt.kind ~= "choose" and prompt.kind ~= "adjust" then return false, "prompt_mismatch" end
		local label = action.label
		if type(label) == "string" and label ~= "" then
			local matches = {}
			for _, option in ipairs(prompt._options or prompt.options or {}) do
				if option.label == label then matches[#matches + 1] = option end
			end
			if #matches ~= 1 or type(matches[1].apply) ~= "function" then
				return false, #matches > 1 and "ambiguous_option" or "unknown_option"
			end
			matches[1].apply()
			return true
		end
		local option = find_option(prompt, action.option_id)
		if not option or type(option.apply) ~= "function" then return false, "unknown_option" end
		option.apply()
		return true
	end
	if kind == "quantity" then
		if prompt.kind ~= "quantity" then return false, "prompt_mismatch" end
		local dialog = top_dialog(game)
		local qty = action.quantity
		if type(qty) ~= "number" or qty % 1 ~= 0 then return false, "invalid_quantity" end
		if dialog.c_box then
			if type(dialog.c_box.setNumber) == "function" then dialog.c_box:setNumber(qty)
			else dialog.c_box.number = qty end
		end
		dialog:okclick()
		return true
	end
	if kind == "text" then
		if prompt.kind ~= "text" then return false, "prompt_mismatch" end
		local dialog = top_dialog(game)
		if type(action.text) ~= "string" then return false, "invalid_text" end
		if type(dialog.setText) == "function" then dialog:setText(action.text) end
		dialog:okclick()
		return true
	end
	if kind == "adjust" then
		if prompt.kind ~= "adjust" then return false, "prompt_mismatch" end
		if action.delta ~= 1 and action.delta ~= -1 then return false, "invalid_delta" end
		local dialog = top_dialog(game)
		for _, node in ipairs(prompt._nodes or {}) do
			if node.node == action.node then
				dialog:onUseTalent(node.item, action.delta > 0)
				return true
			end
		end
		return false, "unknown_node"
	end
	if kind == "aim" then
		if prompt.kind ~= "aim" then return false, "prompt_mismatch" end
		local target = game.target and game.target.target
		if type(target) ~= "table" then return false, "target_unavailable" end
		local x, y, entity
		if action.direction ~= nil then
			local delta = DIRECTIONS[action.direction]
			if not delta then return false, "invalid_direction" end
			x = game.player.x + delta[1]
			y = game.player.y + delta[2]
		elseif action.target_id ~= nil then
			entity = actor_by_id(game, action.target_id)
			if not entity then return false, "target_lost" end
			x, y = entity.x, entity.y
		elseif action.x ~= nil or action.y ~= nil then
			if type(action.x) ~= "number" or type(action.y) ~= "number" then return false, "invalid_coordinate" end
			x, y = action.x, action.y
		else
			return false, "invalid_aim"
		end
		target.x, target.y, target.entity = x, y, entity
		local accept = game.targetmode_key and game.targetmode_key.virtuals and game.targetmode_key.virtuals.ACCEPT
		if type(accept) ~= "function" then return false, "target_unavailable" end
		accept()
		return true
	end
	return false, "unknown_answer"
end

return M
