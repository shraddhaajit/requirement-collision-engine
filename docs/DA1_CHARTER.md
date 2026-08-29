# MASTER BUILD CHARTER — DIGITAL ASSIGNMENT 1

## Project: Requirement Collision Engine (RCE)

### DA1 Component: Controlled Enterprise Expense Workflow System (CEWS)

---

# 1. IMPORTANT BUILD INSTRUCTION

Build **ONLY Digital Assignment 1** in this phase.

Do **not** implement the Requirement Collision Engine, AST analysis, NetworkX graph analysis, Git-history mining, mutation testing, Streamlit dashboard, Pyvis visualization, Ollama/LLM integration, GitHub Actions PR blocking, or any other DA2/DA3 functionality.

However, **DA1 must be architected deliberately so that DA2 and DA3 can connect to it later without requiring a major rewrite.**

The project is **ONE software engineering project divided into THREE Digital Assignments**:

```text
ONE PROJECT
│
├── DA1 — Controlled Enterprise Expense Workflow System
│          Requirements + Implementation + Testing + Traceability
│
├── DA2 — Requirement Collision Engine
│          Static Analysis + AST + Git + NetworkX + Collision Detection
│
└── DA3 — Collision Verification & Quality Automation
           Mutation Testing + Severity + Dashboard + CI/CD
```

DA1 is the foundation.

The application created in DA1 is the **controlled target system** that the later Requirement Collision Engine will analyze.

---

# 2. PROJECT VISION

The overall project is called the:

**Requirement Collision Engine (RCE)**

The problem being investigated is:

> A software system can pass its existing tests while a new business requirement silently violates or bypasses an existing business rule.

The final project will eventually detect and verify these requirement collisions.

However, DA1 does not build the detection engine.

DA1 builds the controlled software environment in which those collisions can later be studied.

The DA1 system is:

**Controlled Enterprise Expense Workflow System (CEWS)**

CEWS simulates an organization's expense approval workflow.

It intentionally contains several interconnected business rules involving:

* expense submission
* budget validation
* manager approval
* HR compliance
* finance approval
* executive approval
* manager overrides
* emergency expenses
* audit logging
* final approval

These rules must be implemented cleanly and deterministically.

The complexity should come from **business-rule interaction**, not from unnecessary technical complexity.

---

# 3. PRIMARY OBJECTIVE OF DA1

The primary objective of DA1 is:

> Design, implement, test, and document a controlled enterprise expense workflow system with explicit requirement-to-code-to-test traceability.

DA1 must demonstrate the following Software Engineering concepts:

* Requirements Engineering
* Requirements Specification
* Requirement Traceability
* Software Design
* Modularity
* Cohesion and Coupling
* Project Planning
* Work Breakdown Structure
* Risk Management
* Agile/XP development practices
* Software Testing
* Regression Testing
* Version Control
* Software Documentation

---

# 4. DA1 SUCCESS CRITERIA

DA1 is considered complete only when all of the following are satisfied:

### Requirements

* 10 clearly defined business requirements exist.
* Every requirement has a unique ID.
* Requirements are internally consistent.
* Requirements are implemented in the CEWS application.
* Requirements are traceable to source-code functions.
* Requirements are traceable to test cases.

### Application

* CEWS runs successfully.
* The complete expense workflow is implemented.
* All 10 business rules are represented in executable logic.
* Rules can interact with one another.
* Invalid requests are handled safely.
* The application produces deterministic results.

### Testing

* A pytest test suite exists.
* Approximately 20 meaningful tests are implemented.
* Tests cover individual rules.
* Tests cover boundary conditions.
* Tests cover interactions between rules.
* Baseline tests pass.

### Documentation

* Requirements are documented.
* RTM is documented.
* Architecture is documented.
* WBS is documented.
* RMMM is documented.
* README explains how to run the project.
* DA1 report/evidence can be generated from the completed work.

### Version Control

* Project is maintained using Git.
* Commits are meaningful and logically grouped.
* The repository has a clean structure.

---

# 5. TECHNOLOGY CONSTRAINTS

Use a simple Python-based implementation.

### Required

* Python
* pytest
* Git

### Allowed

* Python standard library
* Lightweight packages only where genuinely useful

### Avoid

Do NOT introduce unnecessary technologies.

Do not add:

* React
* Node.js
* Flask
* Django
* PostgreSQL
* MongoDB
* Docker
* Kubernetes
* cloud services
* external APIs
* LLM APIs
* authentication systems
* payment gateways

The purpose of DA1 is the **software engineering model and business-rule implementation**, not technology complexity.

A local, deterministic Python application is sufficient.

---

# 6. CLOSED-WORLD ASSUMPTION

DA1 must operate under a **Closed-World Assumption**.

The application is a controlled target created specifically for the RCE project.

Do not attempt to make CEWS a universal enterprise expense platform.

Do not design it to support arbitrary external applications.

The system should be:

* small
* deterministic
* understandable
* testable
* traceable
* intentionally structured
* easy for static analysis to inspect later

The goal is precision rather than generality.

---

# 7. THE TEN BUSINESS REQUIREMENTS

These requirements are the authoritative requirements for DA1.

Do not casually change their meaning.

## REQ-01 — Expense Submission

An employee can submit an expense request containing:

* request ID
* employee ID
* department
* expense type
* amount
* supporting details

A submitted expense must enter the workflow.

---

## REQ-02 — Budget Validation

Every submitted expense must be checked against the available department budget before approval.

If the expense exceeds the available budget, it must not proceed to approval.

---

## REQ-03 — Manager Approval

Expenses above **₹10,000** require manager approval before further processing.

Expenses at or below ₹10,000 do not require manager approval under this threshold rule.

---

## REQ-04 — HR Compliance

Every travel-related expense must undergo HR compliance verification before final approval.

This rule is intentionally important because later assignments will investigate whether another rule can accidentally bypass it.

---

## REQ-05 — Finance Approval

Expenses above **₹25,000** require finance approval.

---

## REQ-06 — Executive Approval

Expenses above **₹50,000** require executive approval.

---

## REQ-07 — Manager Travel Override

A manager can approve a travel expense below **₹15,000** without the normal manager approval stage.

However:

* HR compliance remains mandatory.
* Audit logging remains mandatory.
* Final approval conditions still apply.

This requirement must NOT bypass mandatory HR compliance.

This is an intentional interaction point for future collision analysis.

---

## REQ-08 — Emergency Expense

An expense marked as emergency may bypass manager approval.

However:

* budget validation remains mandatory
* audit logging remains mandatory
* other mandatory conditions still apply

Emergency status must not mean "approve without validation."

---

## REQ-09 — Audit Logging

Every important workflow action must be recorded.

At minimum, the audit log must capture:

* request ID
* user/actor
* action
* timestamp

Actions include:

* submission
* approval
* rejection
* override
* bypass

---

## REQ-10 — Final Approval

An expense can receive final approval only when all mandatory conditions applicable to that expense have been satisfied.

This is the final gate.

Final approval must not blindly trust an earlier approval.

---

# 8. IMPORTANT BUSINESS-RULE INTERACTIONS

The application must not implement the requirements as ten completely isolated functions.

The rules need meaningful interactions.

Examples:

### Example A — Normal travel expense

```text
Travel expense
      ↓
Budget validation
      ↓
Manager approval if required
      ↓
HR compliance
      ↓
Finance if required
      ↓
Executive if required
      ↓
Final approval
      ↓
Audit log
```

### Example B — ₹12,000 travel expense

This expense:

* exceeds ₹10,000
* is below ₹15,000
* is travel

Therefore:

* manager-related logic applies
* travel HR compliance applies
* audit logging applies
* final approval must consider all applicable rules

This is a key future collision scenario.

---

### Example C — Emergency travel expense

Emergency status may bypass the manager approval stage.

It must NOT bypass:

* budget validation
* HR compliance
* audit logging
* final approval conditions

---

### Example D — ₹60,000 expense

Because the amount exceeds:

* ₹10,000 → manager approval required
* ₹25,000 → finance approval required
* ₹50,000 → executive approval required

If it is also travel:

* HR compliance is required

This demonstrates multiple simultaneous business rules.

---

# 9. CEWS DATA MODEL

Create a simple expense representation.

Each expense should contain approximately:

```text
request_id
employee_id
department
expense_type
amount
budget
is_emergency
status
audit_log
```

Do not over-engineer the data model.

A Python class/dataclass is appropriate.

Use clear field names.

---

# 10. CEWS MODULE STRUCTURE

Use a modular structure similar to:

```text
rce-project/
│
├── cews/
│   ├── __init__.py
│   ├── expense.py
│   ├── approval.py
│   ├── compliance.py
│   └── audit.py
│
├── tests/
│   └── test_cews.py
│
├── requirements/
│   └── requirements.md
│
├── docs/
│   └── RTM.md
│
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

The exact structure may be improved if there is a strong technical reason.

Do not create dozens of files.

Keep the project understandable.

---

# 11. FUNCTION DESIGN

The following logical functions should exist or have equivalent clearly identifiable functions.

```text
submit_expense()
validate_budget()
check_manager_approval()
check_hr_compliance()
check_finance_approval()
check_executive_approval()
manager_override()
process_emergency_expense()
record_audit_log()
final_approval()
```

Each function must have one clear responsibility where practical.

Do not create meaningless wrapper functions simply to increase the file count.

---

# 12. REQUIREMENT TRACE TAGGING

This is extremely important.

Every requirement-related implementation must contain an explicit trace identifier.

Use a simple format such as:

```python
"""TRACE: REQ-04"""
```

or an equivalent comment/docstring format.

Examples:

```python
def validate_budget(expense):
    """TRACE: REQ-02"""
```

```python
def check_hr_compliance(expense):
    """TRACE: REQ-04"""
```

If a function genuinely implements multiple requirements:

```python
def final_approval(expense):
    """TRACE: REQ-04, REQ-07, REQ-08, REQ-10"""
```

Do not add incorrect trace IDs merely to make the RTM look complete.

The traceability must reflect the actual implementation.

---

# 13. TEST DESIGN

Create approximately **20 pytest test cases**.

Do not simply create 20 copies of the same test.

Tests should cover:

### Requirement tests

* expense submission
* budget validation
* manager threshold
* HR compliance
* finance threshold
* executive threshold
* manager override
* emergency bypass
* audit logging
* final approval

### Boundary tests

Examples:

* ₹10,000
* ₹10,001
* ₹15,000
* ₹15,001
* ₹25,000
* ₹25,001
* ₹50,000
* ₹50,001

Be deliberate about whether the requirement uses "above" or "below."

### Interaction tests

Examples:

* travel + manager threshold
* travel + manager override
* emergency + travel
* emergency + budget failure
* high-value travel
* final approval with incomplete compliance

The tests should demonstrate that the business rules work together.

---

# 14. BASELINE TEST SUITE

DA1 must establish a clean baseline.

The final DA1 test suite should pass before DA1 is considered complete.

The project should be able to demonstrate:

```text
pytest
↓
All baseline tests pass
```

This baseline is important because DA3 will eventually use mutation testing to evaluate whether tests can detect intentionally altered business logic.

Do NOT implement mutation testing in DA1.

Simply create a strong baseline test suite.

---

# 15. REQUIREMENT TRACEABILITY MATRIX

Create a complete RTM.

At minimum:

| Requirement | Implementation              | Test Case | Status      |
| ----------- | ---------------------------- | --------- | ----------- |
| REQ-01      | submit_expense()            | TC-01     | Implemented |
| REQ-02      | validate_budget()            | TC-02     | Implemented |
| REQ-03      | check_manager_approval()     | TC-03     | Implemented |
| REQ-04      | check_hr_compliance()        | TC-04     | Implemented |
| REQ-05      | check_finance_approval()     | TC-05     | Implemented |
| REQ-06      | check_executive_approval()   | TC-06     | Implemented |
| REQ-07      | manager_override()           | TC-07     | Implemented |
| REQ-08      | process_emergency_expense()  | TC-08     | Implemented |
| REQ-09      | record_audit_log()           | TC-09     | Implemented |
| REQ-10      | final_approval()              | TC-10     | Implemented |

The actual test mapping may contain multiple test cases per requirement.

The RTM must represent the actual codebase.

---

# 16. ARCHITECTURAL PRINCIPLES

Use the following principles:

### Modularity

Separate:

* expense handling
* approval logic
* compliance logic
* audit logic

where appropriate.

### High Cohesion

Each module should contain closely related responsibilities.

### Low Coupling

Avoid unnecessary dependencies between modules.

### Traceability

Requirements must be identifiable in the implementation.

### Determinism

The same input should produce the same business decision.

Avoid random behavior.

---

# 17. MAIN WORKFLOW

The system should provide a clear way to process an expense.

Conceptually:

```text
Submit
  ↓
Budget Validation
  ↓
Determine Required Approvals
  ↓
Apply Emergency / Override Rules
  ↓
HR Compliance if Travel
  ↓
Finance if Required
  ↓
Executive if Required
  ↓
Final Approval
  ↓
Audit Logging
```

The implementation may structure this differently internally, but the business behavior must follow the requirements.

---

# 18. ERROR HANDLING

Handle invalid inputs sensibly.

Examples:

* invalid amount
* missing employee ID
* missing request ID
* unsupported expense type
* negative budget
* expense exceeding budget

The application should fail safely.

Do not allow invalid data to silently receive approval.

---

# 19. OUTPUT

The application does not need a sophisticated user interface.

A CLI demonstration is sufficient.

For example:

```text
Expense Request: EXP-001
Type: Travel
Amount: ₹12,000

Budget Validation: PASS
Manager Requirement: YES
HR Compliance: REQUIRED
Finance Approval: NOT REQUIRED
Executive Approval: NOT REQUIRED

Final Status: APPROVED
```

The exact formatting can be improved.

The output should be clear enough for a faculty demonstration.

---

# 20. DA1 DEMONSTRATION SCENARIOS

Prepare several predefined demonstration scenarios.

At minimum:

### Scenario 1 — Normal expense

Demonstrates:

* submission
* budget validation
* normal approval

### Scenario 2 — ₹12,000 travel expense

Demonstrates:

* travel classification
* manager threshold
* HR compliance
* traceability

### Scenario 3 — Emergency expense

Demonstrates:

* emergency bypass
* mandatory budget validation
* mandatory audit logging

### Scenario 4 — ₹60,000 travel expense

Demonstrates:

* manager approval
* HR compliance
* finance approval
* executive approval
* final approval

### Scenario 5 — Budget failure

Demonstrates that an expense exceeding its budget cannot be approved.

These scenarios should be deterministic and easy to reproduce.

---

# 21. PROJECT DOCUMENTATION

Create concise project documentation.

## README.md

Include:

* project name
* project purpose
* DA1 scope
* requirements summary
* project structure
* installation
* how to run
* how to run tests
* sample usage

Do not write a massive README.

---

# 22. REQUIREMENTS DOCUMENT

Create:

```text
requirements/requirements.md
```

Include:

* project purpose
* 10 requirements
* requirement descriptions
* assumptions
* constraints

Use the exact REQ identifiers.

---

# 23. ARCHITECTURE DOCUMENT

Create a concise architecture document containing:

* system overview
* module responsibilities
* workflow
* data model
* traceability approach

Include at least one simple architecture diagram.

---

# 24. WBS

Create a basic WBS for DA1.

Example:

```text
1. Planning
   1.1 Define scope
   1.2 Define requirements

2. Requirements
   2.1 Define business rules
   2.2 Create RTM

3. Design
   3.1 Design data model
   3.2 Design modules

4. Development
   4.1 Implement expense handling
   4.2 Implement approval logic
   4.3 Implement compliance
   4.4 Implement audit logging

5. Testing
   5.1 Unit tests
   5.2 Integration tests
   5.3 Regression testing

6. Documentation
   6.1 README
   6.2 Architecture
   6.3 DA1 report
```

---

# 25. RMMM

Create a simple Risk, Mitigation, Monitoring and Management plan.

Include risks such as:

### Requirement inconsistency

Mitigation:
Maintain a single authoritative requirements document and RTM.

### Rule interaction errors

Mitigation:
Use explicit interaction tests.

### Implementation complexity

Mitigation:
Keep CEWS small and modular.

### Testing gaps

Mitigation:
Map every requirement to test cases.

### Future RCE incompatibility

Mitigation:
Use deterministic Python code and explicit requirement trace tags.

---

# 26. AGILE / XP CONNECTION

DA1 should demonstrate the course concepts rather than merely mention them.

Use a small iterative development process.

Suggested iterations:

```text
Sprint 1
Requirements + Design

Sprint 2
Core Expense + Budget

Sprint 3
Approval + Compliance + Audit

Sprint 4
Testing + Traceability + Documentation
```

Each sprint should have:

* objective
* tasks
* deliverable
* Definition of Done

Do not over-document this.

---

# 27. DEFINITION OF DONE

DA1 is done when:

* All 10 requirements are frozen.
* CEWS implementation is complete.
* All major functions are implemented.
* Trace tags are present.
* Test suite is complete.
* Baseline tests pass.
* RTM is complete.
* Documentation is complete.
* README works.
* Demonstration scenarios work.
* Git repository is clean and reproducible.

---

# 28. FUTURE CONNECTION — DA2

DA2 is NOT part of this build.

The DA1 architecture must simply make DA2 possible.

DA2 will eventually build the **Requirement Collision Engine**.

It will inspect CEWS using:

```text
Python AST
+
Requirement Trace Tags
+
Git History
+
NetworkX
```

The eventual analysis path will be approximately:

```text
Requirement
     ↓
Python Function
     ↓
Code Dependency
     ↓
Related Requirement
     ↓
Potential Collision
```

DA1 must therefore preserve:

* explicit requirement IDs
* deterministic functions
* modular source files
* meaningful Git history
* traceable tests

Do NOT build the RCE now.

---

# 29. FUTURE CONNECTION — DA3

DA3 will use the collision information produced by DA2.

Eventually:

```text
Collision Detected
       ↓
Targeted Mutation
       ↓
Existing Tests
       ↓
Mutation Survives?
       ↓
Severity
       ↓
Quality Report
       ↓
CI/CD Decision
```

DA1 only needs to provide:

* a working test suite
* deterministic business logic
* meaningful rule interactions
* clean source structure

Do NOT install or implement mutmut in DA1 unless absolutely necessary for environment compatibility testing. The actual mutation-testing work belongs to DA3.

---

# 30. FUTURE CONNECTION — DASHBOARD

A future DA3 dashboard may display:

* requirements
* affected functions
* dependency relationships
* collision status
* mutation results
* severity
* test results

DA1 does not need Streamlit or Pyvis.

Keep the CEWS implementation independent from any future visualization layer.

---

# 31. FUTURE CONNECTION — LOCAL AI

The eventual project may use a locally hosted LLM such as Ollama to generate a short executive explanation of a detected collision.

This is entirely outside DA1.

Do not add AI functionality to CEWS.

DA1 should remain deterministic and independent of external models.

---

# 32. GIT REQUIREMENTS

Initialize the project as a Git repository.

Use meaningful commits.

Examples:

```text
initialise DA1 project structure
define CEWS requirements
implement expense model
implement budget validation
implement approval workflow
implement HR compliance
implement audit logging
add baseline test suite
add requirement traceability
complete DA1 documentation
```

Do not make one enormous commit containing the entire project.

The Git history is important because DA2 will eventually use historical information to study software evolution and co-change relationships.

---

# 33. CODE QUALITY

The code should be:

* readable
* deterministic
* modular
* reasonably documented
* PEP 8 compliant
* easy to inspect using Python AST
* free from unnecessary abstractions

Avoid:

* overengineering
* design patterns that provide no value
* excessive classes
* deeply nested logic
* unnecessary dependencies
* hidden global state
* complicated frameworks

The application should look like a deliberately engineered controlled research target.

---

# 34. WHAT NOT TO DO

Do NOT:

* build DA2 early
* build DA3 early
* implement the RCE
* implement graph traversal
* implement mutation testing
* implement GitHub Actions
* implement Streamlit
* implement Pyvis
* implement Ollama
* build a production-scale expense platform
* add authentication
* add payments
* add cloud infrastructure
* use external APIs
* create a frontend unless it is genuinely necessary for DA1
* artificially inflate the project with unnecessary features

The objective is **quality and traceability, not feature count**.

---

# 35. FINAL DA1 ARCHITECTURE

The completed DA1 should conceptually look like:

```text
                    CEWS
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
     Expense      Approval     Compliance
     Handling      Rules          Rules
        │            │            │
        └────────────┼────────────┘
                     ▼
                 Audit Log
                     │
                     ▼
                 Test Suite
                     │
                     ▼
                    RTM
```

Every important component must remain traceable to the original requirements.

---

# 36. FINAL DA1 DELIVERABLE

At the end of the build, the repository should contain a working CEWS implementation and its engineering artifacts.

The final DA1 package should include:

```text
Working CEWS
+
10 Requirements
+
RTM
+
~20 Tests
+
Architecture
+
WBS
+
RMMM
+
README
+
Git History
+
DA1 Report
```

This constitutes the complete **DA1 foundation** of the Requirement Collision Engine project.

---

# 37. FINAL INSTRUCTION TO THE BUILD AGENT

Build the project incrementally.

First:

1. Create the repository structure.
2. Create the requirements document.
3. Implement the expense data model.
4. Implement each business rule.
5. Connect the rules into the CEWS workflow.
6. Add requirement trace tags.
7. Write the test suite.
8. Run and fix all baseline tests.
9. Create the RTM.
10. Create architecture and project documentation.
11. Verify the demonstration scenarios.
12. Initialize/maintain Git history.
13. Perform a final DA1 quality review.

At every stage, prioritize **correctness, traceability, simplicity, and future compatibility**.

Do not proceed into DA2 or DA3 implementation.

When finished, report:

* what was built
* project structure
* requirements implemented
* tests created
* test results
* traceability coverage
* demonstration scenarios
* documentation created
* Git status
* any remaining DA1 issues

The final output must represent a **complete, working DA1**, not a prototype or placeholder.

## END OF DA1 BUILD CHARTER
