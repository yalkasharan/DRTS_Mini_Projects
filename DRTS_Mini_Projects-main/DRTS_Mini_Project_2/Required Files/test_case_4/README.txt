Test Case 4 — CBS Starvation Prevention Demonstration
======================================================

PURPOSE
-------
This test case is specifically designed to demonstrate that Credit-Based
Shaping (CBS) prevents starvation of lower-priority queues, whereas Strict
Priority (SP) scheduling allows them to starve when Class A utilization is
very high.

SCENARIO
--------
A single ES1 → SW1 → ES0 hop carries two Class A streams with combined
link utilisation of 95 %. Under SP, this near-saturating load causes the
Class B and Best-Effort streams to have worst-case response times far
exceeding their deadlines. Under CBS, the idle-slope mechanism caps the
credit that Class A can accumulate, keeping Class B and Best-Effort
response times well within their deadlines.

STREAMS
-------
  stream-A1   PCP=2 (Class A)  1500 B  period=160 µs   util=75.0%
  stream-A2   PCP=2 (Class A)   500 B  period=200 µs   util=20.0%
  stream-B1   PCP=1 (Class B)   800 B  period=5000 µs  util= 1.3%
  stream-BE1  PCP=0 (Best Eff) 1000 B  period=10000 µs util= 0.8%

Total Class A utilisation = 95 %

EXPECTED ANALYTICAL RESULTS (idle_slope_A = idle_slope_B = 0.5)
----------------------------------------------------------------
  stream-A1  CBS WCD ≈  573 µs  ≤ deadline 2000 µs  [schedulable]
  stream-A2  CBS WCD ≈  733 µs  ≤ deadline 2000 µs  [schedulable]
  stream-B1  CBS WCD ≈  701 µs  ≤ deadline 1000 µs  [schedulable]
  stream-BE1 CBS WCD ≈  669 µs  ≤ deadline 1000 µs  [schedulable]

  stream-B1  SP WCD  ≈ 2573 µs  > deadline 1000 µs  [DEADLINE MISS]
  stream-BE1 SP WCD  ≈ 4315 µs  > deadline 1000 µs  [DEADLINE MISS]

KEY TAKEAWAY
------------
CBS prevents starvation: even with 95% Class A link utilisation, the
credit mechanism guarantees that Class B and Best-Effort frames are
served within bounded response times. SP provides no such guarantee —
the lower-priority queues experience response times more than 2× their
deadline under identical traffic load.
