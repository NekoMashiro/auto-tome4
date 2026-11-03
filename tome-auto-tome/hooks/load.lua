-- Load the test bolt when ToME starts. The hook file is otherwise idle.
local class = require "engine.class"
local ActorTalents = require "engine.interface.ActorTalents"

class:bindHook("ToME:load", function(self, data)
	ActorTalents:loadDefinition("/data-auto-tome/talents.lua")
end)
