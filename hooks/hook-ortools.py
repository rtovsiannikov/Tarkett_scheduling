"""PyInstaller hook for Google OR-Tools.

OR-Tools ships compiled extension modules and solver runtime libraries.  A plain
PyInstaller analysis can miss some of them because parts of OR-Tools are loaded
lazily.  This hook explicitly collects OR-Tools submodules, package data and
native dynamic libraries so the bundled desktop app can use CP-SAT instead of
falling back to the greedy scheduler.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hiddenimports = collect_submodules("ortools")
datas = collect_data_files("ortools")
binaries = collect_dynamic_libs("ortools")
