# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path.cwd().resolve()

datas = []
binaries = []
hiddenimports = [
    "tarkett_scheduler",
    "tarkett_scheduler.core",
    "tarkett_scheduler.demo_data_generator",
    "desktop_app.main",
    "desktop_app.dataframe_model",
    "desktop_app.gantt_widget",
    "desktop_app.inventory_widget",
    "desktop_app.kpi_cards",
    "desktop_app.legend_window",
    "scripts.check_ortools",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

# Include generated demo data when it exists. The workflow runs the generator
# before PyInstaller, so the desktop app opens with a ready-to-load demo bundle.
for folder_name in ["generated_demo_data"]:
    folder = project_root / folder_name
    if folder.exists():
        datas.append((str(folder), folder_name))

for file_name in ["README.md", "requirements.txt"]:
    file_path = project_root / file_name
    if file_path.exists():
        datas.append((str(file_path), "."))

# This mirrors the approach that worked in the previous optimal_scheduling
# desktop build: collect_all is more reliable for native-wheel packages than
# trying to manually list DLLs, generated protobuf files and Qt plugins.
for package_name in ["ortools", "google.protobuf", "absl", "matplotlib", "PySide6", "pandas", "numpy"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports
    hiddenimports += collect_submodules(package_name)

hiddenimports = sorted(set(hiddenimports))

a = Analysis(
    ["run_desktop_app.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"] if (project_root / "hooks").exists() else [],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["notebook", "jupyter", "IPython", "pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TarkettFlowScheduler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TarkettFlowScheduler",
    contents_directory=".",
)
