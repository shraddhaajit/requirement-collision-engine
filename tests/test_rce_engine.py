"""Unit and integration tests for RCE Phase 6: Engine integration layer.

Covers:
- Successful end-to-end analysis of CEWS.
- Successful analysis of synthetic, unrelated Python projects.
- Relative and absolute project-root and requirement paths.
- Engine with change-impact analysis enabled.
- Unknown impact targets and warning handling.
- Missing project roots and missing requirement files.
- Syntax error resilience and partial-status tracking.
- Output serialization and text report formatting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rce.engine import (
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PARTIAL,
    EngineResult,
    format_engine_result,
    run_engine,
)


def test_engine_cews_end_to_end():
    """Verify that the engine runs successfully on the authoritative CEWS codebase."""
    result = run_engine(project_root=".")

    assert isinstance(result, EngineResult)
    assert result.success is True
    assert result.status == STATUS_COMPLETE
    assert result.requirements_count == 10
    assert result.modules_count >= 4
    assert result.functions_count >= 10
    assert result.graph_nodes_count >= 30
    assert result.graph_edges_count >= 30
    assert result.collisions_count >= 3

    # Check for known ground-truth CEWS collision
    col_ids = {f.collision_id for f in result.findings}
    assert "COL-RULE_B-REQ-03-REQ-07-AMOUNT" in col_ids


def test_engine_synthetic_project(tmp_path: Path):
    """Verify engine analysis on an isolated synthetic Python project."""
    spec_md = tmp_path / "specs.md"
    spec_md.write_text(
        "# Specification\n\n"
        "### REQ-01 — Task Queueing\n"
        "Enqueue background work items.\n\n"
        "### REQ-02 — Task Execution\n"
        "Process items from queue.\n",
        encoding="utf-8",
    )

    src_dir = tmp_path / "worker"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    (src_dir / "queue.py").write_text(
        '"""Task queue.\n\nTRACE: REQ-01\n"""\n\n'
        'def enqueue_task(item: str) -> bool:\n'
        '    """Enqueue work.\n\nTRACE: REQ-01\n"""\n'
        '    if len(item) > 0:\n'
        '        return True\n'
        '    return False\n',
        encoding="utf-8",
    )

    (src_dir / "runner.py").write_text(
        '"""Worker runner.\n\nTRACE: REQ-02\n"""\n'
        'from worker.queue import enqueue_task\n\n'
        'def execute_all() -> None:\n'
        '    """Execute.\n\nTRACE: REQ-02\n"""\n'
        '    enqueue_task("job1")\n',
        encoding="utf-8",
    )

    result = run_engine(
        project_root=tmp_path,
        requirements_path="specs.md",
    )

    assert result.success is True
    assert result.status == STATUS_COMPLETE
    assert result.requirements_count == 2
    assert result.modules_count >= 2
    assert result.functions_count >= 2
    assert result.graph_nodes_count > 0


def test_engine_with_impact_analysis():
    """Verify that optional change-impact analysis integrates into the engine result."""
    result = run_engine(
        project_root=".",
        impact_target="REQ-03",
        max_depth=3,
    )

    assert result.success is True
    assert result.impact_report is not None
    assert result.impact_report.target_id == "REQ-03"
    assert result.impact_report.total_impacted_count > 0
    assert any("check_manager_approval" in fn for fn in result.impact_report.affected_functions)


def test_engine_unknown_impact_target():
    """Verify that unknown impact targets do not crash the engine and emit warnings."""
    result = run_engine(
        project_root=".",
        impact_target="UNKNOWN_REQ_9999",
    )

    assert result.success is True
    assert result.impact_report is not None
    assert result.impact_report.total_impacted_count == 0
    assert any("UNKNOWN_REQ_9999" in w for w in result.warnings)


def test_engine_invalid_project_root(tmp_path: Path):
    """Verify handling of missing or non-directory project root."""
    missing_dir = tmp_path / "does_not_exist"
    result = run_engine(project_root=missing_dir)

    assert result.success is False
    assert result.status == STATUS_FAILED
    assert len(result.errors) > 0
    assert any("does not exist" in e for e in result.errors)


def test_engine_missing_requirements_file(tmp_path: Path):
    """Verify handling of explicitly requested but non-existent requirements file."""
    result = run_engine(
        project_root=tmp_path,
        requirements_path="missing_requirements.md",
    )

    assert any("missing_requirements.md" in e for e in result.errors)
    assert result.status in (STATUS_PARTIAL, STATUS_FAILED)


def test_engine_syntax_error_partial_analysis(tmp_path: Path):
    """Verify that syntax errors in individual files yield partial status without halting analysis."""
    # 1. Valid requirement
    (tmp_path / "requirements.md").write_text(
        "# Specification\n\n"
        "### REQ-01 — Valid Operation\n"
        "Must perform operation safely.\n",
        encoding="utf-8",
    )

    # 2. Valid file
    (tmp_path / "good.py").write_text(
        '"""Good module.\n\nTRACE: REQ-01\n"""\n'
        'def good_func() -> int:\n'
        '    """Valid function.\n\nTRACE: REQ-01\n"""\n'
        '    return 42\n',
        encoding="utf-8",
    )

    # 3. Syntax error file
    (tmp_path / "broken.py").write_text(
        'def unclosed_syntax(\n',
        encoding="utf-8",
    )

    result = run_engine(project_root=tmp_path)

    assert result.success is True
    assert result.status == STATUS_PARTIAL
    assert result.requirements_count == 1
    # good.py was analyzed
    assert result.modules_count >= 1
    assert any("broken.py" in w for w in result.warnings)
    assert result.metadata.get("syntax_error_count", 0) >= 1


def test_engine_relative_and_absolute_paths(tmp_path: Path):
    """Verify that relative and absolute paths are resolved consistently."""
    req_file = tmp_path / "requirements.md"
    req_file.write_text(
        "# Spec\n\n### REQ-01 — Simple\nDesc.\n",
        encoding="utf-8",
    )

    # Absolute path
    res_abs = run_engine(project_root=tmp_path.resolve())
    assert res_abs.success is True
    assert res_abs.requirements_count == 1

    # Relative path (relative to cwd if set)
    res_cews_rel = run_engine(project_root=".")
    assert res_cews_rel.success is True
    assert res_cews_rel.requirements_count == 10


def test_engine_serialization():
    """Verify dictionary and JSON serialization of EngineResult."""
    result = run_engine(project_root=".")

    res_dict = result.to_dict()
    assert isinstance(res_dict, dict)
    assert res_dict["status"] == STATUS_COMPLETE
    assert "statistics" in res_dict
    assert "findings" in res_dict
    assert res_dict["statistics"]["requirements_count"] == 10

    res_json = result.to_json()
    parsed = json.loads(res_json)
    assert parsed["status"] == STATUS_COMPLETE
    assert len(parsed["findings"]) == len(result.findings)


def test_engine_format_text_output():
    """Verify that format_engine_result produces a detailed and structured text report."""
    result = run_engine(project_root=".", impact_target="REQ-03")
    text = format_engine_result(result)

    assert "REQUIREMENT COLLISION ENGINE (RCE)" in text
    assert "Project Statistics:" in text
    assert "Requirements   : 10" in text
    assert "Collision Findings" in text
    assert "COL-RULE_B-REQ-03-REQ-07-AMOUNT" in text
    assert "CHANGE-IMPACT ANALYSIS REPORT" in text
