"""Human-readable Markdown view of a NextStepReport (for maintainers and demos)."""

from __future__ import annotations

from missing_info.schemas import FactStatus, NextStepReport

_DECISION_TITLES = {
    "propose_answer": "Propose an answer",
    "request_information": "Request information",
    "escalate": "Escalate / refer",
}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(report: NextStepReport) -> str:
    lines = [f"# Case {report.case_id}: next step", ""]

    decision = report.decision
    title = _DECISION_TITLES[decision.type.value]
    target = f" ({decision.hypothesis_id})" if decision.hypothesis_id else ""
    lines += [f"**Decision:** {title}{target}", "", decision.rationale, ""]

    lines += ["## Next steps", ""]
    if report.next_steps:
        for index, step in enumerate(report.next_steps, 1):
            lines.append(f"{index}. **[{step.kind.value}]** {step.text}")
            details = [f"facet `{step.facet}`", f"gain {step.expected_information_gain:.3f} bits", f"cost {step.cost}"]
            lines.append(f"   - {', '.join(details)}")
            if step.rationale:
                lines.append(f"   - why: {step.rationale}")
    else:
        lines.append("_None._")
    lines.append("")

    lines += ["## Known facts", ""]
    if report.known_facts:
        lines += ["| facet | value | source | quote |", "|---|---|---|---|"]
        for fact in report.known_facts:
            value = fact.value if fact.status is FactStatus.OBSERVED else "_done, result unknown_"
            lines.append(f"| {fact.facet} | {_cell(value or '')} | {fact.origin.location} | {_cell(fact.origin.quote)} |")
    else:
        lines.append("_Nothing could be extracted from the case._")
    lines.append("")

    lines += ["## Hypotheses", "", "| id | prior | posterior | evidence | conflicts | statement |", "|---|---|---|---|---|---|"]
    for item in report.hypotheses:
        lines.append(
            f"| {item.hypothesis_id} | {item.prior:.2f} | {item.posterior:.2f} | {item.evidence_strength.value} "
            f"| {_cell(', '.join(item.conflicting_facts)) or '-'} | {_cell(item.statement)} |"
        )
    lines.append("")

    if report.missing_information:
        lines += ["## Still unknown", ""]
        for item in report.missing_information:
            lines.append(
                f"- `{item.facet}`: {item.description} "
                f"(relevant to {', '.join(item.relevant_hypotheses)}; gain {item.expected_information_gain:.3f})"
            )
        lines.append("")

    if report.skipped_probes:
        lines += ["## Not asked again", ""]
        lines += [f"- `{item.facet}`: {item.reason}" for item in report.skipped_probes]
        lines.append("")

    if report.limitations:
        lines += ["## Limitations", ""]
        lines += [f"- {note}" for note in report.limitations]
        lines.append("")

    return "\n".join(lines)
