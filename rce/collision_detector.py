"""Requirement Collision Detection Engine for RCE (Phase 4).

Deterministically analyzes business requirements, AST conditions, and knowledge graphs
to detect potential requirement conflicts, boundary overlaps, and override/bypass interactions.
Produces explainable, structured CollisionFinding records with concrete evidence without executing code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

import networkx as nx

from rce.ast_analyzer import (
    ConditionInfo,
    FunctionInfo,
    ModuleInfo,
    ProjectAnalysis,
    _STANDARD_BUILTINS,
    analyze_project,
)
from rce.knowledge_graph import (
    EDGE_CALLS,
    EDGE_HAS_CONDITION,
    EDGE_IMPLEMENTS,
    NODE_FUNCTION,
    NODE_REQUIREMENT,
    build_knowledge_graph,
    get_artifacts_for_requirement,
    requirement_node_id,
)
from rce.requirement_parser import Requirement, parse_requirements


# Severity and Confidence constants with documented meanings
# Severity:
#   HIGH: Direct logical contradiction (e.g. x > 100 vs x <= 100 for the same action)
#         or critical override of an mandatory gate requiring immediate architectural attention.
#   MEDIUM: Boundary condition overlap or explicit override of a normal gate.
#   LOW: Shared decision condition requiring structural review.
#   WARNING: Inconclusive interaction with partial evidence.
# Confidence:
#   HIGH: Backed by both explicit requirement text and AST source conditions.
#   MEDIUM: Backed by AST source conditions on shared or compatible variables.
#   LOW: Inferred from semantic text markers or graph structure.
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
SEVERITY_WARNING = "WARNING"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

# Categories
CAT_CONDITION_CONTRADICTION = "CONDITION_CONTRADICTION"
CAT_BOUNDARY_OVERLAP = "BOUNDARY_CONDITION_COLLISION"
CAT_OVERRIDE_INTERACTION = "OVERRIDE_BYPASS_INTERACTION"
CAT_SHARED_CONDITION = "SHARED_CONDITION_OVERLAP"

# Rule names
RULE_A_SHARED_CONDITIONS = "Rule A — Shared implementation with overlapping conditions"
RULE_B_CONFLICTING_CONDITIONS = "Rule B — Conflicting conditions"
RULE_C_OVERRIDE_INTERACTIONS = "Rule C — Explicit exception or override interactions"

# Regex for parsing comparisons: var op literal OR literal op var
_CMP_VAR_LITERAL_REGEX = re.compile(
    r"^([a-zA-Z_][\w\.]*)\s*(==|!=|<=|>=|<|>)\s*([\'\"][^\'\"]*[\'\"]|-?\d+(?:\.\d+)?)$"
)
_CMP_LITERAL_VAR_REGEX = re.compile(
    r"^([\'\"][^\'\"]*[\'\"]|-?\d+(?:\.\d+)?)\s*(==|!=|<=|>=|<|>)\s*([a-zA-Z_][\w\.]*)$"
)
_METHOD_LOWER_CMP_REGEX = re.compile(
    r"^([a-zA-Z_][\w\.]*)\.lower\(\)\s*(==|!=)\s*([\'\"][^\'\"]*[\'\"])$"
)

# Semantic override / bypass keywords in requirement documentation
_OVERRIDE_KEYWORDS = {
    "override",
    "bypass",
    "bypasses",
    "bypassed",
    "bypassing",
    "emergency",
    "exception",
    "without the normal",
    "waive",
    "exempt",
    "exemption",
    "supersede",
}

# Semantic mandatory keywords in requirement documentation
_MANDATORY_KEYWORDS = {
    "mandatory",
    "must not bypass",
    "must not skip",
    "remains mandatory",
    "still applies",
    "shall not",
}


@dataclass
class CollisionFinding:
    """Structured record of a potential requirement collision."""

    collision_id: str
    requirement_ids: List[str]
    category: str
    severity: str
    confidence: str
    explanation: str
    evidence: List[str]
    related_functions: List[str]
    source_files: List[str]
    line_numbers: List[int]
    detection_rule: str
    requires_human_review: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to a JSON-compatible dictionary."""
        return {
            "collision_id": self.collision_id,
            "requirement_ids": sorted(list(self.requirement_ids)),
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "related_functions": sorted(list(self.related_functions)),
            "source_files": sorted(list(self.source_files)),
            "line_numbers": sorted(list(self.line_numbers)),
            "detection_rule": self.detection_rule,
            "requires_human_review": self.requires_human_review,
        }


@dataclass(frozen=True)
class _ParsedComparison:
    """Internal normalized representation of an atomic comparison."""

    base_var: str
    target_var: str
    operator: str
    literal_value: Union[float, str]
    is_numeric: bool
    raw_expression: str
    line_number: int
    source_file: str
    function_name: str
    requirement_ids: List[str]


def _normalize_var_name(raw_var: str) -> Tuple[str, str]:
    """Normalize variable expressions into (base_var, attribute_or_var_name).

    Examples:
        'expense.amount' -> ('expense', 'amount')
        'order.total' -> ('order', 'total')
        'score' -> ('', 'score')
    """
    parts = [p.strip().lower() for p in raw_var.split(".") if p.strip()]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    elif len(parts) == 1:
        return "", parts[0]
    return "", ""


def _parse_comparison(
    expr: str,
    line_number: int,
    source_file: str,
    function_name: str,
    requirement_ids: List[str],
) -> Optional[_ParsedComparison]:
    """Attempt to parse a condition string into a structured comparison."""
    trimmed = expr.strip()

    # Pattern 1: var.lower() == 'val'
    m_lower = _METHOD_LOWER_CMP_REGEX.match(trimmed)
    if m_lower:
        var_name, op, lit = m_lower.groups()
        base_v, target_v = _normalize_var_name(var_name)
        lit_val = lit.strip("'\"").lower()
        return _ParsedComparison(
            base_var=base_v,
            target_var=target_v,
            operator=op,
            literal_value=lit_val,
            is_numeric=False,
            raw_expression=trimmed,
            line_number=line_number,
            source_file=source_file,
            function_name=function_name,
            requirement_ids=requirement_ids,
        )

    # Pattern 2: var op literal
    m_var = _CMP_VAR_LITERAL_REGEX.match(trimmed)
    if m_var:
        var_name, op, lit = m_var.groups()
        base_v, target_v = _normalize_var_name(var_name)
        is_num = False
        lit_val: Union[float, str]
        try:
            lit_val = float(lit)
            is_num = True
        except ValueError:
            lit_val = lit.strip("'\"")

        return _ParsedComparison(
            base_var=base_v,
            target_var=target_v,
            operator=op,
            literal_value=lit_val,
            is_numeric=is_num,
            raw_expression=trimmed,
            line_number=line_number,
            source_file=source_file,
            function_name=function_name,
            requirement_ids=requirement_ids,
        )

    # Pattern 3: literal op var (flip operator)
    m_lit = _CMP_LITERAL_VAR_REGEX.match(trimmed)
    if m_lit:
        lit, op, var_name = m_lit.groups()
        base_v, target_v = _normalize_var_name(var_name)
        inv_map = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}
        inv_op = inv_map.get(op, op)
        is_num = False
        try:
            lit_val = float(lit)
            is_num = True
        except ValueError:
            lit_val = lit.strip("'\"")

        return _ParsedComparison(
            base_var=base_v,
            target_var=target_v,
            operator=inv_op,
            literal_value=lit_val,
            is_numeric=is_num,
            raw_expression=trimmed,
            line_number=line_number,
            source_file=source_file,
            function_name=function_name,
            requirement_ids=requirement_ids,
        )

    return None


def _build_call_index(
    analysis: ProjectAnalysis,
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build caller and callee maps and parameter names map from analysis."""
    callers: Dict[str, Set[str]] = {}
    callees: Dict[str, Set[str]] = {}
    params: Dict[str, Set[str]] = {}

    for fn in analysis.functions:
        fn_name = fn.name
        params[fn_name] = {p.lower() for p in fn.parameters}
        if fn_name not in callees:
            callees[fn_name] = set()

        for call in fn.calls:
            called = call.called_name.split(".")[-1]
            callees[fn_name].add(called)
            if called not in callers:
                callers[called] = set()
            callers[called].add(fn_name)

    return callers, callees, params


def _are_functions_related(
    c1: _ParsedComparison,
    c2: _ParsedComparison,
    analysis: ProjectAnalysis,
    callers: Dict[str, Set[str]],
    callees: Dict[str, Set[str]],
    params: Dict[str, Set[str]],
    graph: Optional[nx.DiGraph] = None,
) -> bool:
    """Check whether two comparisons originate from related functions.

    Prevents equating variables from unrelated functions.
    """
    if c1.function_name == c2.function_name and c1.source_file == c2.source_file:
        return True

    fn1 = c1.function_name
    fn2 = c2.function_name

    # Check caller-callee relationship
    if fn2 in callees.get(fn1, set()) or fn1 in callees.get(fn2, set()):
        return True

    # Check shared caller (e.g. final_approval calls both check_manager_approval and manager_override)
    fn1_callers = callers.get(fn1, set())
    fn2_callers = callers.get(fn2, set())
    if fn1_callers and fn2_callers and bool(fn1_callers & fn2_callers):
        return True

    # Check same source file and shared parameter / base variable
    if c1.source_file == c2.source_file:
        fn1_params = params.get(fn1, set())
        fn2_params = params.get(fn2, set())
        if fn1_params and fn2_params and bool(fn1_params & fn2_params):
            return True
        if c1.base_var and c2.base_var and c1.base_var == c2.base_var:
            return True

    # Check Knowledge Graph if available
    if graph is not None:
        try:
            for n1 in graph.nodes:
                if fn1 in str(n1):
                    for n2 in graph.nodes:
                        if fn2 in str(n2):
                            if graph.has_edge(n1, n2) or graph.has_edge(n2, n1):
                                return True
        except Exception:
            pass

    return False


def _check_rule_b_conflicting_conditions(
    analysis: ProjectAnalysis,
    req_map: Dict[str, Requirement],
    graph: Optional[nx.DiGraph] = None,
) -> List[CollisionFinding]:
    """Rule B: Identify contradictions or overlapping boundary conditions on compatible variables."""
    findings: List[CollisionFinding] = []
    seen_pairs: Set[Tuple[str, str, str]] = set()

    callers, callees, params = _build_call_index(analysis)

    # Collect parsed comparisons attached to production functions with traceability
    comparisons: List[_ParsedComparison] = []
    for fn in analysis.functions:
        if not fn.traceability_ids:
            continue
        # Skip test cases so we only analyze production business rules
        if fn.name.startswith("test_") or "test" in Path(fn.file_path).parts:
            continue

        for cond in fn.conditions:
            parsed = _parse_comparison(
                expr=cond.expression,
                line_number=cond.line_number,
                source_file=fn.file_path,
                function_name=fn.name,
                requirement_ids=fn.traceability_ids,
            )
            if parsed is not None:
                comparisons.append(parsed)

    # Compare pairs of parsed comparisons
    for i in range(len(comparisons)):
        for j in range(i + 1, len(comparisons)):
            c1 = comparisons[i]
            c2 = comparisons[j]

            # 1. Target variable must match exactly
            if not c1.target_var or not c2.target_var or c1.target_var != c2.target_var:
                continue

            # 2. If both base variables are non-empty, they must match
            if c1.base_var and c2.base_var and c1.base_var != c2.base_var:
                continue

            # 3. Functions must be related (do not equate variables from unrelated functions)
            if not _are_functions_related(c1, c2, analysis, callers, callees, params, graph):
                continue

            # 4. Must originate from different requirement sets
            req_set1 = set(c1.requirement_ids)
            req_set2 = set(c2.requirement_ids)
            diff_pairs = [
                (r1, r2)
                for r1 in req_set1
                for r2 in req_set2
                if r1 != r2
            ]
            if not diff_pairs:
                continue

            # Check numeric comparisons
            if c1.is_numeric and c2.is_numeric:
                val1 = float(c1.literal_value)
                val2 = float(c2.literal_value)
                op1 = c1.operator
                op2 = c2.operator

                # Subcase B.1: Direct contradiction
                # Opposing operators on the exact same threshold value (e.g. x > 100 vs x <= 100)
                is_contradiction = (
                    (op1 == ">" and op2 in ("<=", "<") and val1 == val2)
                    or (op2 == ">" and op1 in ("<=", "<") and val2 == val1)
                    or (op1 == ">=" and op2 == "<" and val1 == val2)
                    or (op2 == ">=" and op1 == "<" and val2 == val1)
                    or (op1 == "==" and op2 == "!=" and val1 == val2)
                    or (op2 == "==" and op1 == "!=" and val2 == val1)
                )

                # Subcase B.2: Opposing operators with overlapping boundary interval
                # e.g., (amount > 10000) and (amount < 15000) -> range (10000, 15000)
                is_overlap = False
                low_val, high_val = 0.0, 0.0
                if not is_contradiction:
                    if op1 in (">", ">=") and op2 in ("<", "<=") and val1 < val2:
                        is_overlap = True
                        low_val, high_val = val1, val2
                    elif op2 in (">", ">=") and op1 in ("<", "<=") and val2 < val1:
                        is_overlap = True
                        low_val, high_val = val2, val1

                if is_contradiction or is_overlap:
                    for r1, r2 in diff_pairs:
                        pair_key = tuple(sorted([r1, r2])) + (c1.target_var,)
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)

                        req_pair = sorted([r1, r2])
                        col_id = f"COL-RULE_B-{req_pair[0]}-{req_pair[1]}-{c1.target_var.upper()}"
                        cat = (
                            CAT_CONDITION_CONTRADICTION
                            if is_contradiction
                            else CAT_BOUNDARY_OVERLAP
                        )
                        sev = SEVERITY_HIGH if is_contradiction else SEVERITY_MEDIUM

                        if is_contradiction:
                            expl = (
                                f"Direct contradictory conditions on variable '{c1.target_var}': "
                                f"'{c1.raw_expression}' (via {r1}) vs '{c2.raw_expression}' (via {r2}). "
                                f"No single value can satisfy both conditions."
                            )
                        else:
                            expl = (
                                f"Boundary interval overlap on variable '{c1.target_var}' between "
                                f"{low_val:,.2f} and {high_val:,.2f}. "
                                f"Conditions '{c1.raw_expression}' ({r1}) and '{c2.raw_expression}' ({r2}) "
                                f"simultaneously evaluate to true in this range."
                            )

                        evidence = [
                            f"Condition 1 in {c1.source_file}:{c1.line_number} ({c1.function_name}): '{c1.raw_expression}'",
                            f"Condition 2 in {c2.source_file}:{c2.line_number} ({c2.function_name}): '{c2.raw_expression}'",
                            f"Target attribute: '{c1.target_var}'",
                        ]

                        findings.append(
                            CollisionFinding(
                                collision_id=col_id,
                                requirement_ids=req_pair,
                                category=cat,
                                severity=sev,
                                confidence=CONFIDENCE_HIGH,
                                explanation=expl,
                                evidence=evidence,
                                related_functions=sorted(list({c1.function_name, c2.function_name})),
                                source_files=sorted(list({c1.source_file, c2.source_file})),
                                line_numbers=sorted([c1.line_number, c2.line_number]),
                                detection_rule=RULE_B_CONFLICTING_CONDITIONS,
                                requires_human_review=True,
                            )
                        )

            # Check discrete equality/inequality contradiction
            elif not c1.is_numeric and not c2.is_numeric:
                is_discrete_conflict = (
                    (c1.operator == "==" and c2.operator == "!=" and c1.literal_value == c2.literal_value)
                    or (c1.operator == "!=" and c2.operator == "==" and c1.literal_value == c2.literal_value)
                    or (c1.operator == "==" and c2.operator == "==" and c1.literal_value != c2.literal_value and c1.function_name == c2.function_name)
                )
                if is_discrete_conflict:
                    for r1, r2 in diff_pairs:
                        pair_key = tuple(sorted([r1, r2])) + (c1.target_var,)
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)

                        req_pair = sorted([r1, r2])
                        col_id = f"COL-RULE_B-{req_pair[0]}-{req_pair[1]}-{c1.target_var.upper()}"
                        findings.append(
                            CollisionFinding(
                                collision_id=col_id,
                                requirement_ids=req_pair,
                                category=CAT_CONDITION_CONTRADICTION,
                                severity=SEVERITY_HIGH,
                                confidence=CONFIDENCE_HIGH,
                                explanation=(
                                    f"Contradictory discrete equality conditions on variable '{c1.target_var}': "
                                    f"'{c1.raw_expression}' ({r1}) contradicts '{c2.raw_expression}' ({r2})."
                                ),
                                evidence=[
                                    f"Condition 1 in {c1.source_file}:{c1.line_number} ({c1.function_name}): '{c1.raw_expression}'",
                                    f"Condition 2 in {c2.source_file}:{c2.line_number} ({c2.function_name}): '{c2.raw_expression}'",
                                    f"Target attribute: '{c1.target_var}'",
                                ],
                                related_functions=sorted(list({c1.function_name, c2.function_name})),
                                source_files=sorted(list({c1.source_file, c2.source_file})),
                                line_numbers=sorted([c1.line_number, c2.line_number]),
                                detection_rule=RULE_B_CONFLICTING_CONDITIONS,
                                requires_human_review=True,
                            )
                        )

    return findings


def _check_rule_c_override_interactions(
    analysis: ProjectAnalysis,
    req_map: Dict[str, Requirement],
    graph: Optional[nx.DiGraph],
) -> List[CollisionFinding]:
    """Rule C: Identify requirements specifying overrides or bypasses with code-level interaction."""
    findings: List[CollisionFinding] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    # 1. Identify candidate override requirements from text
    override_reqs: Dict[str, Tuple[Requirement, str, List[str], Set[str]]] = {}
    for r_id, req in req_map.items():
        text_corpus = f"{req.title} {req.description}".lower()
        matched_kw = [kw for kw in _OVERRIDE_KEYWORDS if kw in text_corpus]
        if not matched_kw:
            continue

        # Split text into lines/sentences to distinguish bypass clauses from preserved constraints
        lines = [line.strip().lower() for line in req.description.splitlines() if line.strip()]
        bypass_clauses: List[str] = []
        preserved_reqs: Set[str] = set()

        for line in lines:
            has_mandatory = any(mkw in line for mkw in _MANDATORY_KEYWORDS)
            has_bypass = any(bkw in line for bkw in _OVERRIDE_KEYWORDS)

            if has_bypass and not has_mandatory:
                bypass_clauses.append(line)

            # Record which requirements are explicitly preserved as mandatory
            for other_id, other_req in req_map.items():
                if other_id == r_id:
                    continue
                if has_mandatory and (other_id.lower() in line or other_req.title.lower() in line):
                    preserved_reqs.add(other_id)

        override_reqs[r_id] = (req, matched_kw[0], bypass_clauses, preserved_reqs)

    if not override_reqs:
        return []

    # Map each requirement ID to functions that trace it
    req_to_functions: Dict[str, List[FunctionInfo]] = {}
    for fn in analysis.functions:
        if fn.name.startswith("test_") or "test" in Path(fn.file_path).parts:
            continue
        for t_id in fn.traceability_ids:
            norm_t = t_id.upper()
            req_to_functions.setdefault(norm_t, []).append(fn)

    # 2. Inspect decision functions evaluating override conditions
    for fn in analysis.functions:
        if fn.name.startswith("test_") or "test" in Path(fn.file_path).parts:
            continue

        fn_reqs = set(fn.traceability_ids)
        fn_calls = {call.called_name.split(".")[-1] for call in fn.calls}

        for cond in fn.conditions:
            cond_expr_lower = cond.expression.lower()
            is_disjunctive_gate = any(
                op in cond_expr_lower for op in (" or ", "not (")
            )
            has_override_flag = any(
                w in cond_expr_lower
                for w in ("override", "bypass", "emergency", "is_override", "is_emergency")
            )

            # Test each candidate override requirement
            for ov_id, (ov_req, ov_kw, bypass_clauses, preserved_reqs) in override_reqs.items():
                ov_functions = {f.name for f in req_to_functions.get(ov_id, [])}
                relates_to_ov = (ov_id in fn_reqs) or bool(fn_calls & ov_functions)
                if not relates_to_ov:
                    continue

                # Ensure this specific condition evaluates the override
                cond_vars_lower = {v.lower() for v in cond.variables}
                _GENERIC_STOP_WORDS = {
                    "expense", "expenses", "request", "requests", "order", "orders",
                    "system", "rule", "rules", "item", "items", "data", "payload",
                    "validation", "approval", "check", "stage", "action", "status",
                    "process", "workflow", "condition", "conditions",
                }
                ov_title_words = {
                    w for w in ov_req.title.lower().split()
                    if len(w) > 2 and w not in _GENERIC_STOP_WORDS
                }
                cond_evaluates_ov = (
                    has_override_flag
                    or any(fn_ov.lower() in cond_expr_lower for fn_ov in ov_functions)
                    or any(any(tw in cv for tw in ov_title_words) for cv in cond_vars_lower)
                    or any(f"{ov_id.lower()}" in v for v in cond_vars_lower)
                )
                if not cond_evaluates_ov:
                    continue

                for other_id, other_req in req_map.items():
                    if other_id == ov_id:
                        continue
                    # Explicitly preserved constraints are NOT bypassed
                    if other_id in preserved_reqs:
                        continue

                    other_functions = {f.name for f in req_to_functions.get(other_id, [])}
                    relates_to_other = (other_id in fn_reqs) or bool(fn_calls & other_functions)

                    # Text evidence: bypass clause explicitly targets other rule
                    bypasses_other_in_text = any(
                        (other_id.lower() in clause or other_req.title.lower() in clause)
                        for clause in bypass_clauses
                    )

                    # Code evidence: condition evaluates target rule's gate/variable in disjunction
                    other_title_words = {
                        w for w in other_req.title.lower().split()
                        if len(w) > 2 and w not in _GENERIC_STOP_WORDS
                    }
                    condition_matches_other = (
                        bool(other_title_words & cond_vars_lower)
                        or any(f"{other_id.lower()}" in v for v in cond_vars_lower)
                        or any(fn_other.lower() in cond_expr_lower for fn_other in other_functions)
                    )

                    is_valid_interaction = False
                    reason = ""

                    if bypasses_other_in_text and relates_to_other and (is_disjunctive_gate or has_override_flag):
                        is_valid_interaction = True
                        reason = (
                            f"Requirement {ov_id} ('{ov_req.title}') specifies bypass of "
                            f"'{other_req.title}' ({other_id})"
                        )
                    elif condition_matches_other and is_disjunctive_gate and (has_override_flag or relates_to_ov):
                        is_valid_interaction = True
                        reason = (
                            f"Decision condition '{cond.expression}' in '{fn.name}' evaluates override "
                            f"alongside gate for '{other_req.title}' ({other_id})"
                        )

                    if is_valid_interaction:
                        pair_key = tuple(sorted([ov_id, other_id]))
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)

                        req_pair = sorted([ov_id, other_id])
                        col_id = f"COL-RULE_C-{req_pair[0]}-{req_pair[1]}"

                        has_mandatory_clause = any(mkw in ov_req.description.lower() for mkw in _MANDATORY_KEYWORDS)
                        sev = SEVERITY_HIGH if has_mandatory_clause else SEVERITY_MEDIUM

                        evidence = [
                            f"Requirement {ov_id} specifies override/bypass semantics: keyword '{ov_kw}'",
                            f"Requirement excerpt: '{ov_req.description.splitlines()[0]}'",
                            f"Decision gate in {fn.file_path}:{cond.line_number} ({fn.name}): '{cond.expression}'",
                        ]
                        if preserved_reqs:
                            evidence.append(
                                f"Mandatory boundary constraint noted in {ov_id}: explicitly preserves "
                                f"{', '.join(sorted(preserved_reqs))}."
                            )

                        expl = (
                            f"{reason}. Implementation gate '{fn.name}' evaluates override condition "
                            f"'{cond.expression}', altering the standard enforcement flow of {other_id}."
                        )

                        findings.append(
                            CollisionFinding(
                                collision_id=col_id,
                                requirement_ids=req_pair,
                                category=CAT_OVERRIDE_INTERACTION,
                                severity=sev,
                                confidence=CONFIDENCE_HIGH,
                                explanation=expl,
                                evidence=evidence,
                                related_functions=[fn.name],
                                source_files=[fn.file_path],
                                line_numbers=[cond.line_number],
                                detection_rule=RULE_C_OVERRIDE_INTERACTIONS,
                                requires_human_review=True,
                            )
                        )

    return findings


def _check_rule_a_shared_implementation_conditions(
    analysis: ProjectAnalysis,
    req_map: Dict[str, Requirement],
    existing_pairs: Set[Tuple[str, str]],
) -> List[CollisionFinding]:
    """Rule A: Identify requirements sharing implementation functions with overlapping conditions."""
    findings: List[CollisionFinding] = []

    # Map variables to conditions within functions
    for fn in analysis.functions:
        if fn.name.startswith("test_") or "test" in Path(fn.file_path).parts:
            continue
        req_ids = sorted(list(set(fn.traceability_ids)))
        if len(req_ids) < 2:
            continue

        # Skip wide orchestrators tracing 5 or more requirements unless specific compound conditions link them
        if len(req_ids) >= 5:
            continue

        # Look for multiple conditions testing the same variable/attribute
        var_to_conds: Dict[str, List[ConditionInfo]] = {}
        for cond in fn.conditions:
            tested_terms: Set[str] = set()
            for v in cond.variables:
                tested_terms.add(v.split(".")[-1].strip().lower())
            for attr in re.findall(r"\b[a-zA-Z_]\w*\.([a-zA-Z_]\w*)\b", cond.expression):
                tested_terms.add(attr.strip().lower())

            for term in tested_terms:
                var_to_conds.setdefault(term, []).append(cond)

        # Check if any substantive decision variable or attribute is tested across multiple distinct decision lines
        overlapping_vars = {
            v: conds
            for v, conds in var_to_conds.items()
            if len({c.line_number for c in conds}) >= 2
            and v not in _STANDARD_BUILTINS
            and v not in ("self", "cls", "expense", "request", "order", "item", "data", "payload", "none", "true", "false", "str", "int", "float", "bool")
            and v not in {p.lower() for p in fn.parameters}
        }

        if not overlapping_vars:
            # Shared code alone without overlapping conditions on specific variables is NOT sufficient evidence
            continue

        # For pairs of requirements sharing this function
        for i in range(len(req_ids)):
            for j in range(i + 1, len(req_ids)):
                r1 = req_ids[i]
                r2 = req_ids[j]
                pair_key = (r1, r2)
                if pair_key in existing_pairs:
                    continue

                existing_pairs.add(pair_key)
                col_id = f"COL-RULE_A-{r1}-{r2}-{fn.name}"

                relevant_cond_strs = [
                    f"Line {c.line_number}: {c.expression}"
                    for c in fn.conditions[:3]
                ]

                evidence = [
                    f"Shared implementation function: '{fn.qualified_name}' at {fn.file_path}:{fn.line_number}",
                    f"Function contains decision conditions with overlapping logic: {len(fn.conditions)} conditions present.",
                ] + relevant_cond_strs

                findings.append(
                    CollisionFinding(
                        collision_id=col_id,
                        requirement_ids=[r1, r2],
                        category=CAT_SHARED_CONDITION,
                        severity=SEVERITY_LOW,
                        confidence=CONFIDENCE_MEDIUM,
                        explanation=(
                            f"Requirements {r1} and {r2} share implementation function '{fn.name}', "
                            f"which contains branching decision conditions requiring architectural review."
                        ),
                        evidence=evidence,
                        related_functions=[fn.name],
                        source_files=[fn.file_path],
                        line_numbers=[fn.line_number],
                        detection_rule=RULE_A_SHARED_CONDITIONS,
                        requires_human_review=True,
                    )
                )

    return findings


def detect_collisions(
    requirements: Optional[Union[Dict[str, Requirement], Iterable[Requirement]]] = None,
    analysis: Optional[ProjectAnalysis] = None,
    graph: Optional[nx.DiGraph] = None,
    project_root: Optional[Union[str, Path]] = None,
    rules: Optional[Iterable[str]] = None,
) -> List[CollisionFinding]:
    """Detect potential requirement collisions and inconsistencies deterministically.

    Args:
        requirements: Optional collection or dictionary of Requirement instances.
        analysis: Optional ProjectAnalysis result from AST analyzer.
        graph: Optional NetworkX Requirement Knowledge Graph.
        project_root: Optional project root path (auto-analyzes if analysis/requirements are missing).
        rules: Optional subset of rules to run (defaults to all: Rule A, Rule B, Rule C).

    Returns:
        Deduplicated list of structured CollisionFinding objects.
    """
    # 1. Normalize requirements
    req_map: Dict[str, Requirement] = {}
    if requirements is not None:
        if isinstance(requirements, dict):
            req_map = {k.upper(): v for k, v in requirements.items()}
        else:
            req_map = {r.id.upper(): r for r in requirements}
    elif project_root is not None:
        p_req = Path(project_root) / "requirements" / "requirements.md"
        if p_req.is_file():
            try:
                req_map = parse_requirements(p_req)
            except Exception:
                pass

    # 2. Normalize AST analysis
    proj_analysis = analysis
    if proj_analysis is None and project_root is not None:
        try:
            proj_analysis = analyze_project(project_root)
        except Exception:
            proj_analysis = None

    # If neither analysis nor requirements are available, return empty list safely
    if proj_analysis is None or not proj_analysis.functions:
        return []

    # 3. Determine active rules
    active_rules = set(rules) if rules is not None else {"RULE_A", "RULE_B", "RULE_C"}
    findings: List[CollisionFinding] = []

    # Track seen (rule, r1, r2) tuples to guarantee duplicate suppression
    recorded_keys: Set[Tuple[str, str, str]] = set()

    # Rule B: Conflicting conditions (highest precision)
    if "RULE_B" in active_rules or any("RULE_B" in r for r in active_rules):
        b_findings = _check_rule_b_conflicting_conditions(proj_analysis, req_map, graph)
        for f in b_findings:
            key = (f.detection_rule, f.requirement_ids[0], f.requirement_ids[1])
            if key not in recorded_keys:
                recorded_keys.add(key)
                findings.append(f)

    # Rule C: Explicit exception / override interactions
    if "RULE_C" in active_rules or any("RULE_C" in r for r in active_rules):
        c_findings = _check_rule_c_override_interactions(proj_analysis, req_map, graph)
        for f in c_findings:
            key = (f.detection_rule, f.requirement_ids[0], f.requirement_ids[1])
            if key not in recorded_keys:
                recorded_keys.add(key)
                findings.append(f)

    # Rule A: Shared implementation conditions
    if "RULE_A" in active_rules or any("RULE_A" in r for r in active_rules):
        existing_pairs = {(f.requirement_ids[0], f.requirement_ids[1]) for f in findings}
        a_findings = _check_rule_a_shared_implementation_conditions(
            proj_analysis, req_map, existing_pairs
        )
        for f in a_findings:
            key = (f.detection_rule, f.requirement_ids[0], f.requirement_ids[1])
            if key not in recorded_keys:
                recorded_keys.add(key)
                findings.append(f)

    # Sort findings deterministically by collision_id
    findings.sort(key=lambda f: f.collision_id)
    return findings


def get_collisions_for_requirement(
    findings: List[CollisionFinding], req_id: str
) -> List[CollisionFinding]:
    """Filter collision findings involving a specific requirement ID."""
    norm = req_id.strip().upper()
    return [f for f in findings if norm in f.requirement_ids]


def findings_to_dict(findings: List[CollisionFinding]) -> List[Dict[str, Any]]:
    """Convert a list of CollisionFindings to serializable dictionaries."""
    return [f.to_dict() for f in findings]


def findings_to_json(findings: List[CollisionFinding], indent: int = 2) -> str:
    """Serialize a list of CollisionFindings to formatted JSON."""
    return json.dumps(findings_to_dict(findings), indent=indent)


def format_collision_report(findings: List[CollisionFinding]) -> str:
    """Generate a clean human-readable summary report of collision findings."""
    if not findings:
        return "No requirement collisions detected based on current evidence."

    lines: List[str] = [
        "=" * 70,
        "  REQUIREMENT COLLISION DETECTION REPORT",
        f"  Total Potential Collisions Flagged: {len(findings)}",
        "=" * 70,
    ]

    for idx, f in enumerate(findings, start=1):
        lines.append(f"\n[{idx}] {f.collision_id} — {f.category} (Severity: {f.severity}, Confidence: {f.confidence})")
        lines.append(f"    Requirements Involved : {', '.join(f.requirement_ids)}")
        lines.append(f"    Detection Rule        : {f.detection_rule}")
        lines.append(f"    Requires Review       : {'YES' if f.requires_human_review else 'NO'}")
        lines.append(f"    Explanation           : {f.explanation}")
        lines.append("    Evidence:")
        for ev in f.evidence:
            lines.append(f"      * {ev}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
