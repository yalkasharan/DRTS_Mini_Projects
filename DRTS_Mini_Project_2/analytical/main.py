"""
TSN AVB CBS Worst-Case Response Time Analyzer.
"""
import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model import BEST_EFFORT, CBSConfig, display_priority_label
from proportional_idle_slopes import compute_proportional_idle_slopes, compute_utilization_summary
from results_utils import ensure_results_dir, validate_link_bandwidths, write_analytical_results_csv
from tsn_parser import assign_priority_classes, load_routes, load_streams, load_topology
from wcrt_analysis import analyze


def _load_reference_wcrts(csv_path: str) -> dict:
    reference = {}
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            reference[int(row["ID"])] = float(row["WCRT"].replace(",", "."))
    return reference


def _print_cbs_config(cbs: CBSConfig, max_priority_level: int) -> None:
    print(" CBS queue slopes:")
    if max_priority_level <= 0:
        print("   No CBS queues present")
        return
    for level in range(max_priority_level, 0, -1):
        print(
            f"   P{level}: idle_slope = {cbs.idle_slope(level)}"
            f"  send_slope = {cbs.send_slope(level)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TSN AVB CBS Worst-Case Response Time Analyzer (Cao 2016/2018)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("topology", help="Path to topology.json")
    parser.add_argument("streams", help="Path to streams.json")
    parser.add_argument("routes", help="Path to routes.json")
    parser.add_argument("--idle-slope-a", type=float, default=0.5, metavar="FLOAT")
    parser.add_argument("--idle-slope-b", type=float, default=0.5, metavar="FLOAT")
    parser.add_argument("--propagation", action="store_true")
    parser.add_argument("--fixed-point", action="store_true")
    parser.add_argument("--proportional-idle-slopes", action="store_true",
                       help="Compute idle slopes based on per-link stream utilization (overrides --idle-slope-a/b)")
    parser.add_argument("--csv", metavar="PATH")
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=str(PROJECT_ROOT / "results" / "analytical-WCDs.csv"),
    )
    args = parser.parse_args()

    _, links = load_topology(args.topology)
    validate_link_bandwidths(links)
    streams = load_streams(args.streams)
    routes = load_routes(args.routes)
    max_priority_level = assign_priority_classes(streams)

    if args.proportional_idle_slopes:
        idle_slopes = compute_proportional_idle_slopes(streams, links, max_priority_level)
        cbs = CBSConfig(idle_slopes=idle_slopes)
        idle_source = "proportional (utilization-based)"
    else:
        cbs = CBSConfig.from_legacy_inputs(
            max_priority_level=max_priority_level,
            idle_slope_a=args.idle_slope_a,
            idle_slope_b=args.idle_slope_b,
        )
        idle_source = "user-specified"

    print("=" * 70)
    print(" TSN AVB CBS WCRT Analyzer")
    print("=" * 70)
    _print_cbs_config(cbs, max_priority_level)
    print(f" Idle slope source        : {idle_source}")
    print(f" Include propagation delays: {args.propagation}")
    print(f" Fixed-point mode active  : {args.fixed_point}")
    if args.proportional_idle_slopes:
        util_summary = compute_utilization_summary(streams, links)
        print(f"\n Stream utilization by priority class:")
        for level in sorted(util_summary.keys()):
            print(f"   Priority {level}: {util_summary[level]:.1%}")
    print()

    print(
        f" {'ID':<5} {'Name':<12} {'PCP':<5} {'Level':<5} {'Class':<12}"
        f" {'Size(B)':<9} {'Period(us)':<12} {'Deadline(us)'}"
    )
    print(
        f" {'-'*5} {'-'*12} {'-'*5} {'-'*5} {'-'*12} {'-'*9} {'-'*12} {'-'*12}"
    )
    for stream in sorted(streams, key=lambda item: item.id):
        deadline = stream.destinations[0]["deadline"] if stream.destinations else "-"
        print(
            f" {stream.id:<5} {stream.name:<12} {stream.pcp:<5} {stream.priority_level:<5} "
            f"{display_priority_label(stream.priority_level, stream.max_priority_level):<12} "
            f"{stream.size_bytes:<9} {stream.period_us:<12.1f} {deadline}"
        )

    single_instance_results = analyze(
        streams,
        routes,
        links,
        cbs,
        include_propagation=args.propagation,
        fixed_point=False,
    )
    results = single_instance_results
    fixed_point_results = None

    if args.fixed_point:
        fixed_point_results = analyze(
            streams,
            routes,
            links,
            cbs,
            include_propagation=args.propagation,
            fixed_point=True,
        )
        results = fixed_point_results

    reference = _load_reference_wcrts(args.csv) if args.csv else {}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'-'*70}")
    print(" WCRT Results")
    print(f"{'-'*70}")

    if reference:
        print(
            f" {'ID':<5} {'Name':<12} {'Class':<12} {'WCRT(us)':>10} {'Ref(us)':>10} "
            f"{'Error(us)':>10} {'Deadline(us)':>13} Status"
        )
        print(
            f" {'-'*5} {'-'*12} {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*13} {'-'*10}"
        )
    else:
        print(f" {'ID':<5} {'Name':<12} {'Class':<12} {'WCRT(us)':>10} {'Deadline(us)':>13} Status")
        print(f" {'-'*5} {'-'*12} {'-'*12} {'-'*10} {'-'*13} {'-'*10}")

    missed = 0
    for stream in sorted(streams, key=lambda item: item.id):
        wcrt = results[stream.id]
        deadline = stream.destinations[0]["deadline"] if stream.destinations else None
        status = "OK"
        if wcrt is None:
            status = "(unschedulable)"
        elif deadline is not None and wcrt > deadline:
            status = "*** MISSED ***"
            missed += 1

        wcrt_str = "N/A" if wcrt is None else f"{wcrt:.2f}"
        deadline_str = "-" if deadline is None else f"{deadline:.1f}"
        class_label = display_priority_label(stream.priority_level, stream.max_priority_level)

        if reference:
            ref_value = reference.get(stream.id)
            ref_str = "-" if ref_value is None else f"{ref_value:.2f}"
            err_str = "-"
            if wcrt is not None and ref_value is not None:
                err_str = f"{wcrt - ref_value:+.2f}"
            print(
                f" {stream.id:<5} {stream.name:<12} {class_label:<12} {wcrt_str:>10} "
                f"{ref_str:>10} {err_str:>10} {deadline_str:>13} {status}"
            )
        else:
            print(
                f" {stream.id:<5} {stream.name:<12} {class_label:<12} {wcrt_str:>10} "
                f"{deadline_str:>13} {status}"
            )

    print(f"{'-'*70}")
    if missed:
        print(f"\n  *** {missed} stream(s) missed their deadline. ***")
    else:
        avb_streams = [stream for stream in streams if not stream.is_best_effort]
        print(f"\n  All {len(avb_streams)} CBS streams meet their deadlines.")

    if args.fixed_point and fixed_point_results is not None:
        print("\n  Fixed-point comparison vs single-instance:")
        for stream in sorted(streams, key=lambda item: item.id):
            if stream.is_best_effort:
                continue
            fp_value = fixed_point_results.get(stream.id)
            single_value = single_instance_results.get(stream.id)
            if fp_value is None or single_value is None:
                relation = "unschedulable"
                delta = "N/A"
            else:
                relation = "tighter" if fp_value < single_value - 1e-9 else "equal"
                delta = f"{single_value - fp_value:.2f} us"
            print(f"    Stream {stream.id}: fixed-point is {relation} by {delta}")

    ensure_results_dir(PROJECT_ROOT)
    write_analytical_results_csv(streams, results, output_path)
    print(f"\n  Saved analytical results to {output_path}")


if __name__ == "__main__":
    main()
