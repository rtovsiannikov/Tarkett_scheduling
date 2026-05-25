Patch: stop UI freezes when switching Baseline / Rescheduled / Recommended tabs

Changed file:
- desktop_app/main.py

Cause:
The previous UI called _show_result() on every tab switch. That method reset all
shared result tables and redrew all three Matplotlib Gantt charts. Matplotlib
redraws synchronously in the Qt GUI thread, so normal tab switching could make
Windows show "Not responding".

Fix:
- cache per-result Gantt render signatures;
- redraw only the currently visible Gantt chart;
- do not redraw baseline/reschedule/recommendation charts on every tab switch;
- block recursive tab-change handling after a solver finishes;
- update KPI cards for the selected result without forcing full chart redraw;
- keep graph toolbar behavior, but make hidden tabs redraw lazily when opened.

This patch does not modify OR-Tools, PyInstaller, GitHub Actions, requirements,
or the solver core.
