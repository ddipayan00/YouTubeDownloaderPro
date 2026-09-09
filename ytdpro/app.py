"""Application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .core.engine import find_ffmpeg
from .settings import APP, ORG, Settings
from .ui.main_window import MainWindow


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )


def run_self_test(app: QApplication) -> int:
    """Build the window, report the environment, and exit without a main loop.

    Used by CI to prove a packaged build actually starts and can see its own
    bundled ffmpeg — a build that merely compiles is not a build that works.
    """
    from . import __version__

    window = MainWindow(Settings())
    ffmpeg = find_ffmpeg()
    print(f"version      : {__version__}")
    print(f"frozen       : {getattr(sys, 'frozen', False)}")
    print(f"qt style     : {app.style().objectName()}")
    print(f"tabs         : {[window.tabs.tabText(i) for i in range(window.tabs.count())]}")
    print(f"ffmpeg       : {ffmpeg or 'NOT FOUND'}")
    if not ffmpeg:
        print("self-test FAILED: no ffmpeg available to this build", file=sys.stderr)
        return 1
    print("self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    configure_logging(verbose="--verbose" in argv)

    app = QApplication(argv)
    app.setApplicationName(APP)
    app.setOrganizationName(ORG)
    # Fusion is the one style available on every platform, so the stylesheet
    # renders identically on Windows, macOS and Linux.
    app.setStyle("Fusion")
    app.setFont(QFont(app.font().family(), 10))

    if "--self-test" in argv:
        return run_self_test(app)

    window = MainWindow(Settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
