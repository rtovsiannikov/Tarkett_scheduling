"""Build-time and bundled-app smoke test for the OR-Tools CP-SAT dependency.

This script is intentionally safe to run as:

    python scripts/check_ortools.py

When Python runs a file from the ``scripts`` directory, ``sys.path[0]`` points to
``scripts`` rather than the repository root.  Therefore we explicitly prepend the
repo root before importing the local ``tarkett_scheduler`` package.
"""
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
import shutil
import sys
import traceback

# Make local project imports work when this file is executed as
# ``python scripts/check_ortools.py`` from GitHub Actions / PowerShell.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ortools.sat.python import cp_model

from tarkett_scheduler.demo_data_generator import DemoConfig, generate_tarkett_like_demo_bundle
from tarkett_scheduler.core import solve_schedule


def _solve_tiny_cp_sat_model() -> None:
    model = cp_model.CpModel()
    x = model.NewBoolVar("x")
    model.Maximize(x)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    status = solver.Solve(model)
    print("Tiny CP-SAT status:", solver.StatusName(status), "x=", solver.Value(x))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"Tiny CP-SAT model failed: {solver.StatusName(status)}")
    if solver.Value(x) != 1:
        raise RuntimeError("Tiny CP-SAT model returned an unexpected value")


def _solve_compact_scheduler_model() -> None:
    bundle_dir = PROJECT_ROOT / "generated_demo_data" / "ortools_smoke_bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    # Keep this deliberately small so the CI smoke test verifies the CP-SAT path
    # without turning the build into a performance benchmark.
    generate_tarkett_like_demo_bundle(
        DemoConfig(
            output_dir=str(bundle_dir),
            seed=3,
            days=3,
            customer_orders=3,
            priority_share=0.34,
        )
    )

    result = solve_schedule(
        bundle_dir,
        scenario_name="baseline_no_disruption",
        time_limit_seconds=30,
        auto_generate_mts_orders=False,
    )
    print("Scheduler status:", result.status)
    print("Scheduler method:", result.metadata.get("method"))
    print("Scheduled operations:", len(result.schedule))

    method = str(result.metadata.get("method", ""))
    if method != "CP-SAT":
        raise RuntimeError(f"Expected scheduler to use CP-SAT, got: {method}")
    if result.schedule.empty:
        raise RuntimeError("Scheduler produced an empty schedule")


def main() -> None:
    print("Working directory:", Path.cwd())
    print("Project root:", PROJECT_ROOT)
    print("Python:", sys.version)
    print("ortools:", version("ortools"))
    _solve_tiny_cp_sat_model()
    try:
        _solve_compact_scheduler_model()
    except Exception:
        traceback.print_exc()
        raise
    print("OR-Tools CP-SAT smoke test passed")


if __name__ == "__main__":
    main()
