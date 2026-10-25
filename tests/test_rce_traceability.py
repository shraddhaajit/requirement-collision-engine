"""Tests for RCE Traceability Extractor (Phase 1)."""

from pathlib import Path
import pytest

from rce.traceability_extractor import (
    TraceItem,
    TraceabilityExtractionError,
    extract_requirement_ids_from_docstring,
    extract_traceability_from_directory,
    extract_traceability_from_file,
    extract_traceability_from_source,
    build_traceability_matrix,
    build_requirement_to_entities_map,
)


def test_extract_cews_directory():
    """Verify static extraction across the real cews/ directory."""
    items = extract_traceability_from_directory("cews")

    # 12 items: 1 class (Expense) + 11 functions across 4 files
    assert len(items) == 12

    # Check that all 10 requirements (REQ-01 to REQ-10) are mapped
    matrix = build_traceability_matrix(items)
    for i in range(1, 11):
        req_id = f"REQ-{i:02d}"
        assert req_id in matrix, f"Expected {req_id} to be mapped in cews"
        assert len(matrix[req_id]) > 0

    # Specific known mappings
    req_map = build_requirement_to_entities_map(items)
    assert any("audit.py:record_audit_log" in ent for ent in req_map["REQ-09"])
    assert any("compliance.py:check_hr_compliance" in ent for ent in req_map["REQ-04"])
    assert any("approval.py:validate_budget" in ent for ent in req_map["REQ-02"])
    assert any("expense.py:Expense" in ent for ent in req_map["REQ-01"])


def test_extract_single_tag():
    """Verify extracting a single requirement tag."""
    code = '''
def calculate_tax():
    """TRACE: REQ-05
    Calculates tax.
    """
    return 0.18
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 1
    assert items[0].name == "calculate_tax"
    assert items[0].requirement_ids == ["REQ-05"]
    assert items[0].entity_type == "function"


def test_extract_multiple_tags_comma_separated():
    """Verify extracting multiple comma-separated requirement tags."""
    code = '''
def gatekeeper():
    """TRACE: REQ-01, REQ-04, REQ-10
    Enforces multiple gates.
    """
    pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 1
    assert items[0].name == "gatekeeper"
    assert items[0].requirement_ids == ["REQ-01", "REQ-04", "REQ-10"]


def test_extract_multiple_trace_lines():
    """Verify extracting tags across multiple TRACE lines in one docstring."""
    code = '''
def composite_action():
    """
    TRACE: REQ-01
    Some intermediate text.
    TRACE: REQ-02, REQ-03
    """
    pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 1
    assert items[0].requirement_ids == ["REQ-01", "REQ-02", "REQ-03"]


def test_ignore_unrelated_text():
    """Verify that requirement IDs mentioned in regular prose are ignored."""
    code = '''
def helper():
    """
    This function was inspired by REQ-01 and references REQ-02 in comments.
    However it only officially traces to REQ-09:
    TRACE: REQ-09
    See also REQ-10 for future planning.
    """
    pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 1
    assert items[0].requirement_ids == ["REQ-09"]


def test_ignore_invalid_tags_safely():
    """Verify that malformed or non-requirement tokens on TRACE line are safely ignored."""
    code = '''
def resilient_func():
    """TRACE: REQ-01, INVALID_TAG, REQ-XYZ, REQ-, 999, REQ-02"""
    pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 1
    # Only valid REQ-<digits> are extracted
    assert items[0].requirement_ids == ["REQ-01", "REQ-02"]


def test_methods_inside_classes():
    """Verify methods inside classes are properly qualified and typed."""
    code = '''
class InvoiceService:
    def create_invoice(self):
        """TRACE: REQ-01"""
        pass

    def approve_invoice(self):
        """TRACE: REQ-03"""
        pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 2
    assert items[0].name == "InvoiceService.create_invoice"
    assert items[0].entity_type == "method"
    assert items[0].requirement_ids == ["REQ-01"]

    assert items[1].name == "InvoiceService.approve_invoice"
    assert items[1].entity_type == "method"
    assert items[1].requirement_ids == ["REQ-03"]


def test_class_definition_trace():
    """Verify class itself tagged with TRACE is captured."""
    code = '''
class ExpenseRecord:
    """TRACE: REQ-01
    Data model representing expense.
    """
    pass
'''
    items = extract_traceability_from_source(code, include_classes=True)
    assert len(items) == 1
    assert items[0].name == "ExpenseRecord"
    assert items[0].entity_type == "class"
    assert items[0].requirement_ids == ["REQ-01"]

    # When include_classes=False, class should be skipped
    items_no_class = extract_traceability_from_source(code, include_classes=False)
    assert len(items_no_class) == 0


def test_async_functions():
    """Verify async functions are properly captured."""
    code = '''
async def notify_manager():
    """TRACE: REQ-03
    Async notification service.
    """
    pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 1
    assert items[0].name == "notify_manager"
    assert items[0].entity_type == "function"
    assert items[0].requirement_ids == ["REQ-03"]


def test_no_trace_tags():
    """Verify entities without TRACE tags produce no items."""
    code = '''
def regular_function():
    """Just a normal docstring without trace tags."""
    pass

def undocumented_function():
    pass
'''
    items = extract_traceability_from_source(code)
    assert len(items) == 0


def test_syntax_error_handling(tmp_path: Path):
    """Verify syntax error in source file raises TraceabilityExtractionError."""
    bad_code = "def broken_syntax(:\n    pass"
    with pytest.raises(TraceabilityExtractionError, match="Syntax error"):
        extract_traceability_from_source(bad_code, file_path="broken.py")

    bad_file = tmp_path / "broken.py"
    bad_file.write_text(bad_code, encoding="utf-8")
    with pytest.raises(TraceabilityExtractionError, match="Syntax error"):
        extract_traceability_from_file(bad_file)


def test_file_not_found_handling():
    """Verify FileNotFoundError is raised for nonexistent file or directory."""
    with pytest.raises(FileNotFoundError):
        extract_traceability_from_file("nonexistent_file_xyz.py")

    with pytest.raises(FileNotFoundError):
        extract_traceability_from_directory("nonexistent_dir_xyz")


def test_trace_item_dataclass_methods():
    """Verify TraceItem dataclass helper methods and properties."""
    item = TraceItem(
        file_path="cews/audit.py",
        name="record_audit_log",
        requirement_ids=["REQ-09"],
        entity_type="function",
        line_number=8,
    )
    assert item.source_file == "cews/audit.py"
    assert item.function_name == "record_audit_log"
    assert item.to_dict() == {
        "file_path": "cews/audit.py",
        "name": "record_audit_log",
        "requirement_ids": ["REQ-09"],
        "entity_type": "function",
        "line_number": 8,
    }
    assert "REQ-09" in repr(item)


def test_strict_valid_ids_filtering():
    """Verify valid_ids parameter strictly filters allowed requirements."""
    docstring = "TRACE: REQ-01, REQ-99, REQ-02"
    # Without valid_ids filter: both REQ-01, REQ-99, REQ-02 are extracted
    all_ids = extract_requirement_ids_from_docstring(docstring)
    assert all_ids == ["REQ-01", "REQ-99", "REQ-02"]

    # With valid_ids filter: REQ-99 is excluded
    filtered = extract_requirement_ids_from_docstring(
        docstring, valid_ids={"REQ-01", "REQ-02"}
    )
    assert filtered == ["REQ-01", "REQ-02"]
