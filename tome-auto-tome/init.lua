-- Auto ToME
-- tome-auto-tome/init.lua
--
-- Local bridge: thirteen world commands and six answers.

long_name = "Auto ToME"
short_name = "auto-tome" -- must match the folder name tome-<short_name>
for_module = "tome"
version = {1, 7, 6} -- Tales of Maj'Eyal version this addon targets
addon_version = {0, 2, 0}
weight = 100
author = { "NekoMashiro" }
homepage = ""
description = [[Expose Tales of Maj'Eyal as thirteen world commands and six answers.
A local client drives the current character through the Auto Test zone.
]]
tags = { "ai", "mcp", "automation" } -- tags must immediately follow description

overload = true
superload = true
data = true
hooks = true
