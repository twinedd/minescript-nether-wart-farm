r"""Read-only Minescript check: \farm_probe."""

import math

from farm_controller import CONFIG, check_location, find_storage, java_client, maturity_target, scan_farms, survey
import minescript as ms

try:
    check_location()
    x, y, z = ms.player_position()
    origin = (math.floor(x), math.floor(y), math.floor(z))
    farms = scan_farms(origin)
    ms.echo(f"[FARM PROBE] Found {len(farms)} farms on levels Y=" +
            ", ".join(str(farm.y) for farm in farms) +
            ". Baritone selects one floor at a time during harvest.")
    client = java_client()
    if not client or not client.player:
        raise RuntimeError("Minescript Java bridge cannot access the player")
    for farm in farms:
        state = survey(farm)
        target = maturity_target(state.total, CONFIG["maturityThreshold"])
        ms.echo(f"[FARM PROBE] {farm.name}: {state.total} cells; mature {state.mature}, "
                f"young {state.young}, empty {state.empty}; threshold {target}.")
    storage = find_storage(origin)
    ms.echo(f"[FARM PROBE] Nearby chest candidates: {len(storage)}. "
            "Select storage chests by right-clicking them after \\start.")
    ms.echo("[FARM PROBE] Minescript, block scanning, and the Java bridge are working.")
except Exception as exc:
    ms.echo(f"[FARM PROBE] Error: {type(exc).__name__}: {exc}")
    raise
