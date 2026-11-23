import os
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from neon.ui import MainWindow, TransferCard
from neon.engine import HttpWorker
from neon.history import History

app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    record = Path(tmp) / 'history.json'
    w = MainWindow(); w.history = History(record)
    f = Path(tmp) / 'completed.bin'; f.write_bytes(b'hello')
    worker = HttpWorker('https://example.org/completed.bin', tmp, w.http_limiter)
    worker.path = f; worker.status = 'Completed'; worker.offset = worker.total = 5
    card = TransferCard(w, worker, worker.snapshot()); w.bind_worker(card); w.add_card(card)
    w.save_history(); w.history = History(Path(tmp) / "other.json"); w.close()
    w2 = MainWindow(); w2.history = History(record); w2.restore_history()
    assert len(w2.cards) == 1 and w2.cards[0].data['status'] == 'Completed'
    assert Path(w2.cards[0].data['path']).read_bytes() == b'hello'
    w2.remove_card(w2.cards[0]); assert f.exists(), 'Remove must preserve the file'
    w2.close(); assert History(record).load() == []
print('History save/restore and remove preserving file: PASS')
