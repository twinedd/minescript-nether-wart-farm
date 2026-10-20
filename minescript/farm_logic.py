"""Pure helpers for the nether-wart controller."""

from dataclasses import dataclass
from collections import deque
import math

WART = "minecraft:nether_wart"
SOIL = "minecraft:soul_sand"


def region_air(block):
    """Minescript BlockRegion represents air as None, unlike getblocklist."""
    return block is None or block == "minecraft:air"


def world_mode(address):
    """Choose polling speed; both singleplayer and servers use chest storage."""
    host = (address or "").lower().split(":", 1)[0]
    return "singleplayer" if host == "localhost" else "server"


@dataclass(frozen=True)
class Survey:
    total: int
    mature: int
    young: int
    empty: int
    invalid: tuple

    @property
    def ratio(self):
        return self.mature / self.total if self.total else 0.0


@dataclass(frozen=True)
class DetectedFarm:
    """One connected patch of soul sand with wart, at a single crop level."""

    cells: tuple
    min_x: int
    max_x: int
    y: int
    min_z: int
    max_z: int
    truncated: bool = False

    @property
    def name(self):
        return f"x={self.min_x}..{self.max_x}, y={self.y}, z={self.min_z}..{self.max_z}"


def discover_farms(region, min_cells=4):
    """Find planted plots in a loaded Minescript BlockRegion.

    Empty soul sand belongs to a plot only when connected to at least one
    nether wart block. A plot touching the scan border is marked incomplete.
    """
    x0, y0, z0 = region.min_pos
    x1, y1, z1 = region.max_pos
    candidates = {}
    planted = set()
    for soil_y in range(y0, y1):
        crop_y = soil_y + 1
        level = set()
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                if region.get_block(x, soil_y, z) != SOIL:
                    continue
                crop = region.get_block(x, crop_y, z)
                if region_air(crop) or crop == WART or crop.startswith(WART + "["):
                    level.add((x, crop_y, z))
                    if crop == WART or (crop and crop.startswith(WART + "[")):
                        planted.add((x, crop_y, z))
        candidates[crop_y] = level

    farms = []
    for crop_y, level in candidates.items():
        while level:
            start = level.pop()
            component = {start}
            queue = deque([start])
            while queue:
                x, y, z = queue.popleft()
                for neighbor in ((x - 1, y, z), (x + 1, y, z),
                                 (x, y, z - 1), (x, y, z + 1)):
                    if neighbor in level:
                        level.remove(neighbor)
                        component.add(neighbor)
                        queue.append(neighbor)
            if len(component) < min_cells or not (component & planted):
                continue
            xs = [p[0] for p in component]
            zs = [p[2] for p in component]
            truncated = any(x in (x0, x1) or z in (z0, z1) or
                            y == y0 + 1 or y == y1 for x, y, z in component)
            farms.append(DetectedFarm(tuple(sorted(component)), min(xs), max(xs), crop_y,
                                      min(zs), max(zs), truncated))
    # Baritone uses a rectangular selection. Merge overlapping rectangles so
    # the same crop cannot belong to two farm runs.
    changed = True
    while changed:
        changed = False
        for i, first in enumerate(farms):
            for j in range(i + 1, len(farms)):
                second = farms[j]
                if (first.y != second.y or first.max_x < second.min_x or
                        second.max_x < first.min_x or first.max_z < second.min_z or
                        second.max_z < first.min_z):
                    continue
                cells = tuple(sorted(set(first.cells) | set(second.cells)))
                farms[i] = DetectedFarm(cells, min(first.min_x, second.min_x),
                                        max(first.max_x, second.max_x), first.y,
                                        min(first.min_z, second.min_z),
                                        max(first.max_z, second.max_z),
                                        first.truncated or second.truncated)
                farms.pop(j)
                changed = True
                break
            if changed:
                break
    return tuple(sorted(farms, key=lambda farm: (farm.y, farm.min_x, farm.min_z)))


def survey_from_blocks(cells, soil_blocks, crop_blocks):
    if len(cells) != len(soil_blocks) or len(cells) != len(crop_blocks):
        raise ValueError("Неполный ответ сканирования мира")
    mature = young = empty = 0
    invalid = []
    for pos, soil, crop in zip(cells, soil_blocks, crop_blocks):
        if soil != SOIL:
            invalid.append((pos, soil, crop))
        elif region_air(crop):
            empty += 1
        elif crop == WART or crop.startswith(WART + "["):
            if "age=3" in crop:
                mature += 1
            else:
                young += 1
        else:
            invalid.append((pos, soil, crop))
    return Survey(len(cells), mature, young, empty, tuple(invalid))


def maturity_target(total, threshold):
    return math.ceil(total * threshold)


def needs_harvest(state, threshold):
    """Resume unfinished replanting after an interrupted run."""
    return state.empty > 0 or state.mature >= maturity_target(state.total, threshold)


def harvest_complete(initial, current, saw_work):
    """Finish a normal sweep despite a few crops maturing behind the bot."""
    if not saw_work or current.empty:
        return False
    allowance = max(1, math.ceil(current.total * 0.005))
    return (current.mature <= allowance and
            initial.mature - current.mature >= initial.mature * 0.9)


def at_approach(position, block_pos):
    """Check Baritone's actual destination, not the chest's distant reach sphere."""
    x, y, z = position
    return (abs(y - block_pos["y"]) < 0.65 and
            math.hypot(x - block_pos["x"] - 0.5,
                       z - block_pos["z"] - 0.5) <= 0.8)


def item_count(items, item_name=WART):
    return sum(item.count for item in items if item.item == item_name)
