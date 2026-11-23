"""Opt-in ZIP extraction with bounded, isolated output."""
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from PySide6.QtCore import QThread, Signal
from .engine import unique_path

class ExtractWorker(QThread):
    result = Signal(str, str)
    def __init__(self, archive):
        super().__init__(); self.archive = Path(archive)

    def run(self):
        folder = None
        created = False
        try:
            folder = unique_path(self.archive.parent, self.archive.stem + ' extracted')
            folder.mkdir()
            created = True
            with zipfile.ZipFile(self.archive) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(e.file_size for e in entries) > 10 * 1024**3:
                    raise ValueError('Archive exceeds extraction limits')
                written = 0
                for entry in entries:
                    name = entry.filename
                    p = PurePosixPath(name)
                    if ('\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or
                        stat.S_ISLNK(entry.external_attr >> 16)):
                        raise ValueError('Archive contains an unsafe path or symbolic link')
                    target = folder.joinpath(*p.parts)
                    if entry.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, target.open('xb') as out:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk: break
                            written += len(chunk)
                            if written > 10 * 1024**3: raise ValueError('Archive exceeds extraction limits')
                            out.write(chunk)
            self.result.emit(str(folder), '')
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
            if created and folder.is_dir(): shutil.rmtree(folder, ignore_errors=True)
            self.result.emit('', str(exc))
