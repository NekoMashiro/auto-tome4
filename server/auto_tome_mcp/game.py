"""Newline JSON client for the game bridge on 127.0.0.1:9741."""

import json
import socket

HOST = "127.0.0.1"
PORT = 9741


class GameError(RuntimeError):
    def __init__(self, error):
        self.error = error or {}
        message = self.error.get("message") if isinstance(self.error, dict) else str(self.error)
        super().__init__(message or "game bridge rejected the request")


class GameClient:
    def __init__(self, host=HOST, port=PORT, timeout=120):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = None
        self.buffer = b""
        self.next_id = 1

    def connect(self):
        if self.socket is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=5)
        sock.settimeout(self.timeout)
        self.socket = sock

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def call(self, op, **fields):
        self.connect()
        request_id = str(self.next_id)
        self.next_id += 1
        payload = {"id": request_id, "op": op}
        payload.update(fields)
        self.socket.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        line = self._readline()
        message = json.loads(line)
        if not message.get("ok"):
            raise GameError(message.get("error"))
        return message.get("result")

    def look(self, kind=None, actor_id=None):
        fields = {}
        if kind:
            fields["kind"] = kind
        if actor_id:
            fields["id"] = actor_id
        return self.call("look", **fields)

    def act(self, action, command_id):
        return self.call("act", command_id=command_id, action=action)

    def status(self, command_id):
        return self.call("status", command_id=command_id)

    def _readline(self):
        while b"\n" not in self.buffer:
            chunk = self.socket.recv(65536)
            if not chunk:
                raise GameError({"code": "closed", "message": "The game closed the bridge."})
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line.decode("utf-8")
