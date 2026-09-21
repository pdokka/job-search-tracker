import fcntl
import gzip
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


class LocalSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.tracker = self.root/'job-tracker'
        self.data = self.tracker/'data'
        self.data.mkdir(parents=True)
        self.script = self.tracker/'tracker.py'
        shutil.copyfile(pathlib.Path(__file__).with_name('tracker.py'), self.script)
        self.state = self.data/'state.json'
        self.original = json.dumps({'jobs': {}, 'boards': {}, 'runs': []}).encode()
        self.state.write_bytes(self.original)

    def run_tracker(self, *args):
        return subprocess.run([sys.executable, str(self.script), *args], capture_output=True, text=True)

    def test_overlapping_run_preserves_data_and_unlocks(self):
        with (self.data/'.run.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_tracker('render')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('already running', result.stderr)
            self.assertEqual(self.state.read_bytes(), self.original)
        result = self.run_tracker('render')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.state.read_text())['jobs'], {})

    def test_failed_review_has_recoverable_backup(self):
        invalid = self.root/'invalid-review.json'
        invalid.write_text('[{"url": "https://example.com/job"}]')
        result = self.run_tracker('review', str(invalid))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state.read_bytes(), self.original)
        backups = list((self.root/'backups').glob('state-*.json.gz'))
        self.assertEqual(len(backups), 1)
        with gzip.open(backups[0], 'rb') as backup:
            self.assertEqual(backup.read(), self.original)

    def test_unscanned_board_failure_stays_visible(self):
        self.state.write_text(json.dumps({'jobs': {}, 'boards': {
            'lever:example': {'error': 'Timed out', 'last_checked': '2026-09-19'}},
            'health': [{'source': 'remoteok', 'rows': 10, 'error': None}]}))
        result = self.run_tracker('render')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = (self.tracker/'TRACKER.md').read_text()
        self.assertIn('Earlier employer-board failures awaiting recheck', report)
        self.assertIn('lever:example: Timed out', report)


if __name__ == '__main__':
    unittest.main()
