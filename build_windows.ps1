$ErrorActionPreference = "Stop"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python scripts/check_ortools.py
python -m tarkett_scheduler.demo_data_generator
python -m PyInstaller FactoryScheduler.spec --clean --noconfirm
& "dist/TarkettFlowScheduler/TarkettFlowScheduler.exe" --smoke-test
if ($LASTEXITCODE -ne 0) { throw "Bundled executable failed OR-Tools smoke test" }
