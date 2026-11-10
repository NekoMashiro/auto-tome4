-- Four looks: around, map, actor, and prompt. around is the only one that returns the log.
local Json = require "mod.auto_tome.Json"
local Prompt = require "mod.auto_tome.Prompt"
local M = {}

local RADIUS = 20
local pending_log = {}

local IMMUNITIES = {
	"poison_immune", "disease_immune", "cut_immune", "confusion_immune", "blind_immune",
	"silence_immune", "disarm_immune", "pin_immune", "stun_immune", "sleep_immune",
	"fear_immune", "knockback_immune", "stone_immune", "instakill_immune", "teleport_immune",
	"negative_status_effect_immune",
}

function M.note(text)
	if type(text) ~= "string" then return end
	text = Prompt.plain(text)
	pending_log[#pending_log + 1] = text
end

local function take_log()
	local lines = pending_log
	pending_log = {}
	return Json.array(lines)
end

local function one_char(text)
	if type(text) ~= "string" or text == "" then return "?" end
	local byte = text:byte(1)
	if not byte or byte < 128 then return text:sub(1, 1) end
	local length = 1
	if byte >= 240 then length = 4
	elseif byte >= 224 then length = 3
	elseif byte >= 192 then length = 2 end
	return text:sub(1, length)
end

local function flagged(value)
	if value == nil or value == false then return false end
	if type(value) == "number" then return value ~= 0 end
	return true
end

local function blocks_move(terrain)
	return flagged(terrain.does_block_move)
end

local function blocks_sight(terrain)
	return flagged(terrain.block_sight)
end

local function damaging_stand(terrain)
	return type(terrain.on_stand) == "function" and (flagged(terrain.mindam) or flagged(terrain.maxdam) or terrain.DamageType ~= nil)
end

-- First matching rule wins. This is the table in docs/look.md.
local function terrain_glyph(terrain)
	if type(terrain) ~= "table" then return "?" end
	if terrain.door_opened then return "+" end
	if (terrain.is_door or terrain.door_closed) and not terrain.door_opened then return "'" end
	local zone = terrain.change_zone
	local level = terrain.change_level
	local world = type(zone) == "string" and zone:find("wilderness", 1, true) ~= nil
	if world or (type(level) == "number" and level < 0) then return "<" end
	if level ~= nil or zone ~= nil then return ">" end
	if terrain.type == "lever" then return "&" end
	local walk = not blocks_move(terrain)
	if walk and damaging_stand(terrain) then return "%" end
	if walk and terrain.air_condition == "water" then return "~" end
	if walk and type(terrain.air_level) == "number" and terrain.air_level > 0 then return ":" end
	if walk and type(terrain.on_stand) == "function" then return ";" end
	if not walk and not blocks_sight(terrain) and flagged(terrain.pass_projectile) then return "=" end
	local can_pass = terrain.can_pass
	if not walk and type(can_pass) == "table" and flagged(can_pass.pass_water) then return "W" end
	if not walk and blocks_sight(terrain) then return "#" end
	if walk then return "." end
	return "#"
end

local function stair_of(terrain, x, y)
	if type(terrain) ~= "table" then return nil end
	if type(terrain.change_level) ~= "number" and type(terrain.change_zone) ~= "string" then return nil end
	local stair = {x = x, y = y}
	if type(terrain.change_level) == "number" then stair.change_level = terrain.change_level end
	if type(terrain.change_zone) == "string" then stair.change_zone = terrain.change_zone end
	return stair
end

local function can_see_actor(player, actor)
	local seen = false
	local ok = pcall(function() seen = player:canSee(actor) and true or false end)
	return ok and seen
end

local function cell_layers(map, player, x, y)
	if not map:isBound(x, y) then return " ", " ", nil end
	local seen = map.seens(x, y) and true or false
	local remembered = (not seen) and map.remembers(x, y) and true or false
	if not seen and not remembered then return " ", " ", nil end
	local terrain = map(x, y, map.TERRAIN)
	local glyph = terrain_glyph(terrain)
	local covered = false
	if seen then
		local actor = map(x, y, map.ACTOR)
		if actor == player or (player and x == player.x and y == player.y) then
			glyph = "@"
			covered = true
		elseif type(actor) == "table" and not actor.dead and can_see_actor(player, actor) then
			glyph = one_char(actor.display)
			covered = true
		end
		if not covered then
			local object = map(x, y, map.OBJECT)
			if type(object) == "table" then glyph = one_char(object.display) end
		end
	else
		local object = map(x, y, map.OBJECT)
		if type(object) == "table" and object.always_remember then glyph = one_char(object.display) end
	end
	return glyph, seen and "S" or "R", stair_of(terrain, x, y)
end

local function grid(map, player, x0, y0, width, height)
	local rows, sight, stairs = {}, {}, {}
	for y = 0, height - 1 do
		local glyphs, marks = {}, {}
		for x = 0, width - 1 do
			local glyph, mark, stair = cell_layers(map, player, x0 + x, y0 + y)
			glyphs[x + 1] = glyph
			marks[x + 1] = mark
			if stair then stairs[#stairs + 1] = stair end
		end
		rows[#rows + 1] = table.concat(glyphs)
		sight[#sight + 1] = table.concat(marks)
	end
	return {
		x = x0, y = y0, w = width, h = height,
		rows = Json.array(rows),
		sight = Json.array(sight),
		stairs = Json.array(stairs),
	}
end

local function object_name(object)
	local name = object.name
	if type(object.getName) == "function" then
		local ok, value = pcall(function() return object:getName({do_color = false}) end)
		if ok and value then name = value end
	end
	return Prompt.plain(name)
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
	return Prompt.plain(text)
end

local function item_record(object, extra)
	local record = {
		id = "item-" .. tostring(object.uid or 0),
		name = object_name(object),
		number = type(object.getNumber) == "function" and object:getNumber() or 1,
	}
	for key, value in pairs(extra or {}) do record[key] = value end
	return record
end

local function objects_at(map, x, y, terrain_char, with_desc)
	local items = {}
	local index = 1
	while true do
		local object = map:getObject(x, y, index)
		if not object then break end
		local extra = {x = x, y = y, display = one_char(object.display), terrain = terrain_char}
		if with_desc then
			local desc = object_desc(object)
			if desc then extra.desc = desc end
		end
		items[#items + 1] = item_record(object, extra)
		index = index + 1
	end
	return items
end

local function rank_name(actor)
	local rank = "normal"
	pcall(function()
		local name = actor.TextRank and actor:TextRank() or actor:textRank()
		if type(name) == "string" and name ~= "" then rank = Prompt.plain(name) end
	end)
	return rank
end

local function actor_brief(actor, player, include_relation)
	local relation = 0
	if include_relation then
		pcall(function() relation = player:reactionToward(actor) end)
	end
	local record = {
		id = "actor-" .. tostring(actor.uid),
		name = Prompt.plain(actor.name),
		x = actor.x, y = actor.y,
		life = actor.life, max_life = actor.max_life,
		level = actor.level or 0,
		randboss = actor.randboss and true or false,
		rank = rank_name(actor),
	}
	if include_relation then record.relation = relation end
	return record
end

local function visible_actors(game, player)
	local actors = {}
	local entities = game.level and game.level.entities or {}
	for _, actor in pairs(entities) do
		if type(actor) == "table" and actor.__is_actor and actor ~= player and actor.x and not actor.dead then
			local seen = false
			local ok = pcall(function()
				seen = player:canSee(actor) and game.level.map.seens(actor.x, actor.y) and true or false
			end)
			if ok and seen then actors[#actors + 1] = actor_brief(actor, player, true) end
		end
	end
	table.sort(actors, function(a, b) return a.id < b.id end)
	return actors
end

local function find_actor(game, actor_id)
	if type(actor_id) ~= "string" then return nil end
	local prefix = "actor-"
	if actor_id:sub(1, #prefix) ~= prefix then return nil end
	local uid = tonumber(actor_id:sub(#prefix + 1))
	local entities = game.level and game.level.entities
	local actor = uid and entities and entities[uid]
	if type(actor) == "table" and actor.x and not actor.dead then return actor end
end

local function prompt_kind(game)
	if not Prompt.needs_answer(game) then return "none" end
	local prompt = Prompt.public(game)
	return prompt.kind or "none"
end

local function number_or_nil(value)
	if type(value) == "number" then return value end
	return nil
end

local function resources_of(player, game)
	local ActorResource = require "engine.interface.ActorResource"
	local list = {}
	for _, def in ipairs(ActorResource.resources_def or {}) do
		if not (def.talent and not (player.knowTalent and player:knowTalent(def.talent))) then
			local show = true
			if def.short_name == "air" then
				local air = number_or_nil(player.air) or 0
				local max_air = number_or_nil(player.max_air) or 0
				show = air < max_air
			end
			if show and type(player[def.getFunction]) == "function" then
				local value, minimum, maximum, regen
				pcall(function() value = player[def.getFunction](player) end)
				if type(player[def.getMinFunction]) == "function" then
					pcall(function() minimum = player[def.getMinFunction](player) end)
				end
				if type(player[def.getMaxFunction]) == "function" then
					pcall(function() maximum = player[def.getMaxFunction](player) end)
				end
				if def.regen_prop then regen = player[def.regen_prop] end
				local record = {
					id = def.short_name,
					name = Prompt.plain(def.name or def.short_name),
					value = number_or_nil(value) or 0,
				}
				local max_value = number_or_nil(maximum)
				if max_value then record.max = max_value end
				if type(regen) == "number" then record.regen = regen end
				if type(def.status_text) == "function" then
					local ok, text = pcall(def.status_text, player)
					if ok and type(text) == "string" and text ~= "" then record.text = Prompt.plain(text) end
				else
					local percent = 100
					local min_value = number_or_nil(minimum)
					local current = number_or_nil(value)
					if min_value and max_value and max_value ~= 0 and current then
						local fraction = current / max_value
						if fraction < 0 then fraction = 0 end
						if fraction > 1 then fraction = 1 end
						percent = math.floor(fraction * 100 + 0.5)
					end
					record.percent = percent
				end
				list[#list + 1] = record
			end
		end
	end
	if player.is_fortress and game and type(game.getPlayer) == "function" then
		local owner = game:getPlayer(true)
		local quest = owner and owner.hasQuest and owner:hasQuest("shertul-fortress")
		if type(quest) == "table" and type(quest.shertul_energy) == "number" then
			list[#list + 1] = {id = "fortress", name = "Fortress", value = quest.shertul_energy}
		end
	end
	return list
end

local function mainhand_name(player)
	local inven = player.getInven and player:getInven("MAINHAND") or nil
	local object = type(inven) == "table" and inven[1] or nil
	if type(object) ~= "table" then return "" end
	return object_name(object)
end

local function zone_names(game)
	local zone = game.zone
	if type(zone) ~= "table" then return "", "" end
	return Prompt.plain(zone.short_name or zone.name or ""), Prompt.plain(zone.name or "")
end

function M.around(game)
	local player = game and game.player
	if not player or not player.x or not game.level or not game.level.map then
		return {in_game = false, prompt_kind = "none", log = take_log()}
	end
	local map = game.level.map
	local view = grid(map, player, player.x - RADIUS, player.y - RADIUS, RADIUS * 2 + 1, RADIUS * 2 + 1)
	local items = {}
	local x0, y0 = view.x, view.y
	for y = 0, view.h - 1 do
		local marks = view.sight[y + 1]
		for x = 0, view.w - 1 do
			local mark = marks:sub(x + 1, x + 1)
			if mark == "S" or mark == "R" then
				local mx, my = x0 + x, y0 + y
				local terrain_char = terrain_glyph(map(mx, my, map.TERRAIN))
				local index = 1
				while true do
					local object = map:getObject(mx, my, index)
					if not object then break end
					if mark == "S" or object.always_remember then
						local extra = {x = mx, y = my, display = one_char(object.display), terrain = terrain_char}
						items[#items + 1] = item_record(object, extra)
					end
					index = index + 1
				end
			end
		end
	end
	local floor_terrain = terrain_glyph(map(player.x, player.y, map.TERRAIN))
	local floor = objects_at(map, player.x, player.y, floor_terrain, true)
	local str = 0
	pcall(function() str = player:getStr() end)
	local zone, zone_name = zone_names(game)
	return {
		in_game = true,
		name = Prompt.plain(player.name or ""),
		x = player.x, y = player.y,
		life = player.life, max_life = player.max_life,
		energy = type(player.energy) == "table" and player.energy.value or 0,
		unused_stats = player.unused_stats or 0,
		str = str,
		mainhand = mainhand_name(player),
		zone = zone, zone_name = zone_name,
		level = game.level.level or 0,
		character_level = player.level or 0,
		prompt_kind = prompt_kind(game),
		view = view,
		actors = Json.array(visible_actors(game, player)),
		items = Json.array(items),
		floor = Json.array(floor),
		resources = Json.array(resources_of(player, game)),
		log = take_log(),
	}
end

function M.map(game)
	local player = game and game.player
	local map = game.level and game.level.map
	if not player or not player.x or not map then return {in_game = false} end
	-- view.x and view.y stay the top-left of the level, which is (0, 0).
	-- x and y are the character, same as around.
	local view = grid(map, player, 0, 0, map.w, map.h)
	local zone, zone_name = zone_names(game)
	return {
		in_game = true,
		x = player.x, y = player.y,
		zone = zone, zone_name = zone_name,
		level = game.level.level or 0,
		view = view,
	}
end

function M.prompt(game)
	if not game or not game.player or not Prompt.needs_answer(game) then
		return {kind = "none", options = Json.array({})}
	end
	local prompt = Prompt.public(game)
	prompt.options = Json.array(prompt.options or {})
	if prompt.nodes then prompt.nodes = Json.array(prompt.nodes) end
	return prompt
end

local function bound(value, low, high)
	if value < low then return low end
	if value > high then return high end
	return value
end

local function call_number(actor, method, ...)
	local value = 0
	local args = {...}
	pcall(function() value = actor[method](actor, unpack(args)) end)
	if type(value) ~= "number" then return 0 end
	return value
end

local function talent_rows(actor)
	local talents = {}
	for id, level in pairs(actor.talents or {}) do
		local talent = actor.getTalentFromId and actor:getTalentFromId(id) or nil
		if type(talent) == "table" and type(level) == "number" and level > 0 then
			local raw = level
			pcall(function() raw = actor:getTalentLevelRaw(id) end)
			local cooling = false
			pcall(function() cooling = actor:isTalentCoolingDown(id) end)
			talents[#talents + 1] = {
				id = id,
				name = Prompt.plain(talent.name),
				mode = talent.mode or "",
				level = type(raw) == "number" and raw or level,
				sustained = actor.sustain_talents and actor.sustain_talents[id] and true or false,
				cooldown = type(cooling) == "number" and cooling or 0,
			}
		end
	end
	table.sort(talents, function(a, b) return a.id < b.id end)
	return talents
end

local function resist_rows(actor)
	local DamageType = require "engine.DamageType"
	local rows = {}
	local resists = actor.resists or {}
	local caps = actor.resists_cap or {}
	for _, def in pairs(DamageType.dam_def or {}) do
		if type(def) == "table" and type(def.type) == "string" then
			local raw = resists[def.type] or 0
			if raw ~= 0 then
				rows[#rows + 1] = {
					name = Prompt.plain(def.name or def.type),
					value = call_number(actor, "combatGetResist", def.type),
					cap = (caps[def.type] or 0) + (caps.all or 0),
				}
			end
		end
	end
	table.sort(rows, function(a, b) return a.name < b.name end)
	return rows
end

local function actor_type_rows(source, cap)
	local rows = {}
	for kind, value in pairs(source or {}) do
		if type(value) == "number" and value ~= 0 then
			rows[#rows + 1] = {type = tostring(kind), value = value, cap = cap}
		end
	end
	table.sort(rows, function(a, b) return a.type < b.type end)
	return rows
end

local function damage_rows(actor)
	local DamageType = require "engine.DamageType"
	local rows = {}
	local bonus = actor.inc_damage or {}
	for _, def in pairs(DamageType.dam_def or {}) do
		if type(def) == "table" and type(def.type) == "string" and (bonus[def.type] or 0) ~= 0 then
			rows[#rows + 1] = {
				name = Prompt.plain(def.name or def.type),
				value = call_number(actor, "combatGetDamageIncrease", def.type),
			}
		end
	end
	table.sort(rows, function(a, b) return a.name < b.name end)
	return rows
end

local function immunity_rows(actor)
	local rows = {}
	for _, name in ipairs(IMMUNITIES) do
		local value = nil
		if type(actor.attr) == "function" then
			local ok, got = pcall(function() return actor:attr(name) end)
			if ok then value = got end
		end
		if value == nil then value = actor[name] end
		if type(value) == "number" then
			rows[#rows + 1] = {name = name, percent = bound(value * 100, 0, 100)}
		end
	end
	return rows
end

function M.actor(game, actor_id)
	local player = game and game.player
	if not player or not player.x then return {in_game = false, code = "no_player"} end
	local actor = player
	local self_lookup = actor_id == nil or actor_id == ""
	if not self_lookup then
		actor = find_actor(game, actor_id)
		if not actor or actor == player then
			if actor ~= player then
				return {status = "failed", code = "actor_unseen", message = "That actor is not visible."}
			end
		end
		if actor ~= player then
			local seen = false
			pcall(function()
				seen = player:canSee(actor) and game.level.map.seens(actor.x, actor.y) and true or false
			end)
			if not seen then
				return {status = "failed", code = "actor_unseen", message = "That actor is not visible."}
			end
		end
	end
	local record = actor_brief(actor, player, actor ~= player)
	record.in_game = true
	record.resists = Json.array(resist_rows(actor))
	local all = actor.resists and actor.resists.all or 0
	if all ~= 0 then
		record.resists_all = {value = all, cap = (actor.resists_cap and actor.resists_cap.all) or 100}
	end
	record.resists_actor = Json.array(actor_type_rows(actor.resists_actor_type, actor.resists_cap_actor_type or 70))
	record.immunities = Json.array(immunity_rows(actor))
	record.saves = {
		physical = math.floor(call_number(actor, "combatPhysicalResist", true)),
		spell = math.floor(call_number(actor, "combatSpellResist", true)),
		mental = math.floor(call_number(actor, "combatMentalResist", true)),
	}
	record.damage = Json.array(damage_rows(actor))
	local damage_all = actor.inc_damage and actor.inc_damage.all or 0
	if damage_all ~= 0 then record.damage_all = damage_all end
	local actor_damage = {}
	for kind, value in pairs(actor.inc_damage_actor_type or {}) do
		if type(value) == "number" and value ~= 0 then
			actor_damage[#actor_damage + 1] = {type = tostring(kind), value = value}
		end
	end
	table.sort(actor_damage, function(a, b) return a.type < b.type end)
	record.damage_actor = Json.array(actor_damage)
	record.talents = Json.array(talent_rows(actor))
	return record
end

-- The old name still builds an around snapshot. Act results use that.
function M.snapshot(game)
	return M.around(game)
end

return M
