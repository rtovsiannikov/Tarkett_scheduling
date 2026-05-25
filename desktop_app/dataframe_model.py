from __future__ import annotations

from typing import Any

import pandas as pd

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal


class DataFrameModel(QAbstractTableModel):
    """Qt model for displaying and editing pandas DataFrames.

    The first versions of this demo only displayed CSV tables. For a customer
    demo this is too limiting: users should be able to edit orders, capacities,
    stock, scenarios and downtime directly in the app, then save the CSV bundle.
    """

    modifiedChanged = Signal(bool)

    def __init__(self, data: pd.DataFrame | None = None, *, editable: bool = False):
        super().__init__()
        self._data = data.copy() if data is not None else pd.DataFrame()
        self._editable = editable
        self._modified = False

    def set_editable(self, editable: bool) -> None:
        self._editable = bool(editable)

    def is_modified(self) -> bool:
        return self._modified

    def clear_modified(self) -> None:
        if self._modified:
            self._modified = False
            self.modifiedChanged.emit(False)

    def dataframe(self) -> pd.DataFrame:
        return self._data.copy()

    def set_dataframe(self, data: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._data = data.copy() if data is not None else pd.DataFrame()
        self._modified = False
        self.endResetModel()
        self.modifiedChanged.emit(False)

    def mark_modified(self, modified: bool = True) -> None:
        if self._modified != bool(modified):
            self._modified = bool(modified)
            self.modifiedChanged.emit(self._modified)

    def insert_blank_row(self) -> None:
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        if self._data.empty and len(self._data.columns) == 0:
            self._data = pd.DataFrame({"new_column": [pd.NA]})
        else:
            self._data.loc[len(self._data)] = [pd.NA for _ in self._data.columns]
        self.endInsertRows()
        self.mark_modified(True)

    def delete_rows(self, rows: list[int]) -> None:
        rows = sorted({int(r) for r in rows if 0 <= int(r) < len(self._data)}, reverse=True)
        if not rows:
            return
        self.beginResetModel()
        self._data = self._data.drop(self._data.index[rows]).reset_index(drop=True)
        self.endResetModel()
        self.mark_modified(True)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._data.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self._data.iloc[index.row(), index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole):
            if pd.isna(value):
                return ""
            if hasattr(value, "strftime"):
                return value.strftime("%Y-%m-%d %H:%M:%S")
            return str(value)
        if role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | Qt.AlignLeft
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if not self._editable or role != Qt.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        old_value = self._data.iat[row, col]
        text = "" if value is None else str(value).strip()
        column = str(self._data.columns[col])
        parsed: Any = text
        if text == "":
            parsed = pd.NA
        else:
            old_series = self._data[column]
            lower = text.lower()
            if pd.api.types.is_bool_dtype(old_series):
                parsed = lower in {"true", "1", "yes", "y", "так", "да"}
            elif pd.api.types.is_integer_dtype(old_series):
                try:
                    parsed = int(float(text.replace(",", ".")))
                except ValueError:
                    parsed = text
            elif pd.api.types.is_float_dtype(old_series):
                try:
                    parsed = float(text.replace(",", "."))
                except ValueError:
                    parsed = text
            elif "date" in column.lower() or "time" in column.lower() or column.lower().endswith("_start") or column.lower().endswith("_end"):
                parsed_dt = pd.to_datetime(text, errors="coerce")
                parsed = text if pd.isna(parsed_dt) else parsed_dt
        if str(old_value) == str(parsed):
            return True
        self._data.iat[row, col] = parsed
        self._modified = True
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        self.modifiedChanged.emit(True)
        return True

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and self._editable:
            flags |= Qt.ItemIsEditable
        return flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._data.columns):
                return str(self._data.columns[section])
            return ""
        return str(section + 1)
