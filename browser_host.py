"""Chromium native-messaging host. Never starts a download itself."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from urllib.parse import urlsplit

EXTENSION_ORIGIN = 'chrome-extension://jjmhgefmdphjpchjedibmohiondjpgab/'
MAX_MESSAGE = 16384


def validate_url(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Invalid link')
    parsed = urlsplit(value)
    if parsed.scheme in ('http', 'https'):
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError('Invalid HTTP link')
    elif parsed.scheme == 'magnet':
        if not value.startswith('magnet:?') or not parsed.query:
            raise ValueError('Invalid magnet link')
    else:
        raise ValueError('Only HTTP, HTTPS and magnet links are supported')
    return value


def read_message(stream):
    header = stream.read(4)
    if len(header) != 4: raise ValueError('Missing message header')
    size = struct.unpack('<I', header)[0]
    if not 1 <= size <= MAX_MESSAGE: raise ValueError('Invalid message length')
    body = stream.read(size)
    if len(body) != size: raise ValueError('Incomplete message')
    request = json.loads(body.decode('utf-8'))
    if not isinstance(request, dict) or set(request) != {'url'}: raise ValueError('Invalid message')
    return validate_url(request['url'])


def write_message(stream, payload):
    data = json.dumps(payload, ensure_ascii=True).encode('utf-8')
    stream.write(struct.pack('<I', len(data)) + data)
    stream.flush()


def main():
    source = sys.stdin.buffer
    destination = sys.stdout.buffer
    try:
        if len(sys.argv) < 2 or sys.argv[1] != EXTENSION_ORIGIN:
            raise ValueError('Extension origin is not authorized')
        url = read_message(source)
        root = Path(sys.executable).resolve().parent
        app = root / 'NexusDownloadManager.exe'
        if not getattr(sys, 'frozen', False) or not app.is_file():
            raise ValueError('Installed download manager was not found')
        subprocess.Popen([str(app), '--browser-url', url], close_fds=True)
        write_message(destination, {'ok': True, 'message': 'Link sent. Review it in Z’s Download Manager.'})
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        write_message(destination, {'ok': False, 'message': str(exc)})

if __name__ == '__main__':
    main()
