Patch: recommendation actions, bottleneck overtime, Gantt hover cards, moved-operation highlighting, KPI comparison.

Changed files:
- tarkett_scheduler/core.py
- desktop_app/main.py
- desktop_app/gantt_widget.py

What is added:
1. Recommendation rows now include action columns:
   action_type, work_center_id, extra_minutes, reference_time, action_parameters, is_actionable.
2. The recommendation engine detects the current bottleneck and creates an actionable recommendation to extend its working shift.
3. Solve with recommendations now passes selected/actionable recommendation rows into the solver.
   If a recommendation row is selected in the Recommendations table, only selected actionable rows are applied.
   If nothing is selected, all actionable recommendations from the active source result are applied.
4. EXTEND_BOTTLENECK_SHIFT is applied as a temporary shift extension before building the optimization model.
5. Recommendation mode still boosts customer MTO weights and weakens MTS lateness.
6. Gantt hover card shows order, batch, product, demand type, machine, stage, quantity, start/end, due date, duration and setup.
7. Rescheduled/recommended operations moved relative to baseline are highlighted with red outlines and small red markers.
8. A KPI comparison tab shows Baseline, Rescheduled, Recommended and deltas.

Upload through GitHub Add file -> Upload files and replace the matching files.
