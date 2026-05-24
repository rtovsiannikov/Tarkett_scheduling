"""PyInstaller hook for Google OR-Tools."""

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

datas, binaries, hiddenimports = collect_all("ortools")
binaries += collect_dynamic_libs("ortools")
