"""Side-effect-free transfer preparation and retry policy."""
import re
from urllib.parse import urlsplit, parse_qs

MAX_BATCH = 500

def validate_transfer_url(value):
    url = value.strip()
    if not url or len(url) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError('Empty, too long, or contains control characters')
    parsed = urlsplit(url)
    if parsed.scheme in ('http', 'https'):
        if not parsed.hostname: raise ValueError('HTTP link needs a hostname')
        try: parsed.port
        except ValueError: raise ValueError('Invalid port') from None
    elif parsed.scheme == 'magnet':
        if not url.startswith('magnet:?') or not any(x.lower().startswith('urn:') for x in parse_qs(parsed.query).get('xt', [])):
            raise ValueError('Magnet link needs an exact-topic identifier')
    else:
        raise ValueError('Use an HTTP, HTTPS, or magnet link')
    return url

def prepare_batch(text, existing=()):
    if len(text.encode('utf-8')) > 1024 * 1024: raise ValueError('Batch input exceeds 1 MiB')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > MAX_BATCH: raise ValueError(f'Batch is limited to {MAX_BATCH} links')
    seen = set(existing); accepted = []; rejected = []
    for number, line in enumerate(lines, 1):
        try:
            url = validate_transfer_url(line)
            if url in seen: raise ValueError('Duplicate link')
            seen.add(url); accepted.append(url)
        except ValueError as exc:
            # Report line numbers and reason, not potentially sensitive URLs.
            rejected.append((number, str(exc)))
    return accepted, rejected

def retry_delay(attempt, base=15, maximum=300):
    return min(maximum, base * 2 ** min(max(0, attempt - 1), 10))

def validate_profile(raw):
    if not isinstance(raw, dict): raise ValueError('Invalid profile')
    directory = raw.get('directory')
    if not isinstance(directory, str) or not directory or len(directory) > 4096:
        raise ValueError('Invalid destination')
    limits = {}
    for name, lower, upper in [('down_limit',0,1000000),('up_limit',0,1000000),('queue_limit',1,20),('retry_limit',0,100)]:
        value = raw.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not lower <= value <= upper:
            raise ValueError(f'Invalid {name}')
        limits[name] = value
    for name in ('organize','extract_zip'):
        if not isinstance(raw.get(name), bool): raise ValueError(f'Invalid {name}')
        limits[name] = raw[name]
    return dict(directory=directory, **limits)
