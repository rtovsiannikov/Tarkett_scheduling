from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


class KpiCard(QFrame):
    def __init__(self, title: str, value: str = "—", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("KpiCard")
        self.setMinimumHeight(88)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #64748b; font-weight: 700;")
        self.value_label = QLabel(value)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.value_label.setFont(font)
        self.value_label.setStyleSheet("color: #0f172a;")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setStyleSheet("color: #475569;")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_content(self, value: Any, subtitle: str = "") -> None:
        self.value_label.setText(_format_value(value))
        self.subtitle_label.setText(subtitle)


def _format_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if 0 <= value <= 1:
            return f"{value * 100:.1f}%"
        return f"{value:.2f}"
    return str(value)


class KpiPanel(QWidget):
    """Compact KPI card panel similar to the original MVP layout."""

    def __init__(self) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.cards: Dict[str, KpiCard] = {
            "otif_rate_customer": KpiCard("Customer OTIF", "—", "MTO + priority orders"),
            "late_orders": KpiCard("Late orders", "—", "orders missing due date"),
            "batches_total": KpiCard("Batches", "—", "split production lots"),
            "press_utilization_proxy": KpiCard("Press utilization", "—", "bottleneck load proxy"),
            "kanban_violations": KpiCard("Kanban alerts", "—", "underflow / overflow"),
            "finished_goods_stockout_events": KpiCard("FG stock alerts", "—", "below safety stock"),
        }
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)

    def set_kpis(self, kpis: Dict[str, Any] | None) -> None:
        kpis = kpis or {}
        subtitles = {
            "otif_rate_customer": "MTO + priority customer orders",
            "late_orders": f"tardiness: {kpis.get('total_tardiness_minutes', 0)} min",
            "batches_total": f"avg/order: {kpis.get('avg_batches_per_order', '—')}",
            "press_utilization_proxy": "Press is the planning drum",
            "kanban_violations": "WIP buffer diagnostics",
            "finished_goods_stockout_events": "MTS warehouse diagnostics",
        }
        for key, card in self.cards.items():
            card.set_content(kpis.get(key), subtitles.get(key, ""))
