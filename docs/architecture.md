# CEWS Architecture Document — DA1

## 1. System Overview
The Controlled Enterprise Expense Workflow System (CEWS) is a deterministic, modular Python application designed as the controlled target system for the Requirement Collision Engine (RCE) research project.

CEWS models an organization's expense approval workflow across multiple departments, enforcing ten business rules (`REQ-01` through `REQ-10`) with explicit requirement-to-code-to-test traceability.

## 2. System Architecture Diagram

```text
                             +------------------------+
                             |   Expense Submission   |
                             |    (cews/expense.py)   |
                             +-----------+------------+
                                         |
                                         v
                             +------------------------+
                             |   Budget Validation    |
                             |   (cews/approval.py)   |
                             +-----------+------------+
                                         |
                                         v
                             +------------------------+
                             |   Approval Thresholds  |
                             |   & Override / Emerg   |
                             |   (cews/approval.py)   |
                             +-----------+------------+
                                         |
                                         v
                             +------------------------+
                             |   HR Compliance Gate   |
                             |  (cews/compliance.py)  |
                             +-----------+------------+
                                         |
                                         v
                             +------------------------+
                             |   Final Approval Gate  |
                             |   (cews/approval.py)   |
                             +-----------+------------+
                                         |
                                         v
                             +------------------------+
                             |    Audit Log Service   |
                             |     (cews/audit.py)    |
                             +------------------------+
```

## 3. Module Responsibilities

| Module | Responsibility | Key Functions | Requirements Covered |
| :--- | :--- | :--- | :--- |
| [`cews.expense`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/expense.py) | Expense data representation, input validation, and main workflow orchestration. | `Expense`, `validate_expense_input()`, `submit_expense()` | REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10 |
| [`cews.approval`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/approval.py) | Business threshold logic, manager travel override, emergency handling, and final gate. | `validate_budget()`, `check_manager_approval()`, `check_finance_approval()`, `check_executive_approval()`, `manager_override()`, `process_emergency_expense()`, `final_approval()` | REQ-02, REQ-03, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10 |
| [`cews.compliance`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/compliance.py) | Regulatory and HR compliance rules for travel-related expenses. | `check_hr_compliance()` | REQ-04 |
| [`cews.audit`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/audit.py) | Workflow audit log recording capturing request_id, actor, action, and timestamp. | `record_audit_log()` | REQ-09 |

## 4. Workflow Stages
1. **Submission**: Validate inputs, initialize audit history.
2. **Budget Check**: Validate amount against budget (`amount <= budget`).
3. **Approval Escalation**:
   - Manager (> ₹10,000)
   - Finance (> ₹25,000)
   - Executive (> ₹50,000)
4. **Override / Emergency Evaluation**:
   - Manager Travel Override (< ₹15,000 travel, retains HR compliance)
   - Emergency Bypass (bypasses manager approval, retains budget & HR checks)
5. **HR Compliance**: Enforces HR compliance for all travel expenses.
6. **Final Gate**: Verifies all applicable mandatory approvals before setting status to `APPROVED` or `REJECTED`.

## 5. Data Model
Represented as a Python `@dataclass`:
- `request_id: str`
- `employee_id: str`
- `department: str`
- `expense_type: str`
- `amount: float`
- `budget: float`
- `is_emergency: bool`
- `status: str`
- `audit_log: List[Dict[str, Any]]`

## 6. Requirement Traceability Approach
Every business logic function contains an explicit `"""TRACE: REQ-XX"""` docstring. This allows future static analysis (AST parsing in DA2) to map requirements to code nodes automatically without dynamic tracing overhead.
