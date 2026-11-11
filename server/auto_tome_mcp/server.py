"""MCP stdio server. Tools are look, act, and status; the game does the work."""

import json
import sys

from auto_tome_mcp.game import GameClient, GameError

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "look",
        "description": (
            "Read the game without changing it. kind defaults to around: a 41x41 view centered on the character, "
            "visible actors, items, resources, and every log line since the previous around. "
            "map is the whole level with the same fog and no log. Its x and y are the character; view.x and view.y are the top-left of that level, which is 0, 0. actor reads one visible actor; omit id to read yourself. "
            "prompt reads the open window. map, actor, and prompt do not include or advance the log. "
            "Sight marks are S seen, R remembered, and space unseen. Stair cells also list change_level."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["around", "map", "actor", "prompt"]},
                "id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "act",
        "description": (
            "Do one world command or answer one window. command_id must be unique per attempt. "
            "The result is an around snapshot plus status. World commands are step, wait, run, move_to, auto_explore, rest, "
            "change_level, pickup, switch_weapons, open_inventory, open_levelup, use, and quit. "
            "Answers are choose, aim, quantity, adjust, text, and cancel. choose takes label, the option text just returned. "
            "A world command fails with player_busy while a window or target prompt is open: read message and options. "
            "move_to takes x and y and uses the game's click-to-walk. It paths when no enemy is visible, and takes one step toward the point when an enemy is visible. "
            "auto_explore stops itself after 5000 steps and logs Auto-explore stopped after 5000 steps. "
            "change_level adds from_level, from_zone, and level_move: up, down, zone, or none. "
            "There is no save command. quit saves and exits the process. It fails if a window is open or the character is dead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command_id": {"type": "string"},
                "action": {"type": "object"},
            },
            "required": ["command_id", "action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "status",
        "description": "Read the stored result of a command_id without running it again.",
        "inputSchema": {
            "type": "object",
            "properties": {"command_id": {"type": "string"}},
            "required": ["command_id"],
            "additionalProperties": False,
        },
    },
]


def encode_message(payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_message(stream):
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
        if len(header) > 65536:
            raise ValueError("MCP header is too large")
    raw_header, rest = header.split(b"\r\n\r\n", 1)
    length = None
    for line in raw_header.decode("ascii", "replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    if length is None:
        raise ValueError("MCP frame is missing Content-Length")
    body = rest
    while len(body) < length:
        chunk = stream.read(length - len(body))
        if not chunk:
            raise ValueError("MCP frame ended early")
        body += chunk
    return json.loads(body.decode("utf-8"))


def tool_result(result, is_error=False):
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "isError": is_error,
    }


def handle_message(message, game):
    if not isinstance(message, dict):
        return None
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None and method:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "auto-tome", "version": "0.2.0"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method != "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Unknown method"},
        }
    params = message.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    try:
        if name == "look":
            result = game.look(arguments.get("kind"), arguments.get("id"))
        elif name == "act":
            result = game.act(arguments.get("action"), arguments.get("command_id"))
        elif name == "status":
            result = game.status(arguments.get("command_id"))
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": tool_result({"code": "unknown_tool", "message": name}, True),
            }
        failed = isinstance(result, dict) and result.get("status") == "failed"
        return {"jsonrpc": "2.0", "id": request_id, "result": tool_result(result, failed)}
    except GameError as error:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": tool_result(error.error, True),
        }


def serve(input_stream, output_stream, game):
    while True:
        message = read_message(input_stream)
        if message is None:
            return
        response = handle_message(message, game)
        if response is not None:
            output_stream.write(encode_message(response))
            output_stream.flush()


def main():
    serve(sys.stdin.buffer, sys.stdout.buffer, GameClient())
