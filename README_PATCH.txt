Patch v7: fixes GitHub Actions failure at "Verify project uses CP-SAT".
The smoke test now uses a compact generated dataset, so the build verifies that OR-Tools is installed and bundled without turning the CI step into a large scheduling benchmark. The workflow also runs on windows-2022 for a more stable PyInstaller environment.
