"""Atomic local transfer history, with a last-known-good backup."""
import json
import os
import tempfile
from pathlib import Path
from PySide6.QtCore import QStandardPaths

class History:
    def __init__(self, path=None):
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.path = Path(path) if path else Path(base) / 'history.json'
        self.backup = self.path.with_suffix(self.path.suffix + '.bak')

    @staticmethod
    def _read(path):
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list): raise ValueError('History must be a list')
        return data

    def load(self):
        try: return self._read(self.path)
        except FileNotFoundError:
            if self.backup.exists(): raise ValueError('History file is missing; a backup is available') from None
            return []

    def load_backup(self):
        return self._read(self.backup)

    def _atomic_write(self, path, payload):
        fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def save(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        if self.path.exists():
            try:
                previous = self.path.read_text(encoding='utf-8')
                if not isinstance(json.loads(previous), list): raise ValueError('Invalid history')
            except (OSError, ValueError, UnicodeError):
                # Never replace a potentially good backup with damaged history.
                pass
            else:
                self._atomic_write(self.backup, previous)
        self._atomic_write(self.path, payload)
