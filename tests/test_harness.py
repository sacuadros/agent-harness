import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / 'bin' / 'harness'
HOME = Path.home()


def harness(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args],
                          capture_output=True, text=True, check=True).stdout


class Render(unittest.TestCase):
    @unittest.skipUnless((HOME / '.claude' / 'CLAUDE.md').is_file(), 'no installed CLAUDE.md')
    def test_claude_matches_installed(self):
        self.assertEqual(harness('render', 'claude'), (HOME / '.claude' / 'CLAUDE.md').read_text())

    @unittest.skipUnless((HOME / '.codex' / 'AGENTS.md').is_file(), 'no installed AGENTS.md')
    def test_codex_matches_installed(self):
        self.assertEqual(harness('render', 'codex'), (HOME / '.codex' / 'AGENTS.md').read_text())


class Install(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_creates_files_in_empty_home(self):
        harness('install', '--home', str(self.home))
        self.assertEqual((self.home / '.claude' / 'CLAUDE.md').read_text(), harness('render', 'claude'))
        self.assertEqual((self.home / '.codex' / 'AGENTS.md').read_text(), harness('render', 'codex'))

    def test_second_install_changes_nothing(self):
        harness('install', '--home', str(self.home))
        out = harness('install', '--home', str(self.home))
        self.assertIn('no changes', out)
        self.assertFalse((self.home / '.agent-harness' / 'backups').exists())

    def test_backs_up_a_changed_file_before_overwriting(self):
        harness('install', '--home', str(self.home))
        installed = self.home / '.claude' / 'CLAUDE.md'
        installed.write_text('hand edit\n')
        harness('install', '--home', str(self.home))
        backups = list((self.home / '.agent-harness' / 'backups').glob('*/.claude/CLAUDE.md'))
        self.assertEqual([b.read_text() for b in backups], ['hand edit\n'])
        self.assertEqual(installed.read_text(), harness('render', 'claude'))

    @unittest.skipUnless((HOME / '.claude' / 'CLAUDE.md').is_file(), 'no installed harness')
    def test_dry_run_on_this_pc_reports_no_changes(self):
        self.assertIn('no changes', harness('install', '--dry-run'))


if __name__ == '__main__':
    unittest.main()
