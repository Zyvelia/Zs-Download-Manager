"""Exercise restoring a partial HTTP download against a range-capable local server."""
import http.server
import tempfile
import threading
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from neon.engine import HttpWorker
from neon.ui import MainWindow, TransferCard
from neon.history import History

payload = bytes(range(256)) * 1024
ranges = []
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        start = int(self.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
        ranges.append(start)
        self.send_response(206 if start else 200)
        self.send_header('Content-Length', str(len(payload)-start))
        self.send_header('ETag', '"test"')
        if start: self.send_header('Content-Range', f'bytes {start}-{len(payload)-1}/{len(payload)}')
        self.end_headers(); self.wfile.write(payload[start:])
    def log_message(self, *args): pass

app=QApplication([]); server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)/'file.bin'; partial = Path(str(path)+'.part'); partial.write_bytes(payload[:65536])
    history = History(Path(tmp)/'history.json'); url=f'http://127.0.0.1:{server.server_port}/file.bin'
    w=MainWindow(); w.history=history
    worker=HttpWorker(url,tmp,w.http_limiter); worker.path=path; worker.validator='"test"'; worker.offset=65536; worker.total=len(payload); worker.status='Queued'
    card=TransferCard(w,worker,worker.snapshot()); w.bind_worker(card); w.add_card(card); w.save_history()
    w.history=History(Path(tmp)/'other.json'); w.close()
    w2=MainWindow(); w2.history=history; w2.restore_history(); assert len(w2.cards)==1
    worker2=w2.cards[0].obj
    while worker2.isRunning(): app.processEvents(); time.sleep(.01)
    app.processEvents()
    assert worker2.status=='Completed', worker2.error
    assert path.read_bytes()==payload and ranges==[65536], ranges
    w2.close()
server.shutdown()
print('Partial download restored and resumed using validated range: PASS')
