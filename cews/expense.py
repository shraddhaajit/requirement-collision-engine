"""Expense Data Model and Orchestration Workflow for CEWS."""

from dataclasses import dataclass, field
from typing import List, Dict, Any

ALLOWED_EXPENSE_TYPES = {"travel", "supplies", "equipment", "training", "meals", "other"}


@dataclass
class Expense:
    """TRACE: REQ-01
    Data model representing a corporate expense request.
    """
    request_id: str
    employee_id: str
    department: str
    expense_type: str
    amount: float
    budget: float
    is_emergency: bool = False
    status: str = "SUBMITTED"
    audit_log: List[Dict[str, Any]] = field(default_factory=list)


def validate_expense_input(expense: Expense) -> None:
    """TRACE: REQ-01
    Validate expense input fields for correctness.
    Raises ValueError if input data is invalid.
    """
    if not expense.request_id or not isinstance(expense.request_id, str) or not expense.request_id.strip():
        raise ValueError("Invalid or missing request_id")
    if not expense.employee_id or not isinstance(expense.employee_id, str) or not expense.employee_id.strip():
        raise ValueError("Invalid or missing employee_id")
    if not expense.department or not isinstance(expense.department, str) or not expense.department.strip():
        raise ValueError("Invalid or missing department")
    if not expense.expense_type or not isinstance(expense.expense_type, str) or expense.expense_type.lower() not in ALLOWED_EXPENSE_TYPES:
        raise ValueError(f"Unsupported or missing expense_type: {expense.expense_type}")
    if not isinstance(expense.amount, (int, float)) or expense.amount <= 0:
        raise ValueError(f"Invalid amount: {expense.amount}")
    if not isinstance(expense.budget, (int, float)) or expense.budget < 0:
        raise ValueError(f"Negative or invalid budget: {expense.budget}")


def submit_expense(expense: Expense) -> Expense:
    """TRACE: REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10
    Orchestrate the full expense approval workflow following Section 17.
    """
    from cews.audit import record_audit_log
    from cews.approval import (
        validate_budget,
        check_manager_approval,
        check_finance_approval,
        check_executive_approval,
        manager_override,
        process_emergency_expense,
        final_approval,
    )
    from cews.compliance import check_hr_compliance

    # Step 1: Record initial submission
    record_audit_log(expense, actor=expense.employee_id or "SYSTEM", action="SUBMITTED")

    # Step 2: Validate input fields
    try:
        validate_expense_input(expense)
    except ValueError as e:
        record_audit_log(expense, actor="SYSTEM", action=f"REJECTED_INVALID_INPUT: {e}")
        expense.status = "REJECTED"
        return expense

    # Step 3: Validate budget
    budget_ok = validate_budget(expense)
    if not budget_ok:
        record_audit_log(expense, actor="SYSTEM", action="REJECTED_BUDGET")
        expense.status = "REJECTED"
        return expense
    record_audit_log(expense, actor="SYSTEM", action="VALIDATED_BUDGET")

    # Step 4: Approval & Override / Emergency rules
    manager_ok = True
    if check_manager_approval(expense):
        if expense.is_emergency:
            emergency_ok = process_emergency_expense(expense)
            if emergency_ok:
                record_audit_log(expense, actor="SYSTEM", action="BYPASS_MANAGER_EMERGENCY")
                manager_ok = True
            else:
                manager_ok = False
        elif manager_override(expense):
            record_audit_log(expense, actor="MANAGER", action="OVERRIDE_MANAGER_TRAVEL")
            manager_ok = True
        else:
            record_audit_log(expense, actor="MANAGER", action="APPROVED_MANAGER")
            manager_ok = True

    # Step 5: HR Compliance for Travel
    hr_ok = True
    if expense.expense_type.lower() == "travel":
        hr_ok = check_hr_compliance(expense)
        if hr_ok:
            record_audit_log(expense, actor="HR", action="COMPLIANT_HR")
        else:
            record_audit_log(expense, actor="HR", action="REJECTED_HR")

    # Step 6: Finance Approval
    finance_ok = True
    if check_finance_approval(expense):
        record_audit_log(expense, actor="FINANCE", action="APPROVED_FINANCE")

    # Step 7: Executive Approval
    exec_ok = True
    if check_executive_approval(expense):
        record_audit_log(expense, actor="EXECUTIVE", action="APPROVED_EXECUTIVE")

    # Step 8: Final Gate
    final_ok = final_approval(
        expense,
        budget_passed=budget_ok,
        manager_passed=manager_ok,
        hr_passed=hr_ok,
        finance_passed=finance_ok,
        exec_passed=exec_ok,
    )

    if final_ok:
        record_audit_log(expense, actor="SYSTEM", action="FINAL_APPROVED")
    else:
        record_audit_log(expense, actor="SYSTEM", action="FINAL_REJECTED")

    return expense
