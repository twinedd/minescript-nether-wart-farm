r"""Minescript command: \farm_done. Finish selecting storage chests."""

import json
from pathlib import Path
import time

import minescript

folder = Path(__file__).resolve().parent
selection = folder / "farm.chest_selection.json"
done = folder / "farm.chest_selection.done"
running = folder / "farm.running"
status = folder / "farm.status.json"

try:
    if not running.exists() or not selection.exists():
        raise RuntimeError("Start the farm with \\start and select chests first")
    data = json.loads(selection.read_text(encoding="utf-8"))
    current = json.loads(status.read_text(encoding="utf-8"))
    if current.get("phase") != "SELECT CHESTS" or time.time() - current.get("time", 0) > 45:
        raise RuntimeError("Chest selection is not active; use \\start again")
    if not data.get("chests"):
        raise RuntimeError("Right-click at least one chest before \\farm_done")
    done.write_text(data["session"], encoding="utf-8")
    minescript.echo(f"[FARM] Confirmed {len(data['chests'])} chests. Starting the farm.")
except (OSError, ValueError, KeyError, RuntimeError) as exc:
    minescript.echo(f"[FARM] {exc}")
