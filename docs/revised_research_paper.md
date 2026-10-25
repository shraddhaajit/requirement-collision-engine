# Static Detection of Potential Requirement Collisions and Change Impacts in Python Software Systems

**Authors:** Shraddha Ajit et al.  
**Affiliation:** School of Computer Science and Engineering  
**Working Paper / Research Report:** Software Engineering Theory & Practice  
**Date:** October 2026  

---

## Abstract

In continuously evolving software systems, business requirements frequently change, creating subtle interactions with existing logic. A critical failure mode arises when a system satisfies all regression test suites, yet a newly introduced requirement silently contradicts, partially overlaps, or bypasses an established business rule. In dynamic programming environments such as Python, the absence of compile-time type checking and rigid specification schemas exacerbates this challenge. This paper presents the **Requirement Collision Engine (RCE)**, a lightweight, general-purpose static analysis framework designed to identify potential requirement collisions, boundary overlaps, and exception bypasses without executing target code. 

RCE introduces a unified **Requirement Knowledge Graph (RKG)** constructed from Markdown specifications, Python Abstract Syntax Trees (AST), and docstring-based traceability annotations. We formalize three heuristic detection rules: *Shared Implementation Overlaps (Rule A)*, *Conflicting Boundary Conditions (Rule B)*, and *Explicit Override/Bypass Interactions (Rule C)*. In addition, RCE implements a breadth-first change-impact traversal that distinguishes explicit traceability from inferred call-graph dependencies. 

We evaluate RCE under a controlled experimental setup comprising three software systems: the reference *Controlled Enterprise Expense Workflow System (CEWS)* and two independent synthetic domain projects modeling *Logistics/Freight Dispatch* and *Inventory/Order Management*. The implementation is backed by a verified test suite of 125 passing tests, including all 24 baseline tests of the reference application. Our results show that RCE deterministically flags deliberately seeded boundary overlaps and bypasses with grounded source-level evidence, preserves non-conflicting controls without false alarms, and isolates direct from transitive impacts. We discuss the conceptual distinction between interval overlap and functional contradiction, analyze the inherent boundaries of static Python analysis, and outline directions for constraint-solver integration and dynamic runtime verification.

**Keywords:** Requirements Engineering, Traceability, Static Analysis, Abstract Syntax Trees, Requirement Collisions, Change-Impact Analysis, Knowledge Graphs.

---

## 1. Introduction and Motivation

Software maintenance and requirements evolution represent the majority of lifecycle costs in modern software engineering [1]. As software systems expand, new requirements are incrementally layered upon pre-existing codebases. During this iterative process, developers and requirements engineers face a persistent hazard: **the requirement collision**.

A requirement collision occurs when two or more functional requirements impose mutually incompatible constraints, create overlapping boundary decisions with ambiguous priority, or allow an exception mechanism to bypass mandatory compliance or security controls [2]. In practice, such defects are exceptionally difficult to detect using standard unit or integration testing. Testing validates only that the system behaves as expected for *pre-programmed test inputs*; it does not systematically verify whether distinct business rules, often authored by separate stakeholders at different times, logically clash across their decision domains [3].

In dynamically typed languages like Python, this hazard is magnified. Python features runtime binding, dynamic dispatch, and permissive attribute access, lacking compile-time verification mechanisms that might otherwise catch interface and constraint anomalies [4]. Furthermore, formal methods and theorem provers (e.g., SMT solvers, Model Checking), while mathematically rigorous, require formal specification languages (e.g., Z, Alloy, TLA+) that are rarely adopted in mainstream industrial agile workflows due to high modeling overhead [5].

To bridge this gap between lightweight agile practices and automated requirement verification, this paper presents the **Requirement Collision Engine (RCE)**. RCE is a general-purpose, non-intrusive static analysis framework designed to extract requirements from standard Markdown documentation, statically parse Python source files via Abstract Syntax Trees (AST), construct an interconnected knowledge graph, and deterministically surface *potential* requirement collisions and change impacts.

---

## 2. Problem Formulation: The Requirement Collision Phenomenon

We formalize the requirement collision problem in evolving software systems as follows:

Let $R = \{r_1, r_2, \dots, r_n\}$ denote a set of functional requirements expressed in structured natural language documentation. Let $C = \{m_1, m_2, \dots, m_k\}$ denote a Python codebase comprising modules, classes, and functions.

Each requirement $r_i$ governs a set of business conditions $\Phi(r_i) = \{\phi_{i,1}, \phi_{i,2}, \dots\}$ evaluated over domain variables $V$. In source code, these conditions are realized as conditional branch predicates $P = \{p_1, p_2, \dots\}$ in functions $F$.

A **Potential Requirement Collision** between two distinct requirements $r_i$ and $r_j$ ($i \neq j$) exists if there exists at least one shared domain variable $v \in V$ such that:

1. **Logical Contradiction:** Predicates $p_i$ (tracing to $r_i$) and $p_j$ (tracing to $r_j$) evaluate over variable $v$ such that no valuation of $v$ can satisfy both intended outcomes simultaneously:
   $$\exists v : (p_i(v) \wedge p_j(v) \equiv \bot)$$
2. **Boundary Interval Overlap:** Predicates $p_i$ and $p_j$ specify overlapping open or closed intervals on a continuous domain:
   $$\mathcal{I}(p_i) \cap \mathcal{I}(p_j) \neq \emptyset$$
   where $\mathcal{I}(p)$ denotes the satisfying numeric interval of predicate $p$, creating an ambiguous operational region where both rules simultaneously hold true.
3. **Override/Bypass Interaction:** Requirement $r_j$ defines an exception or waiver mechanism that alters or skips the execution of a gate predicate $p_i$ enforcing requirement $r_i$, particularly where $r_i$ is intended to be a mandatory control.

Importantly, RCE does not claim to *prove* semantic inconsistency in the mathematical sense. Rather, it operates as a **heuristic static anomaly detector** that isolates structural and syntactic evidence of potential conflict, highlighting findings that mandate human engineering review.

---

## 3. Research Objectives and Scope Boundaries

### Objectives
1. **Lightweight Traceability & Graph Unification:** Automatically parse structured Markdown specifications and Python docstring annotations (`TRACE: REQ-XX`) to build a NetworkX-based **Requirement Knowledge Graph (RKG)** linking requirements, code artifacts, AST predicates, and tests.
2. **Deterministic, Explainable Collision Detection:** Formulate rule-based detectors that identify shared implementation multiplexing, boundary condition overlaps, and override interactions with line-level source grounding.
3. **Change-Impact Analysis with Inferred Boundary Separation:** Provide graph-based traversal algorithms that distinguish direct implementations (Hop 1) from inferred transitive dependencies (Hop 2+), recommending regression test suites without test duplication.
4. **Controlled Multi-Domain Evaluation:** Validate RCE across a reference enterprise application and independent synthetic domains to verify that detection logic is not hardcoded to a specific application schema.

### Scope Boundaries
* RCE is **strictly static**; it does not execute target software, avoiding runtime side effects, database dependencies, or environment instability.
* RCE targets Python codebases adopting docstring-based traceability tags and Markdown requirement files.
* RCE produces **potential findings** requiring human triage; it does not replace domain experts or formal proofs.

---

## 4. Related Work

Our research builds upon established literature across four principal software engineering domains:

### 4.1 Requirements Traceability Engineering
Gotel and Finkelstein [6] established the classic taxonomy of pre-RS and post-RS requirements traceability, emphasizing the persistent challenge of obtaining and maintaining accurate links between requirements and downstream artifacts. Cleland-Huang et al. [7] and Egyed [8] investigated automated traceability recovery through information retrieval and syntactic heuristics. RCE adopts an explicit, in-source docstring annotation standard (`TRACE: REQ-XX`) inspired by standard safety-critical traceability workflows (e.g., DO-178C).

### 4.2 Inconsistency and Interaction Management
Nuseibeh, Easterbrook, and Russo [9] argued that inconsistencies in software engineering cannot be entirely prevented and must instead be tolerated, highlighted, and actively managed. Robinson, Pawlowski, and Volkov [10] surveyed requirements interaction management, categorizing interactions into structural conflicts, resource contentions, and exception overrides. RCE operationalizes these insights into concrete AST pattern checks.

### 4.3 Static Code Analysis and Abstract Syntax Trees
Static analysis via Abstract Syntax Trees has long been employed for bug finding, security auditing, and code smell detection (e.g., Flake8, Bandit, SonarQube). However, existing static linters analyze code in isolation from the requirements specification. RCE combines AST predicate extraction with specification parsing to analyze code against documented business intent.

### 4.4 Software Change-Impact Analysis
Arnold and Bohner [11] formalized change-impact analysis (CIA) models, categorizing approaches into call-graph based, dependency-based, and traceability-based techniques. Ball [12] analyzed the boundaries between static and dynamic impact analysis. RCE implements a hybrid model that traverses both the syntactic call graph and the semantic requirement bipartite graph.

---

## 5. Methodology & System Architecture

The RCE architecture is organized as a six-stage feedforward static pipeline:

```text
[Markdown Requirements]           [Python Source Code]
          │                                 │
          ▼                                 ▼
   Requirement Parser              AST Static Analyzer
   (rce.requirement_parser)        (rce.ast_analyzer)
          │                                 │
          └───────────────┬─────────────────┘
                          ▼
             Traceability Extractor
             (rce.traceability_extractor)
                          │
                          ▼
            Requirement Knowledge Graph
            (rce.knowledge_graph - NetworkX)
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    Collision Detector          Change-Impact Analyzer
  (rce.collision_detector)      (rce.impact_analyzer)
            │                           │
            └─────────────┬─────────────┘
                          ▼
                  Engine Orchestrator
                  (rce.engine & rce.cli)
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
      Console Report           Machine-Readable JSON
```

### 5.1 Requirement Parsing & Normalization
The requirement parser inspects Markdown documents, isolating level-3 headers matching the regular expression:
$$\text{Heading Pattern} = \texttt{\^{}\#\#\#\textbackslash{}s+(REQ-\textbackslash{}d+)\textbackslash{}s*[:\u2014\-]\textbackslash{}s*(.+)\$}$$
The parser extracts the requirement identifier, normalized title, and body description, ensuring uniqueness and validating mandatory descriptive content.

### 5.2 Python AST Analysis & Condition Extraction
RCE analyzes Python source code using Python's standard `ast` module. The `CodeVisitor` inspects nodes without executing or importing module bytecodes:
* **Functions & Methods:** Records function name, docstring, parameters, enclosing class, line range, and calls.
* **Call Extraction:** Captures function invocations (`ast.Call`), recording both simple names (`func()`) and qualified attribute accesses (`obj.method()`).
* **Condition Extraction:** Traverses conditional nodes (`ast.If`, `ast.While`, `ast.Assert`), decomposing compound boolean operators (`ast.BoolOp`, `ast.UnaryOp`) into atomic binary comparison records:
  $$\text{Condition} = \langle \text{var}, \text{operator}, \text{literal}, \text{is\_numeric}, \text{file}, \text{line} \rangle$$

### 5.3 Knowledge Graph Formulation
The Requirement Knowledge Graph is modeled as a directed graph $G = (V_G, E_G)$ using NetworkX:
* **Node Types $V_G$:**
  $$V_G = V_{\text{req}} \cup V_{\text{mod}} \cup V_{\text{class}} \cup V_{\text{func}} \cup V_{\text{cond}} \cup V_{\text{test}}$$
* **Edge Types $E_G$:**
  $$E_G = E_{\text{CONTAINS}} \cup E_{\text{IMPLEMENTS}} \cup E_{\text{CALLS}} \cup E_{\text{HAS\_CONDITION}} \cup E_{\text{VERIFIES}}$$

Traceability edges ($E_{\text{IMPLEMENTS}}$ and $E_{\text{VERIFIES}}$) are constructed exclusively from parsed `TRACE: REQ-XX` tags. Code containment and call edges represent syntactic program structure.

### 5.4 Collision Detection Heuristics

#### Rule A: Shared Implementation with Overlapping Conditions
Flags functions $f \in V_{\text{func}}$ where:
$$|\{r \in V_{\text{req}} \mid (r, f) \in E_{\text{IMPLEMENTS}}\}| \geq 2 \quad \wedge \quad |\{c \in V_{\text{cond}} \mid (f, c) \in E_{\text{HAS\_CONDITION}}\}| \geq 2$$
This flags localized multiplexing where multiple business rules are coupled within a single procedural block.

#### Rule B: Conflicting Boundary Conditions
Given distinct requirements $r_1, r_2$ tracing to functions $f_1, f_2$, Rule B evaluates conditions $c_1 \in \text{Cond}(f_1)$ and $c_2 \in \text{Cond}(f_2)$ operating on the same target variable $v$:
1. **Numeric Contradiction:** Direct opposing relational operators on identical values ($v > k$ vs. $v \leq k$).
2. **Discrete Inequality:** Conflicting equality assertions ($v == \text{"A"}$ vs. $v == \text{"B"}$ or $v == \text{"A"}$ vs. $v != \text{"A"}$).
3. **Boundary Interval Overlap:** Relational conditions defining an overlapping interval $[k_1, k_2]$ where both evaluate to true simultaneously (e.g., $v > 50$ and $v < 75$).

#### Rule C: Explicit Exception and Override Interactions
Identifies requirements specifying override keywords (*override*, *bypass*, *waiver*, *emergency*) in conjunction with code-level decision gates evaluating override flags or disjunctive bypass predicates (e.g., `not (check or is_override)`).

### 5.5 Change-Impact Analysis Model
Given a target artifact $t \in V_G$, the impact analyzer performs a bounded Breadth-First Search (BFS) up to depth $d_{\text{max}}$:
* **Hop 1 (Direct Impact):** Neighbors connected via explicit $E_{\text{IMPLEMENTS}}$, enclosing $E_{\text{CONTAINS}}$, or direct $E_{\text{VERIFIES}}$ edges. Marked as $\text{Inferred} = \text{False}$.
* **Hop 2+ (Transitive Impact):** Nodes reached via $E_{\text{CALLS}}$ hierarchies, module containment, and cross-implementing requirements. Marked as $\text{Inferred} = \text{True}$.
* **Regression Test Recommendation:** Automatically identifies test nodes $V_{\text{test}}$ reachable from any impacted node.

---

## 6. Implementation Details

RCE is implemented in standard Python 3.10+ and comprises 10 core modules in the `rce` package:

| Module | Lines of Code | Responsibility |
|---|---|---|
| `rce.requirement_parser` | ~250 | Markdown requirement parsing, validation, and ID normalization |
| `rce.traceability_extractor` | ~380 | In-source docstring `TRACE:` token extraction |
| `rce.ast_analyzer` | ~980 | Non-executing AST traversal, call and condition extraction |
| `rce.knowledge_graph` | ~750 | NetworkX graph construction, node/edge query APIs |
| `rce.collision_detector` | ~930 | Deterministic implementation of Rules A, B, and C |
| `rce.impact_analyzer` | ~850 | BFS change-impact traversal and regression test mapping |
| `rce.engine` | ~450 | Pipeline orchestration, error handling, partial analysis |
| `rce.cli` | ~180 | Argument parsing, text streaming, machine-readable JSON |

### Discovery Isolation & Exclusion Safeguards
To ensure general-purpose execution across real project directories, RCE incorporates strict directory discovery rules. The static engine automatically excludes:
* Virtual environments (`.venv`, `venv`, `env`).
* Source control metadata (`.git`).
* Bytecode and temporary caches (`__pycache__`, `.pytest_cache`, `.mypy_cache`).
* Test directories (`tests`, `test`, `testing`) are cataloged exclusively for test-verification linking and are excluded from application logic scanning.
* Tool implementation packages (`rce/`) are excluded from target code scanning when analyzing host repositories.

---

## 7. Experimental Evaluation Setup

To evaluate whether RCE functions as a general-purpose static tool beyond its initial design context, we conducted controlled experiments across three distinct software systems.

### 7.1 Target Systems

1. **CEWS (Corporate Expense Workflow System):**
   * *Domain:* Enterprise financial approval workflow.
   * *Scale:* 10 requirements (`REQ-01` to `REQ-10`), 4 core business modules (`cews.expense`, `cews.approval`, `cews.compliance`, `cews.audit`), 24 baseline tests.
   * *Characteristics:* Multi-tiered thresholds (Manager > ₹10k, Finance > ₹25k, Executive > ₹50k), travel manager override (< ₹15k), emergency bypass, and audit recording.

2. **Synthetic Project A (Warehouse & Logistics Domain):**
   * *Domain:* Freight calculation and courier dispatch routing.
   * *Scale:* 3 requirements (`REQ-01` Heavy Freight Surcharge, `REQ-02` Express Shipping Waiver, `REQ-03` Remote Delivery Eligibility), 3 modules (`shipping.py`, `express.py`, `delivery.py`), 1 test module.
   * *Seeded Scenarios:* Deliberate boundary overlap on `weight` between surcharge (> 50 kg) and express waiver (< 75 kg); Rule C override gate in `dispatch_cargo`; unrelated control `zone_code == "ZONE_REMOTE"`.

3. **Synthetic Project B (Inventory & Order Management Domain):**
   * *Domain:* Warehouse stock tracking, bulk purchase validation, and order lifecycle.
   * *Scale:* 5 requirements (`REQ-01` Stock Availability, `REQ-02` Automated Replenishment, `REQ-03` Standard Order Limit, `REQ-04` Wholesale Bulk Minimum, `REQ-05` Cancellation Policy), 3 modules (`stock.py`, `orders.py`, `lifecycle.py`), 1 test module.
   * *Seeded Scenarios:* Cross-module call chain (`orders.py` calling `stock.py`); boundary overlap on `quantity` between standard orders ($\leq 100$) and wholesale minimum ($> 50$); non-conflicting stock thresholds ($\geq 10$ vs. $< 5$); non-conflicting cancellation status (`status == "PENDING"`).

*Note on Evaluation Nature:* Projects A and B are **controlled synthetic test cases** engineered to benchmark specific detector behaviors under isolated conditions; they are not claimed to represent organic, large-scale commercial benchmark datasets.

### 7.2 Verified Test Suite Profile
The entire test suite was executed under Python 3.12.6 on Windows PowerShell using `pytest -v`:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.6, pytest-9.1.1, pluggy-1.6.0
collected 125 items

tests/test_cews.py ........................                              [ 19%]
tests/test_rce_parser.py ............                                    [ 28%]
tests/test_rce_traceability.py ..............                            [ 40%]
tests/test_rce_ast_analyzer.py ............                              [ 49%]
tests/test_rce_knowledge_graph.py ...........                             [ 58%]
tests/test_rce_collision_detector.py .............                        [ 68%]
tests/test_rce_impact_analyzer.py ...............                         [ 80%]
tests/test_rce_cli.py ........                                           [ 87%]
tests/test_rce_engine.py ..........                                      [ 95%]
tests/test_rce_validation_projects.py ......                             [100%]

============================= 125 passed in 3.11s =============================
```
All **125 tests passed**, including all **24 original CEWS tests**, with zero regressions.

---

## 8. Empirical Findings and Technical Discussion

### 8.1 Summary of Collision Detection Results

| Target Project | Requirements | Modules | Functions | Conditions | Collisions Detected | Primary Rules Triggered |
|---|---|---|---|---|---|---|
| **CEWS** | 10 | 4 | 13 | 53 | 3 | Rule B (Amount Overlap: REQ-03 vs REQ-07)<br/>Rule C (Emergency Bypass: REQ-03 vs REQ-08)<br/>Rule C (Manager Override: REQ-03 vs REQ-07) |
| **Project A** (Logistics) | 3 | 3 | 4 | 4 | 2 | Rule B (Weight Overlap: REQ-01 vs REQ-02)<br/>Rule C (Waiver Bypass: REQ-01 vs REQ-02) |
| **Project B** (Inventory) | 5 | 3 | 5 | 5 | 1 | Rule B (Quantity Overlap: REQ-03 vs REQ-04) |

### 8.2 Grounded Evidence and Source Attribution
In all detected findings, RCE generated deterministic collision records complete with source paths, function names, line numbers, and exact predicate expressions. For example, in Project A:
```text
Collision ID : COL-RULE_B-REQ-01-REQ-02-WEIGHT
Category     : BOUNDARY_CONDITION_COLLISION
Severity     : MEDIUM | Confidence: HIGH
Explanation  : Boundary interval overlap on variable 'weight' between 50.00 and 75.00.
               Conditions 'weight < 75.0' (REQ-02) and 'weight > 50.0' (REQ-01)
               simultaneously evaluate to true in this range.
Evidence     :
  - Condition 1 in warehouse/shipping.py:6 (calculate_freight_surcharge): 'weight > 50.0'
  - Condition 2 in warehouse/express.py:6 (express_shipping_waiver): 'weight < 75.0'
  - Target attribute: 'weight'
```

### 8.3 Conceptual Distinction: Interval Overlap vs. Logical Contradiction
A fundamental theoretical insight highlighted by our evaluation is that **an interval overlap does not inherently constitute a software bug**. 

In Project B, standard consumer orders allow `quantity <= 100`, while wholesale bulk orders require `quantity > 50`. The interval $(50, 100]$ is mathematically an overlap. However, in business reality, an order of 75 units could validly qualify as either a large consumer order or a small wholesale order depending on customer categorization. RCE correctly flags this overlap as a `MEDIUM` severity collision requiring human review, rather than asserting a fatal contradiction. 

Conversely, a `HIGH` severity contradiction occurs when opposing operators act on identical thresholds without qualifying discriminators (e.g. `x > 100` and `x <= 100` triggering conflicting actions). RCE's explainability model ensures that human engineers receive the exact mathematical context needed to judge validity.

### 8.4 Precision on Non-Conflicting Controls
To assess false alarm resistance in controlled settings, both synthetic projects included non-conflicting controls:
* In Project A, `REQ-03` evaluated `zone_code == "ZONE_REMOTE"`. RCE produced **0** collision findings involving `REQ-03`.
* In Project B, `REQ-01` evaluated `stock >= 10` and `REQ-02` evaluated `stock < 5`. Because $[0, 5) \cap [10, \infty) = \emptyset$, RCE generated **0** collisions on variable `stock`.
* In Project B, order cancellation `status == "PENDING"` generated **0** collisions.

### 8.5 Change-Impact Traversal Accuracy
Change-impact analysis was tested across the cross-module call chain in Project B:
`validate_wholesale_order` (`inventory/orders.py`) calls `verify_stock_available` (`inventory/stock.py`).
Initiating impact analysis from `REQ-04` yielded:
* **Direct Impacts (Hop 1, Inferred = No):** Function `validate_wholesale_order`, module `inventory.orders`.
* **Transitive Impacts (Hop 2+, Inferred = Yes):** Callee function `verify_stock_available` (depth 2), requirement `REQ-04` self-closure (depth 2), module `inventory.stock` (depth 3), co-implementing requirement `REQ-01` (depth 3).
* **Test Discovery:** Recommended regression tests were accurately mapped without duplicate entries.

---

## 9. Threats to Validity and Limitations

### 9.1 Construct Validity
* *Traceability Tag Reliance:* RCE relies on developer-annotated `TRACE: REQ-XX` docstrings. If developers omit or mislabel docstrings, the resulting knowledge graph will be incomplete. While RCE infers untagged functions through call-graph traversal, unlinked roots cannot be discovered statically.
* *Semantic Variable Matching:* Collision detection currently compares AST conditions sharing identical variable or attribute names. If two requirements govern the same conceptual entity under different identifier names (e.g., `weight` vs. `cargo_mass`), static AST analysis will not detect the collision without semantic thesauri or ontologies.

### 9.2 Internal Validity
* *Controlled Test Projects:* Projects A and B were deliberately authored to validate known detector mechanics. While they prove that the engine is not hardcoded to CEWS, they do not prove recall on arbitrary, unstructured codebases.

### 9.3 External Validity & Non-Generalization
* *Broad Generalization Remains Unverified:* We explicitly state that RCE's accuracy, performance, and scalability across large-scale commercial or multi-million-line open-source repositories have not yet been established.
* *Specification Formatting Constraints:* RCE requires Markdown files adhering to level-3 heading conventions. Free-form text documents, PDFs, or spreadsheet-based requirements must be pre-processed before analysis.

### 9.4 Inherent Limitations of Static Python AST Analysis
* *Dynamic Dispatch & Reflection:* Invocations via `getattr()`, `eval()`, or dynamic monkey-patching cannot be statically resolved into call-graph edges.
* *Compound Multi-Statement Logic:* Multi-line boolean calculations that accumulate state across multiple statements without a direct binary comparison expression are not currently decomposed into atomic interval bounds.

---

## 10. Conclusion and Future Research Directions

This paper introduced the **Requirement Collision Engine (RCE)**, a static analysis framework that integrates Markdown requirements specifications and Python source code into a queryable Requirement Knowledge Graph. By evaluating AST comparison predicates and traceability links, RCE deterministically detects potential requirement collisions (shared implementations, boundary overlaps, and override bypasses) and provides explainable change-impact analysis without executing target code.

Evaluation across the reference CEWS system and two independent synthetic domains confirmed that RCE operates deterministically, isolates grounded source evidence, distinguishes direct from inferred dependencies, and preserves passing regression baselines (125/125 passing tests).

### Future Research Directions
1. **SMT Solver Integration:** Incorporating constraint solvers (e.g., Z3) to formally verify satisfiability across complex multi-variable predicates and non-linear inequalities.
2. **LLM-Assisted Traceability Extraction:** Leveraging lightweight local language models to infer requirement linkages in legacy repositories lacking explicit docstring tags.
3. **Dynamic Concolic Execution:** Combining static AST heuristics with concolic testing to generate concrete test inputs that trigger detected boundary overlaps at runtime.
4. **Empirical Open-Source Benchmarking:** Conducting large-scale empirical studies across diverse GitHub Python repositories to establish benchmark precision and recall metrics.

---

## References

1. B. W. Boehm, *Software Engineering Economics*, Prentice-Hall, Englewood Cliffs, NJ, 1981.
2. P. Zave and M. Jackson, "Four dark corners of requirements engineering," *ACM Transactions on Software Engineering and Methodology (TOSEM)*, vol. 6, no. 1, pp. 1–30, 1997.
3. E. W. Dijkstra, "Notes on structured programming," in *Structured Programming*, Academic Press, London, 1972, pp. 1–82.
4. G. van Rossum and F. L. Drake, *Python 3 Reference Manual*, CreateSpace, Scotts Valley, CA, 2009.
5. D. Jackson, *Software Abstractions: Logic, Language, and Analysis*, MIT Press, Cambridge, MA, 2012.
6. O. C. Gotel and C. W. Finkelstein, "An analysis of the requirements traceability problem," in *Proceedings of the First International Conference on Requirements Engineering (ICRE)*, Colorado Springs, CO, 1994, pp. 94–101.
7. J. Cleland-Huang, O. Gotel, and A. Zisman, *Software and Systems Traceability*, Springer-Verlag, London, 2012.
8. A. Egyed, "A scenario-driven approach to trace dependency analysis," *IEEE Transactions on Software Engineering*, vol. 29, no. 12, pp. 1161–1179, 2003.
9. B. Nuseibeh, S. Easterbrook, and A. Russo, "Leveraging inconsistency in software development," *IEEE Computer*, vol. 33, no. 4, pp. 24–29, 2000.
10. W. N. Robinson, S. D. Pawlowski, and V. Volkov, "Requirements interaction management," *ACM Computing Surveys (CSUR)*, vol. 35, no. 2, pp. 132–190, 2003.
11. R. S. Arnold and S. A. Bohner, "Impact analysis—towards a software engineering discipline," in *Proceedings of the Conference on Software Maintenance*, Montreal, QC, 1993, pp. 292–301.
12. T. Ball, "The concept of dynamic analysis," in *Proceedings of the 7th European Software Engineering Conference (ESEC/FSE)*, Toulouse, France, 1999, pp. 216–234.
13. A. van Lamsweerde, *Requirements Engineering: From System Goals to UML Models to Software Specifications*, John Wiley & Sons, Chichester, UK, 2009.
14. A. Hagberg, P. Swart, and D. S Chult, "Exploring network structure, dynamics, and function using NetworkX," in *Proceedings of the 7th Python in Science Conference (SciPy)*, Pasadena, CA, 2008, pp. 11–15.
