from __future__ import annotations

"""Non-invasive GUI progress patch for the desktop scheduler.

The solver runs in a worker QThread, but OR-Tools CP-SAT does not expose
continuous progress events to the current GUI. The old UI put QProgressBar
into the native indeterminate mode (range 0..0); in the Windows/PyInstaller
build this often appears frozen. This module monkey-patches MainWindow so the
bar is driven by a QTimer in the Qt main thread.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def _ensure_timer(window) -> QTimer:
    timer = getattr(window, "_solver_progress_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setInterval(250)
        timer.timeout.connect(lambda: _tick_progress(window))
        window._solver_progress_timer = timer
    return timer


def _tick_progress(window) -> None:
    bar = getattr(window, "progress_bar", None)
    label = getattr(window, "progress_label", None)
    if bar is None:
        return

    # Elapsed-time progress is a UI indicator, not a CP-SAT optimality progress
    # metric. It keeps the app visibly alive while the C++ solver searches.
    elapsed = float(getattr(window, "_solver_elapsed_seconds", 0.0)) + 0.25
    window._solver_elapsed_seconds = elapsed
    message = str(getattr(window, "_solver_progress_message", "Solving"))

    try:
        limit = int(window.time_limit.value()) if hasattr(window, "time_limit") else 0
    except Exception:
        limit = 0

    if limit > 0:
        value = max(1, min(99, int(elapsed * 100.0 / float(limit))))
        bar.setRange(0, 100)
        bar.setValue(value)
        bar.setFormat(f"{message}: {int(elapsed)}s / {limit}s")
        if label is not None:
            label.setText(f"{message} — elapsed {int(elapsed)}s of {limit}s")
    else:
        # Unlimited solve: use a deterministic bouncing pulse.
        value = int(getattr(window, "_solver_pulse_value", 0))
        direction = int(getattr(window, "_solver_pulse_direction", 1))
        value += direction * 4
        if value >= 99:
            value = 99
            direction = -1
        elif value <= 1:
            value = 1
            direction = 1
        window._solver_pulse_value = value
        window._solver_pulse_direction = direction
        bar.setRange(0, 100)
        bar.setValue(value)
        bar.setFormat(f"{message}: {int(elapsed)}s")
        if label is not None:
            label.setText(f"{message} — elapsed {int(elapsed)}s")


def apply(main_module) -> None:
    """Patch desktop_app.main.MainWindow without rewriting the whole file."""

    MainWindow = main_module.MainWindow

    def patched_busy(self, message: str) -> None:
        self._solver_progress_message = str(message)
        self._solver_elapsed_seconds = 0.0
        self._solver_pulse_value = 1
        self._solver_pulse_direction = 1

        self.progress_label.setText(str(message))
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(1)
        self.progress_bar.setFormat("starting")
        self.status_label.setText(f"Status: {message}")
        self.statusBar().showMessage(str(message))

        timer = _ensure_timer(self)
        if not timer.isActive():
            timer.start()
        QApplication.processEvents()

    def patched_idle(self, message: str) -> None:
        timer = getattr(self, "_solver_progress_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("done")
        self.progress_label.setText(str(message))
        self.status_label.setText(f"Status: {message}")
        self.statusBar().showMessage(str(message))
        QApplication.processEvents()

    MainWindow._busy = patched_busy
    MainWindow._idle = patched_idle
