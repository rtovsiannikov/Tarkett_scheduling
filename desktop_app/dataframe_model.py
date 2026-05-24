from __future__ import annotations

import pandas as pd

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataFrameModel(QAbstractTableModel):
    """Small Qt model for displaying pandas DataFrames."""

    def __init__(self, data: pd.DataFrame | None = None):
        super().__init__()
        self._data = data.copy() if data is not None else pd.DataFrame()

    def set_dataframe(self, data: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._data = data.copy() if data is not None else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._data.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        value = self._data.iloc[index.row(), index.column()]
        if pd.isna(value):
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M")
        return str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._data.columns):
                return str(self._data.columns[section])
            return ""
        return str(section + 1)
