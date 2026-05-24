"""Generate a Tarkett-like bundle, solve it, and export result CSVs."""
from pathlib import Path

from tarkett_scheduler import DemoConfig, generate_tarkett_like_demo_bundle, solve_schedule, save_result


def main() -> None:
    bundle_dir = generate_tarkett_like_demo_bundle(DemoConfig(output_dir="generated_demo_data/tarkett_like_demo"))
    print(f"Generated bundle: {bundle_dir}")

    baseline = solve_schedule(bundle_dir, scenario_name="baseline_no_disruption", time_limit_seconds=20)
    out = save_result(baseline, Path("scheduler_outputs") / "baseline")
    print(f"Baseline status: {baseline.status}")
    print(f"Method: {baseline.metadata.get('method')}")
    print(f"KPIs: {baseline.kpis}")
    print(f"Saved baseline outputs: {out}")

    rescheduled = solve_schedule(
        bundle_dir,
        scenario_name="press_downtime_3h",
        previous_schedule=baseline.schedule,
        time_limit_seconds=20,
    )
    out2 = save_result(rescheduled, Path("scheduler_outputs") / "press_downtime_3h")
    print(f"Reschedule status: {rescheduled.status}")
    print(f"Method: {rescheduled.metadata.get('method')}")
    print(f"KPIs: {rescheduled.kpis}")
    print(f"Saved rescheduling outputs: {out2}")


if __name__ == "__main__":
    main()
