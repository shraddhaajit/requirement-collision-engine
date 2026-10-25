"""Integration layer for the Requirement Collision Engine (RCE) (Phase 6).

Orchestrates the complete static analysis pipeline:
1. Validates and resolves project roots and source paths.
2. Parses requirement markdown documents.
3. Performs AST analysis and dependency resolution.
4. Extracts traceability links.
5. Constructs the NetworkX Requirement Knowledge Graph.
6. Executes collision detection rules.
7. Performs change-impact analysis when requested.
8. Formats structured, serializable results with complete audit trails.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

import networkx as nx

from rce.ast_analyzer import (
    ASTAnalysisError,
    DEFAULT_EXCLUDED_DIRS,
    ProjectAnalysis,
    analyze_file,
    analyze_project,
    derive_module_name,
)
from rce.collision_detector import CollisionFinding, detect_collisions, format_collision_report
from rce.impact_analyzer import ImpactReport, analyze_impact, format_impact_report
from rce.knowledge_graph import (
    NODE_CLASS,
    NODE_CONDITION,
    NODE_FUNCTION,
    NODE_METHOD,
    NODE_MODULE,
    NODE_REQUIREMENT,
    NODE_TEST,
    build_knowledge_graph,
)
from rce.requirement_parser import Requirement, RequirementParseError, parse_requirements


# Engine status constants
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"


@dataclass
class EngineResult:
    """Structured result of an RCE analysis run."""

    project_root: str
    success: bool
    status: str  # "complete", "partial", "failed"
    requirements_file: Optional[str]
    requirements_count: int
    modules_count: int
    functions_count: int
    classes_count: int
    conditions_count: int
    graph_nodes_count: int
    graph_edges_count: int
    collisions_count: int
    findings: List[CollisionFinding]
    impact_report: Optional[ImpactReport] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert engine result to a JSON-compatible dictionary."""
        return {
            "project_root": self.project_root,
            "success": self.success,
            "status": self.status,
            "requirements_file": self.requirements_file,
            "statistics": {
                "requirements_count": self.requirements_count,
                "modules_count": self.modules_count,
                "functions_count": self.functions_count,
                "classes_count": self.classes_count,
                "conditions_count": self.conditions_count,
                "graph_nodes_count": self.graph_nodes_count,
                "graph_edges_count": self.graph_edges_count,
                "collisions_count": self.collisions_count,
            },
            "findings": [f.to_dict() for f in self.findings],
            "impact_report": self.impact_report.to_dict() if self.impact_report else None,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize engine result to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def _discover_requirements_file(project_root: Path) -> Optional[Path]:
    """Auto-detect requirements Markdown file in standard project locations."""
    candidate_rel_paths = [
        Path("requirements") / "requirements.md",
        Path("docs") / "requirements.md",
        Path("requirements.md"),
        Path("requirements") / "specification.md",
        Path("docs") / "specification.md",
    ]

    for rel in candidate_rel_paths:
        candidate = project_root / rel
        if candidate.is_file():
            return candidate

    # Search for markdown files under requirements/ or docs/
    for sub in ("requirements", "docs"):
        sub_dir = project_root / sub
        if sub_dir.is_dir():
            for p in sub_dir.glob("*.md"):
                if p.is_file():
                    return p

    # Check project root for any markdown file with 'req' in name
    for p in project_root.glob("*.md"):
        if "req" in p.name.lower():
            return p

    return None


def run_engine(
    project_root: Union[str, Path] = ".",
    requirements_path: Optional[Union[str, Path]] = None,
    source_dirs: Optional[Iterable[Union[str, Path]]] = None,
    impact_target: Optional[str] = None,
    max_depth: int = 5,
    include_conditions: bool = True,
    include_tests: bool = True,
    include_containment: bool = True,
) -> EngineResult:
    """Orchestrate the end-to-end RCE static analysis workflow.

    Args:
        project_root: Root directory of the project to analyze.
        requirements_path: Path to requirements Markdown file (auto-detected if None).
        source_dirs: Optional specific source directories to analyze.
        impact_target: Optional requirement ID, function, module, or collision ID for impact analysis.
        max_depth: Maximum BFS depth for impact analysis.
        include_conditions: Whether to extract AST branching conditions.
        include_tests: Whether to discover and link test functions.
        include_containment: Whether to model module and class containment edges.

    Returns:
        Structured EngineResult instance.
    """
    warnings: List[str] = []
    errors: List[str] = []

    # 1. Resolve and validate project root
    try:
        resolved_root = Path(project_root).resolve()
    except Exception as exc:
        return EngineResult(
            project_root=str(project_root),
            success=False,
            status=STATUS_FAILED,
            requirements_file=None,
            requirements_count=0,
            modules_count=0,
            functions_count=0,
            classes_count=0,
            conditions_count=0,
            graph_nodes_count=0,
            graph_edges_count=0,
            collisions_count=0,
            findings=[],
            errors=[f"Invalid project root path: {exc}"],
        )

    if not resolved_root.exists():
        return EngineResult(
            project_root=str(resolved_root),
            success=False,
            status=STATUS_FAILED,
            requirements_file=None,
            requirements_count=0,
            modules_count=0,
            functions_count=0,
            classes_count=0,
            conditions_count=0,
            graph_nodes_count=0,
            graph_edges_count=0,
            collisions_count=0,
            findings=[],
            errors=[f"Project root does not exist: {resolved_root}"],
        )

    if not resolved_root.is_dir():
        return EngineResult(
            project_root=str(resolved_root),
            success=False,
            status=STATUS_FAILED,
            requirements_file=None,
            requirements_count=0,
            modules_count=0,
            functions_count=0,
            classes_count=0,
            conditions_count=0,
            graph_nodes_count=0,
            graph_edges_count=0,
            collisions_count=0,
            findings=[],
            errors=[f"Project root is not a directory: {resolved_root}"],
        )

    # 2. Resolve requirements file
    resolved_req_file: Optional[Path] = None
    requirements: Dict[str, Requirement] = {}

    if requirements_path is not None:
        raw_p = Path(requirements_path)
        if raw_p.is_absolute():
            candidate = raw_p
        else:
            candidate = (resolved_root / raw_p).resolve()

        if candidate.is_file():
            resolved_req_file = candidate
        else:
            errors.append(f"Specified requirements file not found: {candidate}")
    else:
        resolved_req_file = _discover_requirements_file(resolved_root)

    if resolved_req_file is not None and resolved_req_file.is_file():
        try:
            requirements = parse_requirements(resolved_req_file)
        except RequirementParseError as exc:
            errors.append(f"Failed to parse requirements file '{resolved_req_file}': {exc}")
        except Exception as exc:
            errors.append(f"Unexpected error reading requirements file '{resolved_req_file}': {exc}")
    elif requirements_path is None:
        warnings.append("No requirements file specified or discovered; proceeding with AST and code analysis only.")

    # 3. Resolve source directories
    resolved_source_dirs: Optional[List[Path]] = None
    if source_dirs:
        resolved_source_dirs = []
        for s in source_dirs:
            sp = Path(s)
            p = sp if sp.is_absolute() else (resolved_root / sp).resolve()
            if p.is_dir():
                resolved_source_dirs.append(p)
            else:
                warnings.append(f"Source directory not found or is not a directory: {p}")

    # 4. Perform AST analysis
    try:
        analysis: ProjectAnalysis = analyze_project(
            project_root=resolved_root,
            source_dirs=resolved_source_dirs,
        )
    except Exception as exc:
        errors.append(f"AST project analysis encountered an unrecoverable error: {exc}")
        return EngineResult(
            project_root=str(resolved_root),
            success=False,
            status=STATUS_FAILED,
            requirements_file=str(resolved_req_file) if resolved_req_file else None,
            requirements_count=len(requirements),
            modules_count=0,
            functions_count=0,
            classes_count=0,
            conditions_count=0,
            graph_nodes_count=0,
            graph_edges_count=0,
            collisions_count=0,
            findings=[],
            warnings=warnings,
            errors=errors,
        )

    # Check for unparseable or syntax-errored files
    active_excluded = set(DEFAULT_EXCLUDED_DIRS)
    if not source_dirs:
        active_excluded.update({"tests", "test", "testing"})
        if (resolved_root / "cews").is_dir() and (resolved_root / "rce").is_dir():
            active_excluded.add("rce")
    syntax_errors: Dict[str, str] = {}
    scan_roots = resolved_source_dirs or [resolved_root]
    for scan_root in scan_roots:
        for current_dir, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [d for d in dirnames if d not in active_excluded and not d.startswith(".")]
            for fname in filenames:
                if fname.endswith(".py"):
                    if not source_dirs and (fname.startswith("test_") or fname.endswith("_test.py")):
                        continue
                    f_path = Path(current_dir) / fname
                    try:
                        rel = f_path.relative_to(resolved_root).as_posix()
                    except ValueError:
                        rel = f_path.as_posix()
                    mod_name = derive_module_name(rel)
                    if mod_name not in analysis.modules:
                        try:
                            analyze_file(f_path, project_root=resolved_root)
                        except ASTAnalysisError as exc:
                            syntax_errors[rel] = str(exc)
                            warnings.append(f"Syntax/AST error in '{rel}': {exc} (file skipped in analysis)")
                        except Exception as exc:
                            warnings.append(f"Could not read or parse file '{rel}': {exc}")

    # 5. Build Knowledge Graph
    try:
        graph: nx.DiGraph = build_knowledge_graph(
            requirements=requirements,
            analysis=analysis,
            project_root=resolved_root,
            include_containment=include_containment,
            include_conditions=include_conditions,
            include_tests=include_tests,
        )
    except Exception as exc:
        errors.append(f"Failed to construct knowledge graph: {exc}")
        graph = nx.DiGraph()

    # 6. Detect Requirement Collisions
    findings: List[CollisionFinding] = []
    if requirements or analysis.modules:
        try:
            findings = detect_collisions(
                requirements=requirements,
                analysis=analysis,
                graph=graph,
            )
        except Exception as exc:
            errors.append(f"Collision detection encountered an unexpected error: {exc}")

    # 7. Perform Change-Impact Analysis (if target requested)
    impact_report: Optional[ImpactReport] = None
    if impact_target:
        try:
            impact_report = analyze_impact(
                target=impact_target,
                graph=graph,
                project_root=resolved_root,
                max_depth=max_depth,
            )
            if impact_report.total_impacted_count == 0:
                warnings.append(
                    f"Impact target '{impact_target}' did not match any requirement, function, module, or collision."
                )
        except Exception as exc:
            errors.append(f"Change-impact analysis failed for target '{impact_target}': {exc}")

    # Determine status
    if errors and not analysis.modules and not requirements:
        status = STATUS_FAILED
        success = False
    elif errors or syntax_errors or not requirements:
        status = STATUS_PARTIAL
        success = True
    else:
        status = STATUS_COMPLETE
        success = True

    conditions_count = sum(len(fn.conditions) for fn in analysis.functions)

    return EngineResult(
        project_root=str(resolved_root),
        success=success,
        status=status,
        requirements_file=str(resolved_req_file) if resolved_req_file else None,
        requirements_count=len(requirements),
        modules_count=len(analysis.modules),
        functions_count=len(analysis.functions),
        classes_count=len(analysis.classes),
        conditions_count=conditions_count,
        graph_nodes_count=graph.number_of_nodes(),
        graph_edges_count=graph.number_of_edges(),
        collisions_count=len(findings),
        findings=findings,
        impact_report=impact_report,
        warnings=warnings,
        errors=errors,
        metadata={
            "syntax_error_count": len(syntax_errors),
        },
    )


def format_engine_result(result: EngineResult) -> str:
    """Format an EngineResult into a human-readable text report."""
    status_display = result.status.upper()
    lines: List[str] = [
        "=" * 72,
        "  REQUIREMENT COLLISION ENGINE (RCE) — ANALYSIS REPORT",
        "=" * 72,
        f"Project Root       : {result.project_root}",
        f"Analysis Status    : {status_display}",
        f"Requirements File  : {result.requirements_file or 'None (auto-detection found no file)'}",
        "",
        "Project Statistics:",
        f"  * Requirements   : {result.requirements_count}",
        f"  * Modules        : {result.modules_count}",
        f"  * Functions      : {result.functions_count}",
        f"  * Classes        : {result.classes_count}",
        f"  * Conditions     : {result.conditions_count}",
        f"  * Graph Nodes    : {result.graph_nodes_count}",
        f"  * Graph Edges    : {result.graph_edges_count}",
        f"  * Collisions     : {result.collisions_count}",
        "-" * 72,
    ]

    # Collision Findings Section
    if result.findings:
        lines.append(f"Collision Findings ({len(result.findings)} detected):")
        for idx, f in enumerate(result.findings, start=1):
            reqs_str = ", ".join(f.requirement_ids)
            funcs_str = ", ".join(f.related_functions) if f.related_functions else "none"
            lines.append(f"\n  [{idx}] {f.collision_id}")
            lines.append(f"      Category     : {f.category}")
            lines.append(f"      Severity     : {f.severity} | Confidence: {f.confidence}")
            lines.append(f"      Rule         : {f.detection_rule}")
            lines.append(f"      Requirements : {reqs_str}")
            lines.append(f"      Functions    : {funcs_str}")
            lines.append(f"      Explanation  : {f.explanation}")
            if f.evidence:
                lines.append("      Evidence     :")
                for ev in f.evidence[:3]:
                    lines.append(f"        - {ev}")
            lines.append(f"      Human Review : {'Required' if f.requires_human_review else 'Optional'}")
    else:
        lines.append("Collision Findings:")
        if result.status == STATUS_COMPLETE:
            lines.append(f"  No requirement collisions detected across {result.requirements_count} analyzed requirements.")
        elif result.status == STATUS_PARTIAL:
            lines.append("  Zero collision findings detected in parseable artifacts.")
            lines.append("  NOTE: Analysis was partial due to syntax errors or missing requirements.")
            lines.append("  Collision-free status cannot be guaranteed for unanalyzed artifacts.")
        else:
            lines.append("  Collision detection could not be performed due to fatal analysis errors.")

    # Impact Analysis Section (if requested)
    if result.impact_report:
        lines.append("\n" + "-" * 72)
        lines.append(format_impact_report(result.impact_report))

    # Warnings Section
    if result.warnings:
        lines.append("\n" + "-" * 72)
        lines.append("Analysis Warnings:")
        for w in result.warnings:
            lines.append(f"  [!] {w}")

    # Errors Section
    if result.errors:
        lines.append("\n" + "-" * 72)
        lines.append("Analysis Errors:")
        for e in result.errors:
            lines.append(f"  [X] {e}")

    lines.append("=" * 72)
    return "\n".join(lines)
