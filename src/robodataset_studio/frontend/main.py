from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from robodataset_studio.frontend.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1280, 860)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
