from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tarkett_scheduler import DemoConfig, generate_tarkett_like_demo_bundle, load_data_bundle, save_result, solve_schedule
from .dataframe_model import DataFrameModel
from .gantt_widget import GanttWidget
from .inventory_widget import InventoryWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Tarkett-like Flow-Line Scheduling Demo")
        self.resize(1400, 900)

        self.bundle_dir: Optional[Path] = None
        self.baseline_result = None
        self.reschedule_result = None

        self.orders_model = DataFrameModel()
        self.schedule_model = DataFrameModel()
        self.order_summary_model = DataFrameModel()
        self.inventory_model = DataFrameModel()
        self.recommendations_model = DataFrameModel()

        self.gantt = GanttWidget()
        self.inventory_plot = InventoryWidget()
        self.kpi_text = QTextEdit()
        self.kpi_text.setReadOnly(True)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        controls = QGroupBox("Demo controls")
        grid = QGridLayout(controls)

        self.bundle_label = QLabel("No bundle loaded")
        self.bundle_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.time_limit = QSpinBox()
        self.time_limit.setRange(2, 180)
        self.time_limit.setValue(20)
        self.time_limit.setSuffix(" s")

        btn_generate = QPushButton("Generate Tarkett-like demo data")
        btn_generate.clicked.connect(self.generate_demo_data)
        btn_load = QPushButton("Load CSV bundle")
        btn_load.clicked.connect(self.load_bundle_dialog)
        btn_solve = QPushButton("Solve baseline")
        btn_solve.clicked.connect(self.solve_baseline)
        btn_reschedule = QPushButton("Run Press downtime rescheduling")
        btn_reschedule.clicked.connect(self.run_rescheduling)
        btn_export = QPushButton("Export current outputs")
        btn_export.clicked.connect(self.export_outputs)

        grid.addWidget(btn_generate, 0, 0)
        grid.addWidget(btn_load, 0, 1)
        grid.addWidget(QLabel("Solver time limit:"), 0, 2)
        grid.addWidget(self.time_limit, 0, 3)
        grid.addWidget(btn_solve, 0, 4)
        grid.addWidget(btn_reschedule, 0, 5)
        grid.addWidget(btn_export, 0, 6)
        grid.addWidget(QLabel("Bundle:"), 1, 0)
        grid.addWidget(self.bundle_label, 1, 1, 1, 6)

        layout.addWidget(controls)

        splitter = QSplitter(Qt.Vertical)
        tabs = QTabWidget()

        self.orders_table = self._table(self.orders_model)
        self.schedule_table = self._table(self.schedule_model)
        self.order_summary_table = self._table(self.order_summary_model)
        self.inventory_table = self._table(self.inventory_model)
        self.recommendations_table = self._table(self.recommendations_model)

        tabs.addTab(self.orders_table, "Orders")
        tabs.addTab(self.gantt, "Gantt")
        tabs.addTab(self.schedule_table, "Schedule table")
        tabs.addTab(self.order_summary_table, "Order summary")
        tabs.addTab(self.inventory_plot, "Inventory chart")
        tabs.addTab(self.inventory_table, "Inventory events")
        tabs.addTab(self.recommendations_table, "Recommendations")
        tabs.addTab(self.kpi_text, "KPIs")

        splitter.addWidget(tabs)
        splitter.addWidget(self.status_text)
        splitter.setSizes([740, 120])
        layout.addWidget(splitter)
        self.setCentralWidget(root)
        self._log("Generate a demo dataset or load an existing CSV bundle to start.")

    def _table(self, model: DataFrameModel) -> QTableView:
        view = QTableView()
        view.setModel(model)
        view.setSortingEnabled(True)
        view.horizontalHeader().setStretchLastSection(False)
        view.resizeColumnsToContents()
        return view

    def _log(self, message: str) -> None:
        self.status_text.append(message)

    def generate_demo_data(self) -> None:
        path = generate_tarkett_like_demo_bundle(DemoConfig(output_dir="generated_demo_data/tarkett_like_demo"))
        self.bundle_dir = Path(path)
        self.bundle_label.setText(str(self.bundle_dir.resolve()))
        self._load_preview()
        self._log(f"Generated Tarkett-like demo bundle: {self.bundle_dir}")

    def load_bundle_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select CSV data bundle")
        if not folder:
            return
        self.bundle_dir = Path(folder)
        self.bundle_label.setText(str(self.bundle_dir.resolve()))
        self._load_preview()
        self._log(f"Loaded bundle: {self.bundle_dir}")

    def _load_preview(self) -> None:
        if self.bundle_dir is None:
            return
        try:
            bundle = load_data_bundle(self.bundle_dir)
            self.orders_model.set_dataframe(bundle.orders)
            self.orders_table.resizeColumnsToContents()
        except Exception as exc:
            QMessageBox.critical(self, "Load error", str(exc))
            self._log(f"Load error: {exc}")

    def solve_baseline(self) -> None:
        if self.bundle_dir is None:
            self.generate_demo_data()
        assert self.bundle_dir is not None
        try:
            self._log("Solving baseline plan...")
            self.baseline_result = solve_schedule(
                self.bundle_dir,
                scenario_name="baseline_no_disruption",
                time_limit_seconds=int(self.time_limit.value()),
            )
            self._show_result(self.baseline_result, "Baseline plan")
            self._log(f"Baseline solved: {self.baseline_result.status}; method={self.baseline_result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Solver error", str(exc))
            self._log(f"Solver error: {exc}")

    def run_rescheduling(self) -> None:
        if self.baseline_result is None:
            self.solve_baseline()
        if self.bundle_dir is None or self.baseline_result is None:
            return
        try:
            self._log("Running Press downtime rescheduling...")
            self.reschedule_result = solve_schedule(
                self.bundle_dir,
                scenario_name="press_downtime_3h",
                previous_schedule=self.baseline_result.schedule,
                time_limit_seconds=int(self.time_limit.value()),
            )
            self._show_result(self.reschedule_result, "Rescheduled plan: Press downtime 3h")
            self._log(f"Rescheduling solved: {self.reschedule_result.status}; method={self.reschedule_result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Rescheduling error", str(exc))
            self._log(f"Rescheduling error: {exc}")

    def _show_result(self, result, title: str) -> None:
        self.schedule_model.set_dataframe(result.schedule)
        self.order_summary_model.set_dataframe(result.order_summary)
        self.inventory_model.set_dataframe(result.inventory_projection)
        self.recommendations_model.set_dataframe(result.recommendations)
        self.gantt.plot_schedule(result.schedule, title)
        self.inventory_plot.plot_inventory(result.inventory_projection, "Inventory projection")
        self.kpi_text.setPlainText(self._format_kpis(result))
        for table in [self.schedule_table, self.order_summary_table, self.inventory_table, self.recommendations_table]:
            table.resizeColumnsToContents()

    def _format_kpis(self, result) -> str:
        lines = ["Solver metadata", "---------------"]
        for k, v in result.metadata.items():
            lines.append(f"{k}: {v}")
        lines.extend(["", "Status", "------", f"status: {result.status}", f"objective_value: {result.objective_value}", f"solve_time_seconds: {result.solve_time_seconds:.3f}"])
        lines.extend(["", "KPIs", "----"])
        for k, v in result.kpis.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def export_outputs(self) -> None:
        result = self.reschedule_result or self.baseline_result
        if result is None:
            QMessageBox.information(self, "Nothing to export", "Solve a plan first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        out = save_result(result, folder)
        self._log(f"Exported outputs to: {out}")
        QMessageBox.information(self, "Export complete", f"Saved CSV outputs to:\n{out}")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
