"""Entry point for the STM32 BLDC commutation desktop monitor."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui import MainWindow
from ui.theme import DARK_STYLESHEET


def main() -> int:
    """Create the Qt application, apply the theme, and start the event loop."""

    app = QApplication(sys.argv)
    app.setApplicationName("STM32 BLDC Commutation Monitor")
    app.setOrganizationName("BLDC Tools")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
