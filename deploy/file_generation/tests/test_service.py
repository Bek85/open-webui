import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import service
from fastapi.testclient import TestClient


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.key = b'test-key-not-for-production-1234567890'
        (root / 'key').write_bytes(self.key)
        self.paths = patch.multiple(service, DATA=root / 'data', KEY_PATH=root / 'key')
        self.paths.start()
        self.client = TestClient(service.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.paths.stop()
        self.temp.cleanup()

    def headers(self, method, path, owner='user1', body=b'', timestamp=None):
        timestamp = str(timestamp or int(time.time()))
        canonical = '\n'.join((method, path, owner, timestamp, hashlib.sha256(body).hexdigest()))
        return {
            'X-File-Owner': owner,
            'X-File-Time': timestamp,
            'X-File-Signature': hmac.new(self.key, canonical.encode(), hashlib.sha256).hexdigest(),
            'Content-Type': 'application/json',
        }

    def create(self):
        body = json.dumps({'format': 'docx', 'title': 'Синов', 'content': 'Ҳуқуқий таҳлил'}).encode()
        response = self.client.post('/render', content=body, headers=self.headers('POST', '/render', body=body))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_owner_only_download(self):
        item = self.create()
        path = '/files/' + item['id']
        owner = self.client.get(path, headers=self.headers('GET', path))
        self.assertEqual(owner.status_code, 200)
        self.assertTrue(owner.content.startswith(b'PK'))
        self.assertIn('attachment', owner.headers['content-disposition'])
        self.assertEqual(owner.headers['cache-control'], 'private, no-store')
        self.assertEqual(self.client.get(path, headers=self.headers('GET', path, owner='user2')).status_code, 404)
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_signature_binds_owner_body_path_and_timestamp(self):
        body = b'{"format":"docx","title":"x","content":"y"}'
        headers = self.headers('POST', '/render', body=body)
        self.assertEqual(self.client.post('/render', content=body + b' ', headers=headers).status_code, 401)
        headers['X-File-Owner'] = 'user2'
        self.assertEqual(self.client.post('/render', content=body, headers=headers).status_code, 401)
        headers = self.headers('POST', '/render', body=body, timestamp=int(time.time()) - 120)
        self.assertEqual(self.client.post('/render', content=body, headers=headers).status_code, 401)

    def test_expiry_and_cleanup_only_generated_files(self):
        item = self.create()
        path = '/files/' + item['id']
        keep = service.DATA / 'unrelated.txt'
        keep.write_text('preserve')
        with service.database() as db:
            db.execute('UPDATE artifacts SET expires_at=0 WHERE id=?', (item['id'],))
        self.assertEqual(self.client.get(path, headers=self.headers('GET', path)).status_code, 410)
        service.cleanup()
        self.assertFalse(service.artifact_path(item['id'], 'docx').exists())
        self.assertEqual(keep.read_text(), 'preserve')
        self.assertEqual(self.client.get(path, headers=self.headers('GET', path)).status_code, 404)

    def test_request_size_and_format_limits(self):
        self.assertEqual(self.client.post('/render', content=b'x' * (service.MAX_BODY + 1)).status_code, 413)
        body = b'{"format":"exe","title":"x","content":"x"}'
        self.assertEqual(
            self.client.post('/render', content=body, headers=self.headers('POST', '/render', body=body)).status_code,
            422,
        )

    def test_quota(self):
        with patch.object(service, 'QUOTA_BYTES', 1):
            body = b'{"format":"docx","title":"x","content":"x"}'
            self.assertEqual(
                self.client.post(
                    '/render', content=body, headers=self.headers('POST', '/render', body=body)
                ).status_code,
                429,
            )


if __name__ == '__main__':
    unittest.main()
