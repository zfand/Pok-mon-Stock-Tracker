import json
import pathlib
import time

STATE_FILE = pathlib.Path(__file__).resolve().parent.parent / "state" / "seen.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"listings": {}, "blocks": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def now() -> int:
    return int(time.time())
