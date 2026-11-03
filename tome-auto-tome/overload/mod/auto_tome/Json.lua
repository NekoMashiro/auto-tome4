-- Minimal JSON for the local bridge. Objects are string-keyed tables.
-- Arrays are tables marked with Json.array.
local M = {}

local array_flag = {}

function M.array(list)
	local out = {}
	for i = 1, #list do out[i] = list[i] end
	return setmetatable(out, {__json_array = array_flag})
end

local function is_array(value)
	local meta = getmetatable(value)
	return type(meta) == "table" and meta.__json_array == array_flag
end

local escape_map = {
	['"'] = '\\"',
	["\\"] = "\\\\",
	["\b"] = "\\b",
	["\f"] = "\\f",
	["\n"] = "\\n",
	["\r"] = "\\r",
	["\t"] = "\\t",
}

local function escape(text)
	return (text:gsub('[%z\1-\31"\\]', function(ch)
		return escape_map[ch] or string.format("\\u%04x", ch:byte())
	end))
end

local encode_value

local function encode_array(value)
	local parts = {}
	for i = 1, #value do parts[i] = encode_value(value[i]) end
	return "[" .. table.concat(parts, ",") .. "]"
end

local function encode_object(value)
	local keys = {}
	for key in pairs(value) do keys[#keys + 1] = key end
	table.sort(keys)
	local parts = {}
	for _, key in ipairs(keys) do
		if type(key) ~= "string" then error("json object key must be a string") end
		parts[#parts + 1] = '"' .. escape(key) .. '":' .. encode_value(value[key])
	end
	return "{" .. table.concat(parts, ",") .. "}"
end

function encode_value(value)
	local kind = type(value)
	if kind == "nil" then return "null"
	elseif kind == "boolean" then return value and "true" or "false"
	elseif kind == "number" then
		if value ~= value or value == math.huge or value == -math.huge then error("json number is not finite") end
		if value % 1 == 0 and math.abs(value) < 1e15 then return string.format("%d", value) end
		return string.format("%.17g", value)
	elseif kind == "string" then return '"' .. escape(value) .. '"'
	elseif kind == "table" then
		if is_array(value) then return encode_array(value) end
		return encode_object(value)
	end
	error("json cannot encode " .. kind)
end

function M.encode(value)
	return encode_value(value)
end

local function decode_error(text, index, message)
	error(string.format("json at %d: %s", index, message))
end

local parse_value

local function skip(text, index)
	local _, stop = text:find("^[ \t\r\n]*", index)
	return (stop or index - 1) + 1
end

local function parse_string(text, index)
	local out = {}
	local i = index + 1
	while i <= #text do
		local ch = text:sub(i, i)
		if ch == '"' then return table.concat(out), i + 1 end
		if ch == "\\" then
			local esc = text:sub(i + 1, i + 1)
			local mapped = ({
				['"'] = '"', ["\\"] = "\\", ["/"] = "/",
				b = "\b", f = "\f", n = "\n", r = "\r", t = "\t",
			})[esc]
			if mapped then
				out[#out + 1] = mapped
				i = i + 2
			elseif esc == "u" then
				local hex = text:sub(i + 2, i + 5)
				if not hex:match("^%x%x%x%x$") then decode_error(text, i, "bad unicode escape") end
				out[#out + 1] = string.char(tonumber(hex, 16) % 256)
				i = i + 6
			else
				decode_error(text, i, "bad escape")
			end
		else
			out[#out + 1] = ch
			i = i + 1
		end
	end
	decode_error(text, index, "unterminated string")
end

local function parse_number(text, index)
	local token = text:match("^-?%d+%.?%d*[eE]?[+%-]?%d*", index)
	if not token or token == "-" then decode_error(text, index, "bad number") end
	return tonumber(token), index + #token
end

local function parse_array(text, index)
	local list = {}
	index = skip(text, index + 1)
	if text:sub(index, index) == "]" then return list, index + 1 end
	while true do
		local value
		value, index = parse_value(text, index)
		list[#list + 1] = value
		index = skip(text, index)
		local ch = text:sub(index, index)
		if ch == "]" then return list, index + 1 end
		if ch ~= "," then decode_error(text, index, "expected ',' or ']'") end
		index = skip(text, index + 1)
	end
end

local function parse_object(text, index)
	local obj = {}
	index = skip(text, index + 1)
	if text:sub(index, index) == "}" then return obj, index + 1 end
	while true do
		if text:sub(index, index) ~= '"' then decode_error(text, index, "expected string key") end
		local key
		key, index = parse_string(text, index)
		index = skip(text, index)
		if text:sub(index, index) ~= ":" then decode_error(text, index, "expected ':'") end
		local value
		value, index = parse_value(text, skip(text, index + 1))
		obj[key] = value
		index = skip(text, index)
		local ch = text:sub(index, index)
		if ch == "}" then return obj, index + 1 end
		if ch ~= "," then decode_error(text, index, "expected ',' or '}'") end
		index = skip(text, index + 1)
	end
end

function parse_value(text, index)
	index = skip(text, index)
	local ch = text:sub(index, index)
	if ch == '"' then return parse_string(text, index) end
	if ch == "{" then return parse_object(text, index) end
	if ch == "[" then return parse_array(text, index) end
	if ch == "t" and text:sub(index, index + 3) == "true" then return true, index + 4 end
	if ch == "f" and text:sub(index, index + 4) == "false" then return false, index + 5 end
	if ch == "n" and text:sub(index, index + 3) == "null" then return nil, index + 4 end
	if ch == "-" or ch:match("%d") then return parse_number(text, index) end
	decode_error(text, index, "unexpected '" .. ch .. "'")
end

function M.decode(text)
	if type(text) ~= "string" then return nil, "json input must be a string" end
	local ok, value, index = pcall(parse_value, text, 1)
	if not ok then return nil, tostring(value) end
	index = skip(text, index)
	if index <= #text then return nil, "trailing json" end
	return value
end

return M
