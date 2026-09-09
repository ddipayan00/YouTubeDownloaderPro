"""Application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .settings import APP, ORG, Settings
from .ui.main_window import MainWindow


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )


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

    window = MainWindow(Settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
