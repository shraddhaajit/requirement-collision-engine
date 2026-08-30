# Controlled Enterprise Expense Workflow System (CEWS) — DA1

**Digital Assignment 1 (DA1) component of the Requirement Collision Engine (RCE) project.**

---

## 1. Project Purpose
CEWS is a controlled, deterministic enterprise expense approval workflow application built to study requirement interactions, rule collisions, and requirement-to-code-to-test traceability. It acts as the foundational target software system for static analysis (DA2) and mutation testing (DA3).

---

## 2. DA1 Scope
- **Included**: 10 explicit business requirements (`REQ-01` to `REQ-10`), modular business logic (`cews/`), baseline pytest suite (24 tests), bi-directional RTM, system architecture, WBS, RMMM, and CLI demonstration (`main.py`).
- **Excluded**: Requirement Collision Engine, AST parsing, Git graph analysis, mutation testing, Streamlit dashboard, LLM integration, databases, or external APIs (per Charter Section 34).

---

## 3. Business Requirements Summary
- **REQ-01**: Expense Submission
- **REQ-02**: Budget Validation
- **REQ-03**: Manager Approval (> ₹10,000)
- **REQ-04**: HR Compliance (Travel expenses)
- **REQ-05**: Finance Approval (> ₹25,000)
- **REQ-06**: Executive Approval (> ₹50,000)
- **REQ-07**: Manager Travel Override (< ₹15,000 travel, retains HR compliance)
- **REQ-08**: Emergency Expense Bypass (bypasses manager approval, retains budget validation)
- **REQ-09**: Audit Logging (`request_id`, `actor`, `action`, `timestamp`)
- **REQ-10**: Final Approval Gate (enforces all mandatory conditions)

---

## 4. Project Structure
```text
sw theory project/
│
├── cews/
│   ├── __init__.py
│   ├── expense.py       # Expense dataclass & submit_expense workflow
│   ├── approval.py      # Thresholds, overrides, emergency & final gate
│   ├── compliance.py    # HR compliance verification
│   └── audit.py         # Audit log recording service
│
├── tests/
│   ├── __init__.py
│   └── test_cews.py     # 24 pytest tests (Requirement, Boundary, Interaction)
│
├── requirements/
│   └── requirements.md  # Authoritative requirements document
│
├── docs/
│   ├── DA1_CHARTER.md   # Master build charter
│   ├── RTM.md           # Requirement Traceability Matrix
│   ├── architecture.md  # Architecture overview & workflow diagram
│   ├── WBS.md           # Work Breakdown Structure
│   └── RMMM.md          # Risk Mitigation Plan
│
├── main.py              # Runnable CLI demo for 5 faculty scenarios
├── requirements.txt     # Python dependencies (pytest)
├── README.md            # Project guide
└── .gitignore
```

---

## 5. Installation & Usage

### 5.1 Environment Setup
```bash
# Initialize virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 5.2 Running the Demonstration CLI Scenarios
Run the 5 predefined faculty demonstration scenarios:
```bash
python main.py
```

### 5.3 Running the Test Suite
Run the full baseline test suite with verbose output:
```bash
pytest -v
```

---

## 6. Sample Python Usage
```python
from cews.expense import Expense, submit_expense

# Create a ₹12,000 travel expense request
expense = Expense(
    request_id="EXP-DEMO",
    employee_id="EMP-101",
    department="Sales",
    expense_type="travel",
    amount=12000.0,
    budget=20000.0
)

# Submit into CEWS workflow
processed_expense = submit_expense(expense)

print(f"Status: {processed_expense.status}")
# Output: Status: APPROVED
```
