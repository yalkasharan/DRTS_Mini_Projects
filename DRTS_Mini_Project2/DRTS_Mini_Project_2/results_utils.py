import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from analytical.model import BEST_EFFORT

EXPECTED_PROJECT_BANDWIDTH_MBPS = 100.0


def ensure_results_dir(project_root: Path) -> Path:
    results_dir = project_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def validate_link_bandwidths(links: Iterable, emit_warning=print) -> None:
    for link in links:
        if abs(float(link.bandwidth_mbps) - EXPECTED_PROJECT_BANDWIDTH_MBPS) > 1e-9:
            emit_warning(
                f"Warning: Link {link.id} has bandwidth {link.bandwidth_mbps:g} Mb/s. "
                "Project spec assumes 100 Mb/s. Results may differ from reference values."
            )


def _stream_deadline(stream) -> Optional[float]:
    if not stream.destinations:
        return None
    return float(stream.destinations[0]["deadline"])


def _is_number(value) -> bool:
    return isinstance(value, (int, float))


def _format_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if _is_number(value):
        return f"{float(value):.6f}"
    return value


def write_analytical_results_csv(streams: List, results: Dict[int, object], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["stream_id", "stream_name", "priority_class", "wcrt_us"],
        )
        writer.writeheader()
        for stream in sorted(streams, key=lambda item: item.id):
            writer.writerow(
                {
                    "stream_id": stream.id,
                    "stream_name": stream.name,
                    "priority_class": stream.priority_class,
                    "wcrt_us": _format_csv_value(results.get(stream.id)),
                }
            )


def write_simulated_results_csv(streams: List, response_times: Dict[int, List[float]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["stream_id", "stream_name", "max_observed_delay_us"],
        )
        writer.writeheader()
        for stream in sorted(streams, key=lambda item: item.id):
            samples = response_times.get(stream.id, [])
            max_delay = max(samples) if samples else None
            writer.writerow(
                {
                    "stream_id": stream.id,
                    "stream_name": stream.name,
                    "max_observed_delay_us": _format_csv_value(max_delay),
                }
            )


def read_analytical_results_csv(csv_path: Path) -> Dict[int, object]:
    results: Dict[int, object] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row["wcrt_us"].strip()
            results[int(row["stream_id"])] = float(value) if value else None
    return results


def read_simulated_results_csv(csv_path: Path) -> Dict[int, Optional[float]]:
    results: Dict[int, Optional[float]] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row["max_observed_delay_us"].strip()
            results[int(row["stream_id"])] = float(value) if value else None
    return results


def write_comparison_csv(
    streams: List,
    analytical_results: Dict[int, object],
    simulated_results: Dict[int, Optional[float]],
    output_path: Path,
    sp_results: Optional[Dict[int, Optional[float]]] = None,
) -> List[dict]:
    fieldnames = [
        "stream_id",
        "stream_name",
        "priority_class",
        "analytical_wcd_us",
        "max_simulated_delay_us",
        "gap_us",
        "bound_satisfied",
    ]
    if sp_results is not None:
        fieldnames.append("sp_wcd_us")

    rows = []
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for stream in sorted(streams, key=lambda item: item.id):
            analytical_value = analytical_results.get(stream.id)
            simulated_value = simulated_results.get(stream.id)
            gap_value = None
            bound_satisfied = None

            if _is_number(analytical_value) and simulated_value is not None:
                gap_value = float(analytical_value) - float(simulated_value)
                bound_satisfied = gap_value >= -1e-9

            row = {
                "stream_id": stream.id,
                "stream_name": stream.name,
                "priority_class": stream.priority_class,
                "analytical_wcd_us": _format_csv_value(analytical_value),
                "max_simulated_delay_us": _format_csv_value(simulated_value),
                "gap_us": _format_csv_value(gap_value),
                "bound_satisfied": "" if bound_satisfied is None else bool(bound_satisfied),
            }
            if sp_results is not None:
                row["sp_wcd_us"] = _format_csv_value(sp_results.get(stream.id))

            writer.writerow(row)
            rows.append(row)

    return rows


def summarize_sp_vs_cbs(streams: List, cbs_results: Dict[int, object], sp_results: Dict[int, Optional[float]]) -> List[str]:
    summary: List[str] = []
    for stream in sorted(streams, key=lambda item: item.id):
        cbs_value = cbs_results.get(stream.id)
        sp_value = sp_results.get(stream.id)
        deadline = _stream_deadline(stream)

        if _is_number(cbs_value) and sp_value is not None:
            if float(cbs_value) < sp_value:
                summary.append(
                    f"Stream {stream.id} ({stream.name}) has a lower WCD under CBS than SP "
                    f"({float(cbs_value):.2f} us vs {sp_value:.2f} us)."
                )
            elif sp_value < float(cbs_value):
                summary.append(
                    f"Stream {stream.id} ({stream.name}) has a lower WCD under SP than CBS "
                    f"({sp_value:.2f} us vs {float(cbs_value):.2f} us)."
                )

        if (
            stream.priority_class == BEST_EFFORT
            and deadline is not None
            and sp_value is not None
            and _is_number(cbs_value)
            and sp_value > deadline
            and float(cbs_value) <= deadline
        ):
            summary.append(
                f"Stream {stream.id} ({stream.name}) misses its deadline under SP "
                f"({sp_value:.2f} us > {deadline:.2f} us) but is schedulable under CBS."
            )

    return summary
