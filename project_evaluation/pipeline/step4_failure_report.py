"""
Step 4: Human-readable comparison and failure analysis for the written report.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional

from config import ACTIONS, REPORTS_DIR


def fmt(value: Optional[float], digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def labelled(entry: Optional[Dict[str, Any]], key: str = "rate") -> str:
    if not entry or entry.get(key) is None:
        return f"n/a (n={entry.get('n', entry.get('n_labeled', 0)) if entry else 0})"
    return f"{entry[key]:.2f} (n={entry.get('n', entry.get('n_labeled'))})"


def comparison_table(systems: Dict[str, Dict[str, Any]]) -> List[str]:
    names = list(systems)
    rows = [
        ("Cases / errors", lambda s: f"{s['n_cases']} / {s['n_errors']}"),
        ("Decision accuracy (overall)", lambda s: fmt(s["decision_quality"]["overall_accuracy"])),
    ]
    buckets = sorted({bucket for s in systems.values() for bucket in s["decision_quality"]["by_bucket"]})
    rows += [
        (f"Decision accuracy: {bucket}", lambda s, b=bucket: labelled(s["decision_quality"]["by_bucket"].get(b)))
        for bucket in buckets
    ]
    rows += [
        ("Recall@5", lambda s: labelled(s["evidence_quality"]["recall@5"], "mean")),
        ("Recall@10", lambda s: labelled(s["evidence_quality"]["recall@10"], "mean")),
        ("Re-asked known information", lambda s: labelled((s["next_step_quality"] or {}).get("re_asked_known_information"))),
        ("First step from information gain", lambda s: labelled((s["next_step_quality"] or {}).get("first_step_from_information_gain"))),
        ("First step hits labelled missing info", lambda s: labelled((s["next_step_quality"] or {}).get("first_step_hits_labelled_missing_information"))),
        ("All operational checks on stored state", lambda s: labelled((s["operational_success"] or {}).get("all_checks"))),
        ("Mean / max latency (s)", lambda s: f"{fmt(s['cost_time']['mean_latency_sec'])} / {fmt(s['cost_time']['max_latency_sec'])}"),
        ("API requests / tokens in+out / cost USD", lambda s: (
            f"{s['cost_time']['api_requests']} / {s['cost_time']['input_tokens']}+{s['cost_time']['output_tokens']}"
            f" / {s['cost_time']['estimated_cost_usd']}"
        )),
    ]
    lines = ["| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [f"| {label} | " + " | ".join(render(systems[name]) for name in names) + " |" for label, render in rows]
    return lines


def action_tables(systems: Dict[str, Dict[str, Any]]) -> List[str]:
    lines = []
    for name, metrics in systems.items():
        lines += [f"**{name}**", "", "| Bucket | " + " | ".join(ACTIONS) + " | error |", "|---|" + "---|" * (len(ACTIONS) + 1)]
        for bucket, counts in metrics["decision_quality"]["actions_by_bucket"].items():
            lines.append(f"| {bucket} | " + " | ".join(str(counts[action]) for action in (*ACTIONS, "error")) + " |")
        lines.append("")
    return lines


def main():
    for split in ("dev", "test"):
        metrics_path = REPORTS_DIR / f"metrics_{split}.json"
        fail_path = REPORTS_DIR / f"failures_{split}.json"
        if not metrics_path.exists():
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        failures = json.loads(fail_path.read_text(encoding="utf-8")) if fail_path.exists() else []
        scenarios = metrics["problem2_scenarios"]

        lines = [
            f"# Evaluation report — {split.upper()}",
            "",
            "## Systems compared on the same cases",
            "",
            *comparison_table(metrics["systems"]),
            "",
            "## Actions taken per bucket",
            "",
            "Shown next to accuracy so that asking or escalating on every case cannot pass as success.",
            "",
            *action_tables(metrics["systems"]),
            "## Multi-turn and operational scenarios (Problem 2 Part 3)",
            "",
            f"{scenarios['passed']}/{scenarios['total']} passed — {scenarios['source']}.",
            "",
            *[
                f"- {row['scenario_id']} {row['name']}: {'passed' if row['passed'] else 'FAILED ' + row['error']}"
                for row in scenarios["results"]
            ],
            "",
            "## Corpus policy",
            "",
            *[f"- {key}: {value}" for key, value in (metrics.get("corpus_policy") or {}).items()],
            "",
            f"## Failures ({len(failures)})",
            "",
        ]
        causes = Counter((failure["system"], failure["probable_cause"]) for failure in failures)
        lines += [f"- {system}: {cause} × {count}" for (system, cause), count in sorted(causes.items())]
        lines.append("")
        for failure in failures[:50]:
            lines.append(
                f"- **{failure['system']} / {failure['case_id']}** ({failure['bucket']}): "
                f"got `{failure['action']}`, expected `{failure['expected']}` — {failure['probable_cause']}"
            )
            if failure.get("error"):
                lines.append(f"  - error: {failure['error']}")

        lines += [
            "",
            "## Notes for the written report",
            "- TEST numbers must come from a single frozen run after all tuning on DEV (step2 needs --allow-test).",
            "- Decision accuracy is only as good as the annotations: fill bucket, acceptable actions,"
            " missing_information and relevant ids by hand.",
            "- If using LLM-as-a-Judge, attach the judge prompt and a human agreement sample here.",
            "- Record source snapshot timestamps/versions from problem1_part1/data/*_meta.json.",
        ]

        out = REPORTS_DIR / f"report_{split}.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
