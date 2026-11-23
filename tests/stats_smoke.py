from PySide6.QtWidgets import QApplication
from neon.ui import MainWindow, TransferCard
from neon.engine import HttpWorker
app=QApplication([]); w=MainWindow(); w.statistics={k:0 for k in w.statistics}
worker=HttpWorker('https://example.org/file','/tmp',w.http_limiter)
card=TransferCard(w,worker,worker.snapshot()); w.bind_worker(card); w.add_card(card)
for status,done in [('Downloading',100),('Completed',200),('Completed',200)]:
    data=worker.snapshot(); data.update(status=status,done=done,total=200); card.update_data(data); w.transfer_changed(card,data)
assert w.statistics['downloaded']==200 and w.statistics['completed']==1, w.statistics
w.remove_card(card); assert w.statistics['completed']==1
w.close(); print('Cumulative statistics and duplicate completion: PASS')
