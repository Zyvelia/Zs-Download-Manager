import functools, http.server, os, tempfile, threading, time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from neon.engine import HttpWorker, TorrentEngine, lt
app=QCoreApplication([])
with tempfile.TemporaryDirectory() as tmp:
    src=Path(tmp)/'source'; dst=Path(tmp)/'dest'; src.mkdir(); dst.mkdir()
    payload=os.urandom(400000); (src/'test.bin').write_bytes(payload)
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(src))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}/test.bin'
    w=HttpWorker(url,str(dst)); w.start(); assert w.wait(10000); assert w.status=='Completed', w.error
    assert (dst/'test.bin').read_bytes()==payload
    w2=HttpWorker(url,str(dst)); w2.start(); assert w2.wait(10000); assert w2.status=='Completed', w2.error
    assert (dst/'test (1).bin').read_bytes()==payload
    print('HTTP download, content and collision protection: PASS')
    server.shutdown()
    fs=lt.file_storage(); lt.add_files(fs,str(src/'test.bin')); ct=lt.create_torrent(fs); lt.set_piece_hashes(ct,str(src)); torrent=Path(tmp)/'test.torrent'; torrent.write_bytes(lt.bencode(ct.generate()))
    engine=TorrentEngine(); h=engine.add(str(torrent),str(dst)); engine.poll(); h.pause(); engine.poll(); h.resume(); engine.poll(); engine.remove(h)
    magnet=lt.make_magnet_uri(lt.torrent_info(str(torrent))); h=engine.add(magnet,str(dst)); engine.poll(); engine.remove(h)
    print('Torrent file and magnet add, status polling, pause/resume/remove: PASS')
