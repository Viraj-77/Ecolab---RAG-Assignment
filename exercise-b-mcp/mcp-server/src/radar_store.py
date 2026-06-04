import json
import shutil
import sys
from pathlib import Path

from .types import Radar

# repo root = two levels up from src/
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = _REPO_ROOT / "ecolab-radar-config.json"
_WORKING = _REPO_ROOT / "mcp-server" / "radar_working.json"


def load_radar() -> Radar:
    if not _WORKING.exists():
        if not _SOURCE.exists():
            raise FileNotFoundError(f"Source radar config not found: {_SOURCE}")
        shutil.copyfile(_SOURCE, _WORKING)
        print("Created radar_working.json from ecolab-radar-config.json", file=sys.stderr)
    with _WORKING.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return Radar.model_validate(data)


def save_radar(radar: Radar) -> None:
    with _WORKING.open("w", encoding="utf-8") as f:
        json.dump(radar.model_dump(), f, indent=2)
