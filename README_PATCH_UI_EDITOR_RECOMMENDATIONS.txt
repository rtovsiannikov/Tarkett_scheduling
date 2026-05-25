Patch: editable desktop UI, long solver limits, recommendation solve, graph controls and rescheduling stability penalties.

Replace these files in the repository root:
- desktop_app/main.py
- desktop_app/dataframe_model.py
- desktop_app/gantt_widget.py
- tarkett_scheduler/core.py

Main additions:
1. Data editor tab with editable CSV tables for orders, products, work centers, routes, shifts, inventory, arrivals, BOM, stock policy, forecast demand, scenarios, downtime events and setup matrix.
2. Save edited tables to CSV, add row, delete selected rows.
3. Solver time limit is now user-controlled: default 600 s, maximum 604800 s, and 0 means no explicit CP-SAT time limit.
4. Scenario combobox + scenario details panel showing what the selected downtime scenario does.
5. Solve with recommendations: guided solve protects customer OTIF more strongly and pushes MTS stock orders into slack capacity.
6. Rescheduling stability penalties exposed in UI: start-shift penalty, moved-operation penalty, Press sequence inversion penalty.
7. Gantt controls: color by order/product/family/type/priority; show/hide labels, deadlines, setup, downtime, priority MTO, customer MTO, stock/MTS; machine filter.
8. Gantt x-axis uses real dates/times instead of hours from start.
9. KPI cards are stored per result view: Baseline Plan, Rescheduled Plan and Recommended Plan update independently when clicked.
