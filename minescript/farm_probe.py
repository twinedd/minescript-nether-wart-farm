r"""Read-only Minescript check: \farm_probe."""

import math

from farm_controller import CONFIG, check_location, find_storage, java_client, maturity_target, scan_farms, survey
import minescript as ms

try:
    check_location()
    x, y, z = ms.player_position()
    origin = (math.floor(x), math.floor(y), math.floor(z))
    farms = scan_farms(origin)
    ms.echo(f"[FARM PROBE] Найдено {len(farms)} грядок на этажах Y=" +
            ", ".join(str(farm.y) for farm in farms) +
            ". Во время сбора Baritone выделяет один этаж за раз.")
    client = java_client()
    if not client or not client.player:
        raise RuntimeError("Java-мост Minescript не видит игрока")
    for farm in farms:
        state = survey(farm)
        target = maturity_target(state.total, CONFIG["maturityThreshold"])
        ms.echo(f"[FARM PROBE] {farm.name}: {state.total} клеток; зрелых {state.mature}, "
                f"молодых {state.young}, пустых {state.empty}; порог {target}.")
    storage = find_storage(origin)
    ms.echo(f"[FARM PROBE] Доступных сундуков для урожая: {len(storage)}.")
    ms.echo("[FARM PROBE] Minescript, состояние блоков и Java-мост работают.")
except Exception as exc:
    ms.echo(f"[FARM PROBE] Ошибка: {type(exc).__name__}: {exc}")
    raise
