# 6-Minute Demonstration Video Script & Terminal Walkthrough

**Project Title**: Requirement Collision Engine (RCE)  
**Target Duration**: 06:00 Minutes (Strictly timed for academic/laboratory evaluation)  
**Tone**: Professional, confident, and technical  
**Presenter Checklist Before Recording**:
1. Open PowerShell terminal in the repository root: `c:\Users\shrad\OneDrive\Desktop\sw theory project`
2. Activate virtual environment: `.\.venv\Scripts\Activate.ps1`
3. Set terminal font size to **18pt** and window resolution to **1080p** (1920x1080)
4. Have this script open on a second display or side window for smooth narration

---

## ⏱️ Video Timeline Summary

| Segment | Timestamp | Duration | Focus Area |
|---|---|---|---|
| **Phase 1** | `0:00 – 0:45` | 45 sec | Introduction, Problem Statement & Core Motivation |
| **Phase 2** | `0:45 – 1:45` | 60 sec | Reference Application (CEWS) & The Illusion of Passing Tests |
| **Phase 3** | `1:45 – 3:00` | 75 sec | RCE Static Collision Detection (Rules B & C with AST Evidence) |
| **Phase 4** | `3:00 – 4:00` | 60 sec | Graph-Based Change-Impact Analysis & Regression Pruning |
| **Phase 5** | `4:00 – 4:45` | 45 sec | Generalization Across Independent Domains (Logistics & Inventory) |
| **Phase 6** | `4:45 – 5:25` | 40 sec | CI/CD Strict Quality Gates & Machine-Readable JSON Export |
| **Phase 7** | `5:25 – 6:00` | 35 sec | Full 125-Test Suite Execution & Conclusion |

---

## 🎙️ Complete Scene-by-Scene Script

---

### Phase 1: Introduction & Problem Statement (`0:00 – 0:45` | 45s)

#### 🖥️ What to Show on Screen:
* Display your title slide or the top of [`README.md`](file:///c:/Users/shrad/OneDrive/Desktop/sw%20theory%20project/README.md) showing the architecture flowchart.

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"Hello everyone. Today I am presenting the **Requirement Collision Engine (RCE)**—a general-purpose static analysis and change-impact engine designed to solve one of the most insidious failure modes in software engineering.*
>
> *In evolving enterprise systems, newly introduced business requirements frequently contradict, overlap, or bypass existing constraints. Crucially, a software system can pass **100% of its existing unit and regression tests**, yet silently harbor conflicting business rules in production.*
>
> *Traditional testing only verifies code against known inputs. RCE takes a fundamentally different approach: it parses natural Markdown specifications, analyzes Python Abstract Syntax Trees without executing target code, constructs a bipartite knowledge graph in NetworkX, and deterministically identifies requirement collisions before deployment."*

---

### Phase 2: Reference System (CEWS) & Passing Tests (`0:45 – 1:45` | 60s)

#### 🖥️ What to Run in Terminal:
```powershell
python main.py
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"To demonstrate this challenge, we first examine our reference target application: the **Controlled Enterprise Expense Workflow System (CEWS)**.*
>
> *CEWS encodes ten formal business requirements—including department budget checks, a ten-thousand-rupee manager approval threshold, travel exceptions, and emergency bypasses. Running `main.py` processes five live evaluation scenarios, from automated approvals to multi-level executive escalations and budget rejections. Every action is tracked in an immutable audit log."*

#### 🖥️ What to Run in Terminal:
```powershell
.venv\Scripts\pytest -v tests/test_cews.py
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"Now watch our test suite: all twenty-four CEWS unit and boundary tests execute and pass completely green.*
>
> *In a traditional software lifecycle, this build would be approved for production. But let us see what the Requirement Collision Engine uncovers when analyzing the actual AST logic."*

---

### Phase 3: Static Collision Detection in Action (`1:45 – 3:00` | 75s)

#### 🖥️ What to Run in Terminal:
```powershell
cls
python -m rce.cli
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"We now invoke RCE via its command-line interface. Without executing a single line of target code, RCE parses ten Markdown requirements, inspects six application modules, extracts fifty-three decision conditions, and synthesizes a two-hundred-and-thirteen-node knowledge graph.*
>
> *Immediately, RCE detects three critical requirement collisions with grounded evidence:*
>
> *First, **Finding 1 under Rule B**: A boundary condition collision on variable `amount` between ten thousand and fifteen thousand rupees. Requirement REQ-03 mandates manager approval above ten thousand, but REQ-07 allows manager travel override below fifteen thousand. In that five-thousand-rupee window, both conditions simultaneously evaluate to true. RCE cites the exact file and lines—`approval.py` line 20 and line 43.*
>
> *Second, **Findings 2 and 3 under Rule C**: Override and bypass interactions. RCE flags that the `final_approval` gate at line 87 alters standard enforcement flow for emergency and travel exceptions.*
>
> *These are not generic linter warnings—they are mathematically grounded AST facts pinpointed for human architectural review."*

---

### Phase 4: Change-Impact Analysis & Test Pruning (`3:00 – 4:00` | 60s)

#### 🖥️ What to Run in Terminal:
```powershell
python -m rce.cli --impact REQ-07
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"When a requirement changes, software engineers struggle to identify everything that could break. RCE solves this with graph-based change-impact analysis.*
>
> *Here, we query the impact of modifying **Requirement REQ-07**. Using breadth-first graph traversal, RCE systematically maps:*
> * Direct impacts at Hop 1—such as implementing functions and enclosing modules.*
> * Transitive impacts at Hops 2 and 3—tracing caller functions, dependent requirements, and callers across the call hierarchy.*
>
> *Most importantly, look at the bottom section: RCE automatically generates a **Recommended Regression Verification Test list**. Instead of blindly re-running thousands of irrelevant tests, QA engineers receive the exact subset of targeted pytest commands needed to verify this change."*

---

### Phase 5: Generalization Across Independent Domains (`4:00 – 4:45` | 45s)

#### 🖥️ What to Run in Terminal:
```powershell
cls
.venv\Scripts\pytest -v tests/test_rce_validation_projects.py
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"A critical question for our research: is RCE tied to enterprise expense workflows? The answer is an emphatic no.*
>
> *In `test_rce_validation_projects.py`, we validate RCE across multiple independent domains:*
> * In **Project A—Logistics and Freight**, RCE detects weight threshold overlaps between heavy freight surcharges and express waivers, while proving unrelated variables like `zone_code` generate zero false alarms.*
> * In **Project B—Inventory Management**, RCE detects quantity collisions between retail caps and wholesale bulk minimums, while verifying that disjoint stock levels are completely non-conflicting.*
> * We also test clean projects and syntax-error handling. All six cross-domain validation tests pass in just over one second."*

---

### Phase 6: CI/CD Quality Gates & JSON Export (`4:45 – 5:25` | 40s)

#### 🖥️ What to Run in Terminal:
```powershell
python -m rce.cli --strict
echo "Exit Code: $LASTEXITCODE"
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"RCE is designed directly for modern DevSecOps pipelines. With the `--strict` flag enabled, RCE returns exit code `2` whenever potential collisions are discovered, immediately halting pull requests before problematic business logic merges.*
>
> *Furthermore, for automated tooling, we can export machine-readable JSON reports:"*

#### 🖥️ What to Run in Terminal:
```powershell
python -m rce.cli --format json --output report.json
Get-Content report.json -TotalCount 25
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"This structured payload feeds directly into SonarQube, security dashboards, or automated code review bots."*

---

### Phase 7: Full Test Suite & Conclusion (`5:25 – 6:00` | 35s)

#### 🖥️ What to Run in Terminal:
```powershell
cls
.venv\Scripts\pytest -q
```

#### 🗣️ Spoken Voiceover (Read Word-for-Word):
> *"Finally, we run our comprehensive test suite. In less than three seconds, all **one hundred and twenty-five automated tests** pass across ten test modules with zero failures and zero regressions.*
>
> *In summary, the Requirement Collision Engine bridges the critical gap between written requirements and Abstract Syntax Tree code implementation. It transforms silent, expensive production conflicts into deterministic, pre-commit engineering insights.*
>
> *Thank you very much."*

---

## 📋 Quick Copy-Paste Command Sequence for Recording

Keep this sequence ready to paste into PowerShell during your recording:

```powershell
# 1. Reference App & Baseline Tests
python main.py
.venv\Scripts\pytest -v tests/test_cews.py

# 2. RCE Static Collision Detection
cls
python -m rce.cli

# 3. Change-Impact Analysis
python -m rce.cli --impact REQ-07

# 4. Cross-Domain Generalization Validation
cls
.venv\Scripts\pytest -v tests/test_rce_validation_projects.py

# 5. CI/CD Strict Mode & JSON Export
python -m rce.cli --strict
echo "Exit Code: $LASTEXITCODE"
python -m rce.cli --format json --output report.json
Get-Content report.json -TotalCount 25

# 6. Full Test Suite Verification
cls
.venv\Scripts\pytest -q
```
