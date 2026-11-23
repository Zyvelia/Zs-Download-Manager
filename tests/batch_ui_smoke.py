import time
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from neon.ui import MainWindow
app=QApplication([]); w=MainWindow(); w.directory='/tmp'; w.pump_queue=lambda: None
text='https://example.org/a\nhttps://example.org/a\nhttps://example.org/b\nfile:///bad'
with patch.object(QInputDialog,'getItem',return_value=('Paste links',True)), patch.object(QInputDialog,'getMultiLineText',return_value=(text,True)), patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
    w.batch_links()
    deadline=time.monotonic()+5
    while getattr(w,'batch_active',False) and time.monotonic()<deadline: app.processEvents(); time.sleep(.01)
assert not w.batch_active and len(w.cards)==2, len(w.cards)
assert {c.obj.url for c in w.cards}=={'https://example.org/a','https://example.org/b'}
w.history_readonly=True; w.close(); print('Batch preview and incremental insertion: PASS')
