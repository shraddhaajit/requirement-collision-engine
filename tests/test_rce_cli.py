"""Command-line interface tests for RCE Phase 6.

Covers:
- Successful text and JSON CLI execution on CEWS.
- Machine-readable JSON output structure and validity.
- Output-file flag handling including parent directory creation.
- Synthetic project analysis via CLI.
- Change-impact analysis invocation via --impact and --max-depth.
- Error handling for invalid --max-depth (negative / zero).
- Error handling for invalid project roots.
- Invocation via `python -m rce` subprocess execution.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rce.cli import main


def test_cli_cews_text_output(capsys):
    """Test standard text output from CLI on CEWS repository."""
    exit_code = main(["--project-root", ".", "--format", "text"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "REQUIREMENT COLLISION ENGINE (RCE)" in captured.out
    assert "Project Statistics:" in captured.out
    assert "Requirements   : 10" in captured.out
    assert "COL-RULE_B-REQ-03-REQ-07-AMOUNT" in captured.out


def test_cli_cews_json_output(capsys):
    """Test machine-readable JSON output from CLI on CEWS repository."""
    exit_code = main(["--project-root", ".", "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    # stdout must parse cleanly as JSON with no extra diagnostic prose
    data = json.loads(captured.out)
    assert data["success"] is True
    assert data["status"] == "complete"
    assert data["statistics"]["requirements_count"] == 10
    assert len(data["findings"]) >= 3


def test_cli_with_impact_flag(capsys):
    """Test running CLI with change-impact analysis requested."""
    exit_code = main([
        "--project-root", ".",
        "--impact", "REQ-03",
        "--max-depth", "3",
        "--format", "json",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["impact_report"] is not None
    assert data["impact_report"]["target_id"] == "REQ-03"
    assert data["impact_report"]["total_impacted_count"] > 0


def test_cli_output_to_file(tmp_path: Path):
    """Test writing CLI results to a file, including automatic parent directory creation."""
    out_file = tmp_path / "nested" / "reports" / "rce_result.json"

    exit_code = main([
        "--project-root", ".",
        "--format", "json",
        "--output", str(out_file),
    ])

    assert exit_code == 0
    assert out_file.is_file()

    content = out_file.read_text(encoding="utf-8")
    data = json.loads(content)
    assert data["success"] is True
    assert data["statistics"]["requirements_count"] == 10


def test_cli_invalid_max_depth(capsys):
    """Test CLI rejection of zero or negative max depth."""
    exit_code_zero = main(["--max-depth", "0"])
    captured_zero = capsys.readouterr()
    assert exit_code_zero == 2
    assert "must be a positive integer" in captured_zero.err

    exit_code_neg = main(["--max-depth", "-3"])
    captured_neg = capsys.readouterr()
    assert exit_code_neg == 2
    assert "must be a positive integer" in captured_neg.err


def test_cli_missing_project_root(capsys, tmp_path: Path):
    """Test CLI behavior when project root does not exist."""
    missing_dir = tmp_path / "non_existent_project"
    exit_code = main(["--project-root", str(missing_dir), "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code != 0
    data = json.loads(captured.out)
    assert data["success"] is False
    assert data["status"] == "failed"
    assert len(data["errors"]) > 0


def test_cli_synthetic_project(tmp_path: Path, capsys):
    """Test CLI on a synthetic custom project with custom requirements and code."""
    req_file = tmp_path / "custom_req.md"
    req_file.write_text(
        "# Custom Specification\n\n"
        "### REQ-01 — Custom Core\n"
        "Core requirement logic.\n",
        encoding="utf-8",
    )

    (tmp_path / "app.py").write_text(
        '"""App logic.\n\nTRACE: REQ-01\n"""\n'
        'def run() -> None:\n'
        '    """Run.\n\nTRACE: REQ-01\n"""\n'
        '    pass\n',
        encoding="utf-8",
    )

    exit_code = main([
        "--project-root", str(tmp_path),
        "--requirements", str(req_file),
        "--format", "text",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Requirements   : 1" in captured.out
    assert "Analysis Status    : COMPLETE" in captured.out


def test_cli_module_execution_subprocess():
    """Verify execution of python -m rce in a separate process."""
    cmd = [sys.executable, "-m", "rce", "--version"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=".")

    assert proc.returncode == 0
    assert "Requirement Collision Engine (RCE) v" in proc.stdout
