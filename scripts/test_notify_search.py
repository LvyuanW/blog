"""Offline tests: no test performs an actual IndexNow or site request."""
import contextlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import notify_search as notify

SITE = 'https://example.test'
KEY = 'server-only-key-123456'
HASH_A = 'a' * 64
HASH_B = 'b' * 64


class Response:
    def __init__(self, status=200, body=b''):
        self.status, self.body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count=-1):
        return self.body if count < 0 else self.body[:count]


class NotifySearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'manifest.json'
        self.state = self.root / 'private/state.json'
        self.key = self.root / 'key.txt'
        self.key.write_bytes((KEY + '\n').encode())
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)
        self.network = patch.object(notify, 'open_request').start()
        self.addCleanup(patch.stopall)
        self.network.side_effect = self.success

    def success(self, request):
        return Response(body=self.key.read_bytes()) if request.get_method() == 'GET' else Response()

    def manifest_with(self, pages):
        self.manifest.write_text(json.dumps({'site': SITE, 'pages': {
            url: {'hash': digest, 'published': '2026-01-01', 'modified': '2026-01-02'}
            for url, digest in pages.items()}}))

    def execute(self, *extra):
        return notify.main(['--manifest', str(self.manifest), '--state', str(self.state),
                            '--key-file', str(self.key), *extra])

    def saved(self):
        return json.loads(self.state.read_text())

    def posts(self):
        return [json.loads(c.args[0].data) for c in self.network.call_args_list
                if c.args[0].get_method() == 'POST']

    def test_initial_submission_and_no_duplicate_submission(self):
        pages = {SITE + '/': HASH_A, SITE + '/library/example/': HASH_B}
        self.manifest_with(pages)
        self.assertEqual(self.execute(), 0)
        self.assertEqual([c.args[0].get_method() for c in self.network.call_args_list], ['GET', 'POST'])
        self.assertEqual(set(self.posts()[0]['urlList']), set(pages))
        self.assertEqual(self.posts()[0]['host'], 'example.test')
        self.assertEqual(self.posts()[0]['keyLocation'], SITE + '/' + KEY + '.txt')
        self.assertEqual(self.saved()['known'], pages)
        self.assertEqual(self.saved()['pending'], {})
        self.assertEqual(self.saved()['submissions'][0]['status'], 'received')
        self.network.reset_mock()
        self.assertEqual(self.execute(), 0)
        self.network.assert_not_called()
        self.assertEqual(len(self.saved()['submissions']), 1)
        self.assertNotIn(KEY, self.output.getvalue())
        self.assertNotIn(KEY, self.state.read_text())
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)

    def test_changes_and_deletions(self):
        self.manifest_with({SITE + '/same/': HASH_A, SITE + '/change/': HASH_A,
                            SITE + '/remove/': HASH_A})
        self.assertEqual(self.execute(), 0)
        self.network.reset_mock()
        current = {SITE + '/same/': HASH_A, SITE + '/change/': HASH_B,
                   SITE + '/new/': HASH_A}
        self.manifest_with(current)
        self.assertEqual(self.execute(), 0)
        self.assertEqual(set(self.posts()[0]['urlList']),
                         {SITE + '/change/', SITE + '/remove/', SITE + '/new/'})
        self.assertEqual(self.saved()['known'], current)
        self.assertEqual(self.saved()['pending'], {})

    def test_failed_submission_is_durable_and_retried(self):
        self.manifest_with({SITE + '/new/': HASH_A})
        self.network.side_effect = [Response(body=self.key.read_bytes()), Response(503)]
        self.assertEqual(self.execute(), 1)
        first = self.saved()
        self.assertEqual(first['known'], {})
        self.assertEqual(first['pending'][SITE + '/new/']['change'], 'added')
        self.assertEqual(first['submissions'][-1]['http_status'], 503)
        self.network.reset_mock()
        self.network.side_effect = self.success
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.posts()[0]['urlList'], [SITE + '/new/'])
        self.assertEqual(self.saved()['pending'], {})
        self.assertEqual([s['status'] for s in self.saved()['submissions']],
                         ['submission_failed', 'received'])

    def test_failed_deletion_is_cancelled_when_page_returns(self):
        self.manifest_with({SITE + '/page/': HASH_A})
        self.assertEqual(self.execute(), 0)
        self.manifest_with({})
        self.network.side_effect = [Response(body=self.key.read_bytes()), Response(429)]
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.saved()['pending'][SITE + '/page/']['change'], 'deleted')
        self.manifest_with({SITE + '/page/': HASH_A})
        self.network.reset_mock()
        self.assertEqual(self.execute(), 0)
        self.network.assert_not_called()
        self.assertEqual(self.saved()['pending'], {})

    def test_202_is_receipt_with_pending_key_validation(self):
        self.manifest_with({SITE + '/': HASH_A})
        self.network.side_effect = [Response(body=self.key.read_bytes()), Response(202)]
        self.assertEqual(self.execute(), 0)
        event = self.saved()['submissions'][-1]
        self.assertEqual(event['status'], 'pending_key_validation')
        self.assertEqual(event['http_status'], 202)
        self.assertEqual(event['count'], 1)
        self.assertIn('timestamp', event)
        self.assertEqual(self.saved()['known'], {SITE + '/': HASH_A})
        self.assertEqual(self.saved()['pending'], {})
        self.assertIn('not indexing confirmation', self.output.getvalue())
        self.network.reset_mock()
        self.assertEqual(self.execute(), 0)
        self.network.assert_not_called()

    def test_no_changes_does_not_read_key_or_use_network(self):
        self.manifest_with({})
        self.key.unlink()
        self.assertEqual(self.execute(), 0)
        self.network.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_invalid_canonical_urls_never_reach_network(self):
        urls = ['https://foreign.test/page/', 'http://example.test/page/',
                'https://example.test.foreign.test/page/', 'https://name@example.test/page/',
                SITE + '/page/#section', SITE + '/page/?lang=en',
                'https://example.test:8443/page/', 'https://example.test/\\evil',
                'https://example.test/\npage/']
        for url in urls:
            with self.subTest(url=url):
                self.manifest_with({url: HASH_A})
                self.assertEqual(self.execute(), 1)
                self.network.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_invalid_state_cannot_submit_foreign_deletions(self):
        self.manifest_with({})
        self.state.parent.mkdir()
        self.state.write_text(json.dumps({'version': 1, 'site': SITE,
                                         'known': {'https://foreign.test/': HASH_A},
                                         'pending': {}, 'submissions': []}))
        before = self.state.read_bytes()
        self.assertEqual(self.execute(), 1)
        self.network.assert_not_called()
        self.assertEqual(before, self.state.read_bytes())

    def test_dry_run_shows_delta_without_network_or_writes(self):
        self.manifest_with({SITE + '/change/': HASH_A, SITE + '/remove/': HASH_A})
        self.assertEqual(self.execute(), 0)
        before = self.state.read_bytes()
        self.network.reset_mock()
        self.manifest_with({SITE + '/change/': HASH_B, SITE + '/new/': HASH_A})
        self.key.unlink()
        self.assertEqual(self.execute('--dry-run'), 0)
        self.network.assert_not_called()
        self.assertEqual(before, self.state.read_bytes())
        self.assertIn('added=1, changed=1, deleted=1', self.output.getvalue())
        for url in ['/change/', '/new/', '/remove/']:
            self.assertIn(SITE + url, self.output.getvalue())

    def test_first_dry_run_creates_no_state_or_lock_directory(self):
        self.manifest_with({SITE + '/': HASH_A})
        self.assertEqual(self.execute('--dry-run'), 0)
        self.assertFalse(self.state.parent.exists())
        self.network.assert_not_called()

    def test_key_mismatch_keeps_queue_and_prevents_post(self):
        self.manifest_with({SITE + '/': HASH_A})
        self.network.side_effect = [Response(body=KEY.encode())]  # Missing newline: not exact.
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.saved()['submissions'][-1]['status'], 'key_content_mismatch')
        self.assertEqual(len(self.saved()['pending']), 1)
        self.assertNotIn(KEY, self.output.getvalue())

    def test_http_error_and_network_exception_do_not_expose_key(self):
        self.manifest_with({SITE + '/': HASH_A})
        error = HTTPError(SITE + '/' + KEY + '.txt', 404, KEY, {}, None)
        self.network.side_effect = error
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.saved()['submissions'][-1]['http_status'], 404)
        self.network.side_effect = [Response(body=self.key.read_bytes()), URLError(KEY)]
        self.assertEqual(self.execute(), 1)
        self.assertNotIn(KEY, self.output.getvalue())
        self.assertNotIn(KEY, self.state.read_text())
        self.assertEqual(len(self.saved()['pending']), 1)

    def test_max_batch_size_and_partial_failure_retries_only_remainder(self):
        pages = {SITE + f'/page/{i}/': HASH_A for i in range(10001)}
        self.manifest_with(pages)
        self.network.side_effect = [Response(body=self.key.read_bytes()), Response(200), Response(429)]
        self.assertEqual(self.execute(), 1)
        self.assertEqual([len(p['urlList']) for p in self.posts()], [10000, 1])
        state = self.saved()
        self.assertEqual(len(state['known']), 10000)
        self.assertEqual(len(state['pending']), 1)
        remainder = list(state['pending'])
        self.network.reset_mock()
        self.network.side_effect = self.success
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.posts()[0]['urlList'], remainder)
        self.assertEqual(self.saved()['known'], pages)
        self.assertEqual(self.saved()['pending'], {})

    def test_atomic_write_failure_preserves_existing_state(self):
        self.manifest_with({SITE + '/': HASH_A})
        self.assertEqual(self.execute(), 0)
        before = self.state.read_bytes()
        with patch.object(notify.os, 'replace', side_effect=OSError('disk failure')):
            self.assertEqual(self.execute(), 1)
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual(list(self.state.parent.glob('.state.json.*')), [])

    def test_redirect_handler_refuses_redirect(self):
        self.assertIsNone(notify.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.test/'))


if __name__ == '__main__':
    unittest.main()
