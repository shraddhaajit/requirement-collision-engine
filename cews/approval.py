"""Approval Workflow Module for CEWS."""

from cews.expense import Expense


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
