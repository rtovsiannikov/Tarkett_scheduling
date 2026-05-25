from __future__ import annotations

from typing import Iterable

import pandas as pd

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates


# A fixed hex palette is used both by the Gantt chart and by the legend window.
# This avoids the old bug where Matplotlib displayed bars with C0/C1/... colors
# but the separate legend window did not know the actual colors.
DEFAULT_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]


def ordered_unique(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = "—" if pd.isna(value) else str(value)
        if text not in seen:
            result.append(text)
            seen.add(text)
    return result


def make_color_map(values: Iterable[object]) -> dict[str, str]:
    uniques = ordered_unique(values)
    return {value: DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)] for i, value in enumerate(uniques)}


class GanttWidget(FigureCanvas):
    """Matplotlib Gantt chart embedded into PySide6.

    The x-axis uses real datetimes, and the chart exposes display switches so
    the desktop UI can choose exactly what to show. Colors are deterministic and
    can be reproduced in the separate legend window.
    """

    def __init__(self):
        self.figure = Figure(figsize=(14, 7), tight_layout=True)
        super().__init__(self.figure)
        self.setMinimumSize(1120, 620)
        self.last_color_by = "order_id"
        self.last_color_map: dict[str, str] = {}

    def plot_schedule(
        self,
        schedule: pd.DataFrame | None,
        title: str = "Schedule",
        *,
        color_by: str = "order_id",
        show_labels: bool = True,
        show_due_dates: bool = True,
        show_setup: bool = True,
        show_downtime: bool = True,
        downtime_events: pd.DataFrame | None = None,
        visible_demand_types: Iterable[str] | None = None,
        machine_filter: str = "",
    ) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        self.last_color_by = color_by
        self.last_color_map = {}
        if schedule is None or schedule.empty:
            ax.set_title("No schedule solved yet")
            ax.set_xlabel("Date / time")
            self.draw()
            return

        data = schedule.copy()
        data["start_time"] = pd.to_datetime(data["start_time"])
        data["end_time"] = pd.to_datetime(data["end_time"])
        data["due_date"] = pd.to_datetime(data["due_date"], errors="coerce")
        if visible_demand_types:
            visible = {str(x).upper() for x in visible_demand_types}
            data = data[data["demand_type"].astype(str).str.upper().isin(visible)]
        if machine_filter.strip():
            tokens = [x.strip().upper() for x in machine_filter.replace(";", ",").split(",") if x.strip()]
            if tokens:
                mask = data["machine_id"].astype(str).str.upper().apply(lambda v: any(t in v for t in tokens))
                data = data[mask]
        if data.empty:
            ax.set_title("No operations match current graph filters")
            ax.set_xlabel("Date / time")
            self.draw()
            return

        stage_order = (
            data[["stage_index", "machine_id"]]
            .drop_duplicates()
            .sort_values("stage_index")["machine_id"]
            .astype(str)
            .tolist()
        )
        y_map = {m: i for i, m in enumerate(stage_order)}

        color_column = color_by if color_by in data.columns else "order_id"
        color_values = data[color_column].astype(str).fillna("—").tolist()
        color_map = make_color_map(color_values)
        self.last_color_map = color_map.copy()
        hatch_map = {
            "PRIORITY_CUSTOMER_ORDER": "//",
            "CUSTOMER_ORDER": "",
            "STOCK_ORDER": "..",
        }

        min_start = data["start_time"].min()
        max_end = data["end_time"].max()
        for _, row in data.sort_values(["stage_index", "start_time", "order_id", "batch_index"]).iterrows():
            start_num = mdates.date2num(row["start_time"])
            end_num = mdates.date2num(row["end_time"])
            dur_days = max(0.0002, end_num - start_num)
            setup_days = min(dur_days, float(row.get("setup_minutes", 0) or 0) / (60.0 * 24.0))
            y = y_map[str(row["machine_id"])]
            dtype = str(row.get("demand_type", "")).upper()
            edge = "black" if dtype == "PRIORITY_CUSTOMER_ORDER" else "#334155"
            linewidth = 1.8 if dtype == "PRIORITY_CUSTOMER_ORDER" else 0.7
            key = str(row.get(color_column, row.get("order_id", "—")))
            color = color_map.get(key, DEFAULT_PALETTE[0])
            ax.barh(
                y,
                dur_days,
                left=start_num,
                height=0.64,
                color=color,
                edgecolor=edge,
                linewidth=linewidth,
                alpha=0.84,
                hatch=hatch_map.get(dtype, ""),
            )
            if show_setup and setup_days > 0.0008:
                ax.barh(
                    y,
                    setup_days,
                    left=start_num,
                    height=0.64,
                    color="white",
                    edgecolor=edge,
                    linewidth=0.4,
                    alpha=0.58,
                )
            duration_hours = (row["end_time"] - row["start_time"]).total_seconds() / 3600.0
            if show_labels and duration_hours > 0.28:
                label = f"{row['order_id']}\nB{int(row.get('batch_index', 1))}/{int(row.get('batches_in_order', 1))}"
                ax.text(start_num + dur_days / 2, y, label, va="center", ha="center", fontsize=7, color="#0f172a")

        if show_due_dates and "due_date" in data.columns:
            y_top = -0.70
            due_rows = data.groupby("order_id").agg({"due_date": "first", "demand_type": "first"}).reset_index()
            for _, row in due_rows.iterrows():
                due = pd.to_datetime(row["due_date"], errors="coerce")
                if pd.isna(due):
                    continue
                x = mdates.date2num(due)
                ax.axvline(x, linestyle="--", linewidth=0.9, alpha=0.34)
                ax.text(x, y_top, str(row["order_id"]), rotation=90, fontsize=7, ha="right", va="bottom", alpha=0.62)

        if show_downtime and downtime_events is not None and not downtime_events.empty:
            down = downtime_events.copy()
            if "event_start" in down.columns:
                down["event_start"] = pd.to_datetime(down["event_start"], errors="coerce")
            for _, row in down.dropna(subset=["event_start"]).iterrows():
                machine = str(row.get("machine_id", ""))
                if machine not in y_map:
                    continue
                start = row["event_start"]
                raw_duration = row.get("actual_duration_minutes", row.get("estimated_duration_minutes", 0))
                duration = float(0 if pd.isna(raw_duration) else raw_duration)
                if duration <= 0:
                    continue
                left = mdates.date2num(start)
                width = duration / (60.0 * 24.0)
                y = y_map[machine]
                ax.barh(y, width, left=left, height=0.82, color="#ef4444", alpha=0.24, edgecolor="#991b1b", linewidth=1.0)
                ax.text(left + width / 2, y + 0.46, f"down {duration:g}m", ha="center", va="bottom", fontsize=7, color="#991b1b")

        ax.set_yticks(range(len(stage_order)))
        ax.set_yticklabels(stage_order)
        ax.invert_yaxis()
        ax.set_xlabel("Date / time")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.25)
        locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
        self.figure.autofmt_xdate(rotation=0)
        ax.set_xlim(mdates.date2num(min_start) - 0.02, mdates.date2num(max_end) + 0.06)
        ax.text(
            0.01,
            0.01,
            "Labels: order + batch. Dashed vertical lines: deadlines. Red overlays: editable downtime. White segment: setup.",
            transform=ax.transAxes,
            fontsize=8,
            color="#475569",
            va="bottom",
        )
        self.draw()
