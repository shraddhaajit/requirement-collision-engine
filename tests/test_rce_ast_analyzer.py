"""Tests for RCE Static AST Analyzer (Phase 2)."""

import json
from pathlib import Path
import pytest

from rce.ast_analyzer import (
    ASTAnalysisError,
    CallInfo,
    ClassInfo,
    ConditionInfo,
    FunctionInfo,
    ModuleInfo,
    ParameterInfo,
    ProjectAnalysis,
    analyze_file,
    analyze_project,
    analyze_source,
    derive_module_name,
)


def test_function_and_class_extraction():
    """Verify static extraction of top-level functions and classes."""
    code = """
class BaseHandler:
    pass

class RequestHandler(BaseHandler):
    \"\"\"Handles HTTP requests.\"\"\"
    def handle(self):
        pass

def global_helper(x, y=10):
    return x + y
"""
    mod = analyze_source(code, file_path="handlers/request.py", module_name="handlers.request")

    assert len(mod.classes) == 2
    assert mod.classes[0].name == "BaseHandler"
    assert mod.classes[0].bases == []
    assert mod.classes[0].qualified_name == "handlers.request:BaseHandler"

    assert mod.classes[1].name == "RequestHandler"
    assert mod.classes[1].bases == ["BaseHandler"]
    assert mod.classes[1].docstring == "Handles HTTP requests."
    assert len(mod.classes[1].methods) == 1

    assert len(mod.functions) == 1
    fn = mod.functions[0]
    assert fn.name == "global_helper"
    assert fn.qualified_name == "handlers.request:global_helper"
    assert fn.is_method is False
    assert fn.line_number == 10
    assert fn.end_line_number >= 10


def test_nested_methods_and_qualified_names():
    """Verify methods inside classes are properly qualified and marked as methods."""
    code = """
class OrderService:
    def process_order(self, order_id: str) -> bool:
        return True

    class NestedValidator:
        def validate(self, data):
            pass
"""
    mod = analyze_source(code, file_path="store/orders.py", module_name="store.orders")
    assert len(mod.classes) == 2

    order_svc = mod.classes[0]
    assert order_svc.name == "OrderService"
    assert len(order_svc.methods) == 1
    method = order_svc.methods[0]
    assert method.name == "OrderService.process_order"
    assert method.qualified_name == "store.orders:OrderService.process_order"
    assert method.is_method is True

    nested = mod.classes[1]
    assert nested.name == "NestedValidator"
    assert len(nested.methods) == 1
    nested_method = nested.methods[0]
    assert nested_method.name == "NestedValidator.validate"
    assert nested_method.is_method is True


def test_parameters_and_source_locations():
    """Verify parameters, type annotations, default values, and kinds."""
    code = """
def complex_signature(
    pos_only: int,
    /,
    regular: str,
    default_val: bool = True,
    *args,
    kw_only: float = 0.5,
    **kwargs,
) -> None:
    pass
"""
    mod = analyze_source(code, file_path="utils.py", module_name="utils")
    assert len(mod.functions) == 1
    fn = mod.functions[0]

    assert fn.parameters == [
        "pos_only",
        "regular",
        "default_val",
        "*args",
        "kw_only",
        "**kwargs",
    ]

    details = {p.name: p for p in fn.parameter_details}
    assert details["pos_only"].kind == "positional_only"
    assert details["pos_only"].type_annotation == "int"

    assert details["regular"].kind == "positional_or_keyword"
    assert details["regular"].type_annotation == "str"

    assert details["default_val"].default_value == "True"
    assert details["default_val"].type_annotation == "bool"

    assert details["*args"].kind == "var_positional"
    assert details["kw_only"].kind == "keyword_only"
    assert details["kw_only"].default_value == "0.5"
    assert details["**kwargs"].kind == "var_keyword"


def test_function_calls_and_dependency_resolution(tmp_path: Path):
    """Verify static dependency resolution for local and cross-module calls."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()

    math_file = pkg_dir / "math_ops.py"
    math_file.write_text(
        """
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
""",
        encoding="utf-8",
    )

    engine_file = pkg_dir / "engine.py"
    engine_file.write_text(
        """
from pkg.math_ops import add
import pkg.math_ops as mops

def calculate(x, y):
    s = add(x, y)
    p = mops.multiply(x, y)
    h = _helper(s)
    print(p)
    return h

def _helper(val):
    return val * 2
""",
        encoding="utf-8",
    )

    analysis = analyze_project(tmp_path)
    calc_fn = analysis.get_function("pkg.engine:calculate")
    assert calc_fn is not None

    resolved = {c.called_name: c.resolved_target for c in calc_fn.calls if c.is_resolved}
    assert resolved["add"] == "pkg.math_ops:add"
    assert resolved["mops.multiply"] == "pkg.math_ops:multiply"
    assert resolved["_helper"] == "pkg.engine:_helper"

    unresolved = [c.called_name for c in calc_fn.calls if not c.is_resolved]
    assert "print" in unresolved

    # Verify project-level call graph
    assert "pkg.math_ops:add" in analysis.call_graph["pkg.engine:calculate"]
    assert "pkg.math_ops:multiply" in analysis.call_graph["pkg.engine:calculate"]
    assert "pkg.engine:_helper" in analysis.call_graph["pkg.engine:calculate"]


def test_method_calls_self_resolution():
    """Verify that self.method() calls resolve to methods on the enclosing class."""
    code = """
class Calculator:
    def compute(self, x):
        return self._step1(x) + self._step2(x)

    def _step1(self, x):
        return x * 2

    def _step2(self, x):
        return x + 1
"""
    mod = analyze_source(code, file_path="calc.py", module_name="calc")
    cls = mod.classes[0]
    compute_fn = cls.methods[0]

    resolved_targets = [c.resolved_target for c in compute_fn.calls if c.is_resolved]
    assert "calc:Calculator._step1" in resolved_targets
    assert "calc:Calculator._step2" in resolved_targets


def test_conditional_expressions_and_comparisons():
    """Verify extraction of if, while, assert, ternary, and comparisons."""
    code = """
def evaluate(val, flag):
    if val > 100 or val < 0:
        return False
    while val > 10:
        val -= 1
    assert val >= 0
    status = "HIGH" if val == 10 else "NORMAL"
    return val == 5
"""
    mod = analyze_source(code, file_path="eval.py", module_name="eval")
    fn = mod.functions[0]

    cond_types = [c.condition_type for c in fn.conditions]
    assert "if" in cond_types
    assert "while" in cond_types
    assert "assert" in cond_types
    assert "if_exp" in cond_types
    assert "compare" in cond_types

    all_ops = [op for c in fn.conditions for op in c.comparison_ops]
    assert ">" in all_ops
    assert "<" in all_ops
    assert ">=" in all_ops
    assert "==" in all_ops

    if_cond = next(c for c in fn.conditions if c.condition_type == "if")
    assert "val" in if_cond.variables
    assert if_cond.line_number == 3


def test_traceability_integration():
    """Verify seamless extraction of requirement traceability IDs using Phase 1 parser."""
    code = """
def travel_gate():
    \"\"\"TRACE: REQ-04, REQ-07
    Enforces travel compliance and manager override.
    Unrelated REQ-99 reference in prose.
    \"\"\"
    pass

class AuditService:
    \"\"\"TRACE: REQ-09
    Audit service component.
    \"\"\"
    def log(self):
        \"\"\"TRACE: REQ-09\"\"\"
        pass
"""
    mod = analyze_source(code, file_path="services.py", module_name="services")

    fn = mod.functions[0]
    assert fn.traceability_ids == ["REQ-04", "REQ-07"]

    cls = mod.classes[0]
    assert cls.traceability_ids == ["REQ-09"]
    assert cls.methods[0].traceability_ids == ["REQ-09"]


def test_syntax_errors_and_missing_files(tmp_path: Path):
    """Verify clear exceptions on syntax errors and nonexistent paths."""
    with pytest.raises(ASTAnalysisError, match="Syntax error"):
        analyze_source("def broken_code(: pass", file_path="bad.py")

    with pytest.raises(FileNotFoundError):
        analyze_file("nonexistent_file_12345.py")

    with pytest.raises(FileNotFoundError):
        analyze_project("nonexistent_project_directory_12345")


def test_cews_project_analysis():
    """Verify analyzer correctly analyzes the actual CEWS codebase."""
    analysis = analyze_project(".", source_dirs=["cews"])

    # Must find all 4 core CEWS modules
    expected_mods = {"cews.approval", "cews.audit", "cews.compliance", "cews.expense"}
    assert expected_mods.issubset(set(analysis.modules.keys()))

    # Check that final_approval has resolved dependencies to compliance and budget
    final_app = analysis.get_function("cews.approval:final_approval")
    assert final_app is not None
    assert "cews.approval:validate_budget" in analysis.call_graph["cews.approval:final_approval"]
    assert "cews.compliance:check_hr_compliance" in analysis.call_graph["cews.approval:final_approval"]
    assert "cews.approval:check_manager_approval" in analysis.call_graph["cews.approval:final_approval"]

    # Check submit_expense orchestrator resolution
    submit_exp = analysis.get_function("cews.expense:submit_expense")
    assert submit_exp is not None
    submit_calls = analysis.call_graph["cews.expense:submit_expense"]
    assert "cews.audit:record_audit_log" in submit_calls
    assert "cews.expense:validate_expense_input" in submit_calls
    assert "cews.approval:final_approval" in submit_calls

    # Requirement lookup helper
    req04_fns = analysis.get_functions_by_requirement("REQ-04")
    req04_names = [f.qualified_name for f in req04_fns]
    assert "cews.compliance:check_hr_compliance" in req04_names
    assert "cews.approval:final_approval" in req04_names


def test_exclusion_of_virtualenv_and_generated_dirs(tmp_path: Path):
    """Verify .venv, venv, and __pycache__ folders are excluded from analysis."""
    # Source file
    src = tmp_path / "app"
    src.mkdir()
    (src / "main.py").write_text("def run(): pass", encoding="utf-8")

    # Excluded dirs with python files
    for folder_name in [".venv", "venv", "__pycache__", ".pytest_cache"]:
        folder = tmp_path / folder_name
        folder.mkdir()
        (folder / "ignored.py").write_text("def ignored(): pass", encoding="utf-8")

    analysis = analyze_project(tmp_path)
    module_names = set(analysis.modules.keys())

    assert "app.main" in module_names
    assert not any(".venv" in m for m in module_names)
    assert not any("venv" in m for m in module_names)
    assert not any("__pycache__" in m for m in module_names)
    assert not any(".pytest_cache" in m for m in module_names)


def test_temporary_test_project_unrelated_to_cews(tmp_path: Path):
    """Verify project-independence using a synthetic inventory management system."""
    inv_dir = tmp_path / "inventory"
    inv_dir.mkdir()

    # models.py
    (inv_dir / "models.py").write_text(
        """
class Item:
    def __init__(self, sku: str, quantity: int, unit_price: float):
        self.sku = sku
        self.quantity = quantity
        self.unit_price = unit_price
""",
        encoding="utf-8",
    )

    # alerts.py
    (inv_dir / "alerts.py").write_text(
        """
def trigger_restock_alert(sku: str, current_qty: int) -> bool:
    \"\"\"TRACE: REQ-102
    Notifies logistics when inventory is critically low.
    \"\"\"
    if current_qty < 10:
        return True
    return False
""",
        encoding="utf-8",
    )

    # warehouse.py
    (inv_dir / "warehouse.py").write_text(
        """
from inventory.alerts import trigger_restock_alert
from inventory.models import Item

class WarehouseManager:
    \"\"\"TRACE: REQ-101\"\"\"
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.items = {}

    def check_stock(self, item: Item) -> bool:
        \"\"\"TRACE: REQ-102\"\"\"
        if item.quantity < 5:
            trigger_restock_alert(item.sku, item.quantity)
            return False
        return True
""",
        encoding="utf-8",
    )

    analysis = analyze_project(tmp_path)

    # Check module discovery
    assert "inventory.models" in analysis.modules
    assert "inventory.alerts" in analysis.modules
    assert "inventory.warehouse" in analysis.modules

    # Check cross-module call resolution
    check_stock_fn = analysis.get_function("inventory.warehouse:WarehouseManager.check_stock")
    assert check_stock_fn is not None
    assert "inventory.alerts:trigger_restock_alert" in analysis.call_graph["inventory.warehouse:WarehouseManager.check_stock"]

    # Check conditions
    conds = check_stock_fn.conditions
    assert any(c.condition_type == "if" and "<" in c.comparison_ops for c in conds)

    # Check traceability IDs on synthetic requirement tag
    assert "REQ-102" in check_stock_fn.traceability_ids

    # Check full dictionary serialization
    serialized = analysis.to_dict()
    assert isinstance(serialized, dict)
    json_str = json.dumps(serialized)
    assert "inventory.warehouse:WarehouseManager.check_stock" in json_str


def test_derive_module_name():
    """Verify module dot-name derivation from relative paths."""
    assert derive_module_name("cews/approval.py") == "cews.approval"
    assert derive_module_name("cews/__init__.py") == "cews"
    assert derive_module_name("src/app/core/engine.py") == "src.app.core.engine"
    assert derive_module_name("script.py") == "script"
