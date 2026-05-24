from __future__ import annotations

import pandas as pd

from PySide6.QtWidgets import QDialog, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout


class OrderLegendWindow(QDialog):
    def __init__(self, schedule: pd.DataFrame | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Order / batch legend")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Colors are assigned by order; labels on the Gantt include batch index."))
        table = QTableWidget()
        layout.addWidget(table)
        if schedule is None or schedule.empty:
            table.setRowCount(0)
            table.setColumnCount(0)
            return
        cols = ["order_id", "product_id", "demand_type", "batches_in_order", "quantity", "due_date", "priority"]
        df = (
            schedule[cols]
            .drop_duplicates("order_id")
            .sort_values(["demand_type", "due_date", "priority"], ascending=[True, True, False])
            .reset_index(drop=True)
        )
        table.setColumnCount(len(cols))
        table.setRowCount(len(df))
        table.setHorizontalHeaderLabels(cols)
        for r, row in df.iterrows():
            for c, col in enumerate(cols):
                table.setItem(r, c, QTableWidgetItem(str(row[col])))
        table.resizeColumnsToContents()
