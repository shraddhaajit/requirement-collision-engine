"""Independent project validation tests for RCE Phase 7.

Validates that RCE functions as a general-purpose static analysis and collision
detection tool across diverse domains beyond CEWS.

Tests:
1. Audit of default discovery exclusions (tests and tool implementation).
2. Domain Project A (Warehouse / Logistics):
   - Freight surcharge, express-shipping waiver, and remote delivery eligibility.
   - Threshold overlap and override detection on 'weight'.
   - Verification that unrelated variable 'zone_code' generates no collision.
   - End-to-end change-impact analysis and test discovery.
3. Domain Project B (Inventory / Order Management):
   - Stock availability, replenishment reorder, quantity limits, and cancellation.
   - Cross-module call/dependency chain (orders -> stock).
   - Conflicting rule detection on 'quantity' (<= 100 vs > 50).
   - Non-conflicting distinct thresholds (>= 10 vs < 5) verified collision-free.
   - Associated test discovery.
4. Clean project with zero collisions reported as successful completed analysis.
5. Syntax-error project reported as partial analysis with audit warnings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rce.cli import main
from rce.engine import (
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    EngineResult,
    run_engine,
)


# ---------------------------------------------------------------------------
# 1. Audit of Default Discovery Exclusions
# ---------------------------------------------------------------------------

def test_default_discovery_excludes_tests_and_tool_implementation():
    """Verify that default analysis on repository root analyzes target code only,

    excluding RCE's own implementation and pytest test files from application modules.
    """
    result = run_engine(project_root=".")

    assert result.success is True
    assert result.status == STATUS_COMPLETE

    # Only CEWS application modules should be analyzed as application modules
    module_names = set(result.to_dict()["statistics"].keys())

    # Check that modules count reflects CEWS core modules (~5-6), not 24+
    assert result.modules_count <= 8
    assert result.functions_count <= 25

    # Check that test files are not counted as application modules
    cews_result = run_engine(project_root=".", source_dirs=["cews"])
    assert cews_result.success is True
    assert cews_result.requirements_count == 10
    assert cews_result.collisions_count == 3


def test_explicit_source_dirs_includes_configured_folder():
    """Verify that when a source directory is explicitly configured, it is analyzed."""
    result = run_engine(project_root=".", source_dirs=["rce"])
    assert result.success is True
    # When explicitly configured, RCE modules are analyzed
    assert result.modules_count >= 5


# ---------------------------------------------------------------------------
# 2. Project A — Warehouse / Logistics Domain
# ---------------------------------------------------------------------------

@pytest.fixture
def project_a_dir(tmp_path: Path) -> Path:
    """Construct synthetic Project A (Warehouse / Logistics)."""
    p_dir = tmp_path / "warehouse_project"
    p_dir.mkdir()

    # Requirements
    req_file = p_dir / "logistics_requirements.md"
    req_file.write_text(
        "# Logistics & Shipping Specification\n\n"
        "### REQ-01 — Heavy Freight Surcharge\n"
        "Shipments with weight exceeding **50.0** kg must incur a heavy freight surcharge of $25.00.\n"
        "Shipments at or below 50.0 kg do not incur surcharge under this threshold rule.\n\n"
        "### REQ-02 — Express Shipping Waiver\n"
        "Express shipping orders with weight below **75.0** kg receive a waiver bypassing the Heavy Freight Surcharge (REQ-01) without the normal heavy freight stage.\n\n"
        "### REQ-03 — Remote Delivery Zone Code\n"
        "Orders delivered to destination zone code equal to **ZONE_REMOTE** must not be dispatched via standard courier.\n",
        encoding="utf-8",
    )

    # Package: warehouse
    src_dir = p_dir / "warehouse"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    # warehouse/shipping.py
    (src_dir / "shipping.py").write_text(
        '"""Shipping surcharge calculation.\n\nTRACE: REQ-01\n"""\n\n'
        'def calculate_freight_surcharge(weight: float) -> float:\n'
        '    """Calculate surcharge.\n\n    TRACE: REQ-01\n    """\n'
        '    if weight > 50.0:\n'
        '        return 25.0\n'
        '    return 0.0\n',
        encoding="utf-8",
    )

    # warehouse/express.py
    (src_dir / "express.py").write_text(
        '"""Express shipping waiver and dispatch gate.\n\nTRACE: REQ-02\n"""\n'
        'from warehouse.shipping import calculate_freight_surcharge\n\n'
        'def express_shipping_waiver(weight: float) -> bool:\n'
        '    """Waiver check.\n\n    TRACE: REQ-02\n    """\n'
        '    if weight < 75.0:\n'
        '        return True\n'
        '    return False\n\n'
        'def dispatch_cargo(weight: float, is_express: bool) -> bool:\n'
        '    """Dispatch gate checking surcharge and waiver.\n\n    TRACE: REQ-01, REQ-02\n    """\n'
        '    surcharge = calculate_freight_surcharge(weight)\n'
        '    is_override = is_express and express_shipping_waiver(weight)\n'
        '    if not (surcharge == 0.0 or is_override):\n'
        '        return False\n'
        '    return True\n',
        encoding="utf-8",
    )

    # warehouse/delivery.py
    (src_dir / "delivery.py").write_text(
        '"""Delivery routing and zone eligibility.\n\nTRACE: REQ-03\n"""\n\n'
        'def check_remote_eligibility(zone_code: str) -> bool:\n'
        '    """Remote zone check.\n\n    TRACE: REQ-03\n    """\n'
        '    if zone_code == "ZONE_REMOTE":\n'
        '        return False\n'
        '    return True\n',
        encoding="utf-8",
    )

    # tests/test_shipping.py
    t_dir = p_dir / "tests"
    t_dir.mkdir()
    (t_dir / "__init__.py").write_text("", encoding="utf-8")
    (t_dir / "test_shipping.py").write_text(
        '"""Warehouse tests.\n\nTRACE: REQ-01\n"""\n'
        'from warehouse.shipping import calculate_freight_surcharge\n\n'
        'def test_freight_rate():\n'
        '    """Test freight rate.\n\n    TRACE: REQ-01\n    """\n'
        '    assert calculate_freight_surcharge(60.0) == 25.0\n'
        '    assert calculate_freight_surcharge(40.0) == 0.0\n',
        encoding="utf-8",
    )

    return p_dir


def test_project_a_end_to_end_analysis(project_a_dir: Path, capsys):
    """Verify complete analysis and grounded collision detection on Project A."""
    result = run_engine(
        project_root=project_a_dir,
        requirements_path="logistics_requirements.md",
        impact_target="REQ-01",
        max_depth=3,
    )

    assert result.success is True
    assert result.status == STATUS_COMPLETE
    assert result.requirements_count == 3
    assert result.modules_count >= 3  # shipping, express, delivery (+ __init__)
    assert result.functions_count >= 4
    assert result.graph_nodes_count > 0
    assert result.graph_edges_count > 0

    # 1. Collision detection verification
    assert result.collisions_count >= 1
    finding_rules = [f.detection_rule for f in result.findings]
    finding_reqs = [set(f.requirement_ids) for f in result.findings]

    # Rule B: Threshold interval overlap on 'weight' between REQ-01 (> 50.0) and REQ-02 (< 75.0)
    rule_b_findings = [f for f in result.findings if "Rule B" in f.detection_rule]
    assert len(rule_b_findings) >= 1
    f_b = rule_b_findings[0]
    assert set(f_b.requirement_ids) == {"REQ-01", "REQ-02"}
    assert "weight" in f_b.explanation.lower()
    assert any("50.0" in ev for ev in f_b.evidence)
    assert any("75.0" in ev for ev in f_b.evidence)
    assert f_b.requires_human_review is True

    # Rule C: Override interaction between REQ-01 and REQ-02
    rule_c_findings = [f for f in result.findings if "Rule C" in f.detection_rule]
    assert len(rule_c_findings) >= 1
    f_c = rule_c_findings[0]
    assert set(f_c.requirement_ids) == {"REQ-01", "REQ-02"}
    assert "REQ-02" in f_c.requirement_ids

    # 2. Precision check: Unrelated condition (zone_code == 'ZONE_REMOTE') must NOT collide
    for f in result.findings:
        assert "REQ-03" not in f.requirement_ids
        assert "zone_code" not in f.explanation

    # 3. Change-impact analysis for REQ-01
    assert result.impact_report is not None
    assert result.impact_report.target_id == "REQ-01"
    assert any("calculate_freight_surcharge" in fn for fn in result.impact_report.affected_functions)
    assert any("dispatch_cargo" in fn for fn in result.impact_report.affected_functions)
    assert any("test_freight_rate" in t for t in result.impact_report.affected_tests)

    # 4. CLI JSON execution
    exit_code = main([
        "--project-root", str(project_a_dir),
        "--requirements", "logistics_requirements.md",
        "--format", "json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed["success"] is True
    assert parsed["statistics"]["requirements_count"] == 3
    assert len(parsed["findings"]) >= 1


# ---------------------------------------------------------------------------
# 3. Project B — Inventory / Order Management Domain
# ---------------------------------------------------------------------------

@pytest.fixture
def project_b_dir(tmp_path: Path) -> Path:
    """Construct synthetic Project B (Inventory / Order Management)."""
    p_dir = tmp_path / "inventory_project"
    p_dir.mkdir()

    # Requirements
    req_file = p_dir / "inventory_requirements.md"
    req_file.write_text(
        "# Inventory Management Specification\n\n"
        "### REQ-01 — Stock Availability Gate\n"
        "Orders must verify that item stock is greater than or equal to **10** units before order confirmation.\n\n"
        "### REQ-02 — Minimum Reorder Replenishment\n"
        "When item stock is less than **5** units, an automated replenishment restock order must be triggered.\n\n"
        "### REQ-03 — Standard Order Quantity Limit\n"
        "Standard retail customer order quantity must not exceed **100** items.\n\n"
        "### REQ-04 — Wholesale Bulk Minimum\n"
        "Wholesale customer order quantity must exceed **50** items.\n\n"
        "### REQ-05 — Order Cancellation Status\n"
        "Cancelled orders must update status to value **CANCELLED**.\n",
        encoding="utf-8",
    )

    # Package: inventory
    src_dir = p_dir / "inventory"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    # inventory/stock.py
    (src_dir / "stock.py").write_text(
        '"""Stock management and replenishment.\n\nTRACE: REQ-01, REQ-02\n"""\n\n'
        'def check_stock_available(stock: int) -> bool:\n'
        '    """Stock gate.\n\n    TRACE: REQ-01\n    """\n'
        '    if stock >= 10:\n'
        '        return True\n'
        '    return False\n\n'
        'def trigger_reorder(stock: int) -> bool:\n'
        '    """Reorder gate.\n\n    TRACE: REQ-02\n    """\n'
        '    if stock < 5:\n'
        '        return True\n'
        '    return False\n',
        encoding="utf-8",
    )

    # inventory/orders.py
    (src_dir / "orders.py").write_text(
        '"""Order placement and quantity validation.\n\nTRACE: REQ-03, REQ-04\n"""\n'
        'from inventory.stock import check_stock_available\n\n'
        'def validate_order_quantity(quantity: int) -> bool:\n'
        '    """Evaluate limits.\n\n    TRACE: REQ-03, REQ-04\n    """\n'
        '    if quantity <= 100:\n'
        '        pass\n'
        '    if quantity > 50:\n'
        '        pass\n'
        '    return True\n\n'
        'def place_order(item_id: str, quantity: int, stock: int) -> bool:\n'
        '    """Place customer order.\n\n    TRACE: REQ-01, REQ-03\n    """\n'
        '    if not check_stock_available(stock):\n'
        '        return False\n'
        '    return validate_order_quantity(quantity)\n',
        encoding="utf-8",
    )

    # inventory/cancellation.py
    (src_dir / "cancellation.py").write_text(
        '"""Order cancellation.\n\nTRACE: REQ-05\n"""\n\n'
        'def cancel_order(order_id: str, status: str) -> str:\n'
        '    """Cancel order.\n\n    TRACE: REQ-05\n    """\n'
        '    if status != "CANCELLED":\n'
        '        return "CANCELLED"\n'
        '    return status\n',
        encoding="utf-8",
    )

    # tests/test_inventory_flow.py
    t_dir = p_dir / "tests"
    t_dir.mkdir()
    (t_dir / "__init__.py").write_text("", encoding="utf-8")
    (t_dir / "test_inventory_flow.py").write_text(
        '"""Order placement test.\n\nTRACE: REQ-01\n"""\n'
        'from inventory.orders import place_order\n\n'
        'def test_order_placement_flow():\n'
        '    """Verify order flow.\n\n    TRACE: REQ-01\n    """\n'
        '    assert place_order("SKU-1", 10, 20) is True\n'
        '    assert place_order("SKU-2", 10, 2) is False\n',
        encoding="utf-8",
    )

    return p_dir


def test_project_b_end_to_end_analysis(project_b_dir: Path, capsys):
    """Verify complete analysis, cross-module call chains, and collision detection on Project B."""
    result = run_engine(
        project_root=project_b_dir,
        requirements_path="inventory_requirements.md",
        impact_target="REQ-01",
        max_depth=3,
    )

    assert result.success is True
    assert result.status == STATUS_COMPLETE
    assert result.requirements_count == 5
    assert result.modules_count >= 3  # stock, orders, cancellation (+ __init__)
    assert result.functions_count >= 5

    # 1. Deliberately conflicting rule detection
    # REQ-03 (quantity <= 100) vs REQ-04 (quantity > 50) in validate_order_quantity
    qty_findings = [
        f for f in result.findings
        if {"REQ-03", "REQ-04"}.issubset(set(f.requirement_ids))
    ]
    assert len(qty_findings) >= 1
    f_qty = qty_findings[0]
    assert "quantity" in f_qty.explanation.lower()
    assert any("50" in ev for ev in f_qty.evidence)
    assert any("100" in ev for ev in f_qty.evidence)

    # 2. Non-conflicting rule verification:
    # REQ-01 (stock >= 10) vs REQ-02 (stock < 5) are disjoint and MUST NOT be flagged as conflicting
    stock_conflict_findings = [
        f for f in result.findings
        if {"REQ-01", "REQ-02"}.issubset(set(f.requirement_ids))
        and f.category in ("CONDITION_CONTRADICTION", "BOUNDARY_CONDITION_COLLISION")
    ]
    assert len(stock_conflict_findings) == 0

    # 3. REQ-05 (status != 'CANCELLED') must NOT collide with stock or quantity
    req05_findings = [f for f in result.findings if "REQ-05" in f.requirement_ids]
    assert len(req05_findings) == 0

    # 4. Cross-module call/dependency chain impact analysis
    # REQ-01 -> check_stock_available <-(CALLS)- place_order
    assert result.impact_report is not None
    assert result.impact_report.target_id == "REQ-01"
    assert any("check_stock_available" in fn for fn in result.impact_report.affected_functions)
    assert any("place_order" in fn for fn in result.impact_report.affected_functions)
    assert any("test_order_placement_flow" in t for t in result.impact_report.affected_tests)

    # 5. CLI invocation in text format
    exit_code = main([
        "--project-root", str(project_b_dir),
        "--requirements", "inventory_requirements.md",
        "--format", "text",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "REQUIREMENT COLLISION ENGINE (RCE)" in captured.out
    assert "Requirements   : 5" in captured.out
    assert "COL-RULE_B-REQ-03-REQ-04" in captured.out


# ---------------------------------------------------------------------------
# 4. Clean Project with No Detected Collisions
# ---------------------------------------------------------------------------

def test_clean_project_zero_collisions_success(tmp_path: Path, capsys):
    """Verify that a project with completely non-conflicting rules reports success,

    not an error, and clearly distinguishes 'zero findings' from analysis failure.
    """
    clean_dir = tmp_path / "clean_project"
    clean_dir.mkdir()

    (clean_dir / "clean_reqs.md").write_text(
        "# Clean Specification\n\n"
        "### REQ-01 — Positive Temperature Warning\n"
        "Temperature must be above **100** degrees to trigger overheating warning.\n\n"
        "### REQ-02 — Freezing Temperature Warning\n"
        "Temperature must be below **0** degrees to trigger frost warning.\n",
        encoding="utf-8",
    )

    (clean_dir / "sensor.py").write_text(
        '"""Temperature sensor.\n\nTRACE: REQ-01, REQ-02\n"""\n\n'
        'def check_temp(temp: float) -> str:\n'
        '    """Sensor check.\n\n    TRACE: REQ-01, REQ-02\n    """\n'
        '    if temp > 100.0:\n'
        '        return "HOT"\n'
        '    if temp < 0.0:\n'
        '        return "FREEZE"\n'
        '    return "NORMAL"\n',
        encoding="utf-8",
    )

    result = run_engine(
        project_root=clean_dir,
        requirements_path="clean_reqs.md",
    )

    assert result.success is True
    assert result.status == STATUS_COMPLETE
    assert result.requirements_count == 2
    assert result.collisions_count == 0
    assert len(result.findings) == 0

    # Text report should clearly communicate clean status
    exit_code = main([
        "--project-root", str(clean_dir),
        "--requirements", "clean_reqs.md",
        "--format", "text",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No requirement collisions detected across 2 analyzed requirements." in captured.out


# ---------------------------------------------------------------------------
# 5. Incomplete / Syntax Error Project Partial Status
# ---------------------------------------------------------------------------

def test_syntax_error_project_marked_partial_not_collision_free(tmp_path: Path, capsys):
    """Verify that syntax errors set status to partial and disclaim collision-free certainty."""
    bad_dir = tmp_path / "broken_project"
    bad_dir.mkdir()

    (bad_dir / "reqs.md").write_text(
        "# Broken Project\n\n"
        "### REQ-01 — Gate Requirement\n"
        "Gate rule.\n",
        encoding="utf-8",
    )

    (bad_dir / "good.py").write_text(
        '"""Valid module.\n\nTRACE: REQ-01\n"""\n'
        'def good_gate(x: int) -> bool:\n'
        '    """Valid.\n\n    TRACE: REQ-01\n    """\n'
        '    if x > 10:\n'
        '        return True\n'
        '    return False\n',
        encoding="utf-8",
    )

    (bad_dir / "syntax_error.py").write_text(
        'def broken_function(\n',  # unclosed parenthesis
        encoding="utf-8",
    )

    result = run_engine(
        project_root=bad_dir,
        requirements_path="reqs.md",
    )

    assert result.success is True
    assert result.status == STATUS_PARTIAL
    assert any("syntax_error.py" in w for w in result.warnings)

    exit_code = main([
        "--project-root", str(bad_dir),
        "--requirements", "reqs.md",
        "--format", "text",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PARTIAL" in captured.out
    assert "Collision-free status cannot be guaranteed for unanalyzed artifacts" in captured.out
