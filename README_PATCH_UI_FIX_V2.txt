Patch: UI/data editor/Gantt/downtime/objective weights

Changed files:
- desktop_app/main.py
- desktop_app/gantt_widget.py
- desktop_app/legend_window.py
- desktop_app/dataframe_model.py
- tarkett_scheduler/core.py
- tarkett_scheduler/demo_data_generator.py
- generated_demo_data/tarkett_like_demo/downtime_events.csv
- generated_demo_data/tarkett_like_demo/scenarios.csv
- run_demo.py

What this fixes/adds:
1. Data editing now has an explicit table selector and Open data editor button.
   Add/Delete row works on the selected table, not only when the Data editor tab is already active.
2. Edited CSV tables are auto-saved before baseline/rescheduling/recommendation solve.
   This fixes the issue where UI edits looked accepted but the solver still read old CSV files.
3. Gantt controls are now available directly above the graph tabs:
   color by order/product/family/demand type/priority, labels, deadlines, setup, downtime, all machines, Press only, Pack only.
4. Legend window now shows the exact same colors as the current Gantt color mode.
5. X-axis uses real date/time labels in YYYY-MM-DD HH:MM style.
6. Downtime scenarios can be edited directly in the sidebar.
   The demo generator now creates 5-minute stops instead of 3-hour events.
7. Solver weights exposed in UI:
   missed PRIO MTO, missed customer MTO, missed MTS stock, tardiness weights, makespan, shift penalty, moved operation penalty, Press sequence penalty.
8. Core solver accepts those weights and records them in metadata/KPI details.

Upload the archive contents to the root of the GitHub repository via Add file -> Upload files.
