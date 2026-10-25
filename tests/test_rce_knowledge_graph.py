"""Tests for RCE Requirement Knowledge Graph (Phase 3)."""

import json
from pathlib import Path
import pytest
import networkx as nx

from rce.ast_analyzer import analyze_project, analyze_source
from rce.knowledge_graph import (
    EDGE_CALLS,
    EDGE_CONTAINS,
    EDGE_DEPENDS_ON,
    EDGE_HAS_CONDITION,
    EDGE_IMPLEMENTS,
    EDGE_VERIFIED_BY,
    NODE_CLASS,
    NODE_CONDITION,
    NODE_FUNCTION,
    NODE_METHOD,
    NODE_MODULE,
    NODE_REQUIREMENT,
    NODE_TEST,
    build_knowledge_graph,
    class_node_id,
    condition_node_id,
    function_node_id,
    get_artifacts_for_requirement,
    get_call_dependencies,
    get_conditions_for_function,
    get_requirements_for_artifact,
    get_requirements_for_function,
    get_tests_for_requirement,
    graph_to_dict,
    graph_to_json,
    module_node_id,
    requirement_node_id,
    test_node_id,
)
from rce.requirement_parser import Requirement, parse_requirements


def test_requirement_and_code_nodes_and_containment():
    """Verify creation of requirement, module, class, and function nodes with CONTAINS edges."""
    reqs = {
        "REQ-01": Requirement(id="REQ-01", title="Auth", description="User authentication.")
    }

    code = """
class UserService:
    def login(self, username, password):
        \"\"\"TRACE: REQ-01\"\"\"
        return True

def standalone_helper():
    pass
"""
    mod = analyze_source(code, file_path="auth/service.py", module_name="auth.service")
    analysis = analyze_project.__wrapped__ if hasattr(analyze_project, "__wrapped__") else None

    # Construct mock analysis container
    class MockAnalysis:
        modules = {"auth.service": mod}
        functions = mod.all_functions
        classes = mod.classes

    G = build_knowledge_graph(requirements=reqs, analysis=MockAnalysis(), include_tests=False)

    # Check nodes
    assert requirement_node_id("REQ-01") in G
    assert module_node_id("auth.service") in G
    assert class_node_id("auth.service:UserService") in G
    assert function_node_id("auth.service:UserService.login") in G
    assert function_node_id("auth.service:standalone_helper") in G

    # Check containment edges
    assert G.has_edge(module_node_id("auth.service"), class_node_id("auth.service:UserService"))
    assert G[module_node_id("auth.service")][class_node_id("auth.service:UserService")]["relation"] == EDGE_CONTAINS

    assert G.has_edge(class_node_id("auth.service:UserService"), function_node_id("auth.service:UserService.login"))
    assert G[class_node_id("auth.service:UserService")][function_node_id("auth.service:UserService.login")]["relation"] == EDGE_CONTAINS

    assert G.has_edge(module_node_id("auth.service"), function_node_id("auth.service:standalone_helper"))


def test_explicit_requirement_to_code_edges():
    """Verify typed IMPLEMENTS edge from requirement to tagged functions and classes."""
    reqs = {
        "REQ-01": Requirement(id="REQ-01", title="First", description="Desc 1"),
        "REQ-02": Requirement(id="REQ-02", title="Second", description="Desc 2"),
    }

    code = """
class DataModel:
    \"\"\"TRACE: REQ-01\"\"\"
    pass

def process():
    \"\"\"TRACE: REQ-01, REQ-02\"\"\"
    pass
"""
    mod = analyze_source(code, file_path="core.py", module_name="core")

    class MockAnalysis:
        modules = {"core": mod}
        functions = mod.all_functions
        classes = mod.classes

    G = build_knowledge_graph(requirements=reqs, analysis=MockAnalysis(), include_tests=False)

    req01_nid = requirement_node_id("REQ-01")
    req02_nid = requirement_node_id("REQ-02")
    cls_nid = class_node_id("core:DataModel")
    fn_nid = function_node_id("core:process")

    # REQ-01 -> DataModel
    assert G.has_edge(req01_nid, cls_nid)
    assert G[req01_nid][cls_nid]["relation"] == EDGE_IMPLEMENTS
    assert G[req01_nid][cls_nid]["explicit"] is True

    # REQ-01 -> process and REQ-02 -> process
    assert G.has_edge(req01_nid, fn_nid)
    assert G.has_edge(req02_nid, fn_nid)


def test_function_call_edges(tmp_path: Path):
    """Verify CALLS edges between caller and callee functions."""
    pkg = tmp_path / "app"
    pkg.mkdir()

    (pkg / "service.py").write_text(
        """
def entry_point():
    return helper()

def helper():
    return 42
""",
        encoding="utf-8",
    )

    analysis = analyze_project(tmp_path)
    G = build_knowledge_graph(analysis=analysis, include_tests=False)

    caller_nid = function_node_id("app.service:entry_point")
    callee_nid = function_node_id("app.service:helper")

    assert G.has_edge(caller_nid, callee_nid)
    assert G[caller_nid][callee_nid]["relation"] == EDGE_CALLS

    callees = get_call_dependencies(G, "app.service:entry_point", direction="callees")
    assert len(callees) == 1
    assert callees[0]["name"] == "helper"

    callers = get_call_dependencies(G, "app.service:helper", direction="callers")
    assert len(callers) == 1
    assert callers[0]["name"] == "entry_point"


def test_condition_nodes_and_edges():
    """Verify HAS_CONDITION edges connecting functions to extracted conditions."""
    code = """
def check_threshold(amount):
    if amount > 1000:
        return True
    return amount <= 500
"""
    mod = analyze_source(code, file_path="rules.py", module_name="rules")

    class MockAnalysis:
        modules = {"rules": mod}
        functions = mod.all_functions
        classes = mod.classes

    G = build_knowledge_graph(analysis=MockAnalysis(), include_conditions=True, include_tests=False)
    fn_nid = function_node_id("rules:check_threshold")

    conds = get_conditions_for_function(G, fn_nid)
    assert len(conds) >= 1
    assert any(c["condition_type"] == "if" and ">" in c["comparison_ops"] for c in conds)


def test_test_nodes_and_supported_traceability_links(tmp_path: Path):
    """Verify test discovery and distinction between explicit and inferred VERIFIED_BY links."""
    src = tmp_path / "app"
    src.mkdir()
    (src / "core.py").write_text(
        """
def compute():
    \"\"\"TRACE: REQ-01\"\"\"
    return 100
""",
        encoding="utf-8",
    )

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text(
        """
from app.core import compute

def test_compute_explicit():
    \"\"\"TRACE: REQ-01\"\"\"
    assert compute() == 100

def test_compute_untagged():
    assert compute() == 100
""",
        encoding="utf-8",
    )

    reqs = {"REQ-01": Requirement("REQ-01", "Compute", "Must compute value")}
    analysis = analyze_project(tmp_path, source_dirs=["app"])

    G = build_knowledge_graph(
        requirements=reqs,
        analysis=analysis,
        project_root=tmp_path,
        test_paths=[tests / "test_core.py"],
    )

    req_nid = requirement_node_id("REQ-01")
    fn_nid = function_node_id("app.core:compute")
    t_explicit_nid = test_node_id("tests.test_core:test_compute_explicit")
    t_untagged_nid = test_node_id("tests.test_core:test_compute_untagged")

    # Explicit trace link from requirement to test
    assert G.has_edge(req_nid, t_explicit_nid)
    assert G[req_nid][t_explicit_nid]["relation"] == EDGE_VERIFIED_BY
    assert G[req_nid][t_explicit_nid]["evidence"] == "explicit_trace_tag"

    # Untagged test must NOT have an explicit trace link to REQ-01
    assert not G.has_edge(req_nid, t_untagged_nid)

    # Both tests call compute(), so implementation artifact is verified by both
    assert G.has_edge(fn_nid, t_explicit_nid)
    assert G.has_edge(fn_nid, t_untagged_nid)
    assert G[fn_nid][t_untagged_nid]["evidence"] == "inferred_call"


def test_queries_in_both_directions():
    """Verify querying artifacts for a requirement and requirements for a function."""
    reqs = {
        "REQ-01": Requirement("REQ-01", "Auth", "Login"),
        "REQ-02": Requirement("REQ-02", "Audit", "Log"),
    }

    code = """
def multi_gate():
    \"\"\"TRACE: REQ-01, REQ-02\"\"\"
    pass
"""
    mod = analyze_source(code, file_path="gate.py", module_name="gate")

    class MockAnalysis:
        modules = {"gate": mod}
        functions = mod.all_functions
        classes = mod.classes

    G = build_knowledge_graph(requirements=reqs, analysis=MockAnalysis(), include_tests=False)

    # 1. Requirement -> Artifacts
    req01_artifacts = get_artifacts_for_requirement(G, "REQ-01")
    assert len(req01_artifacts) == 1
    assert req01_artifacts[0]["name"] == "multi_gate"

    # 2. Function -> Requirements (accepting node ID, qualified name, or function name)
    reqs_found1 = get_requirements_for_function(G, "function:gate:multi_gate")
    assert reqs_found1 == ["REQ-01", "REQ-02"]

    reqs_found2 = get_requirements_for_function(G, "gate:multi_gate")
    assert reqs_found2 == ["REQ-01", "REQ-02"]

    reqs_found3 = get_requirements_for_function(G, "multi_gate")
    assert reqs_found3 == ["REQ-01", "REQ-02"]


def test_graph_serialization():
    """Verify dictionary and JSON serialization of knowledge graph."""
    reqs = {"REQ-01": Requirement("REQ-01", "Title", "Desc")}
    code = "def f():\n    \"\"\"TRACE: REQ-01\"\"\"\n    pass"
    mod = analyze_source(code, file_path="f.py", module_name="f")

    class MockAnalysis:
        modules = {"f": mod}
        functions = mod.all_functions
        classes = mod.classes

    G = build_knowledge_graph(requirements=reqs, analysis=MockAnalysis(), include_tests=False)

    data = graph_to_dict(G)
    assert isinstance(data, dict)
    assert "nodes" in data
    assert "edges" in data
    assert data["node_count"] == G.number_of_nodes()
    assert data["edge_count"] == G.number_of_edges()

    json_str = graph_to_json(G)
    parsed = json.loads(json_str)
    assert parsed["node_count"] == data["node_count"]


def test_missing_or_malformed_traceability():
    """Verify graceful handling when trace tags reference undeclared requirements."""
    code = """
def mystery_function():
    \"\"\"TRACE: REQ-999\"\"\"
    pass

def normal_function():
    pass
"""
    mod = analyze_source(code, file_path="mod.py", module_name="mod")

    class MockAnalysis:
        modules = {"mod": mod}
        functions = mod.all_functions
        classes = mod.classes

    # Build without pre-declaring REQ-999
    G = build_knowledge_graph(requirements={}, analysis=MockAnalysis(), include_tests=False)

    # Must create a placeholder node for REQ-999 without crashing
    assert requirement_node_id("REQ-999") in G
    assert G.has_edge(requirement_node_id("REQ-999"), function_node_id("mod:mystery_function"))

    # Normal function has no requirement edges
    normal_reqs = get_requirements_for_function(G, "mod:normal_function")
    assert normal_reqs == []


def test_empty_or_partial_inputs():
    """Verify graph builder handles empty or partial inputs robustly."""
    # Completely empty
    G_empty = build_knowledge_graph()
    assert isinstance(G_empty, nx.DiGraph)
    assert G_empty.number_of_nodes() == 0

    # Only requirements
    reqs = {"REQ-01": Requirement("REQ-01", "T", "D")}
    G_reqs = build_knowledge_graph(requirements=reqs, include_tests=False)
    assert G_reqs.number_of_nodes() == 1
    assert requirement_node_id("REQ-01") in G_reqs

    # Nonexistent test path raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        build_knowledge_graph(test_paths=["nonexistent_test_file_xyz.py"])


def test_temporary_non_cews_project(tmp_path: Path):
    """Verify complete knowledge graph construction on a non-CEWS inventory project."""
    inv = tmp_path / "inventory"
    inv.mkdir()

    (inv / "catalog.py").write_text(
        """
class ProductCatalog:
    \"\"\"TRACE: REQ-101\"\"\"
    def add_product(self, sku, price):
        \"\"\"TRACE: REQ-101\"\"\"
        if price < 0:
            raise ValueError()
        return True
""",
        encoding="utf-8",
    )

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_catalog.py").write_text(
        """
from inventory.catalog import ProductCatalog

def test_add_valid_product():
    \"\"\"TRACE: REQ-101\"\"\"
    pc = ProductCatalog()
    assert pc.add_product("SKU1", 10.0) is True
""",
        encoding="utf-8",
    )

    reqs = {"REQ-101": Requirement("REQ-101", "Catalog Management", "Must add products")}
    analysis = analyze_project(tmp_path, source_dirs=["inventory"])

    G = build_knowledge_graph(
        requirements=reqs,
        analysis=analysis,
        project_root=tmp_path,
        test_paths=[tests / "test_catalog.py"],
    )

    # Verify nodes
    req_nid = requirement_node_id("REQ-101")
    assert req_nid in G
    assert class_node_id("inventory.catalog:ProductCatalog") in G
    assert function_node_id("inventory.catalog:ProductCatalog.add_product") in G
    assert test_node_id("tests.test_catalog:test_add_valid_product") in G

    # Verify bidirectional queries
    artifacts = get_artifacts_for_requirement(G, "REQ-101")
    artifact_names = [a.get("name") for a in artifacts]
    assert "ProductCatalog" in artifact_names
    assert "ProductCatalog.add_product" in artifact_names
    assert "test_add_valid_product" in artifact_names

    reqs_found = get_requirements_for_function(G, "ProductCatalog.add_product")
    assert reqs_found == ["REQ-101"]


def test_cews_full_knowledge_graph():
    """Verify knowledge graph construction and relationships on the authoritative CEWS system."""
    reqs = parse_requirements("requirements/requirements.md")
    analysis = analyze_project(".", source_dirs=["cews"])
    test_file = Path("tests/test_cews.py")

    G = build_knowledge_graph(
        requirements=reqs,
        analysis=analysis,
        project_root=".",
        test_paths=[test_file],
    )

    # 1. All 10 requirements must be present
    for i in range(1, 11):
        assert requirement_node_id(f"REQ-{i:02d}") in G

    # 2. final_approval implements REQ-04, REQ-07, REQ-08, REQ-10
    final_app_reqs = get_requirements_for_function(G, "cews.approval:final_approval")
    assert "REQ-04" in final_app_reqs
    assert "REQ-07" in final_app_reqs
    assert "REQ-08" in final_app_reqs
    assert "REQ-10" in final_app_reqs

    # 3. submit_expense implements all 10 requirements
    submit_reqs = get_requirements_for_function(G, "cews.expense:submit_expense")
    assert len(submit_reqs) == 10

    # 4. validate_budget has condition nodes
    conditions = get_conditions_for_function(G, "cews.approval:validate_budget")
    assert len(conditions) > 0

    # 5. Tests verify requirements explicitly
    req01_tests = get_tests_for_requirement(G, "REQ-01")
    assert any("test_req01_expense_submission" in t["name"] for t in req01_tests)

    # 6. Call dependencies for final_approval
    callees = get_call_dependencies(G, "cews.approval:final_approval", direction="callees")
    callee_names = [c["name"] for c in callees]
    assert "validate_budget" in callee_names
    assert "check_hr_compliance" in callee_names
    assert "check_manager_approval" in callee_names
