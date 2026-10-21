"""Checks the click-to-select workflow without a running Minecraft client."""

import json
from pathlib import Path
from queue import Empty
import runpy
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "minescript"))
sys.modules.setdefault("minescript", types.ModuleType("minescript"))
import farm_controller as controller


class ChestSelectionTests(unittest.TestCase):
    def test_double_chest_halves_count_as_one(self):
        left = "minecraft:chest[facing=north,type=left,waterlogged=false]"
        right = "minecraft:chest[facing=north,type=right,waterlogged=false]"
        blocks = {(6, 3, 5): left, (7, 3, 5): right}
        with patch.object(controller.ms, "getblock", side_effect=lambda *p: blocks.get(p), create=True):
            self.assertEqual(controller.chest_group_key({"x": 6, "y": 3, "z": 5}, left),
                             controller.chest_group_key({"x": 7, "y": 3, "z": 5}, right))

    def test_right_click_selects_once_and_done_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            selection = Path(directory) / "farm.chest_selection.json"
            done = Path(directory) / "farm.chest_selection.done"

            class Events:
                calls = 0

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    pass

                def register_mouse_listener(self):
                    pass

                def get(self, timeout=None):
                    self.calls += 1
                    if self.calls <= 2:
                        return types.SimpleNamespace(type="mouse", button=1, action=1, screen=None)
                    done.write_text(json.loads(selection.read_text())["session"], encoding="utf-8")
                    raise Empty

            def getblock(x, y, z):
                if (x, y, z) == (6, 3, 5):
                    return "minecraft:chest[facing=north,type=single]"
                return "minecraft:stone" if y == 2 else "minecraft:air"

            with patch.object(controller, "CHEST_SELECTION", selection), \
                    patch.object(controller, "CHEST_SELECTION_DONE", done), \
                    patch.object(controller, "halted"), \
                    patch.object(controller, "report"), \
                    patch.object(controller.ms, "EventQueue", Events, create=True), \
                    patch.object(controller.ms, "EventType", types.SimpleNamespace(MOUSE="mouse"), create=True), \
                    patch.object(controller.ms, "player_get_targeted_block",
                                 return_value=types.SimpleNamespace(position=(6, 3, 5)), create=True), \
                    patch.object(controller.ms, "player_position", return_value=(5.5, 3.0, 5.5), create=True), \
                    patch.object(controller.ms, "getblock", side_effect=getblock, create=True):
                plans = controller.select_chests()

            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0]["chest"], {"x": 6, "y": 3, "z": 5})
            self.assertEqual(len(json.loads(selection.read_text())["chests"]), 1)

    def test_done_requires_selection_and_active_run(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            shutil.copy2(Path(__file__).resolve().parents[1] / "minescript" / "farm_done.py",
                         folder / "farm_done.py")
            (folder / "farm.running").write_text("running", encoding="utf-8")
            (folder / "farm.status.json").write_text(
                json.dumps({"phase": "SELECT CHESTS", "time": time.time()}), encoding="utf-8")
            selection = folder / "farm.chest_selection.json"
            selection.write_text(json.dumps({"session": "abc", "chests": []}), encoding="utf-8")
            with patch.object(controller.ms, "echo", create=True) as echo:
                runpy.run_path(str(folder / "farm_done.py"), run_name="__main__")
            self.assertFalse((folder / "farm.chest_selection.done").exists())
            self.assertIn("at least one chest", str(echo.call_args))

            selection.write_text(json.dumps({"session": "abc", "chests": [{"x": 6, "y": 3, "z": 5}]}),
                                 encoding="utf-8")
            with patch.object(controller.ms, "echo", create=True):
                runpy.run_path(str(folder / "farm_done.py"), run_name="__main__")
            self.assertEqual((folder / "farm.chest_selection.done").read_text(), "abc")

    def test_main_uses_selected_storage_without_scanning_for_chests(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            plan = {"chest": {"x": 6, "y": 3, "z": 5},
                    "approach": {"x": 5, "y": 3, "z": 5}}
            farm = types.SimpleNamespace(name="plot", y=3, cells=((1, 3, 1),))
            state = controller.survey_from_blocks(
                farm.cells, ["minecraft:soul_sand"], ["minecraft:nether_wart[age=3]"])
            order = []

            def select():
                order.append("select")
                return (plan,)

            def scan(_origin):
                order.append("scan")
                return (farm,)

            with patch.object(controller, "ROOT", folder), \
                    patch.object(controller, "STOP", folder / "farm.stop"), \
                    patch.object(controller, "STATUS", folder / "farm.status.json"), \
                    patch.object(controller, "CHEST_SELECTION", folder / "farm.chest_selection.json"), \
                    patch.object(controller, "CHEST_SELECTION_DONE", folder / "farm.chest_selection.done"), \
                    patch.object(controller, "check_location", return_value="server"), \
                    patch.object(controller, "select_chests", side_effect=select), \
                    patch.object(controller, "scan_farms", side_effect=scan), \
                    patch.object(controller, "find_storage", side_effect=AssertionError("unexpected auto-scan")), \
                    patch.object(controller, "survey", return_value=state), \
                    patch.object(controller, "store_in_chests"), \
                    patch.object(controller, "harvest") as harvest, \
                    patch.object(controller, "cash_out") as cash_out, \
                    patch.object(controller, "report"), \
                    patch.object(controller.ms, "player_position", return_value=(1.5, 3.0, 1.5), create=True), \
                    patch.object(controller.ms, "chat", create=True), \
                    patch.object(sys, "argv", ["start.py", "once"]):
                controller.main()

            self.assertEqual(order, ["select", "scan"])
            harvest.assert_called_once_with(farm, "server", (plan,), "1/1")
            cash_out.assert_called_once_with(resume=False, storage=(plan,))


if __name__ == "__main__":
    unittest.main()
