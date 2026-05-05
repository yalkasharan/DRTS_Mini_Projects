# DRTS Mini-Project 2 — Full Evaluation Against Project Description

> Evaluated against `02225_DRTS_F26_mini_project_2.pdf` and the "What is a good project" grading criteria.

---

## Section 1: Project Requirements (from PDF)

### R1. "Develop their own software"

| Verdict | ✅ Satisfied |
|---------|-------------|

The entire codebase is custom Python — no third-party CBS analysis libraries are used. `requirements.txt` only lists `matplotlib`, `seaborn`, `pandas` (plotting). All CBS analysis formulas, simulator logic, and data parsing are self-implemented.

---

### R2. "Determine the worst-case delays (WCDs) of a set of periodic real-time streams considering TSN and the Credit Based Shaper (CBS)"

| Verdict | ✅ Satisfied |
|---------|-------------|

[wcrt_analysis.py](file:///c:/Users/yalka/OneDrive/Desktop/DRTS/DRTS_Mini_Project2/DRTS_Mini_Project_2/analytical/wcrt_analysis.py) implements the CBS WCD analysis from Cao et al. 2016 (reference [3] in the PDF). The implementation includes:
- Same-priority CBS inflation factor: `(1 + sendSlope/idleSlope)`
- Higher-priority blocking via recursive accumulation
- Lower-priority non-preemptive blocking for the highest CBS class
- Per-hop WCD computation summed for end-to-end WCD

**Verified against ALL 3 reference test cases** — exact match on every stream:

| Stream | TC1 Ref | TC1 Yours | TC2 Ref | TC2 Yours | TC3 Ref | TC3 Yours |
|--------|---------|-----------|---------|-----------|---------|-----------|
| 0 | 603.2 | 603.2 ✅ | 1087.2 | 1087.2 ✅ | 601.6 | 601.6 ✅ |
| 1 | 603.2 | 603.2 ✅ | 1087.2 | 1087.2 ✅ | 601.6 | 601.6 ✅ |
| 2 | 632.8 | 632.8 ✅ | 1175.28 | 1175.28 ✅ | 574.56 | 574.56 ✅ |
| 3 | 632.8 | 632.8 ✅ | 1175.28 | 1175.28 ✅ | 574.56 | 574.56 ✅ |
| 4 | 884.48 | 884.48 ✅ | 1646.4 | 1646.4 ✅ | 919.2 | 919.2 ✅ |
| 5 | 884.48 | 884.48 ✅ | 1646.4 | 1646.4 ✅ | 919.2 | 919.2 ✅ |
| 6 | 808.0 | 808.0 ✅ | 1626.48 | 1626.48 ✅ | 957.12 | 957.12 ✅ |
| 7 | 808.0 | 808.0 ✅ | 1626.48 | 1626.48 ✅ | 957.12 | 957.12 ✅ |

**24/24 reference values matched exactly across all test cases.**

---

### R3. "Compare the calculated WCDs with response times observed during simulations"

| Verdict | ✅ Satisfied |
|---------|-------------|

The comparison pipeline is comprehensive:
- [compare_results.py](file:///c:/Users/yalka/OneDrive/Desktop/DRTS/DRTS_Mini_Project2/DRTS_Mini_Project_2/compare_results.py) generates `comparison.csv` with per-stream: analytical WCD, simulated max delay, gap, and `bound_satisfied` flag
- The simulator [main.py](file:///c:/Users/yalka/OneDrive/Desktop/DRTS/DRTS_Mini_Project2/DRTS_Mini_Project_2/simulator/main.py) prints inline comparison with gap statistics
- 4 dedicated visualization charts: bar chart comparison (chart 1), bound satisfaction table (chart 2), tightness analysis with gap percentages (chart 4), and CBS credit evolution (chart 5)
- All 10 streams show `bound_satisfied = True` (simulated max ≤ analytical WCD)

---

### R4. (Optional) "Compare Strict Priority (SP) shaping with CBS"

| Verdict | ✅ Satisfied (Optional — Implemented) |
|---------|-------------|

[sp_rta.py](file:///c:/Users/yalka/OneDrive/Desktop/DRTS/DRTS_Mini_Project2/DRTS_Mini_Project_2/analytical/sp_rta.py) implements standard fixed-point RTA for SP scheduling. The comparison is in `comparison.csv` (includes `sp_wcd_us` column) and chart 3 (`chart3_cbs_vs_sp.png`).

#### R4a. "For SP, calculate the WCDs using standard Response Time Analysis (RTA)"

| Verdict | ✅ Satisfied |
|---------|-------------|

The `_rta_link()` function uses the standard RTA recurrence: `R_{n+1} = C_i + Σ ⌈R_n / T_j⌉ × C_j` for all higher-priority interfering streams. This is the textbook fixed-priority RTA.

#### R4b. "Demonstrating the impact of the credit mechanism on preventing starvation of lower-priority queues is a key goal"

| Verdict | ✅ Satisfied |
|---------|-------------|

Chart 3 shows BE streams (Stream 8, 9) have SP WCD of 718.64 µs vs CBS WCD of 705.60 µs. The `summarize_sp_vs_cbs()` function in `results_utils.py` detects when BE streams miss their deadline under SP but meet it under CBS, and prints starvation warnings. The chart labels SP-starved streams with "STARVED" annotations.

---

### R5. "Line topology (end system connected to another end system via a few switches)"

| Verdict | ✅ Satisfied |
|---------|-------------|

All three test cases use line topologies: ES → SW1 → ES (2-hop). The code correctly handles these paths via `get_path_links()` which traverses the route's node sequence.

---

### R6. "Three queues (CBS with high priority — AVB A, CBS with lower priority — AVB B, and Best Effort — BE)"

| Verdict | ✅ Satisfied |
|---------|-------------|

The [model.py](file:///c:/Users/yalka/OneDrive/Desktop/DRTS/DRTS_Mini_Project2/DRTS_Mini_Project_2/analytical/model.py) maps PCP values to three priority levels: `PCP 2 → CLASS_A (level 2)`, `PCP 1 → CLASS_B (level 1)`, `PCP 0 → BEST_EFFORT (level 0)`. The simulator's `OutputPort` class maintains separate queues and CBS credits per level. The analytical tool dispatches to different WCD formulas based on priority.

---

### R7. "Assume that all streams go on the same direction... all streams will share all links"

| Verdict | ⚠️ Partially Satisfied |
|---------|-------------|

The test cases actually have streams going in **both directions** (some ES0→ES1, others ES1→ES0). The code handles this correctly — it determines co-flows per output link via `get_coflows()`, so streams only interfere when they share the same output port. This is actually **more general** than the simplified assumption, which is better. However, the project description explicitly says to assume same direction/shared links, and the code doesn't enforce this simplification — it works for any topology. This is a strength, not a weakness, but it means the code differs from the stated assumption.

---

### R8. "The analysis is presented on the lecture slides and in [2]. [...] Cao et al. [3]"

| Verdict | ✅ Satisfied |
|---------|-------------|

The implementation follows Cao et al. 2016 (reference [3]) for the per-class independent WCD analysis. Docstrings explicitly reference "Cao et al. 2016" and "Cao et al. 2018". The module docstring in `wcrt_analysis.py` explains the formula structure.

---

### R9. "Sizes are in bytes, 100 Mb/s, idleSlope and sendingSlope are set to 0.5"

| Verdict | ✅ Satisfied |
|---------|-------------|

- Sizes: Stream `size` field is in bytes, and `_tx_time()` computes `(size_bytes * 8) / bandwidth_mbps`
- Bandwidth: `topology.json` sets `"default_bandwidth_mbps": 100`, and `validate_link_bandwidths()` warns if links differ from 100 Mb/s
- CBS slopes: `CBSConfig.from_legacy_inputs()` defaults to `idle_slope_a=0.5`, `idle_slope_b=0.5`; `send_slope = 1.0 - idle_slope = 0.5`

---

## Section 3: Optional Extensions (from PDF)

### E1. "Generalized Analysis for Multiple Queues and Arbitrary Network Topologies" (Cao 2018 [4])

| Verdict | ✅ Implemented |
|---------|-------------|

The model uses numeric priority levels `0..N-1` instead of hardcoded A/B/BE. `_recursive_higher_priority_term()` generalizes the two-CBS-queue formula to arbitrary priority levels using recursive folding from Cao 2018. `assign_priority_classes()` maps any number of distinct PCP values to contiguous levels. Test case 2 is verified with this generalized analysis. Unit test `test_three_cbs_class_case_produces_valid_wcds` validates a 3-class case.

---

### E2. "Strict Priority Scheduling Analysis and Comparison with CBS"

| Verdict | ✅ Implemented |
|---------|-------------|

Full SP RTA implementation in `sp_rta.py` with comparison infrastructure (chart 3, `summarize_sp_vs_cbs()`, `sp_wcd_us` column in comparison CSV). Both analytical SP and CBS results are produced and compared.

---

## "What is a Good Project" Grading Criteria

### G1. Simulator Tool Development

| Verdict | ✅ Satisfied |
|---------|-------------|

[sim_engine.py](file:///c:/Users/yalka/OneDrive/Desktop/DRTS/DRTS_Mini_Project2/DRTS_Mini_Project_2/simulator/sim_engine.py) is a full discrete-event simulator:
- Three queue types (CBS A, CBS B, BE) per output port
- CBS credit mechanism: credits grow at `idleSlope` when queue has pending frames, decrease at `sendingSlope` during transmission, reset to 0 when queue empties with positive credit
- Priority-based selection (highest CBS first, then BE)
- Credit-based gating (negative credit blocks transmission)
- Multi-hop forwarding with propagation delay
- Records end-to-end response times (min, avg, max per stream)
- Optional credit logging for visualization

---

### G2. Analytical Tool Development

| Verdict | ✅ Satisfied |
|---------|-------------|

Complete CBS WCRT analytical tool with exact match on all 24 reference values. Supports both single-instance and fixed-point modes. Handles per-hop analysis with optional propagation delay.

---

### G3. Analysis Validation

| Verdict | ✅ Satisfied |
|---------|-------------|

Comprehensive validation:
- All simulated max delays ≤ analytical WCDs (bounds valid)
- Gap analysis with percentage tightness
- 8 visualization charts
- Automated comparison pipeline (`compare_results.py`)

---

### G4. Thorough Results Analysis

| Verdict | ⚠️ Partially Satisfied |
|---------|-------------|

The **code infrastructure** for thorough analysis is excellent (8 charts, gap statistics, tightness analysis, multi-test-case summary). However, **a written report interpreting the results is missing**. The plots and CSVs are generated but there's no PDF report documenting the findings, interpreting them, or discussing trade-offs.

---

### G5. Comparative Performance Evaluation

| Verdict | ✅ Satisfied (in code) |
|---------|-------------|

The comparison infrastructure covers:
- CBS vs SP WCDs (chart 3)
- Bound tightness analysis (chart 4)
- Multi-test-case WCD vs link utilization (chart 7)
- Fixed-point vs single-instance bounds (chart 8)
- Starvation detection under SP

---

### G6. Good Test Cases

| Verdict | ✅ Satisfied |
|---------|-------------|

Three test cases with varied parameters:
- Different packet sizes (626–1331 bytes)
- Different periods (1000, 2000 µs)
- Different link propagation delays
- Different link utilizations (29.5% to 37.3%)
- All three verified against reference WCRTs

---

### G7. Critical Evaluation

| Verdict | ⚠️ Partially Satisfied |
|---------|-------------|

The code demonstrates **awareness** of pessimism (fixed-point mode produces tighter bounds, gap analysis quantifies conservatism). But there's no written discussion of **why** the bounds are pessimistic, what the sources of pessimism are (single-instance assumption, worst-case phasing, no jitter modeling), or how they could be improved. This discussion belongs in the report.

---

### G8. Effective Teamwork

| Verdict | N/A |
|---------|-------------|

Cannot evaluate from code alone — this requires the report to describe task division.

---

### G9. Well-Written Report

| Verdict | ❌ Not Satisfied |
|---------|-------------|

> [!CAUTION]
> **No PDF report found in the project.** The submission requires a PDF report with:
> - Introduction & Theory (goals, background, assumptions)
> - Implementation (tool purpose, pseudocode, technical details)
> - Testing & Validation (test cases, validation process)
> - Evaluation & Discussion (results, analysis, trade-offs, limitations)

This is the **single most critical missing deliverable**.

---

## Submission Deliverables Check

| Deliverable | Status |
|-------------|--------|
| PDF Report | ❌ Missing |
| Code (all source files and scripts) | ✅ Present |
| Results (output data or logs) | ✅ Present (8 CSVs, 8 charts) |
| README (instructions for running) | ✅ Present (clear README.md with run commands) |

---

## Overall Rating

### Scoring Breakdown

| Category | Weight | Score | Notes |
|----------|--------|-------|-------|
| **Analytical Tool — Correctness** | 20% | **20/20** | 24/24 reference values matched exactly |
| **Simulator — CBS Implementation** | 20% | **20/20** | Correct credit mechanism, multi-hop, event-driven |
| **Comparison & Validation** | 15% | **14/15** | Comprehensive but prop-delay asymmetry in default comparison |
| **Optional: SP RTA + Comparison** | 10% | **10/10** | Full SP implementation with starvation analysis |
| **Optional: Generalization (Cao 2018)** | 5% | **5/5** | Arbitrary priority levels, verified |
| **Test Cases** | 5% | **5/5** | 3 varied test cases, all verified |
| **Code Quality & Structure** | 10% | **9/10** | Excellent structure; minor: `run_all.py` path mismatch |
| **Report** | 15% | **0/15** | ❌ Missing entirely |

### **Overall: ~83/100 — Limited by the missing report**

> [!WARNING]
> **Without the report, the grade will be significantly impacted.** The code alone is top-tier (would score ~98/100 if only code were evaluated), but the project spec explicitly requires a PDF report with theory, pseudocode, validation discussion, and critical evaluation. The report is estimated at 15% of the grade and also provides the venue for G4 (thorough results analysis) and G7 (critical evaluation), which are currently only partially satisfied.

### What you need to do for a top grade

1. **Write the PDF report** — This is non-negotiable. Structure it as:
   - **Introduction & Theory**: CBS mechanism, Cao 2016 formulas, assumptions (line topology, 100 Mb/s, slopes = 0.5)
   - **Implementation**: Tool architecture diagram, CBS analysis pseudocode, simulator event loop pseudocode
   - **Testing & Validation**: Present the 3 test cases, show all 24/24 reference matches, explain comparison methodology
   - **Evaluation & Discussion**: Use your 8 charts, discuss bound tightness (avg gap ~30%), sources of pessimism (single-instance, worst-case phasing), CBS vs SP starvation prevention, fixed-point improvements

2. **Discuss sources of pessimism** — Explain why analytical bounds are conservative (single-instance assumption ignores period-based spacing, worst-case blocking from all lower-priority traffic simultaneously)

3. **Fix `run_all.py` path** — Change `mini-project-2` to `Required Files` so the full pipeline runs out of the box
