#!/usr/bin/env python3
"""Offline checks for MCP framing and the test-level route."""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from auto_tome_mcp.server import encode_message, handle_message, read_message
from play_test import bfs, walkable


class FakeGame:
    def __init__(self):
        self.calls = []

    def look(self, kind=None, actor_id=None):
        self.calls.append(("look", kind, actor_id))
        return {"in_game": True, "prompt_kind": "none", "prompt": {"kind": "none", "options": []}}

    def act(self, action, command_id):
        self.calls.append(("act", command_id, action))
        return {"status": "completed", "command_id": command_id, "prompt": {"kind": "none", "options": []}}

    def status(self, command_id):
        self.calls.append(("status", command_id))
        return {"status": "completed", "command_id": command_id}


def test_frame_roundtrip():
    payload = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    stream = io.BytesIO(encode_message(payload))
    assert read_message(stream) == payload


def test_tools_forward_look_and_act():
    game = FakeGame()
    listed = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, game)
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert names == ["look", "act", "status"]
    handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "look", "arguments": {}}}, game)
    handle_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "act", "arguments": {"command_id": "c1", "action": {"type": "wait"}}},
    }, game)
    assert game.calls[0][0] == "look"
    assert game.calls[1] == ("act", "c1", {"type": "wait"})
    note = handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, game)
    assert note is None


def test_route_reaches_the_far_room_and_the_stairs():
    tiles = walkable()
    assert bfs((2, 2), (7, 2), tiles)[0] == (3, 2)
    assert bfs((7, 2), (37, 3), tiles)[-1] == (37, 3)
    assert bfs((20, 32), (37, 2), tiles)[-1] == (37, 2)
    assert (6, 2) in tiles
    assert (4, 2) in tiles


def test_failed_action_is_reported():
    class Failing:
        def act(self, action, command_id):
            return {"status": "failed", "code": "player_busy", "command_id": command_id}

    response = handle_message({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "act", "arguments": {"command_id": "c2", "action": {"type": "wait"}}},
    }, Failing())
    body = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is True
    assert body["code"] == "player_busy"


if __name__ == "__main__":
    test_frame_roundtrip()
    test_tools_forward_look_and_act()
    test_route_reaches_the_far_room_and_the_stairs()
    test_failed_action_is_reported()
    print("offline checks passed")
