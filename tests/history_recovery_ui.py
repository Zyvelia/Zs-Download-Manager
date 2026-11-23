import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from neon.history import History
from neon.ui import MainWindow
app=QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    history=History(Path(tmp)/'history.json')
    history.save([]); history.save([]); history.path.write_text('{broken',encoding='utf-8')
    with patch('neon.ui.History',return_value=history), patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
        w=MainWindow()
    assert not w.history_readonly
    w.save_history(); assert history.load()==[] and history.load_backup()==[]
    w.close()
print('Corrupt history recovery requires confirmation and restores backup: PASS')
