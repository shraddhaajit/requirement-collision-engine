"""Unit and integration tests for RCE Phase 5: Change-Impact Analysis.

Covers:
1. Direct impact from a requirement to its explicitly linked function.
2. Transitive impact through a caller/callee or dependency chain.
3. Discovery of associated tests (explicit tag and inferred call).
4. Analysis starting from a module or function.
5. Collision-based analysis (via CollisionFinding and collision ID).
6. Correct direct versus transitive classification and depth bounds.
7. Stable output, deterministic ordering, and duplicate suppression.
8. Handling cycles and mutual recursions in the dependency graph.
9. Unknown IDs, missing nodes, and partial/empty inputs.
10. Synthetic non-CEWS Python project end-to-end impact analysis.
11. Regression coverage for existing knowledge graph behavior and real CEWS integration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import networkx as nx
import pytest

from rce.collision_detector import (
    CAT_BOUNDARY_OVERLAP,
    CAT_CONDITION_CONTRADICTION,
    CONFIDENCE_HIGH,
    SEVERITY_HIGH,
    CollisionFinding,
)
from rce.impact_analyzer import (
    IMPACT_DIRECT,
    IMPACT_TRANSITIVE,
    ImpactReport,
    ImpactedArtifact,
    analyze_collision_impact,
    analyze_function_impact,
    analyze_impact,
    analyze_module_impact,
    analyze_requirement_impact,
    format_impact_report,
    report_to_dict,
    report_to_json,
)
from rce.knowledge_graph import (
    EDGE_CALLS,
    EDGE_CONTAINS,
    EDGE_DEPENDS_ON,
    EDGE_IMPLEMENTS,
    EDGE_VERIFIED_BY,
    NODE_FUNCTION,
    NODE_MODULE,
    NODE_REQUIREMENT,
    NODE_TEST,
    build_knowledge_graph,
    function_node_id,
    get_artifacts_for_requirement,
    module_node_id,
    requirement_node_id,
    test_node_id,
)
from rce.requirement_parser import Requirement, parse_requirements


# ---------------------------------------------------------------------------
# Test Graph Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_graph() -> nx.DiGraph:
    """Construct an in-memory knowledge graph for testing impact traversal.

    Graph topology:
    - Requirements: REQ-01, REQ-02
    - Modules: billing, auth, tests_billing
    - Functions:
        * billing: calculate_total, apply_discount, helper_round
        * auth: check_permission
    - Tests:
        * tests_billing: test_calc_total, test_discount_rule
    - Call relations:
        * calculate_total --CALLS--> apply_discount
        * apply_discount --CALLS--> helper_round
        * calculate_total --CALLS--> check_permission
        * test_calc_total --CALLS--> calculate_total
    - Traceability relations:
        * REQ-01 --IMPLEMENTS--> calculate_total
        * REQ-01 --VERIFIED_BY--> test_calc_total
        * REQ-02 --IMPLEMENTS--> apply_discount
    """
    G = nx.DiGraph()

    # Modules
    m_bill = module_node_id("billing")
    m_auth = module_node_id("auth")
    m_test = module_node_id("tests_billing")
    G.add_node(m_bill, artifact_type=NODE_MODULE, name="billing", file_path="billing.py")
    G.add_node(m_auth, artifact_type=NODE_MODULE, name="auth", file_path="auth.py")
    G.add_node(m_test, artifact_type=NODE_MODULE, name="tests_billing", file_path="tests/test_billing.py")

    # Module dependencies (billing imports auth)
    G.add_edge(m_bill, m_auth, relation=EDGE_DEPENDS_ON)

    # Functions
    f_calc = function_node_id("billing:calculate_total")
    f_disc = function_node_id("billing:apply_discount")
    f_rnd = function_node_id("billing:helper_round")
    f_perm = function_node_id("auth:check_permission")

    G.add_node(f_calc, artifact_type=NODE_FUNCTION, name="calculate_total", qualified_name="billing:calculate_total", source_path="billing.py", line_number=10)
    G.add_node(f_disc, artifact_type=NODE_FUNCTION, name="apply_discount", qualified_name="billing:apply_discount", source_path="billing.py", line_number=30)
    G.add_node(f_rnd, artifact_type=NODE_FUNCTION, name="helper_round", qualified_name="billing:helper_round", source_path="billing.py", line_number=50)
    G.add_node(f_perm, artifact_type=NODE_FUNCTION, name="check_permission", qualified_name="auth:check_permission", source_path="auth.py", line_number=5)

    # Containment
    G.add_edge(m_bill, f_calc, relation=EDGE_CONTAINS)
    G.add_edge(m_bill, f_disc, relation=EDGE_CONTAINS)
    G.add_edge(m_bill, f_rnd, relation=EDGE_CONTAINS)
    G.add_edge(m_auth, f_perm, relation=EDGE_CONTAINS)

    # Calls
    G.add_edge(f_calc, f_disc, relation=EDGE_CALLS)
    G.add_edge(f_disc, f_rnd, relation=EDGE_CALLS)
    G.add_edge(f_calc, f_perm, relation=EDGE_CALLS)

    # Tests
    t_calc = test_node_id("tests_billing:test_calc_total")
    t_disc = test_node_id("tests_billing:test_discount_rule")
    G.add_node(t_calc, artifact_type=NODE_TEST, name="test_calc_total", qualified_name="tests_billing:test_calc_total", source_path="tests/test_billing.py", line_number=12)
    G.add_node(t_disc, artifact_type=NODE_TEST, name="test_discount_rule", qualified_name="tests_billing:test_discount_rule", source_path="tests/test_billing.py", line_number=25)
    G.add_edge(m_test, t_calc, relation=EDGE_CONTAINS)
    G.add_edge(m_test, t_disc, relation=EDGE_CONTAINS)

    # Test calls function
    G.add_edge(t_calc, f_calc, relation=EDGE_CALLS)

    # Requirements
    r1 = requirement_node_id("REQ-01")
    r2 = requirement_node_id("REQ-02")
    G.add_node(r1, artifact_type=NODE_REQUIREMENT, id="REQ-01", name="REQ-01: Calculate Billing", title="Calculate Billing")
    G.add_node(r2, artifact_type=NODE_REQUIREMENT, id="REQ-02", name="REQ-02: Discount Policy", title="Discount Policy")

    # Traceability links
    G.add_edge(r1, f_calc, relation=EDGE_IMPLEMENTS)
    G.add_edge(r1, t_calc, relation=EDGE_VERIFIED_BY)
    G.add_edge(r2, f_disc, relation=EDGE_IMPLEMENTS)
    G.add_edge(r2, t_disc, relation=EDGE_VERIFIED_BY)

    return G


# ---------------------------------------------------------------------------
# Test 1: Direct Impact from Requirement to Linked Function
# ---------------------------------------------------------------------------

def test_direct_impact_requirement_to_function(synthetic_graph: nx.DiGraph):
    """Verify that analyzing a requirement directly links to its implementation function."""
    report = analyze_requirement_impact("REQ-01", synthetic_graph)

    assert isinstance(report, ImpactReport)
    assert report.target_id == "REQ-01"
    assert report.target_type == "requirement"

    direct_ids = {a.artifact_id for a in report.direct_impacts}
    f_calc_id = function_node_id("billing:calculate_total")
    assert f_calc_id in direct_ids

    calc_art = next(a for a in report.direct_impacts if a.artifact_id == f_calc_id)
    assert calc_art.impact_level == IMPACT_DIRECT
    assert calc_art.depth == 1
    assert "Directly implements requirement REQ-01" in calc_art.reason
    assert calc_art.is_inferred is False
    assert any("calculate_total" in fn for fn in report.affected_functions)


# ---------------------------------------------------------------------------
# Test 2: Transitive Impact through Caller/Callee Chain
# ---------------------------------------------------------------------------

def test_transitive_impact_caller_callee_chain(synthetic_graph: nx.DiGraph):
    """Verify downstream callee dependencies and upstream caller dependencies."""
    report = analyze_requirement_impact("REQ-01", synthetic_graph, max_depth=5)

    f_calc = function_node_id("billing:calculate_total")
    f_disc = function_node_id("billing:apply_discount")
    f_rnd = function_node_id("billing:helper_round")
    f_perm = function_node_id("auth:check_permission")

    # f_calc is depth 1 (direct)
    assert any(a.artifact_id == f_calc and a.depth == 1 for a in report.direct_impacts)

    # f_disc (called by f_calc) is depth 2 (transitive)
    disc_art = next((a for a in report.transitive_impacts if a.artifact_id == f_disc), None)
    assert disc_art is not None
    assert disc_art.depth == 2
    assert disc_art.impact_level == IMPACT_TRANSITIVE
    assert disc_art.is_inferred is True
    assert "Called by" in disc_art.reason

    # f_perm (called by f_calc) is depth 2 (transitive)
    perm_art = next((a for a in report.transitive_impacts if a.artifact_id == f_perm), None)
    assert perm_art is not None
    assert perm_art.depth == 2

    # f_rnd (called by f_disc) is depth 3 (transitive chain: calc -> disc -> rnd)
    rnd_art = next((a for a in report.transitive_impacts if a.artifact_id == f_rnd), None)
    assert rnd_art is not None
    assert rnd_art.depth == 3
    assert len(rnd_art.traversal_path) >= 5

    # Check affected functions list includes all
    assert any("calculate_total" in fn for fn in report.affected_functions)
    assert any("apply_discount" in fn for fn in report.affected_functions)
    assert any("helper_round" in fn for fn in report.affected_functions)
    assert any("check_permission" in fn for fn in report.affected_functions)


# ---------------------------------------------------------------------------
# Test 3: Discovery of Associated Tests
# ---------------------------------------------------------------------------

def test_associated_tests_discovery(synthetic_graph: nx.DiGraph):
    """Verify discovery of tests linked explicitly or through call graph."""
    # REQ-01 has explicit test test_calc_total, and test_calc_total also calls calculate_total
    report = analyze_requirement_impact("REQ-01", synthetic_graph)

    t_calc = test_node_id("tests_billing:test_calc_total")
    assert any(a.artifact_id == t_calc and a.depth == 1 for a in report.direct_impacts)
    assert any("test_calc_total" in t for t in report.affected_tests)

    # Now check impact from function calculate_total
    fn_report = analyze_function_impact("calculate_total", synthetic_graph)
    assert any("test_calc_total" in t for t in fn_report.affected_tests)


# ---------------------------------------------------------------------------
# Test 4: Analysis Starting from Module or Function
# ---------------------------------------------------------------------------

def test_impact_starting_from_function(synthetic_graph: nx.DiGraph):
    """Verify analysis starting directly from a function name or node ID."""
    report = analyze_function_impact("apply_discount", synthetic_graph)

    assert report.target_type == "function"

    # 1. Direct callers: calculate_total calls apply_discount
    f_calc = function_node_id("billing:calculate_total")
    assert any(a.artifact_id == f_calc and a.depth == 1 for a in report.direct_impacts)

    # 2. Direct callees: apply_discount calls helper_round
    f_rnd = function_node_id("billing:helper_round")
    assert any(a.artifact_id == f_rnd and a.depth == 1 for a in report.direct_impacts)

    # 3. Implemented requirement: REQ-02 implements apply_discount
    assert "REQ-02" in report.affected_requirements

    # 4. Transitive caller impact: test_calc_total calls calculate_total
    t_calc = test_node_id("tests_billing:test_calc_total")
    assert any(a.artifact_id == t_calc and a.depth >= 2 for a in report.transitive_impacts)


def test_impact_starting_from_module(synthetic_graph: nx.DiGraph):
    """Verify analysis starting from an entire module."""
    report = analyze_module_impact("auth", synthetic_graph)

    assert report.target_type == "module"
    # Contained functions
    f_perm = function_node_id("auth:check_permission")
    assert any(a.artifact_id == f_perm and a.depth == 1 for a in report.direct_impacts)

    # Importing module: billing depends on auth
    m_bill = module_node_id("billing")
    assert any(a.artifact_id == m_bill and a.depth == 1 for a in report.direct_impacts)
    assert "billing" in report.affected_modules


# ---------------------------------------------------------------------------
# Test 5: Collision-Based Analysis
# ---------------------------------------------------------------------------

def test_collision_based_analysis_with_object(synthetic_graph: nx.DiGraph):
    """Verify analysis starting from a structured CollisionFinding instance."""
    finding = CollisionFinding(
        collision_id="COL-TEST-001",
        requirement_ids=["REQ-01", "REQ-02"],
        category=CAT_CONDITION_CONTRADICTION,
        severity=SEVERITY_HIGH,
        confidence=CONFIDENCE_HIGH,
        detection_rule="RULE_B_CONFLICTING_CONDITIONS",
        explanation="Contradicting discount conditions between billing requirements",
        evidence=["amount > 100", "amount <= 100"],
        source_files=["billing.py"],
        line_numbers=[10, 30],
        related_functions=["calculate_total", "apply_discount"],
    )

    report = analyze_collision_impact(finding, synthetic_graph)

    assert report.target_type == "collision"
    assert report.target_id == "COL-TEST-001"
    # Both requirements are represented
    assert "REQ-01" in report.affected_requirements
    assert "REQ-02" in report.affected_requirements
    # Related functions are represented
    assert any("calculate_total" in fn for fn in report.affected_functions)
    assert any("apply_discount" in fn for fn in report.affected_functions)


def test_collision_based_analysis_with_id_string(synthetic_graph: nx.DiGraph):
    """Verify analysis starting from a collision ID string."""
    col_str = "COL-RULE_B-REQ-01-REQ-02-DISCOUNT"
    report = analyze_collision_impact(col_str, synthetic_graph)

    assert report.target_type == "collision"
    assert report.target_id == col_str
    assert "REQ-01" in report.affected_requirements
    assert "REQ-02" in report.affected_requirements


# ---------------------------------------------------------------------------
# Test 6: Direct vs Transitive Classification
# ---------------------------------------------------------------------------

def test_direct_vs_transitive_classification(synthetic_graph: nx.DiGraph):
    """Confirm strict separation: depth 1 is direct, depth >= 2 is transitive."""
    report = analyze_requirement_impact("REQ-01", synthetic_graph, max_depth=5)

    for art in report.direct_impacts:
        assert art.impact_level == IMPACT_DIRECT
        assert art.depth == 1

    for art in report.transitive_impacts:
        assert art.impact_level == IMPACT_TRANSITIVE
        assert art.depth >= 2

    assert report.total_impacted_count == len(report.direct_impacts) + len(report.transitive_impacts)
    assert report.summary["total_impacted"] == report.total_impacted_count
    assert report.summary["direct_impacted"] == len(report.direct_impacts)
    assert report.summary["transitive_impacted"] == len(report.transitive_impacts)


# ---------------------------------------------------------------------------
# Test 7: Stable Output and Duplicate Suppression
# ---------------------------------------------------------------------------

def test_stable_output_and_duplicate_suppression(synthetic_graph: nx.DiGraph):
    """Ensure determinism and duplicate prevention across repeated runs and diamond graphs."""
    report1 = analyze_requirement_impact("REQ-01", synthetic_graph)
    report2 = analyze_requirement_impact("REQ-01", synthetic_graph)

    # Identical JSON serialization
    assert report1.to_dict() == report2.to_dict()
    assert report_to_json(report1) == report_to_json(report2)

    # Duplicate suppression check: every artifact ID is unique across report
    all_artifact_ids = [a.artifact_id for a in report1.direct_impacts] + [
        a.artifact_id for a in report1.transitive_impacts
    ]
    assert len(all_artifact_ids) == len(set(all_artifact_ids))


def test_diamond_dependency_no_duplicate():
    """Diamond graph (A -> B, A -> C, B -> D, C -> D) must visit D exactly once."""
    G = nx.DiGraph()
    for name in ["A", "B", "C", "D"]:
        nid = function_node_id(f"mod:{name}")
        G.add_node(nid, artifact_type=NODE_FUNCTION, name=name, qualified_name=f"mod:{name}")

    G.add_edge(function_node_id("mod:A"), function_node_id("mod:B"), relation=EDGE_CALLS)
    G.add_edge(function_node_id("mod:A"), function_node_id("mod:C"), relation=EDGE_CALLS)
    G.add_edge(function_node_id("mod:B"), function_node_id("mod:D"), relation=EDGE_CALLS)
    G.add_edge(function_node_id("mod:C"), function_node_id("mod:D"), relation=EDGE_CALLS)

    report = analyze_function_impact("mod:A", G)

    d_nid = function_node_id("mod:D")
    matching = [a for a in report.transitive_impacts if a.artifact_id == d_nid]
    assert len(matching) == 1
    assert matching[0].depth == 2


# ---------------------------------------------------------------------------
# Test 8: Cycles and Mutual Recursion Handling
# ---------------------------------------------------------------------------

def test_cycles_and_mutual_recursion_termination():
    """Graphs with cycles must terminate cleanly without infinite recursion."""
    G = nx.DiGraph()
    fa = function_node_id("cycle_mod:func_a")
    fb = function_node_id("cycle_mod:func_b")
    fc = function_node_id("cycle_mod:func_c")

    G.add_node(fa, artifact_type=NODE_FUNCTION, name="func_a", qualified_name="cycle_mod:func_a")
    G.add_node(fb, artifact_type=NODE_FUNCTION, name="func_b", qualified_name="cycle_mod:func_b")
    G.add_node(fc, artifact_type=NODE_FUNCTION, name="func_c", qualified_name="cycle_mod:func_c")

    # Mutual recursion cycle: fa <-> fb
    G.add_edge(fa, fb, relation=EDGE_CALLS)
    G.add_edge(fb, fa, relation=EDGE_CALLS)

    # Self loop: fc -> fc
    G.add_edge(fb, fc, relation=EDGE_CALLS)
    G.add_edge(fc, fc, relation=EDGE_CALLS)

    # Run analysis on func_a with large max_depth
    report = analyze_function_impact("cycle_mod:func_a", G, max_depth=10)

    assert report.total_impacted_count >= 2
    visited_ids = [a.artifact_id for a in report.direct_impacts + report.transitive_impacts]
    assert len(visited_ids) == len(set(visited_ids))  # No duplicates
    assert fb in visited_ids
    assert fc in visited_ids


# ---------------------------------------------------------------------------
# Test 9: Unknown IDs and Partial Inputs
# ---------------------------------------------------------------------------

def test_unknown_ids_and_empty_inputs(synthetic_graph: nx.DiGraph):
    """Graceful handling of non-existent IDs, empty graphs, and unknown targets."""
    # Unknown requirement
    r_empty = analyze_requirement_impact("REQ-9999", synthetic_graph)
    assert r_empty.total_impacted_count == 0
    assert r_empty.target_id == "REQ-9999"

    # Unknown function
    f_empty = analyze_function_impact("non_existent_func", synthetic_graph)
    assert f_empty.total_impacted_count == 0

    # Unknown module
    m_empty = analyze_module_impact("missing_module", synthetic_graph)
    assert m_empty.total_impacted_count == 0

    # Empty graph
    empty_graph = nx.DiGraph()
    rep = analyze_impact("REQ-01", empty_graph)
    assert rep.total_impacted_count == 0

    # General analyze_impact dispatch fallback
    un_rep = analyze_impact("random_unknown_token", synthetic_graph)
    assert un_rep.total_impacted_count == 0


# ---------------------------------------------------------------------------
# Test 10: Synthetic Non-CEWS Python Project
# ---------------------------------------------------------------------------

def test_synthetic_non_cews_project_impact(tmp_path: Path):
    """End-to-end impact analysis on a completely custom, non-CEWS Python project."""
    req_file = tmp_path / "requirements.md"
    req_file.write_text(
        "# Inventory System Specification\n\n"
        "### REQ-01 — Low Inventory Warning\n"
        "Must raise alert if stock < threshold.\n\n"
        "### REQ-02 — Restock Ordering\n"
        "Automatically trigger restock order when inventory alert is raised.\n",
        encoding="utf-8",
    )

    src_dir = tmp_path / "inventory"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    alert_py = src_dir / "alert.py"
    alert_py.write_text(
        '"""Alerting service.\n\n'
        'TRACE: REQ-01\n'
        '"""\n\n'
        'def check_low_stock(stock: int, threshold: int = 10) -> bool:\n'
        '    """Evaluate stock levels.\n\n'
        '    TRACE: REQ-01\n'
        '    """\n'
        '    if stock < threshold:\n'
        '        return True\n'
        '    return False\n',
        encoding="utf-8",
    )

    order_py = src_dir / "order.py"
    order_py.write_text(
        '"""Order processing.\n\n'
        'TRACE: REQ-02\n'
        '"""\n'
        'from inventory.alert import check_low_stock\n\n'
        'def trigger_restock(item_id: str, current_stock: int) -> bool:\n'
        '    """Place automatic restock.\n\n'
        '    TRACE: REQ-02\n'
        '    """\n'
        '    if check_low_stock(current_stock, 10):\n'
        '        return True\n'
        '    return False\n',
        encoding="utf-8",
    )

    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "__init__.py").write_text("", encoding="utf-8")
    test_py = test_dir / "test_inventory.py"
    test_py.write_text(
        '"""Inventory unit tests."""\n'
        'from inventory.alert import check_low_stock\n'
        'from inventory.order import trigger_restock\n\n'
        'def test_low_stock_detection():\n'
        '    """Verify alert.\n\n'
        '    TRACE: REQ-01\n'
        '    """\n'
        '    assert check_low_stock(5, 10) is True\n\n'
        'def test_restock_caller():\n'
        '    """Test trigger restock callers."""\n'
        '    assert trigger_restock("ITEM1", 4) is True\n',
        encoding="utf-8",
    )

    # Build knowledge graph
    reqs = parse_requirements(req_file)
    graph = build_knowledge_graph(requirements=reqs, project_root=tmp_path)
    assert graph.number_of_nodes() > 0

    # Analyze impact of modifying REQ-01
    report = analyze_impact("REQ-01", graph=graph)

    assert report.target_id == "REQ-01"
    assert report.total_impacted_count > 0

    # check_low_stock is directly impacted
    assert any("check_low_stock" in fn for fn in report.affected_functions)

    # trigger_restock calls check_low_stock, so it must be transitively impacted
    assert any("trigger_restock" in fn for fn in report.affected_functions)

    # tests are discovered
    assert any("test_low_stock_detection" in t for t in report.affected_tests)

    # Formatting verification
    fmt = format_impact_report(report)
    assert "CHANGE-IMPACT ANALYSIS REPORT" in fmt
    assert "REQ-01" in fmt
    assert "check_low_stock" in fmt


# ---------------------------------------------------------------------------
# Test 11: Real CEWS Integration and Regression Coverage
# ---------------------------------------------------------------------------

def test_cews_knowledge_graph_regression_and_impact():
    """Verify that existing graph behavior is preserved and test CEWS REQ-03 impact."""
    # Build live CEWS knowledge graph
    graph = build_knowledge_graph(project_root=".")
    assert graph.number_of_nodes() >= 30

    # 1. Existing graph query functions still work (regression coverage)
    req3_artifacts = get_artifacts_for_requirement(graph, "REQ-03")
    assert len(req3_artifacts) > 0

    # 2. Analyze impact of REQ-03 (Manager Approval requirement)
    report = analyze_requirement_impact("REQ-03", graph)

    assert report.target_id == "REQ-03"
    assert report.total_impacted_count > 0

    # Implementation function check_manager_approval should be directly impacted
    assert any("check_manager_approval" in fn for fn in report.affected_functions)
    assert any("approval" in mod for mod in report.affected_modules)

    # Associated tests should be identified
    assert len(report.affected_tests) > 0
    assert any("test_req03" in t or "approval" in t for t in report.affected_tests)

    # 3. Analyze impact starting from function 'check_manager_approval'
    fn_report = analyze_function_impact("check_manager_approval", graph)
    assert fn_report.total_impacted_count > 0
    assert "REQ-03" in fn_report.affected_requirements

    # 4. Analyze impact for real collision between REQ-03 and REQ-07
    col_report = analyze_impact("COL-RULE_B-REQ-03-REQ-07-AMOUNT", graph=graph)
    assert col_report.target_type == "collision"
    assert "REQ-03" in col_report.affected_requirements
    assert "REQ-07" in col_report.affected_requirements


# ---------------------------------------------------------------------------
# Test 12: Serialization and Reporting
# ---------------------------------------------------------------------------

def test_report_serialization(synthetic_graph: nx.DiGraph):
    """Verify to_dict, to_json, and format_impact_report serialization."""
    report = analyze_requirement_impact("REQ-01", synthetic_graph)

    r_dict = report_to_dict(report)
    assert isinstance(r_dict, dict)
    assert r_dict["target_id"] == "REQ-01"
    assert r_dict["target_type"] == "requirement"
    assert "direct_impacts" in r_dict
    assert "transitive_impacts" in r_dict
    assert "summary" in r_dict

    r_json = report_to_json(report)
    parsed = json.loads(r_json)
    assert parsed["target_id"] == "REQ-01"

    formatted = format_impact_report(report)
    assert "CHANGE-IMPACT ANALYSIS REPORT" in formatted
    assert "REQ-01" in formatted
    assert "Direct Impacts (Hop 1)" in formatted
