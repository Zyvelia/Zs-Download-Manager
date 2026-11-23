"""Local HTTP checks for checksum quarantine and rate limiting."""
import functools
import hashlib
import http.server
import tempfile
import threading
import time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from neon.engine import HttpWorker, RateLimiter

app = QCoreApplication([])
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); source = root / 'src'; source.mkdir(); dest = root / 'dest'; dest.mkdir()
    payload = b'z' * 32768; (source / 'file.bin').write_bytes(payload)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(source))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/file.bin'
    correct = HttpWorker(url, str(dest), checksum=hashlib.sha256(payload).hexdigest())
    correct.start(); assert correct.wait(10000); assert correct.status == 'Completed'; assert correct.path.read_bytes() == payload
    strong = HttpWorker(url, str(dest), checksum=hashlib.sha512(payload).hexdigest(), hash_type='sha512')
    strong.start(); assert strong.wait(10000); assert strong.status == 'Completed'; assert strong.path.read_bytes() == payload
    wrong = HttpWorker(url, str(dest), checksum='0' * 64)
    wrong.start(); assert wrong.wait(10000); assert wrong.status == 'Checksum mismatch'; assert not wrong.path.exists(); assert Path(str(wrong.path) + '.part').exists()
    wrong.resolve_mismatch(False); assert wrong.status == 'Canceled'; assert not Path(str(wrong.path) + '.part').exists()
    keep = HttpWorker(url, str(dest), checksum='0' * 64)
    keep.start(); assert keep.wait(10000); keep.resolve_mismatch(True); assert keep.status == 'Completed'; assert keep.path.read_bytes() == payload
    rate = RateLimiter(); rate.set_rate(32768)
    limited = HttpWorker(url, str(dest), limiter=rate); start = time.monotonic(); limited.start(); assert limited.wait(10000); elapsed = time.monotonic() - start
    assert limited.status == 'Completed' and elapsed >= .85, (limited.status, elapsed)
    server.shutdown()
print('Checksum match, mismatch quarantine, discard, keep and rate limit: PASS')
