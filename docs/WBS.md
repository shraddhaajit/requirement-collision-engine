# Work Breakdown Structure (WBS) — CEWS (DA1)

## 1. Project Planning & Scoping
- **1.1 Scope Definition**: Freeze DA1 scope (CEWS target system only; DA2/DA3 features excluded per Section 34).
- **1.2 Environment Setup**: Initialize Git repository, Python virtual environment, pytest dependency, and folder structure.

## 2. Requirements Engineering
- **2.1 Requirements Specification**: Document 10 business requirements (`REQ-01` to `REQ-10`) with exact thresholds and constraints in [`requirements/requirements.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/requirements/requirements.md).
- **2.2 Traceability Planning**: Establish requirement trace tag convention (`"""TRACE: REQ-XX"""`) and create [`docs/RTM.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/docs/RTM.md).

## 3. System Design
- **3.1 Data Model Design**: Define `Expense` dataclass schema with 9 required attributes in [`cews/expense.py`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/expense.py).
- **3.2 Module Architecture Design**: Design modular system decomposition ([`cews/approval.py`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/approval.py), [`cews/compliance.py`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/compliance.py), [`cews/audit.py`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/cews/audit.py)) promoting low coupling and high cohesion.

## 4. Development & Implementation
- **4.1 Expense Core & Validation**: Implement `Expense`, `validate_expense_input()`, and `submit_expense()` workflow orchestrator.
- **4.2 Approval Logic**: Implement `validate_budget()`, `check_manager_approval()`, `check_finance_approval()`, `check_executive_approval()`, `manager_override()`, `process_emergency_expense()`, and `final_approval()`.
- **4.3 Compliance Verification**: Implement `check_hr_compliance()` for travel expense verification.
- **4.4 Audit Logging**: Implement `record_audit_log()` capturing `request_id`, `actor`, `action`, and `timestamp`.

## 5. Testing & Quality Assurance
- **5.1 Requirement Tests**: Write 10 individual requirement verification tests.
- **5.2 Boundary Tests**: Write 8 threshold boundary tests (₹10k, ₹15k, ₹25k, ₹50k).
- **5.3 Interaction Tests**: Write 6 complex interaction test scenarios (Scenarios A–D).
- **5.4 Baseline Execution**: Run `pytest` to confirm 100% deterministic test pass rate (24/24 passed).

## 6. Documentation & Demonstration
- **6.1 Project Documentation**: Author [`README.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/README.md), [`docs/architecture.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/docs/architecture.md), [`docs/WBS.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/docs/WBS.md), and [`docs/RMMM.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/docs/RMMM.md).
- **6.2 Demonstration Suite**: Implement runnable CLI demonstration in [`main.py`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/main.py) for 5 faculty scenarios.
