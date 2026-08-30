"""Approval Workflow Module for CEWS."""

from cews.expense import Expense
from cews.compliance import check_hr_compliance


def validate_budget(expense: Expense) -> bool:
    """TRACE: REQ-02
    Validate that the expense amount does not exceed the available department budget.
    """
    if expense.amount < 0 or expense.budget < 0:
        return False
    return expense.amount <= expense.budget


def check_manager_approval(expense: Expense) -> bool:
    """TRACE: REQ-03
    Check if manager approval is required (expenses above ₹10,000).
    """
    return expense.amount > 10000.0


def check_finance_approval(expense: Expense) -> bool:
    """TRACE: REQ-05
    Check if finance approval is required (expenses above ₹25,000).
    """
    return expense.amount > 25000.0


def check_executive_approval(expense: Expense) -> bool:
    """TRACE: REQ-06
    Check if executive approval is required (expenses above ₹50,000).
    """
    return expense.amount > 50000.0


def manager_override(expense: Expense) -> bool:
    """TRACE: REQ-07
    Allows a manager to approve a travel expense below ₹15,000 without the normal manager approval stage.
    Must NOT skip mandatory HR compliance.
    Returns True if override is valid and HR compliance passes.
    """
    if expense.expense_type.lower() == "travel" and expense.amount < 15000.0:
        # HR compliance remains mandatory during override
        hr_passed = check_hr_compliance(expense)
        return hr_passed
    return False


def process_emergency_expense(expense: Expense) -> bool:
    """TRACE: REQ-08
    An emergency expense may bypass the manager approval stage.
    However, budget validation, audit logging, and other mandatory conditions still apply.
    Returns True if emergency status is valid.
    """
    if not expense.is_emergency:
        return False
    # Budget validation must still be satisfied
    if not validate_budget(expense):
        return False
    return True


def final_approval(expense: Expense, budget_passed: bool = True, manager_passed: bool = True,
                   hr_passed: bool = True, finance_passed: bool = True, exec_passed: bool = True) -> bool:
    """TRACE: REQ-04, REQ-07, REQ-08, REQ-10
    Final gate for expense approval.
    Gates on all applicable mandatory conditions actually being satisfied.
    Does not blindly trust earlier approvals.
    """
    # 1. Mandatory Budget Validation
    if not budget_passed or not validate_budget(expense):
        expense.status = "REJECTED"
        return False

    # 2. Mandatory HR Compliance for Travel
    if expense.expense_type.lower() == "travel":
        if not hr_passed or not check_hr_compliance(expense):
            expense.status = "REJECTED"
            return False

    # 3. Manager Approval Requirement (above ₹10,000)
    # Bypassed ONLY IF valid manager override (< ₹15,000 travel) OR valid emergency expense
    if check_manager_approval(expense):
        is_override = manager_override(expense)
        is_emergency = expense.is_emergency and process_emergency_expense(expense)
        if not (manager_passed or is_override or is_emergency):
            expense.status = "REJECTED"
            return False

    # 4. Mandatory Finance Approval (above ₹25,000)
    if check_finance_approval(expense):
        if not finance_passed:
            expense.status = "REJECTED"
            return False

    # 5. Mandatory Executive Approval (above ₹50,000)
    if check_executive_approval(expense):
        if not exec_passed:
            expense.status = "REJECTED"
            return False

    expense.status = "APPROVED"
    return True
