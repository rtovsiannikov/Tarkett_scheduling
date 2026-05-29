from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class InventoryWidget(QWidget):
    """Interactive inventory time-series view.

    The old widget plotted four hard-coded lines. This version lets the user
    inspect concrete stock items and aggregate warehouse occupancy over time,
    using the same event projection that is exported to inventory_projection.csv.
    """

    ALL = "__ALL__"

    def __init__(self) -> None:
        super().__init__()
        self._projection = pd.DataFrame()
        self._title = "Inventory projection"
        self._updating_controls = False

        self.location_combo = QComboBox()
        self.item_combo = QComboBox()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Selected item / selected warehouse items", "items")
        self.mode_combo.addItem("Total stock by warehouse", "totals")
        self.mode_combo.addItem("Both selected items and warehouse totals", "both")
        self.mode_combo.setCurrentIndex(2)

        self.show_thresholds_check = QCheckBox("Safety / target / max")
        self.show_thresholds_check.setChecked(True)
        self.show_events_check = QCheckBox("Event markers")
        self.show_events_check.setChecked(False)
        self.show_violations_check = QCheckBox("Violation markers")
        self.show_violations_check.setChecked(True)

        self.summary_label = QLabel("No inventory projection yet")
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.summary_label.setStyleSheet("color:#334155; padding: 4px;")

        self.figure = Figure(figsize=(12, 5.6), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(440)

        controls = QGroupBox("Inventory view")
        controls_layout = QHBoxLayout(controls)
        controls_layout.addWidget(QLabel("Warehouse:"))
        controls_layout.addWidget(self.location_combo, stretch=1)
        controls_layout.addWidget(QLabel("Item:"))
        controls_layout.addWidget(self.item_combo, stretch=2)
        controls_layout.addWidget(QLabel("Mode:"))
        controls_layout.addWidget(self.mode_combo, stretch=2)
        controls_layout.addWidget(self.show_thresholds_check)
        controls_layout.addWidget(self.show_events_check)
        controls_layout.addWidget(self.show_violations_check)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        layout.addWidget(controls)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.canvas, stretch=1)

        self.location_combo.currentIndexChanged.connect(self._on_location_changed)
        self.item_combo.currentIndexChanged.connect(self._redraw)
        self.mode_combo.currentIndexChanged.connect(self._redraw)
        self.show_thresholds_check.stateChanged.connect(self._redraw)
        self.show_events_check.stateChanged.connect(self._redraw)
        self.show_violations_check.stateChanged.connect(self._redraw)

    def plot_inventory(self, projection: pd.DataFrame | None, title: str = "Inventory projection") -> None:
        self._title = title
        if projection is None or projection.empty:
            self._projection = pd.DataFrame()
        else:
            self._projection = projection.copy()
            if "event_time" in self._projection.columns:
                self._projection["event_time"] = pd.to_datetime(self._projection["event_time"], errors="coerce")
            for col in ["location", "item_id", "event_type", "details"]:
                if col in self._projection.columns:
                    self._projection[col] = self._projection[col].fillna("").astype(str)
        self._populate_controls()
        self._redraw()

    def _populate_controls(self) -> None:
        self._updating_controls = True
        try:
            current_location = self.location_combo.currentData() or self.ALL
            self.location_combo.blockSignals(True)
            self.location_combo.clear()
            self.location_combo.addItem("All warehouses", self.ALL)
            if not self._projection.empty and "location" in self._projection.columns:
                locations = sorted(self._projection["location"].dropna().astype(str).unique().tolist())
                for loc in locations:
                    self.location_combo.addItem(loc, loc)
                if current_location in locations:
                    self.location_combo.setCurrentIndex(self.location_combo.findData(current_location))
                else:
                    self.location_combo.setCurrentIndex(0)
            self.location_combo.blockSignals(False)
            self._populate_item_combo()
        finally:
            self._updating_controls = False

    def _populate_item_combo(self) -> None:
        current_item = self.item_combo.currentData()
        df = self._filtered_by_location(self.location_combo.currentData() or self.ALL)
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        self.item_combo.addItem("All items", None)
        if not df.empty and {"location", "item_id"}.issubset(df.columns):
            pairs = (
                df[["location", "item_id"]]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .sort_values(["location", "item_id"])
            )
            show_location = (self.location_combo.currentData() or self.ALL) == self.ALL
            for _, row in pairs.iterrows():
                loc, item = row["location"], row["item_id"]
                label = f"{loc}:{item}" if show_location else item
                self.item_combo.addItem(label, (loc, item))
            if current_item is not None:
                idx = self.item_combo.findData(current_item)
                if idx >= 0:
                    self.item_combo.setCurrentIndex(idx)
        self.item_combo.blockSignals(False)

    def _on_location_changed(self) -> None:
        if self._updating_controls:
            return
        self._populate_item_combo()
        self._redraw()

    def _filtered_by_location(self, location: Any) -> pd.DataFrame:
        if self._projection.empty or location in (None, self.ALL):
            return self._projection.copy()
        return self._projection[self._projection["location"].astype(str) == str(location)].copy()

    def _selected_item_groups(self) -> List[Tuple[str, str, pd.DataFrame]]:
        df = self._filtered_by_location(self.location_combo.currentData() or self.ALL)
        if df.empty or not {"location", "item_id"}.issubset(df.columns):
            return []
        item_data = self.item_combo.currentData()
        if item_data is not None:
            loc, item = item_data
            g = df[(df["location"].astype(str) == str(loc)) & (df["item_id"].astype(str) == str(item))].copy()
            return [(str(loc), str(item), g.sort_values("event_time"))] if not g.empty else []

        groups: List[Tuple[str, str, pd.DataFrame]] = []
        # Keep the chart readable when the user selects all warehouses/items.
        counts = (
            df.groupby(["location", "item_id"], dropna=False)
            .size()
            .sort_values(ascending=False)
            .head(14)
        )
        for (loc, item), _ in counts.items():
            g = df[(df["location"].astype(str) == str(loc)) & (df["item_id"].astype(str) == str(item))].copy()
            if not g.empty:
                groups.append((str(loc), str(item), g.sort_values("event_time")))
        return groups

    def _location_totals(self) -> pd.DataFrame:
        df = self._filtered_by_location(self.location_combo.currentData() or self.ALL)
        if df.empty or not {"location", "item_id", "event_time", "balance_qty"}.issubset(df.columns):
            return pd.DataFrame(columns=["event_time", "location", "total_balance_qty"])
        rows: List[Dict[str, Any]] = []
        for loc, group in df.sort_values("event_time").groupby("location"):
            current: Dict[str, float] = {}
            for event_time, tg in group.groupby("event_time", sort=True):
                for _, row in tg.iterrows():
                    current[str(row["item_id"])] = float(row.get("balance_qty", 0) or 0)
                rows.append(
                    {
                        "event_time": event_time,
                        "location": str(loc),
                        "total_balance_qty": round(sum(current.values()), 4),
                    }
                )
        return pd.DataFrame(rows)

    def _redraw(self) -> None:
        if self._updating_controls:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if self._projection.empty:
            ax.set_title("No inventory projection yet")
            self.summary_label.setText("No inventory projection yet")
            self.canvas.draw()
            return

        mode = self.mode_combo.currentData() or "items"
        lines = 0
        if mode in {"items", "both"}:
            groups = self._selected_item_groups()
            for loc, item, g in groups:
                if g.empty:
                    continue
                label = f"{loc}:{item}"
                ax.step(g["event_time"], g["balance_qty"], where="post", label=label)
                lines += 1
                if self.show_thresholds_check.isChecked() and len(groups) <= 3:
                    self._draw_thresholds(ax, g, label_prefix=label)
                if self.show_events_check.isChecked() and len(groups) <= 6:
                    for ts in g["event_time"].dropna().unique():
                        ax.axvline(ts, linewidth=0.7, alpha=0.08)
                if self.show_violations_check.isChecked():
                    self._draw_violations(ax, g)

        if mode in {"totals", "both"}:
            totals = self._location_totals()
            if not totals.empty:
                for loc, g in totals.groupby("location"):
                    ax.step(
                        g["event_time"],
                        g["total_balance_qty"],
                        where="post",
                        linewidth=2.2,
                        linestyle="--" if mode == "both" else "-",
                        label=f"TOTAL {loc}",
                    )
                    lines += 1

        if lines == 0:
            ax.text(0.5, 0.5, "No matching inventory rows", ha="center", va="center", transform=ax.transAxes)

        ax.set_title(self._title)
        ax.set_ylabel("Quantity")
        ax.tick_params(axis="x", rotation=25)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="best")
        self.summary_label.setText(self._summary_text(lines))
        self.canvas.draw()

    def _draw_thresholds(self, ax: Any, g: pd.DataFrame, *, label_prefix: str) -> None:
        if g.empty:
            return
        for col, style, suffix in [
            ("safety_stock", "--", "safety"),
            ("target_stock", ":", "target"),
            ("max_stock", "-.", "max"),
        ]:
            if col not in g.columns:
                continue
            value = pd.to_numeric(g[col], errors="coerce").dropna()
            if value.empty:
                continue
            threshold = float(value.iloc[-1])
            if threshold > 0:
                ax.axhline(threshold, linestyle=style, linewidth=0.9, alpha=0.35, label=f"{label_prefix} {suffix}")

    def _draw_violations(self, ax: Any, g: pd.DataFrame) -> None:
        if g.empty:
            return
        mask = pd.Series([False] * len(g), index=g.index)
        for col in ["below_zero", "below_safety", "above_max"]:
            if col in g.columns:
                mask = mask | g[col].fillna(False).astype(bool)
        bad = g[mask]
        if not bad.empty:
            ax.scatter(bad["event_time"], bad["balance_qty"], marker="x", s=52, linewidths=1.4, label="inventory warning")

    def _summary_text(self, plotted_lines: int) -> str:
        df = self._filtered_by_location(self.location_combo.currentData() or self.ALL)
        if df.empty:
            return "No rows match the selected warehouse/item filter."
        item_data = self.item_combo.currentData()
        if item_data is not None:
            loc, item = item_data
            df = df[(df["location"].astype(str) == str(loc)) & (df["item_id"].astype(str) == str(item))]

        event_count = len(df)
        locations = df["location"].nunique() if "location" in df.columns else 0
        items = df[["location", "item_id"]].drop_duplicates().shape[0] if {"location", "item_id"}.issubset(df.columns) else 0
        latest_lines: List[str] = []
        if {"location", "item_id", "event_time", "balance_qty"}.issubset(df.columns):
            latest = df.sort_values("event_time").groupby(["location", "item_id"], as_index=False).tail(1)
            for _, row in latest.head(6).iterrows():
                latest_lines.append(f"{row['location']}:{row['item_id']}={float(row['balance_qty']):.1f}")

        def count_bool(col: str) -> int:
            return int(df[col].fillna(False).astype(bool).sum()) if col in df.columns else 0

        warnings = []
        below_zero = count_bool("below_zero")
        below_safety = count_bool("below_safety")
        above_max = count_bool("above_max")
        if below_zero:
            warnings.append(f"below zero: {below_zero}")
        if below_safety:
            warnings.append(f"below safety: {below_safety}")
        if above_max:
            warnings.append(f"above max: {above_max}")
        warning_text = "; ".join(warnings) if warnings else "no threshold violations in selected rows"
        latest_text = "; ".join(latest_lines)
        if len(latest_lines) == 6 and items > 6:
            latest_text += "; ..."
        return (
            f"Rows: {event_count} | Warehouses: {locations} | Item traces: {items} | "
            f"Plotted lines: {plotted_lines}. Latest: {latest_text}. Warnings: {warning_text}."
        )
