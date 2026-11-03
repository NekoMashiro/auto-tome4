-- The game checks the socket once per tick. An act reply waits until the next decision:
-- the character is idle again, or a real prompt is open. look and status reply immediately.
local Json = require "mod.auto_tome.Json"
local Observe = require "mod.auto_tome.Observe"
local Prompt = require "mod.auto_tome.Prompt"
local Commands = require "mod.auto_tome.Commands"
local M = {}

M.PORT = 9741

local ANSWERS = {choose = true, aim = true, quantity = true, adjust = true, text = true, cancel = true}

local state = {
	started = false,
	buffer = "",
	results = {},
	order = {},
}

local function remember(id, result)
	if state.results[id] then return end
	state.results[id] = result
	state.order[#state.order + 1] = id
	while #state.order > 32 do
		state.results[state.order[1]] = nil
		table.remove(state.order, 1)
	end
end

local function reply(client, id, ok, body)
	local payload = {id = id or "", ok = ok}
	if ok then payload.result = body else payload.error = body end
	local line = Json.encode(payload) .. "\n"
	pcall(function() client:send(line) end)
end

local function fail(code, message)
	return {code = code, message = message or code}
end

local function result_of(game, command_id, status, code)
	local snap = Observe.snapshot(game)
	snap.status = status
	snap.command_id = command_id
	if code then snap.code = code end
	if status == "completed" and snap.prompt and snap.prompt.kind and snap.prompt.kind ~= "none" then
		snap.status = "awaiting_input"
	end
	return snap
end

local function handle(game, request)
	if type(request) ~= "table" or type(request.op) ~= "string" then
		return false, fail("invalid_request", "Expected an object with op.")
	end
	if request.op == "look" then
		return true, Observe.snapshot(game)
	end
	if request.op == "status" then
		local id = request.command_id
		if type(id) ~= "string" or id == "" then return false, fail("invalid_command_id") end
		local stored = state.results[id]
		if not stored then return false, fail("unknown_command") end
		return true, stored
	end
	if request.op ~= "act" then return false, fail("unknown_op") end
	local command_id = request.command_id
	if type(command_id) ~= "string" or command_id == "" then return false, fail("invalid_command_id") end
	if state.results[command_id] then return true, state.results[command_id] end
	local action = request.action
	if type(action) ~= "table" or type(action.type) ~= "string" then
		local bad = result_of(game, command_id, "failed", "invalid_action")
		remember(command_id, bad)
		return true, bad
	end
	local ran, ok, err = pcall(function()
		if ANSWERS[action.type] then
			if not Prompt.blocking(game) and action.type ~= "cancel" then return false, "nothing_to_answer" end
			return Prompt.apply(game, action)
		end
		return Commands.execute(game, action)
	end)
	if not ran then ok, err = false, tostring(ok) end
	if not ok then
		local snap = result_of(game, command_id, "failed", err or "failed")
		remember(command_id, snap)
		return true, snap
	end
	-- The scheduler runs after this poll. Hold the reply so one act covers the whole action.
	state.pending = {request_id = request.id, command_id = command_id, t0 = os.time()}
	return true, nil
end

local function finish_pending(game, status, code)
	local pending = state.pending
	local snap = result_of(game, pending.command_id, status, code)
	remember(pending.command_id, snap)
	reply(state.client, pending.request_id, true, snap)
	state.pending = nil
end

local function ensure(game)
	if state.started then return true end
	local ok, socket = pcall(require, "socket")
	if not ok then
		print("[auto-tome] luasocket is unavailable")
		state.started = true
		return false
	end
	local server, err = socket.bind("127.0.0.1", M.PORT)
	if not server then
		print("[auto-tome] bind failed", err)
		state.started = true
		return false
	end
	server:settimeout(0)
	state.server = server
	state.started = true
	print("[auto-tome] listening on 127.0.0.1:" .. M.PORT)
	return true
end

local function pop_line()
	local newline = state.buffer:find("\n", 1, true)
	if not newline then return nil end
	local line = state.buffer:sub(1, newline - 1):gsub("\r$", "")
	state.buffer = state.buffer:sub(newline + 1)
	return line
end

local function absorb(client)
	local data, err, partial = client:receive("*a")
	local chunk = type(data) == "string" and data or ""
	if chunk == "" and type(partial) == "string" then chunk = partial end
	if chunk ~= "" then state.buffer = state.buffer .. chunk end
	return err
end

function M.poll(game)
	if state.polling then return end
	state.polling = true
	local function finish() state.polling = false end
	if not ensure(game) or not state.server then return finish() end
	local incoming = state.server:accept()
	if incoming then
		if state.client then pcall(function() state.client:close() end) end
		incoming:settimeout(0)
		state.client = incoming
		state.buffer = ""
		state.pending = nil
	end
	if not state.client then return finish() end
	if #state.buffer > 1048576 then
		state.buffer = ""
		state.pending = nil
		reply(state.client, "", false, fail("line_too_long"))
		return finish()
	end
	local err = absorb(state.client)
	if err == "closed" then
		state.client = nil
		state.buffer = ""
		state.pending = nil
		return finish()
	end
	if state.pending then
		local status = Prompt.settled(game)
		if status then finish_pending(game, status)
		elseif os.time() - state.pending.t0 >= 110 then finish_pending(game, "failed", "still_busy") end
		return finish()
	end
	local line = pop_line()
	if not line or line == "" then return finish() end
	local request, decode_err = Json.decode(line)
	if not request then
		reply(state.client, "", false, fail("invalid_json", decode_err))
		return finish()
	end
	local ok, success, body = pcall(handle, game, request)
	if not ok then
		reply(state.client, request.id, false, fail("internal_error", tostring(success)))
		return finish()
	end
	if body ~= nil then reply(state.client, request.id, success, body) end
	return finish()
end

return M
