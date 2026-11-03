"""MCP stdio server. Tools are look, act, and status; the game does the work."""

import json
import sys

from auto_tome_mcp.game import GameClient, GameError

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "look",
        "description": "Read the current character, the visible tile, and the open prompt.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "act",
        "description": "Send one world command or one answer. command_id must be unique per attempt.",
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
            result = game.look()
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
