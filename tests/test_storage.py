import hashlib
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from dmlocal.storage import _download_one, hf_url

PAYLOAD = b"the pinned model fixture"
SEEN_RANGES = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        range_value = self.headers.get("Range")
        SEEN_RANGES.append(range_value)
        if range_value:
            offset = int(range_value.split("=", 1)[1].split("-", 1)[0])
            body = PAYLOAD[offset:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {offset}-{len(PAYLOAD)-1}/{len(PAYLOAD)}")
        else:
            body = PAYLOAD
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass


class StorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/fixture"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def opener(self, request, timeout=10):
        forwarded = Request(self.url, headers=dict(request.header_items()))
        return urlopen(forwarded, timeout=timeout)

    def test_hf_url_preserves_repo_namespace_and_pinned_revision(self):
        self.assertEqual(hf_url("owner/model", "a" * 40, "sub/model.bin"),
                         "https://huggingface.co/owner/model/resolve/" + "a" * 40 + "/sub/model.bin")

    def test_download_resumes_with_http_range_and_verifies(self):
        SEEN_RANGES.clear()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "model.bin"
            target.with_name("model.bin.part").write_bytes(PAYLOAD[:7])
            spec = {"path": "model.bin", "size": len(PAYLOAD), "sha256": hashlib.sha256(PAYLOAD).hexdigest()}
            self.assertEqual(_download_one(spec, target, "owner/model", "a" * 40, opener=self.opener), target)
            self.assertTrue(any(x == "bytes=7-" for x in SEEN_RANGES))
            self.assertEqual(target.read_bytes(), PAYLOAD)
            self.assertFalse(target.with_name("model.bin.part").exists())

    def test_bad_sha256_is_rejected_and_partial_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "model.bin"
            spec = {"path": "model.bin", "size": len(PAYLOAD), "sha256": "0" * 64}
            with self.assertRaisesRegex(OSError, "SHA-256 mismatch"):
                _download_one(spec, target, "owner/model", "a" * 40, opener=self.opener, retries=1)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name("model.bin.part").exists())


if __name__ == "__main__": unittest.main()
