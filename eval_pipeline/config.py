"""Global paths and constants for the evaluation pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EVAL = ROOT / "data" / "eval"

ISSUES_PATH = RAW / "issues.jsonl"
COMMENTS_PATH = RAW / "comments.jsonl"
DOCS_PATH = RAW / "documentation.jsonl"
RELEASES_PATH = RAW / "release_notes.jsonl"

CASES_DIR = EVAL / "cases"
ANNOT_DIR = EVAL / "annotations"
MULTI_DIR = EVAL / "multi_turn"
RUNS_DIR = EVAL / "runs"
REPORTS_DIR = EVAL / "reports"

SPLIT_PATH = EVAL / "case_split.json"

# Evaluation design
N_DEV = 15
N_TEST = 15
N_TOTAL = N_DEV + N_TEST
N_MULTI_TURN = 10          # at least 10; half will land in test via random split
RECALL_KS = [5, 10]
SPLIT_SEED = 42

# Minimum text length to consider an issue usable as a case
MIN_BODY_LEN = 80