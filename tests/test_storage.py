"""Checks for generic chest storage without a running Minecraft client."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "minescript"))
sys.modules.setdefault("minescript", types.ModuleType("minescript"))

import farm_controller as controller


class Region:
    min_pos = (0, 0, 0)
    max_pos = (12, 8, 12)

    def get_block(self, x, y, z):
        if (x, y, z) == (6, 3, 5):
            return "minecraft:chest[facing=north,type=single,waterlogged=false]"
        if y == 2:
            return "minecraft:stone"
        return None


class StorageTests(unittest.TestCase):
    def test_any_server_skips_identity_and_base_checks(self):
        with patch.object(controller.ms, "world_info", return_value=types.SimpleNamespace(address="example.org:25565"), create=True), \
                patch.object(controller.ms, "player_name", side_effect=AssertionError("nickname queried"), create=True):
            self.assertEqual(controller.check_location(), "server")

    def test_nearby_chest_is_found_without_server_coordinates(self):
        with patch.object(controller.ms, "get_block_region", return_value=Region(), create=True), \
                patch.object(controller, "chest_distance", return_value=3), \
                patch.object(controller, "report"):
            plans = controller.find_storage((5, 3, 5))
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["chest"], {"x": 6, "y": 3, "z": 5})
        self.assertTrue(plans[0]["approaches"])

    def test_cash_out_only_stores_in_chests(self):
        with patch.object(controller, "command") as command, \
                patch.object(controller, "store_in_chests", return_value=12) as store:
            self.assertEqual(controller.cash_out(True, ("chest",)), 12)
        command.assert_called_once_with("stop")
        store.assert_called_once_with(("chest",), required=True)

    def test_full_first_chest_uses_next_chest(self):
        stacks = [types.SimpleNamespace(slot=54 + i, item=controller.WART, count=64)
                  for i in range(3)]
        active = {"chest": None}
        plans = tuple({"chest": {"x": i, "y": 3, "z": 5},
                       "approach": {"x": i, "y": 3, "z": 4}} for i in (5, 6))

        def open_chest(chest):
            active["chest"] = chest["x"]
            return 54

        def click(slot, **_kwargs):
            before = sum(item.count for item in stacks)
            if active["chest"] == 6:
                stacks[:] = [item for item in stacks if item.slot != slot]
            return sum(item.count for item in stacks) if active["chest"] == 6 else before

        with patch.object(controller, "approach_chest"), \
                patch.object(controller, "open_chest", side_effect=open_chest), \
                patch.object(controller, "close_menu"), \
                patch.object(controller, "click_slot", side_effect=click), \
                patch.object(controller, "wart_stack_count", side_effect=lambda: len(stacks)), \
                patch.object(controller, "inventory_wart", side_effect=lambda: sum(item.count for item in stacks)), \
                patch.object(controller, "free_slots", return_value=35), \
                patch.object(controller.ms, "container_get_items", side_effect=lambda: stacks, create=True), \
                patch.object(controller, "report"):
            self.assertEqual(controller.store_in_chests(plans, required=True), 128)
        self.assertEqual(len(stacks), 1)


if __name__ == "__main__":
    unittest.main()
