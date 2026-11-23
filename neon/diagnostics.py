"""Bounded local diagnostics: metadata only, no links, filenames or secrets."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from PySide6.QtCore import QStandardPaths

def create_logger():
    logger = logging.getLogger('zdm.events')
    if logger.handlers: return logger
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / 'activity.log', maxBytes=512 * 1024, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    except OSError:
        handler = logging.NullHandler()
    logger.addHandler(handler); logger.setLevel(logging.INFO); logger.propagate = False
    return logger
