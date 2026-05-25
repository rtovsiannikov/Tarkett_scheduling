Patch: non-blocking visible solver progress indicator

Why this is needed
------------------
The current desktop app already runs CP-SAT in a QThread, so the window can stay
responsive. However, the progress bar was set to Qt's native indeterminate mode
(range 0..0). In a Windows/PyInstaller build this often looks like a frozen grey
or green bar. Also, OR-Tools CP-SAT does not provide continuous progress events
to the current UI, so there is no real percentage of optimization progress.

What this patch does
--------------------
1. Adds desktop_app/solver_progress_patch.py.
2. Replaces run_desktop_app.py so it applies the patch before creating MainWindow.
3. The progress bar is now driven by a QTimer in the GUI thread:
   - if time limit > 0, it shows elapsed time against the selected limit;
   - if time limit = 0, it shows a bouncing pulse with elapsed seconds.
4. This does not touch OR-Tools, PyInstaller, workflow files, or the scheduler core.

Files to upload
---------------
- run_desktop_app.py
- desktop_app/solver_progress_patch.py

Upload the contents of this archive to the repository root via GitHub
Add file -> Upload files, then rebuild the executable in Actions.
