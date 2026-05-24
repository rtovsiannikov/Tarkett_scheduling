"""Collect protobuf modules used by OR-Tools generated *_pb2 modules."""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("google.protobuf")
