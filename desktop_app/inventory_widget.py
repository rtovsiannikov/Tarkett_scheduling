from __future__ import annotations

import pandas as pd

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class InventoryWidget(FigureCanvas):
    """Inventory time-series view for raw material, Kanban, finished goods."""

    def __init__(self):
        self.figure = Figure(figsize=(11, 4.5), tight_layout=True)
        super().__init__(self.figure)

    def plot_inventory(self, projection: pd.DataFrame | None, title: str = "Inventory projection") -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if projection is None or projection.empty:
            ax.set_title("No inventory projection yet")
            self.draw()
            return
        df = projection.copy()
        df["event_time"] = pd.to_datetime(df["event_time"])
        # Focus on the most demonstrative items.
        preferred = [
            ("KANBAN", "WIP_BOARD"),
            ("FINISHED_GOODS", "TRES_STOCK"),
            ("RAW_MATERIAL", "oak_top_layer"),
            ("RAW_MATERIAL", "packaging_box"),
        ]
        any_line = False
        for loc, item in preferred:
            g = df[(df["location"] == loc) & (df["item_id"] == item)].sort_values("event_time")
            if g.empty:
                continue
            any_line = True
            label = f"{loc}:{item}"
            ax.step(g["event_time"], g["balance_qty"], where="post", label=label)
            safety = float(g["safety_stock"].iloc[-1]) if "safety_stock" in g.columns else 0
            target = float(g["target_stock"].iloc[-1]) if "target_stock" in g.columns else 0
            if safety > 0:
                ax.axhline(safety, linestyle="--", linewidth=0.8, alpha=0.35)
            if target > 0:
                ax.axhline(target, linestyle=":", linewidth=0.8, alpha=0.35)
        if not any_line:
            for (loc, item), g in df.groupby(["location", "item_id"]):
                ax.step(g["event_time"], g["balance_qty"], where="post", label=f"{loc}:{item}")
        ax.set_title(title)
        ax.set_ylabel("Quantity")
        ax.tick_params(axis="x", rotation=25)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
        self.draw()
