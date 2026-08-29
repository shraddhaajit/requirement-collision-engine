"""Approval Workflow Module for CEWS."""

from cews.expense import Expense


def validate_budget(expense: Expense) -> bool:
    """TRACE: REQ-02
    Validate that the expense amount does not exceed the available department budget.
    """
    if expense.amount < 0 or expense.budget < 0:
        return False
    return expense.amount <= expense.budget
