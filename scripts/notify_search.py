#!/usr/bin/env python3
"""Notify IndexNow after deployment; a receipt is not an indexing guarantee.

State is private, durable, and independent of the deployed directory. Only the
standard library is used. No request is made when the canonical content hashes
have not changed. --dry-run neither contacts the network nor writes any files.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_ENDPOINT = 'https://api.indexnow.org/indexnow'
BATCH_SIZE = 10000
HASH = re.compile(r'^[0-9a-fA-F]{64}$')
KEY = re.compile(r'^[a-zA-Z0-9-]{8,128}$')


class InvalidInput(ValueError):
    """Messages are fixed labels: never expose input or the verification key."""


class NotificationError(Exception):
    def __init__(self, status, http_status=None):
        self.status = status
        self.http_status = http_status


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def secure_url(value):
    if not isinstance(value, str) or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        raise InvalidInput('invalid HTTPS URL')
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError()
    except ValueError:
        raise InvalidInput('invalid HTTPS URL') from None
    return parsed


def site_origin(value):
    parsed = secure_url(value)
    if parsed.path not in ('', '/') or parsed.query:
        raise InvalidInput('site must be an HTTPS origin')
    return 'https://' + parsed.netloc.lower()


def canonical_url(value, site):
    parsed = secure_url(value)
    origin = urlsplit(site)
    if parsed.hostname != origin.hostname or parsed.netloc.lower() != origin.netloc or parsed.query:
        raise InvalidInput('canonical URL is outside the site or contains a query')
    if not parsed.path.startswith('/'):
        raise InvalidInput('canonical URL requires an absolute path')


def content_hash(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise InvalidInput('invalid content hash')
    return value.lower()


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('pages'), dict):
        raise InvalidInput('invalid manifest')
    site = site_origin(data.get('site'))
    pages = {}
    for url, meta in data['pages'].items():
        canonical_url(url, site)
        if not isinstance(meta, dict):
            raise InvalidInput('invalid page metadata')
        pages[url] = content_hash(meta.get('hash'))
    return site, pages


def load_state(path, site):
    if not Path(path).exists():
        return {'version': 1, 'site': site, 'known': {}, 'pending': {}, 'submissions': []}
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(state, dict) or state.get('version') != 1 or state.get('site') != site
            or not isinstance(state.get('known'), dict)
            or not isinstance(state.get('pending'), dict)
            or not isinstance(state.get('submissions'), list)):
        raise InvalidInput('invalid state or state belongs to a different site')
    for url, value in state['known'].items():
        canonical_url(url, site)
        content_hash(value)
    for url, item in state['pending'].items():
        canonical_url(url, site)
        if not isinstance(item, dict) or item.get('change') not in ('added', 'changed', 'deleted'):
            raise InvalidInput('invalid pending queue')
        if item['change'] == 'deleted':
            if item.get('hash') is not None:
                raise InvalidInput('invalid pending deletion')
        else:
            content_hash(item.get('hash'))
    return state


def reconcile(state, pages):
    """Retry only changes that still apply to the latest deployed manifest."""
    pending = {}
    for url in sorted(set(state['known']) | set(pages)):
        old, new = state['known'].get(url), pages.get(url)
        if old == new:
            continue
        change = 'deleted' if new is None else 'added' if old is None else 'changed'
        previous = state['pending'].get(url, {})
        queued_at = previous.get('queued_at') if previous.get('hash') == new else None
        pending[url] = {'hash': new, 'change': change, 'queued_at': queued_at or timestamp()}
    state['pending'] = pending
    return pending


def save_state(path, state):
    """Write a private temporary file and atomically replace the state file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '.', delete=False) as out:
            temporary = Path(out.name)
            json.dump(state, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def state_lock(path):
    """Serialize deployment/manual retries sharing the same state file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(request):
    # A redirect must not silently move key verification or the POST elsewhere.
    return build_opener(NoRedirect).open(request, timeout=20)


def load_key(path):
    raw = Path(path).read_bytes()
    try:
        key = raw.decode('ascii').strip()
    except UnicodeDecodeError:
        raise InvalidInput('invalid key file') from None
    if not KEY.fullmatch(key) or raw not in (key.encode(), (key + '\n').encode(), (key + '\r\n').encode()):
        raise InvalidInput('invalid key file')
    return key, raw


def verify_key(site, key, expected):
    location = site + '/' + key + '.txt'
    request = Request(location, headers={'Cache-Control': 'no-cache', 'User-Agent': '6yuan-IndexNow/1.0'})
    with open_request(request) as response:
        if response.status != 200:
            raise NotificationError('key_verification_failed', response.status)
        if response.read(len(expected) + 1) != expected:
            raise NotificationError('key_content_mismatch')
    return location


def record(state, status, count, http_status=None):
    item = {'timestamp': timestamp(), 'status': status, 'count': count}
    if http_status is not None:
        item['http_status'] = http_status
    state['submissions'].append(item)


def failure(state, path, error, count, phase):
    if isinstance(error, NotificationError):
        status, code = error.status, error.http_status
    elif isinstance(error, HTTPError):
        status, code = phase + '_failed', error.code
    else:
        status, code = phase + '_failed', None
    record(state, status, count, code)
    save_state(path, state)
    label = ' HTTP ' + str(code) if code is not None else ''
    print(f'IndexNow: {status}{label}; {len(state["pending"])} URL(s) retained for retry.')
    return 1


def run(manifest, state_path, key_file, endpoint=DEFAULT_ENDPOINT, dry_run=False):
    site, pages = load_manifest(manifest)
    secure_url(endpoint)
    if dry_run:
        state = load_state(state_path, site)
        pending = reconcile(state, pages)
        counts = {kind: sum(item['change'] == kind for item in pending.values())
                  for kind in ('added', 'changed', 'deleted')}
        print('IndexNow dry run: ' + ', '.join(f'{key}={value}' for key, value in counts.items()))
        for url, item in pending.items():
            print(f'{item["change"]}: {url}')
        return 0
    with state_lock(state_path):
        state = load_state(state_path, site)
        pending = reconcile(state, pages)
        if not pending:
            # Reconciliation may have cancelled changes from an earlier failed run.
            if Path(state_path).exists():
                save_state(state_path, state)
            print('IndexNow: no changes; no network request.')
            return 0
        save_state(state_path, state)
        try:
            key, raw = load_key(key_file)
            location = verify_key(site, key, raw)
        except Exception as error:
            return failure(state, state_path, error, len(pending), 'key_verification')
        urls = list(pending)
        for start in range(0, len(urls), BATCH_SIZE):
            batch = urls[start:start + BATCH_SIZE]
            payload = {'host': urlsplit(site).hostname, 'key': key,
                       'keyLocation': location, 'urlList': batch}
            request = Request(endpoint, data=json.dumps(payload).encode('utf-8'),
                              headers={'Content-Type': 'application/json; charset=utf-8',
                                       'User-Agent': '6yuan-IndexNow/1.0'}, method='POST')
            try:
                with open_request(request) as response:
                    code = response.status
                if code not in (200, 202):
                    raise NotificationError('submission_failed', code)
            except Exception as error:
                return failure(state, state_path, error, len(batch), 'submission')
            for url in batch:
                item = state['pending'].pop(url)
                if item['hash'] is None:
                    state['known'].pop(url, None)
                else:
                    state['known'][url] = item['hash']
            status = 'pending_key_validation' if code == 202 else 'received'
            record(state, status, len(batch), code)
            save_state(state_path, state)
            print(f'IndexNow: {len(batch)} URL(s) {status} (HTTP {code}); receipt is not indexing confirmation.')
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        return run(args.manifest, args.state, args.key_file, args.endpoint, args.dry_run)
    except InvalidInput as error:
        print('IndexNow: ' + str(error) + '; nothing submitted.')
    except Exception as error:
        # Exception text can contain the key URL. Only emit the exception type.
        print(f'IndexNow: local failure ({type(error).__name__}); check inputs/state and retry.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
