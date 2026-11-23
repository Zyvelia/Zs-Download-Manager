import http.server, tempfile, threading
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from neon.engine import HttpWorker
payload=b'completed partial data'; requests=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append(self.headers.get('Range'))
        if self.headers.get('Range'):
            self.send_response(416); self.send_header('Content-Range', f'bytes */{len(payload)}'); self.send_header('ETag', '"same"'); self.end_headers()
        else:
            self.send_response(200); self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def log_message(self,*args): pass
app=QCoreApplication([]); srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler); threading.Thread(target=srv.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as tmp:
    for index, validator in enumerate(('"same"','"old"')):
        path=Path(tmp)/f'{index}.bin'; Path(str(path)+'.part').write_bytes(payload)
        w=HttpWorker(f'http://127.0.0.1:{srv.server_port}/file',tmp); w.path=path; w.validator=validator; w.start(); assert w.wait(10000); assert w.status=='Completed', w.error; assert path.read_bytes()==payload
assert requests == [f'bytes={len(payload)}-', f'bytes={len(payload)}-', None], requests
srv.shutdown(); print('HTTP 416 recovery with matching and changed validators: PASS')
