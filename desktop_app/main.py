from __future__ import annotations

from pathlib import Path
import sys
from typing import Dict, Optional

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
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
QPushButton#WarningButton { background: #b45309; }
QLineEdit, QSpinBox, QComboBox {
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


DATA_FILES = {
    "orders": "orders.csv",
    "products": "products.csv",
    "work_centers": "work_centers.csv",
    "routes": "routes.csv",
    "shifts": "shifts.csv",
    "inventory": "inventory.csv",
    "inventory_arrivals": "inventory_arrivals.csv",
    "bom": "bom.csv",
    "stock_policy": "stock_policy.csv",
    "forecast_demand": "forecast_demand.csv",
    "scenarios": "scenarios.csv",
    "downtime_events": "downtime_events.csv",
    "setup_matrix": "setup_matrix.csv",
}


RESULT_TITLES = {
    "baseline": "Baseline plan",
    "reschedule": "Rescheduled plan",
    "recommendation": "Recommended plan",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Tarkett-like Factory Scheduling & Rescheduling Demo")
        self.resize(1580, 940)
        self.setStyleSheet(APP_STYLE)

        self.bundle_dir: Optional[Path] = None
        self.results: Dict[str, object | None] = {"baseline": None, "reschedule": None, "recommendation": None}
        self.active_result_key = "baseline"
        self.legend_window: Optional[OrderLegendWindow] = None
        self.downtime_events = pd.DataFrame()

        self.orders_model = DataFrameModel(editable=True)
        self.products_model = DataFrameModel(editable=True)
        self.work_centers_model = DataFrameModel(editable=True)
        self.routes_model = DataFrameModel(editable=True)
        self.shifts_model = DataFrameModel(editable=True)
        self.inventory_source_model = DataFrameModel(editable=True)
        self.inventory_arrivals_model = DataFrameModel(editable=True)
        self.bom_model = DataFrameModel(editable=True)
        self.stock_policy_model = DataFrameModel(editable=True)
        self.forecast_demand_model = DataFrameModel(editable=True)
        self.scenarios_model = DataFrameModel(editable=True)
        self.downtime_model = DataFrameModel(editable=True)
        self.setup_matrix_model = DataFrameModel(editable=True)
        self.data_models: Dict[str, DataFrameModel] = {
            "orders": self.orders_model,
            "products": self.products_model,
            "work_centers": self.work_centers_model,
            "routes": self.routes_model,
            "shifts": self.shifts_model,
            "inventory": self.inventory_source_model,
            "inventory_arrivals": self.inventory_arrivals_model,
            "bom": self.bom_model,
            "stock_policy": self.stock_policy_model,
            "forecast_demand": self.forecast_demand_model,
            "scenarios": self.scenarios_model,
            "downtime_events": self.downtime_model,
            "setup_matrix": self.setup_matrix_model,
        }

        self.batch_model = DataFrameModel()
        self.schedule_model = DataFrameModel()
        self.order_summary_model = DataFrameModel()
        self.inventory_events_model = DataFrameModel()
        self.recommendations_model = DataFrameModel()

        self.baseline_gantt = GanttWidget()
        self.reschedule_gantt = GanttWidget()
        self.recommendation_gantt = GanttWidget()
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
        save_action = QAction("Save edited CSV bundle", self)
        save_action.triggered.connect(self.save_edited_bundle)
        export_action = QAction("Export latest results", self)
        export_action.triggered.connect(self.export_outputs)
        legend_action = QAction("Show order legend", self)
        legend_action.triggered.connect(self.show_legend)
        self.menuBar().addAction(open_action)
        self.menuBar().addAction(save_action)
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
        splitter.setSizes([370, 1210])
        root_layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(root)
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Generate demo data or load a CSV bundle.")
        self._log("Generate a Tarkett-like bundle, edit CSV tables if needed, then solve the baseline plan.")

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
        subtitle = QLabel("Editable flow-line planning: CSV data → CP-SAT → baseline / reschedule / recommendation plans")
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
        panel.setMinimumWidth(340)
        panel.setMaximumWidth(410)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        data_group = QGroupBox("Data & editor")
        data_layout = QVBoxLayout(data_group)
        self.bundle_path_edit = QLineEdit()
        self.bundle_path_edit.setReadOnly(True)
        self.data_table_selector = QComboBox()
        for key, filename in DATA_FILES.items():
            self.data_table_selector.addItem(filename, key)
        self.data_table_selector.currentIndexChanged.connect(self.select_data_table_from_combo)
        btn_open_editor = QPushButton("Open data editor")
        btn_open_editor.setObjectName("SecondaryButton")
        btn_open_editor.clicked.connect(self.open_data_editor)
        btn_generate = QPushButton("Generate Tarkett-like demo data")
        btn_generate.setObjectName("SuccessButton")
        btn_generate.clicked.connect(self.generate_demo_data)
        btn_load = QPushButton("Load CSV bundle")
        btn_load.setObjectName("SecondaryButton")
        btn_load.clicked.connect(self.load_bundle_dialog)
        btn_save = QPushButton("Save edited tables to CSV")
        btn_save.setObjectName("WarningButton")
        btn_save.clicked.connect(self.save_edited_bundle)
        btn_add_row = QPushButton("Add row to current data table")
        btn_add_row.setObjectName("SecondaryButton")
        btn_add_row.clicked.connect(self.add_row_to_current_data_table)
        btn_delete_rows = QPushButton("Delete selected rows")
        btn_delete_rows.setObjectName("SecondaryButton")
        btn_delete_rows.clicked.connect(self.delete_selected_data_rows)
        data_layout.addWidget(QLabel("Bundle folder"))
        data_layout.addWidget(self.bundle_path_edit)
        data_layout.addWidget(QLabel("Table to edit"))
        data_layout.addWidget(self.data_table_selector)
        data_layout.addWidget(btn_open_editor)
        data_layout.addWidget(btn_generate)
        data_layout.addWidget(btn_load)
        data_layout.addWidget(btn_save)
        data_layout.addWidget(btn_add_row)
        data_layout.addWidget(btn_delete_rows)

        solver_group = QGroupBox("Solver settings")
        solver_layout = QGridLayout(solver_group)
        self.time_limit = QSpinBox()
        self.time_limit.setRange(0, 604800)
        self.time_limit.setValue(600)
        self.time_limit.setSuffix(" s")
        self.time_limit.setToolTip("0 = no explicit CP-SAT time limit. For demos 600 seconds is usually enough.")
        solver_layout.addWidget(QLabel("Time limit"), 0, 0)
        solver_layout.addWidget(self.time_limit, 0, 1)
        hint = QLabel("0 means unlimited; user controls the limit.")
        hint.setStyleSheet("color:#64748b; font-size: 11px;")
        solver_layout.addWidget(hint, 1, 0, 1, 2)

        self.shift_penalty = QSpinBox()
        self.shift_penalty.setRange(0, 10000)
        self.shift_penalty.setValue(3)
        self.moved_penalty = QSpinBox()
        self.moved_penalty.setRange(0, 1000000)
        self.moved_penalty.setValue(1500)
        self.sequence_penalty = QSpinBox()
        self.sequence_penalty.setRange(0, 1000000)
        self.sequence_penalty.setValue(2500)

        self.missed_priority_penalty = QSpinBox()
        self.missed_priority_penalty.setRange(0, 10000000)
        self.missed_priority_penalty.setValue(200000)
        self.missed_customer_penalty = QSpinBox()
        self.missed_customer_penalty.setRange(0, 10000000)
        self.missed_customer_penalty.setValue(80000)
        self.missed_stock_penalty = QSpinBox()
        self.missed_stock_penalty.setRange(0, 10000000)
        self.missed_stock_penalty.setValue(5000)
        self.priority_tardiness_weight = QSpinBox()
        self.priority_tardiness_weight.setRange(0, 1000000)
        self.priority_tardiness_weight.setValue(2000)
        self.customer_tardiness_weight = QSpinBox()
        self.customer_tardiness_weight.setRange(0, 1000000)
        self.customer_tardiness_weight.setValue(450)
        self.stock_tardiness_weight = QSpinBox()
        self.stock_tardiness_weight.setRange(0, 1000000)
        self.stock_tardiness_weight.setValue(80)
        self.makespan_weight = QSpinBox()
        self.makespan_weight.setRange(0, 1000000)
        self.makespan_weight.setValue(1)

        solver_layout.addWidget(QLabel("Shift penalty/min"), 2, 0)
        solver_layout.addWidget(self.shift_penalty, 2, 1)
        solver_layout.addWidget(QLabel("Moved op penalty"), 3, 0)
        solver_layout.addWidget(self.moved_penalty, 3, 1)
        solver_layout.addWidget(QLabel("Press sequence penalty"), 4, 0)
        solver_layout.addWidget(self.sequence_penalty, 4, 1)
        solver_layout.addWidget(QLabel("Missed PRIO MTO"), 5, 0)
        solver_layout.addWidget(self.missed_priority_penalty, 5, 1)
        solver_layout.addWidget(QLabel("Missed customer MTO"), 6, 0)
        solver_layout.addWidget(self.missed_customer_penalty, 6, 1)
        solver_layout.addWidget(QLabel("Missed MTS stock"), 7, 0)
        solver_layout.addWidget(self.missed_stock_penalty, 7, 1)
        solver_layout.addWidget(QLabel("PRIO tardiness/min"), 8, 0)
        solver_layout.addWidget(self.priority_tardiness_weight, 8, 1)
        solver_layout.addWidget(QLabel("Customer tardiness/min"), 9, 0)
        solver_layout.addWidget(self.customer_tardiness_weight, 9, 1)
        solver_layout.addWidget(QLabel("MTS tardiness/min"), 10, 0)
        solver_layout.addWidget(self.stock_tardiness_weight, 10, 1)
        solver_layout.addWidget(QLabel("Makespan weight"), 11, 0)
        solver_layout.addWidget(self.makespan_weight, 11, 1)

        scenario_group = QGroupBox("Downtime / what-if scenario")
        scenario_layout = QVBoxLayout(scenario_group)
        self.scenario_combo = QComboBox()
        self.scenario_combo.currentTextChanged.connect(self.update_scenario_details)
        self.scenario_details = QTextEdit()
        self.scenario_details.setReadOnly(True)
        self.scenario_details.setMinimumHeight(96)
        self.downtime_machine_combo = QComboBox()
        self.downtime_start_edit = QLineEdit()
        self.downtime_start_edit.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self.downtime_duration = QSpinBox()
        self.downtime_duration.setRange(1, 24 * 60)
        self.downtime_duration.setValue(5)
        self.downtime_duration.setSuffix(" min")
        self.downtime_reason_edit = QLineEdit()
        self.downtime_reason_edit.setPlaceholderText("Reason, e.g. short press stop")
        btn_apply_downtime = QPushButton("Apply downtime edit to table")
        btn_apply_downtime.setObjectName("WarningButton")
        btn_apply_downtime.clicked.connect(self.apply_inline_downtime_edit)
        scenario_layout.addWidget(QLabel("Selected scenario"))
        scenario_layout.addWidget(self.scenario_combo)
        scenario_layout.addWidget(self.scenario_details)
        scenario_layout.addWidget(QLabel("Machine"))
        scenario_layout.addWidget(self.downtime_machine_combo)
        scenario_layout.addWidget(QLabel("Start time"))
        scenario_layout.addWidget(self.downtime_start_edit)
        scenario_layout.addWidget(QLabel("Downtime duration"))
        scenario_layout.addWidget(self.downtime_duration)
        scenario_layout.addWidget(QLabel("Reason"))
        scenario_layout.addWidget(self.downtime_reason_edit)
        scenario_layout.addWidget(btn_apply_downtime)
        edit_hint = QLabel("Default demo scenarios are 5-minute stops. Edit here or in Data editor, save, then solve.")
        edit_hint.setWordWrap(True)
        edit_hint.setStyleSheet("color:#64748b; font-size: 11px;")
        scenario_layout.addWidget(edit_hint)

        graph_group = QGroupBox("Gantt display")
        graph_layout = QGridLayout(graph_group)
        self.color_by_combo = QComboBox()
        self.color_by_combo.addItems(["order_id", "product_id", "product_family", "demand_type", "priority"])
        self.color_by_combo.currentTextChanged.connect(self.update_gantt_plots)
        self.show_labels_check = QCheckBox("Labels")
        self.show_labels_check.setChecked(True)
        self.show_due_check = QCheckBox("Deadlines")
        self.show_due_check.setChecked(True)
        self.show_setup_check = QCheckBox("Setup blocks")
        self.show_setup_check.setChecked(True)
        self.show_downtime_check = QCheckBox("Downtime")
        self.show_downtime_check.setChecked(True)
        self.show_priority_check = QCheckBox("Priority MTO")
        self.show_priority_check.setChecked(True)
        self.show_customer_check = QCheckBox("Customer MTO")
        self.show_customer_check.setChecked(True)
        self.show_stock_check = QCheckBox("Stock/MTS")
        self.show_stock_check.setChecked(True)
        for cb in [self.show_labels_check, self.show_due_check, self.show_setup_check, self.show_downtime_check, self.show_priority_check, self.show_customer_check, self.show_stock_check]:
            cb.stateChanged.connect(self.update_gantt_plots)
        self.machine_filter_edit = QLineEdit()
        self.machine_filter_edit.setPlaceholderText("e.g. PRESS,PACK or leave empty")
        self.machine_filter_edit.textChanged.connect(self.update_gantt_plots)
        graph_layout.addWidget(QLabel("Color by"), 0, 0)
        graph_layout.addWidget(self.color_by_combo, 0, 1)
        graph_layout.addWidget(self.show_labels_check, 1, 0)
        graph_layout.addWidget(self.show_due_check, 1, 1)
        graph_layout.addWidget(self.show_setup_check, 2, 0)
        graph_layout.addWidget(self.show_downtime_check, 2, 1)
        graph_layout.addWidget(self.show_priority_check, 3, 0)
        graph_layout.addWidget(self.show_customer_check, 3, 1)
        graph_layout.addWidget(self.show_stock_check, 4, 0)
        graph_layout.addWidget(QLabel("Machine filter"), 5, 0)
        graph_layout.addWidget(self.machine_filter_edit, 5, 1)

        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        self.solve_button = QPushButton("Solve baseline plan")
        self.solve_button.clicked.connect(self.solve_baseline)
        self.reschedule_button = QPushButton("Run selected downtime rescheduling")
        self.reschedule_button.setObjectName("SecondaryButton")
        self.reschedule_button.clicked.connect(self.run_rescheduling)
        self.recommendation_button = QPushButton("Solve with recommendations")
        self.recommendation_button.setObjectName("SuccessButton")
        self.recommendation_button.clicked.connect(self.solve_with_recommendations)
        self.export_button = QPushButton("Export active result")
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
        actions_layout.addWidget(self.recommendation_button)
        actions_layout.addWidget(self.export_button)
        actions_layout.addWidget(self.legend_button)
        actions_layout.addSpacing(6)
        actions_layout.addWidget(self.progress_label)
        actions_layout.addWidget(self.progress_bar)

        layout.addWidget(data_group)
        layout.addWidget(solver_group)
        layout.addWidget(scenario_group)
        layout.addWidget(graph_group)
        layout.addWidget(actions_group)
        layout.addStretch(1)
        return panel

    def _build_graph_toolbar(self) -> QWidget:
        group = QGroupBox("Graph view controls")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 8, 10, 8)

        def add_button(text: str, callback) -> None:
            btn = QPushButton(text)
            btn.setObjectName("SecondaryButton")
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addWidget(QLabel("Color:"))
        add_button("Orders", lambda: self.set_graph_color_by("order_id"))
        add_button("Products", lambda: self.set_graph_color_by("product_id"))
        add_button("Families", lambda: self.set_graph_color_by("product_family"))
        add_button("Demand type", lambda: self.set_graph_color_by("demand_type"))
        add_button("Priority", lambda: self.set_graph_color_by("priority"))
        layout.addSpacing(10)
        add_button("Labels on/off", lambda: self.toggle_graph_checkbox(self.show_labels_check))
        add_button("Deadlines on/off", lambda: self.toggle_graph_checkbox(self.show_due_check))
        add_button("Setup on/off", lambda: self.toggle_graph_checkbox(self.show_setup_check))
        add_button("Downtime on/off", lambda: self.toggle_graph_checkbox(self.show_downtime_check))
        layout.addSpacing(10)
        add_button("All machines", lambda: self.set_machine_filter(""))
        add_button("Press only", lambda: self.set_machine_filter("PRESS"))
        add_button("Pack only", lambda: self.set_machine_filter("PACK"))
        layout.addStretch(1)
        return group

    def _build_main_area(self) -> QWidget:
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.kpi_panel)
        layout.addWidget(self._build_graph_toolbar())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.currentChanged.connect(self.on_main_tab_changed)

        self.batch_table = self._table(self.batch_model)
        self.schedule_table = self._table(self.schedule_model)
        self.order_summary_table = self._table(self.order_summary_model)
        self.inventory_events_table = self._table(self.inventory_events_model)
        self.recommendations_table = self._table(self.recommendations_model)

        self.tabs.addTab(self._wrap_scrollable(self.baseline_gantt), "Baseline Plan")
        self.tabs.addTab(self._wrap_scrollable(self.reschedule_gantt), "Rescheduled Plan")
        self.tabs.addTab(self._wrap_scrollable(self.recommendation_gantt), "Recommended Plan")
        self.tabs.addTab(self.batch_table, "Batch split")
        self.tabs.addTab(self.schedule_table, "Operations table")
        self.tabs.addTab(self.order_summary_table, "Order summary")
        self.tabs.addTab(self._wrap_scrollable(self.inventory_plot), "Inventory chart")
        self.tabs.addTab(self.inventory_events_table, "Inventory events")
        self.tabs.addTab(self.recommendations_table, "Recommendations")
        self.tabs.addTab(self._build_data_editor_tab(), "Data editor")
        self.tabs.addTab(self.kpi_text, "KPI details")
        self.tabs.addTab(self.status_text, "Solver log")
        layout.addWidget(self.tabs, stretch=1)
        return area

    def _build_data_editor_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.data_tabs = QTabWidget()
        self.data_tabs.currentChanged.connect(self.sync_data_selector_from_tabs)
        self.data_tables: Dict[str, QTableView] = {}
        for key, model in self.data_models.items():
            table = self._table(model, editable=True)
            self.data_tables[key] = table
            self.data_tabs.addTab(table, DATA_FILES[key])
        layout.addWidget(self.data_tabs)
        return widget

    def _wrap_scrollable(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _table(self, model: DataFrameModel, *, editable: bool = False) -> QTableView:
        view = QTableView()
        view.setModel(model)
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QAbstractItemView.SelectRows)
        if editable:
            view.setEditTriggers(QAbstractItemView.AllEditTriggers)
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
            self.results = {"baseline": None, "reschedule": None, "recommendation": None}
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
        self.results = {"baseline": None, "reschedule": None, "recommendation": None}
        self._load_preview()
        self._idle("bundle loaded")
        self._log(f"Loaded bundle: {self.bundle_dir}")

    def _load_preview(self) -> None:
        if self.bundle_dir is None:
            return
        try:
            # Data editor must show the raw CSV files, not auto-generated MTS rows.
            # The preview batch split still uses the effective planning bundle with
            # MTS replenishment orders generated from stock_policy.csv.
            raw_bundle = load_data_bundle(self.bundle_dir, auto_generate_mts_orders=False)
            planning_bundle = load_data_bundle(self.bundle_dir, auto_generate_mts_orders=True)
            frames = {
                "orders": raw_bundle.orders,
                "products": raw_bundle.products,
                "work_centers": raw_bundle.work_centers,
                "routes": raw_bundle.routes,
                "shifts": raw_bundle.shifts,
                "inventory": raw_bundle.inventory,
                "inventory_arrivals": raw_bundle.inventory_arrivals,
                "bom": raw_bundle.bom,
                "stock_policy": raw_bundle.stock_policy,
                "forecast_demand": raw_bundle.forecast_demand,
                "scenarios": raw_bundle.scenarios,
                "downtime_events": raw_bundle.downtime_events,
                "setup_matrix": raw_bundle.setup_matrix,
            }
            for key, frame in frames.items():
                self.data_models[key].set_dataframe(frame)
            self.batch_model.set_dataframe(build_batches(planning_bundle))
            self.downtime_events = raw_bundle.downtime_events.copy()
            self._populate_downtime_machine_combo(raw_bundle)
            self._populate_scenarios(raw_bundle)
            for table in list(self.data_tables.values()) + [self.batch_table]:
                table.resizeColumnsToContents()
        except Exception as exc:
            QMessageBox.critical(self, "Load error", str(exc))
            self._log(f"Load error: {exc}")

    def _populate_scenarios(self, bundle) -> None:
        current = self.scenario_combo.currentText() if hasattr(self, "scenario_combo") else ""
        self.scenario_combo.blockSignals(True)
        self.scenario_combo.clear()
        names = []
        if not bundle.scenarios.empty and "scenario_name" in bundle.scenarios.columns:
            names = bundle.scenarios["scenario_name"].dropna().astype(str).tolist()
        if "baseline_no_disruption" not in names:
            names.insert(0, "baseline_no_disruption")
        for name in names:
            self.scenario_combo.addItem(name)
        if current and current in names:
            self.scenario_combo.setCurrentText(current)
        else:
            non_baseline = [n for n in names if n != "baseline_no_disruption"]
            if non_baseline:
                self.scenario_combo.setCurrentText(non_baseline[0])
        self.scenario_combo.blockSignals(False)
        self.update_scenario_details(self.scenario_combo.currentText())

    def update_scenario_details(self, scenario_name: str | None = None) -> None:
        scenario_name = scenario_name or self.scenario_combo.currentText()
        lines = [f"Scenario: {scenario_name}"]
        scenarios = self.scenarios_model.dataframe()
        downtime = self.downtime_model.dataframe()
        if not scenarios.empty and "scenario_name" in scenarios.columns:
            match = scenarios[scenarios["scenario_name"].astype(str) == str(scenario_name)]
            if not match.empty:
                row = match.iloc[0]
                lines.append(f"Description: {row.get('description', '')}")
                lines.append(f"Event start: {row.get('event_start', '')}")
                lines.append(f"Replan time: {row.get('replan_time', '')}")
        if not downtime.empty and "scenario_name" in downtime.columns:
            matches = downtime[downtime["scenario_name"].astype(str) == str(scenario_name)]
            if not matches.empty:
                lines.append("")
                lines.append("Downtime events:")
                for _, row in matches.iterrows():
                    lines.append(
                        f"- {row.get('machine_id', '')}: start={row.get('event_start', '')}, "
                        f"estimated={row.get('estimated_duration_minutes', '')} min, "
                        f"actual={row.get('actual_duration_minutes', '')} min, reason={row.get('reason', '')}"
                    )
        lines.append("")
        lines.append("Edit this here or in Data editor → scenarios.csv / downtime_events.csv.")
        self.scenario_details.setPlainText("\n".join(lines))
        self._sync_inline_downtime_fields(str(scenario_name))

    def save_edited_bundle(self) -> None:
        if self.bundle_dir is None:
            QMessageBox.information(self, "No bundle", "Generate or load a bundle first.")
            return
        try:
            self._save_edited_bundle_to_disk(reload_after=True)
            self._log(f"Saved edited CSV bundle: {self.bundle_dir.resolve()}")
            QMessageBox.information(self, "Saved", "Edited CSV tables were saved. Solve again to use the new data.")
        except Exception as exc:
            QMessageBox.critical(self, "Save error", str(exc))
            self._log(f"Save error: {exc}")

    def _has_modified_data(self) -> bool:
        return any(model.is_modified() for model in self.data_models.values())

    def _save_edited_bundle_to_disk(self, *, reload_after: bool = False) -> None:
        if self.bundle_dir is None:
            return
        for key, filename in DATA_FILES.items():
            df = self.data_models[key].dataframe()
            df.to_csv(self.bundle_dir / filename, index=False)
            self.data_models[key].clear_modified()
        if reload_after:
            self._load_preview()

    def _ensure_edits_saved_before_solve(self) -> None:
        if self.bundle_dir is not None and self._has_modified_data():
            self._save_edited_bundle_to_disk(reload_after=False)
            self._log("Auto-saved edited CSV tables before solving.")

    def open_data_editor(self) -> None:
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Data editor":
                self.tabs.setCurrentIndex(i)
                break
        self.select_data_table_from_combo()

    def select_data_table_from_combo(self) -> None:
        if not hasattr(self, "data_tabs") or not hasattr(self, "data_table_selector"):
            return
        key = self.data_table_selector.currentData()
        keys = list(self.data_models.keys())
        if key in keys:
            self.data_tabs.setCurrentIndex(keys.index(key))

    def sync_data_selector_from_tabs(self, index: int) -> None:
        if not hasattr(self, "data_table_selector"):
            return
        keys = list(self.data_models.keys())
        if 0 <= index < len(keys):
            key = keys[index]
            combo_index = self.data_table_selector.findData(key)
            if combo_index >= 0 and self.data_table_selector.currentIndex() != combo_index:
                self.data_table_selector.blockSignals(True)
                self.data_table_selector.setCurrentIndex(combo_index)
                self.data_table_selector.blockSignals(False)

    def add_row_to_current_data_table(self) -> None:
        key = self._current_data_key()
        if not key:
            QMessageBox.information(self, "Data editor", "Open the Data editor tab and choose a table first.")
            return
        self.data_models[key].insert_blank_row()
        self._log(f"Added blank row to {DATA_FILES[key]}.")

    def delete_selected_data_rows(self) -> None:
        key = self._current_data_key()
        if not key:
            QMessageBox.information(self, "Data editor", "Open the Data editor tab and choose a table first.")
            return
        table = self.data_tables[key]
        rows = [idx.row() for idx in table.selectionModel().selectedRows()]
        self.data_models[key].delete_rows(rows)
        self._log(f"Deleted {len(rows)} selected row(s) from {DATA_FILES[key]}.")

    def _current_data_key(self) -> str:
        if hasattr(self, "data_table_selector"):
            key = self.data_table_selector.currentData()
            if key in self.data_models:
                return str(key)
        if not hasattr(self, "data_tabs"):
            return ""
        idx = self.data_tabs.currentIndex()
        keys = list(self.data_models.keys())
        return keys[idx] if 0 <= idx < len(keys) else ""

    def set_graph_color_by(self, value: str) -> None:
        if hasattr(self, "color_by_combo"):
            self.color_by_combo.setCurrentText(value)
        self.update_gantt_plots()

    def toggle_graph_checkbox(self, checkbox: QCheckBox) -> None:
        checkbox.setChecked(not checkbox.isChecked())
        self.update_gantt_plots()

    def set_machine_filter(self, value: str) -> None:
        if hasattr(self, "machine_filter_edit"):
            self.machine_filter_edit.setText(value)
        self.update_gantt_plots()

    def _selected_disruption_scenario(self) -> str:
        current = self.scenario_combo.currentText().strip() if hasattr(self, "scenario_combo") else ""
        if current and current != "baseline_no_disruption":
            return current
        for i in range(self.scenario_combo.count()):
            text = self.scenario_combo.itemText(i)
            if text and text != "baseline_no_disruption":
                return text
        return current or "baseline_no_disruption"

    def _populate_downtime_machine_combo(self, bundle) -> None:
        if not hasattr(self, "downtime_machine_combo"):
            return
        current = self.downtime_machine_combo.currentText()
        machines: list[str] = []
        if not bundle.work_centers.empty and "work_center_id" in bundle.work_centers.columns:
            machines.extend(bundle.work_centers["work_center_id"].dropna().astype(str).tolist())
        if not bundle.downtime_events.empty and "machine_id" in bundle.downtime_events.columns:
            machines.extend(bundle.downtime_events["machine_id"].dropna().astype(str).tolist())
        machines = list(dict.fromkeys(machines))
        self.downtime_machine_combo.blockSignals(True)
        self.downtime_machine_combo.clear()
        self.downtime_machine_combo.addItems(machines or ["PRESS", "LACK", "PACK"])
        if current and current in machines:
            self.downtime_machine_combo.setCurrentText(current)
        self.downtime_machine_combo.blockSignals(False)

    def _sync_inline_downtime_fields(self, scenario_name: str) -> None:
        if not hasattr(self, "downtime_start_edit"):
            return
        downtime = self.downtime_model.dataframe()
        if downtime.empty or "scenario_name" not in downtime.columns:
            return
        matches = downtime[downtime["scenario_name"].astype(str) == str(scenario_name)]
        if matches.empty:
            return
        row = matches.iloc[0]
        machine = str(row.get("machine_id", "PRESS"))
        if machine and self.downtime_machine_combo.findText(machine) < 0:
            self.downtime_machine_combo.addItem(machine)
        self.downtime_machine_combo.setCurrentText(machine)
        start = pd.to_datetime(row.get("event_start", ""), errors="coerce")
        self.downtime_start_edit.setText("" if pd.isna(start) else start.strftime("%Y-%m-%d %H:%M:%S"))
        raw_duration = row.get("actual_duration_minutes", row.get("estimated_duration_minutes", 5))
        if pd.isna(raw_duration) or int(float(raw_duration)) <= 0:
            raw_duration = row.get("estimated_duration_minutes", 5)
        self.downtime_duration.setValue(max(1, int(float(raw_duration))))
        self.downtime_reason_edit.setText(str(row.get("reason", "")))

    def apply_inline_downtime_edit(self) -> None:
        scenario_name = self.scenario_combo.currentText().strip() or "press_stop_5min"
        start = pd.to_datetime(self.downtime_start_edit.text().strip(), errors="coerce")
        if pd.isna(start):
            QMessageBox.warning(self, "Invalid downtime start", "Use a date/time like 2026-05-27 10:00:00.")
            return
        machine = self.downtime_machine_combo.currentText().strip() or "PRESS"
        duration = int(self.downtime_duration.value())
        reason = self.downtime_reason_edit.text().strip() or "Short machine stop"
        downtime = self.downtime_model.dataframe()
        cols = ["scenario_name", "machine_id", "event_start", "estimated_duration_minutes", "actual_duration_minutes", "reason"]
        if downtime.empty:
            downtime = pd.DataFrame(columns=cols)
        for col in cols:
            if col not in downtime.columns:
                downtime[col] = pd.NA
        mask = downtime["scenario_name"].astype(str) == scenario_name
        row_data = {
            "scenario_name": scenario_name,
            "machine_id": machine,
            "event_start": start,
            "estimated_duration_minutes": duration,
            "actual_duration_minutes": duration,
            "reason": reason,
        }
        if mask.any():
            first_idx = downtime.index[mask][0]
            for col, value in row_data.items():
                downtime.at[first_idx, col] = value
        else:
            downtime = pd.concat([downtime, pd.DataFrame([row_data])], ignore_index=True)
        self.downtime_model.set_dataframe(downtime)
        self.downtime_model.mark_modified(True)

        scenarios = self.scenarios_model.dataframe()
        scenario_cols = ["scenario_name", "description", "event_start", "replan_time"]
        if scenarios.empty:
            scenarios = pd.DataFrame(columns=scenario_cols)
        for col in scenario_cols:
            if col not in scenarios.columns:
                scenarios[col] = pd.NA
        smask = scenarios["scenario_name"].astype(str) == scenario_name
        if smask.any():
            idx = scenarios.index[smask][0]
            scenarios.at[idx, "event_start"] = start
            scenarios.at[idx, "replan_time"] = start
            if not str(scenarios.at[idx, "description"] or "").strip():
                scenarios.at[idx, "description"] = f"{machine} {duration}-minute stop"
        else:
            scenarios = pd.concat([scenarios, pd.DataFrame([{
                "scenario_name": scenario_name,
                "description": f"{machine} {duration}-minute stop",
                "event_start": start,
                "replan_time": start,
            }])], ignore_index=True)
        self.scenarios_model.set_dataframe(scenarios)
        self.scenarios_model.mark_modified(True)
        self._populate_scenarios(type("BundlePreview", (), {"scenarios": scenarios, "downtime_events": downtime})())
        self.scenario_combo.setCurrentText(scenario_name)
        self.update_scenario_details(scenario_name)
        self._log(f"Applied downtime edit: {scenario_name}, {machine}, {duration} min. It will be auto-saved before solving.")

    def _solve_kwargs(self) -> Dict[str, int]:
        return {
            "time_limit_seconds": int(self.time_limit.value()),
            "stability_shift_penalty_per_minute": int(self.shift_penalty.value()),
            "stability_moved_penalty": int(self.moved_penalty.value()),
            "order_sequence_penalty": int(self.sequence_penalty.value()),
            "missed_priority_penalty": int(self.missed_priority_penalty.value()),
            "missed_customer_penalty": int(self.missed_customer_penalty.value()),
            "missed_stock_penalty": int(self.missed_stock_penalty.value()),
            "priority_tardiness_weight": int(self.priority_tardiness_weight.value()),
            "customer_tardiness_weight": int(self.customer_tardiness_weight.value()),
            "stock_tardiness_weight": int(self.stock_tardiness_weight.value()),
            "makespan_weight": int(self.makespan_weight.value()),
        }

    def solve_baseline(self) -> None:
        if self.bundle_dir is None:
            self.generate_demo_data()
        if self.bundle_dir is None:
            return
        try:
            self._ensure_edits_saved_before_solve()
            self._busy("Solving baseline")
            self.results["baseline"] = solve_schedule(
                self.bundle_dir,
                scenario_name="baseline_no_disruption",
                **self._solve_kwargs(),
            )
            self._show_result("baseline")
            self.tabs.setCurrentIndex(0)
            self._idle("baseline solved")
            result = self.results["baseline"]
            self._log(f"Baseline solved: {result.status}; method={result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Solver error", str(exc))
            self._idle("solver failed")
            self._log(f"Solver error: {exc}")

    def run_rescheduling(self) -> None:
        if self.results["baseline"] is None:
            self.solve_baseline()
        if self.bundle_dir is None or self.results["baseline"] is None:
            return
        scenario = self._selected_disruption_scenario()
        try:
            self._ensure_edits_saved_before_solve()
            self._busy("Running rescheduling")
            baseline = self.results["baseline"]
            self.results["reschedule"] = solve_schedule(
                self.bundle_dir,
                scenario_name=scenario,
                previous_schedule=baseline.schedule,
                **self._solve_kwargs(),
            )
            self._show_result("reschedule")
            self.tabs.setCurrentIndex(1)
            self._idle("rescheduling solved")
            result = self.results["reschedule"]
            self._log(f"Rescheduling solved: {result.status}; method={result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Rescheduling error", str(exc))
            self._idle("rescheduling failed")
            self._log(f"Rescheduling error: {exc}")

    def solve_with_recommendations(self) -> None:
        if self.results["baseline"] is None:
            self.solve_baseline()
        if self.bundle_dir is None:
            return
        # If a rescheduling plan exists, recommendations are applied to that what-if scenario.
        # Otherwise they guide the baseline solve by protecting customer OTIF and pushing MTS into slack capacity.
        scenario = "baseline_no_disruption"
        previous = None
        base = self.results.get("reschedule") or self.results.get("baseline")
        if self.results.get("reschedule") is not None:
            scenario = self._selected_disruption_scenario()
            previous = self.results["baseline"].schedule if self.results.get("baseline") is not None else None
        try:
            self._ensure_edits_saved_before_solve()
            self._busy("Solving with recommendations")
            self.results["recommendation"] = solve_schedule(
                self.bundle_dir,
                scenario_name=scenario,
                previous_schedule=previous,
                recommendation_mode=True,
                **self._solve_kwargs(),
            )
            self._show_result("recommendation")
            self.tabs.setCurrentIndex(2)
            self._idle("recommended plan solved")
            result = self.results["recommendation"]
            self._log(f"Recommended solve: {result.status}; method={result.metadata.get('method')}")
        except Exception as exc:
            QMessageBox.critical(self, "Recommendation solver error", str(exc))
            self._idle("recommendation solve failed")
            self._log(f"Recommendation solver error: {exc}")

    def _show_result(self, key: str) -> None:
        result = self.results.get(key)
        if result is None:
            self._set_result_tables(None)
            return
        self.active_result_key = key
        self._set_result_tables(result)
        self.update_gantt_plots()
        self.inventory_plot.plot_inventory(result.inventory_projection, f"Inventory projection — {RESULT_TITLES.get(key, key)}")
        self.kpi_panel.set_kpis(result.kpis)
        self.kpi_text.setPlainText(self._format_kpis(result))
        for table in [self.batch_table, self.schedule_table, self.order_summary_table, self.inventory_events_table, self.recommendations_table]:
            table.resizeColumnsToContents()

    def _set_result_tables(self, result) -> None:
        if result is None:
            for model in [self.batch_model, self.schedule_model, self.order_summary_model, self.inventory_events_model, self.recommendations_model]:
                model.set_dataframe(pd.DataFrame())
            self.kpi_panel.set_kpis({})
            self.kpi_text.setPlainText("")
            return
        self.batch_model.set_dataframe(compute_batch_summary(result.schedule))
        self.schedule_model.set_dataframe(result.schedule)
        self.order_summary_model.set_dataframe(result.order_summary)
        self.inventory_events_model.set_dataframe(result.inventory_projection)
        self.recommendations_model.set_dataframe(result.recommendations)

    def on_main_tab_changed(self, index: int) -> None:
        if index == 0:
            self._show_result("baseline")
        elif index == 1:
            self._show_result("reschedule")
        elif index == 2:
            self._show_result("recommendation")

    def _visible_demand_types(self) -> list[str]:
        types = []
        if self.show_priority_check.isChecked():
            types.append("PRIORITY_CUSTOMER_ORDER")
        if self.show_customer_check.isChecked():
            types.append("CUSTOMER_ORDER")
        if self.show_stock_check.isChecked():
            types.append("STOCK_ORDER")
        return types

    def update_gantt_plots(self) -> None:
        options = {
            "color_by": self.color_by_combo.currentText() if hasattr(self, "color_by_combo") else "order_id",
            "show_labels": getattr(self, "show_labels_check", None).isChecked() if hasattr(self, "show_labels_check") else True,
            "show_due_dates": getattr(self, "show_due_check", None).isChecked() if hasattr(self, "show_due_check") else True,
            "show_setup": getattr(self, "show_setup_check", None).isChecked() if hasattr(self, "show_setup_check") else True,
            "show_downtime": getattr(self, "show_downtime_check", None).isChecked() if hasattr(self, "show_downtime_check") else True,
            "downtime_events": self.downtime_model.dataframe() if hasattr(self, "downtime_model") else self.downtime_events,
            "visible_demand_types": self._visible_demand_types() if hasattr(self, "show_priority_check") else None,
            "machine_filter": self.machine_filter_edit.text() if hasattr(self, "machine_filter_edit") else "",
        }
        for key, widget in [("baseline", self.baseline_gantt), ("reschedule", self.reschedule_gantt), ("recommendation", self.recommendation_gantt)]:
            result = self.results.get(key)
            title = RESULT_TITLES.get(key, key)
            if result is not None:
                scenario = result.metadata.get("scenario_name", "")
                if scenario:
                    title = f"{title}: {scenario}"
                widget.plot_schedule(result.schedule, title, **options)
            else:
                widget.plot_schedule(pd.DataFrame(), title, **options)

    def _format_kpis(self, result) -> str:
        lines = [f"View: {RESULT_TITLES.get(self.active_result_key, self.active_result_key)}", "", "Solver metadata", "---------------"]
        for k, v in result.metadata.items():
            lines.append(f"{k}: {v}")
        lines.extend(["", "Status", "------", f"status: {result.status}", f"objective_value: {result.objective_value}", f"solve_time_seconds: {result.solve_time_seconds:.3f}"])
        lines.extend(["", "KPIs", "----"])
        for k, v in result.kpis.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def export_outputs(self) -> None:
        result = self.results.get(self.active_result_key) or self.results.get("recommendation") or self.results.get("reschedule") or self.results.get("baseline")
        if result is None:
            QMessageBox.information(self, "Nothing to export", "Solve a plan first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        out = save_result(result, folder)
        batch_summary = compute_batch_summary(result.schedule)
        batch_summary.to_csv(Path(out) / "batch_summary.csv", index=False)
        self._log(f"Exported active result ({self.active_result_key}) to: {out}")
        QMessageBox.information(self, "Export complete", f"Saved CSV outputs to:\n{out}")

    def show_legend(self) -> None:
        result = self.results.get(self.active_result_key) or self.results.get("recommendation") or self.results.get("reschedule") or self.results.get("baseline")
        schedule = None if result is None else result.schedule
        color_by = self.color_by_combo.currentText() if hasattr(self, "color_by_combo") else "order_id"
        self.legend_window = OrderLegendWindow(schedule, self, color_by=color_by)
        self.legend_window.show()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
