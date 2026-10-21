r"""Minescript + Baritone nether-wart farm with chest-only storage.

Run in Minecraft chat as ``\start``. ``\start once`` runs a single harvest.
"""

import json
import math
from pathlib import Path
from queue import Empty
import sys
import time
import traceback
import uuid

import minescript as ms
from farm_logic import WART, at_approach, discover_farms, harvest_complete, item_count, maturity_target, needs_harvest, region_air, survey_from_blocks, world_mode

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "farm_config.json").read_text(encoding="utf-8"))
STATUS = ROOT / "farm.status.json"
STOP = ROOT / "farm.stop"
LOG = ROOT / "farm.log"
CHEST_SELECTION = ROOT / "farm.chest_selection.json"
CHEST_SELECTION_DONE = ROOT / "farm.chest_selection.done"


def report(phase, detail="", *, echo=False):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {phase}: {detail}"
    with LOG.open("a", encoding="utf-8") as out:
        out.write(line + "\n")
    STATUS.write_text(json.dumps({"phase": phase, "detail": detail, "time": time.time()}, ensure_ascii=False), encoding="utf-8")
    ms.log("[FARM]", phase, detail)
    if echo:
        ms.echo("[FARM]", phase, detail)


def halted():
    if STOP.exists():
        raise InterruptedError("Stopped with \\stop")


def pause(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        halted()
        time.sleep(min(0.2, end - time.monotonic()))


def command(text):
    halted()
    ms.chat("#" + text)
    time.sleep(0.3)


def inventory_wart():
    return item_count(ms.player_inventory())


def wart_stack_count():
    return sum(1 for item in ms.player_inventory() if item.item == WART)


def free_slots():
    used = {item.slot for item in ms.player_inventory() if 0 <= item.slot < 36}
    return 36 - len(used)


def survey(farm):
    soil = ms.getblocklist([[x, y - 1, z] for x, y, z in farm.cells])
    crop = ms.getblocklist([list(pos) for pos in farm.cells])
    result = survey_from_blocks(farm.cells, soil, crop)
    if result.invalid:
        sample = result.invalid[:3]
        raise RuntimeError(f"Farm is not loaded or has changed: {sample}")
    return result


def scan_farms(origin):
    """Read nearby loaded blocks, shrinking the radius if outer chunks are absent."""
    cx, cy, cz = origin
    vertical = CONFIG["scanVerticalRadius"]
    errors = []
    for radius in dict.fromkeys((CONFIG["scanRadius"], 40, 32, 24, 16)):
        if radius > CONFIG["scanRadius"]:
            continue
        try:
            region = ms.get_block_region(
                [cx - radius, cy - vertical - 1, cz - radius],
                [cx + radius, cy + vertical, cz + radius])
        except Exception as exc:
            errors.append(f"radius {radius}: {type(exc).__name__}: {exc}")
            continue
        found = discover_farms(region, CONFIG["minFarmCells"])
        complete = tuple(farm for farm in found if not farm.truncated)
        incomplete = tuple(farm for farm in found if farm.truncated)
        if incomplete:
            report("SCAN", f"Beyond the {radius}-block scan area: " +
                   "; ".join(f.name for f in incomplete))
            raise RuntimeError("Some farms extend beyond the scan area; move closer to the farm center")
        if not complete:
            raise RuntimeError("No planted nether wart farms found" +
                               ("; " + "; ".join(errors) if errors else ""))
        report("SCAN", f"Found {len(complete)} farms with {sum(len(f.cells) for f in complete)} cells: " +
               "; ".join(f"{f.name} ({len(f.cells)})" for f in complete), echo=True)
        return complete
    raise RuntimeError("No fully loaded scan area: " + "; ".join(errors))


def check_location():
    world = ms.world_info()
    if world is None:
        raise RuntimeError("Join a world or server first")
    return world_mode(world.address)


def configure_baritone(farm):
    command("stop")
    for option in ("allowBreak false", "replantCrops true", "replantNetherWart true",
                   "farmUsingSelection true", "harvestImmatureNetherWart false"):
        command(option)
    command("sel clear")
    command(f"sel pos1 {farm.min_x} {farm.y - 1} {farm.min_z}")
    command(f"sel pos2 {farm.max_x} {farm.y} {farm.max_z}")


def java_client():
    from java import JavaClass
    return JavaClass("net.minecraft.client.Minecraft").getInstance()


_baritone_query_unavailable = False


def baritone_farm_active():
    """Return None if this Minescript build cannot query the Baritone API."""
    global _baritone_query_unavailable
    if _baritone_query_unavailable:
        return None
    try:
        from java import JavaClass
        api = JavaClass("baritone.api.BaritoneAPI")
        return bool(api.getProvider().getPrimaryBaritone().getFarmProcess().isActive())
    except Exception as exc:
        _baritone_query_unavailable = True
        report("DIAGNOSTIC", f"Could not read Baritone state: {exc}")
        return None


def click_slot(slot, button=0, quick_move=False, before_inventory=None):
    from java import JavaClass
    mc = java_client()
    if ms.container_get_items() is None:
        raise RuntimeError("Menu closed before the click")
    if quick_move and before_inventory is None:
        before_inventory = inventory_wart()
    click = JavaClass("net.minecraft.world.inventory.ClickType")
    kind = click.QUICK_MOVE if quick_move else click.PICKUP
    mc.gameMode.handleInventoryMouseClick(mc.player.containerMenu.containerId, slot, button, kind, mc.player)
    if not quick_move:
        pause(0.4)
        return None
    # Keep a short gap between chest clicks, then wait for the inventory
    # update before sending another. A slow server still controls the pace.
    pause(0.10)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        after = inventory_wart()
        if after != before_inventory:
            return after
        pause(0.05)
    return inventory_wart()


def menu_size():
    mc = java_client()
    return len(mc.player.containerMenu.slots)


def close_menu():
    if ms.container_get_items() is not None:
        java_client().player.closeContainer()
        pause(0.25)


def wait_menu(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        halted()
        items = ms.container_get_items()
        if items is not None and predicate(items):
            return items
        time.sleep(0.15)
    raise TimeoutError(f"Timed out waiting for menu: {ms.screen_name()!r}")


def chest_distance(chest):
    x, y, z = ms.player_position()
    return math.dist((x, y + 1.62, z), (chest["x"] + 0.5, chest["y"] + 0.5, chest["z"] + 0.5))


def is_chest(block):
    return bool(block and block.split("[", 1)[0] in
                ("minecraft:chest", "minecraft:trapped_chest"))


def chest_property(block, name):
    marker = name + "="
    return block.split(marker, 1)[1].split(",", 1)[0].split("]", 1)[0] if marker in block else None


def chest_group_key(chest, block):
    """Treat both halves of a double chest as one storage container."""
    position = (chest["x"], chest["y"], chest["z"])
    chest_type = chest_property(block, "type")
    facing = chest_property(block, "facing")
    if chest_type not in ("left", "right") or facing is None:
        return position
    opposite = "right" if chest_type == "left" else "left"
    for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        other_position = (position[0] + dx, position[1], position[2] + dz)
        other = ms.getblock(*other_position)
        if (is_chest(other) and other.split("[", 1)[0] == block.split("[", 1)[0] and
                chest_property(other, "type") == opposite and
                chest_property(other, "facing") == facing):
            return min(position, other_position)
    return position


def plan_selected_chest(chest):
    """Record walkable cells beside a chest and the position used to click it."""
    x, y, z = chest["x"], chest["y"], chest["z"]
    player = ms.player_position()
    choices = []
    for nx, nz in ((x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1)):
        for feet_y in (y, y - 1):
            feet = ms.getblock(nx, feet_y, nz)
            head = ms.getblock(nx, feet_y + 1, nz)
            ground = ms.getblock(nx, feet_y - 1, nz)
            if ((region_air(feet) or (feet and feet.startswith(WART + "["))) and
                    region_air(head) and ground not in
                    (None, "minecraft:air", "minecraft:void_air", "minecraft:water", "minecraft:lava")):
                choices.append((nx, feet_y, nz))
    choices.sort(key=lambda p: math.dist((p[0] + 0.5, p[1], p[2] + 0.5), player))
    clicked_from = (math.floor(player[0]), round(player[1]), math.floor(player[2]))
    if clicked_from not in choices and chest_distance(chest) <= 4.4:
        choices.insert(0, clicked_from)
    choices = choices[:3]
    if not choices:
        raise RuntimeError(f"No reachable standing position beside chest {chest}")
    approaches = tuple({"x": ax, "y": ay, "z": az} for ax, ay, az in choices)
    return {"chest": chest, "approach": approaches[0], "approaches": approaches}


def save_chest_selection(session, plans):
    data = {"session": session, "chests": [plan["chest"] for plan in plans]}
    temporary = CHEST_SELECTION.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(CHEST_SELECTION)


def select_chests():
    """Collect right-clicked chests until the user runs \\farm_done."""
    session = uuid.uuid4().hex
    CHEST_SELECTION_DONE.unlink(missing_ok=True)
    plans = []
    selected_groups = set()
    save_chest_selection(session, plans)
    report("SELECT CHESTS", "Right-click each storage chest, close its menu, then type \\farm_done to start. Use \\stop to cancel.", echo=True)
    heartbeat = time.monotonic()
    with ms.EventQueue() as events:
        events.register_mouse_listener()
        while True:
            halted()
            if CHEST_SELECTION_DONE.exists():
                requested_session = CHEST_SELECTION_DONE.read_text(encoding="utf-8").strip()
                CHEST_SELECTION_DONE.unlink(missing_ok=True)
                if requested_session == session and plans:
                    report("SELECT CHESTS", f"Confirmed {len(plans)} storage chests; starting farm", echo=True)
                    return tuple(plans)
            if time.monotonic() - heartbeat >= 30:
                report("SELECT CHESTS", f"Waiting for \\farm_done; {len(plans)} chests selected")
                heartbeat = time.monotonic()
            try:
                event = events.get(timeout=0.2)
            except Empty:
                continue
            if event.type != ms.EventType.MOUSE or event.button != 1 or event.action != 1 or event.screen:
                continue
            try:
                hit = ms.player_get_targeted_block(5)
                if hit is None:
                    continue
                x, y, z = map(int, hit.position)
                chest = {"x": x, "y": y, "z": z}
                block = ms.getblock(x, y, z)
                if not is_chest(block):
                    continue
                group = chest_group_key(chest, block)
                if group in selected_groups:
                    report("SELECT CHESTS", f"Chest {chest} is already selected", echo=True)
                    continue
                plan = plan_selected_chest(chest)
            except Exception as exc:
                report("SELECT CHESTS", f"Could not read that chest click: {exc}", echo=True)
                continue
            plans.append(plan)
            selected_groups.add(group)
            save_chest_selection(session, plans)
            report("SELECT CHESTS", f"Added chest {len(plans)}: {chest}. Close its menu, or type \\farm_done when finished.", echo=True)


def find_storage(origin):
    """Find nearby ordinary chests and walkable positions beside them."""
    cx, cy, cz = origin
    vertical = CONFIG["chestVerticalRadius"]
    region = None
    errors = []
    for radius in dict.fromkeys((CONFIG["chestScanRadius"], 20, 16, 12, 8)):
        if radius > CONFIG["chestScanRadius"]:
            continue
        try:
            region = ms.get_block_region(
                [cx - radius, cy - vertical, cz - radius],
                [cx + radius, cy + vertical, cz + radius])
            break
        except Exception as exc:
            errors.append(f"radius {radius}: {exc}")
    if region is None:
        report("STORAGE", "Could not scan for chests: " + "; ".join(errors))
        return ()
    plans = []
    for y in range(region.min_pos[1] + 1, region.max_pos[1]):
        for z in range(region.min_pos[2] + 1, region.max_pos[2]):
            for x in range(region.min_pos[0] + 1, region.max_pos[0]):
                block = region.get_block(x, y, z)
                if not (block and (block.startswith("minecraft:chest") or
                                   block.startswith("minecraft:trapped_chest"))):
                    continue
                choices = []
                for nx, nz in ((x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1)):
                    for feet_y in (y, y - 1):
                        feet = region.get_block(nx, feet_y, nz)
                        if ((region_air(feet) or (feet and feet.startswith(WART + "["))) and
                                region_air(region.get_block(nx, feet_y + 1, nz)) and
                                region.get_block(nx, feet_y - 1, nz) not in
                                (None, "minecraft:air", "minecraft:void_air", "minecraft:water", "minecraft:lava")):
                            choices.append((nx, feet_y, nz))
                if not choices:
                    continue
                choices.sort(key=lambda p: math.dist(p, origin))
                approaches = tuple({"x": ax, "y": ay, "z": az} for ax, ay, az in choices)
                plans.append({"chest": {"x": x, "y": y, "z": z},
                              "approach": approaches[0], "approaches": approaches})
    plans.sort(key=lambda plan: math.dist(
        (plan["chest"]["x"], plan["chest"]["y"], plan["chest"]["z"]), origin))
    if plans:
        report("STORAGE", f"Found {len(plans)} nearby chests; first {plans[0]['chest']}", echo=True)
    else:
        report("STORAGE", "No nearby chest found; harvest stays in inventory", echo=True)
    return tuple(plans)


def approach_chest(plan):
    chest = plan["chest"]
    approaches = plan.get("approaches", (plan["approach"],))
    for p in approaches[:3]:
        if at_approach(ms.player_position(), p):
            return
        report("PATH", f"Moving next to chest {chest}, target {p}")
        command(f"goto {p['x']} {p['y']} {p['z']}")
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if at_approach(ms.player_position(), p):
                command("stop")
                return
            pause(0.4)
        command("stop")
    raise TimeoutError(f"Baritone could not reach a block next to chest {chest}; "
                       f"tried {approaches[:3]}")


def open_chest(chest):
    if chest_distance(chest) > 4.4:
        raise RuntimeError(f"Chest is too far away: {chest}")
    block = ms.getblock(chest["x"], chest["y"], chest["z"])
    if not block or "chest" not in block:
        raise RuntimeError(f"No chest at {chest}; found {block}")
    for height in (0.6, 0.85, 0.4):
        ms.player_look_at(chest["x"] + 0.5, chest["y"] + height, chest["z"] + 0.5)
        pause(0.15)
        hit = ms.player_get_targeted_block(4.5)
        if hit and tuple(hit.position) == (chest["x"], chest["y"], chest["z"]):
            ms.player_press_use(True)
            pause(0.12)
            ms.player_press_use(False)
            wait_menu(lambda _items: True)
            count = menu_size() - 36
            if count not in (27, 54):
                close_menu()
                raise RuntimeError(f"Opened a non-chest menu: {ms.screen_name()}, {count} slots")
            report("CHEST", f"Opened {chest}, {count} slots")
            return count
    raise RuntimeError(f"Could not aim at chest {chest}")


def store_in_chests(plans, *, required=False):
    """Deposit extra wart stacks while retaining one stack for replanting."""
    if not plans:
        if required:
            raise RuntimeError("Inventory is filling up. Place a chest near the starting point")
        report("STORAGE", f"No chest; {inventory_wart()} wart remains in inventory", echo=True)
        return 0
    moved = 0
    threshold = CONFIG["cashOutAtFreeSlots"]
    for plan in plans:
        if wart_stack_count() <= 1:
            break
        chest = plan["chest"]
        try:
            approach_chest(plan)
            size = open_chest(chest)
        except Exception as exc:
            report("STORAGE", f"Skipping chest {chest}: {exc}")
            continue
        try:
            while True:
                items = ms.container_get_items()
                if items is None:
                    break
                stacks = [i for i in items if i.slot >= size and i.item == WART]
                if len(stacks) <= 1:
                    break
                keep = max(stacks, key=lambda i: i.count)
                stack = next(i for i in stacks if i.slot != keep.slot)
                before = inventory_wart()
                after = click_slot(stack.slot, quick_move=True,
                                   before_inventory=before)
                delta = before - after
                if delta <= 0:
                    break
                moved += delta
        finally:
            close_menu()
    if moved:
        report("STORAGE", f"Stored {moved} wart; kept {inventory_wart()} for replanting", echo=True)
    if wart_stack_count() > 1:
        raise RuntimeError("Could not store all extra wart: chests are full or unreachable")
    if required and free_slots() <= threshold:
        raise RuntimeError("Chests are full or unreachable; harvest stopped before inventory overflow")
    return moved


def cash_out(resume, storage):
    command("stop")
    return store_in_chests(storage, required=resume)


def harvest(farm, mode, storage, progress):
    if free_slots() < CONFIG["minFreeSlotsBeforeStart"]:
        raise RuntimeError(f"Not enough free inventory slots ({free_slots()}); make room first")
    initial = survey(farm)
    configure_baritone(farm)
    command("farm")
    report("HARVEST", f"Floor {progress}: Baritone started on {len(farm.cells)} cells: {farm.name}", echo=True)
    start_time = last_change = time.monotonic()
    previous = None
    completed_polls = 0
    restarts = 0
    saw_work = False
    while time.monotonic() - start_time < CONFIG["harvestTimeoutSeconds"]:
        pause(min(2, CONFIG["harvestPollSeconds"]) if mode == "singleplayer" else CONFIG["harvestPollSeconds"])
        state = survey(farm)
        current = (state.mature, state.empty)
        wart = inventory_wart()
        active = baritone_farm_active()
        x, y, z = ms.player_position()
        report("HARVEST", f"Floor {progress}, Y={farm.y}: mature {state.mature}, young {state.young}, empty {state.empty}, wart {wart}, free slots {free_slots()}, Baritone={active}, position=({x:.1f},{y:.1f},{z:.1f})")
        if state.empty > 0 or state.mature != initial.mature or state.young != initial.young:
            saw_work = True
        if current != previous:
            last_change = time.monotonic()
            previous = current
            restarts = 0
        if harvest_complete(initial, state, saw_work):
            if completed_polls == 0:
                command("stop")
            completed_polls += 1
            if completed_polls >= 3:
                if state.mature:
                    report("HARVEST", f"Floor {progress}: {state.mature}/{state.total} mature left; "
                           "all cells replanted, moving to storage", echo=True)
                return state
            continue
        else:
            completed_polls = 0
        storage_threshold = CONFIG["cashOutAtFreeSlots"]
        if free_slots() <= storage_threshold:
            report("PAUSE", "Inventory is filling up; storing wart", echo=True)
            cash_out(resume=True, storage=storage)
            command("farm")
            last_change = time.monotonic()
        elif active is False and (state.mature > 0 or state.empty > 0):
            if restarts >= CONFIG["maxFarmRestarts"]:
                raise TimeoutError(f"Baritone stopped {restarts} times before harvest finished: {state}")
            restarts += 1
            if wart == 0 and state.empty > 0:
                # Give dropped wart time to reach the inventory before restarting.
                pause(2)
            report("RETRY", f"Baritone stopped before all cells were replanted; restart {restarts}/{CONFIG['maxFarmRestarts']}", echo=True)
            command("farm")
            last_change = time.monotonic()
        elif time.monotonic() - last_change >= CONFIG["stallSeconds"]:
            if restarts >= CONFIG["maxFarmRestarts"]:
                raise TimeoutError(f"Baritone stalled on the farm: {state}")
            restarts += 1
            report("RETRY", f"No changes for {CONFIG['stallSeconds']} seconds; restarting Baritone {restarts}/{CONFIG['maxFarmRestarts']}", echo=True)
            command("stop")
            command("farm")
            last_change = time.monotonic()
    raise TimeoutError("Harvest timed out; Baritone stopped")


def main():
    args = {arg.lower() for arg in sys.argv[1:]}
    if args - {"once"}:
        ms.echo("Usage: \\start [once]")
        return
    once = "once" in args
    lock = ROOT / "farm.running"
    if lock.exists():
        recent = False
        try:
            recent = time.time() - json.loads(STATUS.read_text(encoding="utf-8"))["time"] < 180
        except (OSError, ValueError, KeyError):
            pass
        if recent:
            ms.echo("[FARM] Already running. Use \\farm_status or \\stop.")
            return
        report("RECOVERY", "Removing a stale lock after the previous run ended", echo=True)
    STOP.unlink(missing_ok=True)
    CHEST_SELECTION.unlink(missing_ok=True)
    CHEST_SELECTION_DONE.unlink(missing_ok=True)
    lock.write_text(str(time.time()), encoding="utf-8")
    try:
        mode = check_location()
        storage = select_chests()
        CHEST_SELECTION.unlink(missing_ok=True)
        CHEST_SELECTION_DONE.unlink(missing_ok=True)
        px, py, pz = ms.player_position()
        origin = (math.floor(px), math.floor(py), math.floor(pz))
        farms = scan_farms(origin)
        # Clear leftover harvest from an earlier run before evaluating inventory space.
        store_in_chests(storage)
        next_scan = time.monotonic() + CONFIG["rescanSeconds"]
        report("READY", f"{len(farms)} farms; {'singleplayer' if mode == 'singleplayer' else 'server'}; "
               "harvest goes into chests", echo=True)
        while True:
            halted()
            if time.monotonic() >= next_scan:
                farms = scan_farms(origin)
                next_scan = time.monotonic() + CONFIG["rescanSeconds"]
            ready = []
            for farm in farms:
                state = survey(farm)
                needed = maturity_target(state.total, CONFIG["maturityThreshold"])
                report("WAIT", f"{farm.name}: mature {state.mature}/{state.total} "
                       f"({state.ratio:.0%}), need {needed}")
                if needs_harvest(state, CONFIG["maturityThreshold"]):
                    ready.append(farm)
            harvested_any = False
            for index, farm in enumerate(ready, start=1):
                state = survey(farm)
                needed = maturity_target(state.total, CONFIG["maturityThreshold"])
                if not needs_harvest(state, CONFIG["maturityThreshold"]):
                    continue
                progress = f"{index}/{len(ready)}"
                report("CYCLE", f"Floor {progress}; Y={farm.y}; starting {farm.name}: mature {state.mature}/{state.total}", echo=True)
                harvest(farm, mode, storage, progress)
                cash_out(resume=False, storage=storage)
                report("CYCLE", f"{farm.name}: harvest and replanting complete; wart stored", echo=True)
                harvested_any = True
            if once and harvested_any:
                break
            pause(CONFIG["checkIntervalSeconds"])
    except InterruptedError as exc:
        report("STOP", str(exc), echo=True)
    except Exception as exc:
        report("ERROR", f"{type(exc).__name__}: {exc}", echo=True)
        with LOG.open("a", encoding="utf-8") as out:
            traceback.print_exc(file=out)
    finally:
        try:
            # These commands intentionally ignore the stop flag.
            ms.chat("#stop")
            ms.chat("#harvestImmatureNetherWart false")
        finally:
            lock.unlink(missing_ok=True)
            STOP.unlink(missing_ok=True)
            CHEST_SELECTION.unlink(missing_ok=True)
            CHEST_SELECTION_DONE.unlink(missing_ok=True)
