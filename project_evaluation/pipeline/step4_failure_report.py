"""
Step 4: Human-readable failure analysis summary for the report.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import REPORTS_DIR


def main():
    for split in ("dev", "test"):
        metrics_path = REPORTS_DIR / f"metrics_{split}.json"
        fail_path = REPORTS_DIR / f"failures_{split}.json"
        if not metrics_path.exists():
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        failures = json.loads(fail_path.read_text(encoding="utf-8")) if fail_path.exists() else []

        lines = [
            f"# Failure & Metrics Report — {split.upper()}",
            "",
            "## Decision quality",
            json.dumps(metrics.get("decision_quality"), indent=2),
            "",
            "## Evidence quality",
            json.dumps(metrics.get("evidence_quality"), indent=2),
            "",
            "## Operational success",
            json.dumps(metrics.get("operational_success"), indent=2),
            "",
            "## Cost & time",
            json.dumps(metrics.get("cost_time"), indent=2),
            "",
            f"## Failures ({len(failures)})",
        ]
        for f in failures[:50]:
            lines.append(
                f"- **{f['case_id']}** turn {f.get('turn')}: "
                f"got `{f.get('action')}`, expected `{f.get('expected')}`"
            )
            lines.append(f"  - excerpt: {f.get('response_excerpt', '')[:200]}")
            lines.append(f"  - cause tag: {f.get('probable_cause')}")

        lines += [
            "",
            "## Notes for the written report",
            "- TEST numbers must come from a single frozen run after all tuning on DEV.",
            "- Fill relevant_chunk_ids / relevant_source_ids in annotations for real Recall@k.",
            "- If using LLM-as-a-Judge, attach the judge prompt and human agreement sample here.",
            "- Record source snapshot timestamps/versions from problem1_part1/data/*_meta.json.",
        ]

        out = REPORTS_DIR / f"report_{split}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
