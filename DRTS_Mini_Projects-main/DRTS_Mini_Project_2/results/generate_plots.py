from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use('Agg')  # Set backend BEFORE importing pyplot
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"
PLOTS_DIR = RESULTS_DIR / "plots"

MIN_FIGSIZE = (12, 6)
DPI = 150

ANALYTICAL_RED = "#c62828"
SIM_BLUE = "#1565c0"
SP_ORANGE = "#ef6c00"
CBS_GREEN = "#2e7d32"
DEADLINE_GRAY = "#757575"
WARNING_RED = "#ff1744"
SINGLE_YELLOW = "#f9a825"
FIXED_PURPLE = "#7b1fa2"

PRIORITY_LABELS = {
    "CLASS_A": "AVB-A",
    "CLASS_B": "AVB-B",
    "BEST_EFFORT": "BE",
    "AVB-A": "AVB-A",
    "AVB-B": "AVB-B",
    "BE": "BE",
}

PRIORITY_ORDER = {"AVB-A": 0, "AVB-B": 1, "BE": 2}
PRIORITY_COLORS = {"AVB-A": ANALYTICAL_RED, "AVB-B": SIM_BLUE, "BE": DEADLINE_GRAY}


def configure_style() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update(
        {
            "figure.dpi": DPI,
            "savefig.dpi": DPI,
            "axes.titlesize": 15,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 11,
        }
    )


def normalize_priority(value: object) -> str:
    return PRIORITY_LABELS.get(str(value), str(value))


def warn_skip(chart_number: int, filename: str, hint: str) -> None:
    print(f"Skipping Chart {chart_number}: {filename} not found. Run {hint} first.")


def load_csv(filename: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS_DIR / filename)


def save_and_show(fig: plt.Figure, filename: str) -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / filename, bbox_inches="tight", dpi=DPI)
    plt.close(fig)


def add_bar_labels(ax: plt.Axes, bars: Iterable, fmt: str = "{:.1f}", position: str = "outside") -> None:
    for bar in bars:
        height = bar.get_height()
        if pd.isna(height):
            continue
        
        # Rule 2: Only place label inside bar if height > 60 units
        if position == "inside" and height > 60:
            # Position label inside the bar, centered
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height / 2,
                fmt.format(height),
                ha="center",
                va="center",
                fontsize=8.5,
                fontweight="bold",
                color="white",
            )
        else:
            # Position label above the bar with minimum 25-unit gap (Rule 3)
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height + max(height * 0.05, 25),
                fmt.format(height),
                ha="center",
                va="bottom",
                fontsize=8.5,
            )


def sort_streams(df: pd.DataFrame) -> pd.DataFrame:
    ordered = df.copy()
    ordered["priority_class"] = ordered["priority_class"].map(normalize_priority)
    ordered["priority_rank"] = ordered["priority_class"].map(PRIORITY_ORDER).fillna(99)
    return ordered.sort_values(["priority_rank", "stream_id"]).reset_index(drop=True)


def load_test_case_stream_metadata(test_case: str) -> Dict[int, dict]:
    # Try multiple path patterns to find the streams.json file
    possible_paths = [
        PROJECT_ROOT / "mini-project-2" / test_case,
        PROJECT_ROOT / "mini-project-2" / test_case.replace("test-case-", "test_case_"),
        PROJECT_ROOT / "Required Files" / test_case.replace("test-case-", "test_case_"),
        PROJECT_ROOT / "Required Files" / test_case,
    ]
    
    for base_dir in possible_paths:
        if base_dir.exists():
            stream_files = list(base_dir.glob("*-streams.json")) or list(base_dir.glob("streams.json"))
            if stream_files:
                with stream_files[0].open(encoding="utf-8") as handle:
                    data = json.load(handle)
                
                metadata: Dict[int, dict] = {}
                for stream in data.get("streams", []):
                    destinations = stream.get("destinations", [])
                    metadata[int(stream["id"])] = {
                        "name": stream.get("name", f"Stream{stream['id']}"),
                        "deadline_us": float(destinations[0]["deadline"]) if destinations else np.nan,
                    }
                return metadata
    
    return {}


def enrich_deadlines(df: pd.DataFrame, test_case: str = "test-case-1") -> pd.DataFrame:
    if "deadline_us" in df.columns:
        df["deadline_us"] = pd.to_numeric(df["deadline_us"], errors="coerce")
        if df["deadline_us"].notna().all():
            return df

    metadata = load_test_case_stream_metadata(test_case)
    enriched = df.copy()

    def resolve_deadline(row: pd.Series) -> float:
        if pd.notna(row.get("deadline_us", np.nan)):
            return float(row["deadline_us"])
        stream_meta = metadata.get(int(row["stream_id"]))
        if stream_meta:
            return float(stream_meta["deadline_us"])
        return np.nan

    enriched["deadline_us"] = enriched.apply(resolve_deadline, axis=1)
    return enriched


def chart1() -> bool:
    csv_name = "comparison.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(1, csv_name, "python compare_results.py")
        return False

    df = enrich_deadlines(sort_streams(load_csv(csv_name)), test_case="test-case-1")
    fig, ax = plt.subplots(figsize=MIN_FIGSIZE, dpi=DPI)

    x = np.arange(len(df))
    width = 0.38
    sim_colors = np.where(
        df["max_simulated_delay_us"] > df["analytical_wcd_us"],
        WARNING_RED,
        SIM_BLUE,
    )

    bars_analytical = ax.bar(
        x - width / 2,
        df["analytical_wcd_us"],
        width,
        color=ANALYTICAL_RED,
        label="Analytical WCD",
    )
    bars_sim = ax.bar(
        x + width / 2,
        df["max_simulated_delay_us"],
        width,
        color=sim_colors,
        label="Simulated Max Delay",
    )

    for idx, deadline in enumerate(df["deadline_us"]):
        if pd.notna(deadline):
            ax.hlines(
                deadline,
                idx - 0.5,
                idx + 0.5,
                colors=DEADLINE_GRAY,
                linestyles="--",
                linewidth=1.5,
            )

    for idx, row in df.iterrows():
        if row["max_simulated_delay_us"] > row["analytical_wcd_us"]:
            # Rule 3: Position warning with sufficient gap above bar label
            ax.annotate(
                "Warning",
                xy=(idx + width / 2, row["max_simulated_delay_us"]),
                xytext=(0, 40),
                textcoords="offset points",
                ha="center",
                color=WARNING_RED,
                fontsize=9,
                fontweight="bold",
                arrowprops={"arrowstyle": "->", "color": WARNING_RED, "lw": 1},
            )

    add_bar_labels(ax, bars_analytical)
    add_bar_labels(ax, bars_sim)

    ax.set_xticks(x)
    ax.set_xticklabels(df["stream_name"])
    for tick, priority in zip(ax.get_xticklabels(), df["priority_class"]):
        tick.set_color(PRIORITY_COLORS.get(priority, "black"))
        tick.set_fontweight("bold")

    ax.set_ylabel("Delay (microseconds)")
    ax.set_xlabel("Streams   (label color: red = AVB-A, blue = AVB-B, grey = BE)", fontsize=11)
    ax.set_title("Analytical WCD vs Simulated Max Delay — Test Case 1")
    legend_items = [
        Patch(facecolor=ANALYTICAL_RED, label="Analytical WCD"),
        Patch(facecolor=SIM_BLUE, label="Simulated Max Delay"),
        Patch(facecolor=WARNING_RED, label="Bound Violated in Simulation"),
        Line2D([0], [0], color=DEADLINE_GRAY, linestyle="--", linewidth=1.5, label="Deadline"),
    ]
    ax.legend(handles=legend_items, loc="upper left")
    save_and_show(fig, "chart1_analytical_vs_simulated.png")
    return True


def _gap_color(gap: float, analytical: float) -> str:
    if pd.isna(gap) or pd.isna(analytical) or analytical <= 0:
        return "#ffffff"
    ratio = gap / analytical
    if ratio > 0.20:
        return "#2e7d32"
    if ratio >= 0.05:
        return "#fdd835"
    return "#fb8c00"


def prepare_comparison_df(test_case: str = "test-case-1") -> pd.DataFrame:
    df = enrich_deadlines(sort_streams(load_csv("comparison.csv")), test_case=test_case).copy()
    numeric_columns = ["analytical_wcd_us", "max_simulated_delay_us", "gap_us", "deadline_us"]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["gap_us"] = df.get("gap_us", df["analytical_wcd_us"] - df["max_simulated_delay_us"])
    df["gap_pct"] = np.where(
        df["analytical_wcd_us"] > 0,
        (df["gap_us"] / df["analytical_wcd_us"]) * 100.0,
        np.nan,
    )
    df["tightness_pct"] = np.where(
        df["analytical_wcd_us"] > 0,
        (df["max_simulated_delay_us"] / df["analytical_wcd_us"]) * 100.0,
        np.nan,
    )
    return df


def build_gap_bands(gap_pct: pd.Series) -> Tuple[pd.Series, Dict[str, str]]:
    """
    Categorize gaps into fixed, meaningful ranges for DRTS analysis.
    
    Gap % shows how conservative the analysis is:
    - >= 50%: Very conservative bound (lots of headroom)
    - 25-50%: Moderately conservative bound
    - 0-25%: Tight bound (close to simulation)
    - < 0%: Bound violated (simulation exceeded analysis)
    """
    colors = {
        "Tight (0-25% gap)": "#ef6c00",        # Orange: tight bounds
        "Moderate (25-50% gap)": "#fdd835",    # Yellow: moderate bounds
        "Conservative (≥50% gap)": "#2e7d32",  # Green: conservative bounds
        "Violated (<0% gap)": "#c62828",       # Red: bound violated
    }
    
    band_labels = pd.Series(dtype="object")
    for idx, val in gap_pct.items():
        if pd.isna(val):
            band_labels[idx] = "No data"
        elif val < 0:
            band_labels[idx] = "Violated (<0% gap)"
        elif val < 25:
            band_labels[idx] = "Tight (0-25% gap)"
        elif val < 50:
            band_labels[idx] = "Moderate (25-50% gap)"
        else:
            band_labels[idx] = "Conservative (≥50% gap)"
    
    return band_labels, colors


def chart2() -> bool:
    csv_name = "comparison.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(2, csv_name, "python compare_results.py")
        return False

    df = sort_streams(load_csv(csv_name))
    display_df = pd.DataFrame(
        {
            "Stream": df["stream_name"],
            "Priority Class": df["priority_class"],
            "Analytical WCD (µs)": df["analytical_wcd_us"].map(lambda v: f"{v:.2f}"),
            "Simulated Max (µs)": df["max_simulated_delay_us"].map(lambda v: f"{v:.2f}"),
            "Gap (µs)": df["gap_us"].map(lambda v: f"{v:.2f}"),
            "Bound Satisfied": df["bound_satisfied"].astype(str),
        }
    )

    fig_height = max(6, 0.45 * len(display_df) + 1.8)
    fig, ax = plt.subplots(figsize=(12, fig_height), dpi=DPI)
    ax.axis("off")
    ax.set_title("Bound Satisfaction Summary — Test Case 1", fontsize=15, pad=16)

    table = ax.table(
        cellText=display_df.values,
        colLabels=display_df.columns,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)

    for col_idx in range(len(display_df.columns)):
        table[(0, col_idx)].set_facecolor("#263238")
        table[(0, col_idx)].set_text_props(color="white", weight="bold")

    for row_idx, row in df.reset_index(drop=True).iterrows():
        satisfied = str(row["bound_satisfied"]).lower() == "true"
        row_color = "#c8e6c9" if satisfied else "#ffcdd2"
        for col_idx in range(len(display_df.columns)):
            table[(row_idx + 1, col_idx)].set_facecolor(row_color)

        gap_cell = table[(row_idx + 1, 4)]
        gap_text_color = "white" if _gap_color(row["gap_us"], row["analytical_wcd_us"]) == "#2e7d32" else "black"
        gap_cell.set_facecolor(_gap_color(row["gap_us"], row["analytical_wcd_us"]))
        gap_cell.set_text_props(color=gap_text_color, weight="bold")

    save_and_show(fig, "chart2_bound_satisfaction_table.png")
    return True


def chart3() -> bool:
    csv_name = "comparison.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(3, csv_name, "python compare_results.py")
        return False

    df = enrich_deadlines(sort_streams(load_csv(csv_name)), test_case="test-case-1")
    if "sp_wcd_us" not in df.columns:
        print("Skipping Chart 3: comparison.csv missing sp_wcd_us column. Run python compare_results.py first.")
        return False

    fig, ax = plt.subplots(figsize=MIN_FIGSIZE, dpi=DPI)
    x = np.arange(len(df))
    width = 0.38

    bars_cbs = ax.bar(x - width / 2, df["analytical_wcd_us"], width, color=CBS_GREEN, label="CBS WCD")
    bars_sp = ax.bar(x + width / 2, df["sp_wcd_us"], width, color=SP_ORANGE, label="SP WCD")

    for idx, deadline in enumerate(df["deadline_us"]):
        if pd.notna(deadline):
            ax.hlines(deadline, idx - 0.5, idx + 0.5, colors=DEADLINE_GRAY, linestyles="--", linewidth=1.5)

    for idx, row in df.iterrows():
        if pd.notna(row["deadline_us"]) and row["sp_wcd_us"] > row["deadline_us"]:
            # Rule 3: Minimum 25-unit vertical gap from bar top
            label_y = row["sp_wcd_us"] + max(df["sp_wcd_us"].max() * 0.05, 25)
            ax.text(
                idx + width / 2,
                label_y,
                "STARVED",
                color=WARNING_RED,
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    add_bar_labels(ax, bars_cbs)
    add_bar_labels(ax, bars_sp)

    ax.set_xticks(x)
    ax.set_xticklabels(df["stream_name"])
    for tick, priority in zip(ax.get_xticklabels(), df["priority_class"]):
        tick.set_color(PRIORITY_COLORS.get(priority, "black"))
        tick.set_fontweight("bold")

    ax.set_ylabel("WCD (microseconds)")
    ax.set_xlabel("Streams   (label color: red = AVB-A, blue = AVB-B, grey = BE)", fontsize=11)
    ax.set_title("CBS vs Strict Priority Analytical WCD — Test Case 1")
    legend_items = [
        Patch(facecolor=CBS_GREEN, label="CBS WCD (analytical bound)"),
        Patch(facecolor=SP_ORANGE, label="SP WCD (RTA)"),
        Line2D([0], [0], color=DEADLINE_GRAY, linestyle="--", linewidth=1.5, label="Deadline"),
    ]
    ax.legend(handles=legend_items, loc="upper left")
    # Note: CBS bounds are conservative due to single-instance analysis (worst-case credit accumulation).
    # See Chart 9 for the explicit starvation prevention demonstration under high Class A load.
    fig.text(
        0.5,
        0.01,
        "Note: CBS analytical bounds are conservative. See Chart 9 for the starvation prevention demonstration.",
        ha="center",
        fontsize=10,
        style="italic",
        color="#546e7a",
    )
    save_and_show(fig, "chart3_cbs_vs_sp.png")
    return True


def chart4() -> bool:
    csv_name = "comparison.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(4, csv_name, "python compare_results.py")
        return False

    df = prepare_comparison_df(test_case="test-case-1")
    df["gap_band"], band_colors = build_gap_bands(df["gap_pct"])

    fig, ax = plt.subplots(figsize=(14, 8), dpi=DPI)
    x = np.arange(len(df))
    width = 0.36
    sim_colors = df["gap_band"].map(band_colors)

    bars_analytical = ax.bar(
        x - width / 2,
        df["analytical_wcd_us"],
        width,
        color=ANALYTICAL_RED,
        alpha=0.9,
        label="Analytical WCD",
    )
    bars_sim = ax.bar(
        x + width / 2,
        df["max_simulated_delay_us"],
        width,
        color=sim_colors,
        edgecolor="black",
        linewidth=0.6,
        label="Simulated Max Delay",
    )

    for idx, deadline in enumerate(df["deadline_us"]):
        if pd.notna(deadline):
            ax.hlines(
                deadline,
                idx - 0.5,
                idx + 0.5,
                colors=DEADLINE_GRAY,
                linestyles="--",
                linewidth=1.8,
                alpha=0.9,
                zorder=10,  # Ensure deadline lines appear on top
                label="Deadline" if idx == 0 else "",  # Only add label once
            )
            # Add deadline value label to the right of the line
            ax.text(
                idx + 0.52,
                deadline,
                f"{deadline:.0f}",
                ha="left",
                va="center",
                fontsize=7.5,
                color=DEADLINE_GRAY,
                style="italic",
            )

    max_height = np.nanmax(df[["analytical_wcd_us", "max_simulated_delay_us", "deadline_us"]].to_numpy(dtype=float))
    annotation_offset = max(max_height * 0.04, 15.0)  # Increased offset for better spacing

    for idx, row in df.iterrows():
        analytical = row["analytical_wcd_us"]
        simulated = row["max_simulated_delay_us"]
        if pd.isna(analytical) or pd.isna(simulated):
            continue

        # Show only gap %, as tightness % is redundant (gap + tightness = 100%)
        if pd.notna(row["gap_pct"]):
            gap_label = f"Gap: {row['gap_pct']:.1f}%"
        else:
            gap_label = ""

        # Position gap label much higher, above where bar values will be
        label_y = max(analytical, simulated) + annotation_offset * 1.5
        ax.text(
            idx,
            label_y,
            gap_label,
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
            color="#263238",
        )

        if simulated > analytical:
            ax.annotate(
                "Violation",
                xy=(idx + width / 2, simulated),
                xytext=(0, 14),
                textcoords="offset points",
                ha="center",
                color=WARNING_RED,
                fontsize=9,
                fontweight="bold",
                arrowprops={"arrowstyle": "->", "color": WARNING_RED, "lw": 1},
            )

    # Add bar labels: analytical above, simulated inside bars
    add_bar_labels(ax, bars_analytical, position="outside")
    add_bar_labels(ax, bars_sim, position="inside")

    ax.set_xticks(x)
    ax.set_xticklabels(df["stream_name"])
    for tick, priority in zip(ax.get_xticklabels(), df["priority_class"]):
        tick.set_color(PRIORITY_COLORS.get(priority, "black"))
        tick.set_fontweight("bold")

    avg_gap = df["gap_pct"].mean()
    min_gap = df["gap_pct"].min()
    max_gap = df["gap_pct"].max()
    satisfied = int((df["bound_satisfied"].astype(str).str.lower() == "true").sum())
    violations = int((df["bound_satisfied"].astype(str).str.lower() == "false").sum())
    loosest_idx = df["gap_pct"].idxmax()
    tightest_idx = df["gap_pct"].idxmin()
    summary_lines = [
        f"Streams: {len(df)}",
        f"Avg gap: {avg_gap:.1f}%",
        f"Gap range: {min_gap:.1f}% to {max_gap:.1f}%",
        f"Bounds satisfied: {satisfied}",
        f"Violations: {violations}",
        f"Tightest: {df.loc[tightest_idx, 'stream_name']} ({df.loc[tightest_idx, 'gap_pct']:.1f}% gap)",
        f"Loosest: {df.loc[loosest_idx, 'stream_name']} ({df.loc[loosest_idx, 'gap_pct']:.1f}% gap)",
    ]
    # Position stats box outside plot area to avoid overlapping bars and labels
    ax.text(
        1.02,
        0.98,
        "\n".join(summary_lines),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9.5,
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "#fafafa", "edgecolor": "#b0bec5", "alpha": 0.95},
    )

    ax.set_ylabel("Delay (microseconds)")
    ax.set_xlabel("Streams   (label color: red = AVB-A, blue = AVB-B, grey = BE)", fontsize=11)
    ax.set_title("Analytical WCD vs Simulated Max Delay — Bound Tightness Analysis")

    legend_items = [
        Patch(facecolor=ANALYTICAL_RED, label="Analytical WCD"),
        Patch(facecolor="#d9d9d9", edgecolor="black", label="Simulated Max Delay"),
    ]
    legend_items.extend(Patch(facecolor=color, label=label) for label, color in band_colors.items())
    if violations > 0:
        legend_items.append(Patch(facecolor=WARNING_RED, label="Bound Violated in Simulation"))
    legend_items.append(Line2D([0], [0], color=DEADLINE_GRAY, linestyle="--", linewidth=1.5, label="Deadline"))

    ax.legend(handles=legend_items, loc="upper left")
    save_and_show(fig, "chart4_analytical_vs_simulated_gap_tightness.png")
    return True


def chart5() -> bool:
    csv_name = "credit_log.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(5, csv_name, "the simulator with credit logging enabled")
        return False

    df = load_csv(csv_name)
    required_columns = {"time_us", "link_id", "queue_class", "credit"}
    if not required_columns.issubset(df.columns):
        print("Skipping Chart 5: credit_log.csv is missing required columns time_us, link_id, queue_class, credit.")
        return False

    df["queue_class"] = df["queue_class"].map(normalize_priority)
    busiest_link = df["link_id"].value_counts().idxmax()
    busy_df = df[df["link_id"] == busiest_link].copy()
    plot_df = busy_df[busy_df["queue_class"].isin(["AVB-A", "AVB-B"])]
    if plot_df.empty:
        print("Skipping Chart 5: credit_log.csv has no AVB-A or AVB-B entries on the busiest link.")
        return False

    fig, ax = plt.subplots(figsize=MIN_FIGSIZE, dpi=DPI)
    line_colors = {"AVB-A": ANALYTICAL_RED, "AVB-B": SIM_BLUE}

    for queue_class in ["AVB-A", "AVB-B"]:
        series = plot_df[plot_df["queue_class"] == queue_class].sort_values("time_us")
        if series.empty:
            continue
        ax.plot(series["time_us"], series["credit"], label=f"{queue_class} credit", color=line_colors[queue_class], linewidth=2)
        ax.fill_between(
            series["time_us"],
            series["credit"],
            0,
            where=series["credit"] < 0,
            color="#ef9a9a",
            alpha=0.35,
        )

    if "event_type" in busy_df.columns:
        event_subset = busy_df[busy_df["event_type"].isin(["tx_start", "tx_end"])]
        for _, row in event_subset.iterrows():
            ax.axvline(
                row["time_us"],
                color=DEADLINE_GRAY,
                linestyle="--",
                linewidth=0.8,
                alpha=0.6,
            )

    ax.set_xlabel("Simulated time (microseconds)")
    ax.set_ylabel("Credit value")
    ax.set_title(f"CBS Credit Evolution — AVB-A and AVB-B on Link {busiest_link}")
    ax.legend(loc="best")
    save_and_show(fig, "chart5_credit_evolution.png")
    return True


def chart6() -> bool:
    csv_name = "per_hop_wcrt.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(6, csv_name, "the analytical tool with per-hop result export enabled")
        return False

    df = load_csv(csv_name)
    required = {"stream_id", "hop_index", "link_id", "wcrt_us", "propagation_delay_us"}
    if not required.issubset(df.columns):
        print("Skipping Chart 6: per_hop_wcrt.csv is missing one or more required columns.")
        return False

    metadata = load_test_case_stream_metadata("test-case-3")
    stream_names = {stream_id: metadata.get(int(stream_id), {}).get("name", f"Stream{stream_id}") for stream_id in df["stream_id"].unique()}
    max_hop = int(df["hop_index"].max()) + 1
    hop_palette = sns.color_palette("Blues", n_colors=max(max_hop + 2, 4))[2:]

    fig, ax = plt.subplots(figsize=MIN_FIGSIZE, dpi=DPI)
    bottom = np.zeros(df["stream_id"].nunique())
    stream_ids = sorted(df["stream_id"].unique())
    x = np.arange(len(stream_ids))

    for hop_index in sorted(df["hop_index"].unique()):
        hop_df = df[df["hop_index"] == hop_index].set_index("stream_id").reindex(stream_ids)
        wcrt_vals = hop_df["wcrt_us"].fillna(0).to_numpy()
        prop_vals = hop_df["propagation_delay_us"].fillna(0).to_numpy()

        ax.bar(
            x,
            wcrt_vals,
            bottom=bottom,
            color=hop_palette[int(hop_index) % len(hop_palette)],
            label=f"Hop {int(hop_index)} WCRT" if hop_index == sorted(df["hop_index"].unique())[0] else None,
        )
        bottom = bottom + wcrt_vals

        ax.bar(
            x,
            prop_vals,
            bottom=bottom,
            color="#cfd8dc",
            label="Propagation Delay" if hop_index == sorted(df["hop_index"].unique())[0] else None,
        )
        bottom = bottom + prop_vals

    for idx, stream_id in enumerate(stream_ids):
        deadline = metadata.get(int(stream_id), {}).get("deadline_us", np.nan)
        if pd.notna(deadline):
            ax.hlines(deadline, idx - 0.4, idx + 0.4, colors=DEADLINE_GRAY, linestyles="--", linewidth=1.5)

    ax.set_xticks(x)
    ax.set_xticklabels([stream_names[sid] for sid in stream_ids])
    ax.set_xlabel("Streams")
    ax.set_ylabel("Cumulative delay (microseconds)")
    ax.set_title("Per-Hop WCD Breakdown — Test Case 3 (3-Switch Line Topology)")
    ax.legend(
        handles=[
            Patch(facecolor=hop_palette[0], label="Per-hop WCRT"),
            Patch(facecolor="#cfd8dc", label="Propagation Delay"),
            Line2D([0], [0], color=DEADLINE_GRAY, linestyle="--", linewidth=1.5, label="Deadline"),
        ],
        loc="upper left",
    )
    save_and_show(fig, "chart6_per_hop_breakdown.png")
    return True


def chart7() -> bool:
    csv_name = "multi_testcase_summary.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(7, csv_name, "the analytical tool across all three test cases")
        return False

    df = load_csv(csv_name)
    required = {"test_case", "stream_id", "priority_class", "link_utilization_percent", "analytical_wcd_us"}
    if not required.issubset(df.columns):
        print("Skipping Chart 7: multi_testcase_summary.csv is missing one or more required columns.")
        return False

    df["priority_class"] = df["priority_class"].map(normalize_priority)
    fig, ax = plt.subplots(figsize=MIN_FIGSIZE, dpi=DPI)

    for priority in ["AVB-A", "AVB-B", "BE"]:
        subset = df[df["priority_class"] == priority]
        if subset.empty:
            continue
        sns.scatterplot(
            data=subset,
            x="link_utilization_percent",
            y="analytical_wcd_us",
            color=PRIORITY_COLORS[priority],
            s=80,
            ax=ax,
            label=priority,
        )
        if len(subset) >= 2:
            sns.regplot(
                data=subset,
                x="link_utilization_percent",
                y="analytical_wcd_us",
                scatter=False,
                ci=None,
                color=PRIORITY_COLORS[priority],
                line_kws={"linewidth": 2},
                ax=ax,
            )

    ax.set_xlabel("Link utilization (%)")
    ax.set_ylabel("Analytical WCD (microseconds)")
    ax.set_title("Link Utilization vs Analytical WCD — All Test Cases")
    save_and_show(fig, "chart7_utilization_vs_wcd.png")
    return True


def chart8() -> bool:
    csv_name = "fixedpoint_comparison.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(8, csv_name, "the analytical tool with and without --fixed-point")
        return False

    df = sort_streams(load_csv(csv_name))
    required = {"stream_id", "priority_class", "single_instance_wcd_us", "fixed_point_wcd_us"}
    if not required.issubset(df.columns):
        print("Skipping Chart 8: fixedpoint_comparison.csv is missing one or more required columns.")
        return False

    df["stream_name"] = df.get("stream_name", df["stream_id"].map(lambda sid: f"Stream{sid}"))
    fig, ax = plt.subplots(figsize=(13, 7), dpi=DPI)
    x = np.arange(len(df))
    width = 0.38

    bars_single = ax.bar(x - width / 2, df["single_instance_wcd_us"], width, color=SINGLE_YELLOW, label="Single-instance")
    bars_fixed = ax.bar(x + width / 2, df["fixed_point_wcd_us"], width, color=FIXED_PURPLE, label="Fixed-point")

    add_bar_labels(ax, bars_single)
    add_bar_labels(ax, bars_fixed)

    for idx, row in df.iterrows():
        single = row["single_instance_wcd_us"]
        fixed = row["fixed_point_wcd_us"]
        if pd.isna(single) or single == 0 or pd.isna(fixed):
            continue
        improvement_pct = ((fixed - single) / single) * 100.0
        descriptor = "tighter" if improvement_pct <= 0 else "looser"
        
        # Place label above the taller bar with adaptive staggering to avoid overlaps
        max_height = max(single, fixed)
        chart_max = df[["single_instance_wcd_us", "fixed_point_wcd_us"]].max().max()
        
        # Stagger labels: alternate vertical position for adjacent bars with same height
        is_staggered = idx % 2 == 1
        base_gap = chart_max * 0.065
        stagger_offset = chart_max * 0.025 if is_staggered else 0
        
        label_y = max_height + base_gap + stagger_offset
        
        ax.text(
            idx,
            label_y,
            f"{abs(improvement_pct):.0f}% {descriptor}",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="black",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(df["stream_name"])
    for tick, priority in zip(ax.get_xticklabels(), df["priority_class"]):
        tick.set_color(PRIORITY_COLORS.get(priority, "black"))
        tick.set_fontweight("bold")

    ax.set_xlabel("Streams\n(label color: red = AVB-A, blue = AVB-B, grey = BE)", fontsize=11, labelpad=15)
    ax.set_ylabel("WCD (microseconds)")
    ax.set_title("Single-Instance vs Fixed-Point WCRT — Test Case 1", fontsize=14, pad=20)
    fig.text(0.5, 0.025, "Fixed-point iteration produces tighter or equal bounds", ha="center", fontsize=10, style="italic")
    ax.legend(loc="upper left", fontsize=11)
    save_and_show(fig, "chart8_fixedpoint_vs_single.png")
    return True


def chart9() -> bool:
    """
    Starvation prevention demonstration (Test Case 4).

    Test Case 4 uses two Class A streams with combined link utilisation of 95%.
    Under SP, Class B and Best-Effort streams miss their deadlines by more than
    2×.  Under CBS (idle_slope = 0.5 per class), the credit mechanism caps Class A
    interference and keeps all streams schedulable.

    Reads: results/starvation_comparison.csv
    """
    csv_name = "starvation_comparison.csv"
    csv_path = RESULTS_DIR / csv_name
    if not csv_path.exists():
        warn_skip(9, csv_name, "python results/generate_starvation_demo.py")
        return False

    df = load_csv(csv_name)
    required = {"stream_name", "priority_class", "cbs_wcd_us", "sp_wcd_us", "deadline_us"}
    if not required.issubset(df.columns):
        print("Skipping Chart 9: starvation_comparison.csv is missing required columns.")
        return False

    df["priority_class"] = df["priority_class"].map(normalize_priority)
    for col in ("cbs_wcd_us", "sp_wcd_us", "deadline_us"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Cap very large SP WCDs for visual clarity; annotate with actual value
    MAX_DISPLAY = df["deadline_us"].max() * 3.5
    df["sp_display"] = df["sp_wcd_us"].clip(upper=MAX_DISPLAY)

    fig, ax = plt.subplots(figsize=(11, 7), dpi=DPI)
    x = np.arange(len(df))
    width = 0.38

    bars_cbs = ax.bar(x - width / 2, df["cbs_wcd_us"], width, color=CBS_GREEN, label="CBS WCD (analytical)")
    bars_sp = ax.bar(x + width / 2, df["sp_display"], width, color=SP_ORANGE, label="SP WCD (RTA)", alpha=0.85)

    # Deadline lines
    for idx, deadline in enumerate(df["deadline_us"]):
        if pd.notna(deadline):
            ax.hlines(
                deadline,
                idx - 0.52,
                idx + 0.52,
                colors=DEADLINE_GRAY,
                linestyles="--",
                linewidth=2.0,
                zorder=5,
            )
            ax.text(idx + 0.55, deadline, f"DL={deadline:.0f}", va="center", fontsize=8, color=DEADLINE_GRAY)

    # Annotations: actual SP value + "STARVED" badge for deadline violations
    for idx, row in df.iterrows():
        cbs_wcd = row["cbs_wcd_us"]
        sp_wcd = row["sp_wcd_us"]
        deadline = row["deadline_us"]
        sp_display = row["sp_display"]

        # CBS value label
        if pd.notna(cbs_wcd):
            ax.text(
                idx - width / 2,
                cbs_wcd + MAX_DISPLAY * 0.025,
                f"{cbs_wcd:.0f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color=CBS_GREEN,
                fontweight="bold",
            )

        # SP value label (always show actual value even if clipped)
        if pd.notna(sp_wcd) and pd.notna(sp_display):
            label_y = sp_display + MAX_DISPLAY * 0.025
            ax.text(
                idx + width / 2,
                label_y,
                f"{sp_wcd:.0f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color=SP_ORANGE,
                fontweight="bold",
            )

        # "STARVED" badge when SP exceeds deadline
        if pd.notna(deadline) and pd.notna(sp_wcd) and sp_wcd > deadline:
            badge_y = sp_display + MAX_DISPLAY * 0.14
            ax.text(
                idx + width / 2,
                badge_y,
                "STARVED\nunder SP",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color="white",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=WARNING_RED,
                    edgecolor=WARNING_RED,
                    alpha=0.92,
                ),
            )

        # "CBS SAVES" badge where CBS is schedulable but SP is not
        if (
            pd.notna(deadline)
            and pd.notna(sp_wcd)
            and pd.notna(cbs_wcd)
            and sp_wcd > deadline
            and cbs_wcd <= deadline
        ):
            ax.text(
                idx - width / 2,
                cbs_wcd + MAX_DISPLAY * 0.14,
                "CBS OK",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
                color="white",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=CBS_GREEN,
                    edgecolor=CBS_GREEN,
                    alpha=0.92,
                ),
            )

    ax.set_xticks(x)
    ax.set_xticklabels(df["stream_name"], fontsize=11)
    for tick, priority in zip(ax.get_xticklabels(), df["priority_class"]):
        tick.set_color(PRIORITY_COLORS.get(priority, "black"))
        tick.set_fontweight("bold")

    ax.set_ylabel("Worst-Case Delay (microseconds)", fontsize=12)
    ax.set_xlabel(
        "Streams   (label color: red = AVB-A, blue = AVB-B, grey = BE)\n"
        "Class A combined utilisation = 95 %  |  idle_slope_A = idle_slope_B = 0.5",
        fontsize=10,
    )
    ax.set_title(
        "CBS Starvation Prevention Demonstration — Test Case 4\n"
        "SP starves Class B and Best-Effort; CBS keeps all streams schedulable",
        fontsize=13,
    )
    ax.set_ylim(bottom=0, top=MAX_DISPLAY * 1.45)

    legend_items = [
        Patch(facecolor=CBS_GREEN, label="CBS WCD  (idle-slope bounded)"),
        Patch(facecolor=SP_ORANGE, label="SP WCD  (RTA, no credit bound)"),
        Line2D([0], [0], color=DEADLINE_GRAY, linestyle="--", linewidth=2.0, label="Stream deadline"),
        Patch(facecolor=WARNING_RED, label="SP deadline violation (starvation)"),
        Patch(facecolor=CBS_GREEN, label="CBS schedulable despite high Class A load"),
    ]
    ax.legend(handles=legend_items, loc="upper left", fontsize=9.5)

    fig.text(
        0.5,
        0.01,
        "CBS idle-slope mechanism caps Class A credit accumulation → finite, bounded delay for all priority classes",
        ha="center",
        fontsize=10,
        style="italic",
        color="#37474f",
    )
    save_and_show(fig, "chart9_starvation_prevention.png")
    return True


def main() -> None:
    configure_style()
    chart_functions: List[Callable[[], bool]] = [
        chart1, chart2, chart3, chart4, chart5, chart6, chart7, chart8, chart9,
    ]
    generated = sum(1 for chart_fn in chart_functions if chart_fn())
    print(f"Generated {generated}/9 charts successfully. Saved to results/plots/")


if __name__ == "__main__":
    main()
