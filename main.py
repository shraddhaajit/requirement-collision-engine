"""Main entry point and CLI Demonstration for CEWS (Controlled Enterprise Expense Workflow System).

Demonstrates the 5 predefined faculty evaluation scenarios per Charter Section 20.
"""

from cews.expense import Expense, submit_expense
from cews.approval import (
    validate_budget,
    check_manager_approval,
    check_finance_approval,
    check_executive_approval,
)
from cews.compliance import check_hr_compliance


import sys

# Ensure UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def print_scenario_output(scenario_num: int, title: str, exp: Expense) -> None:
    """Format and print scenario results per Charter Section 19."""
    print("=" * 60)
    print(f"SCENARIO {scenario_num}: {title}")
    print("=" * 60)
    print(f"Request ID       : {exp.request_id}")
    print(f"Employee ID      : {exp.employee_id}")
    print(f"Department       : {exp.department}")
    print(f"Expense Type     : {exp.expense_type.capitalize()}")
    print(f"Amount           : Rs. {exp.amount:,.2f}")
    print(f"Department Budget: Rs. {exp.budget:,.2f}")
    print(f"Emergency Status : {'YES' if exp.is_emergency else 'NO'}")
    print("-" * 60)
    
    # Process workflow
    processed = submit_expense(exp)
    
    # Audit log actions recorded on processed expense
    actions = [log["action"] for log in processed.audit_log]

    # Evaluate rule indicators
    budget_pass = "PASS" if validate_budget(processed) else "FAIL"

    # Derive Manager Approval status from actual audit log actions
    if any("BYPASS_MANAGER_EMERGENCY" in a for a in actions):
        mgr_req = "BYPASSED (emergency, REQ-08)"
    elif any("OVERRIDE_MANAGER_TRAVEL" in a for a in actions):
        mgr_req = "OVERRIDDEN (REQ-07)"
    elif any("APPROVED_MANAGER" in a for a in actions):
        mgr_req = "APPROVED (standard)"
    else:
        mgr_req = "NOT REQUIRED"

    # Derive HR Compliance status via check_hr_compliance() call
    if check_hr_compliance(processed):
        hr_req = "COMPLIANT (REQ-04)" if processed.expense_type.lower() == "travel" else "NOT REQUIRED"
    else:
        hr_req = "NON-COMPLIANT"

    fin_req = "REQUIRED (> Rs. 25,000)" if check_finance_approval(processed) else "NOT REQUIRED"
    exec_req = "REQUIRED (> Rs. 50,000)" if check_executive_approval(processed) else "NOT REQUIRED"

    print(f"Budget Validation  : {budget_pass}")
    print(f"Manager Approval   : {mgr_req}")
    print(f"HR Compliance      : {hr_req}")
    print(f"Finance Approval   : {fin_req}")
    print(f"Executive Approval : {exec_req}")
    print("-" * 60)
    print(f"FINAL STATUS       : {processed.status}")
    print("-" * 60)
    print("Audit Log Actions Recorded:")
    for log in processed.audit_log:
        print(f"  - [{log['timestamp'][:19]}] Actor: {log['actor']:<10} Action: {log['action']}")
    print("\n")


def run_demonstration():
    """Run all 5 faculty demonstration scenarios."""
    print("\n" + "#" * 60)
    print("  CEWS DEMONSTRATION SUITE — DIGITAL ASSIGNMENT 1 (DA1)")
    print("#" * 60 + "\n")

    # Scenario 1 — Normal expense
    s1 = Expense("EXP-S1", "EMP-101", "Engineering", "supplies", 5000.0, 10000.0)
    print_scenario_output(1, "Normal Expense Submission", s1)

    # Scenario 2 — ₹12,000 travel expense (Manager threshold + Manager Travel Override + HR compliance)
    s2 = Expense("EXP-S2", "EMP-102", "Sales", "travel", 12000.0, 20000.0)
    print_scenario_output(2, "₹12,000 Travel Expense (Manager Travel Override)", s2)

    # Scenario 3 — Emergency expense (Bypasses manager stage, enforces budget validation)
    s3 = Expense("EXP-S3", "EMP-103", "Operations", "supplies", 18000.0, 25000.0, is_emergency=True)
    print_scenario_output(3, "Emergency Expense (Manager Bypass + Budget Validation)", s3)

    # Scenario 4 — ₹60,000 travel expense (Multi-rule: Manager, HR, Finance, Executive)
    s4 = Expense("EXP-S4", "EMP-104", "Executive", "travel", 60000.0, 100000.0)
    print_scenario_output(4, "₹60,000 Travel Expense (Multi-Level Approval Escalation)", s4)

    # Scenario 5 — Budget failure (Expense exceeds available budget)
    s5 = Expense("EXP-S5", "EMP-105", "Marketing", "supplies", 15000.0, 10000.0)
    print_scenario_output(5, "Budget Failure (Amount Exceeds Department Budget)", s5)


if __name__ == "__main__":
    run_demonstration()
