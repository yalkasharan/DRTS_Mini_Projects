import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytical"))

from results_utils import (
    ensure_results_dir,
    read_analytical_results_csv,
    read_simulated_results_csv,
    summarize_sp_vs_cbs,
    validate_link_bandwidths,
    write_comparison_csv,
)
from sp_rta import analyze_sp
from tsn_parser import assign_priority_classes, load_routes, load_streams, load_topology


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate analytical vs simulated comparison output for test-case results.",
    )
    parser.add_argument("topology", help="Path to topology.json")
    parser.add_argument("streams", help="Path to streams.json")
    parser.add_argument("routes", help="Path to routes.json")
    parser.add_argument(
        "--analytical",
        default=str(PROJECT_ROOT / "results" / "analytical-WCDs.csv"),
        help="Path to analytical results CSV",
    )
    parser.add_argument(
        "--simulated",
        default=str(PROJECT_ROOT / "results" / "simulated-max-delays.csv"),
        help="Path to simulated max delay CSV",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "results" / "comparison.csv"),
        help="Path to write the combined comparison CSV",
    )
    args = parser.parse_args()

    _, links = load_topology(args.topology)
    validate_link_bandwidths(links)
    streams = load_streams(args.streams)
    routes = load_routes(args.routes)
    assign_priority_classes(streams)

    analytical_results = read_analytical_results_csv(Path(args.analytical))
    simulated_results = read_simulated_results_csv(Path(args.simulated))
    sp_results = analyze_sp(streams, routes, links)

    ensure_results_dir(PROJECT_ROOT)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = write_comparison_csv(
        streams,
        analytical_results,
        simulated_results,
        output_path,
        sp_results=sp_results,
    )

    print(f"Saved combined comparison to {output_path}")

    violations = [row for row in rows if row["bound_satisfied"] is False]
    for row in violations:
        print(
            f"Warning: Stream {row['stream_id']} ({row['stream_name']}) violates the analytical bound "
            f"(gap {row['gap_us']} us)."
        )

    summary = summarize_sp_vs_cbs(streams, analytical_results, sp_results)
    if summary:
        print("\nSP vs CBS summary:")
        for line in summary:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
