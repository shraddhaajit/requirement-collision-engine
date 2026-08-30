"""Baseline Test Suite for CEWS (Controlled Enterprise Expense Workflow System)."""

import pytest
from cews.expense import Expense, submit_expense, validate_expense_input
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
from cews.audit import record_audit_log


# =====================================================================
# 1. REQUIREMENT TESTS (REQ-01 through REQ-10)
# =====================================================================

def test_req01_expense_submission():
    """TRACE: REQ-01 - Confirm expense submission enters workflow and records audit log."""
    exp = Expense(
        request_id="EXP-101",
        employee_id="EMP-01",
        department="Engineering",
        expense_type="supplies",
        amount=5000.0,
        budget=10000.0,
    )
    result = submit_expense(exp)
    assert result.status == "APPROVED"
    assert any(log["action"] == "SUBMITTED" for log in result.audit_log)


def test_req02_budget_validation():
    """TRACE: REQ-02 - Confirm expense exceeding budget is rejected."""
    exp = Expense(
        request_id="EXP-102",
        employee_id="EMP-02",
        department="Marketing",
        expense_type="supplies",
        amount=15000.0,
        budget=10000.0,
    )
    result = submit_expense(exp)
    assert result.status == "REJECTED"
    assert not validate_budget(exp)
    assert any("REJECTED_BUDGET" in log["action"] for log in result.audit_log)


def test_req03_manager_approval():
    """TRACE: REQ-03 - Confirm expenses above ₹10,000 trigger manager approval check."""
    exp_below = Expense("EXP-103A", "EMP-03", "Sales", "supplies", 9000.0, 20000.0)
    exp_above = Expense("EXP-103B", "EMP-03", "Sales", "supplies", 12000.0, 20000.0)

    assert check_manager_approval(exp_below) is False
    assert check_manager_approval(exp_above) is True


def test_req04_hr_compliance():
    """TRACE: REQ-04 - Confirm travel expenses undergo HR compliance verification."""
    travel_exp = Expense("EXP-104", "EMP-04", "HR", "travel", 8000.0, 15000.0)
    assert check_hr_compliance(travel_exp) is True
    result = submit_expense(travel_exp)
    assert any(log["action"] == "COMPLIANT_HR" for log in result.audit_log)


def test_req05_finance_approval():
    """TRACE: REQ-05 - Confirm expenses above ₹25,000 trigger finance approval check."""
    exp_below = Expense("EXP-105A", "EMP-05", "Finance", "equipment", 24000.0, 30000.0)
    exp_above = Expense("EXP-105B", "EMP-05", "Finance", "equipment", 26000.0, 30000.0)

    assert check_finance_approval(exp_below) is False
    assert check_finance_approval(exp_above) is True

    res_above = submit_expense(exp_above)
    assert any(log["action"] == "APPROVED_FINANCE" for log in res_above.audit_log)


def test_req06_executive_approval():
    """TRACE: REQ-06 - Confirm expenses above ₹50,000 trigger executive approval check."""
    exp_below = Expense("EXP-106A", "EMP-06", "Exec", "equipment", 49000.0, 60000.0)
    exp_above = Expense("EXP-106B", "EMP-06", "Exec", "equipment", 55000.0, 60000.0)

    assert check_executive_approval(exp_below) is False
    assert check_executive_approval(exp_above) is True

    res_above = submit_expense(exp_above)
    assert any(log["action"] == "APPROVED_EXECUTIVE" for log in res_above.audit_log)


def test_req07_manager_travel_override():
    """TRACE: REQ-07 - Confirm manager override for travel < ₹15,000 still enforces HR compliance."""
    exp = Expense("EXP-107", "EMP-07", "Sales", "travel", 12000.0, 20000.0)
    assert manager_override(exp) is True
    result = submit_expense(exp)
    assert result.status == "APPROVED"
    assert any(log["action"] == "OVERRIDE_MANAGER_TRAVEL" for log in result.audit_log)
    assert any(log["action"] == "COMPLIANT_HR" for log in result.audit_log)


def test_req08_emergency_expense_bypass():
    """TRACE: REQ-08 - Confirm emergency status bypasses manager approval but requires budget validation."""
    exp = Expense("EXP-108", "EMP-08", "Ops", "supplies", 18000.0, 25000.0, is_emergency=True)
    assert process_emergency_expense(exp) is True
    result = submit_expense(exp)
    assert result.status == "APPROVED"
    assert any(log["action"] == "BYPASS_MANAGER_EMERGENCY" for log in result.audit_log)


def test_req09_audit_logging():
    """TRACE: REQ-09 - Confirm audit log entries capture request_id, actor, action, and timestamp."""
    exp = Expense("EXP-109", "EMP-09", "IT", "supplies", 3000.0, 10000.0)
    entry = record_audit_log(exp, actor="EMP-09", action="TEST_ACTION")
    assert entry["request_id"] == "EXP-109"
    assert entry["actor"] == "EMP-09"
    assert entry["action"] == "TEST_ACTION"
    assert "timestamp" in entry
    assert len(exp.audit_log) == 1


def test_req10_final_approval_gate():
    """TRACE: REQ-10 - Confirm final approval fails if mandatory budget condition is not satisfied."""
    exp = Expense("EXP-110", "EMP-10", "Legal", "supplies", 12000.0, 10000.0)
    approved = final_approval(exp, budget_passed=False)
    assert approved is False
    assert exp.status == "REJECTED"


# =====================================================================
# 2. BOUNDARY TESTS (Thresholds: ₹10k, ₹15k, ₹25k, ₹50k)
# =====================================================================

def test_boundary_manager_10000_below():
    """Confirm ₹10,000 exactly does NOT require manager approval."""
    exp = Expense("BND-10k", "EMP-B", "Eng", "supplies", 10000.0, 20000.0)
    assert check_manager_approval(exp) is False


def test_boundary_manager_10001_above():
    """Confirm ₹10,001 DOES require manager approval."""
    exp = Expense("BND-10k1", "EMP-B", "Eng", "supplies", 10001.0, 20000.0)
    assert check_manager_approval(exp) is True


def test_boundary_override_14999_below():
    """Confirm ₹14,999 travel qualifies for manager travel override."""
    exp = Expense("BND-15k-", "EMP-B", "Sales", "travel", 14999.0, 20000.0)
    assert manager_override(exp) is True


def test_boundary_override_15000_at_above():
    """Confirm ₹15,000 travel does NOT qualify for manager travel override."""
    exp = Expense("BND-15k", "EMP-B", "Sales", "travel", 15000.0, 20000.0)
    assert manager_override(exp) is False


def test_boundary_finance_25000_at_below():
    """Confirm ₹25,000 exactly does NOT require finance approval."""
    exp = Expense("BND-25k", "EMP-B", "Finance", "equipment", 25000.0, 30000.0)
    assert check_finance_approval(exp) is False


def test_boundary_finance_25001_above():
    """Confirm ₹25,001 DOES require finance approval."""
    exp = Expense("BND-25k1", "EMP-B", "Finance", "equipment", 25001.0, 30000.0)
    assert check_finance_approval(exp) is True


def test_boundary_executive_50000_at_below():
    """Confirm ₹50,000 exactly does NOT require executive approval."""
    exp = Expense("BND-50k", "EMP-B", "Exec", "equipment", 50000.0, 60000.0)
    assert check_executive_approval(exp) is False


def test_boundary_executive_50001_above():
    """Confirm ₹50,001 DOES require executive approval."""
    exp = Expense("BND-50k1", "EMP-B", "Exec", "equipment", 50001.0, 60000.0)
    assert check_executive_approval(exp) is True


# =====================================================================
# 3. INTERACTION TESTS (Scenarios A-D and complex interactions)
# =====================================================================

def test_interaction_travel_manager_threshold():
    """Example B: ₹12,000 travel expense (exceeds ₹10k, below ₹15k, travel HR compliance applied)."""
    exp = Expense("INT-01", "EMP-I1", "Sales", "travel", 12000.0, 20000.0)
    result = submit_expense(exp)
    assert result.status == "APPROVED"
    assert any(log["action"] == "OVERRIDE_MANAGER_TRAVEL" for log in result.audit_log)
    assert any(log["action"] == "COMPLIANT_HR" for log in result.audit_log)


def test_interaction_travel_manager_override():
    """Travel + Manager override interaction: override applies but HR compliance remains mandatory."""
    exp = Expense("INT-02", "EMP-I2", "Marketing", "travel", 14000.0, 25000.0)
    assert manager_override(exp) is True
    assert check_hr_compliance(exp) is True
    result = submit_expense(exp)
    assert result.status == "APPROVED"


def test_interaction_emergency_travel():
    """Example C: Emergency travel expense bypasses manager stage but NOT HR compliance or budget."""
    exp = Expense("INT-03", "EMP-I3", "Field", "travel", 18000.0, 30000.0, is_emergency=True)
    result = submit_expense(exp)
    assert result.status == "APPROVED"
    assert any(log["action"] == "BYPASS_MANAGER_EMERGENCY" for log in result.audit_log)
    assert any(log["action"] == "COMPLIANT_HR" for log in result.audit_log)


def test_interaction_emergency_budget_failure():
    """Emergency expense exceeding budget MUST fail budget validation and be REJECTED."""
    exp = Expense("INT-04", "EMP-I4", "Field", "travel", 35000.0, 30000.0, is_emergency=True)
    result = submit_expense(exp)
    assert result.status == "REJECTED"
    assert any("REJECTED_BUDGET" in log["action"] for log in result.audit_log)


def test_interaction_high_value_travel():
    """Example D: ₹60,000 travel expense requiring Manager, Finance, Executive, and HR compliance."""
    exp = Expense("INT-05", "EMP-I5", "Exec", "travel", 60000.0, 100000.0)
    result = submit_expense(exp)
    assert result.status == "APPROVED"
    assert any(log["action"] == "APPROVED_MANAGER" for log in result.audit_log)
    assert any(log["action"] == "COMPLIANT_HR" for log in result.audit_log)
    assert any(log["action"] == "APPROVED_FINANCE" for log in result.audit_log)
    assert any(log["action"] == "APPROVED_EXECUTIVE" for log in result.audit_log)


def test_interaction_final_approval_incomplete_compliance():
    """Final approval fails if HR compliance is not satisfied for travel expense."""
    exp = Expense("INT-06", "EMP-I6", "Legal", "travel", 8000.0, 15000.0)
    approved = final_approval(exp, budget_passed=True, manager_passed=True, hr_passed=False)
    assert approved is False
    assert exp.status == "REJECTED"
