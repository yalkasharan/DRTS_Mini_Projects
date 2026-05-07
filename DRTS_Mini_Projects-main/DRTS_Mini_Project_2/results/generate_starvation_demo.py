#!/usr/bin/env python3
"""
Generate CBS vs SP comparison data for Test Case 4 (starvation demonstration).

Test Case 4 features two Class A streams with combined link utilisation of 95%.
Under Strict Priority (SP), Class B and Best-Effort streams experience
response times that far exceed their deadlines — they are effectively
starved. Under CBS (idle_slope=0.5 for each AVB class), the credit
mechanism caps Class A interference and keeps lower-priority response
times well within their deadlines.

Outputs: results/starvation_comparison.csv
"""
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytical"))

from model import CBSConfig  # noqa: E402
from sp_rta import analyze_sp  # noqa: E402
from tsn_parser import assign_priority_classes, load_routes, load_streams, load_topology  # noqa: E402
from wcrt_analysis import analyze  # noqa: E402

TC4 = PROJECT_ROOT / "Required Files" / "test_case_4"
OUTPUT_CSV = PROJECT_ROOT / "results" / "starvation_comparison.csv"


def _deadline(stream) -> float | None:
    if stream.destinations:
        return float(stream.destinations[0]["deadline"])
    return None


def main() -> None:
    print("=" * 60)
    print(" Starvation Demo: CBS vs SP — Test Case 4")
    print(" Class A utilisation ≈ 95 % (stream-A1=75%, stream-A2=20%)")
    print("=" * 60)

    _, links = load_topology(str(TC4 / "topology.json"))
    streams = load_streams(str(TC4 / "streams.json"))
    routes = load_routes(str(TC4 / "routes.json"))
    assign_priority_classes(streams)

    cbs = CBSConfig.from_legacy_inputs(
        max_priority_level=2,
        idle_slope_a=0.5,
        idle_slope_b=0.5,
    )

    cbs_results = analyze(streams, routes, links, cbs, include_propagation=True)
    sp_results = analyze_sp(streams, routes, links)

    rows = []
    print(
        f"\n  {'Stream':<14} {'PCP':<5} {'Class':<12}"
        f" {'CBS WCD':>10} {'SP WCD':>10} {'Deadline':>10}"
        f"  {'CBS':>5} {'SP':>5}"
    )
    print("  " + "-" * 75)

    for stream in sorted(streams, key=lambda s: s.id):
        deadline = _deadline(stream)
        cbs_wcd = cbs_results.get(stream.id)
        sp_wcd = sp_results.get(stream.id)

        cbs_ok = cbs_wcd is not None and deadline is not None and cbs_wcd <= deadline
        sp_ok = sp_wcd is not None and deadline is not None and sp_wcd <= deadline

        cbs_str = f"{cbs_wcd:.1f}" if cbs_wcd is not None else "INFEASIBLE"
        sp_str = f"{sp_wcd:.1f}" if sp_wcd is not None else "INFEASIBLE"
        deadline_str = f"{deadline:.0f}" if deadline is not None else "—"

        print(
            f"  {stream.name:<14} {stream.pcp:<5} {stream.priority_class:<12}"
            f" {cbs_str:>10} {sp_str:>10} {deadline_str:>10}"
            f"  {'✓' if cbs_ok else '✗':>5} {'✓' if sp_ok else '✗':>5}"
        )

        rows.append(
            {
                "stream_id": stream.id,
                "stream_name": stream.name,
                "priority_class": stream.priority_class,
                "cbs_wcd_us": f"{cbs_wcd:.3f}" if cbs_wcd is not None else "",
                "sp_wcd_us": f"{sp_wcd:.3f}" if sp_wcd is not None else "",
                "deadline_us": f"{deadline:.1f}" if deadline is not None else "",
                "cbs_schedulable": str(cbs_ok),
                "sp_schedulable": str(sp_ok),
            }
        )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  Starvation comparison data written to {OUTPUT_CSV}")

    cbs_misses = sum(1 for r in rows if r["cbs_schedulable"] == "False")
    sp_misses = sum(1 for r in rows if r["sp_schedulable"] == "False")
    print(f"\n  Deadline violations — CBS: {cbs_misses}, SP: {sp_misses}")
    if sp_misses > cbs_misses:
        print(
            f"  → CBS prevents starvation: {sp_misses - cbs_misses} stream(s) "
            "schedulable under CBS but infeasible under SP."
        )
    print()


if __name__ == "__main__":
    main()
