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


def run(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args], capture_output=True, text=True)


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


class Check(unittest.TestCase):
    @unittest.skipUnless((HOME / '.claude' / 'CLAUDE.md').is_file(), 'no installed harness')
    def test_ok_on_this_pc(self):
        result = run('check')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'))

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        harness('install', '--home', str(self.home))

    def test_ok_after_install(self):
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'))

    def test_hand_edited_file_fails(self):
        (self.home / '.claude' / 'CLAUDE.md').write_text('hand edit\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.home / '.claude' / 'CLAUDE.md'), result.stdout)

    def test_missing_file_fails(self):
        (self.home / '.codex' / 'AGENTS.md').unlink()
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.home / '.codex' / 'AGENTS.md'), result.stdout)

    def test_broken_agent_configs_fail(self):
        settings = self.home / '.claude' / 'settings.json'
        config = self.home / '.codex' / 'config.toml'
        settings.write_text('{"hooks": ')
        config.write_text('model = \n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(settings), result.stdout)
        self.assertIn(str(config), result.stdout)


if __name__ == '__main__':
    unittest.main()
