from __future__ import annotations

import pandas as pd

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class GanttWidget(FigureCanvas):
    """Matplotlib Gantt chart embedded into PySide6."""

    def __init__(self):
        self.figure = Figure(figsize=(11, 5), tight_layout=True)
        super().__init__(self.figure)

    def plot_schedule(self, schedule: pd.DataFrame | None, title: str = "Schedule") -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if schedule is None or schedule.empty:
            ax.set_title("No schedule solved yet")
            ax.set_xlabel("Time")
            self.draw()
            return

        data = schedule.copy()
        data["start_time"] = pd.to_datetime(data["start_time"])
        data["end_time"] = pd.to_datetime(data["end_time"])
        stages = list(data.sort_values("stage_index")["machine_id"].drop_duplicates())
        y_map = {m: i for i, m in enumerate(stages)}
        origin = data["start_time"].min()

        order_ids = list(data["order_id"].drop_duplicates())
        color_map = {oid: f"C{i % 10}" for i, oid in enumerate(order_ids)}

        for _, row in data.iterrows():
            start_h = (row["start_time"] - origin).total_seconds() / 3600.0
            dur_h = (row["end_time"] - row["start_time"]).total_seconds() / 3600.0
            y = y_map[str(row["machine_id"])]
            edge = "black" if str(row.get("demand_type", "")).upper() == "PRIORITY_CUSTOMER_ORDER" else None
            linewidth = 1.8 if edge else 0.6
            ax.barh(
                y,
                dur_h,
                left=start_h,
                height=0.65,
                color=color_map[str(row["order_id"])],
                edgecolor=edge,
                linewidth=linewidth,
                alpha=0.82,
            )
            if dur_h > 0.35:
                ax.text(start_h + dur_h / 2, y, str(row["order_id"]), va="center", ha="center", fontsize=8)

        # Draw due-date markers per order near the top axis.
        due_rows = data.groupby("order_id")["due_date"].first().reset_index()
        max_y = len(stages) - 1
        for _, row in due_rows.iterrows():
            due = pd.to_datetime(row["due_date"])
            if due >= origin:
                x = (due - origin).total_seconds() / 3600.0
                ax.axvline(x, linestyle="--", linewidth=0.8, alpha=0.35)

        ax.set_yticks(range(len(stages)))
        ax.set_yticklabels(stages)
        ax.invert_yaxis()
        ax.set_xlabel(f"Hours from {origin:%Y-%m-%d %H:%M}")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.25)
        self.draw()
