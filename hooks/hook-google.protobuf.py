"""PyInstaller hook for protobuf modules used by OR-Tools."""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("google.protobuf")
