from PySide6.QtWidgets import QApplication
from neon.ui import MainWindow, TransferCard
from neon.engine import HttpWorker
app=QApplication([]); w=MainWindow(); w.retry_limit.setValue(1)
worker=HttpWorker('https://example.org/a','/tmp',w.http_limiter); c=TransferCard(w,worker,worker.snapshot()); w.add_card(c)
for state in ('Connecting','Waiting for network','Connecting','Waiting for network'):
    worker.status=state; worker.error='temporary failure'; d=worker.snapshot(); c.update_data(d); w.transfer_changed(c,d)
assert worker.status=='Failed' and 'Retry limit reached' in c.data['error'] and c.retry_attempts==2
w.history_readonly=True; w.close(); print('Retry backoff and limit UI state: PASS')
