import functools, http.server, tempfile, threading, time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from neon.engine import HttpWorker
from neon.history import History
from neon.workflows import prepare_batch, retry_delay, validate_profile

app=QCoreApplication([])
a, bad=prepare_batch('https://example.org/a\nhttps://example.org/a\nfile:///x\nmagnet:?xt=urn:btih:abc')
assert len(a)==2 and len(bad)==2 and retry_delay(1)==15 and retry_delay(10)==300
profile=dict(directory='/tmp',down_limit=0,up_limit=1024,queue_limit=3,retry_limit=0,organize=True,extract_zip=False)
assert validate_profile(profile)==profile
try: validate_profile({**profile, 'queue_limit': 0})
except ValueError: pass
else: raise AssertionError('Invalid profile accepted')
assert prepare_batch('magnet:?xt=urn%3Abtih%3Aabc')[0]
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); history=History(root/'history.json')
    history.save([{'version':1}]); history.save([{'version':2}]); assert history.load_backup()==[{'version':1}]
    history.path.write_text('damaged'); assert history.load_backup()==[{'version':1}]
    src=root/'src'; src.mkdir(); dest=root/'out'; dest.mkdir(); payload=b'abc'*20000; (src/'file.bin').write_bytes(payload)
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(src))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler); threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}/file.bin'
    w1=HttpWorker(url,str(dest)); w2=HttpWorker(url,str(dest)); w1.start(); w2.start(); assert w1.wait(10000) and w2.wait(10000)
    assert w1.status==w2.status=='Completed', (w1.error,w2.error)
    assert w1.path!=w2.path and w1.path.read_bytes()==w2.path.read_bytes()==payload
    server.shutdown()
print('Batch validation, capped retry delay, history backup, concurrent filename safety: PASS')
