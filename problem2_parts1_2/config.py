from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
VAR_DIR = PACKAGE_DIR / "runtime"
ASSETS_DIR = PACKAGE_DIR / "assets"

DEFAULT_DB_PATH = Path(os.environ.get("SUPPORT_AGENT_DB", VAR_DIR / "support_agent.sqlite3"))
SEED_CASES_PATH = ASSETS_DIR / "seed_cases.json"
EVIDENCE_PATH = ASSETS_DIR / "evidence_store.json"

DEFAULT_TOP_K = 5
MAX_TOP_K = 20

ALLOWED_ACTIONS = ("comment", "labels", "state")
ALLOWED_TICKET_STATES = ("open", "closed")
