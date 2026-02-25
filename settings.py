import json
from pathlib import Path

APP_DIR = Path.home() / ".config" / "py_file_explorer"
SETTINGS_PATH = APP_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "start_path": str(Path.home()),
    "theme": "dark",
    "show_hidden": False,
    "favorites": [str(Path.home()), str(Path.home() / "Documents")],
    "recent_tabs": [str(Path.home())],
}


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return DEFAULT_SETTINGS.copy()

    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()

    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)

    if not isinstance(merged.get("favorites"), list):
        merged["favorites"] = DEFAULT_SETTINGS["favorites"]
    if not isinstance(merged.get("recent_tabs"), list):
        merged["recent_tabs"] = DEFAULT_SETTINGS["recent_tabs"]
    if not isinstance(merged.get("show_hidden"), bool):
        merged["show_hidden"] = DEFAULT_SETTINGS["show_hidden"]

    return merged


def save_settings(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
