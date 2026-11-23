import os
import re
import shutil
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QSettings, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QCheckBox, QDialog, QDialogButtonBox, QSystemTrayIcon, QMenu, QInputDialog, QPlainTextEdit, QProgressDialog,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget)
from .engine import HttpWorker, TorrentEngine, RateLimiter, readable
from .history import History
from .extract import ExtractWorker
from .taskbar import TaskbarProgress
from .workflows import prepare_batch, validate_transfer_url, retry_delay, validate_profile
from .diagnostics import create_logger

ROOT = Path(__file__).resolve().parent.parent
STYLE = '''
QWidget { color: #eee9f7; font-family: "DejaVu Sans"; font-size: 12px; }
QMainWindow, #canvas { background: #0d0b12; }
#sidebar { background: #131019; border-right: 1px solid #302336; }
#panel, #card, #metric { background: #191520; border: 1px solid #33283a; border-radius: 14px; }
#card { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #211725,stop:1 #15121e); border: 1px solid #563047; border-left: 3px solid #ef4e80; border-radius: 14px; }
#card:hover { border: 1px solid #a14a80; border-left: 3px solid #f85783; }
#listSurface { background: transparent; }
#transferIcon { color: #ff78a6; background: #3a1e35; border: 1px solid #78345f; border-radius: 11px; font-size: 20px; font-weight: bold; }
#transferStatus { color: #d995c3; font-size: 11px; font-weight: bold; }
#percent { color: #f795bb; font-size: 15px; font-weight: bold; }
#torrentBadge { color: #dcb3ff; background: #43255a; border: 1px solid #9053b4; border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: bold; }
#httpBadge { color: #ff9db8; background: #4c2036; border: 1px solid #a34267; border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: bold; }
#metric { background: #1b1522; }
#muted { color: #9b91a5; }
#eyebrow { color: #c17ca7; font-size: 10px; font-weight: bold; letter-spacing: 2px; }
#title { font-size: 25px; font-weight: bold; }
#metricValue { font-size: 22px; font-weight: bold; }
#filename { font-size: 14px; font-weight: bold; }
#badge { color: #f992af; background: #3b1d30; border-radius: 6px; padding: 4px 7px; font-size: 10px; font-weight: bold; }
QLineEdit { background: #100e16; border: 1px solid #493447; border-radius: 9px; padding: 11px; selection-background-color: #af386c; }
QLineEdit:focus { border: 1px solid #dc487b; }
QPushButton { background: #292130; border: 1px solid #493449; border-radius: 8px; padding: 9px 13px; font-weight: bold; }
QPushButton:hover { background: #3a273d; border-color: #a34f83; }
QPushButton:disabled { color: #635a69; background: #211c25; border-color: #302a32; }
QPushButton#primary { background: #d53e67; border: 0; color: white; padding: 11px 18px; }
QPushButton#primary:hover { background: #ed527c; }
QPushButton#nav { text-align: left; background: transparent; border: none; padding: 12px; color: #a99caf; }
QPushButton#nav:checked { color: #fff; background: #382132; border-left: 3px solid #f4537d; }
QProgressBar { background: #302938; border: 0; border-radius: 4px; max-height: 7px; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #f04b6e,stop:1 #a950f4); border-radius: 4px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #16121c; width: 9px; }
QScrollBar::handle:vertical { background: #584155; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
'''

def label(text, name=None):
    w = QLabel(text)
    if name: w.setObjectName(name)
    return w

def button(text, callback, primary=False):
    b = QPushButton(text)
    if primary: b.setObjectName('primary')
    b.clicked.connect(callback)
    return b

class SpeedGraph(QWidget):
    def __init__(self):
        super().__init__(); self.samples = []; self.setMinimumHeight(90); self.setMaximumHeight(110)
    def add_sample(self, down, up):
        self.samples = (self.samples + [(down, up)])[-60:]; self.update()
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#191520')); painter.setPen(QColor('#9b91a5')); painter.drawText(12, 20, 'TRANSFER SPEED   ↓ RED    ↑ PURPLE')
        if len(self.samples) < 2: return
        high = max(max(a,b) for a,b in self.samples) or 1
        for channel, color in ((0, '#ff527a'), (1, '#b66cff')):
            path = QPainterPath()
            for i, point in enumerate(self.samples):
                x = 12 + i * max(1, self.width()-24) / 59
                y = self.height()-10 - point[channel] / high * max(1, self.height()-40)
                if i == 0: path.moveTo(x,y)
                else: path.lineTo(x,y)
            painter.setPen(QPen(QColor(color), 2)); painter.drawPath(path)


class TransferCard(QFrame):
    def __init__(self, owner, obj, data):
        super().__init__(); self.setObjectName('card'); self.owner, self.obj = owner, obj
        box = QVBoxLayout(self); box.setContentsMargins(18, 16, 18, 16); box.setSpacing(10)
        top = QHBoxLayout(); top.setSpacing(12)
        self.icon = label('↓', 'transferIcon'); self.icon.setFixedSize(43,43); self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter); top.addWidget(self.icon)
        heading = QVBoxLayout(); heading.setSpacing(3); self.name = label('', 'filename'); self.name.setWordWrap(True); heading.addWidget(self.name)
        self.status = label('', 'transferStatus'); heading.addWidget(self.status); top.addLayout(heading, 1)
        self.badge = label('', 'httpBadge'); top.addWidget(self.badge); box.addLayout(top)
        self.detail = label('', 'muted'); self.detail.setWordWrap(True); box.addWidget(self.detail)
        progress_row = QHBoxLayout(); self.progress = QProgressBar(); self.progress.setTextVisible(False); progress_row.addWidget(self.progress, 1)
        self.percent = label('', 'percent'); self.percent.setMinimumWidth(54); self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); progress_row.addWidget(self.percent); box.addLayout(progress_row)
        self.stats = label('', 'muted'); self.stats.setWordWrap(True); box.addWidget(self.stats)
        row = QHBoxLayout(); row.setSpacing(7); row.addStretch()
        self.pause = button('Pause', self.toggle); row.addWidget(self.pause)
        self.cancel = button('Cancel', self.cancel_transfer); row.addWidget(self.cancel)
        self.open = button('Open', self.open_file); row.addWidget(self.open)
        self.resolve = button('Review hash', self.review_hash); row.addWidget(self.resolve); box.addLayout(row)
        row = QHBoxLayout(); row.setSpacing(7); row.addStretch()
        self.priority_button = button('Priority', self.set_priority); row.addWidget(self.priority_button)
        self.peers_button = button('Peers', self.show_peers); row.addWidget(self.peers_button)
        self.limits_button = button('Limits', self.edit_limits); row.addWidget(self.limits_button); row.addWidget(button('Folder', self.open_folder)); row.addWidget(button('Remove', self.remove)); row.addWidget(button('Delete', self.delete_file)); box.addLayout(row)
        self.update_data(data)

    def update_data(self, d):
        self.data = d; self.name.setText(d['name'])
        is_torrent = d['kind'] == 'TORRENT'
        self.badge.setObjectName('torrentBadge' if is_torrent else 'httpBadge')
        self.badge.setText('TORRENT' if is_torrent else 'DIRECT DOWNLOAD')
        self.badge.style().unpolish(self.badge); self.badge.style().polish(self.badge)
        self.icon.setText('◎' if is_torrent else '↓'); self.status.setText('●  ' + d['status'].upper())
        self.detail.setText(d['path'] + (f"\n{d['error']}" if d.get('error') else ''))
        pct = d.get('progress', d['done']/d['total'] if d['total'] else 0)
        if not d['total'] and d['status'] in ('Downloading', 'Connecting', 'Fetching metadata'):
            if hasattr(self.owner, 'reduced_motion') and self.owner.reduced_motion.isChecked():
                self.progress.setRange(0, 1000); self.progress.setValue(0)
            else: self.progress.setRange(0, 0)
            percent = 'Size unknown'
        else:
            self.progress.setRange(0, 1000); self.progress.setValue(round(min(1, pct)*1000)); percent = f'{pct*100:.1f}%'
        self.percent.setText(percent if percent != 'Size unknown' else '—')
        self.stats.setText(f"{readable(d['done'])} / {readable(d['total']) if d['total'] else 'unknown'}    ↓ {readable(d['down'])}/s    ↑ {readable(d['up'])}/s  ·  Uploaded {readable(d['uploaded'])}")
        torrent = d['kind'] == 'TORRENT'
        self.pause.setText('Resume' if d['status'] in ('Paused', 'Failed') else 'Pause')
        self.resolve.setVisible(d['status'] == 'Checksum mismatch')
        self.limits_button.setEnabled(d['status'] != 'Canceled')
        self.priority_button.setEnabled((is_torrent and d['status'] not in ('Canceled','Seeding','Failed')) or (not is_torrent and d['status'] in ('Queued','Paused','Waiting for network')))
        self.peers_button.setVisible(is_torrent); self.peers_button.setEnabled(d['status'] != 'Canceled')
        self.pause.setEnabled(d['status'] not in ('Completed', 'Canceled', 'Checksum mismatch', 'Verifying') and (torrent or not self.obj.isRunning() or d['status'] in ('Downloading', 'Connecting')))
        self.cancel.setEnabled(d['status'] not in ('Completed', 'Canceled', 'Checksum mismatch') and not (torrent and d['status'] == 'Seeding'))
        self.open.setEnabled(d['status'] in ('Completed', 'Seeding') and os.path.exists(d['path']))

    def toggle(self):
        if self.data['kind'] == 'TORRENT':
            self.obj.resume() if self.data['status'] == 'Paused' else self.obj.pause()
        elif self.obj.isRunning(): self.obj.halt('Paused'); self.pause.setEnabled(False)
        elif self.data['status'] in ('Waiting for network', 'Queued'): self.obj.status = 'Paused'; self.obj.emit_update()
        else: self.retry_attempts = 0; self.next_retry = 0; self.obj.status = 'Queued'; self.obj.emit_update(); self.owner.pump_queue()

    def cancel_transfer(self):
        if self.data['kind'] == 'TORRENT':
            self.torrent_info = dict(self.owner.torrents.sources.get(self.obj, {})); self.owner.torrents.remove(self.obj); self.data['status'] = 'Canceled'; self.data['down'] = self.data['up'] = 0; self.update_data(self.data)
            self.owner.refresh_metrics()
        elif self.obj.isRunning(): self.obj.halt('Canceled'); self.cancel.setEnabled(False)
        else:
            if self.obj.path: Path(str(self.obj.path) + '.part').unlink(missing_ok=True)
            self.obj.status = 'Canceled'; self.obj.offset = 0; self.obj.emit_update()

    def set_priority(self):
        levels = ['Low', 'Normal', 'High']
        choice, ok = QInputDialog.getItem(self, 'Queue priority', 'Priority for waiting transfers:', levels, getattr(self, 'priority', 1), False)
        if ok:
            self.priority = levels.index(choice)
            if self.data['kind'] == 'TORRENT':
                try:
                    if self.priority == 2: self.obj.queue_position_top()
                    elif self.priority == 0: self.obj.queue_position_bottom()
                    else: self.obj.queue_position_up()
                except RuntimeError as exc: QMessageBox.warning(self, 'Priority unavailable', str(exc)); return
            self.owner.save_history(); self.owner.pump_queue()

    def show_peers(self):
        try:
            peers = self.obj.get_peer_info()
            lines = [f"Peer {i+1}: ↓ {readable(p.down_speed)}/s  ↑ {readable(p.up_speed)}/s" for i,p in enumerate(peers)]
            QMessageBox.information(self, 'Connected peers', 'Peer addresses and identifiers are hidden. This is a local snapshot.\n\n' + ('\n'.join(lines[:100]) if lines else 'No connected peers.'))
        except RuntimeError as exc: QMessageBox.warning(self, 'Peers unavailable', str(exc))

    def review_hash(self):
        if self.obj.isRunning():
            QTimer.singleShot(100, self.review_hash); return
        dialog = QMessageBox(self)
        dialog.setWindowTitle(f'{self.obj.hash_type.upper()} mismatch')
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(f'The downloaded file does not match the expected {self.obj.hash_type.upper()}. It may be corrupt or altered.')
        dialog.setInformativeText(f"Expected: {self.obj.checksum}\nActual: {self.obj.actual_checksum}\n\nDiscard the file or keep it anyway?")
        discard = dialog.addButton('Discard file', QMessageBox.ButtonRole.DestructiveRole)
        keep = dialog.addButton('Keep anyway', QMessageBox.ButtonRole.AcceptRole)
        reverify = dialog.addButton('Verify another hash', QMessageBox.ButtonRole.ActionRole)
        dialog.addButton('Decide later', QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(discard); dialog.exec()
        if dialog.clickedButton() == keep: self.obj.resolve_mismatch(True)
        elif dialog.clickedButton() == discard: self.obj.resolve_mismatch(False)
        elif dialog.clickedButton() == reverify:
            algorithm, ok = QInputDialog.getItem(self, 'Verify checksum', 'Hash type:', ['SHA-256', 'SHA-512'], 0, False)
            if not ok: return
            expected, ok = QInputDialog.getText(self, 'Verify checksum', 'Expected hexadecimal hash:')
            if not ok: return
            name = algorithm.lower().replace('-', ''); expected = expected.strip()
            if len(expected) != (64 if name == 'sha256' else 128) or not re.fullmatch(r'[0-9a-fA-F]+', expected):
                QMessageBox.warning(self, 'Invalid checksum', 'Enter a valid hexadecimal hash of the selected type.'); return
            self.obj.hash_type = name; self.obj.checksum = expected.lower(); self.obj.reverify_only = True; self.obj.start()

    def edit_limits(self):
        dialog = QDialog(self); dialog.setWindowTitle('Transfer speed limits'); layout = QVBoxLayout(dialog)
        layout.addWidget(label('Download limit (KiB/s; 0 = unlimited)'))
        down = QSpinBox(); down.setRange(0, 1000000); layout.addWidget(down)
        torrent = self.data['kind'] == 'TORRENT'
        down.setValue((self.obj.download_limit() if torrent else self.obj.local_limiter.rate) // 1024)
        upload = None
        if torrent:
            layout.addWidget(label('Upload limit (KiB/s; 0 = unlimited)'))
            upload = QSpinBox(); upload.setRange(0, 1000000); upload.setValue(self.obj.upload_limit() // 1024); layout.addWidget(upload)
        else:
            layout.addWidget(label('Direct downloads do not upload data.', 'muted'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if torrent: self.obj.set_download_limit(down.value() * 1024); self.obj.set_upload_limit(upload.value() * 1024)
            else: self.obj.local_limiter.set_rate(down.value() * 1024)

    def open_file(self): QDesktopServices.openUrl(QUrl.fromLocalFile(self.data['path']))
    def open_folder(self):
        path = Path(self.data['path']); folder = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    def delete_file(self):
        if self.data['kind'] == 'HTTP' and self.obj.isRunning():
            QMessageBox.information(self, 'Transfer active', 'Pause or cancel the transfer first.'); return
        target = Path(self.data['path'])
        if self.data['kind'] == 'TORRENT':
            info = self.owner.torrents.sources.get(self.obj) or getattr(self, 'torrent_info', None)
            if not info: QMessageBox.warning(self, 'Delete unavailable', 'The torrent folder is unavailable.'); return
            target = Path(info['folder'])
        elif self.data['status'] not in ('Completed',):
            target = Path(str(self.obj.path) + '.part') if self.obj.path else None
        if not target or not target.exists():
            QMessageBox.information(self, 'File unavailable', 'The downloaded file was not found.'); return
        if QMessageBox.question(self, 'Delete downloaded data', f'Permanently delete {target} and remove this history entry?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        try:
            if self.data['kind'] == 'TORRENT':
                if self.obj in self.owner.torrents.handles: self.owner.torrents.remove(self.obj)
                if target.is_symlink(): raise ValueError('Cannot delete a symbolic-link folder.')
                shutil.rmtree(target)
            else: target.unlink()
            self.owner.remove_card(self)
        except (OSError, ValueError) as exc: QMessageBox.warning(self, 'Delete failed', str(exc))

    def remove(self):
        if self.data['kind'] == 'HTTP' and self.obj.isRunning():
            QMessageBox.information(self, 'Transfer active', 'Pause or cancel this transfer before removing it.'); return
        if self.data['kind'] == 'TORRENT' and self.obj in self.owner.torrents.handles:
            self.owner.torrents.remove(self.obj)
        self.owner.remove_card(self)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Z's Download Manager"); self.resize(1200, 820); self.setMinimumSize(850, 600)
        self.setWindowIcon(QIcon(str(ROOT / 'assets/logo.svg'))); self.setStyleSheet(STYLE)
        self.taskbar = TaskbarProgress(self)
        self.logger = create_logger(); self.bulk_loading = False
        self.settings = QSettings('Nexus', 'DownloadManager'); self.history = History(); self.restoring = False; self.history_readonly = False; self.cards = []; self.nav_buttons = {}; self.section = 'Dashboard'
        self.directory = self.settings.value('directory', str(Path.home() / 'Downloads'))
        self.torrents = TorrentEngine(); self.torrents.changed.connect(self.torrent_update)
        self.http_limiter = RateLimiter(); self.last_status = {}; self.clipboard_seen = ''; self.extract_workers = []
        self.statistics = {k: int(self.settings.value('stats_' + k, 0)) for k in ('downloaded', 'uploaded', 'completed', 'active_seconds')}
        self.stats_baseline = {}
        self.tray = QSystemTrayIcon(QIcon(str(ROOT / 'assets/logo.svg')), self)
        self.notification_path = None
        self.tray.messageClicked.connect(self.open_notification)
        menu = QMenu(self); menu.addAction('Open dashboard', lambda: self.navigate_and_show()); menu.addAction('Pause all', self.pause_all); menu.addAction('Resume all', self.resume_all); self.tray.setContextMenu(menu)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        root = QWidget(); root.setObjectName('canvas'); self.setCentralWidget(root); outer = QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side = QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(215); sl = QVBoxLayout(side); sl.setContentsMargins(18,24,18,20); sl.setSpacing(5)
        brand = QHBoxLayout(); logo = QLabel(); logo.setPixmap(QIcon(str(ROOT/'assets/logo.svg')).pixmap(44,44)); brand.addWidget(logo)
        brandtext = QVBoxLayout(); brandtext.addWidget(label("Z'S", 'filename')); brandtext.addWidget(label('DOWNLOADS', 'eyebrow')); brand.addLayout(brandtext); sl.addLayout(brand); sl.addSpacing(38)
        sl.addWidget(label('WORKSPACE', 'eyebrow')); sl.addSpacing(7)
        for icon, section in [('◈','Dashboard'),('↓','Downloads'),('⚙','Settings')]:
            b = QPushButton(f'{icon}   {section}'); b.setObjectName('nav'); b.setCheckable(True); b.clicked.connect(lambda checked=False, s=section: self.navigate(s)); sl.addWidget(b); self.nav_buttons[section] = b
        sl.addStretch(); sl.addWidget(label('●  ENGINE ONLINE', 'eyebrow')); sl.addWidget(label('Built for the flow.', 'muted')); outer.addWidget(side)
        main = QWidget(); ml = QVBoxLayout(main); ml.setContentsMargins(32,28,32,24); ml.setSpacing(18); outer.addWidget(main,1)
        header = QHBoxLayout(); titles = QVBoxLayout(); titles.addWidget(label('YOUR TRANSFER SPACE', 'eyebrow')); self.heading = label('Dashboard', 'title'); titles.addWidget(self.heading); header.addLayout(titles); header.addStretch(); header.addWidget(button('Mini mode', self.open_mini)); header.addWidget(label('●  SYSTEM READY', 'eyebrow')); ml.addLayout(header)
        self.content = QWidget(); self.content_layout = QVBoxLayout(self.content); self.content_layout.setContentsMargins(0,0,0,0); self.content_layout.setSpacing(16); ml.addWidget(self.content, 1)
        self.metrics = QWidget(); metrics_layout = QHBoxLayout(self.metrics); metrics_layout.setContentsMargins(0,0,0,0); metrics_layout.setSpacing(10); self.metric_values = []; self.metric_frames = []
        for title in ['DOWNLOAD SPEED','UPLOAD SPEED','ACTIVE TRANSFERS','COMPLETED']:
            frame = QFrame(); frame.setObjectName('metric'); fl = QVBoxLayout(frame); fl.setContentsMargins(16,14,16,14); fl.addWidget(label(title,'eyebrow')); value = label('0','metricValue'); fl.addWidget(value); self.metric_values.append(value); self.metric_frames.append(frame); frame.setVisible(self.settings.value('metric_' + title, True, type=bool)); metrics_layout.addWidget(frame)
        self.content_layout.addWidget(self.metrics)
        self.speed_graph = SpeedGraph(); self.content_layout.addWidget(self.speed_graph)
        self.graph_timer = QTimer(self); self.graph_timer.timeout.connect(self.sample_speeds); self.graph_timer.start(1000)
        self.add_panel = QFrame(); self.add_panel.setObjectName('panel'); al = QVBoxLayout(self.add_panel); al.setContentsMargins(18,16,18,17)
        row = QHBoxLayout(); row.addWidget(label('Start a transfer', 'filename')); row.addStretch(); row.addWidget(label('HTTP / HTTPS  ·  MAGNET  ·  TORRENT', 'eyebrow')); al.addLayout(row)
        row = QHBoxLayout(); self.url = QLineEdit(); self.url.setPlaceholderText('Paste a download URL or magnet link…'); self.url.returnPressed.connect(self.add_url); row.addWidget(self.url,1); row.addWidget(button('Add transfer  ↗',self.add_url,True)); row.addWidget(button('Open .torrent',self.add_torrent_file)); row.addWidget(button('Batch links',self.batch_links)); al.addLayout(row)
        hash_row = QHBoxLayout(); self.hash_type = QComboBox(); self.hash_type.addItems(['SHA-256','SHA-512']); hash_row.addWidget(self.hash_type)
        self.hash_input = QLineEdit(); self.hash_input.setPlaceholderText('Optional expected checksum for direct downloads'); hash_row.addWidget(self.hash_input,1); al.addLayout(hash_row)
        self.destination = label('', 'muted'); al.addWidget(self.destination); self.content_layout.addWidget(self.add_panel)
        filters = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText('Search transfers…'); self.search.textChanged.connect(self.filter_cards); filters.addWidget(self.search, 1)
        self.filter = QComboBox(); self.filter.addItems(['All', 'Active', 'Completed', 'Failed', 'Torrents', 'Quarantine']); self.filter.currentTextChanged.connect(self.filter_cards); filters.addWidget(self.filter)
        self.sort = QComboBox(); self.sort.addItems(['Date', 'Name', 'Size', 'Speed', 'Progress', 'Status']); self.sort.currentTextChanged.connect(self.sort_cards); filters.addWidget(self.sort); filters.addWidget(button('Clear history', self.clear_history))
        self.filter_widget = QWidget(); self.filter_widget.setLayout(filters); filters.setContentsMargins(0,0,0,0); self.content_layout.addWidget(self.filter_widget)
        self.list_label = label('TRANSFER ACTIVITY', 'eyebrow'); self.content_layout.addWidget(self.list_label)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget = QWidget(); self.list_widget.setObjectName('listSurface'); self.list_layout = QVBoxLayout(self.list_widget); self.list_layout.setContentsMargins(0,0,0,0); self.list_layout.setSpacing(10)
        self.empty = label('No transfers yet. Paste a link above to get started.', 'muted'); self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.list_layout.addWidget(self.empty); self.list_layout.addStretch(); self.scroll.setWidget(self.list_widget); self.content_layout.addWidget(self.scroll,1)
        self.settings_panel = QFrame(); self.settings_panel.setObjectName('panel'); se = QVBoxLayout(self.settings_panel); se.setContentsMargins(20,20,20,20); se.addWidget(label('Download destination','filename')); se.addWidget(label('New transfers are saved to this folder.', 'muted')); sr = QHBoxLayout(); self.path_label = label('','muted'); self.path_label.setWordWrap(True); sr.addWidget(self.path_label,1); sr.addWidget(button('Choose folder',self.choose_folder)); se.addLayout(sr)
        se.addWidget(label('Global speed limits', 'filename')); se.addWidget(label('KiB/s across all transfers; 0 = unlimited.', 'muted'))
        self.global_down = QSpinBox(); self.global_down.setRange(0,1000000); self.global_down.setPrefix('Download: '); self.global_down.setSuffix(' KiB/s'); self.global_down.setValue(int(self.settings.value('down_limit',0))); se.addWidget(self.global_down)
        self.global_up = QSpinBox(); self.global_up.setRange(0,1000000); self.global_up.setPrefix('Upload: '); self.global_up.setSuffix(' KiB/s'); self.global_up.setValue(int(self.settings.value('up_limit',0))); se.addWidget(self.global_up)
        self.global_down.valueChanged.connect(self.update_limits); self.global_up.valueChanged.connect(self.update_limits)
        se.addWidget(label('Queue and retries', 'filename'))
        self.queue_limit = QSpinBox(); self.queue_limit.setRange(1, 20); self.queue_limit.setPrefix('HTTP slots: '); self.queue_limit.setValue(int(self.settings.value('queue_limit', 3))); self.queue_limit.valueChanged.connect(self.queue_settings_changed); se.addWidget(self.queue_limit)
        self.retry_limit = QSpinBox(); self.retry_limit.setRange(0, 100); self.retry_limit.setPrefix('Retry limit (0 = unlimited): '); self.retry_limit.setValue(int(self.settings.value('retry_limit', 0))); self.retry_limit.valueChanged.connect(self.queue_settings_changed); se.addWidget(self.retry_limit)
        se.addWidget(button('View activity log', self.show_activity))
        se.addWidget(label('Dashboard panels', 'filename'))
        for idx, title in enumerate(['DOWNLOAD SPEED','UPLOAD SPEED','ACTIVE TRANSFERS','COMPLETED']):
            check = QCheckBox(title.title()); check.setChecked(self.settings.value('metric_' + title, True, type=bool)); check.toggled.connect(lambda enabled, i=idx, name=title: self.set_metric_visible(i, name, enabled)); se.addWidget(check)
        self.graph_enabled = QCheckBox('Show speed graph'); self.graph_enabled.setChecked(self.settings.value('show_graph', True, type=bool)); self.graph_enabled.toggled.connect(lambda enabled: self.settings.setValue('show_graph', enabled)); se.addWidget(self.graph_enabled)
        self.reduced_motion = QCheckBox('Reduce motion'); self.reduced_motion.setChecked(self.settings.value('reduced_motion', False, type=bool)); self.reduced_motion.toggled.connect(self.set_reduced_motion); se.addWidget(self.reduced_motion)
        self.compact = QCheckBox('Compact transfer cards'); self.compact.setChecked(self.settings.value('compact', False, type=bool)); self.compact.toggled.connect(self.set_compact); se.addWidget(self.compact)
        self.extract_enabled = QCheckBox('Automatically extract completed ZIP archives'); self.extract_enabled.setChecked(self.settings.value('extract_zip', False, type=bool)); self.extract_enabled.toggled.connect(lambda v: self.settings.setValue('extract_zip', v)); se.addWidget(self.extract_enabled)
        self.organize = QCheckBox('Organize direct downloads into folders by file type'); self.organize.setChecked(self.settings.value('organize', False, type=bool)); self.organize.toggled.connect(lambda v: self.settings.setValue('organize', v)); se.addWidget(self.organize)
        profiles = QHBoxLayout(); profiles.addWidget(button('Save profile', self.save_profile)); profiles.addWidget(button('Apply profile', self.apply_profile)); se.addLayout(profiles)
        options = QHBoxLayout(); options.addWidget(button('Export settings', self.export_settings)); options.addWidget(button('Import settings', self.import_settings)); se.addLayout(options)
        se.addWidget(label('Lifetime transfer statistics', 'filename'))
        self.stats_label = label('', 'muted'); self.stats_label.setWordWrap(True); se.addWidget(self.stats_label)
        self.clipboard_enabled = QCheckBox('Offer to add links copied to the clipboard'); self.clipboard_enabled.setChecked(self.settings.value('clipboard', False, type=bool)); self.clipboard_enabled.toggled.connect(lambda v: self.settings.setValue('clipboard',v)); se.addWidget(self.clipboard_enabled)
        se.addWidget(label('Notifications appear when your system tray is available. Click a completed notification to open the file.', 'muted')); se.addStretch(); self.settings_scroll = QScrollArea(); self.settings_scroll.setWidgetResizable(True); self.settings_scroll.setWidget(self.settings_panel); self.content_layout.addWidget(self.settings_scroll,1)
        self.navigate('Dashboard'); self.update_directory(); self.refresh_metrics(); self.refresh_statistics(); self.update_limits(); self.restore_history()
        self.save_timer = QTimer(self); self.save_timer.timeout.connect(self.save_history); self.save_timer.start(5000)
        self.retry_timer = QTimer(self); self.retry_timer.timeout.connect(self.retry_network); self.retry_timer.start(5000)

    def navigate(self, section):
        self.section = section; self.heading.setText(section)
        for name,b in self.nav_buttons.items(): b.setChecked(name == section)
        settings = section == 'Settings'; self.settings_scroll.setVisible(settings); self.scroll.setVisible(not settings); self.list_label.setVisible(not settings); self.add_panel.setVisible(not settings); self.filter_widget.setVisible(not settings); self.metrics.setVisible(section == 'Dashboard'); self.speed_graph.setVisible(section == 'Dashboard' and self.graph_enabled.isChecked())
        self.filter_cards()
    def filter_cards(self, *args):
        count=0
        for c in self.cards:
            visible = self.section in ('Dashboard', 'Downloads')
            query = self.search.text().strip().lower(); selected = self.filter.currentText(); status = c.data['status']
            visible = visible and (not query or query in c.data['name'].lower() or query in c.data['path'].lower())
            visible = visible and (selected == 'All' or (selected == 'Active' and status in ('Connecting','Downloading','Fetching metadata','Verifying','Seeding')) or (selected == 'Completed' and status in ('Completed','Seeding')) or (selected == 'Failed' and status in ('Failed','Checksum mismatch')) or (selected == 'Torrents' and c.data['kind'] == 'TORRENT') or (selected == 'Quarantine' and status == 'Checksum mismatch'))
            c.setVisible(visible); count += bool(visible)
        self.empty.setText('No transfers match your search or filter.' if self.cards else 'No transfers yet. Paste a link above to get started.')
        self.empty.setVisible(count == 0)
    def set_reduced_motion(self, enabled):
        self.settings.setValue('reduced_motion', enabled)
        for card in self.cards: card.update_data(card.data)

    def set_metric_visible(self, index, name, enabled):
        self.settings.setValue('metric_' + name, enabled); self.metric_frames[index].setVisible(enabled)

    def set_compact(self, value):
        self.settings.setValue('compact', value)
        for card in self.cards: card.detail.setVisible(not value); card.stats.setVisible(not value)

    def sort_cards(self, *args):
        choice = self.sort.currentText()
        def key(card):
            d = card.data
            return {'Date': lambda: getattr(card, 'created', 0), 'Name': lambda: d['name'].lower(),
                    'Size': lambda: d['total'], 'Speed': lambda: d['down'],
                    'Progress': lambda: d['done'] / d['total'] if d['total'] else 0,
                    'Status': lambda: d['status']}.get(choice, lambda: 0)()
        ordered = sorted(self.cards, key=key, reverse=choice in ('Date','Size','Speed','Progress'))
        for i, card in enumerate(ordered): self.list_layout.removeWidget(card); self.list_layout.insertWidget(i, card)

    def clear_history(self):
        choice, ok = QInputDialog.getItem(self, 'Clear history', 'Remove inactive entries:', ['Completed', 'Failed', 'Canceled', 'Older than 30 days', 'Currently filtered'], 0, False)
        if not ok: return
        inactive = ('Completed', 'Failed', 'Canceled', 'Paused', 'Checksum mismatch')
        def matches(c):
            if c.data['status'] not in inactive: return False
            if c.data['kind'] == 'HTTP' and c.obj.isRunning(): return False
            if choice == 'Older than 30 days': return getattr(c, 'created', time.time()) < time.time() - 30*86400
            if choice == 'Currently filtered': return not c.isHidden()
            return c.data['status'] == choice
        targets = [c for c in self.cards if matches(c)]
        if not targets: QMessageBox.information(self, 'Clear history', 'No inactive entries match.'); return
        if QMessageBox.question(self, 'Clear history', f'Remove {len(targets)} history entries? Downloaded and partial files will be kept.') != QMessageBox.StandardButton.Yes: return
        for c in targets:
            if c.data['kind'] == 'TORRENT' and c.obj in self.torrents.handles: self.torrents.remove(c.obj)
            self.remove_card(c)

    def destination_for(self, url):
        folder = Path(self.directory)
        if self.organize.isChecked():
            ext = Path(urlsplit(url).path).suffix.lower()
            categories = {'.zip':'Archives','.rar':'Archives','.7z':'Archives','.tar':'Archives','.gz':'Archives', '.mp4':'Videos','.mkv':'Videos','.mov':'Videos','.avi':'Videos', '.pdf':'Documents','.docx':'Documents','.txt':'Documents', '.png':'Images','.jpg':'Images','.jpeg':'Images','.webp':'Images'}
            folder = folder / categories.get(ext, 'Other')
            folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def get_profiles(self):
        try:
            profiles = json.loads(self.settings.value('profiles_json', '{}'))
            if not isinstance(profiles, dict): raise ValueError('Invalid profiles data')
            return profiles
        except (ValueError, TypeError) as exc:
            raise ValueError('Saved profiles could not be read; existing data was not changed.') from exc

    def save_profile(self):
        name, ok = QInputDialog.getText(self, 'Save profile', 'Profile name:')
        name = name.strip()
        if not ok or not name: return
        if len(name) > 80: QMessageBox.warning(self, 'Save profile', 'Use a name of 80 characters or fewer.'); return
        try:
            profiles = self.get_profiles()
            if name not in profiles and len(profiles) >= 20: raise ValueError('Maximum of 20 profiles reached.')
            if name in profiles and QMessageBox.question(self, 'Replace profile', f'Replace profile {name}?') != QMessageBox.StandardButton.Yes: return
            profiles[name] = validate_profile(dict(directory=self.directory, down_limit=self.global_down.value(), up_limit=self.global_up.value(), queue_limit=self.queue_limit.value(), retry_limit=self.retry_limit.value(), organize=self.organize.isChecked(), extract_zip=self.extract_enabled.isChecked()))
            self.settings.setValue('profiles_json', json.dumps(profiles)); self.logger.info('profile saved')
        except ValueError as exc: QMessageBox.warning(self, 'Save profile', str(exc))

    def apply_profile(self):
        try: profiles = self.get_profiles()
        except ValueError as exc: QMessageBox.warning(self, 'Apply profile', str(exc)); return
        if not profiles: QMessageBox.information(self, 'Apply profile', 'Save a profile first.'); return
        name, ok = QInputDialog.getItem(self, 'Apply profile', 'Choose a saved profile:', sorted(profiles), 0, False)
        if not ok: return
        try: profile = validate_profile(profiles[name])
        except ValueError as exc: QMessageBox.warning(self, 'Apply profile', str(exc)); return
        self.directory = profile['directory']; self.settings.setValue('directory', self.directory); self.update_directory()
        self.global_down.setValue(profile['down_limit']); self.global_up.setValue(profile['up_limit'])
        self.queue_limit.setValue(profile['queue_limit']); self.retry_limit.setValue(profile['retry_limit'])
        self.organize.setChecked(profile['organize']); self.extract_enabled.setChecked(profile['extract_zip']); self.logger.info('profile applied')

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export settings', 'z-settings.json', 'JSON (*.json)')
        if not path: return
        try:
            values = {'directory': self.directory, 'down_limit': self.global_down.value(), 'up_limit': self.global_up.value(), 'clipboard': self.clipboard_enabled.isChecked(), 'organize': self.organize.isChecked(), 'extract_zip': self.extract_enabled.isChecked(), 'compact': self.compact.isChecked(), 'reduced_motion': self.reduced_motion.isChecked(), 'show_graph': self.graph_enabled.isChecked(), 'queue_limit': self.queue_limit.value(), 'retry_limit': self.retry_limit.value(), 'profiles': self.get_profiles()}
            for i, name in enumerate(('DOWNLOAD SPEED','UPLOAD SPEED','ACTIVE TRANSFERS','COMPLETED')): values['metric_' + name] = self.settings.value('metric_' + name, True, type=bool)
            Path(path).write_text(json.dumps(values, indent=2), encoding='utf-8')
        except (OSError, ValueError) as exc: QMessageBox.warning(self, 'Export failed', str(exc))

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import settings', '', 'JSON (*.json)')
        if not path: return
        try:
            values = json.loads(Path(path).read_text(encoding='utf-8'))
            down = int(values.get('down_limit', 0)); up = int(values.get('up_limit', 0))
            if not (0 <= down <= 1000000 and 0 <= up <= 1000000): raise ValueError('Invalid speed limit')
            queue_limit = int(values.get('queue_limit', self.queue_limit.value())); retry_limit = int(values.get('retry_limit', self.retry_limit.value()))
            if not (1 <= queue_limit <= 20 and 0 <= retry_limit <= 100): raise ValueError('Invalid queue or retry limit')
            profiles = values.get('profiles')
            if profiles is not None:
                if not isinstance(profiles, dict) or len(profiles) > 20: raise ValueError('Invalid profiles')
                for key, profile in profiles.items():
                    if not isinstance(key, str) or not key or len(key) > 80: raise ValueError('Invalid profile name')
                    validate_profile(profile)
            directory = values.get('directory', self.directory)
            if not isinstance(directory, str) or not directory: raise ValueError('Invalid directory')
            def checked(value): return value if isinstance(value, bool) else str(value).lower() in ('true','1')
            self.directory = directory; self.settings.setValue('directory', directory); self.update_directory()
            self.global_down.setValue(down); self.global_up.setValue(up)
            self.queue_limit.setValue(queue_limit); self.retry_limit.setValue(retry_limit)
            if profiles is not None: self.settings.setValue('profiles_json', json.dumps(profiles))
            self.clipboard_enabled.setChecked(checked(values.get('clipboard', False))); self.organize.setChecked(checked(values.get('organize', False)))
            self.extract_enabled.setChecked(checked(values.get('extract_zip', False))); self.reduced_motion.setChecked(checked(values.get('reduced_motion', False))); self.compact.setChecked(checked(values.get('compact', False))); self.graph_enabled.setChecked(checked(values.get('show_graph', True)))
            for name in ('DOWNLOAD SPEED','UPLOAD SPEED','ACTIVE TRANSFERS','COMPLETED'):
                if 'metric_' + name in values: self.settings.setValue('metric_' + name, checked(values['metric_' + name]))
            QMessageBox.information(self, 'Settings imported', 'Restart the app to apply all dashboard panel settings.')
        except (OSError, ValueError, TypeError, AttributeError) as exc: QMessageBox.warning(self, 'Import failed', str(exc))

    def navigate_and_show(self):
        self.navigate('Dashboard'); self.showNormal(); self.raise_(); self.activateWindow()

    def pause_all(self):
        for c in self.cards:
            if c.data['kind'] == 'HTTP' and c.obj.isRunning(): c.obj.halt('Paused')
            elif c.data['kind'] == 'HTTP' and c.data['status'] in ('Queued','Waiting for network'): c.obj.status = 'Paused'; c.obj.emit_update()
            elif c.data['kind'] == 'TORRENT' and c.obj in self.torrents.handles: c.obj.pause()

    def resume_all(self):
        for c in self.cards:
            if c.data['kind'] == 'HTTP' and c.data['status'] in ('Paused','Waiting for network') and not c.obj.isRunning(): c.retry_attempts = 0; c.next_retry = 0; c.obj.status = 'Queued'; c.obj.emit_update()
            elif c.data['kind'] == 'TORRENT' and c.data['status'] == 'Paused' and c.obj in self.torrents.handles: c.obj.resume()
        self.pump_queue()

    def update_directory(self):
        self.destination.setText('SAVE TO  ·  ' + self.directory); self.path_label.setText(self.directory)
    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose download folder', self.directory)
        if path: self.directory = path; self.settings.setValue('directory',path); self.update_directory()
    def ensure_directory(self):
        p=Path(self.directory); p.mkdir(parents=True,exist_ok=True)
        if not p.is_dir() or not os.access(p,os.W_OK): raise ValueError('Download destination is not writable.')
    def queue_settings_changed(self, *args):
        if not hasattr(self, 'retry_limit'): return
        self.settings.setValue('queue_limit', self.queue_limit.value()); self.settings.setValue('retry_limit', self.retry_limit.value())
        self.pump_queue()

    def show_activity(self):
        dialog = QDialog(self); dialog.setWindowTitle('Activity log'); dialog.resize(700, 420)
        layout = QVBoxLayout(dialog); layout.addWidget(label('Recent state transitions. Links and filenames are excluded.', 'muted'))
        view = QPlainTextEdit(); view.setReadOnly(True)
        try:
            log_file = Path(self.history.path.parent) / 'activity.log'
            with log_file.open('rb') as f:
                f.seek(0, os.SEEK_END); f.seek(max(0, f.tell() - 100000)); content = f.read().decode('utf-8', 'replace')
            view.setPlainText(content)
        except OSError: view.setPlainText('No activity log is available.')
        layout.addWidget(view); layout.addWidget(button('Close', dialog.accept)); dialog.exec()

    def batch_links(self):
        if getattr(self, 'batch_active', False): return
        method, ok = QInputDialog.getItem(self, 'Batch links', 'Input source:', ['Paste links', 'Import UTF-8 text file'], 0, False)
        if not ok: return
        if method == 'Paste links':
            text, ok = QInputDialog.getMultiLineText(self, 'Batch links', 'One HTTP(S) or magnet link per line:')
            if not ok: return
        else:
            path, _ = QFileDialog.getOpenFileName(self, 'Import links', '', 'Text files (*.txt);;All files (*)')
            if not path: return
            try:
                if Path(path).stat().st_size > 1024 * 1024: raise ValueError('Text file exceeds 1 MiB')
                text = Path(path).read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError, ValueError) as exc: QMessageBox.warning(self, 'Import failed', str(exc)); return
        try:
            existing = [c.obj.url for c in self.cards if c.data['kind'] == 'HTTP']
            existing += [info['source'] for info in self.torrents.sources.values() if info['source'].startswith('magnet:')]
            accepted, rejected = prepare_batch(text, existing)
            self.ensure_directory()
        except (OSError, ValueError) as exc: QMessageBox.warning(self, 'Batch preview', str(exc)); return
        details = '\n'.join(f'Line {n}: {reason}' for n, reason in rejected[:12])
        if len(rejected) > 12: details += f'\n… and {len(rejected)-12} more.'
        if not accepted: QMessageBox.information(self, 'Batch preview', 'No new valid links.\n' + details); return
        answer = QMessageBox.question(self, 'Batch preview', f'Add {len(accepted)} links? {len(rejected)} invalid or duplicate lines will be skipped.\n{details}', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        self.batch_active = True; self.bulk_loading = True
        self.batch_dialog = QProgressDialog('Adding transfers…', 'Stop adding', 0, len(accepted), self)
        self.batch_dialog.setWindowModality(Qt.WindowModality.WindowModal); self.batch_dialog.setMinimumDuration(0); self.batch_dialog.show()
        state = {'index': 0, 'failed': 0}
        def step():
            if not self.batch_active: return
            if self.batch_dialog.wasCanceled() or state['index'] >= len(accepted):
                self.batch_active = False; self.bulk_loading = False; self.batch_dialog.close()
                self.filter_cards(); self.sort_cards(); self.refresh_metrics(); self.update_limits(); self.pump_queue(); self.save_history()
                if state['failed']: QMessageBox.warning(self, 'Batch complete', f"{state['failed']} transfers could not be added. Other transfers were kept.")
                return
            for _ in range(12):
                if state['index'] >= len(accepted): break
                url = accepted[state['index']]; state['index'] += 1
                try:
                    if url.startswith('magnet:?'): self.add_torrent(url)
                    else:
                        worker = HttpWorker(url, self.destination_for(url), self.http_limiter)
                        card = TransferCard(self, worker, worker.snapshot()); self.bind_worker(card); self.add_card(card)
                except (OSError, ValueError, RuntimeError): state['failed'] += 1
            self.batch_dialog.setValue(state['index']); QTimer.singleShot(0, step)
        QTimer.singleShot(0, step)

    def add_url(self):
        url = self.url.text().strip()
        try:
            self.ensure_directory()
            url = validate_transfer_url(url)
            checksum = self.hash_input.text().strip()
            algorithm = self.hash_type.currentText().lower().replace('-', '')
            digits = 64 if algorithm == 'sha256' else 128
            if checksum and (len(checksum) != digits or not re.fullmatch(r'[0-9a-fA-F]+', checksum)): raise ValueError(f'{algorithm.upper()} must be exactly {digits} hexadecimal characters.')
            if url.startswith('magnet:?'):
                if checksum: raise ValueError('Checksums are available for direct downloads only. Torrents use their own piece verification.')
                self.add_torrent(url)
            else:
                directory = self.destination_for(url)
                worker=HttpWorker(url,directory,self.http_limiter,checksum,algorithm); card=TransferCard(self,worker,worker.snapshot()); self.bind_worker(card); self.add_card(card); self.pump_queue(); self.save_history()
            self.url.clear(); self.hash_input.clear()
        except Exception as e: QMessageBox.warning(self,'Could not start transfer',str(e))
    def add_torrent_file(self):
        if self.hash_input.text().strip():
            QMessageBox.information(self, 'SHA-256 verification', 'The checksum field applies to direct downloads. Clear it before adding a torrent; torrents verify their pieces automatically.'); return
        path,_=QFileDialog.getOpenFileName(self,'Open torrent file','','Torrent files (*.torrent)')
        if path:
            try: self.ensure_directory(); self.add_torrent(path)
            except Exception as e: QMessageBox.warning(self,'Could not open torrent',str(e))
    def add_torrent(self, source):
        h=self.torrents.add(source,self.directory)
        d=dict(name='Fetching metadata…',kind='TORRENT',status='Fetching metadata',done=0,total=0,down=0,up=0,uploaded=0,path=self.directory,error='')
        self.add_card(TransferCard(self,h,d)); self.torrents.poll(); self.save_history()
    def torrent_update(self,h,data):
        for c in self.cards:
            if c.data['kind']=='TORRENT' and c.obj==h: c.update_data(data); self.transfer_changed(c, data); break
        self.refresh_metrics()
    def add_card(self,c):
        c.created = getattr(c, 'created', time.time()); self.stats_baseline[c] = (c.data['done'], c.data['uploaded']); self.cards.append(c)
        c.detail.setVisible(not self.compact.isChecked()); c.stats.setVisible(not self.compact.isChecked()); self.list_layout.insertWidget(self.list_layout.count()-1,c)
        if not self.bulk_loading: self.filter_cards(); self.sort_cards(); self.refresh_metrics(); self.update_limits()
    def remove_card(self,c): self.stats_baseline.pop(c, None); self.last_status.pop(c, None); self.cards.remove(c); self.list_layout.removeWidget(c); c.deleteLater(); self.filter_cards(); self.refresh_metrics(); self.update_limits(); self.save_history()
    def refresh_metrics(self,*args):
        ds=[c.data for c in self.cards]; values=[readable(sum(x['down'] for x in ds))+'/s',readable(sum(x['up'] for x in ds))+'/s',str(sum(x['status'] in ('Downloading','Connecting','Fetching metadata','Seeding') for x in ds)),str(sum(x['status'] in ('Completed','Seeding') for x in ds))]
        for w,v in zip(self.metric_values,values): w.setText(v)
        self.taskbar.update(ds)
    def pump_queue(self):
        # Direct transfers are bounded; higher-priority waiting items start first.
        active = sum(c.obj.isRunning() for c in self.cards if c.data['kind'] == 'HTTP')
        queued = [c for c in self.cards if c.data['kind'] == 'HTTP' and c.obj.status == 'Queued' and not c.obj.isRunning()]
        queued.sort(key=lambda c: (-getattr(c, 'priority', 1), getattr(c, 'created', 0)))
        limit = self.queue_limit.value() if hasattr(self, 'queue_limit') else 3
        for card in queued[:max(0, limit-active)]: card.obj.start()

    def bind_worker(self, card):
        card.obj.changed.connect(card.update_data)
        card.obj.changed.connect(lambda data, c=card: self.transfer_changed(c, data))
        card.obj.finished.connect(self.pump_queue)

    def history_records(self):
        records = []
        for card in self.cards:
            data = dict(card.data); obj = card.obj
            data.update(created=getattr(card, 'created', time.time()), priority=getattr(card, 'priority', 1), counted=getattr(card, 'counted', False), retry_attempts=getattr(card, 'retry_attempts', 0), next_retry=getattr(card, 'next_retry', 0))
            if data['kind'] == 'HTTP':
                data.update(url=obj.url, directory=obj.directory, validator=obj.validator, checksum=obj.checksum, hash_type=obj.hash_type, actual_checksum=obj.actual_checksum, local_limit=obj.local_limiter.rate, worker_path=str(obj.path) if obj.path else '')
            else:
                info = self.torrents.sources.get(obj) or getattr(card, 'torrent_info', None)
                if not info: continue
                data.update(info)
            records.append(data)
        return records

    def save_history(self):
        if self.restoring or self.history_readonly or self.bulk_loading: return
        for key, value in self.statistics.items(): self.settings.setValue('stats_' + key, value)
        try: self.history.save(self.history_records())
        except OSError as exc:
            if not getattr(self, '_history_error_shown', False):
                self._history_error_shown = True; QMessageBox.warning(self, 'History could not be saved', str(exc))

    def restore_history(self):
        self.restoring = True; self.bulk_loading = True; restart = []; errors = []
        try:
            try: records = self.history.load()
            except (OSError, ValueError) as exc:
                try: backup = self.history.load_backup()
                except (OSError, ValueError):
                    self.history_readonly = True; QMessageBox.warning(self, 'History could not be loaded', str(exc)); return
                if QMessageBox.question(self, 'History recovery', 'History is unreadable. Restore the previous backup? Newer changes may be missing.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    self.history_readonly = True; return
                records = backup; self.logger.warning('history restored from backup')
            for data in records:
                try:
                    if data['kind'] == 'HTTP':
                        obj = HttpWorker(data['url'], data['directory'], self.http_limiter, data.get('checksum',''), data.get('hash_type','sha256'))
                        obj.path = Path(data['worker_path']) if data.get('worker_path') else None
                        obj.validator = data.get('validator'); obj.total = data.get('total', 0); obj.offset = data.get('done', 0)
                        obj.actual_checksum = data.get('actual_checksum', ''); obj.status = data['status']; obj.error = data.get('error','')
                        obj.local_limiter.set_rate(data.get('local_limit',0))
                        if obj.status in ('Queued','Downloading','Connecting','Verifying','Waiting for network'):
                            obj.status = 'Queued'; restart.append(obj)
                        data.update(obj.snapshot())
                        card = TransferCard(self, obj, data); self.bind_worker(card)
                    else:
                        if data['status'] == 'Canceled':
                            obj = object()
                            card = TransferCard(self, obj, data)
                            card.torrent_info = {key: data.get(key) for key in ('source', 'blob', 'folder')}
                        else:
                            obj = self.torrents.add(data['source'], str(Path(data['folder']).parent), restore_folder=data['folder'], saved_blob=data.get('blob'))
                            if data['status'] == 'Paused': obj.pause()
                            card = TransferCard(self, obj, data)
                    card.created = data.get('created', time.time()); card.priority = data.get('priority', 1)
                    if data['kind'] == 'TORRENT' and data['status'] != 'Canceled':
                        if card.priority == 2: obj.queue_position_top()
                        elif card.priority == 0: obj.queue_position_bottom()
                    card.counted = data.get('counted', data.get('status') in ('Completed','Seeding')); card.retry_attempts = data.get('retry_attempts', 0); card.next_retry = data.get('next_retry', 0); self.add_card(card)
                except (ValueError, OSError, KeyError, RuntimeError) as exc: errors.append(str(exc))
            self.pump_queue()
            self.torrents.poll()
            if errors:
                self.history_readonly = True
                QMessageBox.warning(self, 'Some transfers could not be restored', 'History will not be overwritten.\n' + '\n'.join(errors[:5]))
        finally:
            self.restoring = False; self.bulk_loading = False
            self.filter_cards(); self.sort_cards(); self.refresh_metrics(); self.update_limits()

    def retry_network(self):
        for card in self.cards:
            if card.data['kind'] == 'HTTP' and card.data['status'] == 'Waiting for network' and not card.obj.isRunning() and time.time() >= getattr(card, 'next_retry', 0): card.obj.status = 'Queued'; card.obj.emit_update()
        self.pump_queue()

    def refresh_statistics(self):
        active = self.statistics['active_seconds']; average = self.statistics['downloaded'] / active if active else 0
        self.stats_label.setText(f"Downloaded: {readable(self.statistics['downloaded'])}   ·   Uploaded: {readable(self.statistics['uploaded'])}\nCompleted: {self.statistics['completed']}   ·   Average download speed during activity: {readable(average)}/s\nStatistics accumulate while this version is running; clearing history does not reset them.")

    def open_mini(self):
        if getattr(self, 'mini', None) and self.mini.isVisible():
            self.mini.raise_(); return
        dialog = QDialog(self, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setWindowTitle("Z's Downloads"); dialog.setMinimumWidth(300)
        layout = QVBoxLayout(dialog); layout.addWidget(label("Z'S DOWNLOAD MANAGER", 'eyebrow'))
        summary = label('', 'filename'); layout.addWidget(summary)
        speeds = label('', 'muted'); layout.addWidget(speeds)
        layout.addWidget(button('Open dashboard', lambda: (dialog.hide(), self.navigate_and_show())))
        timer = QTimer(dialog)
        def refresh():
            items = [c.data for c in self.cards]
            summary.setText(f"{sum(d['status'] in ('Connecting','Downloading','Fetching metadata','Seeding') for d in items)} active transfers")
            speeds.setText(f"↓ {readable(sum(d['down'] for d in items))}/s    ↑ {readable(sum(d['up'] for d in items))}/s")
        timer.timeout.connect(refresh); timer.start(1000); refresh()
        self.mini = dialog; dialog.show()

    def sample_speeds(self):
        self.speed_graph.add_sample(sum(c.data['down'] for c in self.cards), sum(c.data['up'] for c in self.cards))
        if any(c.data['status'] in ('Downloading', 'Fetching metadata', 'Seeding') for c in self.cards): self.statistics['active_seconds'] += 1
        self.refresh_statistics()

    def update_limits(self, *args):
        down = self.global_down.value() * 1024; up = self.global_up.value() * 1024
        self.settings.setValue('down_limit', self.global_down.value()); self.settings.setValue('up_limit', self.global_up.value())
        # Split a capped budget while both protocols are active, so their sum stays capped.
        http_active = any(c.data['kind']=='HTTP' and c.data['status'] in ('Queued','Connecting','Downloading') for c in self.cards)
        torrent_active = any(c.data['kind']=='TORRENT' and c.data['status'] in ('Fetching metadata','Downloading','Seeding') for c in self.cards)
        http_rate = max(1, down // 2) if down and http_active and torrent_active else down
        torrent_rate = max(1, down - http_rate) if down and http_active and torrent_active else down
        self.http_limiter.set_rate(http_rate)
        if self.torrents.session: self.torrents.session.apply_settings({'download_rate_limit': torrent_rate, 'upload_rate_limit': up})

    def transfer_changed(self, card, data):
        old = self.last_status.get(card); new = data['status']; self.last_status[card] = new
        prev_down, prev_up = self.stats_baseline.get(card, (data['done'], data['uploaded']))
        self.statistics['downloaded'] += max(0, data['done'] - prev_down)
        self.statistics['uploaded'] += max(0, data['uploaded'] - prev_up)
        self.stats_baseline[card] = (data['done'], data['uploaded'])
        if new in ('Completed', 'Seeding') and not getattr(card, 'counted', False):
            card.counted = True; self.statistics['completed'] += 1
        self.refresh_statistics()
        if old != new:
            if new == 'Waiting for network' and data['kind'] == 'HTTP':
                card.retry_attempts = getattr(card, 'retry_attempts', 0) + 1
                if self.retry_limit.value() and card.retry_attempts > self.retry_limit.value():
                    card.obj.status = new = 'Failed'; card.obj.error = 'Retry limit reached. ' + card.obj.error
                    data = card.obj.snapshot(); card.update_data(data); self.last_status[card] = new
                else:
                    delay = retry_delay(card.retry_attempts); card.next_retry = time.time() + delay
                    data = dict(data); data['error'] = f"{data.get('error','')}  ·  Retry {card.retry_attempts} in about {delay}s"
                    card.update_data(data)
            elif new in ('Completed', 'Seeding'):
                card.retry_attempts = 0; card.next_retry = 0
            self.logger.info('transfer kind=%s state=%s', data['kind'], new)
            self.filter_cards(); self.update_limits()
            if new == 'Checksum mismatch': QTimer.singleShot(0, card.review_hash)
            if new == 'Completed' and data['kind'] == 'HTTP' and not data.get('error') and self.extract_enabled.isChecked() and data['path'].lower().endswith('.zip'):
                self.extract_zip(data['path'])
            if new in ('Completed', 'Seeding', 'Failed') and old not in ('Completed', 'Seeding', 'Failed'):
                self.notification_path = data['path'] if new in ('Completed', 'Seeding') else None
                if self.tray.isVisible(): self.tray.showMessage("Z's Download Manager", f"{data['name']}: {new}." + (' Click to open.' if self.notification_path else ''), QSystemTrayIcon.MessageIcon.Information, 10000)
        self.refresh_metrics()
        if old != new: self.save_history()

    def extract_zip(self, path):
        worker = ExtractWorker(path); self.extract_workers.append(worker)
        def finished(folder, error):
            message = f'ZIP extracted to {folder}' if folder else f'ZIP extraction failed: {error}'
            if self.tray.isVisible(): self.tray.showMessage("Z's Download Manager", message, QSystemTrayIcon.MessageIcon.Information, 10000)
            elif error: QMessageBox.warning(self, 'Extraction failed', message)
        worker.result.connect(finished)
        worker.finished.connect(lambda: self.extract_workers.remove(worker) if worker in self.extract_workers else None)
        worker.start()

    def open_notification(self):
        if self.notification_path and os.path.exists(self.notification_path): QDesktopServices.openUrl(QUrl.fromLocalFile(self.notification_path))
        else: self.showNormal(); self.raise_(); self.activateWindow()

    def clipboard_changed(self):
        if not hasattr(self, 'clipboard_enabled') or not self.clipboard_enabled.isChecked(): return
        text = QApplication.clipboard().text().strip()
        if text == self.clipboard_seen: return
        self.clipboard_seen = text
        parsed = urlsplit(text)
        if not ((parsed.scheme in ('http','https') and parsed.hostname) or text.startswith('magnet:?')): return
        if QMessageBox.question(self, 'Clipboard link', 'Add the copied link to the transfer box?') == QMessageBox.StandardButton.Yes:
            self.url.setText(text); self.navigate('Downloads'); self.showNormal(); self.raise_(); self.activateWindow()

    def closeEvent(self,event):
        self.batch_active = False; self.bulk_loading = False
        workers=[c.obj for c in self.cards if c.data['kind']=='HTTP' and c.obj.isRunning()]
        resume_on_start = [w for w in workers if not w.stop_event.is_set()]
        for w in workers: w.halt('Paused')
        for w in workers: w.wait(17000)
        for w in self.extract_workers[:]: w.wait()
        for c in self.cards:
            if c.data['kind'] == 'HTTP':
                if c.obj in resume_on_start and c.obj.status == 'Paused': c.obj.status = 'Queued'
                c.data = c.obj.snapshot()
        self.save_history()
        self.taskbar.close()
        event.accept()
