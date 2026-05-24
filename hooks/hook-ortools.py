"""PyInstaller hook for Google OR-Tools."""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hiddenimports = collect_submodules("ortools")
binaries = collect_dynamic_libs("ortools")
datas = collect_data_files("ortools")
