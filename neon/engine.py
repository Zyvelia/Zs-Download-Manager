"""Transfer engines. Workers never touch widgets; updates cross Qt signals."""
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread, QTimer

try:
    import libtorrent as lt
except ImportError:
    lt = None


def readable(n, suffix='B'):
    n = max(0, n or 0)
    for unit in ('', 'K', 'M', 'G', 'T'):
        if n < 1024 or unit == 'T':
            return f'{n:.1f} {unit}{suffix}'
        n /= 1024


def unique_path(directory, name):
    name = Path(name).name.strip().strip('.') or 'download'
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', name)
    stem, ext = os.path.splitext(name)
    for i in range(10000):
        p = Path(directory) / (name if i == 0 else f'{stem} ({i}){ext}')
        if not p.exists() and not Path(str(p) + '.part').exists():
            return p
    raise OSError('Could not find an available filename')


class HttpWorker(QThread):
    changed = Signal(object)
    def __init__(self, url, directory):
        super().__init__()
        self.url, self.directory = url, directory
        self.stop_event = threading.Event()
        self.reason = 'Paused'
        self.path = None
        self.offset = 0
        self.total = 0
        self.validator = None
        self.status = 'Queued'
        self.error = ''
        self.speed = 0
        self.name = urllib.parse.unquote(Path(urllib.parse.urlsplit(url).path).name) or 'download'
        self.kind = 'HTTP'

    def snapshot(self):
        return dict(name=self.name, kind=self.kind, status=self.status, done=self.offset,
                    total=self.total, down=self.speed, up=0, uploaded=0,
                    path=str(self.path or Path(self.directory) / self.name), error=self.error)

    def emit_update(self): self.changed.emit(self.snapshot())

    def halt(self, reason):
        self.reason = reason
        self.stop_event.set()

    def run(self):
        self.stop_event.clear()
        self.status, self.error = 'Connecting', ''
        self.emit_update()
        try:
            if self.path is None:
                self.path = unique_path(self.directory, self.name)
            part = Path(str(self.path) + '.part')
            self.offset = part.stat().st_size if part.exists() else 0
            headers = {'User-Agent': 'NeonDownloadManager/1.0', 'Accept-Encoding': 'identity'}
            if self.offset and not self.validator:
                self.offset = 0  # Restart if the server supplied no safe resume validator.
            if self.offset:
                headers['Range'] = f'bytes={self.offset}-'
                headers['If-Range'] = self.validator
            with urllib.request.urlopen(urllib.request.Request(self.url, headers=headers), timeout=15) as response:
                if self.offset and response.status != 206:
                    # The server ignored Range; restart the partial file from zero.
                    self.offset = 0
                if response.status == 206:
                    content_range = response.headers.get('Content-Range', '')
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)', content_range)
                    if not match or int(match.group(1)) != self.offset:
                        raise ValueError('Server returned an invalid byte range')
                    self.total = int(match.group(3)) if match.group(3) != '*' else 0
                else:
                    self.total = int(response.headers.get('Content-Length') or 0)
                self.validator = response.headers.get('ETag') or response.headers.get('Last-Modified')
                if self.validator and self.validator.startswith('W/'):
                    self.validator = response.headers.get('Last-Modified')
                self.status = 'Downloading'
                last_time, last_bytes = time.monotonic(), self.offset
                with open(part, 'ab' if self.offset else 'wb') as out:
                    while not self.stop_event.is_set():
                        chunk = response.read(128 * 1024)
                        if not chunk: break
                        out.write(chunk)
                        self.offset += len(chunk)
                        now = time.monotonic()
                        if now - last_time >= .3:
                            self.speed = (self.offset - last_bytes) / (now - last_time)
                            last_time, last_bytes = now, self.offset
                            self.emit_update()
            self.speed = 0
            if self.stop_event.is_set():
                self.status = self.reason
                if self.reason == 'Canceled':
                    part.unlink(missing_ok=True)
                    self.offset = 0
            elif self.total and self.offset != self.total:
                raise IOError(f'Incomplete response ({self.offset} of {self.total} bytes)')
            else:
                # Hard-link gives an atomic no-overwrite commit in the same directory.
                try:
                    os.link(part, self.path)
                except FileExistsError:
                    self.path = unique_path(self.directory, self.name)
                    os.link(part, self.path)
                part.unlink()
                self.status = 'Completed'
        except Exception as exc:
            self.speed = 0
            self.status, self.error = 'Failed', str(exc)
        self.emit_update()


class TorrentEngine(QObject):
    changed = Signal(object, object)
    def __init__(self):
        super().__init__()
        self.session = lt.session({'listen_interfaces': '0.0.0.0:6881'}) if lt else None
        self.handles = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(700)

    def add(self, source, directory):
        if not self.session: raise RuntimeError('libtorrent is not installed. Install it to enable torrents.')
        if source.startswith('magnet:'):
            params = lt.parse_magnet_uri(source)
        else:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(source)
        # Isolate each torrent so it can never overwrite an existing destination file.
        folder = unique_path(directory, 'Torrent transfer')
        folder.mkdir()
        params.save_path = str(folder)
        # Refuse an already-added info hash rather than silently sharing a handle.
        try:
            h = self.session.add_torrent(params)
            if any(existing == h for existing in self.handles):
                raise ValueError('This torrent is already in the list')
        except Exception:
            folder.rmdir()
            raise
        self.handles.append(h)
        self.poll()
        return h

    def poll(self):
        for h in self.handles[:]:
            try:
                s = h.status()
                error = str(s.errc.message()) if s.errc.value() else ''
                status = ('Failed' if error else 'Paused' if s.paused else
                          'Seeding' if s.is_seeding else 'Downloading' if s.has_metadata else 'Fetching metadata')
                self.changed.emit(h, dict(name=s.name or 'Fetching metadata…', kind='TORRENT', status=status,
                    done=s.total_done, total=s.total_wanted, down=s.download_rate, up=s.upload_rate,
                    uploaded=s.all_time_upload, path=os.path.join(s.save_path, s.name) if s.name else s.save_path,
                    error=error, progress=s.progress))
            except RuntimeError:
                pass

    def remove(self, h):
        self.session.remove_torrent(h)  # preserve files
        self.handles.remove(h)
