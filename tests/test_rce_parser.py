"""Tests for RCE Requirement Parser (Phase 1)."""

from pathlib import Path
import pytest

from rce.requirement_parser import (
    Requirement,
    RequirementParseError,
    parse_requirements,
    parse_requirements_from_text,
)


def test_parse_authoritative_requirements_md():
    """Verify parsing the authoritative requirements/requirements.md document."""
    reqs = parse_requirements("requirements/requirements.md")

    # Must contain exactly REQ-01 through REQ-10
    assert len(reqs) == 10
    expected_keys = [f"REQ-{i:02d}" for i in range(1, 11)]
    assert list(reqs.keys()) == expected_keys

    # Check REQ-01 details
    req01 = reqs["REQ-01"]
    assert req01.id == "REQ-01"
    assert req01.title == "Expense Submission"
    assert "Request ID" in req01.description
    assert "Employee ID" in req01.description
    assert "A submitted expense must enter the workflow." in req01.description

    # Check REQ-07 details
    req07 = reqs["REQ-07"]
    assert req07.id == "REQ-07"
    assert req07.title == "Manager Travel Override"
    assert "15,000" in req07.description
    assert "HR compliance remains mandatory." in req07.description

    # Check REQ-10 details - must stop before Section 3 ("3. Assumptions")
    req10 = reqs["REQ-10"]
    assert req10.id == "REQ-10"
    assert req10.title == "Final Approval"
    assert "Assumptions" not in req10.description
    assert "final gate" in req10.description.lower()


def test_parse_valid_custom_markdown(tmp_path: Path):
    """Test parsing markdown with varied delimiters and formatting."""
    content = """# System Requirements

## Section 2
### REQ-01 — First Requirement
Description of requirement 1.
Second line of description.

### REQ-02: Second Requirement
Description of requirement 2.

### REQ-03 - Third Requirement
Description of requirement 3.

## Section 3 Non-Req
Trailing notes.
"""
    file_path = tmp_path / "custom_reqs.md"
    file_path.write_text(content, encoding="utf-8")

    reqs = parse_requirements(file_path)
    assert len(reqs) == 3
    assert reqs["REQ-01"].title == "First Requirement"
    assert "Second line" in reqs["REQ-01"].description
    assert reqs["REQ-02"].title == "Second Requirement"
    assert reqs["REQ-03"].title == "Third Requirement"


def test_parse_missing_file_raises_filenotfound():
    """Verify FileNotFoundError is raised when file does not exist."""
    with pytest.raises(FileNotFoundError):
        parse_requirements("non_existent_requirements_file_12345.md")


def test_parse_empty_content_raises_error():
    """Verify empty or whitespace-only content raises RequirementParseError."""
    with pytest.raises(RequirementParseError, match="empty"):
        parse_requirements_from_text("")

    with pytest.raises(RequirementParseError, match="empty"):
        parse_requirements_from_text("   \n\n  \t  ")


def test_parse_no_requirements_raises_error():
    """Verify document with headings but no REQ entries raises RequirementParseError."""
    content = """# Overview
## Introduction
This document contains no requirements.
"""
    with pytest.raises(RequirementParseError, match="No valid requirement entries"):
        parse_requirements_from_text(content)


def test_parse_missing_title_raises_error():
    """Verify requirement heading with missing title raises RequirementParseError."""
    content = """### REQ-01
This requirement has no title on the heading line.
"""
    with pytest.raises(RequirementParseError, match="missing a title"):
        parse_requirements_from_text(content)


def test_parse_empty_title_raises_error():
    """Verify requirement heading with empty title delimiter raises RequirementParseError."""
    content = """### REQ-01 —   
This requirement has whitespace-only title.
"""
    with pytest.raises(RequirementParseError, match="missing a title"):
        parse_requirements_from_text(content)


def test_parse_empty_description_raises_error():
    """Verify requirement without description raises RequirementParseError."""
    content = """### REQ-01 — First
### REQ-02 — Second
Description of second requirement.
"""
    with pytest.raises(RequirementParseError, match="empty description"):
        parse_requirements_from_text(content)


def test_parse_duplicate_id_raises_error():
    """Verify duplicate requirement IDs raise RequirementParseError."""
    content = """### REQ-01 — First Version
Description 1.

### REQ-01 — Duplicate Version
Description 2.
"""
    with pytest.raises(RequirementParseError, match="Duplicate requirement ID"):
        parse_requirements_from_text(content)


def test_parse_malformed_id_raises_error():
    """Verify malformed requirement ID format raises RequirementParseError."""
    content = """### REQ-ABC — Invalid Identifier
Description here.
"""
    with pytest.raises(RequirementParseError, match="Malformed requirement heading"):
        parse_requirements_from_text(content)


def test_expected_ids_validation():
    """Verify expected_ids enforcement passes when present and fails when missing."""
    content = """### REQ-01 — First
Description 1.

### REQ-02 — Second
Description 2.
"""
    # Success case
    parsed = parse_requirements_from_text(content, expected_ids=["REQ-01", "REQ-02"])
    assert len(parsed) == 2

    # Failure case
    with pytest.raises(RequirementParseError, match=r"Missing expected requirements.*REQ-03"):
        parse_requirements_from_text(content, expected_ids=["REQ-01", "REQ-02", "REQ-03"])


def test_requirement_dataclass_methods():
    """Verify Requirement dataclass helper methods."""
    req = Requirement(id="REQ-01", title="Title", description="Desc")
    d = req.to_dict()
    assert d == {"id": "REQ-01", "title": "Title", "description": "Desc"}
    rep = repr(req)
    assert "REQ-01" in rep
    assert "Title" in rep
