import base64
import hashlib
import io
import json
import struct
from pathlib import Path
from browser_host import EXTENSION_ORIGIN, read_message, validate_url, write_message

manifest = json.loads(Path('browser-extension/manifest.json').read_text())
digest = hashlib.sha256(base64.b64decode(manifest['key'])).digest()[:16]
id = ''.join(chr(97 + (b >> 4)) + chr(97 + (b & 15)) for b in digest)
host = json.loads(Path('browser-extension/native-host.json').read_text())
assert host['allowed_origins'] == [f'chrome-extension://{id}/'] == [EXTENSION_ORIGIN]
assert not manifest.get('externally_connectable') and not manifest.get('content_scripts')
for url in ('https://example.org/file.zip', 'magnet:?xt=urn:btih:1234'):
    body = json.dumps({'url': url}).encode(); assert read_message(io.BytesIO(struct.pack('<I', len(body))+body)) == url
for url in ('file:///C:/test', 'http://user:pass@example.org/', 'http://example.org/\nhi', 'javascript:alert(1)', 'https://' + 'x'*5000):
    try: validate_url(url)
    except ValueError: pass
    else: raise AssertionError(f'Unsafe URL accepted: {url}')
for payload in (struct.pack('<I', 20000), struct.pack('<I', 10) + b'{}', struct.pack('<I', 2) + b'{}'):
    try: read_message(io.BytesIO(payload))
    except ValueError: pass
    else: raise AssertionError('Malformed native message accepted')
out=io.BytesIO(); write_message(out, {'ok': True}); data=out.getvalue(); assert struct.unpack('<I', data[:4])[0] == len(data)-4
print('Native-message framing, allowlist, and input validation: PASS')
# Exercise host authorization and process invocation with in-memory browser pipes.
import sys, tempfile
from unittest.mock import patch
import browser_host
class Pipe:
    def __init__(self, raw): self.buffer = raw
body=json.dumps({'url':'https://example.org/file'}).encode()
wire=struct.pack('<I',len(body))+body
with tempfile.TemporaryDirectory() as tmp:
    executable=Path(tmp)/'ZBrowserHost.exe'; executable.touch(); (Path(tmp)/'NexusDownloadManager.exe').touch()
    for origin, allowed in [('chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/',False),(EXTENSION_ORIGIN,True)]:
        inp, out = Pipe(io.BytesIO(wire)), Pipe(io.BytesIO())
        with patch.object(sys,'argv',['host',origin]), patch.object(sys,'stdin',inp), patch.object(sys,'stdout',out), patch.object(sys,'executable',str(executable)), patch.object(sys,'frozen',True,create=True), patch.object(browser_host.subprocess,'Popen') as spawn:
            browser_host.main()
        response=json.loads(out.buffer.getvalue()[4:]); assert response['ok']==allowed
        assert spawn.called==allowed
        if allowed: assert spawn.call_args.args[0][1:] == ['--browser-url','https://example.org/file']
print('Unauthorized origin rejected; authorized request only opens app review: PASS')
