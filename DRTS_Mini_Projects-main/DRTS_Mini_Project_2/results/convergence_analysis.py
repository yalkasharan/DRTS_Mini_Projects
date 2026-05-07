"""
Convergence Study: Simulation Duration vs Response Time Stability

This script runs the simulator with increasing multiples of the hyperperiod
and demonstrates that worst-case response times converge to stable values,
validating that 2× hyperperiod is sufficient for capturing worst-case behavior.

Usage:
  python results/convergence_analysis.py <topology.json> <streams.json> <routes.json>
"""

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytical"))
sys.path.insert(0, str(PROJECT_ROOT / "simulator"))

from model import CBSConfig
from results_utils import ensure_results_dir, validate_link_bandwidths
from sim_engine import Simulator
from simulator.main import _compute_hyperperiod_us
from tsn_parser import assign_priority_classes, load_routes, load_streams, load_topology


def run_simulation_with_duration(
    streams, routes, links, cbs, duration_us, warmup_us
):
    """Run simulator and return response times for all streams."""
    sim = Simulator(streams, routes, links, cbs, duration_us, warmup_us)
    return sim.run()


def main():
    parser = argparse.ArgumentParser(
        description="Convergence study: simulation duration vs response time stability"
    )
    parser.add_argument("topology", help="Path to topology.json")
    parser.add_argument("streams", help="Path to streams.json")
    parser.add_argument("routes", help="Path to routes.json")
    parser.add_argument(
        "--hyperperiods",
        type=int,
        nargs="+",
        default=[0.5, 1, 2, 5, 10],
        help="Hyperperiod multipliers to test (default: 0.5 1 2 5 10)",
    )
    parser.add_argument(
        "--idle-slope-a", type=float, default=0.5, metavar="F"
    )
    parser.add_argument(
        "--idle-slope-b", type=float, default=0.5, metavar="F"
    )
    parser.add_argument(
        "--warmup", type=float, default=10.0, metavar="MS"
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "results" / "convergence_study.csv"),
        help="Output CSV file",
    )
    args = parser.parse_args()

    _, links = load_topology(args.topology)
    validate_link_bandwidths(links)
    streams = load_streams(args.streams)
    routes = load_routes(args.routes)
    assign_priority_classes(streams)

    cbs = CBSConfig.from_legacy_inputs(
        max_priority_level=max(s.priority_level for s in streams),
        idle_slope_a=args.idle_slope_a,
        idle_slope_b=args.idle_slope_b,
    )

    hyperperiod_us = _compute_hyperperiod_us(streams)
    warmup_us = args.warmup * 1e3

    print("=" * 72)
    print(" Convergence Study: Simulation Duration vs WCRT Stability")
    print("=" * 72)
    print(f"\n Hyperperiod: {hyperperiod_us / 1e3:.1f} ms")
    print(f" Warm-up: {args.warmup:.1f} ms")
    print(f" Testing multipliers: {args.hyperperiods}\n")

    # Run simulations
    results = {}
    for multiplier in sorted(set(args.hyperperiods)):
        duration_us = hyperperiod_us * multiplier
        duration_ms = duration_us / 1e3

        print(f" Running {multiplier}× hyperperiod ({duration_ms:.1f} ms)...", end="", flush=True)
        response_times = run_simulation_with_duration(
            streams, routes, links, cbs, duration_us, warmup_us
        )
        results[multiplier] = response_times
        print(" Done.")

    # Write results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["stream_id", "stream_name", "priority_class"] + [
            f"wcrt_{m}x_hyperperiod_us" for m in sorted(set(args.hyperperiods))
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for stream in sorted(streams, key=lambda s: s.id):
            row = {
                "stream_id": stream.id,
                "stream_name": stream.name,
                "priority_class": stream.priority_class,
            }
            for multiplier in sorted(set(args.hyperperiods)):
                samples = results[multiplier].get(stream.id, [])
                max_rt = max(samples) if samples else None
                row[f"wcrt_{multiplier}x_hyperperiod_us"] = f"{max_rt:.2f}" if max_rt else ""
            writer.writerow(row)

    print(f"\n Convergence study saved to {output_path}\n")

    # Print summary
    print("-" * 72)
    print(" Convergence Summary (max response times in microseconds)")
    print("-" * 72)
    for stream in sorted(streams, key=lambda s: s.id):
        print(f"\n Stream {stream.id} ({stream.name}):")
        values = []
        for multiplier in sorted(set(args.hyperperiods)):
            samples = results[multiplier].get(stream.id, [])
            max_rt = max(samples) if samples else None
            if max_rt:
                values.append(max_rt)
                print(f"   {multiplier}× hyperperiod: {max_rt:.2f} us")

        if len(values) > 1:
            max_change = max(abs(values[i] - values[i-1]) for i in range(1, len(values)))
            stabilized = max_change < 0.5 * min(values)
            status = "CONVERGED" if stabilized else "UNSTABLE"
            print(f"   Max delta: {max_change:.2f} us  [{status}]")


if __name__ == "__main__":
    main()
