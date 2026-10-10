import sys
from pathlib import Path

# The pipeline steps are plain scripts that import each other by module name.
PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))
