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

    This version also mimics the old MVP behavior more closely:
    - hovering over an operation displays an order/batch card;
    - operations moved relative to a baseline/previous plan receive a red outline
      and a small marker so rescheduling changes are visually obvious.
    """

    def __init__(self):
        self.figure = Figure(figsize=(14, 7), tight_layout=True)
        super().__init__(self.figure)
        self.setMinimumSize(1120, 620)
        self.last_color_by = "order_id"
        self.last_color_map: dict[str, str] = {}
        self._bar_records: list[tuple[object, str]] = []
        self._hover_annotation = None
        self.mpl_connect("motion_notify_event", self._on_motion)

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
        previous_schedule: pd.DataFrame | None = None,
        highlight_changes: bool = True,
    ) -> None:
        self.figure.clear()
        self._bar_records = []
        self._hover_annotation = None
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

        previous = self._previous_lookup(previous_schedule)

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
            op_id = str(row.get("operation_id", ""))
            changed = highlight_changes and self._is_changed(row, previous)

            if changed:
                edge = "#dc2626"
                linewidth = 2.3
            elif dtype == "PRIORITY_CUSTOMER_ORDER":
                edge = "black"
                linewidth = 1.8
            else:
                edge = "#334155"
                linewidth = 0.7

            key = str(row.get(color_column, row.get("order_id", "—")))
            color = color_map.get(key, DEFAULT_PALETTE[0])
            bar = ax.barh(
                y,
                dur_days,
                left=start_num,
                height=0.64,
                color=color,
                edgecolor=edge,
                linewidth=linewidth,
                alpha=0.84,
                hatch=hatch_map.get(dtype, ""),
            )[0]
            self._bar_records.append((bar, self._tooltip_text(row, changed=changed, previous=previous.get(op_id))))

            if changed:
                ax.scatter([end_num], [y], marker="s", s=18, color="#dc2626", zorder=5)

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
            "Hover: order card. Red outline/square: moved vs baseline. Dashed lines: deadlines. Red overlays: downtime. White segment: setup.",
            transform=ax.transAxes,
            fontsize=8,
            color="#475569",
            va="bottom",
        )

        self._hover_annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(14, 18),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.45", fc="white", ec="#334155", alpha=0.96),
            arrowprops=dict(arrowstyle="->", color="#334155"),
            fontsize=8,
            color="#0f172a",
        )
        self._hover_annotation.set_visible(False)
        self.draw()

    @staticmethod
    def _previous_lookup(previous_schedule: pd.DataFrame | None) -> dict[str, dict[str, object]]:
        if previous_schedule is None or previous_schedule.empty or "operation_id" not in previous_schedule.columns:
            return {}
        prev = previous_schedule.copy()
        prev["operation_id"] = prev["operation_id"].astype(str)
        prev["start_time"] = pd.to_datetime(prev["start_time"], errors="coerce")
        prev["end_time"] = pd.to_datetime(prev["end_time"], errors="coerce")
        return prev.drop_duplicates("operation_id", keep="last").set_index("operation_id").to_dict("index")

    @staticmethod
    def _is_changed(row: pd.Series, previous: dict[str, dict[str, object]]) -> bool:
        op_id = str(row.get("operation_id", ""))
        old = previous.get(op_id)
        if not old:
            return False
        old_machine = str(old.get("machine_id", ""))
        if old_machine and old_machine != str(row.get("machine_id", "")):
            return True
        old_start = pd.to_datetime(old.get("start_time"), errors="coerce")
        old_end = pd.to_datetime(old.get("end_time"), errors="coerce")
        if pd.isna(old_start) or pd.isna(old_end):
            return False
        start = pd.to_datetime(row.get("start_time"), errors="coerce")
        end = pd.to_datetime(row.get("end_time"), errors="coerce")
        if pd.isna(start) or pd.isna(end):
            return False
        return abs((start - old_start).total_seconds()) > 60 or abs((end - old_end).total_seconds()) > 60

    @staticmethod
    def _fmt_dt(value: object) -> str:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return "—"
        return ts.strftime("%Y-%m-%d %H:%M")

    def _tooltip_text(self, row: pd.Series, *, changed: bool, previous: dict[str, object] | None) -> str:
        duration = row.get("duration_minutes", "—")
        setup = row.get("setup_minutes", "—")
        lines = [
            f"Order: {row.get('order_id', '—')}",
            f"Batch: {row.get('batch_id', '—')} ({row.get('batch_index', '—')}/{row.get('batches_in_order', '—')})",
            f"Product: {row.get('product_id', '—')} / {row.get('product_family', '—')}",
            f"Demand: {row.get('demand_type', '—')} | priority {row.get('priority', '—')}",
            f"Machine: {row.get('machine_id', '—')} | stage {row.get('stage_name', '—')}",
            f"Qty: {row.get('quantity', '—')} | input {row.get('input_quantity', '—')}",
            f"Start: {self._fmt_dt(row.get('start_time'))}",
            f"End:   {self._fmt_dt(row.get('end_time'))}",
            f"Due:   {self._fmt_dt(row.get('due_date'))}",
            f"Duration: {duration} min | setup {setup} min",
        ]
        if changed and previous:
            lines.append("Changed vs baseline: YES")
            lines.append(f"Previous start: {self._fmt_dt(previous.get('start_time'))}")
            lines.append(f"Previous end:   {self._fmt_dt(previous.get('end_time'))}")
        return "\n".join(lines)

    def _on_motion(self, event) -> None:
        if self._hover_annotation is None:
            return
        visible = self._hover_annotation.get_visible()
        if event.inaxes is None:
            if visible:
                self._hover_annotation.set_visible(False)
                self.draw_idle()
            return
        for patch, text in reversed(self._bar_records):
            contains, _ = patch.contains(event)
            if contains:
                self._hover_annotation.xy = (event.xdata, event.ydata)
                self._hover_annotation.set_text(text)
                self._hover_annotation.set_visible(True)
                self.draw_idle()
                return
        if visible:
            self._hover_annotation.set_visible(False)
            self.draw_idle()
