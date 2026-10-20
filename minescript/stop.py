r"""Minescript command: \stop."""

from pathlib import Path
import minescript

folder = Path(__file__).resolve().parent
(folder / "farm.stop").write_text("stop", encoding="utf-8")
minescript.chat("#stop")
minescript.echo("[FARM] Stop requested.")
