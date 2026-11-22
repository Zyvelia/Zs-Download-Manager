import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QSettings, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QCheckBox, QDialog, QDialogButtonBox, QSystemTrayIcon,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget)
from .engine import HttpWorker, TorrentEngine, RateLimiter, readable

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
        self.resolve = button('Review hash', self.review_hash); row.addWidget(self.resolve)
        self.limits_button = button('Limits', self.edit_limits); row.addWidget(self.limits_button); row.addWidget(button('Folder', self.open_folder)); row.addWidget(button('Remove', self.remove)); box.addLayout(row)
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
            self.progress.setRange(0, 0); percent = 'Size unknown'
        else:
            self.progress.setRange(0, 1000); self.progress.setValue(round(min(1, pct)*1000)); percent = f'{pct*100:.1f}%'
        self.percent.setText(percent if percent != 'Size unknown' else '—')
        self.stats.setText(f"{readable(d['done'])} / {readable(d['total']) if d['total'] else 'unknown'}    ↓ {readable(d['down'])}/s    ↑ {readable(d['up'])}/s  ·  Uploaded {readable(d['uploaded'])}")
        torrent = d['kind'] == 'TORRENT'
        self.pause.setText('Resume' if d['status'] in ('Paused', 'Failed') else 'Pause')
        self.resolve.setVisible(d['status'] == 'Checksum mismatch')
        self.limits_button.setEnabled(d['status'] != 'Canceled')
        self.pause.setEnabled(d['status'] not in ('Completed', 'Canceled', 'Checksum mismatch', 'Verifying') and (torrent or not self.obj.isRunning() or d['status'] in ('Downloading', 'Connecting')))
        self.cancel.setEnabled(d['status'] not in ('Completed', 'Canceled', 'Checksum mismatch') and not (torrent and d['status'] == 'Seeding'))
        self.open.setEnabled(d['status'] in ('Completed', 'Seeding') and os.path.exists(d['path']))

    def toggle(self):
        if self.data['kind'] == 'TORRENT':
            self.obj.resume() if self.data['status'] == 'Paused' else self.obj.pause()
        elif self.obj.isRunning(): self.obj.halt('Paused'); self.pause.setEnabled(False)
        else: self.obj.start()

    def cancel_transfer(self):
        if self.data['kind'] == 'TORRENT':
            self.owner.torrents.remove(self.obj); self.data['status'] = 'Canceled'; self.data['down'] = self.data['up'] = 0; self.update_data(self.data)
            self.owner.refresh_metrics()
        elif self.obj.isRunning(): self.obj.halt('Canceled'); self.cancel.setEnabled(False)
        else:
            if self.obj.path: Path(str(self.obj.path) + '.part').unlink(missing_ok=True)
            self.obj.status = 'Canceled'; self.obj.offset = 0; self.obj.emit_update()

    def review_hash(self):
        if self.obj.isRunning():
            QTimer.singleShot(100, self.review_hash); return
        dialog = QMessageBox(self)
        dialog.setWindowTitle('SHA-256 mismatch')
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText('The downloaded file does not match the expected SHA-256. It may be corrupt or altered.')
        dialog.setInformativeText(f"Expected: {self.obj.checksum}\nActual: {self.obj.actual_checksum}\n\nDiscard the file or keep it anyway?")
        discard = dialog.addButton('Discard file', QMessageBox.ButtonRole.DestructiveRole)
        keep = dialog.addButton('Keep anyway', QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton('Decide later', QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(discard); dialog.exec()
        if dialog.clickedButton() == keep: self.obj.resolve_mismatch(True)
        elif dialog.clickedButton() == discard: self.obj.resolve_mismatch(False)

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
        self.settings = QSettings('Nexus', 'DownloadManager'); self.cards = []; self.nav_buttons = {}; self.section = 'Dashboard'
        self.directory = self.settings.value('directory', str(Path.home() / 'Downloads'))
        self.torrents = TorrentEngine(); self.torrents.changed.connect(self.torrent_update)
        self.http_limiter = RateLimiter(); self.last_status = {}; self.clipboard_seen = ''
        self.tray = QSystemTrayIcon(QIcon(str(ROOT / 'assets/logo.svg')), self)
        self.notification_path = None
        self.tray.messageClicked.connect(self.open_notification)
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
        header = QHBoxLayout(); titles = QVBoxLayout(); titles.addWidget(label('YOUR TRANSFER SPACE', 'eyebrow')); self.heading = label('Dashboard', 'title'); titles.addWidget(self.heading); header.addLayout(titles); header.addStretch(); header.addWidget(label('●  SYSTEM READY', 'eyebrow')); ml.addLayout(header)
        self.content = QWidget(); self.content_layout = QVBoxLayout(self.content); self.content_layout.setContentsMargins(0,0,0,0); self.content_layout.setSpacing(16); ml.addWidget(self.content, 1)
        self.metrics = QWidget(); metrics_layout = QHBoxLayout(self.metrics); metrics_layout.setContentsMargins(0,0,0,0); metrics_layout.setSpacing(10); self.metric_values = []
        for title in ['DOWNLOAD SPEED','UPLOAD SPEED','ACTIVE TRANSFERS','COMPLETED']:
            frame = QFrame(); frame.setObjectName('metric'); fl = QVBoxLayout(frame); fl.setContentsMargins(16,14,16,14); fl.addWidget(label(title,'eyebrow')); value = label('0','metricValue'); fl.addWidget(value); self.metric_values.append(value); metrics_layout.addWidget(frame)
        self.content_layout.addWidget(self.metrics)
        self.add_panel = QFrame(); self.add_panel.setObjectName('panel'); al = QVBoxLayout(self.add_panel); al.setContentsMargins(18,16,18,17)
        row = QHBoxLayout(); row.addWidget(label('Start a transfer', 'filename')); row.addStretch(); row.addWidget(label('HTTP / HTTPS  ·  MAGNET  ·  TORRENT', 'eyebrow')); al.addLayout(row)
        row = QHBoxLayout(); self.url = QLineEdit(); self.url.setPlaceholderText('Paste a download URL or magnet link…'); self.url.returnPressed.connect(self.add_url); row.addWidget(self.url,1); row.addWidget(button('Add transfer  ↗',self.add_url,True)); row.addWidget(button('Open .torrent',self.add_torrent_file)); al.addLayout(row)
        self.hash_input = QLineEdit(); self.hash_input.setPlaceholderText('Optional SHA-256 for direct downloads (64 hex characters)'); al.addWidget(self.hash_input)
        self.destination = label('', 'muted'); al.addWidget(self.destination); self.content_layout.addWidget(self.add_panel)
        filters = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText('Search transfers…'); self.search.textChanged.connect(self.filter_cards); filters.addWidget(self.search, 1)
        self.filter = QComboBox(); self.filter.addItems(['All', 'Active', 'Completed', 'Failed', 'Torrents']); self.filter.currentTextChanged.connect(self.filter_cards); filters.addWidget(self.filter)
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
        self.clipboard_enabled = QCheckBox('Offer to add links copied to the clipboard'); self.clipboard_enabled.setChecked(self.settings.value('clipboard', False, type=bool)); self.clipboard_enabled.toggled.connect(lambda v: self.settings.setValue('clipboard',v)); se.addWidget(self.clipboard_enabled)
        se.addWidget(label('Notifications appear when your system tray is available. Click a completed notification to open the file.', 'muted')); se.addStretch(); self.content_layout.addWidget(self.settings_panel,1)
        self.navigate('Dashboard'); self.update_directory(); self.refresh_metrics(); self.update_limits()

    def navigate(self, section):
        self.section = section; self.heading.setText(section)
        for name,b in self.nav_buttons.items(): b.setChecked(name == section)
        settings = section == 'Settings'; self.settings_panel.setVisible(settings); self.scroll.setVisible(not settings); self.list_label.setVisible(not settings); self.add_panel.setVisible(not settings); self.filter_widget.setVisible(not settings); self.metrics.setVisible(section == 'Dashboard')
        self.filter_cards()
    def filter_cards(self, *args):
        count=0
        for c in self.cards:
            visible = self.section in ('Dashboard', 'Downloads')
            query = self.search.text().strip().lower(); selected = self.filter.currentText(); status = c.data['status']
            visible = visible and (not query or query in c.data['name'].lower() or query in c.data['path'].lower())
            visible = visible and (selected == 'All' or (selected == 'Active' and status in ('Connecting','Downloading','Fetching metadata','Verifying','Seeding')) or (selected == 'Completed' and status in ('Completed','Seeding')) or (selected == 'Failed' and status in ('Failed','Checksum mismatch')) or (selected == 'Torrents' and c.data['kind'] == 'TORRENT'))
            c.setVisible(visible); count += bool(visible)
        self.empty.setText('No transfers match your search or filter.' if self.cards else 'No transfers yet. Paste a link above to get started.')
        self.empty.setVisible(count == 0)
    def update_directory(self):
        self.destination.setText('SAVE TO  ·  ' + self.directory); self.path_label.setText(self.directory)
    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose download folder', self.directory)
        if path: self.directory = path; self.settings.setValue('directory',path); self.update_directory()
    def ensure_directory(self):
        p=Path(self.directory); p.mkdir(parents=True,exist_ok=True)
        if not p.is_dir() or not os.access(p,os.W_OK): raise ValueError('Download destination is not writable.')
    def add_url(self):
        url = self.url.text().strip()
        try:
            self.ensure_directory()
            checksum = self.hash_input.text().strip()
            if checksum and not re.fullmatch(r'[0-9a-fA-F]{64}', checksum): raise ValueError('SHA-256 must be exactly 64 hexadecimal characters.')
            if url.startswith('magnet:?'):
                if checksum: raise ValueError('SHA-256 verification is available for direct downloads only. Torrents use their own piece verification.')
                self.add_torrent(url)
            else:
                parsed=urlsplit(url)
                if parsed.scheme not in ('http','https') or not parsed.hostname: raise ValueError('Enter a valid HTTP, HTTPS, or magnet link.')
                worker=HttpWorker(url,self.directory,self.http_limiter,checksum); card=TransferCard(self,worker,worker.snapshot()); self.add_card(card); worker.changed.connect(card.update_data); worker.changed.connect(lambda data, c=card: self.transfer_changed(c, data)); worker.start()
            self.url.clear(); self.hash_input.clear()
        except Exception as e: QMessageBox.warning(self,'Could not start transfer',str(e))
    def add_torrent_file(self):
        if self.hash_input.text().strip():
            QMessageBox.information(self, 'SHA-256 verification', 'The SHA-256 field applies to direct downloads. Clear it before adding a torrent; torrents verify their pieces automatically.'); return
        path,_=QFileDialog.getOpenFileName(self,'Open torrent file','','Torrent files (*.torrent)')
        if path:
            try: self.ensure_directory(); self.add_torrent(path)
            except Exception as e: QMessageBox.warning(self,'Could not open torrent',str(e))
    def add_torrent(self, source):
        h=self.torrents.add(source,self.directory)
        d=dict(name='Fetching metadata…',kind='TORRENT',status='Fetching metadata',done=0,total=0,down=0,up=0,uploaded=0,path=self.directory,error='')
        self.add_card(TransferCard(self,h,d)); self.torrents.poll()
    def torrent_update(self,h,data):
        for c in self.cards:
            if c.data['kind']=='TORRENT' and c.obj==h: c.update_data(data); self.transfer_changed(c, data); break
        self.refresh_metrics()
    def add_card(self,c): self.cards.append(c); self.list_layout.insertWidget(self.list_layout.count()-1,c); self.filter_cards(); self.refresh_metrics(); self.update_limits()
    def remove_card(self,c): self.last_status.pop(c, None); self.cards.remove(c); self.list_layout.removeWidget(c); c.deleteLater(); self.filter_cards(); self.refresh_metrics(); self.update_limits()
    def refresh_metrics(self,*args):
        ds=[c.data for c in self.cards]; values=[readable(sum(x['down'] for x in ds))+'/s',readable(sum(x['up'] for x in ds))+'/s',str(sum(x['status'] in ('Downloading','Connecting','Fetching metadata','Seeding') for x in ds)),str(sum(x['status'] in ('Completed','Seeding') for x in ds))]
        for w,v in zip(self.metric_values,values): w.setText(v)
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
        if old != new:
            self.filter_cards(); self.update_limits()
            if new == 'Checksum mismatch': QTimer.singleShot(0, card.review_hash)
            if new in ('Completed', 'Seeding', 'Failed') and old not in ('Completed', 'Seeding', 'Failed'):
                self.notification_path = data['path'] if new in ('Completed', 'Seeding') else None
                if self.tray.isVisible(): self.tray.showMessage("Z's Download Manager", f"{data['name']}: {new}." + (' Click to open.' if self.notification_path else ''), QSystemTrayIcon.MessageIcon.Information, 10000)
        self.refresh_metrics()

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
        workers=[c.obj for c in self.cards if c.data['kind']=='HTTP' and c.obj.isRunning()]
        for w in workers: w.halt('Paused')
        for w in workers: w.wait(17000)
        event.accept()
