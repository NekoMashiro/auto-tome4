-- Player-visible snapshot small enough for the test client to choose an action.
local Json = require "mod.auto_tome.Json"
local Prompt = require "mod.auto_tome.Prompt"
local M = {}

local function lines_of(value)
	if type(value) ~= "table" then return {} end
	local out = {}
	for i = 1, math.min(#value, 12) do
		out[#out + 1] = Prompt.plain(value[i])
	end
	return out
end

local function recent_log(game)
	local display = game.uiset and game.uiset.logdisplay or game.logdisplay
	if type(display) == "table" and type(display.getLines) == "function" then
		local ok, lines = pcall(display.getLines, display, 12)
		if ok then return lines_of(lines) end
	end
	return {}
end

local function object_desc(object)
	if type(object) ~= "table" then return nil end
	local text = nil
	if type(object.getDesc) == "function" then
		local ok, value = pcall(function() return object:getDesc({do_color = false}) end)
		if ok then text = value end
	end
	if type(text) ~= "string" or text == "" then text = object.desc end
	if type(text) ~= "string" or text == "" then return nil end
	text = Prompt.plain(text)
	if #text > 1200 then text = text:sub(1, 1200) end
	return text
end

local function item_record(object, extra)
	local record = {
		id = "item-" .. tostring(object.uid or 0),
		name = Prompt.plain(object.getName and object:getName({do_color = false}) or object.name),
		number = type(object.getNumber) == "function" and object:getNumber() or 1,
	}
	for key, value in pairs(extra or {}) do record[key] = value end
	return record
end

local function inventory_items(player)
	local items = {}
	local inven = player.getInven and player:getInven("INVEN") or nil
	if type(inven) ~= "table" then return items end
	for slot, object in ipairs(inven) do
		if type(object) == "table" then
			items[#items + 1] = item_record(object, {slot = slot})
		end
	end
	return items
end

local function floor_items(game, player)
	local items = {}
	local map = game.level and game.level.map
	if not map or not player.x then return items end
	local index = 1
	while true do
		local object = map:getObject(player.x, player.y, index)
		if not object then break end
		local extra = {x = player.x, y = player.y}
		local desc = object_desc(object)
		if desc then extra.desc = desc end
		items[#items + 1] = item_record(object, extra)
		index = index + 1
	end
	return items
end

local function visible_actors(game, player)
	local actors = {}
	local entities = game.level and game.level.entities or {}
	for _, actor in pairs(entities) do
		if type(actor) == "table" and actor.__is_actor and actor ~= player and actor.x and not actor.dead then
			local ok, seen = pcall(function()
				return player:canSee(actor) and game.level.map.seens(actor.x, actor.y) and true or false
			end)
			if ok and seen then
				local reaction = 0
				pcall(function() reaction = player:reactionToward(actor) end)
				actors[#actors + 1] = {
					id = "actor-" .. tostring(actor.uid),
					name = Prompt.plain(actor.name),
					x = actor.x, y = actor.y,
					life = actor.life, max_life = actor.max_life,
					hostile = reaction < 0,
				}
			end
		end
	end
	table.sort(actors, function(a, b) return a.id < b.id end)
	return actors
end

local function talents_of(player)
	local talents = {}
	for id, level in pairs(player.talents or {}) do
		local talent = player.getTalentFromId and player:getTalentFromId(id) or nil
		if type(talent) == "table" and type(level) == "number" and level > 0 and (talent.mode == "activated" or talent.mode == "sustained") then
			talents[#talents + 1] = {
				id = id,
				name = Prompt.plain(talent.name),
				mode = talent.mode,
				sustained = player.sustain_talents and player.sustain_talents[id] and true or false,
			}
		end
	end
	table.sort(talents, function(a, b) return a.id < b.id end)
	return talents
end

local function mainhand_name(player)
	local inven = player.getInven and player:getInven("MAINHAND") or nil
	local object = type(inven) == "table" and inven[1] or nil
	if type(object) ~= "table" then return "" end
	return Prompt.plain(object.getName and object:getName({do_color = false, no_count = true}) or object.name)
end

function M.snapshot(game)
	local player = game and game.player
	if not player or not player.x then
		return {in_game = false, prompt = {kind = "none", options = Json.array({})}}
	end
	local prompt = Prompt.public(game)
	prompt.options = Json.array(prompt.options or {})
	if prompt.nodes then prompt.nodes = Json.array(prompt.nodes) end
	local activity = nil
	if player.resting then activity = "rest"
	elseif player.running then activity = "run" end
	local enough = false
	pcall(function() enough = player:enoughEnergy() and true or false end)
	local str = 0
	pcall(function() str = player:getStr() end)
	return {
		in_game = true,
		x = player.x, y = player.y,
		life = player.life, max_life = player.max_life,
		energy = type(player.energy) == "table" and player.energy.value or 0,
		unused_stats = player.unused_stats or 0,
		str = str,
		mainhand = mainhand_name(player),
		activity = activity,
		can_act = enough and not Prompt.blocking(game),
		zone = game.zone and Prompt.plain(game.zone.short_name or game.zone.name) or "",
		zone_name = game.zone and Prompt.plain(game.zone.name) or "",
		level = game.level and game.level.level or 0,
		character_level = player.level or 0,
		actors = Json.array(visible_actors(game, player)),
		talents = Json.array(talents_of(player)),
		inventory = Json.array(inventory_items(player)),
		floor = Json.array(floor_items(game, player)),
		log = Json.array(recent_log(game)),
		prompt = prompt,
	}
end

return M
