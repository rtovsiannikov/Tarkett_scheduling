# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

ROOT = Path.cwd()

# OR-Tools contains generated protobuf modules and native compiled extensions.
# collect_all() is more reliable on Windows than only collect_dynamic_libs().
ortools_datas, ortools_binaries, ortools_hidden = collect_all("ortools")
protobuf_hidden = collect_submodules("google.protobuf")
absl_hidden = collect_submodules("absl")
matplotlib_hidden = [
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
]
project_hidden = [
    "scripts.check_ortools",
    "tarkett_scheduler.core",
    "tarkett_scheduler.demo_data_generator",
    "desktop_app.main",
]

hiddenimports = sorted(set(
    ortools_hidden
    + protobuf_hidden
    + absl_hidden
    + matplotlib_hidden
    + project_hidden
    + [
        "ortools.sat.python.cp_model",
        "ortools.sat.python.cp_model_helper",
        "ortools.sat.cp_model_pb2",
    ]
))

binaries = list(ortools_binaries) + collect_dynamic_libs("ortools")

datas = list(ortools_datas) + collect_data_files("matplotlib")
if (ROOT / "generated_demo_data").exists():
    datas.append((str(ROOT / "generated_demo_data"), "generated_demo_data"))


a = Analysis(
    ["run_desktop_app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "notebook"],
    noarchive=False,
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TarkettFlowScheduler",
)
