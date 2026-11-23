import tempfile, threading, urllib.error
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from neon.engine import HttpWorker
app=QCoreApplication([])
with tempfile.TemporaryDirectory() as tmp:
    worker=HttpWorker('http://example.org/test',tmp); entered=threading.Event()
    def request(*args,**kwargs):
        entered.set(); worker.stop_event.wait(3); raise urllib.error.URLError('offline')
    with patch('urllib.request.urlopen',side_effect=request):
        worker.start(); assert entered.wait(2); worker.halt('Canceled'); assert worker.wait(5000)
    assert worker.status=='Canceled',worker.status
    assert not Path(str(worker.path)+'.part').exists()
print('Cancellation wins over a simultaneous network error: PASS')
