"""Minescript command: \farm_status."""

from pathlib import Path
import json
import minescript

path = Path(__file__).resolve().parent / "farm.status.json"
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        minescript.echo("[FARM]", data.get("phase"), data.get("detail", ""))
    except (OSError, ValueError):
        minescript.echo("[FARM] Status file is damaged; see farm.log for details.")
else:
    minescript.echo("[FARM] Not started yet.")
