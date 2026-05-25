from __future__ import annotations

import os
import sys
import traceback


def _smoke_test() -> None:
    """Run a CI/manual smoke test for the bundled executable.

    In normal application mode we start the PySide6 GUI. In smoke-test mode we
    deliberately avoid importing the GUI and only verify OR-Tools/CP-SAT. The
    explicit os._exit(0) is intentional: with PyInstaller + native OR-Tools DLLs
    on Windows, interpreter shutdown can sometimes propagate a non-zero process
    code after all checks have passed.
    """
    try:
        from scripts.check_ortools import main as check_ortools_main

        check_ortools_main()
        print("Bundled executable smoke test finished successfully.")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


def main() -> None:
    if "--smoke-test" in sys.argv:
        _smoke_test()
        return

    # Import the desktop module explicitly so we can apply the progress-bar
    # patch before MainWindow is instantiated.
    import desktop_app.main as desktop_main
    from desktop_app.solver_progress_patch import apply as apply_progress_patch

    apply_progress_patch(desktop_main)
    desktop_main.main()


if __name__ == "__main__":
    main()
