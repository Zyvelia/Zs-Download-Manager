"""Atomic per-user transfer history. Records are data, never executable code."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QStandardPaths

class History:
    def __init__(self, path=None):
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.path = Path(path) if path else Path(base) / 'history.json'

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, list): raise ValueError('History must be a list')
            return data
        except FileNotFoundError:
            return []

    def save(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
