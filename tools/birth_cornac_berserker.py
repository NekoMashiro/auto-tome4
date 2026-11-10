#!/usr/bin/env python3
"""Start a new Age of Ascendancy game as a Cornac Berserker.

The engine rebirth path is a vault description plus one process argument.
force_fallback makes it birth from the descriptors instead of reloading a
played character. no_birth_popup is left unset, so the level-up dialog stays open.

    python3 tools/birth_cornac_berserker.py

Run this on the machine that shows the game.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import drive_game
from auto_tome_mcp.game import GameClient, GameError

NAME = "CornacBerserker"
VAULT = Path.home() / ".t-engine" / "4.0" / "tome" / "vault" / NAME
SAVE = Path.home() / ".t-engine" / "4.0" / "tome" / "save" / NAME

# World is omitted on purpose. The dialog already defaults to Maj'Eyal, and
# loadPremade only presses Play when exactly four of its five checks match.
DESCRIPTOR = """module = "tome"
module_version = {1,7,6}
name = "Cornac Berserker"
short_name = "CornacBerserker"
force_fallback = true
description = "Fresh Cornac Berserker in Maj'Eyal: The Age of Ascendancy."
descriptors = {
	["difficulty"] = "Normal",
	["permadeath"] = "Adventure",
	["race"] = "Human",
	["subrace"] = "Cornac",
	["class"] = "Warrior",
	["subclass"] = "Berserker",
	["base"] = "base",
}
"""


def prepare_vault():
    if VAULT.exists():
        shutil.rmtree(VAULT)
    VAULT.mkdir(parents=True)
    (VAULT / "desc.lua").write_text(DESCRIPTOR)
    # The vault list only checks that this file exists. Fallback birth does not read it.
    (VAULT / "character.teac").write_bytes(b"\n")
    if SAVE.exists():
        shutil.rmtree(SAVE)


def stop_game():
    for pid in drive_game.engine_pids():
        print("stopping t-engine %s" % pid, flush=True)
        os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 15
    while drive_game.engine_pids() and time.time() < deadline:
        time.sleep(0.3)
    for pid in drive_game.engine_pids():
        os.kill(pid, signal.SIGKILL)


def launch(game_dir, log_path, display):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w")
    env = os.environ.copy()
    env.update(display.env)
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["SDL_VIDEODRIVER"] = "x11"
    # -E is a prefix, not a separate argument. The rest is Lua for __module_extra_info.
    # Leave no_birth_popup unset so birth opens the level-up dialog.
    command = ["./t-engine", "-Mtome", "-n", '-Eauto_quickbirth="%s"' % NAME]
    print("launch %s" % " ".join(command), flush=True)
    process = subprocess.Popen(
        command,
        cwd=str(game_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    process.log_file = log_file
    return process


def look_once():
    client = GameClient(timeout=8)
    try:
        client.connect()
        snap = client.look()
        if snap and snap.get("in_game"):
            if snap.get("prompt_kind") not in (None, "none"):
                snap["prompt"] = client.look("prompt")
            sheet = client.look("actor")
            if isinstance(sheet, dict):
                snap["talents"] = sheet.get("talents") or []
        return snap
    except (OSError, TimeoutError, GameError):
        return None
    finally:
        client.close()


def interesting(snap):
    if not snap or not snap.get("in_game"):
        return False
    prompt = snap.get("prompt") or {}
    kind = snap.get("prompt_kind") or prompt.get("kind")
    return kind not in (None, "none")


def summarize(snap):
    prompt = (snap or {}).get("prompt") or {}
    talents = [item.get("id") for item in (snap or {}).get("talents") or []]
    return {
        "in_game": (snap or {}).get("in_game"),
        "zone": (snap or {}).get("zone"),
        "zone_name": (snap or {}).get("zone_name"),
        "level": (snap or {}).get("level"),
        "x": (snap or {}).get("x"),
        "y": (snap or {}).get("y"),
        "mainhand": (snap or {}).get("mainhand"),
        "str": (snap or {}).get("str"),
        "unused_stats": (snap or {}).get("unused_stats"),
        "talents": talents,
        "prompt_kind": prompt.get("kind"),
        "prompt_title": prompt.get("title"),
        "prompt_nodes": [item.get("node") for item in prompt.get("nodes") or []][:8],
        "prompt_options": [item.get("label") for item in prompt.get("options") or []][:8],
    }


def birth_ok(info):
    talents = set(info["talents"] or [])
    weapon = (info["mainhand"] or "").lower()
    return (
        info["in_game"]
        and info["zone"] == "trollmire"
        and info["level"] == 1
        and info["prompt_kind"] == "adjust"
        and "greatsword" in weapon
        and "T_WARSHOUT_BERSERKER" in talents
    )


def main():
    game_dir = Path.home() / "tome-test" / "t-engine4-linux64-1.7.6"
    log_path = Path.home() / "tome-test" / "birth-cornac.log"
    display = drive_game.Desktop(
        os.environ.get("DISPLAY", ":10.0"),
        os.environ.get("XAUTHORITY", str(Path.home() / ".Xauthority")),
    )
    prepare_vault()
    stop_game()
    started = launch(game_dir, log_path, display)
    display.start_wiggle()
    deadline = time.time() + 150
    last = None
    try:
        while time.time() < deadline:
            if started.poll() is not None:
                print("t-engine exited with %s" % started.returncode, flush=True)
                break
            last = look_once()
            if interesting(last):
                break
            time.sleep(0.5)
    finally:
        display.stop_wiggle()
    info = summarize(last)
    print(json.dumps(info, ensure_ascii=False, indent=2), flush=True)
    if not birth_ok(info):
        text = log_path.read_text(errors="replace") if log_path.exists() else ""
        tail = "\n".join(text.splitlines()[-40:])
        print(tail, flush=True)
        return 1
    print(
        "Cornac Berserker is in %s level %s at %s,%s with the level-up dialog open"
        % (info["zone"], info["level"], info["x"], info["y"]),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
