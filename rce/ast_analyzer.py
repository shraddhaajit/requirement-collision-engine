"""Reusable Python Static AST Analyzer for the Requirement Collision Engine (RCE).

Provides project-independent static analysis of Python source code and projects.
Extracts functions, methods, classes, parameters, calls, conditions, comparisons,
and traceability links without executing or importing any analyzed code.
Statically resolves local and cross-module dependencies where possible while
clearly distinguishing unresolved external, library, or dynamic calls.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from rce.traceability_extractor import extract_requirement_ids_from_docstring


class ASTAnalysisError(Exception):
    """Raised when static AST analysis encounters an unrecoverable syntax or structure error."""
    pass


# Default directories to ignore when discovering Python source files
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
    ".idea",
    ".vscode",
}

# Standard comparison operators mapped to human-readable symbols
_CMP_OP_SYMBOLS = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
}

# Standard built-ins recognized for classification
_STANDARD_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray", "bytes",
    "callable", "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir",
    "divmod", "enumerate", "eval", "exec", "filter", "float", "format", "frozenset",
    "getattr", "globals", "hasattr", "hash", "help", "hex", "id", "input", "int",
    "isinstance", "issubclass", "iter", "len", "list", "locals", "map", "max",
    "memoryview", "min", "next", "object", "oct", "open", "ord", "pow", "print",
    "property", "range", "repr", "reversed", "round", "set", "setattr", "slice",
    "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
}


def _safe_unparse(node: Optional[ast.AST]) -> Optional[str]:
    """Safely unparse an AST node to source expression string."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return str(node)


@dataclass(frozen=True)
class ParameterInfo:
    """Information about a function or method parameter."""

    name: str
    type_annotation: Optional[str] = None
    default_value: Optional[str] = None
    kind: str = "positional_or_keyword"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type_annotation": self.type_annotation,
            "default_value": self.default_value,
            "kind": self.kind,
        }


@dataclass
class ConditionInfo:
    """Information about a conditional expression or comparison."""

    line_number: int
    end_line_number: Optional[int]
    condition_type: str  # "if", "elif", "while", "assert", "if_exp", "compare"
    expression: str
    comparison_ops: List[str]
    variables: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "condition_type": self.condition_type,
            "expression": self.expression,
            "comparison_ops": list(self.comparison_ops),
            "variables": list(self.variables),
        }


@dataclass
class CallInfo:
    """Information about a function or method call made inside a function."""

    called_name: str
    line_number: int
    end_line_number: Optional[int]
    arg_count: int
    resolved_target: Optional[str] = None
    resolution_kind: str = "unresolved"

    @property
    def is_resolved(self) -> bool:
        return self.resolved_target is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "called_name": self.called_name,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "arg_count": self.arg_count,
            "resolved_target": self.resolved_target,
            "resolution_kind": self.resolution_kind,
            "is_resolved": self.is_resolved,
        }


@dataclass(frozen=True)
class ImportRecord:
    """Static record of an import statement."""

    module: str
    imported_name: Optional[str] = None
    alias: str = ""
    level: int = 0
    line_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "imported_name": self.imported_name,
            "alias": self.alias,
            "level": self.level,
            "line_number": self.line_number,
        }


@dataclass
class FunctionInfo:
    """Comprehensive static information about a function or method."""

    name: str
    qualified_name: str
    file_path: str
    module_name: str
    line_number: int
    end_line_number: Optional[int]
    parameters: List[str]
    parameter_details: List[ParameterInfo]
    is_method: bool = False
    is_async: bool = False
    docstring: Optional[str] = None
    traceability_ids: List[str] = field(default_factory=list)
    calls: List[CallInfo] = field(default_factory=list)
    conditions: List[ConditionInfo] = field(default_factory=list)
    local_imports: List[ImportRecord] = field(default_factory=list)

    @property
    def resolved_calls(self) -> List[CallInfo]:
        return [c for c in self.calls if c.is_resolved]

    @property
    def unresolved_calls(self) -> List[CallInfo]:
        return [c for c in self.calls if not c.is_resolved]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "module_name": self.module_name,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "parameters": list(self.parameters),
            "parameter_details": [p.to_dict() for p in self.parameter_details],
            "is_method": self.is_method,
            "is_async": self.is_async,
            "docstring": self.docstring,
            "traceability_ids": list(self.traceability_ids),
            "calls": [c.to_dict() for c in self.calls],
            "conditions": [cd.to_dict() for cd in self.conditions],
            "local_imports": [imp.to_dict() for imp in self.local_imports],
        }


@dataclass
class ClassInfo:
    """Comprehensive static information about a class."""

    name: str
    qualified_name: str
    file_path: str
    module_name: str
    line_number: int
    end_line_number: Optional[int]
    bases: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    traceability_ids: List[str] = field(default_factory=list)
    methods: List[FunctionInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "module_name": self.module_name,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "bases": list(self.bases),
            "docstring": self.docstring,
            "traceability_ids": list(self.traceability_ids),
            "methods": [m.to_dict() for m in self.methods],
        }


@dataclass
class ModuleInfo:
    """Static analysis results for a single Python module."""

    file_path: str
    module_name: str
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    imports: List[ImportRecord] = field(default_factory=list)

    @property
    def all_functions(self) -> List[FunctionInfo]:
        """Return all functions and methods in this module."""
        result = list(self.functions)
        for cls in self.classes:
            result.extend(cls.methods)
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "module_name": self.module_name,
            "classes": [c.to_dict() for c in self.classes],
            "functions": [f.to_dict() for f in self.functions],
            "imports": [imp.to_dict() for imp in self.imports],
        }


@dataclass
class ProjectAnalysis:
    """Comprehensive static analysis results across an entire project."""

    project_root: str
    modules: Dict[str, ModuleInfo]
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    call_graph: Dict[str, List[str]]
    unresolved_calls: Dict[str, List[str]]

    def get_function(self, qualified_name: str) -> Optional[FunctionInfo]:
        """Look up a function by its qualified name or 'module:name' representation."""
        for fn in self.functions:
            if fn.qualified_name == qualified_name:
                return fn
            if f"{fn.module_name}:{fn.name}" == qualified_name:
                return fn
        return None

    def get_functions_by_requirement(self, req_id: str) -> List[FunctionInfo]:
        """Return all functions tagged with the given requirement ID."""
        norm = req_id.upper()
        return [fn for fn in self.functions if norm in fn.traceability_ids]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": self.project_root,
            "modules": {k: m.to_dict() for k, m in self.modules.items()},
            "functions": [f.to_dict() for f in self.functions],
            "classes": [c.to_dict() for c in self.classes],
            "call_graph": {k: list(v) for k, v in self.call_graph.items()},
            "unresolved_calls": {k: list(v) for k, v in self.unresolved_calls.items()},
        }


def _extract_parameters(args_node: ast.arguments) -> Tuple[List[str], List[ParameterInfo]]:
    """Extract parameter names and detailed parameter metadata from an arguments node."""
    param_names: List[str] = []
    param_details: List[ParameterInfo] = []

    posonly = getattr(args_node, "posonlyargs", [])
    args = args_node.args
    all_pos = posonly + args
    defaults = args_node.defaults
    num_no_defaults = len(all_pos) - len(defaults)

    for idx, arg in enumerate(all_pos):
        param_names.append(arg.arg)
        ann = _safe_unparse(arg.annotation)
        default_val = None
        if idx >= num_no_defaults:
            default_val = _safe_unparse(defaults[idx - num_no_defaults])
        kind = "positional_only" if idx < len(posonly) else "positional_or_keyword"
        param_details.append(
            ParameterInfo(
                name=arg.arg,
                type_annotation=ann,
                default_value=default_val,
                kind=kind,
            )
        )

    if args_node.vararg:
        arg = args_node.vararg
        param_names.append(f"*{arg.arg}")
        ann = _safe_unparse(arg.annotation)
        param_details.append(
            ParameterInfo(name=f"*{arg.arg}", type_annotation=ann, kind="var_positional")
        )

    for idx, arg in enumerate(args_node.kwonlyargs):
        param_names.append(arg.arg)
        ann = _safe_unparse(arg.annotation)
        def_node = args_node.kw_defaults[idx] if idx < len(args_node.kw_defaults) else None
        default_val = _safe_unparse(def_node)
        param_details.append(
            ParameterInfo(
                name=arg.arg,
                type_annotation=ann,
                default_value=default_val,
                kind="keyword_only",
            )
        )

    if args_node.kwarg:
        arg = args_node.kwarg
        param_names.append(f"**{arg.arg}")
        ann = _safe_unparse(arg.annotation)
        param_details.append(
            ParameterInfo(name=f"**{arg.arg}", type_annotation=ann, kind="var_keyword")
        )

    return param_names, param_details


def _extract_comparison_ops_and_vars(expr_node: ast.AST) -> Tuple[List[str], List[str]]:
    """Extract comparison operator symbols and variable names from an expression."""
    ops: List[str] = []
    variables: Set[str] = set()

    for subnode in ast.walk(expr_node):
        if isinstance(subnode, ast.Compare):
            for op in subnode.ops:
                symbol = _CMP_OP_SYMBOLS.get(type(op), type(op).__name__)
                ops.append(symbol)
        elif isinstance(subnode, ast.Name):
            variables.add(subnode.id)

    return ops, sorted(variables)


class _ModuleASTVisitor(ast.NodeVisitor):
    """AST visitor collecting classes, functions, calls, conditions, and imports."""

    def __init__(self, file_path: str, module_name: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.classes: List[ClassInfo] = []
        self.functions: List[FunctionInfo] = []
        self.imports: List[ImportRecord] = []

        self._class_stack: List[ClassInfo] = []
        self._func_stack: List[FunctionInfo] = []
        self._root_tests_seen: Set[int] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            rec = ImportRecord(
                module=alias.name,
                imported_name=None,
                alias=alias.asname or alias.name,
                level=0,
                line_number=node.lineno,
            )
            if self._func_stack:
                self._func_stack[-1].local_imports.append(rec)
            else:
                self.imports.append(rec)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raw_mod = node.module or ""
        for alias in node.names:
            rec = ImportRecord(
                module=raw_mod,
                imported_name=alias.name,
                alias=alias.asname or alias.name,
                level=node.level,
                line_number=node.lineno,
            )
            if self._func_stack:
                self._func_stack[-1].local_imports.append(rec)
            else:
                self.imports.append(rec)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        doc = ast.get_docstring(node)
        req_ids = extract_requirement_ids_from_docstring(doc)

        if self._class_stack:
            qualname = f"{self._class_stack[-1].name}.{node.name}"
        else:
            qualname = node.name

        full_qualname = f"{self.module_name}:{qualname}"
        bases = [_safe_unparse(b) or "" for b in node.bases]

        cls_info = ClassInfo(
            name=node.name,
            qualified_name=full_qualname,
            file_path=self.file_path,
            module_name=self.module_name,
            line_number=node.lineno,
            end_line_number=getattr(node, "end_lineno", node.lineno),
            bases=bases,
            docstring=doc,
            traceability_ids=req_ids,
        )

        self.classes.append(cls_info)
        self._class_stack.append(cls_info)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function_node(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function_node(node, is_async=True)

    def _handle_function_node(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], is_async: bool
    ) -> None:
        doc = ast.get_docstring(node)
        req_ids = extract_requirement_ids_from_docstring(doc)
        param_names, param_details = _extract_parameters(node.args)

        is_method = len(self._class_stack) > 0
        if is_method:
            parent_class = self._class_stack[-1]
            func_name = f"{parent_class.name}.{node.name}"
            qualname = f"{self.module_name}:{func_name}"
        elif self._func_stack:
            parent_func = self._func_stack[-1]
            func_name = f"{parent_func.name}.<locals>.{node.name}"
            qualname = f"{self.module_name}:{func_name}"
        else:
            func_name = node.name
            qualname = f"{self.module_name}:{func_name}"

        fn_info = FunctionInfo(
            name=func_name,
            qualified_name=qualname,
            file_path=self.file_path,
            module_name=self.module_name,
            line_number=node.lineno,
            end_line_number=getattr(node, "end_lineno", node.lineno),
            parameters=param_names,
            parameter_details=param_details,
            is_method=is_method,
            is_async=is_async,
            docstring=doc,
            traceability_ids=req_ids,
        )

        if is_method:
            self._class_stack[-1].methods.append(fn_info)
        else:
            self.functions.append(fn_info)

        self._func_stack.append(fn_info)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if self._func_stack:
            callee_str = _safe_unparse(node.func) or "<unknown>"
            arg_count = len(node.args) + len(node.keywords)
            call_info = CallInfo(
                called_name=callee_str,
                line_number=node.lineno,
                end_line_number=getattr(node, "end_lineno", node.lineno),
                arg_count=arg_count,
            )
            self._func_stack[-1].calls.append(call_info)

        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        if self._func_stack:
            self._record_condition(node.test, "if", node.lineno, getattr(node.test, "end_lineno", node.lineno))
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        if self._func_stack:
            self._record_condition(node.test, "while", node.lineno, getattr(node.test, "end_lineno", node.lineno))
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if self._func_stack:
            self._record_condition(node.test, "assert", node.lineno, getattr(node.test, "end_lineno", node.lineno))
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        if self._func_stack:
            self._record_condition(node.test, "if_exp", node.lineno, getattr(node.test, "end_lineno", node.lineno))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self._func_stack:
            # If this Compare node was not already recorded as the root test of an if/while/assert/if_exp
            if id(node) not in self._root_tests_seen:
                ops = [_CMP_OP_SYMBOLS.get(type(op), type(op).__name__) for op in node.ops]
                vars_in_cmp = sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name)})
                self._func_stack[-1].conditions.append(
                    ConditionInfo(
                        line_number=node.lineno,
                        end_line_number=getattr(node, "end_lineno", node.lineno),
                        condition_type="compare",
                        expression=_safe_unparse(node) or "",
                        comparison_ops=ops,
                        variables=vars_in_cmp,
                    )
                )
        self.generic_visit(node)

    def _record_condition(self, test_node: ast.AST, cond_type: str, lineno: int, end_lineno: Optional[int]) -> None:
        self._root_tests_seen.add(id(test_node))
        ops, vars_list = _extract_comparison_ops_and_vars(test_node)
        self._func_stack[-1].conditions.append(
            ConditionInfo(
                line_number=lineno,
                end_line_number=end_lineno,
                condition_type=cond_type,
                expression=_safe_unparse(test_node) or "",
                comparison_ops=ops,
                variables=vars_list,
            )
        )


def analyze_source(
    source_code: str,
    file_path: str = "<string>",
    module_name: str = "<string>",
) -> ModuleInfo:
    """Statically analyze a Python source code string.

    Args:
        source_code: Python code content.
        file_path: Display file path.
        module_name: Python module dot-notation name.

    Returns:
        ModuleInfo containing extracted classes, functions, calls, and conditions.

    Raises:
        ASTAnalysisError: If the source code cannot be parsed by ast.
    """
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError as err:
        raise ASTAnalysisError(f"Syntax error in '{file_path}': {err}") from err

    visitor = _ModuleASTVisitor(file_path=file_path, module_name=module_name)
    visitor.visit(tree)

    mod = ModuleInfo(
        file_path=file_path,
        module_name=module_name,
        classes=visitor.classes,
        functions=visitor.functions,
        imports=visitor.imports,
    )
    _resolve_project_dependencies({module_name: mod})
    return mod


def derive_module_name(rel_path: Union[str, Path]) -> str:
    """Derive Python module dot-path from a relative file path."""
    path_str = Path(rel_path).as_posix()
    if path_str.endswith(".py"):
        path_str = path_str[:-3]

    parts = [p for p in path_str.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts.pop()

    return ".".join(parts) if parts else "root"


def analyze_file(
    file_path: Union[str, Path],
    project_root: Optional[Union[str, Path]] = None,
) -> ModuleInfo:
    """Statically analyze a single Python file without importing or executing it.

    Args:
        file_path: Path to Python source file.
        project_root: Optional project root to compute relative path and module name.

    Returns:
        ModuleInfo instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ASTAnalysisError: If static AST parsing fails.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path}")

    content = path.read_text(encoding="utf-8")

    if project_root is not None:
        root_path = Path(project_root).resolve()
        try:
            rel_path = path.relative_to(root_path).as_posix()
        except ValueError:
            rel_path = path.as_posix()
    else:
        rel_path = path.as_posix()

    mod_name = derive_module_name(rel_path)
    return analyze_source(source_code=content, file_path=rel_path, module_name=mod_name)


def _resolve_import_module_name(current_module: str, import_record: ImportRecord) -> str:
    """Resolve relative or absolute module dot-name from an import record."""
    if import_record.level == 0:
        return import_record.module

    # Relative import: compute base package
    curr_parts = current_module.split(".")
    # level 1 = current package, level 2 = parent package, etc.
    if len(curr_parts) >= import_record.level:
        base_parts = curr_parts[: len(curr_parts) - import_record.level]
    else:
        base_parts = []

    if import_record.module:
        return ".".join(base_parts + [import_record.module])
    return ".".join(base_parts)


def _resolve_project_dependencies(
    modules: Dict[str, ModuleInfo],
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Statically resolve function calls to known project definitions.

    Distinguishes resolved local and cross-module relationships from
    unresolved external, library, or dynamic calls without executing code.
    """
    # 1. Build project symbol tables
    all_functions: Dict[str, FunctionInfo] = {}
    module_functions: Dict[str, Dict[str, FunctionInfo]] = {}
    module_classes: Dict[str, Dict[str, ClassInfo]] = {}

    for mod_name, mod in modules.items():
        mod_fns: Dict[str, FunctionInfo] = {}
        mod_cls: Dict[str, ClassInfo] = {}

        for fn in mod.functions:
            all_functions[fn.qualified_name] = fn
            all_functions[f"{mod_name}:{fn.name}"] = fn
            mod_fns[fn.name] = fn

        for cls in mod.classes:
            mod_cls[cls.name] = cls
            for method in cls.methods:
                all_functions[method.qualified_name] = method
                all_functions[f"{mod_name}:{method.name}"] = method
                # Also index by simple method name e.g. "method" within class
                simple_m_name = method.name.split(".", 1)[-1]
                all_functions[f"{mod_name}:{cls.name}.{simple_m_name}"] = method
                mod_fns[method.name] = method
                mod_fns[f"{cls.name}.{simple_m_name}"] = method

        module_functions[mod_name] = mod_fns
        module_classes[mod_name] = mod_cls

    call_graph: Dict[str, List[str]] = {}
    unresolved_calls: Dict[str, List[str]] = {}

    # 2. Resolve calls in each function
    for mod_name, mod in modules.items():
        # Pre-resolve module-level imports
        mod_import_map: Dict[str, Tuple[str, Optional[str]]] = {}
        for imp in mod.imports:
            target_mod = _resolve_import_module_name(mod_name, imp)
            mod_import_map[imp.alias] = (target_mod, imp.imported_name)

        for fn in mod.all_functions:
            # Build combined import map: module-level + local function-level
            local_import_map = dict(mod_import_map)
            for imp in fn.local_imports:
                target_mod = _resolve_import_module_name(mod_name, imp)
                local_import_map[imp.alias] = (target_mod, imp.imported_name)

            resolved_targets: List[str] = []
            unresolved_names: List[str] = []

            for call in fn.calls:
                expr = call.called_name

                # Case A: Simple identifier call (e.g., validate_budget(x))
                if "." not in expr:
                    # Check imports first
                    if expr in local_import_map:
                        target_mod, target_sym = local_import_map[expr]
                        sym_name = target_sym if target_sym is not None else expr
                        qual = f"{target_mod}:{sym_name}"
                        if qual in all_functions:
                            call.resolved_target = all_functions[qual].qualified_name
                            call.resolution_kind = "imported_function"
                        elif target_mod in module_classes and sym_name in module_classes[target_mod]:
                            # Instantiation of imported class
                            call.resolved_target = f"{target_mod}:{sym_name}"
                            call.resolution_kind = "imported_class"

                    # Check current module top-level functions
                    if not call.is_resolved:
                        if expr in module_functions.get(mod_name, {}):
                            call.resolved_target = module_functions[mod_name][expr].qualified_name
                            call.resolution_kind = "local_function"
                        elif expr in module_classes.get(mod_name, {}):
                            call.resolved_target = f"{mod_name}:{expr}"
                            call.resolution_kind = "local_class"

                    # Check standard built-ins
                    if not call.is_resolved:
                        if expr in _STANDARD_BUILTINS:
                            call.resolution_kind = "builtin"
                        else:
                            call.resolution_kind = "unresolved_external"

                # Case B: Method call on self or cls (e.g., self.helper())
                elif expr.startswith("self.") or expr.startswith("cls."):
                    method_name = expr.split(".", 1)[1]
                    if fn.is_method:
                        # Extract class name from fn.name (e.g. "MyClass.my_method")
                        cls_name = fn.name.split(".", 1)[0]
                        qual = f"{mod_name}:{cls_name}.{method_name}"
                        if qual in all_functions:
                            call.resolved_target = all_functions[qual].qualified_name
                            call.resolution_kind = "local_method"
                        else:
                            call.resolution_kind = "unresolved_method"
                    else:
                        call.resolution_kind = "unresolved_method"

                # Case C: Qualified call (e.g., mod.func(), obj.method())
                else:
                    prefix, attr = expr.rsplit(".", 1)

                    # Check if prefix is an imported module alias
                    if prefix in local_import_map:
                        target_mod, _ = local_import_map[prefix]
                        qual = f"{target_mod}:{attr}"
                        if qual in all_functions:
                            call.resolved_target = all_functions[qual].qualified_name
                            call.resolution_kind = "module_qualified_call"
                        elif target_mod in module_classes and attr in module_classes[target_mod]:
                            call.resolved_target = f"{target_mod}:{attr}"
                            call.resolution_kind = "imported_class"
                        else:
                            call.resolution_kind = "unresolved_external"
                    # Check if prefix is a known local class name
                    elif prefix in module_classes.get(mod_name, {}):
                        qual = f"{mod_name}:{prefix}.{attr}"
                        if qual in all_functions:
                            call.resolved_target = all_functions[qual].qualified_name
                            call.resolution_kind = "class_method_call"
                        else:
                            call.resolution_kind = "unresolved_method"
                    else:
                        call.resolution_kind = "unresolved_dynamic_or_external"

                # Record resolved / unresolved entries
                if call.is_resolved and call.resolved_target:
                    resolved_targets.append(call.resolved_target)
                else:
                    unresolved_names.append(call.called_name)

            call_graph[fn.qualified_name] = sorted(list(dict.fromkeys(resolved_targets)))
            unresolved_calls[fn.qualified_name] = sorted(list(dict.fromkeys(unresolved_names)))

    return call_graph, unresolved_calls


def analyze_project(
    project_root: Union[str, Path] = ".",
    source_dirs: Optional[Iterable[str]] = None,
    excluded_dirs: Optional[Iterable[str]] = None,
) -> ProjectAnalysis:
    """Statically analyze a Python project without executing or importing any code.

    Discovers Python files, parses their AST, extracts functions/classes/calls/conditions,
    resolves static dependencies between functions, and constructs a call graph.

    Args:
        project_root: Root path of the project.
        source_dirs: Optional subset of subdirectories to scan (e.g. ['cews', 'src']).
        excluded_dirs: Optional set of directory names to exclude.

    Returns:
        ProjectAnalysis instance containing all modules, functions, classes, and call graph.

    Raises:
        FileNotFoundError: If project_root does not exist.
    """
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project root directory not found: {root}")

    active_excluded: Set[str] = set(DEFAULT_EXCLUDED_DIRS)
    if not source_dirs:
        # Default application scan: exclude test directories
        active_excluded.update({"tests", "test", "testing"})
        # When analyzing CEWS workspace, exclude RCE engine implementation from target code
        if (root / "cews").is_dir() and (root / "rce").is_dir():
            active_excluded.add("rce")
    if excluded_dirs:
        active_excluded.update(excluded_dirs)

    # Determine directories to scan
    if source_dirs:
        scan_roots = [root / d for d in source_dirs if (root / d).is_dir()]
    else:
        scan_roots = [root]

    modules: Dict[str, ModuleInfo] = {}

    for scan_root in scan_roots:
        for current_dir, dirnames, filenames in os.walk(scan_root):
            # Exclude unwanted directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in active_excluded and not d.startswith(".")
            ]

            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue

                # In default scan, ignore standalone test files (discovered by test pass)
                if not source_dirs and (fname.startswith("test_") or fname.endswith("_test.py")):
                    continue

                full_path = Path(current_dir) / fname
                try:
                    rel_path = full_path.relative_to(root).as_posix()
                except ValueError:
                    rel_path = full_path.as_posix()

                mod_name = derive_module_name(rel_path)
                try:
                    mod_info = analyze_file(full_path, project_root=root)
                    modules[mod_name] = mod_info
                except ASTAnalysisError:
                    # Ignore or re-raise if needed; here we continue gracefully
                    continue

    # Flatten functions and classes
    all_functions: List[FunctionInfo] = []
    all_classes: List[ClassInfo] = []

    for mod in modules.values():
        all_functions.extend(mod.all_functions)
        all_classes.extend(mod.classes)

    # Deterministic sorting
    all_functions.sort(key=lambda fn: (fn.file_path, fn.line_number, fn.name))
    all_classes.sort(key=lambda c: (c.file_path, c.line_number, c.name))

    # Resolve dependencies
    call_graph, unresolved_calls = _resolve_project_dependencies(modules)

    return ProjectAnalysis(
        project_root=root.as_posix(),
        modules=modules,
        functions=all_functions,
        classes=all_classes,
        call_graph=call_graph,
        unresolved_calls=unresolved_calls,
    )
