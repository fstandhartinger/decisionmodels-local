"""Only synthetic fixture patches and archives; never imports author source."""
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dmlocal.runtimes.recipe import RecipeRuntime, _contained_path
from dmlocal.runtimes.textpatch import apply_text_patch
from dmlocal.runtime_selection import recipe_errors
from tests.helpers import model_with_variants, variant

DIFF = b'diff --git a/file.txt b/file.txt\nindex aaaaaaa..bbbbbbb 100644\n--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n'
NEW = b'diff --git a/new.txt b/new.txt\nnew file mode 100644\nindex 0000000..aaaaaaa\n--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+added\n'


class TextPatchTests(unittest.TestCase):
    def fixture(self, tmp, data=DIFF):
        v = variant()
        rt = RecipeRuntime(model_with_variants([v]), v, tmp)
        rt.weights.mkdir(parents=True)
        (rt.weights / 'serve.patch').write_bytes(data)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            info = tarfile.TarInfo('root/file.txt')
            info.size = 4
            tar.addfile(info, io.BytesIO(b'old\n'))
        raw = archive.getvalue()
        spec = dict(source='github', repo='own/fixture', revision='a'*40,
                    sha256=hashlib.sha256(raw).hexdigest(), dest='code/fixture',
                    patch=dict(path='serve.patch', sha256=hashlib.sha256(data).hexdigest(), tree_sha256='c'*64))
        inventory = {'file.txt':hashlib.sha256(b'new\n').hexdigest()}
        if data == DIFF + NEW:
            inventory['new.txt'] = hashlib.sha256(b'added\n').hexdigest()
        spec['patch']['tree_sha256'] = hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return rt, spec, raw

    def test_valid_and_repeated_prepare_checks_exact_tree_without_redownload(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt, spec, raw = self.fixture(tmp, DIFF + NEW)
            with patch('urllib.request.urlopen', return_value=io.BytesIO(raw)) as download:
                dest = rt._download_code(spec)
                self.assertEqual((dest/'file.txt').read_bytes(), b'new\n')
                self.assertEqual((dest/'new.txt').read_bytes(), b'added\n')
                self.assertEqual(rt._download_code(spec), dest)
                self.assertEqual(download.call_count, 1)
            (dest/'file.txt').write_bytes(b'tampered')
            marker = dest/'.dm-local-source.json'
            forged = json.loads(marker.read_text())
            forged['files']['file.txt'] = hashlib.sha256(b'tampered').hexdigest()
            marker.write_text(json.dumps(forged))
            with self.assertRaisesRegex(RuntimeError, 'tampered'):
                rt._download_code(spec)

    def test_patch_tamper_and_pin_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt, spec, raw = self.fixture(tmp)
            with patch('urllib.request.urlopen', return_value=io.BytesIO(raw)):
                dest = rt._download_code(spec)
            (rt.weights/'serve.patch').write_bytes(DIFF + b'bad')
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                rt._download_code(spec)
            (rt.weights/'serve.patch').write_bytes(DIFF)
            spec['revision'] = 'b'*40
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                rt._download_code(spec)
            self.assertEqual((dest/'file.txt').read_bytes(), b'new\n')

    def test_traversal_absolute_and_special_patch_forms_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'file.txt').write_bytes(b'old\n')
            for name in ('../escape', '/tmp/escape', 'a/../../escape', 'C:/escape', '.git/config', '.dm-local-source.json', 'x\\escape'):
                with self.subTest(name=name), self.assertRaises((ValueError, RuntimeError)):
                    apply_text_patch(root, DIFF.replace(b'file.txt', name.encode()), _contained_path)
            for data in (DIFF.replace(b'100644',b'120000'), DIFF.replace(b'index ', b'GIT binary patch\nindex '),
                         DIFF.replace(b'b/file.txt\nindex',b'b/other.txt\nindex'), DIFF+b'junk\n', DIFF.replace(b'-old', b'-wrong')):
                with self.assertRaises((ValueError, RuntimeError)):
                    apply_text_patch(root, data, _contained_path)
            self.assertEqual((root/'file.txt').read_bytes(), b'old\n')

    def test_symlink_patch_checkout_and_target_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt, spec, raw = self.fixture(tmp)
            outside = Path(tmp)/'outside'
            outside.mkdir()
            (rt.weights/'serve.patch').unlink()
            (outside/'patch').write_bytes(DIFF)
            (rt.weights/'serve.patch').symlink_to(outside/'patch')
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                rt._download_code(spec)
            (rt.weights/'serve.patch').unlink()
            (rt.weights/'serve.patch').write_bytes(DIFF)
            (rt.weights/'code').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                rt._download_code(spec)
            (outside/'file.txt').symlink_to(outside/'victim')
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                apply_text_patch(outside, DIFF, _contained_path)

    def test_second_hunk_failure_has_no_visible_partial_checkout_and_retry_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt, spec, raw = self.fixture(tmp, DIFF + NEW.replace(b'+added', b'+added\n+overflow'))
            with patch('urllib.request.urlopen', return_value=io.BytesIO(raw)), self.assertRaises(ValueError):
                rt._download_code(spec)
            self.assertFalse((rt.weights/spec['dest']).exists())
            self.assertEqual(list((rt.weights/'code').iterdir()), [])
            (rt.weights/'serve.patch').write_bytes(DIFF)
            spec['patch']['sha256'] = hashlib.sha256(DIFF).hexdigest()
            with patch('urllib.request.urlopen', return_value=io.BytesIO(raw)):
                self.assertEqual((rt._download_code(spec)/'file.txt').read_bytes(), b'new\n')

    def test_write_failure_cleans_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt, spec, raw = self.fixture(tmp)
            with patch('urllib.request.urlopen', return_value=io.BytesIO(raw)), \
                    patch('dmlocal.runtimes.recipe.os.rename', side_effect=OSError('fixture failure')), \
                    self.assertRaisesRegex(OSError, 'fixture failure'):
                rt._download_code(spec)
            self.assertEqual(list((rt.weights/'code').iterdir()), [])

    def test_prepare_twice_never_reapplies_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt, spec, raw = self.fixture(tmp)
            rt.recipe['code'] = [spec]
            with patch.object(rt, '_prepare_python'), patch('urllib.request.urlopen', return_value=io.BytesIO(raw)) as download:
                rt.prepare()
                rt.prepare()
            self.assertEqual(download.call_count, 1)
            self.assertEqual((rt.weights/spec['dest']/'file.txt').read_bytes(), b'new\n')

    def test_wrong_archive_and_result_hash_leave_no_checkout(self):
        for field in ('sha256', 'tree_sha256'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                rt, spec, raw = self.fixture(tmp)
                if field == 'sha256':
                    spec[field] = '0'*64
                else:
                    spec['patch'][field] = '0'*64
                with patch('urllib.request.urlopen', return_value=io.BytesIO(raw)), self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                    rt._download_code(spec)
                self.assertFalse((rt.weights/spec['dest']).exists())
                self.assertEqual(list((rt.weights/'code').iterdir()), [])

    def test_headerless_new_file_and_mismatched_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            # macOS temporary paths may traverse a system alias such as /var.
            # Runtime roots are canonicalized before the path guard is called.
            root = Path(tmp).resolve()
            headerless = NEW.replace(b'--- /dev/null\n+++ b/new.txt\n', b'')
            apply_text_patch(root, headerless, _contained_path)
            self.assertEqual((root/'new.txt').read_bytes(), b'added\n')
            (root/'new.txt').unlink()
            with self.assertRaises(ValueError):
                apply_text_patch(root, NEW.replace(b'+++ b/new.txt', b'+++ b/escape'), _contained_path)

    def test_schema_rejects_unpinned_or_unsafe_patch(self):
        v = variant()
        code = dict(source='github', repo='own/fixture', revision='a'*40, sha256='b'*64, dest='code/fixture',
                    patch={'path':'serve.patch','sha256':'c'*64,'tree_sha256':'d'*64})
        v['install']['code'] = [code]
        self.assertEqual(recipe_errors(v), [])
        for value in ({'path':'../bad','sha256':'c'*64}, {'path':'serve.patch','sha256':'main'},
                      {'path':'serve.patch','sha256':'c'*64,'command':['sh']}):
            code['patch'] = value
            self.assertTrue(any('.patch' in e for e in recipe_errors(v)))


if __name__ == '__main__':
    unittest.main()
