"""EmailCenter desktop entry point."""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="EmailCenter Desktop")
    parser.add_argument("--project", help="Bestehenden Projektordner beim Start öffnen")
    parser.add_argument('--self-check', metavar='REPORT_JSON', help='Lokale Laufzeitprüfung ohne Versand')
    options = parser.parse_args(argv)
    if options.self_check:
        from .release_check import check
        return check(options.self_check)
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 fehlt. Installieren mit: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    from .ui.main_window import MainWindow
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("EmailCenter")
    application.setOrganizationName("EmailCenter")
    window = MainWindow()
    window.show()
    if options.project:
        window.controller.submit("open_project", {"path": options.project})
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
