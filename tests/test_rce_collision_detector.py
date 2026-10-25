"""Unit and integration tests for RCE Phase 4: Collision Detection Engine.

Covers:
- Deliberately constructed conflicting-condition examples (Rule B).
- Non-conflicting pairs of requirements sharing a function (Rule A precision).
- Exception and override interactions (Rule C).
- Different variable names and unrelated functions that must not be equated.
- Boundary condition overlap cases (Rule B).
- Duplicate suppression across detection runs.
- Missing evidence, empty graphs, and partial inputs.
- Synthetic multi-module non-CEWS project.
- Real CEWS integration test checking REQ-03 / REQ-07 / REQ-08 interactions with grounded evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from rce.ast_analyzer import (
    ConditionInfo,
    FunctionInfo,
    ModuleInfo,
    ProjectAnalysis,
    analyze_project,
    analyze_source,
)
from rce.collision_detector import (
    CAT_BOUNDARY_OVERLAP,
    CAT_CONDITION_CONTRADICTION,
    CAT_OVERRIDE_INTERACTION,
    CAT_SHARED_CONDITION,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    RULE_A_SHARED_CONDITIONS,
    RULE_B_CONFLICTING_CONDITIONS,
    RULE_C_OVERRIDE_INTERACTIONS,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    CollisionFinding,
    detect_collisions,
    findings_to_dict,
    findings_to_json,
    format_collision_report,
    get_collisions_for_requirement,
)
from rce.knowledge_graph import build_knowledge_graph
from rce.requirement_parser import Requirement, parse_requirements_from_text


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _make_req(req_id: str, title: str, description: str) -> Requirement:
    """Helper to construct a Requirement dataclass for testing."""
    return Requirement(
        id=req_id.upper(),
        title=title,
        description=description,
    )


def _make_analysis(modules: dict[str, ModuleInfo]) -> ProjectAnalysis:
    """Helper to construct a valid ProjectAnalysis instance from modules."""
    all_fns: list[FunctionInfo] = []
    all_classes = []
    for mod in modules.values():
        all_fns.extend(mod.all_functions)
        all_classes.extend(mod.classes)
    return ProjectAnalysis(
        project_root=".",
        modules=modules,
        functions=all_fns,
        classes=all_classes,
        call_graph={},
        unresolved_calls={},
    )


# ---------------------------------------------------------------------------
# 1. Deliberately constructed conflicting-condition example (Rule B)
# ---------------------------------------------------------------------------

def test_rule_b_direct_numeric_contradiction():
    """Conflicting numeric conditions on the same variable and threshold must be flagged."""
    code = '''
def check_minimum_balance(account):
    """TRACE: REQ-01"""
    if account.balance > 100.0:
        return True
    return False

def check_maximum_balance(account):
    """TRACE: REQ-02"""
    if account.balance <= 100.0:
        return True
    return False
'''
    mod = analyze_source(code, "bank/accounts.py", "bank.accounts")
    analysis = _make_analysis({"bank.accounts": mod})

    reqs = [
        _make_req("REQ-01", "Minimum Balance", "Balance must exceed 100."),
        _make_req("REQ-02", "Maximum Balance", "Balance must be at most 100."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_B"])

    assert len(findings) == 1
    f = findings[0]
    assert f.collision_id == "COL-RULE_B-REQ-01-REQ-02-BALANCE"
    assert f.category == CAT_CONDITION_CONTRADICTION
    assert f.severity == SEVERITY_HIGH
    assert f.confidence == CONFIDENCE_HIGH
    assert f.requirement_ids == ["REQ-01", "REQ-02"]
    assert f.requires_human_review is True
    assert "account.balance > 100.0" in f.evidence[0] or "account.balance > 100.0" in f.evidence[1]
    assert "account.balance <= 100.0" in f.evidence[0] or "account.balance <= 100.0" in f.evidence[1]


def test_rule_b_discrete_equality_contradiction():
    """Discrete contradictory equality conditions (== vs != on same value) must be flagged."""
    code = '''
def verify_active_status(order):
    """TRACE: REQ-01"""
    if order.status == "CONFIRMED":
        return True
    return False

def verify_inactive_status(order):
    """TRACE: REQ-02"""
    if order.status != "CONFIRMED":
        return True
    return False
'''
    mod = analyze_source(code, "orders/status.py", "orders.status")
    analysis = _make_analysis({"orders.status": mod})

    reqs = [
        _make_req("REQ-01", "Confirmed Order", "Order status must be CONFIRMED."),
        _make_req("REQ-02", "Unconfirmed Order", "Order status must not be CONFIRMED."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_B"])

    assert len(findings) == 1
    f = findings[0]
    assert f.category == CAT_CONDITION_CONTRADICTION
    assert f.severity == SEVERITY_HIGH
    assert "status" in f.collision_id.lower()


# ---------------------------------------------------------------------------
# 2. Boundary condition overlap (Rule B)
# ---------------------------------------------------------------------------

def test_rule_b_boundary_condition_overlap():
    """Opposing operators with lower_bound < upper_bound must be flagged as boundary overlap."""
    code = '''
def check_tier_one(customer):
    """TRACE: REQ-01"""
    if customer.score >= 500.0:
        return "TIER_ONE"
    return "STANDARD"

def check_tier_two_limit(customer):
    """TRACE: REQ-02"""
    if customer.score <= 750.0:
        return "TIER_TWO"
    return "STANDARD"
'''
    mod = analyze_source(code, "loyalty/tiers.py", "loyalty.tiers")
    analysis = _make_analysis({"loyalty.tiers": mod})

    reqs = [
        _make_req("REQ-01", "Tier 1 Qualification", "Customers with score >= 500 qualify for Tier 1."),
        _make_req("REQ-02", "Tier 2 Limit", "Customers with score <= 750 qualify for Tier 2."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_B"])

    assert len(findings) == 1
    f = findings[0]
    assert f.category == CAT_BOUNDARY_OVERLAP
    assert f.severity == SEVERITY_MEDIUM
    assert f.confidence == CONFIDENCE_HIGH
    assert "500.00" in f.explanation
    assert "750.00" in f.explanation


# ---------------------------------------------------------------------------
# 3. Non-conflicting pair sharing a function (Rule A precision)
# ---------------------------------------------------------------------------

def test_non_conflicting_pair_sharing_function():
    """Requirements sharing a function with orthogonal conditions must NOT be flagged."""
    code = '''
def process_user_registration(user):
    """TRACE: REQ-01, REQ-02
    Handles registration input validation.
    """
    # REQ-01: email must be non-empty
    if not user.email:
        raise ValueError("Missing email")
    # REQ-02: age must be positive
    if user.age <= 0:
        raise ValueError("Invalid age")
    return True
'''
    mod = analyze_source(code, "users/reg.py", "users.reg")
    analysis = _make_analysis({"users.reg": mod})

    reqs = [
        _make_req("REQ-01", "Email Validation", "User email must be provided."),
        _make_req("REQ-02", "Age Validation", "User age must be positive."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis)
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# 4. Incompatible variables and unrelated functions must NOT be equated
# ---------------------------------------------------------------------------

def test_different_variable_names_not_equated():
    """Conditions testing different attributes must not be equated."""
    code = '''
def check_pricing(order):
    """TRACE: REQ-01"""
    if order.price > 100.0:
        return True
    return False

def check_weight(order):
    """TRACE: REQ-02"""
    if order.weight < 50.0:
        return True
    return False
'''
    mod = analyze_source(code, "shipping/pricing.py", "shipping.pricing")
    analysis = _make_analysis({"shipping.pricing": mod})

    reqs = [
        _make_req("REQ-01", "Price Check", "Orders with price > 100."),
        _make_req("REQ-02", "Weight Check", "Orders with weight < 50."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_B"])
    assert len(findings) == 0


def test_unrelated_functions_with_same_local_var_not_equated():
    """Unrelated functions in different modules sharing a local variable name must NOT be equated."""
    code_mod_a = '''
def set_network_timeout(config):
    """TRACE: REQ-01"""
    if config.limit > 100:
        return True
    return False
'''
    code_mod_b = '''
def set_storage_cache(store):
    """TRACE: REQ-02"""
    if store.limit < 50:
        return True
    return False
'''
    mod_a = analyze_source(code_mod_a, "infra/network.py", "infra.network")
    mod_b = analyze_source(code_mod_b, "infra/storage.py", "infra.storage")
    analysis = _make_analysis({"infra.network": mod_a, "infra.storage": mod_b})

    reqs = [
        _make_req("REQ-01", "Network Timeout", "Network limit must be > 100."),
        _make_req("REQ-02", "Storage Cache", "Storage limit must be < 50."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_B"])
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# 5. Exception or override interaction (Rule C)
# ---------------------------------------------------------------------------

def test_rule_c_override_interaction():
    """Override requirement linked to standard rule in text and disjunctive gate must be flagged."""
    code = '''
def standard_payment_check(order):
    """TRACE: REQ-01"""
    return order.is_paid

def vip_override_check(order):
    """TRACE: REQ-02"""
    return order.is_vip and order.vip_level > 2

def process_dispatch(order):
    """TRACE: REQ-01, REQ-02"""
    paid = standard_payment_check(order)
    vip_ok = vip_override_check(order)
    if not (paid or vip_ok):
        return False
    return True
'''
    mod = analyze_source(code, "fulfillment/dispatch.py", "fulfillment.dispatch")
    analysis = _make_analysis({"fulfillment.dispatch": mod})

    reqs = [
        _make_req("REQ-01", "Payment Check", "Standard orders require payment clearance."),
        _make_req(
            "REQ-02",
            "VIP Override",
            "VIP orders may bypass payment check stage.\nHowever:\n- Customer verification remains mandatory.",
        ),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_C"])

    assert len(findings) == 1
    f = findings[0]
    assert f.collision_id == "COL-RULE_C-REQ-01-REQ-02"
    assert f.category == CAT_OVERRIDE_INTERACTION
    assert f.severity == SEVERITY_HIGH  # due to mandatory customer verification constraint
    assert f.confidence == CONFIDENCE_HIGH
    assert f.requirement_ids == ["REQ-01", "REQ-02"]
    assert "process_dispatch" in f.related_functions
    assert any("not (paid or vip_ok)" in ev for ev in f.evidence)


# ---------------------------------------------------------------------------
# 6. Shared implementation with overlapping conditions (Rule A)
# ---------------------------------------------------------------------------

def test_rule_a_shared_implementation_overlapping_conditions():
    """Shared function with multiple branching conditions on the same variable triggers Rule A."""
    code = '''
def dispatch_role_action(actor):
    """TRACE: REQ-01, REQ-02"""
    if actor.role == "ADMIN":
        return "ALL_ACCESS"
    if actor.role == "AUDITOR":
        return "READ_ONLY"
    return "DENIED"
'''
    mod = analyze_source(code, "security/rbac.py", "security.rbac")
    analysis = _make_analysis({"security.rbac": mod})

    reqs = [
        _make_req("REQ-01", "Admin Privileges", "Admins have full access."),
        _make_req("REQ-02", "Auditor Access", "Auditors have read-only access."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_A"])

    assert len(findings) == 1
    f = findings[0]
    assert f.category == CAT_SHARED_CONDITION
    assert f.severity == SEVERITY_LOW
    assert f.confidence == CONFIDENCE_MEDIUM
    assert f.requirement_ids == ["REQ-01", "REQ-02"]
    assert "dispatch_role_action" in f.related_functions


# ---------------------------------------------------------------------------
# 7. Duplicate suppression
# ---------------------------------------------------------------------------

def test_duplicate_suppression():
    """Multiple identical comparisons or runs must produce deduplicated findings."""
    code = '''
def validate_a(item):
    """TRACE: REQ-01"""
    if item.val > 100.0:
        return True
    if item.val > 100.0:
        return True
    return False

def validate_b(item):
    """TRACE: REQ-02"""
    if item.val <= 100.0:
        return True
    return False
'''
    mod = analyze_source(code, "dup/test_dup.py", "dup.test_dup")
    analysis = _make_analysis({"dup.test_dup": mod})

    reqs = [
        _make_req("REQ-01", "Rule A", "Val > 100."),
        _make_req("REQ-02", "Rule B", "Val <= 100."),
    ]

    findings = detect_collisions(requirements=reqs, analysis=analysis, rules=["RULE_B"])
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# 8. Missing evidence, empty graphs, and partial inputs
# ---------------------------------------------------------------------------

def test_missing_evidence_and_partial_inputs():
    """Empty or partial inputs must be handled gracefully without errors."""
    # None inputs
    assert detect_collisions() == []

    # Empty requirements and analysis
    assert detect_collisions(requirements={}, analysis=None) == []

    # Empty graph
    empty_graph = nx.DiGraph()
    assert detect_collisions(requirements=[], analysis=None, graph=empty_graph) == []

    # Analysis with no conditions
    code = '''
def no_conditions():
    """TRACE: REQ-01"""
    return 42
'''
    mod = analyze_source(code, "empty/test.py", "empty.test")
    analysis = _make_analysis({"empty.test": mod})
    reqs = [_make_req("REQ-01", "No Cond", "Does nothing.")]
    assert detect_collisions(requirements=reqs, analysis=analysis) == []

    # Format report with empty findings
    assert format_collision_report([]) == "No requirement collisions detected based on current evidence."


# ---------------------------------------------------------------------------
# 9. Synthetic multi-module non-CEWS project
# ---------------------------------------------------------------------------

def test_synthetic_non_cews_project(tmp_path: Path):
    """End-to-end collision detection on an arbitrary synthetic non-CEWS project."""
    req_dir = tmp_path / "requirements"
    req_dir.mkdir(parents=True)
    (req_dir / "requirements.md").write_text(
        """# Warehouse Shipping Requirements

### REQ-01 — Heavy Freight Surcharge
Shipments with weight above 50.0 kg require a freight surcharge.

### REQ-02 — Express Weight Waiver
Express delivery can waive freight surcharge for shipments with weight below 70.0 kg without the normal heavy freight surcharge.
However:
- Hazmat inspection remains mandatory.

### REQ-03 — Hazmat Inspection
Hazardous materials must undergo hazmat inspection before dispatch.
""",
        encoding="utf-8",
    )

    src_dir = tmp_path / "logistics"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    (src_dir / "freight.py").write_text(
        '''"""Freight calculation module."""

def check_heavy_freight(cargo) -> bool:
    """TRACE: REQ-01"""
    if cargo.weight > 50.0:
        return cargo.has_surcharge
    return True

def express_weight_waiver(cargo) -> bool:
    """TRACE: REQ-02"""
    if cargo.is_express and cargo.weight < 70.0:
        return True
    return False

def check_hazmat(cargo) -> bool:
    """TRACE: REQ-03"""
    if cargo.is_hazmat:
        return cargo.hazmat_cleared
    return True

def dispatch_cargo(cargo) -> bool:
    """TRACE: REQ-01, REQ-02, REQ-03"""
    freight_ok = check_heavy_freight(cargo)
    express_ok = express_weight_waiver(cargo)
    hazmat_ok = check_hazmat(cargo)

    if not hazmat_ok:
        return False
    if not (freight_ok or express_ok):
        return False
    return True
''',
        encoding="utf-8",
    )

    # Run collision detector on synthetic project root
    findings = detect_collisions(project_root=tmp_path)

    rule_b_findings = [f for f in findings if f.detection_rule == RULE_B_CONFLICTING_CONDITIONS]
    rule_c_findings = [f for f in findings if f.detection_rule == RULE_C_OVERRIDE_INTERACTIONS]

    assert len(rule_b_findings) == 1
    assert rule_b_findings[0].collision_id == "COL-RULE_B-REQ-01-REQ-02-WEIGHT"
    assert rule_b_findings[0].category == CAT_BOUNDARY_OVERLAP
    assert "50.00" in rule_b_findings[0].explanation
    assert "70.00" in rule_b_findings[0].explanation

    assert len(rule_c_findings) == 1
    assert rule_c_findings[0].collision_id == "COL-RULE_C-REQ-01-REQ-02"
    assert rule_c_findings[0].category == CAT_OVERRIDE_INTERACTION
    assert rule_c_findings[0].severity == SEVERITY_HIGH  # due to mandatory hazmat constraint


# ---------------------------------------------------------------------------
# 10. CEWS integration test (Ground Truth Verification)
# ---------------------------------------------------------------------------

def test_cews_integration_collisions():
    """Verify CEWS collision detection flags known interactions with extracted evidence.

    Expected findings on CEWS:
    1. COL-RULE_B-REQ-03-REQ-07-AMOUNT: Boundary condition overlap (10,000 to 15,000).
    2. COL-RULE_C-REQ-03-REQ-07: REQ-07 bypasses REQ-03 manager approval in final_approval.
    3. COL-RULE_C-REQ-03-REQ-08: REQ-08 bypasses REQ-03 manager approval in final_approval.
    4. No spurious collision between REQ-01 and REQ-02 in validate_expense_input.
    """
    findings = detect_collisions(project_root=".")

    # 1. Check Rule B finding on amount
    col_b_req3_req7 = [
        f for f in findings
        if f.collision_id == "COL-RULE_B-REQ-03-REQ-07-AMOUNT"
    ]
    assert len(col_b_req3_req7) == 1
    f_b = col_b_req3_req7[0]
    assert f_b.category == CAT_BOUNDARY_OVERLAP
    assert f_b.severity == SEVERITY_MEDIUM
    assert f_b.confidence == CONFIDENCE_HIGH
    assert f_b.requires_human_review is True
    assert "10,000.00" in f_b.explanation
    assert "15,000.00" in f_b.explanation
    assert "amount" in f_b.evidence[2]

    # 2. Check Rule C finding between REQ-03 and REQ-07
    col_c_req3_req7 = [
        f for f in findings
        if f.collision_id == "COL-RULE_C-REQ-03-REQ-07"
    ]
    assert len(col_c_req3_req7) == 1
    f_c = col_c_req3_req7[0]
    assert f_c.category == CAT_OVERRIDE_INTERACTION
    assert f_c.severity == SEVERITY_HIGH  # preserves HR compliance
    assert f_c.confidence == CONFIDENCE_HIGH
    assert f_c.requires_human_review is True
    assert "final_approval" in f_c.related_functions

    # 3. Check Rule C finding between REQ-03 and REQ-08
    col_c_req3_req8 = [
        f for f in findings
        if f.collision_id == "COL-RULE_C-REQ-03-REQ-08"
    ]
    assert len(col_c_req3_req8) == 1

    # 4. Filter by requirement
    req3_findings = get_collisions_for_requirement(findings, "REQ-03")
    assert len(req3_findings) == 3

    req7_findings = get_collisions_for_requirement(findings, "REQ-07")
    assert len(req7_findings) == 2

    # 5. Check no false positive between REQ-01 and REQ-02
    req1_req2_findings = [
        f for f in findings
        if "REQ-01" in f.requirement_ids and "REQ-02" in f.requirement_ids
    ]
    assert len(req1_req2_findings) == 0


# ---------------------------------------------------------------------------
# 11. Serialization and Reporting
# ---------------------------------------------------------------------------

def test_serialization_and_reporting():
    """Serialization to dict, JSON, and text report must work cleanly."""
    finding = CollisionFinding(
        collision_id="COL-TEST-01",
        requirement_ids=["REQ-01", "REQ-02"],
        category=CAT_BOUNDARY_OVERLAP,
        severity=SEVERITY_MEDIUM,
        confidence=CONFIDENCE_HIGH,
        explanation="Test explanation.",
        evidence=["Evidence 1", "Evidence 2"],
        related_functions=["func_a", "func_b"],
        source_files=["file_a.py", "file_b.py"],
        line_numbers=[10, 20],
        detection_rule=RULE_B_CONFLICTING_CONDITIONS,
        requires_human_review=True,
    )

    # Test dictionary serialization
    d_list = findings_to_dict([finding])
    assert len(d_list) == 1
    assert d_list[0]["collision_id"] == "COL-TEST-01"
    assert d_list[0]["requires_human_review"] is True

    # Test JSON serialization
    json_str = findings_to_json([finding])
    parsed_json = json.loads(json_str)
    assert parsed_json[0]["category"] == CAT_BOUNDARY_OVERLAP

    # Test text report formatting
    report = format_collision_report([finding])
    assert "REQUIREMENT COLLISION DETECTION REPORT" in report
    assert "COL-TEST-01" in report
    assert "Test explanation." in report
    assert "Evidence 1" in report
