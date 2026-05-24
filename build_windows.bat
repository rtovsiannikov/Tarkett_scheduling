@echo off
setlocal enabledelayedexpansion
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [WARNING] Recommended build interpreter is Python 3.11 x64.
  echo [WARNING] OR-Tools wheels are version-sensitive; use GitHub Actions or Python 3.11 if pip install fails.
)
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python scripts\check_ortools.py
pyinstaller FactoryScheduler.spec --clean --noconfirm
