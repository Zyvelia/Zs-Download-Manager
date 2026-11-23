from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QInputDialog
from neon.ui import MainWindow
app=QApplication([]); w=MainWindow(); w.directory='/tmp'; w.global_down.setValue(123); w.queue_limit.setValue(7); w.organize.setChecked(True)
with patch.object(QInputDialog,'getText',return_value=('Test',True)): w.save_profile()
w.global_down.setValue(0); w.queue_limit.setValue(3); w.organize.setChecked(False)
with patch.object(QInputDialog,'getItem',return_value=('Test',True)): w.apply_profile()
assert w.directory=='/tmp' and w.global_down.value()==123 and w.queue_limit.value()==7 and w.organize.isChecked()
w.history_readonly=True; w.close(); print('Named workflow profile save/apply: PASS')
