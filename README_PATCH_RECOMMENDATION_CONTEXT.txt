Patch: context-sensitive recommendation solve

Problem fixed:
Previously, Solve with recommendations used a downtime scenario whenever any
rescheduling result already existed. Because of this, even if the user switched
back to Baseline Plan and clicked Solve with recommendations, the recommended
solve could still include the selected downtime scenario.

New behavior:
- If the active tab is Baseline Plan, recommendation solve uses:
  scenario_name = baseline_no_disruption
  previous_schedule = None
  No downtime is displayed on the Recommended Plan Gantt.

- If the active tab is Rescheduled Plan, recommendation solve uses:
  scenario_name = the scenario stored in the rescheduling result metadata
  previous_schedule = baseline.schedule
  Downtime is displayed only for that rescheduling scenario.

- The solver log now prints the source context, for example:
  Recommendation solve source: baseline plan, scenario=baseline_no_disruption
  Recommendation solve source: rescheduled plan, scenario=press_stop_5min

Files changed:
- desktop_app/main.py
