#!/usr/bin/env python3
"""Launch ToME straight into a level, and keep the pointer moving.

Run this on the machine that shows the game. The process arguments select the
module and character, so the main menu is never shown. With no flags this births
a character named auto_test, runs the acceptance test, and deletes only that
save. --no-play without --save births the Cornac Berserker used for play. An
idle character still blocks the engine in SDL_WaitEvent, so the pointer keeps
moving a few pixels across the portrait until this process exits.

    python3 tools/drive_game.py
    python3 tools/drive_game.py --save guvena --no-play
    python3 tools/drive_game.py --no-play
    python3 tools/drive_game.py --wiggle-only
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from auto_tome_mcp.game import GameClient, GameError

REPO = Path(__file__).resolve().parents[1]
TEST_NAME = "auto_test"
TEST_DESCRIPTOR = """module = "tome"
module_version = {1,7,6}
name = "auto_test"
short_name = "auto_test"
force_fallback = true
description = "Acceptance-test Cornac Berserker. This save is disposable."
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


class Desktop:
    def __init__(self, display, xauthority):
        self.env = os.environ.copy()
        self.env["DISPLAY"] = display
        self.env["XAUTHORITY"] = xauthority
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def run(self, args, check=True):
        result = subprocess.run(args, env=self.env, text=True, capture_output=True)
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError("%s failed (%s)" % (" ".join(args), detail))
        return result

    def windows(self):
        found = self.run(["xdotool", "search", "--name", "Maj"], check=False)
        if found.returncode != 0:
            return []
        windows = []
        for line in found.stdout.split():
            info = self.run(["xwininfo", "-id", line], check=False)
            if info.returncode != 0:
                continue
            fields = {}
            for row in info.stdout.splitlines():
                if ":" not in row:
                    continue
                key, value = row.split(":", 1)
                fields[key.strip()] = value.strip()
            try:
                windows.append((
                    int(line),
                    int(fields["Absolute upper-left X"]),
                    int(fields["Absolute upper-left Y"]),
                    int(fields["Width"]),
                    int(fields["Height"]),
                ))
            except (KeyError, ValueError):
                continue
        return windows

    def client_window(self):
        found = self.windows()
        if not found:
            return None
        # The window manager frame is a few pixels larger than the game surface.
        return min(found, key=lambda item: item[3] * item[4])

    def move(self, x, y):
        with self.lock:
            self.run(["xdotool", "mousemove", str(int(x)), str(int(y))])

    def start_wiggle(self):
        if self._thread is not None:
            return
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                window = self.client_window()
                if window is not None:
                    _, origin_x, origin_y, _, _ = window
                    # Stay on the portrait. Motion here wakes the frame loop and does not path the character.
                    self.move(origin_x + 48, origin_y + 46)
                    if self._stop.is_set():
                        break
                    self.move(origin_x + 51, origin_y + 49)
                self._stop.wait(0.2)

        self._thread = threading.Thread(target=loop, name="pointer-wiggle", daemon=True)
        self._thread.start()

    def stop_wiggle(self):
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=2)


def engine_pids():
    pids = []
    proc = Path("/proc")
    if not proc.is_dir():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        parts = [part for part in command.split(" ") if part]
        if parts and Path(parts[0]).name == "t-engine":
            pids.append(int(entry.name))
    return pids


def install_addon(source, destination):
    if not source.is_dir():
        raise RuntimeError("Addon source is missing: %s" % source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        destination.unlink()
    shutil.copytree(source, destination, dirs_exist_ok=True)


def stop_game():
    for pid in engine_pids():
        print("stopping t-engine %s" % pid, flush=True)
        os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 15
    while engine_pids() and time.time() < deadline:
        time.sleep(0.3)
    for pid in engine_pids():
        os.kill(pid, signal.SIGKILL)


def launch_game(game_dir, log_path, display, command):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w")
    env = os.environ.copy()
    env["DISPLAY"] = display.env["DISPLAY"]
    env["XAUTHORITY"] = display.env["XAUTHORITY"]
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["SDL_VIDEODRIVER"] = "x11"
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


def engine_command(save_name):
    # -M, -u, -n and -E are prefixes. The characters after the flag are the value.
    if save_name:
        return ["./t-engine", "-Mtome", "-u" + save_name]
    from birth_cornac_berserker import NAME, prepare_vault
    prepare_vault()
    extra = (
        'auto_quickbirth="%s" no_birth_popup=true birth_done_script=[==[game.paused = false]==]'
        % NAME
    )
    return ["./t-engine", "-Mtome", "-n", "-E" + extra]


def prepare_test_character():
    # The birth dialog copies short_name into the character name, and that name is the save directory.
    root = Path.home() / ".t-engine" / "4.0" / "tome"
    vault = root / "vault" / TEST_NAME
    save = root / "save" / TEST_NAME
    if vault.exists():
        shutil.rmtree(vault)
    vault.mkdir(parents=True)
    (vault / "desc.lua").write_text(TEST_DESCRIPTOR)
    (vault / "character.teac").write_bytes(b"\n")
    if save.exists():
        print("removing only %s" % save, flush=True)
        shutil.rmtree(save)


def test_engine_command():
    prepare_test_character()
    extra = (
        'auto_quickbirth="%s" no_birth_popup=true birth_done_script=[==[game.paused = false]==]'
        % TEST_NAME
    )
    return ["./t-engine", "-Mtome", "-n", "-E" + extra]


def look_once(timeout):
    client = GameClient(timeout=timeout)
    try:
        client.connect()
        return client.look()
    except (OSError, TimeoutError, GameError):
        return None
    finally:
        client.close()


def playable(snap):
    if not snap or not snap.get("in_game"):
        return False
    kind = snap.get("prompt_kind")
    if kind is None:
        kind = (snap.get("prompt") or {}).get("kind")
    return kind in (None, "none")


def wait_in_game(timeout):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = look_once(3)
        if playable(last):
            return last
        time.sleep(0.2)
    return last


def main():
    parser = argparse.ArgumentParser(description="Launch ToME and keep the pointer moving inside the window.")
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":10.0"))
    parser.add_argument("--xauthority", default=os.environ.get("XAUTHORITY", str(Path.home() / ".Xauthority")))
    parser.add_argument("--game", default=str(Path.home() / "tome-test" / "t-engine4-linux64-1.7.6"))
    parser.add_argument("--log", default=str(Path.home() / "tome-test" / "tome.log"))
    parser.add_argument("--save", help="Load this save. Only valid with --no-play. The acceptance test always uses auto_test.")
    parser.add_argument("--no-play", action="store_true", help="Stop once a character can act, and keep moving the pointer.")
    parser.add_argument("--wiggle-only", action="store_true", help="The game is already open. Only move the pointer.")
    parser.add_argument("--quit", action="store_true", help="Close the game when this script exits.")
    args = parser.parse_args()

    game_dir = Path(args.game)
    log_path = Path(args.log)
    display = Desktop(args.display, args.xauthority)
    started = None

    def shutdown(status):
        display.stop_wiggle()
        if args.quit and started is not None and started.poll() is None:
            os.killpg(started.pid, signal.SIGTERM)
        return status

    running_test = not args.no_play and not args.wiggle_only
    if running_test and args.save:
        print("The acceptance test always uses the auto_test character and does not load --save.")
        print("Load an existing character with: python3 tools/drive_game.py --save NAME --no-play")
        return 2

    # The test must not attach to a character that is already in a level. enter_test saves on the zone change.
    if not args.wiggle_only and (running_test or not playable(look_once(3))):
        if not (game_dir / "t-engine").exists():
            print("Game binary is missing: %s" % (game_dir / "t-engine"))
            return 2
        install_addon(REPO / "tome-auto-tome", game_dir / "game" / "addons" / "tome-auto-tome")
        if running_test:
            print("stopping the current game without saving, then starting auto_test", flush=True)
        stop_game()
        command = test_engine_command() if running_test else engine_command(args.save)
        started = launch_game(game_dir, log_path, display, command)

    display.start_wiggle()
    try:
        if not args.wiggle_only:
            ready = wait_in_game(150)
            if not ready or not ready.get("in_game"):
                print("A character is not in a level yet.")
                if log_path.exists():
                    tail = log_path.read_text(errors="replace").splitlines()[-30:]
                    print("\n".join(tail))
                return shutdown(1)
            print(
                "in game at %s,%s %s level %s" % (ready.get("x"), ready.get("y"), ready.get("zone"), ready.get("level")),
                flush=True,
            )
        if args.no_play or args.wiggle_only:
            print("pointer is moving inside the game window; Ctrl-C stops it", flush=True)
            while True:
                time.sleep(1)
        env = os.environ.copy()
        env["PYTHONPATH"] = "server"
        env["PYTHONUNBUFFERED"] = "1"
        result = subprocess.run([sys.executable, str(REPO / "tools" / "play_test.py")], cwd=str(REPO), env=env)
        return shutdown(result.returncode)
    except KeyboardInterrupt:
        return shutdown(0)
    except RuntimeError as error:
        print(error)
        return shutdown(1)


if __name__ == "__main__":
    sys.exit(main())
