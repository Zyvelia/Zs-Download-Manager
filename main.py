import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from browser_host import validate_url
from neon.ui import MainWindow

def main():
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Z's Download Manager")
    window = MainWindow()
    window.show()
    if len(sys.argv) == 3 and sys.argv[1] == '--browser-url':
        def review_browser_link():
            try: url = validate_url(sys.argv[2])
            except ValueError: return
            box = QMessageBox(window); box.setWindowTitle('Review browser link')
            box.setIcon(QMessageBox.Icon.Question); box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText('A browser extension sent this link. Place it in the download box?')
            box.setDetailedText(url); box.setInformativeText(url)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() == QMessageBox.StandardButton.Yes:
                window.navigate('Downloads'); window.url.setText(url); window.url.setFocus()
        QTimer.singleShot(0, review_browser_link)
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())
