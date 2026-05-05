"""
Pessimism Analysis: Bound Tightness Assessment

This script analyzes the gap between analytical bounds and simulated results,
measuring how conservative (pessimistic) the analytical WCRT analysis is.

The gap represents the over-approximation: 
  gap = analytical_wcrt - simulated_max_delay

Positive gaps indicate the bound is conservative; zero/negative gaps indicate
either a bug or that the simulation didn't capture the worst case.

Usage:
  python results/pessimism_analysis.py --analytical results/analytical-WCDs.csv \
                                       --simulated results/simulated-max-delays.csv \
                                       --topology Required\ Files/test_case_1/topology.json \
                                       --streams Required\ Files/test_case_1/streams.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytical"))

from results_utils import read_analytical_results_csv, read_simulated_results_csv


def load_streams_metadata(streams_path: str) -> Dict[int, dict]:
    """Load stream metadata for classification."""
    with open(streams_path) as f:
        data = json.load(f)
    streams = {}
    for s in data.get("streams", []):
        streams[s["id"]] = {
            "name": s["name"],
            "pcp": s["PCP"],
            "size": s["size"],
            "period": s["period"],
        }
    return streams


def categorize_pessimism(gap: float, value: float) -> Tuple[str, str]:
    """Categorize pessimism level."""
    if value == 0:
        return "Unschedulable", "unschedulable"
    
    ratio = gap / value if value > 0 else 0
    
    if gap < 0:
        return "VIOLATION (gap < 0)", "violation"
    elif ratio < 0.1:
        return "Tight (< 10%)", "tight"
    elif ratio < 0.25:
        return "Moderate (10-25%)", "moderate"
    elif ratio < 0.5:
        return "Conservative (25-50%)", "conservative"
    else:
        return "Very Conservative (> 50%)", "very_conservative"


def main():
    parser = argparse.ArgumentParser(
        description="Analyze pessimism in analytical bounds"
    )
    parser.add_argument(
        "--analytical",
        required=True,
        help="Path to analytical results CSV",
    )
    parser.add_argument(
        "--simulated",
        required=True,
        help="Path to simulated results CSV",
    )
    parser.add_argument(
        "--topology",
        help="Path to topology.json (optional, for link count)",
    )
    parser.add_argument(
        "--streams",
        help="Path to streams.json (optional, for stream metadata)",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "results" / "pessimism_analysis.csv"),
        help="Output CSV file",
    )
    args = parser.parse_args()

    analytical = read_analytical_results_csv(Path(args.analytical))
    simulated = read_simulated_results_csv(Path(args.simulated))
    
    streams_meta = {}
    if args.streams:
        streams_meta = load_streams_metadata(args.streams)

    print("=" * 80)
    print(" Pessimism Analysis: Bound Tightness Assessment")
    print("=" * 80)

    gaps = []
    ratios = []
    
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "stream_id",
            "stream_name",
            "pcp",
            "size_bytes",
            "period_us",
            "analytical_wcrt_us",
            "simulated_max_us",
            "gap_us",
            "gap_ratio",
            "pessimism_category",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for sid in sorted(analytical.keys()):
            anal_val = analytical.get(sid)
            sim_val = simulated.get(sid)

            if anal_val is None or sim_val is None:
                continue

            gap = float(anal_val) - float(sim_val)
            ratio = gap / float(anal_val) if float(anal_val) > 0 else 0
            category, _ = categorize_pessimism(gap, float(anal_val))

            gaps.append(gap)
            ratios.append(ratio)

            meta = streams_meta.get(sid, {})
            row = {
                "stream_id": sid,
                "stream_name": meta.get("name", f"Stream{sid}"),
                "pcp": meta.get("pcp", "-"),
                "size_bytes": meta.get("size", "-"),
                "period_us": meta.get("period", "-"),
                "analytical_wcrt_us": f"{float(anal_val):.2f}",
                "simulated_max_us": f"{float(sim_val):.2f}",
                "gap_us": f"{gap:.2f}",
                "gap_ratio": f"{ratio:.1%}",
                "pessimism_category": category,
            }
            writer.writerow(row)

    print(f"\n Pessimism analysis saved to {args.output}\n")

    # Print statistics
    if gaps:
        print("-" * 80)
        print(" Pessimism Statistics (all streams)")
        print("-" * 80)
        
        valid_gaps = [g for g in gaps if g >= 0]
        valid_ratios = [r for r in ratios if r >= 0]
        
        if valid_gaps:
            print(f" Total streams analyzed : {len(gaps)}")
            print(f" Streams with valid gaps: {len(valid_gaps)}")
            print(f" Violations (gap < 0)   : {len(gaps) - len(valid_gaps)}")
            print()
            print(f" Gap (analytical - simulated):")
            print(f"   Min  : {min(valid_gaps):>10.2f} us")
            print(f"   Max  : {max(valid_gaps):>10.2f} us")
            print(f"   Mean : {sum(valid_gaps) / len(valid_gaps):>10.2f} us")
            print(f"   Median: {sorted(valid_gaps)[len(valid_gaps)//2]:>10.2f} us")
            print()
            print(f" Gap ratio (gap / analytical):")
            print(f"   Min  : {min(valid_ratios):>10.1%}")
            print(f"   Max  : {max(valid_ratios):>10.1%}")
            print(f"   Mean : {sum(valid_ratios) / len(valid_ratios):>10.1%}")
            print()
            
            # Category distribution
            categories = {"Tight": 0, "Moderate": 0, "Conservative": 0, "Very Conservative": 0, "Other": 0}
            for g, v in zip(gaps, [analytical.get(sid) for sid in sorted(analytical.keys())]):
                if g < 0:
                    cat = "Violation"
                else:
                    ratio = g / v if v and v > 0 else 0
                    if ratio < 0.1:
                        cat = "Tight"
                    elif ratio < 0.25:
                        cat = "Moderate"
                    elif ratio < 0.5:
                        cat = "Conservative"
                    else:
                        cat = "Very Conservative"
                categories[cat] = categories.get(cat, 0) + 1
            
            print(" Pessimism distribution:")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
                pct = 100 * count / len(gaps) if gaps else 0
                print(f"   {cat:>20s}: {count:>3d} streams ({pct:>5.1f}%)")
    
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
