from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tarkett_scheduler import (
    DemoConfig,
    build_batches,
    compute_batch_summary,
    generate_tarkett_like_demo_bundle,
    load_data_bundle,
    save_result,
    solve_schedule,
)
from .dataframe_model import DataFrameModel
from .gantt_widget import GanttWidget
from .inventory_widget import InventoryWidget
from .kpi_cards import KpiPanel
from .legend_window import OrderLegendWindow


APP_STYLE = """
QMainWindow { background: #f5f7fb; }
QGroupBox {
    border: 1px solid #d8dee8;
    border-radius: 12px;
    margin-top: 8px;
    padding: 8px;
    background: #ffffff;
    font-weight: 700;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QPushButton {
    padding: 8px 10px;
    border-radius: 8px;
    background: #1f6feb;
    color: white;
    font-weight: 700;
}
QPushButton:disabled { background: #aeb8c6; }
QPushButton#SecondaryButton { background: #394150; }
QPushButton#SuccessButton { background: #15803d; }
QLineEdit, QSpinBox {
    padding: 5px;
    border: 1px solid #cfd7e3;
    border-radius: 7px;
    background: #ffffff;
}
QTableView {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    gridline-color: #e5e7eb;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}
QHeaderView::section {
    background: #eef2f7;
    padding: 5px;
    border: 1px solid #d9e0ea;
    font-weight: 700;
}
QTextEdit {
    background: #0f172a;
    color: #e5e7eb;
    border-radius: 10px;
    font-family: Consolas, monospace;
}
QFrame#HeaderFrame, QFrame#KpiCard {
    background: #ffffff;
    border: 1px solid #dde3ea;
    border-radius: 16px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Tarkett-like Factory Scheduling & Rescheduling Demo")
        self.resize(1520, 930)
        self.setStyleSheet(APP_STYLE)

        self.bundle_dir: Optional[Path] = None
        self.baseline_result = None
        self.reschedule_result = None
        self.legend_window: Optional[OrderLegendWindow] = None

        self.orders_model = DataFrameModel()
        self.batch_model = DataFrameModel()
        self.schedule_model = DataFrameModel()
        self.order_summary_model = DataFrameModel()
        self.inventory_model = DataFrameModel()
        self.recommendations_model = DataFrameModel()
        self.products_model = DataFrameModel()
        self.work_centers_model = DataFrameModel()
        self.raw_inventory_model = DataFrameModel()

        self.baseline_gantt = GanttWidget()
        self.reschedule_gantt = GanttWidget()
        self.inventory_plot = InventoryWidget()
        self.kpi_panel = KpiPanel()
        self.kpi_text = QTextEdit()
        self.kpi_text.setReadOnly(True)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)

        self._build_actions()
        self._build_ui()
        self._try_load_default_bundle()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_actions(self) -> None:
        open_action = QAction("Open data bundle", self)
        open_action.triggered.connect(self.load_bundle_dialog)
        export_action = QAction("Export latest results", self)
        export_action.triggered.connect(self.export_outputs)
        legend_action = QAction("Show order legend", self)
        legend_action.triggered.connect(self.show_legend)
        self.menuBar().addAction(open_action)
        self.menuBar().addAction(export_action)
        self.menuBar().addAction(legend_action)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)
        root_layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Horizontal)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setWidget(self._build_sidebar())
        splitter.addWidget(sidebar_scroll)
        splitter.addWidget(self._build_main_area())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 1180])
        root_layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(root)
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Generate demo data or load a CSV bundle.")
        self._log("Generate a Tarkett-like bundle, then solve the baseline plan.")

    def _build_header(self) -> QWidget:
        box = QFrame()
        box.setObjectName("HeaderFrame")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Tarkett-like Factory Scheduling & Rescheduling Demo")
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)
        subtitle = QLabel("Flow line: Raw materials → PREP → PRESS → KANBAN → LACK → PROFILING → PACK → Finished goods")
        subtitle.setStyleSheet("color: #475569;")
        title_box = QVBoxLayout()
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        self.bundle_label = QLabel("Dataset: not selected")
        self.bundle_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label = QLabel("Status: idle")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.bundle_label.setStyleSheet("color: #334155; padding: 3px 8px;")
        self.status_label.setStyleSheet("color: #334155; padding: 3px 8px;")
        layout.addLayout(title_box, stretch=1)
        layout.addWidget(self.bundle_label)
        layout.addWidget(self.status_label)
        return box

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(310)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        data_group = QGroupBox("Data & generator")
        data_layout = QVBoxLayout(data_group)
        self.bundle_path_edit = QLineEdit()
        self.bundle_path_edit.setReadOnly(True)
        btn_generate = QPushButton("Generate Tarkett-like demo data")
        btn_generate.setObjectName("SuccessButton")
        btn_generate.clicked.connect(self.generate_demo_data)
        btn_load = QPushButton("Load CSV bundle")
        btn_load.setObjectName("SecondaryButton")
        btn_load.clicked.connect(self.load_bundle_dialog)
        data_layout.addWidget(QLabel("Bundle folder"))
        data_layout.addWidget(self.bundle_path_edit)
        data_layout.addWidget(btn_generate)
        data_layout.addWidget(btn_load)

        solver_group = QGroupBox("Solver settings")
        solver_layout = QGridLayout(solver_group)
        self.time_limit = QSpinBox()
        self.time_limit.setRange(2, 180)
        self.time_limit.setValue(20)
        self.time_limit.setSuffix(" s")
        solver_layout.addWidget(QLabel("Time limit"), 0, 0)
        solver_layout.addWidget(self.time_limit, 0, 1)
        self.scenario_edit = QLineEdit("press_downtime_3h")
        solver_layout.addWidget(QLabel("Scenario"), 1, 0)
        solver_layout.addWidget(self.scenario_edit, 1, 1)

        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        self.solve_button = QPushButton("Solve baseline plan")
        self.solve_button.clicked.connect(self.solve_baseline)
        self.reschedule_button = QPushButton("Run Press downtime rescheduling")
        self.reschedule_button.setObjectName("SecondaryButton")
        self.reschedule_button.clicked.connect(self.run_rescheduling)
        self.export_button = QPushButton("Export current outputs")
        self.export_button.setObjectName("SecondaryButton")
        self.export_button.clicked.connect(self.export_outputs)
        self.legend_button = QPushButton("Show order legend")
        self.legend_button.setObjectName("SecondaryButton")
        self.legend_button.clicked.connect(self.show_legend)
        self.progress_label = QLabel("Idle")
        self.progress_label.setStyleSheet("color: #5a6472; font-size: 11px;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("idle")
        actions_layout.addWidget(self.solve_button)
        actions_layout.addWidget(self.reschedule_button)
        actions_layout.addWidget(self.export_button)
        actions_layout.addWidget(self.legend_button)
        actions_layout.addSpacing(6)
        actions_layout.addWidget(self.progress_label)
        actions_layout.addWidget(self.progress_bar)

        concept_group = QGroupBox("Demo concept")
        concept_layout = QVBoxLayout(concept_group)
        concept = QLabel(
            "Orders are split into production batches. MTO batches are measured by OTIF; "
            "MTS batches replenish finished-goods stock. Kanban is modeled as a WIP buffer after PRESS."
        )
        concept.setWordWrap(True)
        concept.setStyleSheet("color: #475569;")
        concept_layout.addWidget(concept)

        layout.addWidget(data_group)
        layout.addWidget(solver_group)
        layout.addWidget(actions_group)
        layout.addWidget(concept_group)
        layout.addStretch(1)
        return panel

    def _build_main_area(self) -> QWidget:
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.kpi_panel)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)

        self.orders_table = self._table(self.orders_model)
        self.batch_table = self._table(self.batch_model)
        self.schedule_table = self._table(self.schedule_model)
        self.order_summary_table = self._table(self.order_summary_model)
        self.inventory_table = self._table(self.inventory_model)
        self.recommendations_table = self._table(self.recommendations_model)
        self.products_table = self._table(self.products_model)
        self.work_centers_table = self._table(self.work_centers_model)
        self.raw_inventory_table = self._table(self.raw_inventory_model)

        self.tabs.addTab(self._wrap_scrollable(self.baseline_gantt), "Baseline Plan")
        self.tabs.addTab(self._wrap_scrollable(self.reschedule_gantt), "Rescheduled Plan")
        self.tabs.addTab(self.batch_table, "Batch split")
        self.tabs.addTab(self.schedule_table, "Operations table")
        self.tabs.addTab(self.order_summary_table, "Order summary")
        self.tabs.addTab(self.orders_table, "Orders")
        self.tabs.addTab(self._wrap_scrollable(self.inventory_plot), "Inventory chart")
        self.tabs.addTab(self.inventory_table, "Inventory events")
        self.tabs.addTab(self.recommendations_table, "Recommendations")
        self.tabs.addTab(self._build_raw_data_tab(), "Raw data")
        self.tabs.addTab(self.kpi_text, "KPI details")
        self.tabs.addTab(self.status_text, "Solver log")
        layout.addWidget(self.tabs, stretch=1)
        return area

    def _build_raw_data_tab(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Products"), 0, 0)
        layout.addWidget(self.products_table, 1, 0)
        layout.addWidget(QLabel("Work centers"), 2, 0)
        layout.addWidget(self.work_centers_table, 3, 0)
        layout.addWidget(QLabel("Inventory / warehouses"), 4, 0)
        layout.addWidget(self.raw_inventory_table, 5, 0)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(3, 1)
        layout.setRowStretch(5, 1)
        return widget

    def _wrap_scrollable(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _table(self, model: DataFrameModel) -> QTableView:
        view = QTableView()
        view.setModel(model)
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.horizontalHeader().setStretchLastSection(False)
        view.resizeColumnsToContents()
        return view

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _try_load_default_bundle(self) -> None:
        default = Path("generated_demo_data/tarkett_like_demo")
        if default.exists():
            self.bundle_dir = default
            self._set_bundle_loaded(default)
            self._load_preview()

    def _log(self, message: str) -> None:
        self.status_text.append(message)
        self.statusBar().showMessage(message)

    def _busy(self, message: str) -> None:
        self.progress_label.setText(message)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("running")
        self.status_label.setText(f"Status: {message}")
        QApplication.processEvents()

    def _idle(self, message: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("done")
        self.progress_label.setText(message)
        self.status_label.setText(f"Status: {message}")
        self.statusBar().showMessage(message)

    def _set_bundle_loaded(self, path: Path) -> None:
        self.bundle_dir = Path(path)
        self.bundle_path_edit.setText(str(self.bundle_dir.resolve()))
        self.bundle_label.setText(f"Dataset: {self.bundle_dir.name}")

    def generate_demo_data(self) -> None:
        try:
            self._busy("Generating demo data")
            path = generate_tarkett_like_demo_bundle(DemoConfig(output_dir="generated_demo_data/tarkett_like_demo"))
            self._set_bundle_loaded(Path(path))
            self._load_preview()
            self._idle("demo data generated")
            self._log(f"Generated Tarkett-like demo bundle: {Path(path).resolve()}")
        except Exception as exc:
            QMessageBox.critical(self, "Generation error", str(exc))
            self._idle("generation failed")
            self._log(f"Generation error: {exc}")

    def load_bundle_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select CSV data bundle")
        if not folder:
            return
        self._set_bundle_loaded(Path(folder))
        self._load_preview()
        self._idle("bundle loaded")
        self._log(f"Loaded bundle: {self.bundle_dir}")

    def _load_preview(self) -> None:
        if self.bundle_dir is None:
            return
        try:
            bundle = load_data_bundle(self.bundle_dir)
            self.orders_model.set_dataframe(bundle.orders)
            self.batch_model.set_dataframe(build_batches(bundle))
            self.products_model.set_dataframe(bundle.products)
            self.work_centers_model.set_dataframe(bundle.work_centers)
            self.raw_inventory_model.set_dataframe(bundle.inventory)
            for table in [self.orders_table, self.batch_table, self.products_table, self.work_centers_table, self.raw_inventory_table]:
                table.resizeColumnsToContents()
        except Exception as exc:
            QMessageBox.critical(self, "Load error", str(exc))
            self._log(f"Load error: {exc}")

    def solve_baseline(self) -> None:
        if self.bundle_dir is None:
            self.generate_demo_data()
        if self.bundle_dir is None:
            return
        try:
            self._busy("Solving baseline")
            self.baseline_result = solve_schedule(
                self.bundle_dir,
                scenario_name="baseline_no_disruption",
                time_limit_seconds=int(self.time_limit.value()),
            )
            self._show_result(self.baseline_result, "Baseline plan", target="baseline")
            self.tabs.setCurrentIndex(0)
            self._idle("baseline solved")
            self._log(f"Baseline solved: {self.baseline_result.status}; method={self.baseline_result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Solver error", str(exc))
            self._idle("solver failed")
            self._log(f"Solver error: {exc}")

    def run_rescheduling(self) -> None:
        if self.baseline_result is None:
            self.solve_baseline()
        if self.bundle_dir is None or self.baseline_result is None:
            return
        scenario = self.scenario_edit.text().strip() or "press_downtime_3h"
        try:
            self._busy("Running rescheduling")
            self.reschedule_result = solve_schedule(
                self.bundle_dir,
                scenario_name=scenario,
                previous_schedule=self.baseline_result.schedule,
                time_limit_seconds=int(self.time_limit.value()),
            )
            self._show_result(self.reschedule_result, f"Rescheduled plan: {scenario}", target="reschedule")
            self.tabs.setCurrentIndex(1)
            self._idle("rescheduling solved")
            self._log(f"Rescheduling solved: {self.reschedule_result.status}; method={self.reschedule_result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Rescheduling error", str(exc))
            self._idle("rescheduling failed")
            self._log(f"Rescheduling error: {exc}")

    def _show_result(self, result, title: str, *, target: str) -> None:
        batch_summary = compute_batch_summary(result.schedule)
        self.batch_model.set_dataframe(batch_summary)
        self.schedule_model.set_dataframe(result.schedule)
        self.order_summary_model.set_dataframe(result.order_summary)
        self.inventory_model.set_dataframe(result.inventory_projection)
        self.recommendations_model.set_dataframe(result.recommendations)
        if target == "baseline":
            self.baseline_gantt.plot_schedule(result.schedule, title)
        else:
            self.reschedule_gantt.plot_schedule(result.schedule, title)
        self.inventory_plot.plot_inventory(result.inventory_projection, "Inventory projection")
        self.kpi_panel.set_kpis(result.kpis)
        self.kpi_text.setPlainText(self._format_kpis(result))
        for table in [self.batch_table, self.schedule_table, self.order_summary_table, self.inventory_table, self.recommendations_table]:
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
        batch_summary = compute_batch_summary(result.schedule)
        batch_summary.to_csv(Path(out) / "batch_summary.csv", index=False)
        self._log(f"Exported outputs to: {out}")
        QMessageBox.information(self, "Export complete", f"Saved CSV outputs to:\n{out}")

    def show_legend(self) -> None:
        result = self.reschedule_result or self.baseline_result
        schedule = None if result is None else result.schedule
        self.legend_window = OrderLegendWindow(schedule, self)
        self.legend_window.show()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
