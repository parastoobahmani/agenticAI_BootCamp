import json
from pathlib import Path

from missing_info.cli import main

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "stuck_loading_on_server.json"


def test_analyze_writes_json_report(tmp_path):
    output = tmp_path / "report.json"
    assert main(["analyze", str(EXAMPLE), "--output", str(output)]) == 0

    report = json.loads(output.read_text())
    assert report["decision"]["type"] == "request_information"
    assert report["schema_version"] == "1.0"


def test_analyze_renders_markdown(tmp_path):
    output = tmp_path / "report.md"
    assert main(["analyze", str(EXAMPLE), "--format", "markdown", "--output", str(output)]) == 0

    text = output.read_text()
    assert "**Decision:** Request information" in text
    assert "## Not asked again" in text


def test_invalid_input_returns_error_code(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"case": {}}')
    assert main(["analyze", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


def test_schema_export(tmp_path):
    assert main(["schema", "--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == {
        "analysis_input.schema.json",
        "next_step_report.schema.json",
    }


def test_llm_without_api_key_fails_cleanly(monkeypatch, capsys):
    monkeypatch.delenv("METIS_API_KEY", raising=False)
    assert main(["analyze", str(EXAMPLE), "--llm"]) == 2
    assert "error:" in capsys.readouterr().err


PART1 = EXAMPLE.parent / "part1"


def test_from_part1_with_case_file(tmp_path):
    output = tmp_path / "report.json"
    argv = ["from-part1", str(PART1 / "evidence_synthesis_result.json"), "--case", str(PART1 / "session_state_case.json")]
    assert main([*argv, "--output", str(output)]) == 0
    assert json.loads(output.read_text())["case_id"] == "part1-demo-session-state"


def test_from_part1_issue_requires_data_dir(capsys):
    assert main(["from-part1", str(PART1 / "evidence_synthesis_result.json"), "--issue", "1"]) == 2
    assert "--data-dir" in capsys.readouterr().err
