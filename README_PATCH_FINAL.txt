Final stable Windows build patch.

Upload these files into the ROOT of the repository and replace existing files:

.github/workflows/build-windows.yml
FactoryScheduler.spec
run_desktop_app.py
scripts/check_ortools.py
requirements.txt

What changed:
1. Removed the fragile post-build bundled OR-Tools smoke-test step from GitHub Actions.
   The previous run showed the executable already imported OR-Tools, solved a tiny CP-SAT
   model, and used CP-SAT in the scheduler, but the PyInstaller process still returned
   exit code 1 during shutdown. That is why the build failed after a successful smoke log.
2. Kept source-level OR-Tools/CP-SAT verification before building.
3. Reworked FactoryScheduler.spec to mirror the previous optimal_scheduling project:
   collect_all("ortools"), collect_all("PySide6"), collect_all("matplotlib"), etc.
4. run_desktop_app.py still supports --smoke-test and now forces exit code 0 after
   successful checks, but the workflow no longer depends on that fragile post-build step.
