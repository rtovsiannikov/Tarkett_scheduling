from __future__ import annotations

import sys


def _smoke_test() -> None:
    from scripts.check_ortools import main as check_ortools_main

    check_ortools_main()


def main() -> None:
    if "--smoke-test" in sys.argv:
        _smoke_test()
        return
    from desktop_app.main import main as app_main

    app_main()


if __name__ == "__main__":
    main()
