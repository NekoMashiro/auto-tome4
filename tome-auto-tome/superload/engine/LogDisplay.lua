-- Copy each game-log line as it is written. around sends the copy and then drops it.
local _M = loadPrevious(...)
local call = _M.call

function _M:call(...)
	call(self, ...)
	local ok, Observe = pcall(require, "mod.auto_tome.Observe")
	if not ok or not game or not game.uiset or self ~= game.uiset.logdisplay then return end
	local line = self.log and self.log[1]
	if type(line) == "table" and type(line.str) == "string" then Observe.note(line.str) end
end

return _M
