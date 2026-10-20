import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "minescript"))

from farm_logic import Survey, at_approach, discover_farms, harvest_complete, maturity_target, needs_harvest, survey_from_blocks, world_mode


class Region:
    def __init__(self, min_pos=(0, 0, 0), max_pos=(25, 8, 25)):
        self.min_pos, self.max_pos = min_pos, max_pos
        self.blocks = {}

    def get_block(self, x, y, z):
        return self.blocks.get((x, y, z))

    def plot(self, x0, x1, y, z0, z1, *, planted=True):
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                self.blocks[x, y - 1, z] = "minecraft:soul_sand"
                if planted:
                    self.blocks[x, y, z] = "minecraft:nether_wart[age=3]"


class FarmLogicTests(unittest.TestCase):
    def test_three_30_by_30_floors_with_minescript_null_air(self):
        region = Region((-5, 0, -5), (45, 20, 45))
        for y in (5, 8, 11):
            region.plot(2, 31, y, 3, 32)
        farms = discover_farms(region)
        self.assertEqual([(farm.y, len(farm.cells), farm.truncated) for farm in farms],
                         [(5, 900, False), (8, 900, False), (11, 900, False)])

    def test_local_world_and_any_server_use_chest_storage(self):
        self.assertEqual(world_mode("localhost"), "singleplayer")
        self.assertEqual(world_mode("example.org:25565"), "server")

    def test_existing_17_by_5_plot_is_found_despite_stone_gap(self):
        region = Region((-10, 0, -10), (25, 20, 25))
        region.plot(2, 6, 5, 2, 18)
        region.blocks[2, 4, 6] = "minecraft:deepslate"
        region.blocks[2, 5, 6] = "minecraft:air"
        farms = discover_farms(region)
        self.assertEqual(len(farms), 1)
        self.assertEqual(len(farms[0].cells), 84)
        self.assertEqual(maturity_target(len(farms[0].cells), 0.85), 72)

    def test_discovers_separate_plots_and_floors_without_coordinates(self):
        region = Region()
        region.plot(2, 6, 3, 2, 5)
        region.plot(14, 17, 3, 14, 17)
        region.plot(2, 5, 6, 2, 4)
        region.blocks[4, 3, 3] = "minecraft:air"
        region.blocks[6, 2, 4] = "minecraft:deepslate"
        farms = discover_farms(region)
        self.assertEqual(sorted(len(f.cells) for f in farms), [12, 16, 19])
        self.assertEqual({f.y for f in farms}, {3, 6})
        self.assertFalse(any(f.truncated for f in farms))
        self.assertEqual(maturity_target(19, 0.85), 17)

    def test_empty_soil_and_scan_edge_are_not_silently_harvested(self):
        region = Region(max_pos=(10, 5, 10))
        region.plot(1, 3, 2, 1, 2, planted=False)
        region.plot(7, 10, 2, 6, 7)
        farms = discover_farms(region)
        self.assertEqual(len(farms), 1)
        self.assertTrue(farms[0].truncated)

    def test_survey_counts_age_and_fails_on_non_soil(self):
        cells = [(x, 3, 2) for x in range(20)]
        soil = ["minecraft:soul_sand"] * len(cells)
        crop = ["minecraft:nether_wart[age=3]"] * 17 + ["minecraft:nether_wart[age=1]"] * 2 + ["minecraft:air"]
        result = survey_from_blocks(cells, soil, crop)
        self.assertEqual((result.mature, result.young, result.empty), (17, 2, 1))
        soil[0] = "minecraft:deepslate"
        self.assertEqual(len(survey_from_blocks(cells, soil, crop).invalid), 1)

    def test_finish_sweep_after_replanting_even_if_a_few_crops_regrow(self):
        initial = Survey(900, 870, 30, 0, ())
        self.assertFalse(harvest_complete(initial, Survey(900, 1, 898, 1, ()), True))
        self.assertTrue(harvest_complete(initial, Survey(900, 1, 899, 0, ()), True))
        self.assertTrue(harvest_complete(initial, Survey(900, 5, 895, 0, ()), True))
        self.assertFalse(harvest_complete(initial, Survey(900, 6, 894, 0, ()), True))
        self.assertFalse(harvest_complete(initial, Survey(900, 1, 899, 0, ()), False))

    def test_interrupted_sweep_resumes_to_replant_empty_cells(self):
        self.assertTrue(needs_harvest(Survey(900, 100, 799, 1, ()), 0.85))
        self.assertFalse(needs_harvest(Survey(900, 100, 800, 0, ()), 0.85))

    def test_chest_approach_requires_reaching_adjacent_block(self):
        approach = {"x": 10, "y": 98, "z": 12}
        self.assertFalse(at_approach((13.5, 98.0, 12.5), approach))
        self.assertFalse(at_approach((10.5, 101.0, 12.5), approach))
        self.assertTrue(at_approach((10.5, 97.875, 12.5), approach))


if __name__ == "__main__":
    unittest.main()
