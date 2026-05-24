"""Build-time and bundled-app smoke test for the CP-SAT dependency."""
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
import shutil
import sys

from ortools.sat.python import cp_model

from tarkett_scheduler.demo_data_generator import DemoConfig, generate_tarkett_like_demo_bundle
from tarkett_scheduler.core import solve_schedule


def _solve_tiny_model() -> None:
    model = cp_model.CpModel()
    x = model.NewBoolVar("x")
    model.Maximize(x)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"Tiny CP-SAT smoke model failed: {solver.StatusName(status)}")
    if solver.Value(x) != 1:
        raise RuntimeError("Tiny CP-SAT smoke model returned an unexpected result")


def _solve_demo_model() -> None:
    bundle_dir = Path("generated_demo_data") / "ortools_smoke_bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    generate_tarkett_like_demo_bundle(DemoConfig(output_dir=str(bundle_dir)))
    result = solve_schedule(bundle_dir, scenario_name="baseline_no_disruption", time_limit_seconds=10)
    method = str(result.metadata.get("method", ""))
    if method != "CP-SAT":
        raise RuntimeError(f"Expected CP-SAT method, got: {method}")
    if result.schedule.empty:
        raise RuntimeError("Demo schedule is empty")


def main() -> None:
    print(f"Python: {sys.version}")
    print(f"ortools: {version('ortools')}")
    _solve_tiny_model()
    _solve_demo_model()
    print("OR-Tools CP-SAT smoke test passed")


if __name__ == "__main__":
    main()
