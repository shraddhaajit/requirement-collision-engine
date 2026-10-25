"""Requirement Knowledge Graph module for the Requirement Collision Engine (RCE).

Constructs a directed NetworkX graph connecting requirements, modules, classes,
functions, conditions, and tests using statically extracted artifacts and relationships.
Provides query and serialization APIs for bidirectional traceability exploration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

import networkx as nx

from rce.ast_analyzer import (
    DEFAULT_EXCLUDED_DIRS,
    ClassInfo,
    ConditionInfo,
    FunctionInfo,
    ModuleInfo,
    ProjectAnalysis,
    _resolve_project_dependencies,
    analyze_file,
    analyze_project,
)
from rce.requirement_parser import Requirement
from rce.traceability_extractor import TraceItem


# Edge relation types
EDGE_IMPLEMENTS = "IMPLEMENTS"
EDGE_CONTAINS = "CONTAINS"
EDGE_CALLS = "CALLS"
EDGE_HAS_CONDITION = "HAS_CONDITION"
EDGE_VERIFIED_BY = "VERIFIED_BY"
EDGE_DEPENDS_ON = "DEPENDS_ON"

# Artifact node types
NODE_REQUIREMENT = "requirement"
NODE_MODULE = "module"
NODE_CLASS = "class"
NODE_FUNCTION = "function"
NODE_METHOD = "method"
NODE_CONDITION = "condition"
NODE_TEST = "test"


def requirement_node_id(req_id: str) -> str:
    """Generate a stable node identifier for a requirement."""
    norm = req_id.strip().upper()
    return norm if norm.startswith("REQ:") else f"req:{norm}"


def module_node_id(module_name: str) -> str:
    """Generate a stable node identifier for a module."""
    norm = module_name.strip()
    return norm if norm.startswith("module:") else f"module:{norm}"


def class_node_id(qualified_name: str) -> str:
    """Generate a stable node identifier for a class."""
    norm = qualified_name.strip()
    return norm if norm.startswith("class:") else f"class:{norm}"


def function_node_id(qualified_name: str) -> str:
    """Generate a stable node identifier for a function or method."""
    norm = qualified_name.strip()
    return norm if norm.startswith("function:") else f"function:{norm}"


def condition_node_id(func_qualname: str, line_number: int, index: int) -> str:
    """Generate a stable node identifier for a condition."""
    return f"condition:{func_qualname}:L{line_number}:{index}"


def test_node_id(test_qualname: str) -> str:
    """Generate a stable node identifier for a test function."""
    norm = test_qualname.strip()
    return norm if norm.startswith("test:") else f"test:{norm}"


# Prevent pytest from mistaking test_node_id as a test function
test_node_id.__test__ = False


def _discover_test_files(
    project_root: Path,
    test_paths: Optional[Iterable[Union[str, Path]]] = None,
    excluded_dirs: Optional[Set[str]] = None,
) -> List[Path]:
    """Discover test source files from paths or by convention under project_root."""
    files: List[Path] = []
    active_excluded = set(DEFAULT_EXCLUDED_DIRS)
    if excluded_dirs:
        active_excluded.update(excluded_dirs)

    if test_paths is not None:
        for tp in test_paths:
            p = Path(tp)
            if not p.is_absolute():
                p = (project_root / p).resolve()
            if p.is_file() and p.suffix == ".py":
                files.append(p)
            elif p.is_dir():
                for root_dir, dirnames, filenames in os.walk(p):
                    dirnames[:] = [d for d in dirnames if d not in active_excluded and not d.startswith(".")]
                    for fname in sorted(filenames):
                        if fname.startswith("test_") or fname.endswith("_test.py"):
                            files.append(Path(root_dir) / fname)
            else:
                raise FileNotFoundError(f"Configured test path not found: {p}")
        return sorted(list(dict.fromkeys(files)), key=lambda p: str(p))

    # Default discovery: look for tests directory
    tests_dir = project_root / "tests"
    if tests_dir.is_dir():
        for root_dir, dirnames, filenames in os.walk(tests_dir):
            dirnames[:] = [d for d in dirnames if d not in active_excluded and not d.startswith(".")]
            for fname in sorted(filenames):
                if (fname.startswith("test_") or fname.endswith("_test.py")) and fname.endswith(".py"):
                    files.append(Path(root_dir) / fname)

    return sorted(list(dict.fromkeys(files)), key=lambda p: str(p))


def build_knowledge_graph(
    requirements: Optional[Union[Dict[str, Requirement], Iterable[Requirement]]] = None,
    trace_items: Optional[Iterable[TraceItem]] = None,
    analysis: Optional[ProjectAnalysis] = None,
    project_root: Optional[Union[str, Path]] = None,
    test_paths: Optional[Iterable[Union[str, Path]]] = None,
    include_conditions: bool = True,
    include_tests: bool = True,
    include_containment: bool = True,
) -> nx.DiGraph:
    """Construct a directed NetworkX Requirement Knowledge Graph.

    Args:
        requirements: Optional collection of Requirement objects.
        trace_items: Optional collection of TraceItem instances.
        analysis: Optional ProjectAnalysis result from AST analyzer.
        project_root: Optional root directory to auto-analyze if analysis is None.
        test_paths: Optional paths or directory of test files to analyze.
        include_conditions: Whether to include condition nodes and edges.
        include_tests: Whether to discover and link test functions.
        include_containment: Whether to include CONTAINS edges for modules/classes.

    Returns:
        Directed NetworkX graph representing the requirement knowledge graph.
    """
    G = nx.DiGraph()
    G.graph["name"] = "RequirementKnowledgeGraph"

    root_path = Path(project_root).resolve() if project_root is not None else Path(".").resolve()

    # 1. Add requirement nodes
    req_map: Dict[str, str] = {}  # req_id -> node_id
    if requirements:
        req_iterable = requirements.values() if isinstance(requirements, dict) else requirements
        for req in req_iterable:
            r_id = req.id.upper()
            nid = requirement_node_id(r_id)
            req_map[r_id] = nid
            G.add_node(
                nid,
                artifact_type=NODE_REQUIREMENT,
                id=r_id,
                title=req.title,
                description=req.description,
                display_name=f"{r_id} — {req.title}",
            )

    # 2. Add code entities from ProjectAnalysis (or auto-analyze project_root)
    proj_analysis = analysis
    if proj_analysis is None and project_root is not None:
        try:
            proj_analysis = analyze_project(project_root)
        except Exception:
            proj_analysis = None

    if proj_analysis is not None:
        # A. Modules & Module dependencies
        for mod_name, mod in proj_analysis.modules.items():
            mod_nid = module_node_id(mod_name)
            G.add_node(
                mod_nid,
                artifact_type=NODE_MODULE,
                name=mod_name,
                display_name=mod_name,
                source_path=mod.file_path,
            )

            # Module dependency edges (imports)
            for imp in mod.imports:
                if imp.module and imp.module in proj_analysis.modules:
                    target_mod_nid = module_node_id(imp.module)
                    if target_mod_nid != mod_nid:
                        G.add_edge(
                            mod_nid,
                            target_mod_nid,
                            relation=EDGE_DEPENDS_ON,
                            type=EDGE_DEPENDS_ON,
                        )

            # B. Classes
            for cls in mod.classes:
                cls_nid = class_node_id(cls.qualified_name)
                G.add_node(
                    cls_nid,
                    artifact_type=NODE_CLASS,
                    name=cls.name,
                    qualified_name=cls.qualified_name,
                    display_name=cls.name,
                    source_path=cls.file_path,
                    module_name=cls.module_name,
                    line_number=cls.line_number,
                    end_line_number=cls.end_line_number,
                    bases=cls.bases,
                    traceability_ids=cls.traceability_ids,
                )

                if include_containment:
                    G.add_edge(mod_nid, cls_nid, relation=EDGE_CONTAINS, type=EDGE_CONTAINS)

                # Class IMPLEMENTS edges
                for r_id in cls.traceability_ids:
                    r_nid = req_map.get(r_id, requirement_node_id(r_id))
                    if r_nid not in G:
                        G.add_node(
                            r_nid,
                            artifact_type=NODE_REQUIREMENT,
                            id=r_id,
                            title=f"Requirement {r_id}",
                            display_name=r_id,
                        )
                        req_map[r_id] = r_nid
                    G.add_edge(
                        r_nid,
                        cls_nid,
                        relation=EDGE_IMPLEMENTS,
                        type=EDGE_IMPLEMENTS,
                        explicit=True,
                    )

                # C. Class Methods
                for method in cls.methods:
                    m_nid = function_node_id(method.qualified_name)
                    G.add_node(
                        m_nid,
                        artifact_type=NODE_METHOD,
                        name=method.name,
                        qualified_name=method.qualified_name,
                        display_name=method.name,
                        source_path=method.file_path,
                        module_name=method.module_name,
                        line_number=method.line_number,
                        end_line_number=method.end_line_number,
                        parameters=method.parameters,
                        is_method=True,
                        traceability_ids=method.traceability_ids,
                    )

                    if include_containment:
                        G.add_edge(cls_nid, m_nid, relation=EDGE_CONTAINS, type=EDGE_CONTAINS)

                    for r_id in method.traceability_ids:
                        r_nid = req_map.get(r_id, requirement_node_id(r_id))
                        if r_nid not in G:
                            G.add_node(
                                r_nid,
                                artifact_type=NODE_REQUIREMENT,
                                id=r_id,
                                title=f"Requirement {r_id}",
                                display_name=r_id,
                            )
                            req_map[r_id] = r_nid
                        G.add_edge(
                            r_nid,
                            m_nid,
                            relation=EDGE_IMPLEMENTS,
                            type=EDGE_IMPLEMENTS,
                            explicit=True,
                        )

                    # Method conditions
                    if include_conditions:
                        for c_idx, cond in enumerate(method.conditions):
                            cond_nid = condition_node_id(method.qualified_name, cond.line_number, c_idx)
                            G.add_node(
                                cond_nid,
                                artifact_type=NODE_CONDITION,
                                display_name=f"{cond.condition_type}: {cond.expression}",
                                condition_type=cond.condition_type,
                                expression=cond.expression,
                                comparison_ops=cond.comparison_ops,
                                variables=cond.variables,
                                source_path=method.file_path,
                                line_number=cond.line_number,
                                end_line_number=cond.end_line_number,
                                function_qualified_name=method.qualified_name,
                            )
                            G.add_edge(
                                m_nid,
                                cond_nid,
                                relation=EDGE_HAS_CONDITION,
                                type=EDGE_HAS_CONDITION,
                            )

            # D. Top-level Functions
            for fn in mod.functions:
                fn_nid = function_node_id(fn.qualified_name)
                G.add_node(
                    fn_nid,
                    artifact_type=NODE_FUNCTION,
                    name=fn.name,
                    qualified_name=fn.qualified_name,
                    display_name=fn.name,
                    source_path=fn.file_path,
                    module_name=fn.module_name,
                    line_number=fn.line_number,
                    end_line_number=fn.end_line_number,
                    parameters=fn.parameters,
                    is_method=False,
                    traceability_ids=fn.traceability_ids,
                )

                if include_containment:
                    G.add_edge(mod_nid, fn_nid, relation=EDGE_CONTAINS, type=EDGE_CONTAINS)

                for r_id in fn.traceability_ids:
                    r_nid = req_map.get(r_id, requirement_node_id(r_id))
                    if r_nid not in G:
                        G.add_node(
                            r_nid,
                            artifact_type=NODE_REQUIREMENT,
                            id=r_id,
                            title=f"Requirement {r_id}",
                            display_name=r_id,
                        )
                        req_map[r_id] = r_nid
                    G.add_edge(
                        r_nid,
                        fn_nid,
                        relation=EDGE_IMPLEMENTS,
                        type=EDGE_IMPLEMENTS,
                        explicit=True,
                    )

                if include_conditions:
                    for c_idx, cond in enumerate(fn.conditions):
                        cond_nid = condition_node_id(fn.qualified_name, cond.line_number, c_idx)
                        G.add_node(
                            cond_nid,
                            artifact_type=NODE_CONDITION,
                            display_name=f"{cond.condition_type}: {cond.expression}",
                            condition_type=cond.condition_type,
                            expression=cond.expression,
                            comparison_ops=cond.comparison_ops,
                            variables=cond.variables,
                            source_path=fn.file_path,
                            line_number=cond.line_number,
                            end_line_number=cond.end_line_number,
                            function_qualified_name=fn.qualified_name,
                        )
                        G.add_edge(
                            fn_nid,
                            cond_nid,
                            relation=EDGE_HAS_CONDITION,
                            type=EDGE_HAS_CONDITION,
                        )

        # E. Inter-function CALLS edges
        for caller_fn in proj_analysis.functions:
            caller_nid = function_node_id(caller_fn.qualified_name)
            for call in caller_fn.calls:
                if call.is_resolved and call.resolved_target:
                    callee_nid = function_node_id(call.resolved_target)
                    # Check if target exists as function, method, or class
                    if callee_nid in G:
                        G.add_edge(
                            caller_nid,
                            callee_nid,
                            relation=EDGE_CALLS,
                            type=EDGE_CALLS,
                            line_number=call.line_number,
                        )
                    else:
                        cls_target_nid = class_node_id(call.resolved_target)
                        if cls_target_nid in G:
                            G.add_edge(
                                caller_nid,
                                cls_target_nid,
                                relation=EDGE_CALLS,
                                type=EDGE_CALLS,
                                line_number=call.line_number,
                            )

    # 3. Integrate additional TraceItems (if provided)
    if trace_items:
        for item in trace_items:
            # Locate corresponding function or class node
            target_nid = None
            for nid, data in G.nodes(data=True):
                if data.get("name") == item.name and (
                    data.get("source_path") == item.file_path
                    or data.get("source_path", "").endswith(item.file_path)
                ):
                    target_nid = nid
                    break

            if target_nid is not None:
                for r_id in item.requirement_ids:
                    r_nid = req_map.get(r_id, requirement_node_id(r_id))
                    if r_nid not in G:
                        G.add_node(
                            r_nid,
                            artifact_type=NODE_REQUIREMENT,
                            id=r_id,
                            title=f"Requirement {r_id}",
                            display_name=r_id,
                        )
                        req_map[r_id] = r_nid
                    if not G.has_edge(r_nid, target_nid):
                        G.add_edge(
                            r_nid,
                            target_nid,
                            relation=EDGE_IMPLEMENTS,
                            type=EDGE_IMPLEMENTS,
                            explicit=True,
                        )

    # 4. Discover and link Tests
    if include_tests and (test_paths is not None or project_root is not None):
        test_files = _discover_test_files(root_path, test_paths=test_paths)
        for test_file in test_files:
            try:
                test_mod = analyze_file(test_file, project_root=root_path)
            except Exception:
                continue

            if proj_analysis is not None:
                all_mods = dict(proj_analysis.modules)
                all_mods[test_mod.module_name] = test_mod
                _resolve_project_dependencies(all_mods)

            for tf in test_mod.functions:
                t_nid = test_node_id(tf.qualified_name)
                has_explicit_trace = bool(tf.traceability_ids)
                G.add_node(
                    t_nid,
                    artifact_type=NODE_TEST,
                    name=tf.name,
                    qualified_name=tf.qualified_name,
                    display_name=tf.name,
                    source_path=tf.file_path,
                    line_number=tf.line_number,
                    end_line_number=tf.end_line_number,
                    traceability_ids=tf.traceability_ids,
                    has_explicit_trace=has_explicit_trace,
                )

                # Link explicit requirement traces
                for r_id in tf.traceability_ids:
                    r_nid = req_map.get(r_id, requirement_node_id(r_id))
                    if r_nid not in G:
                        G.add_node(
                            r_nid,
                            artifact_type=NODE_REQUIREMENT,
                            id=r_id,
                            title=f"Requirement {r_id}",
                            display_name=r_id,
                        )
                        req_map[r_id] = r_nid
                    G.add_edge(
                        r_nid,
                        t_nid,
                        relation=EDGE_VERIFIED_BY,
                        type=EDGE_VERIFIED_BY,
                        evidence="explicit_trace_tag",
                    )

                # Link calls made by test to implementation functions
                for call in tf.calls:
                    if call.is_resolved and call.resolved_target:
                        target_fn_nid = function_node_id(call.resolved_target)
                        if target_fn_nid in G:
                            # Implementation artifact is verified by test
                            G.add_edge(
                                target_fn_nid,
                                t_nid,
                                relation=EDGE_VERIFIED_BY,
                                type=EDGE_VERIFIED_BY,
                                evidence="inferred_call",
                            )
                            # Test calls implementation artifact
                            G.add_edge(
                                t_nid,
                                target_fn_nid,
                                relation=EDGE_CALLS,
                                type=EDGE_CALLS,
                                line_number=call.line_number,
                            )

    return G


def _find_node_id(G: nx.DiGraph, query: str) -> Optional[str]:
    """Resolve an identifier, qualified name, or display name to an existing graph node ID."""
    if query in G:
        return query

    # Try prefixes
    for prefix in ("req:", "function:", "class:", "module:", "test:"):
        candidate = f"{prefix}{query}"
        if candidate in G:
            return candidate

    # Try matching attributes
    for nid, data in G.nodes(data=True):
        if data.get("qualified_name") == query or data.get("name") == query or data.get("id") == query:
            return nid

    return None


def get_artifacts_for_requirement(
    G: nx.DiGraph,
    req_id: str,
    artifact_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all implementation and test artifacts connected to a requirement.

    Args:
        G: NetworkX Requirement Knowledge Graph.
        req_id: Requirement identifier (e.g., 'REQ-01' or 'req:REQ-01').
        artifact_type: Optional filter by artifact_type ('function', 'method', 'class', 'test').

    Returns:
        List of node data dictionaries including node 'id'.
    """
    req_nid = requirement_node_id(req_id)
    if req_nid not in G:
        return []

    results: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    # Outgoing edges from requirement (IMPLEMENTS, VERIFIED_BY)
    for _, target, edge_data in G.out_edges(req_nid, data=True):
        rel = edge_data.get("relation")
        if rel in (EDGE_IMPLEMENTS, EDGE_VERIFIED_BY):
            if target not in seen:
                seen.add(target)
                target_data = dict(G.nodes[target])
                target_data["id"] = target
                target_data["relation"] = rel
                target_data["evidence"] = edge_data.get("evidence", "explicit")
                if artifact_type is None or target_data.get("artifact_type") == artifact_type:
                    results.append(target_data)

    # Also check incoming edges in case of reversed edge representation
    for source, _, edge_data in G.in_edges(req_nid, data=True):
        rel = edge_data.get("relation")
        if rel in (EDGE_IMPLEMENTS, EDGE_VERIFIED_BY):
            if source not in seen:
                seen.add(source)
                source_data = dict(G.nodes[source])
                source_data["id"] = source
                source_data["relation"] = rel
                source_data["evidence"] = edge_data.get("evidence", "explicit")
                if artifact_type is None or source_data.get("artifact_type") == artifact_type:
                    results.append(source_data)

    return sorted(results, key=lambda x: str(x.get("id")))


def get_requirements_for_artifact(G: nx.DiGraph, artifact_id: str) -> List[str]:
    """Retrieve all requirement IDs associated with a code entity or test.

    Args:
        G: NetworkX Requirement Knowledge Graph.
        artifact_id: Node ID, qualified name, or name of function/class/test.

    Returns:
        Sorted list of requirement ID strings (e.g. ['REQ-01', 'REQ-02']).
    """
    nid = _find_node_id(G, artifact_id)
    if nid is None or nid not in G:
        return []

    req_ids: Set[str] = set()

    # Check incoming edges from requirement nodes
    for source, _, edge_data in G.in_edges(nid, data=True):
        if edge_data.get("relation") in (EDGE_IMPLEMENTS, EDGE_VERIFIED_BY):
            src_data = G.nodes[source]
            if src_data.get("artifact_type") == NODE_REQUIREMENT:
                req_ids.add(src_data.get("id", source.replace("req:", "")))

    # Check outgoing edges to requirement nodes
    for _, target, edge_data in G.out_edges(nid, data=True):
        if edge_data.get("relation") in (EDGE_IMPLEMENTS, EDGE_VERIFIED_BY):
            tgt_data = G.nodes[target]
            if tgt_data.get("artifact_type") == NODE_REQUIREMENT:
                req_ids.add(tgt_data.get("id", target.replace("req:", "")))

    # Also check direct traceability_ids attribute on the node
    for r in G.nodes[nid].get("traceability_ids", []):
        req_ids.add(r)

    return sorted(list(req_ids))


def get_requirements_for_function(G: nx.DiGraph, function_id: str) -> List[str]:
    """Retrieve requirement IDs implemented by a function or method."""
    return get_requirements_for_artifact(G, function_id)


def get_tests_for_requirement(G: nx.DiGraph, req_id: str) -> List[Dict[str, Any]]:
    """Retrieve all test nodes verified by or associated with a requirement."""
    return get_artifacts_for_requirement(G, req_id, artifact_type=NODE_TEST)


def get_conditions_for_function(G: nx.DiGraph, function_id: str) -> List[Dict[str, Any]]:
    """Retrieve all condition nodes attached to a function or method."""
    nid = _find_node_id(G, function_id)
    if nid is None or nid not in G:
        return []

    conditions: List[Dict[str, Any]] = []
    for _, target, edge_data in G.out_edges(nid, data=True):
        if edge_data.get("relation") == EDGE_HAS_CONDITION:
            cond_data = dict(G.nodes[target])
            cond_data["id"] = target
            conditions.append(cond_data)

    return sorted(conditions, key=lambda c: (c.get("line_number", 0), c.get("id", "")))


def get_call_dependencies(
    G: nx.DiGraph, function_id: str, direction: str = "callees"
) -> List[Dict[str, Any]]:
    """Retrieve function call dependencies for a function (callees or callers).

    Args:
        G: NetworkX Requirement Knowledge Graph.
        function_id: Function identifier or qualified name.
        direction: 'callees' (functions called by this function) or 'callers' (functions that call this function).

    Returns:
        List of connected function node data dictionaries.
    """
    nid = _find_node_id(G, function_id)
    if nid is None or nid not in G:
        return []

    deps: List[Dict[str, Any]] = []

    if direction == "callees":
        for _, target, edge_data in G.out_edges(nid, data=True):
            if edge_data.get("relation") == EDGE_CALLS:
                data = dict(G.nodes[target])
                data["id"] = target
                data["call_line"] = edge_data.get("line_number")
                deps.append(data)
    elif direction == "callers":
        for source, _, edge_data in G.in_edges(nid, data=True):
            if edge_data.get("relation") == EDGE_CALLS:
                data = dict(G.nodes[source])
                data["id"] = source
                data["call_line"] = edge_data.get("line_number")
                deps.append(data)

    return sorted(deps, key=lambda d: str(d.get("id")))


def graph_to_dict(G: nx.DiGraph) -> Dict[str, Any]:
    """Serialize the NetworkX graph to a dictionary for JSON conversion."""
    nodes = [{"id": n, **data} for n, data in G.nodes(data=True)]
    edges = [{"source": u, "target": v, **data} for u, v, data in G.edges(data=True)]

    return {
        "metadata": dict(G.graph),
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "nodes": sorted(nodes, key=lambda x: str(x["id"])),
        "edges": sorted(edges, key=lambda x: (str(x["source"]), str(x["target"]))),
    }


def graph_to_json(G: nx.DiGraph, indent: Optional[int] = 2) -> str:
    """Serialize the NetworkX graph to a formatted JSON string."""
    return json.dumps(graph_to_dict(G), indent=indent)
