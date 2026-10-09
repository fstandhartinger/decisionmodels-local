"""Exercise the real host APIs; do not substitute mocked platform identities."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from dmlocal import process


class NativeProcessTests(unittest.TestCase):
    def wait_file(self, path):
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(path.exists(), str(path))

    def test_live_fixture_and_descendant_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child_pid = root / 'child.pid'
            script = root / 'fixture.py'
            script.write_text(
                "import subprocess, sys, time\n"
                "from pathlib import Path\n"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                "Path(sys.argv[1]).write_text(str(p.pid))\n"
                "time.sleep(120)\n")
            data = process.start_process(root, 'fixture', [sys.executable, str(script), str(child_pid)], cwd=root)
            try:
                self.wait_file(child_pid)
                print('native fixture identity:', json.dumps(data), flush=True)
                if sys.platform == 'darwin':
                    print('native fixture argv:', process._darwin_argv(data['pid']), flush=True)
                self.assertTrue(process.read_process(root, 'fixture')['running'])
                # A fresh CLI must verify the record without cached Popen state.
                check = subprocess.check_output([
                    sys.executable, '-c',
                    'import json,sys; from dmlocal.process import read_process; '
                    'print(json.dumps(read_process(sys.argv[1], "fixture")))', str(root)], text=True)
                self.assertTrue(json.loads(check)['running'])
                descendant = int(child_pid.read_text())
                self.assertTrue(process.process_alive(descendant))
                self.assertTrue(process.stop_process(root, 'fixture', timeout=2)['stopped'])
                deadline = time.monotonic() + 5
                while process.process_alive(descendant) and time.monotonic() < deadline:
                    # Linux may briefly retain a dead grandchild as a zombie.
                    if sys.platform.startswith('linux'):
                        stat = Path('/proc') / str(descendant) / 'stat'
                        if stat.exists() and stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                            break
                    time.sleep(.05)
                if sys.platform.startswith('linux'):
                    self.assertFalse(process._session_has_member(data['pid']))
                else:
                    self.assertFalse(process.process_alive(descendant))
            finally:
                if process.pidfile(root, 'fixture').exists():
                    print('native fixture log:', Path(data['log']).read_text(errors='replace'), flush=True)
                    process.stop_process(root, 'fixture', timeout=1)

    def test_descendants_remain_owned_after_command_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child_pid = root / 'child.pid'
            script = root / 'fixture.py'
            script.write_text(
                "import subprocess, sys\n"
                "from pathlib import Path\n"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                "Path(sys.argv[1]).write_text(str(p.pid))\n")
            data = process.start_process(root, 'orphan', [sys.executable, str(script), str(child_pid)], cwd=root)
            try:
                self.wait_file(child_pid)
                time.sleep(.3)
                descendant = int(child_pid.read_text())
                self.assertTrue(process.process_alive(descendant))
                if os.name == 'nt':
                    self.assertTrue(process.read_process(root, 'orphan')['running'])
                self.assertTrue(process.stop_process(root, 'orphan', timeout=2)['stopped'])
                self.assertFalse(process._session_has_member(data['pid']))
                if os.name == 'nt' or sys.platform == 'darwin':
                    self.assertFalse(process.process_alive(descendant))
            finally:
                if process.pidfile(root, 'orphan').exists():
                    print('native orphan identity:', data, flush=True)
                    print('native orphan log:', Path(data['log']).read_text(errors='replace'), flush=True)
                    process.stop_process(root, 'orphan', timeout=1)

    @unittest.skipUnless(os.name == 'nt', 'native Windows Job Object acquisition')
    def test_delayed_supervisor_acquires_job_before_parent_closes_handle(self):
        # Widen the original race while still using real Windows APIs.
        delayed = process._WINDOWS_SUPERVISOR.replace(
            "api = ctypes.WinDLL", "time.sleep(.25)\napi = ctypes.WinDLL", 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(process, '_WINDOWS_SUPERVISOR', delayed):
                data = process.start_process(root, 'delayed', [sys.executable, '-c', 'import time; time.sleep(120)'], cwd=root)
            try:
                self.assertTrue(process.read_process(root, 'delayed')['running'])
                self.assertFalse(list((root / 'run').glob('.*.ready*')))
            finally:
                print('native delayed supervisor identity:', data, flush=True)
                print('native delayed supervisor log:', Path(data['log']).read_text(errors='replace'), flush=True)
                process.stop_process(root, 'delayed', timeout=1)

    @unittest.skipUnless(os.name == 'nt' or sys.platform == 'darwin', 'native creation identity')
    def test_changed_birth_refuses_stop_and_preserves_live_tree_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = process.start_process(root, 'identity', [sys.executable, '-c', 'import time; time.sleep(120)'], cwd=root)
            record = process.pidfile(root, 'identity')
            original = record.read_text()
            changed = dict(data)
            if os.name == 'nt':
                changed['windows_birth'] += 1
            else:
                changed['darwin_birth'] = [0, 0]
            altered = json.dumps(changed)
            record.write_text(altered)
            try:
                with self.assertRaises(RuntimeError):
                    process.stop_process(root, 'identity', timeout=.1)
                self.assertTrue(process.process_alive(data['pid']))
                self.assertFalse(process.read_process(root, 'identity')['running'])
                self.assertEqual(record.read_text(), altered)
            finally:
                record.write_text(original)
                process.stop_process(root, 'identity', timeout=1)

    def test_live_foreign_pid_is_unchanged_and_record_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = {} if os.name == 'nt' else {'start_new_session': True}
            foreign = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], **kwargs)
            record = process.pidfile(root, 'foreign')
            record.parent.mkdir(parents=True)
            original = json.dumps({'pid': foreign.pid, 'pgid': foreign.pid,
                                   'command': [sys.executable, '-c', 'different command']})
            record.write_text(original)
            try:
                with self.assertRaises(RuntimeError):
                    process.stop_process(root, 'foreign', timeout=.1)
                self.assertIsNone(foreign.poll())
                self.assertEqual(record.read_text(), original)
                with self.assertRaises(RuntimeError):
                    process.start_process(root, 'foreign', [sys.executable, '-c', 'pass'])
                self.assertEqual(record.read_text(), original)
            finally:
                foreign.terminate()
                foreign.wait(timeout=5)
