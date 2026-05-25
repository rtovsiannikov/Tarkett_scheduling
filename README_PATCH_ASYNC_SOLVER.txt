Patch: keep the PySide6 desktop UI responsive while CP-SAT is solving.

Changed file:
- desktop_app/main.py

What changed:
- Long solve calls are now executed in a QThread worker, not in the Qt main GUI thread.
- The main window remains repaintable/clickable while OR-Tools searches.
- Solver buttons are disabled during an active solve to avoid starting overlapping jobs.
- The progress bar stays in indeterminate mode until the worker returns.
- Baseline is now required before rescheduling/recommendation solves, because those modes need the baseline schedule for movement penalties.

Why this is needed:
- Windows marks a Qt app as "Not responding" whenever the GUI event loop is blocked for several seconds.
- CP-SAT can run for 600 seconds or more, so it must not run directly inside the button click handler.

Upload this patch by replacing desktop_app/main.py in the repository.
