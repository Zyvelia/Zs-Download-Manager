import sys
from PySide6.QtWidgets import QApplication
from neon.ui import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Nexus Download Manager')
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())
