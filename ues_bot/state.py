"""JSON state storage for seen events."""

from __future__ import annotations

import os
import json
from typing import Dict


def load_state(state_file: str) -> Dict:
    if not os.path.exists(state_file):
        return {"events": {}}
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state_file: str, state: Dict) -> None:
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
