#!/usr/bin/env python3
"""
Generate the extra CSV files needed for charts 5-8.

Creates:
  results/credit_log.csv            -> Chart 5 (CBS credit evolution)
  results/per_hop_wcrt.csv          -> Chart 6 (per-hop WCD breakdown)
  results/multi_testcase_summary.csv -> Chart 7 (utilization vs WCD)
  results/fixedpoint_comparison.csv  -> Chart 8 (single-instance vs fixed-point)

Usage:
    python generate_extra_csvs.py
"""
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytical"))
sys.path.insert(0, str(PROJECT_ROOT / "simulator"))

from model import CBSConfig, priority_label
from tsn_parser import load_topology, load_streams, load_routes, assign_priority_classes
from wcrt_analysis import (
    analyze,
    get_path_links,
    get_coflows,
    _build_link_lookup,
    _single_instance_cbs_link_wcrt,
    _best_effort_link_wcrt,
    _tx_time,
)
from sim_engine import Simulator

RESULTS_DIR = PROJECT_ROOT / "results"
REQUIRED_FILES = PROJECT_ROOT / "Required Files"

TEST_CASES = [
    ("test-case-1", REQUIRED_FILES / "test_case_1"),
    ("test-case-2", REQUIRED_FILES / "test_case_2"),
    ("test-case-3", REQUIRED_FILES / "test_case_3"),
]


def load_case(case_dir):
    """Load and return all data for a single test case."""
    _, links = load_topology(str(case_dir / "topology.json"))
    streams = load_streams(str(case_dir / "streams.json"))
    routes = load_routes(str(case_dir / "routes.json"))
    max_level = assign_priority_classes(streams)
    cbs = CBSConfig.from_legacy_inputs(max_priority_level=max_level)
    return links, streams, routes, max_level, cbs


def generate_per_hop_wcrt():
    """Chart 6: per-hop WCD breakdown for test-case-1."""
    case_name, case_dir = TEST_CASES[0]
    links, streams, routes, _, cbs = load_case(case_dir)
    route_map = {r.flow_id: r for r in routes}
    link_lookup = _build_link_lookup(links)

    rows = []
    for stream in sorted(streams, key=lambda s: s.id):
        route = route_map.get(stream.id)
        if route is None:
            continue
        path_links = get_path_links(route.paths[0], link_lookup)
        for hop_idx, link in enumerate(path_links):
            coflows = get_coflows(link, streams, route_map, link_lookup)
            if stream.is_best_effort:
                wcrt = _best_effort_link_wcrt(stream, link, coflows)
            else:
                wcrt = _single_instance_cbs_link_wcrt(stream, link, coflows, cbs)
            rows.append({
                "stream_id": stream.id,
                "hop_index": hop_idx,
                "link_id": link.id,
                "wcrt_us": f"{wcrt:.6f}",
                "propagation_delay_us": f"{link.delay_us:.6f}",
            })

    out = RESULTS_DIR / "per_hop_wcrt.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stream_id", "hop_index", "link_id", "wcrt_us", "propagation_delay_us"])
        w.writeheader()
        w.writerows(rows)
    print(f"  Generated {out.name} ({len(rows)} rows)")


def generate_multi_testcase_summary():
    """Chart 7: analytical WCD and link utilization across all test cases."""
    rows = []
    for case_name, case_dir in TEST_CASES:
        if not case_dir.exists():
            print(f"  Skipping {case_name}: {case_dir} not found")
            continue

        links, streams, routes, max_level, cbs = load_case(case_dir)
        route_map = {r.flow_id: r for r in routes}
        link_lookup = _build_link_lookup(links)
        results = analyze(streams, routes, links, cbs, fixed_point=False)

        for stream in sorted(streams, key=lambda s: s.id):
            route = route_map.get(stream.id)
            if route is None:
                continue
            # Compute max link utilization along this stream's path
            path_links = get_path_links(route.paths[0], link_lookup)
            max_util = 0.0
            for link in path_links:
                coflows = get_coflows(link, streams, route_map, link_lookup)
                util = sum(
                    _tx_time(s.size_bytes, link.bandwidth_mbps) / s.period_us
                    for s in coflows
                ) * 100.0
                max_util = max(max_util, util)

            rows.append({
                "test_case": case_name,
                "stream_id": stream.id,
                "stream_name": stream.name,
                "priority_class": stream.priority_class,
                "link_utilization_percent": f"{max_util:.2f}",
                "analytical_wcd_us": f"{results[stream.id]:.6f}" if results[stream.id] is not None else "",
            })

    out = RESULTS_DIR / "multi_testcase_summary.csv"
    fields = ["test_case", "stream_id", "stream_name", "priority_class", "link_utilization_percent", "analytical_wcd_us"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  Generated {out.name} ({len(rows)} rows)")


def generate_fixedpoint_comparison():
    """Chart 8: single-instance vs fixed-point WCD for test-case-1."""
    case_name, case_dir = TEST_CASES[0]
    links, streams, routes, _, cbs = load_case(case_dir)

    single = analyze(streams, routes, links, cbs, fixed_point=False)
    fixed = analyze(streams, routes, links, cbs, fixed_point=True)

    rows = []
    for stream in sorted(streams, key=lambda s: s.id):
        if stream.is_best_effort:
            continue
        s_val = single.get(stream.id)
        f_val = fixed.get(stream.id)
        rows.append({
            "stream_id": stream.id,
            "stream_name": stream.name,
            "priority_class": stream.priority_class,
            "single_instance_wcd_us": f"{s_val:.6f}" if s_val is not None else "",
            "fixed_point_wcd_us": f"{f_val:.6f}" if f_val is not None else "",
        })

    out = RESULTS_DIR / "fixedpoint_comparison.csv"
    fields = ["stream_id", "stream_name", "priority_class", "single_instance_wcd_us", "fixed_point_wcd_us"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  Generated {out.name} ({len(rows)} rows)")


def generate_credit_log():
    """Chart 5: CBS credit evolution from a short simulation run."""
    case_name, case_dir = TEST_CASES[0]
    links, streams, routes, _, cbs = load_case(case_dir)

    # Run a shorter simulation (200ms) to keep the CSV manageable
    duration_us = 200_000.0
    warmup_us = 10_000.0

    print("  Running simulation with credit logging (200 ms) ...")
    sim = Simulator(streams, routes, links, cbs, duration_us, warmup_us, log_credits=True)
    sim.run()

    out = RESULTS_DIR / "credit_log.csv"
    fields = ["time_us", "link_id", "queue_class", "credit", "event_type"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for entry in sim.credit_log:
            w.writerow({
                "time_us": f"{entry['time_us']:.6f}",
                "link_id": entry["link_id"],
                "queue_class": entry["queue_class"],
                "credit": f"{entry['credit']:.6f}",
                "event_type": entry["event_type"],
            })
    print(f"  Generated {out.name} ({len(sim.credit_log)} rows)")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print(" Generating extra CSV files for Charts 5-8")
    print("=" * 60)

    print("\n[1/4] Per-hop WCD breakdown (chart 6) ...")
    generate_per_hop_wcrt()

    print("\n[2/4] Multi test-case summary (chart 7) ...")
    generate_multi_testcase_summary()

    print("\n[3/4] Fixed-point comparison (chart 8) ...")
    generate_fixedpoint_comparison()

    print("\n[4/4] Credit log (chart 5) ...")
    generate_credit_log()

    print("\n" + "=" * 60)
    print(" All 4 CSV files generated in results/")
    print(" Now run: python results/generate_plots.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
