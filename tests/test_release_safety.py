import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request

from dmlocal import licence, storage
from tests.helpers import model_with_variants, variant


class ReleaseSafetyTests(unittest.TestCase):
    def test_model_redirect_keeps_token_only_on_same_origin(self):
        handler = storage._DownloadRedirect()
        request = Request("https://huggingface.co/a/b/resolve/pin/weights", headers={"Authorization": "Bearer private"})
        other = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example/weights?signed=yes")
        self.assertIsNone(other.get_header("Authorization"))
        same = handler.redirect_request(request, None, 302, "Found", {}, "https://huggingface.co/new")
        self.assertEqual(same.get_header("Authorization"), "Bearer private")
        with self.assertRaises(URLError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://cdn.example/weights")

    def test_completed_partial_is_verified_without_another_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "weights.bin"
            partial = target.with_name("weights.bin.part")
            partial.write_bytes(b"model")
            spec = {"path": "weights.bin", "size": 5, "sha256": storage.sha256_file(partial)}
            def no_network(*a, **k):
                self.fail("a fully verified partial should not download again")
            storage._download_one(spec, target, "a/b", "1" * 40, opener=no_network)
            self.assertEqual(target.read_bytes(), b"model")
            self.assertFalse(partial.exists())

    def test_explicit_revocation_does_not_receive_network_grace(self):
        class Rejected:
            def read(self): return b'{"valid":false}'
            def __enter__(self): return self
            def __exit__(self, *a): pass
        with tempfile.TemporaryDirectory() as tmp:
            now = 1_800_000_000
            config = {"usage": "company", "licence": {"key": "stored", "valid": True, "verified_at": now - 31 * 86400}}
            (Path(tmp) / "config.json").write_text(json.dumps(config))
            with patch.object(licence.time, "time", return_value=now):
                with self.assertRaises(licence.LicenceRejected):
                    licence.require_install(model_with_variants([variant()]), tmp, accept=True, opener=lambda *a, **k: Rejected())
