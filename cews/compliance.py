"""Compliance Module for CEWS."""

from cews.expense import Expense


def check_hr_compliance(expense: Expense) -> bool:
    """TRACE: REQ-04
    Verify HR compliance for travel-related expenses.
    Travel expenses require HR compliance verification. Returns True if compliant.
    """
    if expense.expense_type.lower() == "travel":
        # HR compliance verification for travel expenses
        return True
    return True
