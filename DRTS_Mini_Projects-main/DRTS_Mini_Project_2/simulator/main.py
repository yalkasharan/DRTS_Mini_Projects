"""
TSN AVB CBS Network Simulator.
"""
import argparse
import csv
import math
import sys
from functools import reduce
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytical"))
sys.path.insert(0, str(PROJECT_ROOT / "simulator"))

from model import CBSConfig, display_priority_label  # type: ignore
from results_utils import ensure_results_dir, validate_link_bandwidths, write_simulated_results_csv  # type: ignore
from sim_engine import Simulator  # type: ignore
from tsn_parser import assign_priority_classes, load_routes, load_streams, load_topology  # type: ignore


def _load_analytical_csv(path: str) -> dict:
    reference = {}
    with open(path, newline="", encoding="utf-8") as handle:
        sample = handle.read(1024)
        handle.seek(0)
        if "stream_id" in sample and "wcrt_us" in sample:
            for row in csv.DictReader(handle):
                value = row["wcrt_us"].strip()
                reference[int(row["stream_id"])] = float(value) if value else None
        else:
            for row in csv.DictReader(handle, delimiter="\t"):
                reference[int(row["ID"])] = float(row["WCRT"].replace(",", "."))
    return reference


def _stats(values: list) -> tuple:
    if not values:
        return 0, float("nan"), float("nan"), float("nan")
    return len(values), min(values), sum(values) / len(values), max(values)


def _compute_hyperperiod_us(streams) -> float:
    """Compute the hyperperiod (LCM of all stream periods) in microseconds."""
    periods = [stream.period_us for stream in streams if stream.period_us > 0]
    if not periods:
        return 1_000_000.0  # fallback: 1 second

    def _lcm(a: float, b: float) -> float:
        """LCM for two values, handling floating-point periods."""
        # Convert to integer microseconds (round to avoid float issues)
        a_int = round(a * 1000)
        b_int = round(b * 1000)
        lcm_int = abs(a_int * b_int) // math.gcd(a_int, b_int)
        return lcm_int / 1000.0

    return reduce(_lcm, periods)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TSN AVB CBS Network Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("topology")
    parser.add_argument("streams")
    parser.add_argument("routes")
    parser.add_argument("--idle-slope-a", type=float, default=0.5, metavar="F")
    parser.add_argument("--idle-slope-b", type=float, default=0.5, metavar="F")
    parser.add_argument(
        "--duration", type=float, default=None, metavar="MS",
        help="Simulation duration in ms. Defaults to 2x hyperperiod of all streams.",
    )
    parser.add_argument(
        "--hyperperiods", type=int, default=2, metavar="N",
        help="Number of hyperperiods to simulate (default: 2). Ignored if --duration is set.",
    )
    parser.add_argument("--warmup", type=float, default=10.0, metavar="MS")
    parser.add_argument("--analytical", metavar="PATH")
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=str(PROJECT_ROOT / "results" / "simulated-max-delays.csv"),
    )
    args = parser.parse_args()

    _, links = load_topology(args.topology)
    validate_link_bandwidths(links)
    streams = load_streams(args.streams)
    routes = load_routes(args.routes)
    max_priority_level = assign_priority_classes(streams)

    cbs = CBSConfig.from_legacy_inputs(
        max_priority_level=max_priority_level,
        idle_slope_a=args.idle_slope_a,
        idle_slope_b=args.idle_slope_b,
    )

    hyperperiod_us = _compute_hyperperiod_us(streams)
    hyperperiod_ms = hyperperiod_us / 1e3

    if args.duration is not None:
        duration_us = args.duration * 1e3
        duration_source = "user-specified"
    else:
        duration_us = hyperperiod_us * args.hyperperiods
        duration_source = f"{args.hyperperiods}x hyperperiod"

    warmup_us = args.warmup * 1e3
    duration_ms = duration_us / 1e3
    cbs_streams = [stream for stream in streams if not stream.is_best_effort]

    print("=" * 72)
    print(" TSN AVB CBS Network Simulator")
    print("=" * 72)
    print(f"\n Hyperperiod          : {hyperperiod_ms:.3f} ms  (LCM of all stream periods)")
    print(f" Simulation duration : {duration_ms:.1f} ms  ({duration_source})")
    print(f" Warm-up period      : {args.warmup:.0f} ms")
    if duration_us < hyperperiod_us:
        print(f" *** WARNING: Duration ({duration_ms:.1f} ms) is shorter than one hyperperiod ")
        print(f"     ({hyperperiod_ms:.3f} ms). Worst-case may not be reached. ***")
    print(" CBS queue slopes:")
    for level in range(max_priority_level, 0, -1):
        print(
            f"   P{level}: idle_slope = {cbs.idle_slope(level)}"
            f"  send_slope = {cbs.send_slope(level)}"
        )

    print("\n Running simulation ...", flush=True)
    sim = Simulator(streams, routes, links, cbs, duration_us, warmup_us)
    response_times = sim.run()
    print(" Done.\n")

    # Verify all CBS streams recorded at least one sample
    for stream in cbs_streams:
        assert response_times.get(stream.id), \
            f"Stream {stream.id} ({stream.name}, priority={stream.priority_level}) has no samples recorded. " \
            f"This may indicate a CBS queue assignment or path resolution issue."

    analytical = _load_analytical_csv(args.analytical) if args.analytical else {}
    has_analytical = bool(analytical)

    print("-" * 72)
    print(" End-to-End Response Times  (all times in us)")
    print("-" * 72)

    if has_analytical:
        print(
            f" {'ID':<5} {'Name':<12} {'Class':<12} {'Frames':>7} {'Min':>8} {'Avg':>8} "
            f"{'Max(sim)':>10} {'WCRT(an)':>10} {'Margin':>9} {'Deadline':>9}"
        )
        print(
            f" {'-'*5} {'-'*12} {'-'*12} {'-'*7} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*9} {'-'*9}"
        )
    else:
        print(
            f" {'ID':<5} {'Name':<12} {'Class':<12} {'Frames':>7} {'Min':>8} {'Avg':>8} {'Max(sim)':>10} {'Deadline':>9}"
        )
        print(f" {'-'*5} {'-'*12} {'-'*12} {'-'*7} {'-'*8} {'-'*8} {'-'*10} {'-'*9}")

    missed = 0
    for stream in sorted(streams, key=lambda item: item.id):
        samples = response_times[stream.id]
        count, minimum, average, maximum = _stats(samples)
        deadline = stream.destinations[0]["deadline"] if stream.destinations else None
        label = display_priority_label(stream.priority_level, stream.max_priority_level)

        max_str = f"{maximum:.2f}" if count > 0 else "-"
        avg_str = f"{average:.2f}" if count > 0 else "-"
        min_str = f"{minimum:.2f}" if count > 0 else "-"
        deadline_str = "-" if deadline is None else f"{deadline:.0f}"
        status = "OK" if count > 0 else "(no frames)"
        if deadline is not None and count > 0 and maximum > deadline:
            status = "*** MISSED ***"
            if not stream.is_best_effort:
                missed += 1

        if has_analytical:
            analytical_value = analytical.get(stream.id)
            analytical_str = "-" if analytical_value is None else f"{analytical_value:.2f}"
            margin_str = "-"
            if deadline is not None and count > 0:
                margin_str = f"{deadline - maximum:+.2f}"
            print(
                f" {stream.id:<5} {stream.name:<12} {label:<12} {count:>7} {min_str:>8} {avg_str:>8} "
                f"{max_str:>10} {analytical_str:>10} {margin_str:>9} {deadline_str:>9}  {status}"
            )
        else:
            print(
                f" {stream.id:<5} {stream.name:<12} {label:<12} {count:>7} {min_str:>8} {avg_str:>8} "
                f"{max_str:>10} {deadline_str:>9}  {status}"
            )

    print()
    if missed:
        print(f"  *** {missed}/{len(cbs_streams)} CBS stream(s) exceeded deadline in simulation ***")
    else:
        print(f"  All {len(cbs_streams)} CBS streams met their deadlines in simulation.")

    if has_analytical:
        comparable = [
            (stream.id, max(response_times[stream.id]), analytical[stream.id])
            for stream in cbs_streams
            if response_times[stream.id] and stream.id in analytical and analytical[stream.id] is not None
        ]
        if comparable:
            gaps = [analytical_value - sim_max for _, sim_max, analytical_value in comparable]
            print("\n  Analytical WCRT vs simulated max response time:")
            print(f"    Analytical WCRT is always >= simulated max ({'YES' if all(gap >= -1e-3 for gap in gaps) else 'NO'})")
            print(f"    Avg gap (analytical - sim_max) : {sum(gaps) / len(gaps):.2f} us")
            print(f"    Max gap (analytical - sim_max) : {max(gaps):.2f} us")
            print(f"    Min gap (analytical - sim_max) : {min(gaps):.2f} us")

    output_path = Path(args.output)
    ensure_results_dir(PROJECT_ROOT)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_simulated_results_csv(streams, response_times, output_path)
    print(f"\n  Saved simulated max delays to {output_path}\n")


if __name__ == "__main__":
    main()
