Patch: baseline Gantt no longer displays downtime events

Files changed:
- desktop_app/main.py

Bug fixed:
The Data editor can contain multiple downtime_events.csv rows for what-if scenarios.
Previous UI code passed the entire downtime_events table to every Gantt chart, so the Baseline Plan tab displayed red downtime overlays even when the solver ran scenario_name=baseline_no_disruption.

New behavior:
- Baseline Plan: never displays downtime overlays.
- Rescheduled Plan: displays only downtime rows matching the solved scenario_name.
- Recommended Plan: displays downtime only when that solve was run for a downtime scenario; otherwise clean baseline recommendation has no downtime overlay.

This patch does not change the solver, GitHub Actions, PyInstaller, or OR-Tools dependencies.
