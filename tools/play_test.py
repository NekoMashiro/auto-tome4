#!/usr/bin/env python3
"""Walk the Auto Test zone with look and act only.

Launch ToME with the auto-tome addon enabled and a character already in a level,
then run: PYTHONPATH=server python3 tools/play_test.py
"""

import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from auto_tome_mcp.game import GameClient, GameError

DIRECTIONS = {
    (0, -1): 8,
    (0, 1): 2,
    (-1, 0): 4,
    (1, 0): 6,
    (-1, -1): 7,
    (1, -1): 9,
    (-1, 1): 1,
    (1, 1): 3,
}


class StepError(RuntimeError):
    def __init__(self, step, snap):
        self.step = step
        self.snap = snap
        prompt = (snap or {}).get("prompt") or {}
        super().__init__(
            "%s failed: status=%s code=%s at %s,%s level=%s prompt=%s %s log=%s"
            % (
                step,
                (snap or {}).get("status"),
                (snap or {}).get("code"),
                (snap or {}).get("x"),
                (snap or {}).get("y"),
                (snap or {}).get("level"),
                (snap or {}).get("prompt_kind") or prompt.get("kind"),
                prompt.get("title") or (snap or {}).get("message") or "",
                " | ".join((snap or {}).get("log") or []),
            )
        )


def stack_count(label):
    text = label or ""
    match = re.search(r"\((\d+)\)\s*$", text)
    if match:
        return int(match.group(1))
    match = re.match(r"(\d+)\s+", text)
    return int(match.group(1)) if match else 1


def walkable():
    tiles = set()
    for x in range(1, 38):
        tiles.add((x, 2))
    tiles.add((37, 3))
    for y in range(3, 33):
        tiles.add((20, y))
    for x in range(16, 31):
        tiles.add((x, 32))
    return tiles


def bfs(start, goal, tiles):
    if start == goal:
        return []
    if start not in tiles or goal not in tiles:
        return None
    queue = [start]
    previous = {start: None}
    while queue:
        x, y = queue.pop(0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (x + dx, y + dy)
            if nxt not in tiles or nxt in previous:
                continue
            previous[nxt] = (x, y)
            if nxt == goal:
                path = [nxt]
                while previous[path[-1]] != start:
                    path.append(previous[path[-1]])
                path.reverse()
                return path
            queue.append(nxt)
    return None


def direction(dx, dy):
    return DIRECTIONS[(dx, dy)]


class Script:
    def __init__(self, client):
        self.client = client
        self.tiles = walkable()

    def act(self, action):
        try:
            result = self.client.act(action, str(uuid.uuid4()))
        except GameError as error:
            raise StepError(action.get("type"), {"status": "failed", "code": str(error), "log": []})
        result = self.attach_prompt(result)
        if result.get("status") == "failed":
            raise StepError(action.get("type"), result)
        return result

    def attach_prompt(self, snap):
        if not isinstance(snap, dict) or snap.get("prompt"):
            return snap
        kind = snap.get("prompt_kind") or "none"
        if kind == "none":
            snap["prompt"] = {"kind": "none", "options": []}
            return snap
        snap["prompt"] = self.client.look("prompt")
        return snap

    def poll(self, predicate, timeout, first=None):
        deadline = time.time() + timeout
        snap = first
        while True:
            if snap is None:
                snap = self.client.look()
            if predicate(snap):
                return snap
            if time.time() > deadline:
                raise StepError("timed out", snap)
            time.sleep(0.05)
            snap = None

    def ready(self, timeout=60):
        def quiet(snap):
            return snap.get("in_game") and snap.get("prompt_kind", "none") in (None, "none")
        return self.poll(quiet, timeout)

    def world(self, action, timeout=60):
        self.ready(timeout)
        return self.act(action)

    def settle(self, timeout=90):
        def quiet(snap):
            return snap.get("prompt_kind", "none") in (None, "none")
        return self.poll(quiet, timeout)

    def option(self, snap, labels):
        wanted = {label.lower() for label in labels}
        for choice in (snap.get("prompt") or {}).get("options") or []:
            if (choice.get("label") or "").lower() in wanted:
                return choice
        return None

    def option_containing(self, snap, text, avoid=()):
        for choice in (snap.get("prompt") or {}).get("options") or []:
            label = choice.get("label") or ""
            lower = label.lower()
            if any(skip.lower() in lower for skip in avoid):
                continue
            if text.lower() in lower:
                return choice
        return None

    def close_prompt(self, snap):
        for _ in range(5):
            kind = (snap.get("prompt") or {}).get("kind")
            if kind in (None, "none"):
                return snap
            if kind != "choose":
                raise StepError("could not close the prompt", snap)
            snap = self.act({"type": "cancel"})
        raise StepError("prompt stayed open", snap)

    def choose(self, snap, labels=None, contains=None, avoid=()):
        option = self.option(snap, labels) if labels else self.option_containing(snap, contains, avoid)
        if not option:
            raise StepError("missing option %s" % (labels or contains), snap)
        return self.act({"type": "choose", "label": option.get("label") or ""})

    def find_item(self, snap, name):
        for item in snap.get("inventory") or []:
            if name.lower() in (item.get("name") or "").lower():
                return item
        return None

    def find_actor(self, snap, name):
        for actor in snap.get("actors") or []:
            if name.lower() in (actor.get("name") or "").lower():
                return actor
        return None

    def step_toward(self, x, y):
        stuck = 0
        last = None
        for _ in range(120):
            snap = self.ready()
            if snap["x"] == x and snap["y"] == y:
                return snap
            path = bfs((snap["x"], snap["y"]), (x, y), self.tiles)
            if not path:
                raise StepError("no path to %s,%s" % (x, y), snap)
            nx, ny = path[0]
            result = self.act({"type": "step", "direction": direction(nx - snap["x"], ny - snap["y"])})
            if (result.get("prompt") or {}).get("kind") not in (None, "none"):
                raise StepError("step opened a prompt", result)
            if (result.get("x"), result.get("y")) == last:
                stuck += 1
                if stuck >= 4:
                    raise StepError("stuck walking to %s,%s" % (x, y), result)
            else:
                stuck = 0
            last = (result.get("x"), result.get("y"))
        raise StepError("too many steps toward %s,%s" % (x, y), self.client.look())

    def run(self):
        print("enter_test")
        entered = self.world({"type": "enter_test"}, timeout=120)
        snap = self.poll(
            lambda item: item.get("zone") == "auto-test" and item.get("level") == 1 and item.get("prompt_kind", "none") in (None, "none"),
            30,
            entered,
        )
        if (snap.get("x"), snap.get("y")) != (2, 2):
            raise StepError("player was not placed at the test start", snap)
        if not self.find_actor(snap, "test dummy"):
            raise StepError("test dummy is not visible", snap)

        print("step")
        moved = self.world({"type": "step", "direction": 6})
        if (moved.get("x"), moved.get("y")) != (3, 2):
            raise StepError("east step did not move one tile", moved)
        if not self.find_actor(moved, "test dummy"):
            raise StepError("the east step attacked before reaching the dummy", moved)

        print("bump attack")
        killed = False
        for _ in range(8):
            snap = self.ready()
            dummy = self.find_actor(snap, "test dummy")
            if not dummy:
                killed = True
                break
            if abs(dummy["x"] - snap["x"]) > 1 or abs(dummy["y"] - snap["y"]) > 1:
                raise StepError("test dummy is not adjacent", snap)
            result = self.act({
                "type": "step",
                "direction": direction(dummy["x"] - snap["x"], dummy["y"] - snap["y"]),
            })
            if result.get("prompt", {}).get("kind") == "choose":
                result = self.choose(result, labels=("yes", "是"))
            if not self.find_actor(result, "test dummy"):
                killed = True
                break
        if not killed:
            raise StepError("bump attack did not remove the dummy", self.client.look())

        print("rest")
        before = self.ready()
        rested = self.act({"type": "rest"})
        log = " ".join(rested.get("log") or []).lower()
        if rested["life"] < before["life"] and "rest" not in log and "休息" not in log:
            raise StepError("rest did not run", rested)
        self.ready()

        print("door")
        self.step_toward(7, 2)

        print("run")
        before = self.ready()
        ran = self.act({"type": "run", "direction": 6})
        if ran["x"] <= before["x"]:
            raise StepError("run did not move east", ran)
        self.ready()

        print("auto_explore")
        before = self.ready()
        explored = self.act({"type": "auto_explore"})
        explore_log = " ".join(explored.get("log") or []).lower()
        moved = (explored["x"], explored["y"]) != (before["x"], before["y"])
        if not moved and "explor" not in explore_log and "nowhere" not in explore_log and "探索" not in explore_log:
            raise StepError("auto_explore did not run", explored)
        self.ready()

        print("pickup")
        self.step_toward(37, 3)
        picked = self.world({"type": "pickup"})
        if picked.get("prompt", {}).get("kind") == "choose":
            picked = self.choose(picked, contains="test gem", avoid=("test shard",))
        picked = self.close_prompt(picked)
        snap = self.ready()
        names = " ".join((item.get("name") or "") for item in snap.get("floor") or []).lower()
        if "test gem" in names:
            raise StepError("test gem was not picked up", snap)

        print("aim")
        aimed = self.world({"type": "use", "id": "T_AUTO_TOME_BOLT"})
        if aimed.get("prompt", {}).get("kind") != "aim":
            raise StepError("targeted talent did not ask for an aim", aimed)
        target_x = aimed["x"] + 1 if (aimed["x"] + 1, aimed["y"]) in self.tiles else aimed["x"]
        fired = self.act({"type": "aim", "x": target_x, "y": aimed["y"]})
        if fired.get("prompt", {}).get("kind") == "choose":
            fired = self.choose(fired, labels=("yes", "是"))
        if not any("bolt" in line.lower() for line in fired.get("log") or []):
            raise StepError("test bolt did not fire", fired)
        self.ready()

        print("use item")
        opened = self.world({"type": "open_inventory"})
        if not self.option_containing(opened, "test salve"):
            raise StepError("test salve is missing", opened)
        used = self.choose(opened, contains="test salve")
        used = self.choose(used, labels=("use", "使用"))
        if (used.get("prompt") or {}).get("kind") == "choose":
            used = self.choose(used, labels=("yes", "是", "accept", "确定"))
        used = self.close_prompt(used)
        if not any("salve" in line.lower() for line in used.get("log") or []):
            raise StepError("test salve was not used", used)
        opened = self.world({"type": "open_inventory"})
        if self.option_containing(opened, "test salve"):
            raise StepError("test salve was not consumed", opened)
        self.act({"type": "cancel"})

        print("cancel")
        opened = self.world({"type": "open_inventory"})
        if opened.get("prompt", {}).get("kind") != "choose":
            raise StepError("inventory did not open", opened)
        if not self.option_containing(opened, "test pebble"):
            raise StepError("test pebble is not in the inventory", opened)
        closed = self.act({"type": "cancel"})
        if closed.get("prompt", {}).get("kind") not in (None, "none"):
            raise StepError("cancel left a prompt", closed)
        opened = self.world({"type": "open_inventory"})
        if not self.option_containing(opened, "test pebble"):
            raise StepError("cancel removed the test pebble", opened)
        self.act({"type": "cancel"})

        print("quantity")
        opened = self.world({"type": "open_inventory"})
        before = self.option_containing(opened, "test pebble")
        before_count = stack_count(before.get("label") if before else "")
        opened = self.choose(opened, contains="test pebble")
        opened = self.choose(opened, labels=("drop", "丢弃", "扔掉"))
        if opened.get("prompt", {}).get("kind") != "quantity":
            raise StepError("drop did not ask for a quantity", opened)
        dropped = self.act({"type": "quantity", "quantity": 1})
        dropped = self.close_prompt(dropped)
        opened = self.world({"type": "open_inventory"})
        after = self.option_containing(opened, "test pebble")
        after_count = stack_count(after.get("label") if after else "")
        self.act({"type": "cancel"})
        if after_count >= before_count:
            raise StepError("dropping one pebble did not shrink the stack", dropped)

        print("levelup")
        before_stats = self.ready().get("unused_stats") or 0
        dialog = self.world({"type": "open_levelup"})
        if dialog.get("prompt", {}).get("kind") != "adjust":
            raise StepError("levelup did not open", dialog)
        nodes = [item["node"] for item in dialog["prompt"].get("nodes") or [] if str(item.get("node", "")).startswith("stat:")]
        if not nodes:
            raise StepError("levelup has no stat node", dialog)
        spent = dialog
        for node in nodes:
            spent = self.act({"type": "adjust", "node": node, "delta": 1})
            if (spent.get("unused_stats") or 0) < before_stats:
                break
        else:
            raise StepError("no stat accepted a point", spent)
        dialog = self.choose(spent, labels=("finish",))
        dialog = self.choose(dialog, labels=("yes", "是"))
        if dialog.get("prompt", {}).get("kind") not in (None, "none"):
            raise StepError("accepting levelup left a prompt", dialog)
        after_stats = self.ready().get("unused_stats") or 0
        if after_stats != before_stats - 1:
            raise StepError("stat point was not spent", dialog)

        print("text")
        opened = self.world({"type": "open_inventory"})
        opened = self.choose(opened, contains="test gem", avoid=("test shard",))
        opened = self.choose(opened, labels=("tag", "标记"))
        if opened.get("prompt", {}).get("kind") != "text":
            raise StepError("tag did not ask for text", opened)
        tagged = self.act({"type": "text", "text": "hq"})
        tagged = self.close_prompt(tagged)
        self.ready()

        print("switch_weapons")
        before = self.ready().get("mainhand") or ""
        self.world({"type": "switch_weapons"})
        after = self.ready().get("mainhand") or ""
        if after == before or "spare" not in after.lower():
            raise StepError("weapon set did not switch to the test spare", {"mainhand": after, "log": [], "prompt": {}})

        print("change_level")
        self.step_toward(37, 2)
        changed = self.world({"type": "change_level"})
        if changed.get("prompt", {}).get("kind") not in (None, "none"):
            raise StepError("change_level opened a dialog", changed)
        if changed.get("level_move") not in ("up", "down", "zone"):
            raise StepError("change_level did not report a move", changed)
        done = self.poll(lambda item: item.get("zone") == "auto-test" and item.get("level") == 2, 30, changed)
        print("test level complete at %s,%s" % (done.get("x"), done.get("y")))


def main():
    client = GameClient()
    try:
        client.connect()
        first = client.look()
    except OSError as error:
        print("Could not reach 127.0.0.1:9741 (%s)." % error)
        print("Launch ToME with the auto-tome addon enabled and load a character into a level, then run this script again.")
        return 2
    except GameError as error:
        print(error)
        return 1
    if not first.get("in_game"):
        print("The bridge is up, but no character is in a level yet.")
        client.close()
        return 2
    try:
        Script(client).run()
    except (StepError, GameError) as error:
        print(error)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
