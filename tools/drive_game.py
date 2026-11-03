#!/usr/bin/env python3
"""Launch ToME, replay a fixed click path, and keep the pointer moving.

Run this on the machine that shows the game. An idle character blocks the engine
in SDL_WaitEvent, so the bridge does not see a request until a real pointer or
key event arrives. After the click path, this script slides the pointer a few
pixels across the portrait until the test process exits.

    python3 tools/drive_game.py
    python3 tools/drive_game.py --no-play
    python3 tools/drive_game.py --new tutorial
    python3 tools/drive_game.py --wiggle-only

Coordinates are pixels inside the 800x600 game window and were taken from the
unlocked Ubuntu desktop: Load Game, the first save row, New Game, Tutorial,
Basic Gameplay.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from auto_tome_mcp.game import GameClient, GameError

REPO = Path(__file__).resolve().parents[1]
LOAD_SAVE = (
    ("click", 520, 123),
    ("pause", 1.0),
    ("click", 131, 107),
    ("pause", 0.4),
    ("key", "Return"),
)
NEW_TUTORIAL = (
    ("click", 574, 95),
    ("until_log", "done loading module", "Age of Ascendancy"),
    ("click", 753, 86),
    ("pause", 1.0),
    ("click", 399, 271),
    ("pause", 2.0),
    ("key", "Escape"),
    ("pause", 0.6),
    ("key", "Escape"),
)


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

    def click_client(self, x, y):
        window = self.client_window()
        if window is None:
            raise RuntimeError("The game window is not on screen.")
        with self.lock:
            self.run(["xdotool", "mousemove", "--window", str(window[0]), str(int(x)), str(int(y))])
            self.run(["xdotool", "click", "--window", str(window[0]), "1"])

    def key(self, name):
        window = self.client_window()
        with self.lock:
            if window is None:
                self.run(["xdotool", "key", name])
            else:
                self.run(["xdotool", "key", "--window", str(window[0]), name])

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


def launch_game(game_dir, log_path, display):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w")
    env = os.environ.copy()
    env["DISPLAY"] = display.env["DISPLAY"]
    env["XAUTHORITY"] = display.env["XAUTHORITY"]
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["SDL_VIDEODRIVER"] = "x11"
    process = subprocess.Popen(
        ["./t-engine"],
        cwd=str(game_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    process.log_file = log_file
    return process


def wait_for(predicate, timeout, label):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.4)
    raise RuntimeError("Timed out waiting for %s." % label)


class LogTail:
    def __init__(self, path):
        self.path = path
        self.mark = path.stat().st_size if path.exists() else 0

    def contains(self, *needles):
        if not self.path.exists():
            return False
        text = self.path.read_text(errors="replace")
        if self.mark > len(text):
            self.mark = 0
        return any(all(needle in line for needle in needles) for line in text[self.mark:].splitlines())


def play_steps(display, steps, log_tail):
    for step in steps:
        kind = step[0]
        if kind == "click":
            print("click %s,%s" % (step[1], step[2]), flush=True)
            display.click_client(step[1], step[2])
        elif kind == "key":
            print("key %s" % step[1], flush=True)
            display.key(step[1])
        elif kind == "pause":
            time.sleep(step[1])
        elif kind == "until_log":
            print("wait for log %s" % " ".join(step[1:]), flush=True)
            wait_for(lambda: log_tail.contains(*step[1:]), 90, " ".join(step[1:]))
        else:
            raise RuntimeError("Unknown step %s" % kind)


def look_once(timeout):
    client = GameClient(timeout=timeout)
    try:
        client.connect()
        return client.look()
    except (OSError, TimeoutError, GameError):
        return None
    finally:
        client.close()


def wait_in_game(timeout):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = look_once(3)
        if last and last.get("in_game") and last.get("can_act") and not last.get("activity"):
            prompt = (last.get("prompt") or {}).get("kind")
            if prompt in (None, "none"):
                return last
        time.sleep(0.2)
    return last


def main():
    parser = argparse.ArgumentParser(description="Launch ToME and keep the pointer moving inside the window.")
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":10.0"))
    parser.add_argument("--xauthority", default=os.environ.get("XAUTHORITY", str(Path.home() / ".Xauthority")))
    parser.add_argument("--game", default=str(Path.home() / "tome-test" / "t-engine4-linux64-1.7.6"))
    parser.add_argument("--log", default=str(Path.home() / "tome-test" / "tome.log"))
    parser.add_argument("--new", choices=("tutorial",), help="Create a tutorial character instead of loading the first save.")
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

    if not args.wiggle_only and not engine_pids():
        if not (game_dir / "t-engine").exists():
            print("Game binary is missing: %s" % (game_dir / "t-engine"))
            return 2
        install_addon(REPO / "tome-auto-tome", game_dir / "game" / "addons" / "tome-auto-tome")
        print("launch %s" % game_dir, flush=True)
        started = launch_game(game_dir, log_path, display)
        log_tail = LogTail(log_path)
        log_tail.mark = 0
        wait_for(lambda: display.client_window() and log_tail.contains("Main Menu"), 90, "the main menu")
        time.sleep(1)
    else:
        log_tail = LogTail(log_path)
        if display.client_window() is None and not args.wiggle_only:
            print("ToME is running, but its window is not on this display.")
            return 2

    display.start_wiggle()
    try:
        if not args.wiggle_only:
            current = look_once(3)
            if not (current and current.get("in_game")):
                play_steps(display, NEW_TUTORIAL if args.new else LOAD_SAVE, log_tail)
            ready = wait_in_game(90)
            if not ready or not ready.get("in_game"):
                print("A character is not in a level yet.")
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
