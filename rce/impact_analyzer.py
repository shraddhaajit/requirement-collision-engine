"""Change-Impact Analysis module for the Requirement Collision Engine (RCE) (Phase 5).

Traverses the NetworkX Requirement Knowledge Graph and AST dependency relationships
to deterministically identify directly and transitively affected requirements, functions,
modules, classes, and tests for a given requirement ID, code artifact, or collision finding.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

import networkx as nx

from rce.collision_detector import CollisionFinding
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
    _find_node_id,
    build_knowledge_graph,
    class_node_id,
    function_node_id,
    module_node_id,
    requirement_node_id,
    test_node_id,
)


# Impact levels
IMPACT_DIRECT = "direct"
IMPACT_TRANSITIVE = "transitive"


@dataclass
class ImpactedArtifact:
    """Represents a single software artifact impacted by a proposed change."""

    artifact_id: str
    artifact_type: str  # "requirement", "function", "method", "class", "module", "test"
    name: str
    impact_level: str  # "direct" or "transitive"
    depth: int  # 1 for direct, >= 2 for transitive
    reason: str
    traversal_path: List[str]
    is_inferred: bool = False
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize impacted artifact to dictionary."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "name": self.name,
            "impact_level": self.impact_level,
            "depth": self.depth,
            "reason": self.reason,
            "traversal_path": list(self.traversal_path),
            "is_inferred": self.is_inferred,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "metadata": dict(self.metadata),
        }


@dataclass
class ImpactReport:
    """Structured report containing direct and transitive change impacts."""

    target_id: str
    target_type: str  # "requirement", "function", "module", "class", "collision"
    direct_impacts: List[ImpactedArtifact]
    transitive_impacts: List[ImpactedArtifact]
    affected_requirements: List[str]
    affected_functions: List[str]
    affected_modules: List[str]
    affected_tests: List[str]
    summary: Dict[str, int]
    traversal_depth: int

    @property
    def total_impacted_count(self) -> int:
        """Total number of impacted artifacts (direct + transitive)."""
        return len(self.direct_impacts) + len(self.transitive_impacts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert impact report to JSON-serializable dictionary."""
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "total_impacted_count": self.total_impacted_count,
            "traversal_depth": self.traversal_depth,
            "summary": dict(self.summary),
            "affected_requirements": sorted(list(self.affected_requirements)),
            "affected_functions": sorted(list(self.affected_functions)),
            "affected_modules": sorted(list(self.affected_modules)),
            "affected_tests": sorted(list(self.affected_tests)),
            "direct_impacts": [a.to_dict() for a in self.direct_impacts],
            "transitive_impacts": [a.to_dict() for a in self.transitive_impacts],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize impact report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def _get_display_name(G: nx.DiGraph, nid: str) -> str:
    """Retrieve user-friendly name for a node in graph."""
    if nid not in G:
        return nid
    data = G.nodes[nid]
    return data.get("display_name") or data.get("name") or data.get("id") or nid


def _build_empty_report(target_id: str, target_type: str) -> ImpactReport:
    """Construct an empty ImpactReport when target or graph is unavailable."""
    return ImpactReport(
        target_id=target_id,
        target_type=target_type,
        direct_impacts=[],
        transitive_impacts=[],
        affected_requirements=[],
        affected_functions=[],
        affected_modules=[],
        affected_tests=[],
        summary={
            "total_impacted": 0,
            "direct_impacted": 0,
            "transitive_impacted": 0,
            "affected_requirements": 0,
            "affected_functions": 0,
            "affected_modules": 0,
            "affected_tests": 0,
        },
        traversal_depth=0,
    )


def _traverse_graph(
    G: nx.DiGraph,
    seed_nodes: List[Union[Tuple[str, str, str, bool], Tuple[str, str, str, bool, str]]],
    target_id: str,
    target_type: str,
    max_depth: int = 5,
) -> ImpactReport:
    """Execute BFS traversal on knowledge graph to classify direct and transitive impacts."""
    if not G or not seed_nodes:
        return _build_empty_report(target_id, target_type)

    visited: Dict[str, ImpactedArtifact] = {}
    # Queue items: (current_node_id, current_depth, traversal_path, reason, is_inferred, direction)
    queue: deque[Tuple[str, int, List[str], str, bool, str]] = deque()

    # Initialize queue with seed direct impacts (Hop 1)
    for item in seed_nodes:
        node_id, reason, edge_sym, is_inferred = item[0], item[1], item[2], item[3]
        direction = item[4] if len(item) > 4 else "both"
        if node_id not in G:
            continue
        ndata = G.nodes[node_id]
        atype = ndata.get("artifact_type", "unknown")
        dname = _get_display_name(G, node_id)
        path = [target_id, edge_sym, node_id]

        art = ImpactedArtifact(
            artifact_id=node_id,
            artifact_type=atype,
            name=dname,
            impact_level=IMPACT_DIRECT,
            depth=1,
            reason=reason,
            traversal_path=path,
            is_inferred=is_inferred,
            source_file=ndata.get("source_path") or ndata.get("file_path"),
            line_number=ndata.get("line_number"),
            metadata=dict(ndata),
        )
        visited[node_id] = art
        queue.append((node_id, 1, path, reason, is_inferred, direction))

    max_reached_depth = 1 if queue else 0

    # Process BFS
    while queue:
        curr_nid, curr_depth, curr_path, curr_reason, curr_inferred, curr_direction = queue.popleft()
        if curr_depth > max_reached_depth:
            max_reached_depth = curr_depth

        if curr_depth >= max_depth:
            continue

        next_depth = curr_depth + 1
        curr_data = G.nodes[curr_nid]
        curr_type = curr_data.get("artifact_type")

        neighbors_to_explore: List[Tuple[str, str, str, bool, str]] = []

        # 1. Traversal for Functions / Methods:
        if curr_type in (NODE_FUNCTION, NODE_METHOD):
            # A. Incoming CALLS: Callers that invoke this function (upstream impact)
            if curr_direction in ("both", "upstream"):
                for src, _, edata in G.in_edges(curr_nid, data=True):
                    if edata.get("relation") == EDGE_CALLS:
                        sdata = G.nodes[src]
                        stype = sdata.get("artifact_type")
                        if stype == NODE_TEST:
                            neighbors_to_explore.append((
                                src,
                                f"Test calls impacted function '{curr_data.get('name')}'",
                                "<--(CALLS)--",
                                True,
                                "upstream",
                            ))
                        else:
                            neighbors_to_explore.append((
                                src,
                                f"Calls impacted function '{curr_data.get('name')}' (caller dependency)",
                                "<--(CALLS)--",
                                True,
                                "upstream",
                            ))

            # B. Outgoing CALLS: Callees invoked by this function (downstream dependencies)
            if curr_direction in ("both", "downstream"):
                for _, tgt, edata in G.out_edges(curr_nid, data=True):
                    if edata.get("relation") == EDGE_CALLS:
                        neighbors_to_explore.append((
                            tgt,
                            f"Called by impacted function '{curr_data.get('name')}' (callee dependency)",
                            "--(CALLS)-->",
                            True,
                            "downstream",
                        ))

            # C. Outgoing VERIFIED_BY: Tests verifying this function
            for _, tgt, edata in G.out_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_VERIFIED_BY:
                    neighbors_to_explore.append((
                        tgt,
                        f"Verifies impacted function '{curr_data.get('name')}'",
                        "--(VERIFIED_BY)-->",
                        True,
                        "both",
                    ))

            # D. Incoming IMPLEMENTS: Requirements implemented by this function
            for src, _, edata in G.in_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_IMPLEMENTS:
                    rdata = G.nodes[src]
                    rname = rdata.get("id") or rdata.get("name") or src
                    neighbors_to_explore.append((
                        src,
                        f"Requirement '{rname}' implemented by impacted function '{curr_data.get('name')}'",
                        "<--(IMPLEMENTS)--",
                        True,
                        "both",
                    ))

            # E. Enclosing Module / Class
            for src, _, edata in G.in_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_CONTAINS:
                    mdata = G.nodes[src]
                    mtype = mdata.get("artifact_type")
                    neighbors_to_explore.append((
                        src,
                        f"Enclosing {mtype} containing impacted function '{curr_data.get('name')}'",
                        "<--(CONTAINS)--",
                        False,
                        "both",
                    ))

        # 2. Traversal for Classes:
        elif curr_type == NODE_CLASS:
            # Methods contained in class
            for _, tgt, edata in G.out_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_CONTAINS:
                    neighbors_to_explore.append((
                        tgt,
                        f"Method contained in impacted class '{curr_data.get('name')}'",
                        "--(CONTAINS)-->",
                        False,
                        "both",
                    ))

            # Requirements implemented by class
            for src, _, edata in G.in_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_IMPLEMENTS:
                    neighbors_to_explore.append((
                        src,
                        f"Requirement implemented by impacted class '{curr_data.get('name')}'",
                        "<--(IMPLEMENTS)--",
                        True,
                        "both",
                    ))

            # Enclosing Module
            for src, _, edata in G.in_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_CONTAINS:
                    neighbors_to_explore.append((
                        src,
                        f"Enclosing module of impacted class '{curr_data.get('name')}'",
                        "<--(CONTAINS)--",
                        False,
                        "both",
                    ))

        # 3. Traversal for Modules:
        elif curr_type == NODE_MODULE:
            if target_type == "module":
                # Contained functions and classes
                for _, tgt, edata in G.out_edges(curr_nid, data=True):
                    if edata.get("relation") == EDGE_CONTAINS:
                        tdata = G.nodes[tgt]
                        neighbors_to_explore.append((
                            tgt,
                            f"Contained in impacted module '{curr_data.get('name')}'",
                            "--(CONTAINS)-->",
                            False,
                            "both",
                        ))

                # Modules depending on this module (imports)
                for src, _, edata in G.in_edges(curr_nid, data=True):
                    if edata.get("relation") == EDGE_DEPENDS_ON:
                        neighbors_to_explore.append((
                            src,
                            f"Imports impacted module '{curr_data.get('name')}' (module dependency)",
                            "<--(DEPENDS_ON)--",
                            True,
                            "both",
                        ))

        # 4. Traversal for Requirements:
        elif curr_type == NODE_REQUIREMENT:
            if target_type in ("requirement", "collision"):
                # Implementation functions
                for _, tgt, edata in G.out_edges(curr_nid, data=True):
                    if edata.get("relation") == EDGE_IMPLEMENTS:
                        neighbors_to_explore.append((
                            tgt,
                            f"Implements impacted requirement '{curr_data.get('id')}'",
                            "--(IMPLEMENTS)-->",
                            False,
                            "both",
                        ))
            # Tests
            for _, tgt, edata in G.out_edges(curr_nid, data=True):
                if edata.get("relation") == EDGE_VERIFIED_BY:
                    neighbors_to_explore.append((
                        tgt,
                        f"Verifies impacted requirement '{curr_data.get('id')}'",
                        "--(VERIFIED_BY)-->",
                        False,
                        "both",
                    ))

        # Queue discovered unvisited neighbors
        for n_item in neighbors_to_explore:
            n_id, n_reason, n_edge, n_inferred = n_item[0], n_item[1], n_item[2], n_item[3]
            n_dir = n_item[4] if len(n_item) > 4 else "both"
            if n_id in visited or n_id not in G:
                continue

            ndata = G.nodes[n_id]
            ntype = ndata.get("artifact_type", "unknown")
            dname = _get_display_name(G, n_id)
            new_path = curr_path + [n_edge, n_id]

            artifact = ImpactedArtifact(
                artifact_id=n_id,
                artifact_type=ntype,
                name=dname,
                impact_level=IMPACT_TRANSITIVE,
                depth=next_depth,
                reason=n_reason,
                traversal_path=new_path,
                is_inferred=n_inferred or curr_inferred,
                source_file=ndata.get("source_path") or ndata.get("file_path"),
                line_number=ndata.get("line_number"),
                metadata=dict(ndata),
            )
            visited[n_id] = artifact
            queue.append((n_id, next_depth, new_path, n_reason, artifact.is_inferred, n_dir))

    # Separate direct and transitive impacts deterministically
    direct_list: List[ImpactedArtifact] = [
        art for art in visited.values() if art.impact_level == IMPACT_DIRECT
    ]
    transitive_list: List[ImpactedArtifact] = [
        art for art in visited.values() if art.impact_level == IMPACT_TRANSITIVE
    ]

    direct_list.sort(key=lambda a: (a.depth, a.artifact_type, a.artifact_id))
    transitive_list.sort(key=lambda a: (a.depth, a.artifact_type, a.artifact_id))

    all_artifacts = list(visited.values())

    # Collect grouped names
    affected_reqs: Set[str] = set()
    affected_fns: Set[str] = set()
    affected_mods: Set[str] = set()
    affected_tests: Set[str] = set()

    for a in all_artifacts:
        data = G.nodes.get(a.artifact_id, {})
        if a.artifact_type == NODE_REQUIREMENT:
            req_name = data.get("id") or a.name
            affected_reqs.add(req_name)
        elif a.artifact_type in (NODE_FUNCTION, NODE_METHOD):
            fn_name = data.get("qualified_name") or data.get("name") or a.name
            affected_fns.add(fn_name)
        elif a.artifact_type == NODE_MODULE:
            mod_name = data.get("name") or a.name
            affected_mods.add(mod_name)
        elif a.artifact_type == NODE_TEST:
            t_name = data.get("qualified_name") or data.get("name") or a.name
            affected_tests.add(t_name)

    summary = {
        "total_impacted": len(visited),
        "direct_impacted": len(direct_list),
        "transitive_impacted": len(transitive_list),
        "affected_requirements": len(affected_reqs),
        "affected_functions": len(affected_fns),
        "affected_modules": len(affected_mods),
        "affected_tests": len(affected_tests),
    }

    return ImpactReport(
        target_id=target_id,
        target_type=target_type,
        direct_impacts=direct_list,
        transitive_impacts=transitive_list,
        affected_requirements=sorted(list(affected_reqs)),
        affected_functions=sorted(list(affected_fns)),
        affected_modules=sorted(list(affected_mods)),
        affected_tests=sorted(list(affected_tests)),
        summary=summary,
        traversal_depth=max_reached_depth,
    )


def analyze_requirement_impact(
    req_id: str,
    graph: nx.DiGraph,
    max_depth: int = 5,
) -> ImpactReport:
    """Analyze change impact starting from a requirement identifier.

    Args:
        req_id: Requirement identifier (e.g., 'REQ-01', 'REQ-03').
        graph: NetworkX Requirement Knowledge Graph.
        max_depth: Maximum hops to traverse through the dependency graph.

    Returns:
        Structured ImpactReport.
    """
    norm_id = req_id.strip().upper()
    req_nid = requirement_node_id(norm_id)

    if not graph or req_nid not in graph:
        return _build_empty_report(norm_id, "requirement")

    seed_nodes: List[Tuple[str, str, str, bool]] = []

    # 1. Functions and classes directly implementing this requirement
    for _, tgt, edata in graph.out_edges(req_nid, data=True):
        if edata.get("relation") == EDGE_IMPLEMENTS:
            tdata = graph.nodes[tgt]
            ttype = tdata.get("artifact_type")
            tname = tdata.get("name", tgt)
            seed_nodes.append((
                tgt,
                f"Directly implements requirement {norm_id} via explicit traceability tag",
                "--(IMPLEMENTS)-->",
                False,
            ))
            # Enclosing module for directly implemented function
            for src, _, medata in graph.in_edges(tgt, data=True):
                if medata.get("relation") == EDGE_CONTAINS and graph.nodes[src].get("artifact_type") == NODE_MODULE:
                    mname = graph.nodes[src].get("name", src)
                    seed_nodes.append((
                        src,
                        f"Enclosing module of implementation {ttype} '{tname}'",
                        "<--(CONTAINS)--",
                        False,
                    ))

    # 2. Directly linked tests
    for _, tgt, edata in graph.out_edges(req_nid, data=True):
        if edata.get("relation") == EDGE_VERIFIED_BY:
            seed_nodes.append((
                tgt,
                f"Directly verifies requirement {norm_id} via explicit test trace tag",
                "--(VERIFIED_BY)-->",
                False,
            ))

    return _traverse_graph(
        G=graph,
        seed_nodes=seed_nodes,
        target_id=norm_id,
        target_type="requirement",
        max_depth=max_depth,
    )


def analyze_function_impact(
    function_id: str,
    graph: nx.DiGraph,
    max_depth: int = 5,
) -> ImpactReport:
    """Analyze change impact starting from a function or method.

    Args:
        function_id: Function qualified name, display name, or node ID.
        graph: NetworkX Requirement Knowledge Graph.
        max_depth: Maximum hops to traverse through the dependency graph.

    Returns:
        Structured ImpactReport.
    """
    if not graph:
        return _build_empty_report(function_id, "function")

    fn_nid = _find_node_id(graph, function_id)
    if fn_nid is None or fn_nid not in graph:
        return _build_empty_report(function_id, "function")

    fn_data = graph.nodes[fn_nid]
    fn_name = fn_data.get("name", function_id)
    seed_nodes: List[Tuple[str, str, str, bool]] = []

    # 1. Requirements directly implemented by this function
    for src, _, edata in graph.in_edges(fn_nid, data=True):
        if edata.get("relation") == EDGE_IMPLEMENTS:
            rdata = graph.nodes[src]
            r_id = rdata.get("id") or rdata.get("name") or src
            seed_nodes.append((
                src,
                f"Requirement '{r_id}' directly implemented by function '{fn_name}'",
                "<--(IMPLEMENTS)--",
                False,
            ))

    # 2. Enclosing module and class
    for src, _, edata in graph.in_edges(fn_nid, data=True):
        if edata.get("relation") == EDGE_CONTAINS:
            sdata = graph.nodes[src]
            stype = sdata.get("artifact_type")
            seed_nodes.append((
                src,
                f"Enclosing {stype} containing function '{fn_name}'",
                "<--(CONTAINS)--",
                False,
            ))

    # 3. Direct callers
    for src, _, edata in graph.in_edges(fn_nid, data=True):
        if edata.get("relation") == EDGE_CALLS:
            sdata = graph.nodes[src]
            if sdata.get("artifact_type") == NODE_TEST:
                seed_nodes.append((
                    src,
                    f"Test calls function '{fn_name}'",
                    "<--(CALLS)--",
                    True,
                    "upstream",
                ))
            else:
                seed_nodes.append((
                    src,
                    f"Calls function '{fn_name}' (direct caller)",
                    "<--(CALLS)--",
                    True,
                    "upstream",
                ))

    # 4. Direct callees
    for _, tgt, edata in graph.out_edges(fn_nid, data=True):
        if edata.get("relation") == EDGE_CALLS:
            seed_nodes.append((
                tgt,
                f"Called by function '{fn_name}' (direct callee)",
                "--(CALLS)-->",
                True,
                "downstream",
            ))

    # 5. Direct tests verifying this function
    for _, tgt, edata in graph.out_edges(fn_nid, data=True):
        if edata.get("relation") == EDGE_VERIFIED_BY:
            seed_nodes.append((
                tgt,
                f"Directly verifies function '{fn_name}'",
                "--(VERIFIED_BY)-->",
                True,
            ))

    return _traverse_graph(
        G=graph,
        seed_nodes=seed_nodes,
        target_id=fn_nid,
        target_type="function",
        max_depth=max_depth,
    )


def analyze_module_impact(
    module_name: str,
    graph: nx.DiGraph,
    max_depth: int = 5,
) -> ImpactReport:
    """Analyze change impact starting from a module.

    Args:
        module_name: Module name, path, or node ID.
        graph: NetworkX Requirement Knowledge Graph.
        max_depth: Maximum hops to traverse through the dependency graph.

    Returns:
        Structured ImpactReport.
    """
    if not graph:
        return _build_empty_report(module_name, "module")

    mod_nid = _find_node_id(graph, module_name)
    if mod_nid is None or mod_nid not in graph:
        return _build_empty_report(module_name, "module")

    mod_data = graph.nodes[mod_nid]
    mod_dname = mod_data.get("name", module_name)
    seed_nodes: List[Tuple[str, str, str, bool]] = []

    # 1. Contained functions, methods, and classes
    for _, tgt, edata in graph.out_edges(mod_nid, data=True):
        if edata.get("relation") == EDGE_CONTAINS:
            tdata = graph.nodes[tgt]
            ttype = tdata.get("artifact_type")
            tname = tdata.get("name", tgt)
            seed_nodes.append((
                tgt,
                f"{ttype.capitalize()} '{tname}' contained in module '{mod_dname}'",
                "--(CONTAINS)-->",
                False,
            ))

    # 2. Dependent modules (modules that import this module)
    for src, _, edata in graph.in_edges(mod_nid, data=True):
        if edata.get("relation") == EDGE_DEPENDS_ON:
            sname = graph.nodes[src].get("name", src)
            seed_nodes.append((
                src,
                f"Module '{sname}' imports '{mod_dname}' (direct module dependency)",
                "<--(DEPENDS_ON)--",
                True,
            ))

    return _traverse_graph(
        G=graph,
        seed_nodes=seed_nodes,
        target_id=mod_nid,
        target_type="module",
        max_depth=max_depth,
    )


def analyze_collision_impact(
    collision: Union[CollisionFinding, str],
    graph: nx.DiGraph,
    findings: Optional[List[CollisionFinding]] = None,
    max_depth: int = 5,
) -> ImpactReport:
    """Analyze change impact for resolving a detected requirement collision.

    Args:
        collision: CollisionFinding instance or collision ID string.
        graph: NetworkX Requirement Knowledge Graph.
        findings: Optional collection of CollisionFinding objects for lookup.
        max_depth: Maximum traversal depth.

    Returns:
        Unified ImpactReport covering all affected artifacts.
    """
    col_id: str
    involved_reqs: List[str] = []
    related_fns: List[str] = []

    if isinstance(collision, CollisionFinding):
        col_id = collision.collision_id
        involved_reqs = list(collision.requirement_ids)
        related_fns = list(collision.related_functions)
    else:
        col_id = str(collision).strip()
        matched = False
        if findings:
            for f in findings:
                if f.collision_id == col_id:
                    involved_reqs = list(f.requirement_ids)
                    related_fns = list(f.related_functions)
                    matched = True
                    break

        if not matched:
            # Infer requirements from collision_id format (e.g. COL-RULE_B-REQ-03-REQ-07-AMOUNT)
            parts = col_id.split("-")
            for idx in range(len(parts) - 1):
                if parts[idx].upper() == "REQ" and parts[idx + 1].isdigit():
                    involved_reqs.append(f"REQ-{parts[idx + 1]}")

    if not graph or (not involved_reqs and not related_fns):
        return _build_empty_report(col_id, "collision")

    seed_nodes: List[Tuple[str, str, str, bool]] = []

    # 1. Add involved requirements as direct starting scope
    for r_id in involved_reqs:
        r_nid = requirement_node_id(r_id)
        if r_nid in graph:
            seed_nodes.append((
                r_nid,
                f"Requirement '{r_id}' involved in collision {col_id}",
                "<--(COLLISION)--",
                False,
            ))
            # Add functions directly implementing this requirement
            for _, tgt, edata in graph.out_edges(r_nid, data=True):
                if edata.get("relation") == EDGE_IMPLEMENTS:
                    seed_nodes.append((
                        tgt,
                        f"Function implementing collided requirement {r_id}",
                        "--(IMPLEMENTS)-->",
                        False,
                    ))

    # 2. Add functions specifically related to the collision
    for fn_name in related_fns:
        fn_nid = _find_node_id(graph, fn_name)
        if fn_nid and fn_nid in graph:
            seed_nodes.append((
                fn_nid,
                f"Implementation gate '{fn_name}' evaluated in collision {col_id}",
                "<--(COLLISION_GATE)--",
                False,
            ))

    return _traverse_graph(
        G=graph,
        seed_nodes=seed_nodes,
        target_id=col_id,
        target_type="collision",
        max_depth=max_depth,
    )


def analyze_impact(
    target: Union[str, CollisionFinding],
    graph: Optional[nx.DiGraph] = None,
    project_root: Optional[Union[str, Path]] = None,
    max_depth: int = 5,
) -> ImpactReport:
    """Universal change-impact analyzer automatically resolving target type.

    Args:
        target: Requirement ID, function name, module name, or CollisionFinding.
        graph: Optional NetworkX Requirement Knowledge Graph.
        project_root: Optional project root path (auto-builds graph if graph is None).
        max_depth: Maximum hops to traverse through graph.

    Returns:
        Structured ImpactReport.
    """
    # 1. Resolve knowledge graph
    G = graph
    if G is None:
        p_root = project_root or "."
        try:
            G = build_knowledge_graph(project_root=p_root)
        except Exception:
            G = nx.DiGraph()

    # 2. Dispatch by target type
    if isinstance(target, CollisionFinding):
        return analyze_collision_impact(target, G, max_depth=max_depth)

    target_str = str(target).strip()

    # Check collision ID prefix
    if target_str.startswith("COL-"):
        return analyze_collision_impact(target_str, G, max_depth=max_depth)

    # Check requirement format
    norm_upper = target_str.upper()
    if norm_upper.startswith("REQ-") or norm_upper.startswith("REQ:"):
        return analyze_requirement_impact(norm_upper, G, max_depth=max_depth)

    # Check node in graph
    nid = _find_node_id(G, target_str)
    if nid and nid in G:
        ntype = G.nodes[nid].get("artifact_type")
        if ntype == NODE_REQUIREMENT:
            return analyze_requirement_impact(nid, G, max_depth=max_depth)
        elif ntype in (NODE_FUNCTION, NODE_METHOD):
            return analyze_function_impact(nid, G, max_depth=max_depth)
        elif ntype == NODE_MODULE:
            return analyze_module_impact(nid, G, max_depth=max_depth)

    # Default fallback: try function lookup, then module lookup
    fn_report = analyze_function_impact(target_str, G, max_depth=max_depth)
    if fn_report.total_impacted_count > 0:
        return fn_report

    mod_report = analyze_module_impact(target_str, G, max_depth=max_depth)
    if mod_report.total_impacted_count > 0:
        return mod_report

    return _build_empty_report(target_str, "unknown")


def report_to_dict(report: ImpactReport) -> Dict[str, Any]:
    """Convert an ImpactReport to a JSON-compatible dictionary."""
    return report.to_dict()


def report_to_json(report: ImpactReport, indent: int = 2) -> str:
    """Serialize an ImpactReport to formatted JSON."""
    return report.to_json(indent=indent)


def format_impact_report(report: ImpactReport) -> str:
    """Generate a clean human-readable change-impact analysis report."""
    lines: List[str] = [
        "=" * 70,
        "  CHANGE-IMPACT ANALYSIS REPORT",
        f"  Target: [{report.target_type}] {report.target_id}",
        "=" * 70,
        "Scope Summary:",
        f"  * Total Impacted Artifacts : {report.total_impacted_count}",
        f"  * Direct Impacts           : {len(report.direct_impacts)}",
        f"  * Transitive Impacts       : {len(report.transitive_impacts)}",
        f"  * Affected Requirements    : {len(report.affected_requirements)} ({', '.join(report.affected_requirements) if report.affected_requirements else 'none'})",
        f"  * Affected Functions       : {len(report.affected_functions)} ({', '.join(report.affected_functions[:5])}{'...' if len(report.affected_functions) > 5 else ''})",
        f"  * Affected Modules         : {len(report.affected_modules)} ({', '.join(report.affected_modules)})",
        f"  * Affected Tests           : {len(report.affected_tests)} ({', '.join(report.affected_tests[:4])}{'...' if len(report.affected_tests) > 4 else ''})",
        f"  * Traversal Depth          : {report.traversal_depth}",
        "-" * 70,
    ]

    if not report.direct_impacts and not report.transitive_impacts:
        lines.append("No impacted artifacts identified for this target.")
        lines.append("=" * 70)
        return "\n".join(lines)

    if report.direct_impacts:
        lines.append("Direct Impacts (Hop 1):")
        for idx, art in enumerate(report.direct_impacts, start=1):
            src_str = f" at {art.source_file}:{art.line_number}" if art.source_file and art.line_number else ""
            lines.append(f"  [{idx}] {art.name} ({art.artifact_type}){src_str}")
            lines.append(f"      Reason   : {art.reason}")
            lines.append(f"      Inferred : {'Yes' if art.is_inferred else 'No'}")

    if report.transitive_impacts:
        lines.append("\nTransitive Impacts (Hop 2+):")
        for idx, art in enumerate(report.transitive_impacts, start=1):
            path_str = " ".join(art.traversal_path)
            lines.append(f"  [{idx}] {art.name} ({art.artifact_type}, depth {art.depth})")
            lines.append(f"      Reason   : {art.reason}")
            lines.append(f"      Path     : {path_str}")
            lines.append(f"      Inferred : {'Yes' if art.is_inferred else 'No'}")

    if report.affected_tests:
        lines.append("\n" + "-" * 70)
        lines.append("Recommended Regression Verification Tests:")
        for t in report.affected_tests:
            lines.append(f"  * pytest -k {t.split(':')[-1]}")

    lines.append("=" * 70)
    return "\n".join(lines)
