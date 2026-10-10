"""Global paths and constants for the evaluation pipeline."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The steps run as plain scripts; make the project packages importable for them.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RAW = PROJECT_ROOT / "problem1_part1" / "data"
EVAL = PROJECT_ROOT / "project_evaluation" / "data"

ISSUES_PATH = RAW / "issues.jsonl"
COMMENTS_PATH = RAW / "comments.jsonl"
DOCS_PATH = RAW / "documentation.jsonl"
RELEASES_PATH = RAW / "release_notes.jsonl"
DOCS_META_PATH = RAW / "docs_meta.json"

CASES_DIR = EVAL / "cases"
ANNOT_DIR = EVAL / "annotations"
RUNS_DIR = EVAL / "runs"
REPORTS_DIR = EVAL / "reports"

SPLIT_PATH = EVAL / "case_split.json"

# Evaluation design
N_DEV = 15
N_TEST = 15
N_TOTAL = N_DEV + N_TEST
RECALL_KS = [5, 10]
SPLIT_SEED = 42

# Multi-turn and operational behaviour (approval, retries, restarts, case isolation) is
# evaluated by the ten Problem 2 Part 3 scenarios (five dev, five test), which run
# against the real stored state. Their results are folded into the metrics report.

# Systems compared on the same cases: the original keyword stub is the baseline, the
# integrated project pipeline (Part 1 -> Part 2 -> Part 3 -> Problem 2 import) is final.
SYSTEMS = ("baseline", "integrated")
ACTIONS = ("answer", "ask_clarification", "escalate")

# Minimum text length to consider an issue usable as a case
MIN_BODY_LEN = 80
