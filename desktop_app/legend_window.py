from __future__ import annotations

import pandas as pd

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from .gantt_widget import make_color_map


class OrderLegendWindow(QDialog):
    def __init__(self, schedule: pd.DataFrame | None, parent=None, *, color_by: str = "order_id") -> None:
        super().__init__(parent)
        self.setWindowTitle("Order / batch color legend")
        self.resize(860, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Colors match the current Gantt setting: color by '{color_by}'. Labels show order + batch index."))
        table = QTableWidget()
        layout.addWidget(table)
        if schedule is None or schedule.empty:
            table.setRowCount(0)
            table.setColumnCount(0)
            return

        df = schedule.copy()
        color_col = color_by if color_by in df.columns else "order_id"
        color_map = make_color_map(df[color_col].astype(str).fillna("—").tolist())

        base_cols = ["order_id", "product_id", "product_family", "demand_type", "batches_in_order", "quantity", "due_date", "priority"]
        cols = [c for c in base_cols if c in df.columns]
        use_cols = list(dict.fromkeys([color_col] + cols))
        grouped = df[use_cols].drop_duplicates("order_id" if "order_id" in cols else color_col)
        sort_cols = [c for c in ["demand_type", "due_date", "priority", "order_id"] if c in grouped.columns]
        if sort_cols:
            ascending_map = {"demand_type": True, "due_date": True, "priority": False, "order_id": True}
            grouped = grouped.sort_values(sort_cols, ascending=[ascending_map[c] for c in sort_cols])
        grouped = grouped.reset_index(drop=True)

        display_cols = ["color", f"color_key:{color_col}"] + cols
        table.setColumnCount(len(display_cols))
        table.setRowCount(len(grouped))
        table.setHorizontalHeaderLabels(display_cols)
        for r, row in grouped.iterrows():
            key = str(row.get(color_col, "—"))
            color = color_map.get(key, "#cccccc")
            swatch = QTableWidgetItem(color)
            swatch.setBackground(QColor(color))
            swatch.setForeground(QColor(color))
            table.setItem(r, 0, swatch)
            table.setItem(r, 1, QTableWidgetItem(key))
            for offset, col in enumerate(cols, start=2):
                table.setItem(r, offset, QTableWidgetItem(str(row.get(col, ""))))
        table.resizeColumnsToContents()
