# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# OR-Tools uses generated protobuf modules and compiled solver extensions.  The
# custom hooks in ./hooks are used first; the lists below are a defensive fallback
# for CI/local builds where hook discovery behaves differently.
ortools_hidden = collect_submodules("ortools")
protobuf_hidden = collect_submodules("google.protobuf")
absl_hidden = collect_submodules("absl")
matplotlib_hidden = [
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
]

hiddenimports = sorted(set(
    ortools_hidden
    + protobuf_hidden
    + absl_hidden
    + matplotlib_hidden
    + [
        "ortools.sat.python.cp_model",
        "ortools.sat.python.cp_model_helper",
        "ortools.sat.cp_model_pb2",
    ]
))

binaries = collect_dynamic_libs("ortools")
datas = (
    [("generated_demo_data", "generated_demo_data")]
    + collect_data_files("ortools")
    + collect_data_files("matplotlib")
)


a = Analysis(
    ["run_desktop_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],
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
