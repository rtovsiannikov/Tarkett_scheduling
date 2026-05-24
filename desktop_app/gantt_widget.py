from __future__ import annotations

import pandas as pd

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class GanttWidget(FigureCanvas):
    """Matplotlib Gantt chart embedded into PySide6.

    The chart is intentionally closer to the original MVP: readable lanes, order
    colors, batch labels, due-date markers and a visual setup segment inside each
    operation bar.
    """

    def __init__(self):
        self.figure = Figure(figsize=(14, 7), tight_layout=True)
        super().__init__(self.figure)
        self.setMinimumSize(1050, 560)

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
        data["due_date"] = pd.to_datetime(data["due_date"])
        stage_order = (
            data[["stage_index", "machine_id"]]
            .drop_duplicates()
            .sort_values("stage_index")["machine_id"]
            .astype(str)
            .tolist()
        )
        y_map = {m: i for i, m in enumerate(stage_order)}
        origin = data["start_time"].min()
        order_ids = list(data["order_id"].astype(str).drop_duplicates())
        color_map = {oid: f"C{i % 10}" for i, oid in enumerate(order_ids)}

        hatch_map = {
            "PRIORITY_CUSTOMER_ORDER": "//",
            "CUSTOMER_ORDER": "",
            "STOCK_ORDER": "..",
        }

        for _, row in data.sort_values(["stage_index", "start_time", "order_id", "batch_index"]).iterrows():
            start_h = (row["start_time"] - origin).total_seconds() / 3600.0
            dur_h = (row["end_time"] - row["start_time"]).total_seconds() / 3600.0
            setup_h = min(dur_h, float(row.get("setup_minutes", 0) or 0) / 60.0)
            y = y_map[str(row["machine_id"])]
            dtype = str(row.get("demand_type", "")).upper()
            edge = "black" if dtype == "PRIORITY_CUSTOMER_ORDER" else "#334155"
            linewidth = 1.8 if dtype == "PRIORITY_CUSTOMER_ORDER" else 0.7
            color = color_map[str(row["order_id"])]
            ax.barh(
                y,
                dur_h,
                left=start_h,
                height=0.64,
                color=color,
                edgecolor=edge,
                linewidth=linewidth,
                alpha=0.82,
                hatch=hatch_map.get(dtype, ""),
            )
            if setup_h > 0.03:
                ax.barh(
                    y,
                    setup_h,
                    left=start_h,
                    height=0.64,
                    color="white",
                    edgecolor=edge,
                    linewidth=0.4,
                    alpha=0.45,
                )
            if dur_h > 0.28:
                label = f"{row['order_id']}\nB{int(row.get('batch_index', 1))}/{int(row.get('batches_in_order', 1))}"
                ax.text(start_h + dur_h / 2, y, label, va="center", ha="center", fontsize=7, color="#0f172a")

        # Draw due-date markers per order, with order id printed on top.
        y_top = -0.70
        due_rows = data.groupby("order_id").agg({"due_date": "first", "demand_type": "first"}).reset_index()
        for _, row in due_rows.iterrows():
            due = pd.to_datetime(row["due_date"])
            if due >= origin:
                x = (due - origin).total_seconds() / 3600.0
                ax.axvline(x, linestyle="--", linewidth=0.9, alpha=0.34)
                ax.text(x, y_top, str(row["order_id"]), rotation=90, fontsize=7, ha="right", va="bottom", alpha=0.62)

        ax.set_yticks(range(len(stage_order)))
        ax.set_yticklabels(stage_order)
        ax.invert_yaxis()
        ax.set_xlabel(f"Hours from {origin:%Y-%m-%d %H:%M}")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.25)
        ax.text(
            0.01,
            0.01,
            "Label: order + batch index. Dashed vertical lines: order due dates. White segment: setup time.",
            transform=ax.transAxes,
            fontsize=8,
            color="#475569",
            va="bottom",
        )
        self.draw()
