import contextlib
import importlib.machinery
import importlib.util
import io
import json
import re
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / 'bin' / 'harness'
HOME = Path.home()
MANAGED_SKILLS = {
    'backlog', 'story', 'pair', 'dependency-safety',
    'promote-project-convention', 'secure-development',
    'software-architecture', 'unslop', 'work-unit-commits',
    'cognitive-doc-design', 'systematic-debugging', 'verification-ladders',
}


def tree(root):
    """Relative path -> bytes for every file under root, skipping old .bak leftovers."""
    return {str(f.relative_to(root)): f.read_bytes() for f in root.rglob('*')
            if f.is_file() and '.bak' not in f.name}


SPAWN = {'CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH': '1'}  # install always sets it


def harness(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args],
                          capture_output=True, encoding='utf-8', check=True).stdout


def load_harness():
    loader = importlib.machinery.SourceFileLoader('harness_tool', str(HARNESS))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('harness_tool', loader))
    loader.exec_module(module)
    return module


def run(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args], capture_output=True, encoding='utf-8')


class SliceFlowPacing(unittest.TestCase):
    """Every agent runs slices on its own after one backlog approval; commits wait for the user."""

    def test_every_agent_gets_the_pacing_contract(self):
        for agent in ('claude', 'codex', 'copilot'):
            text = harness('render', agent)
            for rule in ('one checkpoint before building: backlog approval',
                         'Commits and pushes always wait for the user', 'ask everything pending in one round'):
                self.assertIn(rule, text, agent)
            self.assertNotIn('sin pausas', text, agent)

    def test_every_agent_gets_the_scope_contract(self):
        for agent in ('claude', 'codex', 'copilot'):
            text = harness('render', agent)
            for rule in ('Do only what was asked', 'ask instead of assuming',
                         'leave it undone unless the user says to apply it'):
                self.assertIn(rule, text, agent)
            self.assertNotIn('recording assumed answers', text, agent)

    def test_every_agent_gets_one_classifier(self):
        for agent in ('claude', 'codex', 'copilot'):
            text = harness('render', agent)
            self.assertIn('Classify before the first write', text, agent)
            self.assertIn('`verification-ladders`', text, agent)
            self.assertEqual(text.count('contracts others consume'), 1, agent)  # the risk items are listed once
            self.assertNotIn('Select assurance independently', text, agent)

    def test_memory_saves_grouped_conclusions_without_a_summary_gate(self):
        for agent in ('claude', 'codex', 'copilot'):
            text = harness('render', agent)
            self.assertNotIn('Before saying "done"', text, agent)
            self.assertIn('grouped by topic', text, agent)

    def test_no_change_is_a_valid_outcome(self):
        for agent in ('claude', 'codex', 'copilot'):
            self.assertIn('No change is a valid outcome', harness('render', agent), agent)

    def test_context7_is_required_before_library_code(self):
        rule = ('Before writing code against a library, framework, SDK, CLI, or cloud API, read its current '
                'documentation with Context7. If Context7 is unavailable, use the official documentation and say so.')
        for agent in ('claude', 'codex', 'copilot'):
            self.assertEqual(harness('render', agent).count(rule), 1, agent)

    def test_commit_rules_are_stated_once(self):
        for agent in ('claude', 'codex', 'copilot'):
            text = harness('render', agent)
            self.assertEqual(text.count('Commits and pushes always wait for the user'), 1, agent)
            self.assertNotIn('remain separately authorized', text, agent)
            self.assertLessEqual(text.count('Co-Authored-By'), 1, agent)

    def test_rendered_instructions_stay_under_the_size_budget(self):
        for agent in ('claude', 'codex', 'copilot'):
            # About 22,800 before the trim. Deduplication alone reached about 20,000; going lower means dropping rules.
            self.assertLessEqual(len(harness('render', agent)), 20500, agent)

    def test_skills_do_not_wait_or_commit_on_their_own(self):
        skills = REPO / 'core' / 'skills'
        self.assertIn('This is the only checkpoint before building', (skills / 'backlog' / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('Do not wait for approval', (skills / 'story' / 'SKILL.md').read_text(encoding='utf-8'))
        pair = (skills / 'pair' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('Do not commit', pair)
        self.assertIn('commit, commit and push, or not yet', pair)

    def test_skills_hand_off_to_the_skill_that_owns_the_problem(self):
        # Nothing in the always-loaded instructions calls these skills, so the skill in use at that moment does.
        skills = REPO / 'core' / 'skills'
        for caller, owner in (('pair', 'systematic-debugging'), ('verification-ladders', 'secure-development'),
                              ('story', 'software-architecture')):
            self.assertIn(f'`{owner}`', (skills / caller / 'SKILL.md').read_text(encoding='utf-8'), caller)
            self.assertTrue((skills / owner / 'SKILL.md').is_file(), owner)


class Restore(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.backups = self.home / '.agent-harness' / 'backups'

    def last_install(self):
        return max(p.parent.name for p in self.backups.glob('*/manifest.json'))

    def test_undoes_an_install_and_keeps_what_it_removes(self):
        harness('install', '--home', str(self.home))
        edited = self.home / '.claude' / 'CLAUDE.md'
        edited.write_text('hand edit\n', encoding='utf-8', newline='\n')
        added = self.home / '.claude' / 'skills' / 'pair' / 'SKILL.md'
        added.unlink()
        harness('install', '--home', str(self.home))
        harness('restore', self.last_install(), '--home', str(self.home))
        self.assertEqual(edited.read_text(encoding='utf-8'), 'hand edit\n')
        self.assertFalse(added.exists())
        kept = list(self.backups.glob('*-before-restore/.claude/CLAUDE.md'))
        self.assertEqual([k.read_text(encoding='utf-8') for k in kept], [harness('render', 'claude')])
        self.assertEqual(len(list(self.backups.glob('*-before-restore/.claude/skills/pair/SKILL.md'))), 1)

    def test_brings_back_a_retired_folder(self):
        old = self.home / '.codex' / 'skills' / 'pair' / 'SKILL.md'
        old.parent.mkdir(parents=True)
        old.write_text('old\n', encoding='utf-8')
        harness('install', '--home', str(self.home))
        self.assertFalse(old.exists())
        harness('restore', self.last_install(), '--home', str(self.home))
        self.assertEqual(old.read_text(encoding='utf-8'), 'old\n')

    def test_refuses_a_backup_it_cannot_complete(self):
        live = self.home / '.claude' / 'CLAUDE.md'
        live.parent.mkdir(parents=True)
        live.write_text('live\n', encoding='utf-8')
        broken = self.backups / '20200101-000000-000000'
        broken.mkdir(parents=True)
        (broken / 'manifest.json').write_text(json.dumps(
            {'created': [], 'replaced': ['.claude/CLAUDE.md'], 'retired': []}), encoding='utf-8')
        result = run('restore', broken.name, '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(live.read_text(encoding='utf-8'), 'live\n')

    @unittest.skipIf(os.name == 'nt', 'symlinks need a privilege on Windows')
    def test_writes_through_a_symlinked_file(self):
        dotfile = self.home / 'dotfiles' / 'CLAUDE.md'
        dotfile.parent.mkdir()
        dotfile.write_text('mine\n', encoding='utf-8')
        link = self.home / '.claude' / 'CLAUDE.md'
        link.parent.mkdir()
        link.symlink_to(dotfile)
        harness('install', '--home', str(self.home))
        harness('restore', self.last_install(), '--home', str(self.home))
        self.assertTrue(link.is_symlink())
        self.assertEqual(dotfile.read_text(encoding='utf-8'), 'mine\n')

    @unittest.skipIf(os.name == 'nt', 'symlinks need a privilege on Windows')
    def test_brings_back_retired_links(self):
        folder = self.home / '.codex' / 'skills' / 'pair'
        folder.mkdir(parents=True)
        (folder / 'SKILL.md').write_text('old\n', encoding='utf-8')
        (folder / 'gone').symlink_to('missing')
        story = self.home / '.codex' / 'skills' / 'story'
        story.symlink_to('pair')
        harness('install', '--home', str(self.home))
        self.assertFalse(folder.exists())
        harness('restore', self.last_install(), '--home', str(self.home))
        self.assertTrue((folder / 'gone').is_symlink())
        self.assertEqual(os.readlink(story), 'pair')

    def test_refuses_a_backup_without_manifest(self):
        for stamp in ('20200101-000000', '../..'):
            result = run('restore', stamp, '--home', str(self.home))
            self.assertEqual(result.returncode, 1, stamp)
            self.assertIn('no install manifest', result.stdout)


class Selection(unittest.TestCase):
    """`install` writes only for the agents you pick, and remembers them."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        for folder in ('.claude', '.codex', '.copilot'):
            (self.home / folder).mkdir(parents=True)
        (self.home / '.claude.json').write_text('{}\n', encoding='utf-8')

    def install(self, *args):
        return harness('install', '--home', str(self.home), *args)

    def exists(self, *paths):
        return [(self.home / path).exists() for path in paths]

    def test_writes_only_for_the_chosen_agent(self):
        self.install('--agents', 'codex')
        self.assertEqual(self.exists('.codex/AGENTS.md', '.agents/skills/pair/SKILL.md'), [True, True])
        self.assertEqual(self.exists('.claude/CLAUDE.md', '.claude/skills', '.claude/settings.json',
                                     '.copilot/copilot-instructions.md'), [False] * 4)

    def test_shared_files_go_with_every_agent_that_reads_them(self):
        self.install('--agents', 'copilot')
        self.assertEqual(self.exists('.copilot/copilot-instructions.md', '.agents/skills/pair/SKILL.md',
                                     '.claude/hooks/harness_guards.py'), [True, True, True])
        self.assertEqual(self.exists('.codex/AGENTS.md', '.claude/CLAUDE.md'), [False, False])

    def test_remembers_the_choice(self):
        self.install('--agents', 'claude')
        self.assertIn('no changes', self.install())
        self.assertEqual(self.exists('.codex/AGENTS.md'), [False])
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'))

    def test_dry_run_changes_nothing(self):
        out = self.install('--agents', 'claude', '--dry-run')
        self.assertIn('CLAUDE.md', out)
        self.assertNotIn('AGENTS.md', out)
        self.assertEqual(self.exists('.agent-harness/agents', '.claude/CLAUDE.md'), [False, False])

    def test_dropping_an_agent_leaves_its_files(self):
        self.install('--agents', 'claude')
        self.install('--agents', 'codex')
        self.assertEqual(self.exists('.claude/CLAUDE.md', '.codex/AGENTS.md'), [True, True])
        self.assertEqual(run('check', '--home', str(self.home)).returncode, 0)

    def test_stale_copies_of_other_agents_stay(self):
        stale = self.home / '.config' / 'copilot' / 'copilot-instructions.md'
        stale.parent.mkdir(parents=True)
        stale.write_text('mine\n', encoding='utf-8')
        self.install('--agents', 'claude')
        self.assertTrue(stale.exists())
        self.assertEqual(run('check', '--home', str(self.home)).returncode, 0)

    def test_refuses_what_it_cannot_find(self):
        shutil.rmtree(self.home / '.copilot')
        env = {**os.environ, 'PATH': ''}
        for name in ('copilot', 'nope'):
            result = subprocess.run([sys.executable, str(HARNESS), 'install', '--home', str(self.home), '--agents', name],
                                    capture_output=True, encoding='utf-8', env=env)
            self.assertEqual(result.returncode, 1, name)
            self.assertIn('not found', result.stdout)
        self.assertEqual(self.exists('.agent-harness/agents', '.claude/CLAUDE.md'), [False, False])

    def test_broken_configs_of_other_agents_do_not_matter(self):
        for broken in ('[]', '{'):
            (self.home / '.copilot' / 'mcp-config.json').write_text(broken, encoding='utf-8')
            (self.home / '.codex' / 'hooks.json').write_text(broken, encoding='utf-8')
            self.install('--agents', 'claude')
            self.assertEqual(run('check', '--home', str(self.home)).returncode, 0, broken)

    def test_an_unusable_choice_counts_as_none(self):
        choice = self.home / '.agent-harness' / 'agents'
        choice.parent.mkdir()
        for content in (b'', b'nope\n', b'\xff\n'):
            choice.write_bytes(content)
            self.install()
            self.assertEqual(self.exists('.claude/CLAUDE.md', '.codex/AGENTS.md'), [True, True], content)
            (self.home / '.claude' / 'CLAUDE.md').unlink()

    def test_installing_one_agent_does_not_make_another_found(self):
        (self.home / '.claude.json').unlink()
        env = {**os.environ, 'PATH': ''}
        command = [sys.executable, str(HARNESS), 'install', '--home', str(self.home), '--agents']
        self.assertEqual(subprocess.run([*command, 'codex'], capture_output=True, env=env).returncode, 0)
        self.assertEqual(subprocess.run([*command, 'claude'], capture_output=True, env=env).returncode, 1)

    def test_vs_code_alone_counts_as_copilot(self):
        tool = load_harness()
        shutil.rmtree(self.home / '.copilot')
        with mock.patch.object(tool.shutil, 'which', lambda name: None):
            self.assertNotIn('copilot', tool.detected(self.home))
            (self.home / tool.VSCODE_USER[1]).mkdir(parents=True)
            self.assertIn('copilot', tool.detected(self.home))

    def test_with_no_choice_every_stale_copy_still_goes(self):
        shutil.rmtree(self.home / '.copilot')
        stale = self.home / '.config' / 'copilot' / 'copilot-instructions.md'
        stale.parent.mkdir(parents=True)
        stale.write_text('old\n', encoding='utf-8')
        self.install()
        self.assertFalse(stale.exists())

    def test_choose_without_a_terminal_gives_up(self):
        result = subprocess.run([sys.executable, str(HARNESS), 'install', '--choose', '--home', str(self.home)],
                                stdin=subprocess.DEVNULL, capture_output=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertIn('nothing selected', result.stdout)
        self.assertNotIn('\x1b', result.stdout)

    @unittest.skipIf(os.name == 'nt', 'needs a pty')
    def test_choose_with_no_input_does_not_hang(self):
        import pty
        master, slave = pty.openpty()
        tui = subprocess.Popen([sys.executable, str(HARNESS), 'install', '--choose', '--home', str(self.home)],
                               stdin=subprocess.DEVNULL, stdout=slave, stderr=slave, env={**os.environ, 'TERM': 'xterm'})
        os.close(slave)
        self.assertEqual(tui.wait(timeout=20), 0)
        os.close(master)

    def test_every_managed_path_has_an_owner(self):
        tool = load_harness()
        for rel in tool.outputs(self.home, agents=set(tool.AGENTS)):
            self.assertTrue(tool.wanted(rel, set(tool.AGENTS)), rel)
        for rel in tool.RETIRED:  # a retired copy may belong to an agent the harness dropped
            self.assertTrue(tool.dropped(rel) or tool.wanted(rel, set(tool.AGENTS)), rel)

    def test_detects_a_config_folder_or_a_command(self):
        tool = load_harness()
        shutil.rmtree(self.home / '.copilot')
        with mock.patch.object(tool.shutil, 'which', lambda name: '/bin/copilot' if name == 'copilot' else None):
            self.assertIn('copilot', tool.detected(self.home))
        with mock.patch.object(tool.shutil, 'which', lambda name: None):
            self.assertEqual(tool.detected(self.home), {'claude', 'codex'})

    def test_text_picker_for_terminals_without_curses(self):
        tool = load_harness()
        names = ['claude', 'codex', 'copilot']
        for answer, expected in (('', {'claude', 'copilot'}), ('2', {'codex'}), ('1, 2', {'claude', 'codex'}), ('q', None)):
            with mock.patch('builtins.input', lambda prompt: answer), mock.patch('builtins.print'):
                self.assertEqual(tool.pick_text(names, {'claude', 'copilot'}, []), expected, answer)

    def test_text_picker_asks_again_for_unknown_answers(self):
        # Names work like numbers; a typo or an out-of-range number asks again instead of installing nothing.
        tool = load_harness()
        names = ['claude', 'codex', 'copilot']
        for answers, expected in ((['codex, copilot'], {'codex', 'copilot'}), (['claude-code', '9', '2'], {'codex'})):
            replies = iter(answers)
            with mock.patch('builtins.input', lambda prompt: next(replies)), mock.patch('builtins.print') as shown:
                self.assertEqual(tool.pick_text(names, {'claude'}, []), expected, answers)
            self.assertEqual(sum('not an agent here' in str(call) for call in shown.call_args_list), len(answers) - 1)

    @unittest.skipIf(load_harness().curses is None, 'needs curses')
    def test_curses_picker_needs_one_agent_ticked(self):
        tool = load_harness()
        keys, frames = iter([ord(' '), 10, ord(' '), 10]), []  # untick, Enter (refused), tick, Enter

        class Screen:
            def erase(self):
                frames.append([])

            def addnstr(self, y, x, line, width):
                frames[-1].append(line)

            def getch(self):
                return next(keys)
        with mock.patch.object(tool.curses, 'wrapper', lambda loop: loop(Screen())), \
                mock.patch.object(tool.curses, 'curs_set', lambda visibility: None), \
                mock.patch.object(tool.curses, 'COLS', 80, create=True):
            self.assertEqual(tool.pick_curses(['claude'], {'claude'}, []), {'claude'})
        self.assertIn('Tick at least one agent', '\n'.join(frames[2]))
        self.assertIn('Unticked agents keep their files', '\n'.join(frames[0]))
        self.assertIn('~/.claude', '\n'.join(frames[0]))

    @unittest.skipIf(os.name == 'nt', 'needs curses and a pty')
    def test_first_install_in_a_terminal_opens_the_picker(self):
        import pty
        master, slave = pty.openpty()
        env = {**os.environ, 'TERM': 'xterm', 'LINES': '24', 'COLUMNS': '80', 'PATH': ''}
        tui = subprocess.Popen([sys.executable, str(HARNESS), 'install', '--home', str(self.home)],
                               stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        seen = b''
        while b'where to install' not in seen:
            seen += os.read(master, 4096)
        os.write(master, b' \r')  # untick Claude Code, then confirm
        try:
            while os.read(master, 4096):
                pass
        except OSError:  # Linux reports the closed pty as EIO
            pass
        self.assertEqual(tui.wait(timeout=30), 0)
        self.assertEqual(self.exists('.claude/CLAUDE.md', '.codex/AGENTS.md'), [False, True])
        self.assertNotIn('claude', (self.home / '.agent-harness' / 'agents').read_text(encoding='utf-8').split())


class Render(unittest.TestCase):
    @unittest.skipUnless((HOME / '.claude' / 'CLAUDE.md').is_file(), 'no installed CLAUDE.md')
    def test_claude_matches_installed(self):
        self.assertEqual(harness('render', 'claude'), (HOME / '.claude' / 'CLAUDE.md').read_text(encoding='utf-8'))

    @unittest.skipUnless((HOME / '.codex' / 'AGENTS.md').is_file(), 'no installed AGENTS.md')
    def test_codex_matches_installed(self):
        self.assertEqual(harness('render', 'codex'), (HOME / '.codex' / 'AGENTS.md').read_text(encoding='utf-8'))


class Install(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_creates_files_in_empty_home(self):
        harness('install', '--home', str(self.home))
        self.assertEqual((self.home / '.claude' / 'CLAUDE.md').read_text(encoding='utf-8'), harness('render', 'claude'))
        self.assertEqual((self.home / '.codex' / 'AGENTS.md').read_text(encoding='utf-8'), harness('render', 'codex'))

    def test_second_install_changes_nothing(self):
        harness('install', '--home', str(self.home))
        backups = list((self.home / '.agent-harness' / 'backups').iterdir())
        out = harness('install', '--home', str(self.home))
        self.assertIn('no changes', out)
        self.assertEqual(list((self.home / '.agent-harness' / 'backups').iterdir()), backups)

    def test_backs_up_a_changed_file_before_overwriting(self):
        harness('install', '--home', str(self.home))
        installed = self.home / '.claude' / 'CLAUDE.md'
        installed.write_text('hand edit\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        backups = list((self.home / '.agent-harness' / 'backups').glob('*/.claude/CLAUDE.md'))
        self.assertEqual([b.read_text(encoding='utf-8') for b in backups], ['hand edit\n'])
        self.assertEqual(installed.read_text(encoding='utf-8'), harness('render', 'claude'))

    @unittest.skipUnless((HOME / '.claude' / 'CLAUDE.md').is_file(), 'no installed harness')
    def test_dry_run_on_this_pc_reports_no_changes(self):
        self.assertIn('no changes', harness('install', '--dry-run'))


class Skills(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        harness('install', '--home', str(self.home))

    def powershell_block(self, text):
        found = re.search(r'```powershell\n(.*?)```', text, re.S)
        self.assertIsNotNone(found, 'no PowerShell form')
        return found[1]

    def test_backlog_skill_has_a_powershell_form(self):
        # Codex on Windows always runs PowerShell; Claude does too without Git Bash.
        for agent_dir in ('.claude', '.agents'):
            self.powershell_block((self.home / agent_dir / 'skills' / 'backlog' / 'SKILL.md').read_text(encoding='utf-8'))

    @unittest.skipUnless(os.name == 'nt', 'runs PowerShell')
    def test_backlog_powershell_form_excludes_slices_once(self):
        command = self.powershell_block((REPO / 'core' / 'skills' / 'backlog' / 'SKILL.md').read_text(encoding='utf-8'))
        repo = Path(tempfile.mkdtemp())
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        for _ in range(2):
            result = subprocess.run(['powershell', '-NoProfile', '-Command', command], cwd=repo,
                                    capture_output=True, encoding='utf-8')
            self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertTrue((repo / '.slices').is_dir())
        exclude = (repo / '.git' / 'info' / 'exclude').read_text(encoding='utf-8')
        self.assertEqual(exclude.splitlines().count('.slices/'), 1)
        (repo / '.slices' / 'x.md').write_text('x', encoding='utf-8')
        self.assertEqual(subprocess.run(['git', 'check-ignore', '-q', '.slices/x.md'], cwd=repo).returncode, 0)

    @unittest.skipUnless(os.name == 'nt', 'README PowerShell setup')
    def test_readme_windows_install_command_runs(self):
        home = Path(tempfile.mkdtemp())
        result = subprocess.run(['powershell', '-NoProfile', '-Command', f'py -3 bin/harness install --dry-run --home "{home}"'],
                                cwd=REPO, capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('would install', result.stdout)

    def assert_matches_installed(self, agent_dir):
        rendered = self.home / agent_dir / 'skills'
        self.assertEqual({d.name for d in rendered.iterdir()}, MANAGED_SKILLS)
        for name in MANAGED_SKILLS:
            installed = HOME / agent_dir / 'skills' / name
            if installed.is_dir():
                self.assertEqual(tree(rendered / name), tree(installed), name)

    def test_claude_copies_match_installed(self):
        self.assert_matches_installed('.claude')

    def test_codex_copies_match_installed(self):
        # ~/.agents/skills is Codex's documented user folder, and Copilot reads it too.
        self.assert_matches_installed('.agents')
        self.assertFalse((self.home / '.codex' / 'skills').exists())

    def test_agent_specific_files_go_only_to_their_agent(self):
        claude = self.home / '.claude' / 'skills' / 'secure-development'
        codex = self.home / '.agents' / 'skills' / 'secure-development'
        self.assertFalse((claude / 'agents' / 'openai.yaml').exists())
        self.assertTrue((codex / 'agents' / 'openai.yaml').is_file())
        # One agent-neutral SKILL.md: Copilot reads the same copy, so it names each agent's tool.
        skill = (claude / 'SKILL.md').read_text(encoding='utf-8')
        self.assertEqual(skill, (codex / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('/security-review', skill)
        self.assertIn('codex-security', skill)
        leftovers = [f for f in self.home.rglob('*') if '.claude.' in f.name or '.codex.' in f.name]
        self.assertEqual(leftovers, [])

    def test_old_codex_skill_copies_are_retired(self):
        old = self.home / '.codex' / 'skills'
        for name in ('pair', '.system', 'hyperframes'):  # .system is Codex's own cache
            (old / name).mkdir(parents=True)
            (old / name / 'SKILL.md').write_text('old\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(sorted(p.name for p in old.iterdir()), ['.system', 'hyperframes'])
        moved = list((self.home / '.agent-harness' / 'backups').glob('*/.codex/skills/pair/SKILL.md'))
        self.assertEqual(len(moved), 1)

    def test_old_gentle_ai_copy_in_agents_skills_is_replaced(self):
        old = self.home / '.agents' / 'skills' / 'work-unit-commits' / 'SKILL.md'
        old.write_text('gentle-ai\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(old.read_bytes(), (REPO / 'core' / 'skills' / 'work-unit-commits' / 'SKILL.md').read_bytes())
        moved = list((self.home / '.agent-harness' / 'backups').glob('*/.agents/skills/work-unit-commits/SKILL.md'))
        self.assertEqual([m.read_text(encoding='utf-8') for m in moved], ['gentle-ai\n'])
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'), result.stdout)

    def test_hand_edited_skill_fails_check(self):
        edited = self.home / '.agents' / 'skills' / 'pair' / 'SKILL.md'
        edited.write_text('hand edit\n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(edited), result.stdout)

    def test_unmanaged_skill_survives_install(self):
        mine = self.home / '.claude' / 'skills' / 'hyperframes' / 'SKILL.md'
        mine.parent.mkdir(parents=True)
        mine.write_text('third party\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(mine.read_text(encoding='utf-8'), 'third party\n')


class Subagents(unittest.TestCase):
    NAMES = ('implementation-worker', 'independent-reviewer', 'test-runner')
    # Intentional wording fix from the B3 story: Codex test-runner said "the root".
    FIXES = {'assigned by the root': 'assigned by the primary agent'}

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        harness('install', '--home', str(self.home))

    def test_match_installed(self):
        for name in self.NAMES:
            for rel in (f'.claude/agents/{name}.md', f'.codex/agents/{name}.toml'):
                installed = HOME / rel
                if not installed.is_file():
                    continue
                expected = installed.read_text(encoding='utf-8')
                for old, new in self.FIXES.items():
                    expected = expected.replace(old, new)
                self.assertEqual((self.home / rel).read_text(encoding='utf-8'), expected, rel)

    def test_codex_agents_claim_no_sandbox(self):
        # Codex ignores sandbox_mode in agent files, so writing it would promise a limit that does not exist.
        for name in self.NAMES:
            self.assertNotIn('sandbox_mode', (self.home / f'.codex/agents/{name}.toml').read_text(encoding='utf-8'))

    def test_claude_subagents_cannot_spawn_subagents(self):
        settings = json.loads((self.home / '.claude/settings.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['env']['CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH'], '1')


class Hooks(unittest.TestCase):
    SCRIPTS = ('harness_guards.py', 'enforce_memory_graph.py', 'engram_auto_enroll.py')

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def install(self):
        harness('install', '--home', str(self.home))

    def test_scripts_are_installed(self):
        self.set_server()  # the auto-enroll script ships only with a server
        self.install()
        for script in self.SCRIPTS:
            self.assertEqual((self.home / '.claude' / 'hooks' / script).read_bytes(),
                             (REPO / 'core' / 'hooks' / script).read_bytes())
        self.assertEqual(sorted(p.name for p in (self.home / '.codex' / 'hooks').iterdir()),
                         ['engram_auto_enroll.py'])

    def write_json(self, rel, data):
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8', newline='\n')
        return path

    def hook_commands(self, rel):
        data = json.loads((self.home / rel).read_text(encoding='utf-8'))
        return self.commands(e for entries in data['hooks'].values() for e in entries)

    def test_auto_enroll_is_not_installed_without_a_server(self):
        # The auto-enroll only enrolls projects for cloud sync: no server, no hook and no script.
        self.install()
        for rel in ('.claude/settings.json', '.codex/hooks.json'):
            self.assertFalse([c for c in self.hook_commands(rel) if 'engram_auto_enroll' in c], rel)
        self.assertFalse((self.home / '.claude/hooks/engram_auto_enroll.py').exists())
        self.assertFalse((self.home / '.codex/hooks/engram_auto_enroll.py').exists())

    def set_server(self):
        config = self.home / '.agent-harness' / 'config.toml'
        config.parent.mkdir(exist_ok=True)
        config.write_text('engram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        return config

    def test_auto_enroll_is_installed_with_a_server(self):
        self.set_server()
        self.install()
        for rel in ('.claude/settings.json', '.codex/hooks.json'):
            self.assertEqual(len([c for c in self.hook_commands(rel) if c.endswith('/engram_auto_enroll.py')]), 2, rel)
        for rel in ('.claude/hooks/engram_auto_enroll.py', '.codex/hooks/engram_auto_enroll.py'):
            self.assertEqual((self.home / rel).read_bytes(), (REPO / 'core/hooks/engram_auto_enroll.py').read_bytes())

    def test_dropping_the_server_removes_the_auto_enroll(self):
        config = self.set_server()
        self.install()
        config.unlink()
        self.install()
        for rel in ('.claude/settings.json', '.codex/hooks.json'):
            self.assertFalse([c for c in self.hook_commands(rel) if 'engram_auto_enroll' in c], rel)
        self.assertFalse((self.home / '.claude/hooks/engram_auto_enroll.py').exists())
        self.assertFalse((self.home / '.codex/hooks/engram_auto_enroll.py').exists())
        harness('check', '--home', str(self.home))  # raises on drift

    def commands(self, entries):
        return [' '.join([h['command'], *h.get('args', [])]) for entry in entries for h in entry['hooks']]

    def engram_codex_config(self):
        codex = self.home / '.codex' / 'config.toml'
        codex.parent.mkdir(parents=True, exist_ok=True)
        codex.write_text('[mcp_servers.engram]\ncommand = "engram"\nargs = ["mcp"]\n', encoding='utf-8', newline='\n')
        return codex

    def test_engram_cloud_settings_come_from_the_pc_config(self):
        # The server URL is per PC (never in this public repo); every agent needs it plus autosync.
        (self.home / '.agent-harness').mkdir()
        (self.home / '.agent-harness' / 'config.toml').write_text(
            'engram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        settings = self.write_json('.claude/settings.json', {'env': {'X': '1'}})
        codex = self.engram_codex_config()
        self.install()
        cloud = {'ENGRAM_CLOUD_SERVER': 'https://engram.example', 'ENGRAM_CLOUD_AUTOSYNC': '1'}
        self.assertEqual(json.loads(settings.read_text(encoding='utf-8'))['env'], {'X': '1', **SPAWN, **cloud})
        self.assertEqual(tomllib.loads(codex.read_text(encoding='utf-8'))['mcp_servers']['engram']['env'], cloud)
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_no_engram_cloud_settings_without_a_server(self):
        codex = self.engram_codex_config()
        self.install()
        self.assertNotIn('ENGRAM_CLOUD_SERVER', json.loads((self.home / '.claude' / 'settings.json').read_text(encoding='utf-8')).get('env', {}))
        self.assertNotIn('env', tomllib.loads(codex.read_text(encoding='utf-8'))['mcp_servers']['engram'])

    def test_removing_the_server_turns_engram_cloud_off(self):
        # Dropping engram_cloud_server must stop the sync, not leave the old server behind.
        config = self.home / '.agent-harness' / 'config.toml'
        config.parent.mkdir()
        config.write_text('engram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        settings = self.write_json('.claude/settings.json', {'env': {'X': '1'}})
        codex = self.engram_codex_config()
        codex.write_text(codex.read_text(encoding='utf-8') + '\n[mcp_servers.engram.env]\nY = "2"\n',
                         encoding='utf-8', newline='\n')
        self.install()
        config.unlink()
        self.install()
        self.assertEqual(json.loads(settings.read_text(encoding='utf-8'))['env'], {'X': '1', **SPAWN})
        self.assertEqual(tomllib.loads(codex.read_text(encoding='utf-8'))['mcp_servers']['engram']['env'], {'Y': '2'})

    def test_policy_hooks_block_when_they_fail(self):
        # Claude blocks when the guard cannot run; the guard itself denies when it errors.
        self.install()
        data = json.loads((self.home / '.claude/settings.json').read_text(encoding='utf-8'))
        for hook in (h for entries in data['hooks'].values() for entry in entries for h in entry['hooks']):
            guard = any(arg.endswith('harness_guards.py') for arg in hook['args'])
            self.assertEqual(hook.get('onFailure'), 'block' if guard else None, hook['args'])
        guard = REPO / 'core/hooks/harness_guards.py'
        for args in (['bash'], ['bash', '--codex'], ['mcp'], ['backup'], ['bash', '--copilot']):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(guard), *args], input='not json',
                                        capture_output=True, encoding='utf-8')
                out = json.loads(result.stdout)
                self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')
                if '--copilot' in args:
                    self.assertEqual(out['permissionDecision'], 'deny')

    def test_guards_cover_mcp_tools_that_run_commands(self):
        # Desktop Commander and similar MCP servers run shell commands outside the Bash tool.
        self.install()
        for rel, args in (('.claude/settings.json', ['mcp']), ('.codex/hooks.json', ['mcp', '--codex'])):
            data = json.loads((self.home / rel).read_text(encoding='utf-8'))
            entries = data['hooks']['PreToolUse']
            matched = [e for e in entries if re.fullmatch(e.get('matcher', ''), 'mcp__desktop-commander__start_process')
                       and self.commands([e])[0].endswith('harness_guards.py ' + ' '.join(args))]
            self.assertTrue(matched, rel)

    def test_installed_claude_hooks_run_as_written(self):
        # Exactly what Claude Code spawns: command + args with no shell (py -3 on Windows), from a spaced home.
        home = Path(tempfile.mkdtemp()) / 'with space'
        home.mkdir()
        (home / '.agent-harness').mkdir()
        (home / '.agent-harness' / 'config.toml').write_text(
            'engram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(home))
        data = json.loads((home / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home)}
        commit = {'tool_name': 'Bash', 'cwd': str(home), 'tool_input': {'command': 'git commit -m "Update stuff"'}}
        ran = 0
        for event, entries in data['hooks'].items():
            for hook in (h for entry in entries for h in entry['hooks']):
                argv = [hook['command'], *hook['args']]
                payload = commit if event == 'PreToolUse' else {'cwd': str(home), 'transcript_path': ''}
                result = subprocess.run(argv, input=json.dumps(payload), capture_output=True,
                                        encoding='utf-8', timeout=60, env=env)
                self.assertEqual(result.returncode, 0, (argv, result.stderr))
                if argv[-1] == 'bash':
                    self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
                ran += 1
        self.assertEqual(ran, 8)  # with the MCP guard

    def test_claude_hooks_run_without_a_shell(self):
        # Exec form: Claude spawns the interpreter itself, so zsh, Git Bash and PowerShell behave alike.
        (self.home / '.agent-harness').mkdir(exist_ok=True)
        (self.home / '.agent-harness' / 'config.toml').write_text(
            'python = "/usr/bin/python3"\nengram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        self.install()
        hooks = (self.home / '.claude' / 'hooks').as_posix()
        data = json.loads((self.home / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        argv = [[h['command'], *h.get('args', [])] for entries in data['hooks'].values()
                for entry in entries for h in entry['hooks']]
        self.assertIn(['/usr/bin/python3', f'{hooks}/harness_guards.py', 'bash'], argv)
        self.assertIn(['/usr/bin/python3', f'{hooks}/engram_auto_enroll.py'], argv)
        self.assertTrue(all(cmd == '/usr/bin/python3' for cmd, *_ in argv), argv)

    @unittest.skipUnless(os.name == 'nt', 'Windows interpreter choice')
    def test_windows_hooks_use_the_py_launcher(self):
        # py -3 survives Python upgrades; without it, the Python that ran the install.
        self.install()
        data = json.loads((self.home / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        hook = data['hooks']['Stop'][0]['hooks'][0]
        expected = ['py', '-3'] if shutil.which('py') else [sys.executable.replace('\\', '/')]
        self.assertEqual([hook['command'], *hook['args']][:len(expected)], expected)

    def test_bash_guards_also_match_the_powershell_tool(self):
        self.install()
        data = json.loads((self.home / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        for entry in data['hooks']['PreToolUse']:
            if self.commands([entry])[0].endswith(('harness_guards.py bash', 'enforce_memory_graph.py pretool')):
                self.assertIn('PowerShell', entry['matcher'].split('|'), entry)

    def test_settings_merge_keeps_foreign_parts(self):
        (self.home / '.agent-harness').mkdir(exist_ok=True)
        (self.home / '.agent-harness' / 'config.toml').write_text(
            'python = "/usr/bin/python3"\nengram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        foreign = {'hooks': [{'type': 'command', 'command': 'codegraph prompt-hook'}]}
        settings = self.write_json('.claude/settings.json', {
            'env': {'X': '1'},
            'hooks': {
                'UserPromptSubmit': [foreign],
                'Stop': [{'hooks': [{'type': 'command', 'timeout': 5,
                                     'command': 'python3 /old/.claude/hooks/enforce_memory_graph.py stop'}]}],
            }})
        self.install()
        data = json.loads(settings.read_text(encoding='utf-8'))
        self.assertEqual(data['env'], {'X': '1', **SPAWN, 'ENGRAM_CLOUD_SERVER': 'https://engram.example', 'ENGRAM_CLOUD_AUTOSYNC': '1'})
        self.assertEqual(data['hooks']['UserPromptSubmit'], [foreign])
        hooks = (self.home / '.claude' / 'hooks').as_posix()
        self.assertEqual(self.commands(data['hooks']['Stop']), [
            f'/usr/bin/python3 {hooks}/enforce_memory_graph.py stop',
            f'/usr/bin/python3 {hooks}/engram_auto_enroll.py',
            f'/usr/bin/python3 {hooks}/enforce_memory_graph.py evidence'])
        self.assertIn(f'/usr/bin/python3 {hooks}/harness_guards.py bash',
                      self.commands(data['hooks']['PreToolUse']))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    @unittest.skipIf(os.name == 'nt', 'POSIX command form')
    def test_codex_commands_stay_plain_on_posix(self):
        # Codex trusts hooks by command hash: unchanged bytes mean no re-approval on the Mac.
        (self.home / '.agent-harness').mkdir()
        (self.home / '.agent-harness' / 'config.toml').write_text('python = "/usr/bin/python3"\n', encoding='utf-8', newline='\n')
        self.install()
        hooks = json.loads((self.home / '.codex' / 'hooks.json').read_text(encoding='utf-8'))['hooks']
        self.assertIn(f'/usr/bin/python3 {self.home.as_posix()}/.claude/hooks/harness_guards.py bash --codex',
                      self.commands(hooks['PreToolUse']))

    def test_codex_guard_commands_run_in_the_platform_hook_shell(self):
        # Codex runs hook commands with sh on POSIX and PowerShell on Windows; profiles may have spaces.
        home = Path(tempfile.mkdtemp()) / 'with space'
        home.mkdir()
        harness('install', '--home', str(home))
        hooks = json.loads((home / '.codex' / 'hooks.json').read_text(encoding='utf-8'))['hooks']
        guard = next(c for c in self.commands(hooks['PreToolUse']) if c.endswith('--codex'))
        shell = ['powershell', '-NoProfile', '-Command'] if os.name == 'nt' else ['sh', '-c']
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git commit -m "Update stuff"'}})
        result = subprocess.run([*shell, guard], input=payload, capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (guard, result.stderr))
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_codex_hooks_keep_foreign_entries_at_their_index(self):
        self.set_server()
        foreign = {'hooks': [{'type': 'command', 'command': 'impeccable hook', 'timeout': 30}]}
        old = lambda cmd: {'hooks': [{'type': 'command', 'command': cmd}]}
        hooks_json = self.write_json('.codex/hooks.json', {'hooks': {
            'PostToolUse': [foreign],
            'Stop': [old('python3 /x/.codex/hooks/engram_auto_enroll.py'), foreign,
                     old('python3 /x/.claude/hooks/enforce_memory_graph.py stop')],
        }})
        self.install()
        hooks = json.loads(hooks_json.read_text(encoding='utf-8'))['hooks']
        self.assertEqual(hooks['PostToolUse'], [foreign])
        stop = hooks['Stop']
        self.assertEqual(len(stop), 4)
        self.assertEqual(stop[1], foreign)
        self.assertTrue(self.commands([stop[0]])[0].endswith('/.codex/hooks/engram_auto_enroll.py'))
        self.assertTrue(self.commands([stop[2]])[0].endswith('/.claude/hooks/enforce_memory_graph.py stop'))
        self.assertTrue(self.commands([stop[3]])[0].endswith('/.claude/hooks/enforce_memory_graph.py evidence'))
        self.assertEqual(len(hooks['PreToolUse']), 4)  # with the MCP guard

    def test_rules_block_keeps_codex_added_rules(self):
        block = (REPO / 'core' / 'hooks' / 'codex.rules').read_text(encoding='utf-8')
        rules = self.home / '.codex' / 'rules' / 'default.rules'
        rules.parent.mkdir(parents=True)
        mine = 'prefix_rule(pattern=["npm", "run", "build"], decision="allow")\n'
        old_copy = next(line for line in block.splitlines() if line.startswith('prefix_rule'))
        rules.write_text(mine + old_copy + '\n', encoding='utf-8', newline='\n')
        self.install()
        text = rules.read_text(encoding='utf-8')
        self.assertTrue(text.startswith(mine))
        self.assertEqual(text.count(old_copy), 1)
        self.assertEqual(text.count('# >>> agent-harness'), 1)
        added = 'prefix_rule(pattern=["make"], decision="allow")\n'
        rules.write_text(text + added, encoding='utf-8', newline='\n')
        self.assertIn('no changes', harness('install', '--home', str(self.home)))
        self.assertTrue(rules.read_text(encoding='utf-8').endswith(added))

    def test_repo_hook_selftests_pass(self):
        for script in ('harness_guards.py', 'enforce_memory_graph.py'):
            result = subprocess.run([sys.executable, str(REPO / 'core' / 'hooks' / script), 'selftest'],
                                    capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, f'{script}: {result.stdout}{result.stderr}')

    def test_failing_selftest_fails_check(self):
        self.install()
        broken = self.home / '.claude' / 'hooks' / 'harness_guards.py'
        broken.write_text('import sys\nsys.exit(1)\n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'selftest failed: {broken}', result.stdout)


class Copilot(unittest.TestCase):
    PROMPTS = Path('Library/Application Support/Code/User/prompts')

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_render_has_every_section_and_its_own_orchestration(self):
        text = harness('render', 'copilot')
        self.assertEqual(len(re.findall(r'<!-- copilot-native:[a-z-]+ -->', text)), 10)
        self.assertIn('## Native GitHub Copilot Orchestration', text)
        self.assertNotIn('Claude Code', text)

    def test_install_writes_instructions_agents_hooks_and_retires_old_files(self):
        (self.home / '.copilot').mkdir()
        prompts = self.home / self.PROMPTS
        prompts.mkdir(parents=True)
        (prompts / 'gentle-ai.instructions.md').write_text('old\n', encoding='utf-8', newline='\n')
        (prompts / 'sonar-fix.prompt.md').write_text('mine\n', encoding='utf-8', newline='\n')
        # VS Code's migration copies profile instructions here, beside copilot-instructions.md.
        migrated = self.home / '.copilot' / 'instructions' / 'agent-harness.instructions.md'
        migrated.parent.mkdir()
        migrated.write_text('old\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertFalse(migrated.exists())
        self.assertEqual((self.home / '.copilot' / 'copilot-instructions.md').read_text(encoding='utf-8'),
                         harness('render', 'copilot'))
        local = (prompts / 'agent-harness.instructions.md').read_text(encoding='utf-8')
        self.assertTrue(local.startswith("---\napplyTo: '**'\n"))
        self.assertFalse((prompts / 'gentle-ai.instructions.md').exists())
        self.assertTrue((prompts / 'sonar-fix.prompt.md').exists())
        agent = (self.home / '.copilot' / 'agents' / 'test-runner.agent.md').read_text(encoding='utf-8')
        self.assertTrue(agent.startswith('---\nname: test-runner\ndescription: '))
        self.assertIn('\ntools: ["read", "search", "execute"]\n---', agent)  # unset means every tool
        hooks = json.loads((self.home / '.copilot' / 'hooks' / 'agent-harness.json').read_text(encoding='utf-8'))
        # Copilot runs `bash` on macOS/Linux and `powershell` on Windows; one key per PC, with the full interpreter.
        shell = 'powershell' if os.name == 'nt' else 'bash'
        commands = [h[shell] for h in hooks['hooks']['PreToolUse']]
        keys = {key for h in hooks['hooks']['PreToolUse'] for key in h}
        self.assertEqual(keys & {'bash', 'powershell', 'args'}, {shell})
        self.assertIn(f'{self.home.as_posix()}/.claude/hooks/harness_guards.py bash --copilot', ' '.join(commands))
        if os.name == 'nt' and shutil.which('py'):
            self.assertTrue(commands[0].startswith('py -3 '), commands[0])
        stop = [h[shell] for h in hooks['hooks']['Stop']]
        guard = f'{self.home.as_posix()}/.claude/hooks/enforce_memory_graph.py'
        self.assertEqual(len(stop), 2)
        self.assertIn(f'{guard} evidence --copilot', stop[0])
        self.assertIn(f'{guard} stop --copilot', stop[1])
        self.assertIn(f'{guard} pretool --copilot', ' '.join(commands))
        self.assertEqual(len(commands), 3)
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_nothing_for_copilot_when_it_is_not_installed(self):
        harness('install', '--home', str(self.home))
        self.assertFalse((self.home / '.copilot').exists())


class NewPC(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_clean_install_with_every_agent_passes_check(self):
        for folder in ('.copilot', 'Library/Application Support/Code/User/prompts'):
            (self.home / folder).mkdir(parents=True)
        harness('install', '--home', str(self.home))
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'), result.stdout)

    def test_hook_selftest_without_zstd_skips_those_cases(self):
        script = REPO / 'core' / 'hooks' / 'enforce_memory_graph.py'
        hide = ("import runpy, sys; sys.modules['compression.zstd'] = None; "
                f"sys.argv = ['x', 'selftest']; runpy.run_path({str(script)!r}, run_name='__main__')")
        result = subprocess.run([sys.executable, '-c', hide], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('skipped zstd cases', result.stdout)

    def test_linux_and_windows_vscode_profiles_get_the_prompt_file(self):
        for profile in ('.config/Code/User', 'AppData/Roaming/Code/User'):
            home = Path(tempfile.mkdtemp())
            (home / '.copilot').mkdir()
            (home / profile).mkdir(parents=True)  # no prompts folder yet: VS Code creates it lazily
            harness('install', '--home', str(home))
            self.assertTrue((home / profile / 'prompts' / 'agent-harness.instructions.md').is_file(), profile)

    def test_readme_commands_and_paths_exist(self):
        readme = (REPO / 'README.md').read_text(encoding='utf-8')
        usage = subprocess.run([sys.executable, str(HARNESS), '--help'], capture_output=True, encoding='utf-8').stdout
        for command in set(re.findall(r'bin/harness (\w+)', readme)):
            self.assertIn(command, usage, command)
        for path in set(re.findall(r'`(core/[\w./-]+?)/?`', readme)):
            if '<' not in path and 'NN-' not in path:
                self.assertTrue((REPO / path).exists(), path)
        self.assertTrue((REPO / 'LICENSE').read_text(encoding='utf-8').startswith('MIT License'))

    def test_old_python_gets_a_clear_message(self):
        fake = ("import runpy, sys; sys.version_info = (3, 10, 0); "
                f"sys.argv = ['harness', 'check']; runpy.run_path({str(HARNESS)!r}, run_name='__main__')")
        result = subprocess.run([sys.executable, '-c', fake], capture_output=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('needs Python 3.11 or newer', result.stderr)


class EvidenceOutput(unittest.TestCase):
    """VS Code's Copilot reads a Stop decision only inside hookSpecificOutput; Claude Code and Codex read it at the top."""

    def decide(self, *flags, mode='evidence'):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / 't.jsonl'
            transcript.write_text('\n'.join(json.dumps(e) for e in (
                {'type': 'user.message', 'data': {}},
                {'type': 'tool.execution_start', 'data': {
                    'toolName': 'apply_patch', 'arguments': {'input': '*** Update File: src/a.py\r\n@@\r\n'}}},
            )), encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(REPO / 'core/hooks/enforce_memory_graph.py'), mode, *flags],
                input=json.dumps({'transcript_path': str(transcript)}), capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_copilot_gets_the_decision_inside_hook_specific_output(self):
        out = self.decide('--copilot')
        specific = out['hookSpecificOutput']
        self.assertEqual((specific['hookEventName'], specific['decision']), ('Stop', 'block'))
        self.assertIn('editó 1 archivo', specific['reason'])
        self.assertEqual(out['decision'], 'block')  # Copilot CLI documents the top-level form

    def test_claude_and_codex_output_is_unchanged(self):
        self.assertEqual(set(self.decide()), {'decision', 'reason'})
        self.assertEqual(set(self.decide(mode='stop')), {'decision', 'reason'})

    def test_copilot_engram_stop_gets_the_decision_in_both_places(self):
        out = self.decide('--copilot', mode='stop')
        self.assertEqual((out['decision'], out['hookSpecificOutput']['hookEventName']), ('block', 'Stop'))
        self.assertEqual(out['hookSpecificOutput']['decision'], 'block')
        self.assertIn('Engram', out['hookSpecificOutput']['reason'])


def load_hook(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'core' / 'hooks' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAKE_ENGRAM = """import os, sqlite3, sys
conn = sqlite3.connect(os.path.join(os.environ['ENGRAM_DATA_DIR'], 'engram.db'))
conn.execute('INSERT INTO sync_enrolled_projects VALUES (?)', (sys.argv[3],))
conn.commit()
conn.close()
"""


class EngramEnroll(unittest.TestCase):
    """The auto-enroll hook runs on SessionStart and Stop for Claude Code and Codex, on every OS."""

    def setUp(self):
        self.hook = load_hook('engram_auto_enroll')
        self.data = Path(tempfile.mkdtemp())
        conn = sqlite3.connect(self.data / 'engram.db')
        conn.executescript(
            'CREATE TABLE observations (project, deleted_at); CREATE TABLE sessions (project);'
            'CREATE TABLE user_prompts (project); CREATE TABLE sync_enrolled_projects (project);'
            "INSERT INTO sessions VALUES ('app'), ('scratch-x');")
        conn.commit()
        conn.close()
        fake = self.data / 'fake_engram.py'
        fake.write_text(FAKE_ENGRAM, encoding='utf-8', newline='\n')
        self.engram = [sys.executable, str(fake)]

    def test_enrolls_missing_projects_once(self):
        self.assertEqual(self.hook.enroll_missing(self.data, self.engram), 1)
        self.assertEqual(self.hook.enroll_missing(self.data, self.engram), 0)

    def test_skips_while_another_session_holds_the_lock(self):
        with open(self.data / 'codex-auto-enroll.lock', 'w') as other:
            self.hook.try_lock(other)
            self.assertEqual(self.hook.enroll_missing(self.data, ['no-such-engram']), 0)

    def test_without_a_database_does_nothing(self):
        self.assertEqual(self.hook.enroll_missing(Path(tempfile.mkdtemp()), ['no-such-engram']), 0)

    def test_finds_engram_on_path_before_homebrew(self):
        bin_dir = Path(tempfile.mkdtemp())
        exe = bin_dir / ('engram.exe' if os.name == 'nt' else 'engram')
        exe.write_text('', encoding='utf-8')
        exe.chmod(0o755)
        with mock.patch.dict(os.environ, {'PATH': str(bin_dir)}):
            self.assertEqual(os.path.normcase(self.hook.engram_command()[0]), os.path.normcase(str(exe)))
        with mock.patch.dict(os.environ, {'PATH': ''}):
            self.assertEqual(self.hook.engram_command(), ['/opt/homebrew/bin/engram'])


class Portability(unittest.TestCase):
    """Windows defaults to cp1252; an ASCII locale reproduces the same failures on Unix."""
    ASCII = {**os.environ, 'LC_ALL': 'C', 'LANG': 'C', 'PYTHONUTF8': '0', 'PYTHONIOENCODING': ''}

    def ascii_run(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8=0', *args], capture_output=True, env=self.ASCII)

    def test_harness_commands_work_without_a_utf8_locale(self):
        home = Path(tempfile.mkdtemp())
        (home / '.copilot').mkdir(parents=True)
        render = self.ascii_run(str(HARNESS), 'render', 'claude')
        self.assertEqual(render.returncode, 0, render.stderr)
        self.assertEqual(render.stdout.decode('utf-8'), harness('render', 'claude'))
        for command in (['install', '--home', str(home)], ['check', '--home', str(home)],
                        ['doctor', '--home', str(home)]):
            result = self.ascii_run(str(HARNESS), *command)
            self.assertEqual(result.returncode, 0, (command, result.stdout, result.stderr))
        self.assertEqual((home / '.claude' / 'CLAUDE.md').read_text(encoding='utf-8'), harness('render', 'claude'))

    def test_hook_selftests_work_without_a_utf8_locale(self):
        for script in ('harness_guards.py', 'enforce_memory_graph.py'):
            result = self.ascii_run(str(REPO / 'core' / 'hooks' / script), 'selftest')
            self.assertEqual(result.returncode, 0, (script, result.stderr))

    def test_rendered_hook_paths_use_forward_slashes(self):
        # hook_key() matches `/hooks/`, and Git Bash would eat Windows backslashes.
        home = Path(tempfile.mkdtemp())
        (home / '.copilot').mkdir()
        harness('install', '--home', str(home))
        for config in ('.claude/settings.json', '.codex/hooks.json', '.copilot/hooks/agent-harness.json'):
            self.assertNotIn('\\', (home / config).read_text(encoding='utf-8'), config)


@unittest.skipIf(os.name == 'nt', 'the fake engram and claude are shell scripts')
class EngramMcp(unittest.TestCase):
    # Engram's Claude plugin stopped shipping .mcp.json in 0.1.16; the MCP is now a user-scope server.
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        bin_dir = Path(tempfile.mkdtemp())
        for name, script in (('engram', 'exit 0\n'),
                             ('claude', 'echo "$@" >> "$HOME/claude-args"\n'
                                        '[ "$2" = add ] && printf \'{"mcpServers": {"engram": {"type": "stdio", '
                                        '"command": "engram"}}}\' > "$HOME/.claude.json"\n'
                                        '[ "$2" = remove ] && printf \'{"mcpServers": {}}\' > "$HOME/.claude.json"\n'
                                        'exit 0\n')):
            (bin_dir / name).write_text('#!/bin/sh\n' + script, encoding='utf-8', newline='\n')
            (bin_dir / name).chmod(0o755)
        self.engram = bin_dir / 'engram'
        self.env = {**os.environ, 'PATH': os.pathsep.join([str(bin_dir), '/usr/bin', '/bin'])}
        plugin = self.home / '.claude/plugins/cache/engram/engram/0.1.16'
        plugin.mkdir(parents=True)
        (self.home / '.claude/plugins/installed_plugins.json').write_text(json.dumps(
            {'plugins': {'engram@engram': [{'installPath': str(plugin), 'version': '0.1.16'}]}}), encoding='utf-8')

    def run_harness(self, *args):
        result = subprocess.run([sys.executable, str(HARNESS), *args, '--home', str(self.home)],
                                capture_output=True, encoding='utf-8', env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_install_registers_the_engram_mcp_once(self):
        self.assertIn('would register the Engram MCP', self.run_harness('install', '--dry-run'))
        self.assertFalse((self.home / 'claude-args').exists())
        self.run_harness('install')
        self.assertEqual((self.home / 'claude-args').read_text(encoding='utf-8'),
                         f'mcp add --transport stdio --scope user engram -- {self.engram} mcp --tools=agent\n')
        self.assertIn('no changes', self.run_harness('install'))

    def test_install_repairs_an_engram_entry_without_a_command(self):
        # An entry left with only its type starts nothing, and `claude mcp add` refuses a name that exists.
        (self.home / '.claude.json').write_text('{"mcpServers": {"engram": {"type": "stdio"}}}', encoding='utf-8')
        self.run_harness('install')
        self.assertEqual((self.home / 'claude-args').read_text(encoding='utf-8'),
                         'mcp remove --scope user engram\n'
                         f'mcp add --transport stdio --scope user engram -- {self.engram} mcp --tools=agent\n')
        self.assertIn('no changes', self.run_harness('install'))

    def test_copilot_gets_engram_and_keeps_its_other_servers(self):
        # VS Code's Copilot target reads ~/.copilot/mcp-config.json, which Settings Sync does not carry.
        config = self.home / '.copilot' / 'mcp-config.json'
        config.parent.mkdir()
        chrome = {'type': 'local', 'command': 'npx', 'args': ['-y', 'chrome-devtools-mcp@latest'], 'tools': ['*']}
        config.write_text(json.dumps({'mcpServers': {'chrome-devtools': chrome}}), encoding='utf-8')
        self.run_harness('install')
        self.assertEqual(json.loads(config.read_text(encoding='utf-8'))['mcpServers'], {
            'chrome-devtools': chrome, 'context7': self.CONTEXT7,
            'engram': {'type': 'local', 'command': str(self.engram), 'args': ['mcp', '--tools=agent'], 'tools': ['*']}})
        self.assertIn('no changes', self.run_harness('install'))
        mine = {'engram': {'command': 'engram'}, 'context7': {'command': 'mine'}}  # entries of the user's own stay as written
        config.write_text(json.dumps({'mcpServers': mine}), encoding='utf-8')
        written = config.read_bytes()
        self.run_harness('install')
        self.assertEqual(config.read_bytes(), written)

    CONTEXT7 = {'type': 'http', 'url': 'https://mcp.context7.com/mcp', 'tools': ['*']}

    def copilot_servers(self, existing=None):
        config = self.home / '.copilot' / 'mcp-config.json'
        config.parent.mkdir(exist_ok=True)
        if existing is not None:
            config.write_text(json.dumps({'mcpServers': existing}), encoding='utf-8')
        self.run_harness('install')
        return json.loads(config.read_text(encoding='utf-8'))['mcpServers'] if config.is_file() else None

    def test_copilot_is_not_given_context7_twice_when_vscode_has_it(self):
        user = self.home / 'Library/Application Support/Code/User'
        user.mkdir(parents=True)
        (user / 'mcp.json').write_text('{\n  // comment\n  "servers": {"io.github.upstash/context7": {}}\n}\n',
                                       encoding='utf-8', newline='\n')
        self.assertNotIn('context7', self.copilot_servers({'chrome-devtools': {'type': 'local', 'command': 'npx'}}))

    def test_copilot_gets_context7_next_to_its_other_servers(self):
        chrome = {'type': 'local', 'command': 'npx', 'args': ['-y', 'chrome-devtools-mcp@latest'], 'tools': ['*']}
        servers = self.copilot_servers({'chrome-devtools': chrome})
        self.assertEqual(servers['context7'], self.CONTEXT7)
        self.assertEqual(servers['chrome-devtools'], chrome)

    def test_copilot_keeps_an_existing_context7_server(self):
        for name, entry in (('io.github.upstash/context7', {'command': 'npx', 'args': ['@upstash/context7-mcp']}),
                            ('docs', {'type': 'http', 'url': 'https://mcp.context7.com/mcp'})):
            self.assertNotIn('context7', self.copilot_servers({name: entry}))
            self.assertEqual(self.copilot_servers()[name], entry)

    def test_copilot_mcp_file_is_created_with_context7(self):
        self.assertEqual(self.copilot_servers()['context7'], self.CONTEXT7)

    def test_copilot_mcp_table_in_another_shape_does_not_break_install(self):
        config = self.home / '.copilot' / 'mcp-config.json'
        config.parent.mkdir()
        config.write_text('{"mcpServers": null}', encoding='utf-8')  # an empty table is filled like a missing one
        self.run_harness('install')
        self.assertEqual(json.loads(config.read_text(encoding='utf-8'))['mcpServers']['context7'], self.CONTEXT7)
        for odd in ('{"mcpServers": []}', '{"mcpServers": "x"}', '[]'):  # not a table: the user's to fix, left as written
            config.write_text(odd, encoding='utf-8')
            self.run_harness('install')
            self.assertEqual(config.read_text(encoding='utf-8'), odd)
            self.run_harness('doctor')
        # check reports a file that is not a JSON object instead of crashing on it
        result = subprocess.run([sys.executable, str(HARNESS), 'check', '--home', str(self.home)],
                                capture_output=True, encoding='utf-8', env=self.env)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f'invalid: {config}', result.stdout)

    def test_doctor_reports_a_missing_engram_mcp(self):
        self.assertIn('engram MCP is not registered for Claude Code', self.run_harness('doctor'))
        (self.home / '.claude.json').write_text('{"mcpServers": {"engram": {"type": "stdio"}}}', encoding='utf-8')
        self.assertIn('engram MCP for Claude Code has no command', self.run_harness('doctor'))
        (self.home / '.claude.json').write_text('{"mcpServers": {"engram": {"command": "engram"}}}', encoding='utf-8')
        self.assertNotIn('engram MCP', self.run_harness('doctor'))


class Doctor(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {**os.environ, 'PATH': os.pathsep.join(['/usr/bin', '/bin'])}

    def doctor(self, **env):
        result = subprocess.run([sys.executable, str(HARNESS), 'doctor', '--home', str(self.home)],
                                capture_output=True, encoding='utf-8', env={**self.env, **env})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    @unittest.skipIf(os.name == 'nt', 'the fake engram is a shell script')
    def test_engram_cloud_status(self):
        bin_dir = Path(tempfile.mkdtemp())
        fake = bin_dir / 'engram'
        fake.write_text('#!/bin/sh\n[ "$1" = cloud ] && printf "Cloud status: %s\\nServer: https://engram.example\\n'
                        'Auth status: %s\\n" "$CLOUD" "$AUTH"\nexit 0\n', encoding='utf-8', newline='\n')
        fake.chmod(0o755)
        (self.home / '.agent-harness').mkdir()
        (self.home / '.agent-harness' / 'config.toml').write_text(
            'engram_cloud_server = "https://engram.example"\n', encoding='utf-8', newline='\n')
        path = os.pathsep.join([str(bin_dir), '/usr/bin', '/bin'])
        out = self.doctor(PATH=path, CLOUD='configured (target=cloud)', AUTH='ready (token provided via ENGRAM_CLOUD_TOKEN)')
        self.assertIn('engram cloud: configured (target=cloud), server https://engram.example, auth ready', out)
        self.assertNotIn('not ready', out)
        out = self.doctor(PATH=path, CLOUD='not configured', AUTH='missing token')
        self.assertIn('engram cloud is not ready', out)

    @unittest.skipIf(os.name == 'nt', 'the fake claude is a shell script')
    def test_old_claude_code_lets_failing_guards_through(self):
        # 2.1.319 closes the last known guard bypasses (env-prefix Bash permissions, worktree sandbox escape).
        bin_dir = Path(tempfile.mkdtemp())
        fake = bin_dir / 'claude'
        fake.write_text('#!/bin/sh\necho "$VERSION (Claude Code)"\n', encoding='utf-8', newline='\n')
        fake.chmod(0o755)
        path = os.pathsep.join([str(bin_dir), '/usr/bin', '/bin'])
        self.assertIn('claude code 2.1.318 can let actions past the guards', self.doctor(PATH=path, VERSION='2.1.318'))
        self.assertNotIn('past the guards', self.doctor(PATH=path, VERSION='2.1.319'))

    @unittest.skipIf(os.name == 'nt', 'the fake engram is a shell script')
    def test_engram_update_comes_from_the_latest_release(self):
        # The Homebrew tap can lag the release, so brew info hides the drift.
        tool = load_harness()
        bin_dir = Path(tempfile.mkdtemp())
        (bin_dir / 'engram').write_text('#!/bin/sh\necho "engram $ENGRAM_V"\n', encoding='utf-8', newline='\n')
        (bin_dir / 'engram').chmod(0o755)
        release = lambda *args, **kwargs: io.BytesIO(b'{"tag_name": "v3.7.0"}')
        which = lambda name: str(bin_dir / 'engram') if name == 'engram' else None

        def doctor(version):
            out = io.StringIO()
            with mock.patch.object(tool.urllib.request, 'urlopen', release), mock.patch.object(tool.shutil, 'which', which), \
                    mock.patch.dict(os.environ, ENGRAM_V=version, PATH=f'{bin_dir}{os.pathsep}/usr/bin:/bin'), contextlib.redirect_stdout(out):
                tool.doctor(self.home)
            return out.getvalue()
        out = doctor('3.5.4')
        self.assertIn('engram update available: 3.5.4 -> 3.7.0', out)
        out = doctor('3.7.0')
        self.assertNotIn('engram update available', out)

    @unittest.skipIf(os.name == 'nt', 'the fake codegraph and npm are shell scripts')
    def test_codegraph_update_asks_for_a_reindex(self):
        bin_dir = Path(tempfile.mkdtemp())
        for name, version in (('codegraph', '$INSTALLED'), ('npm', '$LATEST')):
            (bin_dir / name).write_text(f'#!/bin/sh\necho "{version}"\n', encoding='utf-8', newline='\n')
            (bin_dir / name).chmod(0o755)
        path = os.pathsep.join([str(bin_dir), '/usr/bin', '/bin'])
        out = self.doctor(PATH=path, INSTALLED='1.1.6', LATEST='1.6.2')
        self.assertIn('codegraph update available: 1.1.6 -> 1.6.2', out)
        self.assertIn('codegraph index', out)
        self.assertNotIn('codegraph update', self.doctor(PATH=path, INSTALLED='1.6.2', LATEST='1.6.2'))
        self.assertNotIn('codegraph update', self.doctor(PATH=path, INSTALLED='1.7.0', LATEST='1.6.2'))

    def test_hook_trust_is_unverified_without_the_codex_api(self):
        # A stored hash, absent state, or disabled feature never proves effective trust.
        harness('install', '--home', str(self.home))
        hooks = (self.home / '.codex' / 'hooks.json')
        events = json.loads(hooks.read_text(encoding='utf-8'))['hooks']
        state = [f'{hooks.as_posix()}:{re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()}:{i}:0'
                 for event, entries in events.items() for i in range(len(entries))]
        config = self.home / '.codex' / 'config.toml'
        base = config.read_text(encoding='utf-8') if config.is_file() else ''
        write = lambda keys: config.write_text(base + '\n[hooks.state]\n' + ''.join(
            f'[hooks.state."{key}"]\ntrusted_hash = "sha256:00"\n' for key in keys), encoding='utf-8')
        write(state)
        self.assertIn('Codex hook state unverified', self.doctor())
        write([key for key in state if ':pre_tool_use:' not in key])
        out = self.doctor()
        self.assertIn('Codex hook state unverified', out)
        config.write_text(base, encoding='utf-8')
        self.assertIn('Codex hook state unverified', self.doctor())
        config.write_text(base + '\n[features]\nhooks = false\n', encoding='utf-8')
        self.assertIn('Codex hook state unverified', self.doctor())

    def test_orphan_skill_overrides(self):
        (self.home / '.claude' / 'skills' / 'present').mkdir(parents=True)
        command = self.home / '.claude/plugins/cache/market/tool/1.0/commands/tool-review.md'
        command.parent.mkdir(parents=True)
        command.write_text('# review\n', encoding='utf-8', newline='\n')
        (self.home / '.claude' / 'settings.json').write_text(json.dumps({'skillOverrides': {
            'present': 'off', 'ghost': 'off', 'init': 'user-invocable-only', 'tool:tool-review': 'off'}}), encoding='utf-8', newline='\n')
        out = self.doctor()
        self.assertIn('orphan skill override: ghost', out)
        self.assertNotIn('present', out)
        self.assertNotIn('tool-review', out)
        self.assertNotIn(': init', out)

    def test_duplicate_path_entries(self):
        out = self.doctor(PATH=os.pathsep.join(['/a', '/usr/bin', '/a', '/bin']))
        self.assertEqual(out.count('duplicate PATH entry: /a'), 1)

    def test_engram_plugins_compared_with_their_own_marketplace(self):
        # Claude and Codex ship separate Engram plugins with their own version numbers.
        plugins = self.home / '.claude' / 'plugins'
        (plugins / 'marketplaces' / 'engram' / '.claude-plugin').mkdir(parents=True)
        (plugins / 'installed_plugins.json').write_text(json.dumps(
            {'plugins': {'engram@engram': [{'version': '0.1.0'}]}}), encoding='utf-8', newline='\n')
        (plugins / 'marketplaces' / 'engram' / '.claude-plugin' / 'marketplace.json').write_text(json.dumps(
            {'plugins': [{'name': 'engram', 'version': '0.1.16'}]}), encoding='utf-8', newline='\n')
        (self.home / '.codex' / 'plugins' / 'cache' / 'engram' / 'engram' / '0.1.5').mkdir(parents=True)
        manifest = self.home / '.codex/.tmp/marketplaces/engram/plugin/codex/.codex-plugin/plugin.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'version': '0.1.5'}), encoding='utf-8', newline='\n')
        out = self.doctor()
        self.assertIn('engram claude plugin outdated: 0.1.0 -> 0.1.16', out)
        self.assertNotIn('codex plugin outdated', out)
        self.assertNotIn('plugins differ', out)

    def test_vscode_setting_pointing_to_a_missing_file(self):
        settings = self.home / 'Library/Application Support/Code/User/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{\n  // comment\n  "github.copilot.chat.instructions": [\n'
                            '    "Lee y sigue las reglas definidas en ~/.config/copilot/instructions.md",\n  ],\n}\n', encoding='utf-8', newline='\n')
        self.assertIn('github.copilot.chat.instructions points to a missing file: ~/.config/copilot/instructions.md',
                      self.doctor())

    def test_context7_missing_for_codex_or_copilot(self):
        finding = lambda agent: f'context7 MCP is not registered for {agent}'
        choice = self.home / '.agent-harness' / 'agents'
        choice.parent.mkdir()
        choice.write_text('claude\n', encoding='utf-8')
        self.assertNotIn('context7', self.doctor())  # Claude Code gets Context7 as a claude.ai connector: never checked
        choice.unlink()
        (self.home / '.copilot').mkdir()
        out = self.doctor()
        self.assertIn(finding('Codex'), out)
        self.assertIn(finding('Copilot'), out)
        (self.home / '.codex').mkdir()
        (self.home / '.codex' / 'config.toml').write_text('[mcp_servers.context7]\nurl = "https://mcp.context7.com/mcp"\n',
                                                          encoding='utf-8', newline='\n')
        (self.home / '.copilot' / 'mcp-config.json').write_text(
            json.dumps({'mcpServers': {'docs': {'url': 'https://mcp.context7.com/mcp'}}}), encoding='utf-8', newline='\n')
        self.assertNotIn('context7 MCP', self.doctor())
        (self.home / '.copilot' / 'mcp-config.json').write_text('{"mcpServers": null}', encoding='utf-8')
        self.assertIn(finding('Copilot'), self.doctor())  # an empty server table is a missing server, not a crash
        (self.home / '.copilot' / 'mcp-config.json').unlink()
        user = self.home / 'Library/Application Support/Code/User'
        user.mkdir(parents=True)
        (user / 'mcp.json').write_text('{\n  // comment\n  "servers": {"io.github.upstash/context7": {}}\n}\n',
                                       encoding='utf-8', newline='\n')
        self.assertNotIn('context7 MCP', self.doctor())

    def test_clean_setup_has_no_findings(self):
        (self.home / '.codex').mkdir()
        (self.home / '.codex' / 'config.toml').write_text('[mcp_servers.context7]\nurl = "https://mcp.context7.com/mcp"\n',
                                                          encoding='utf-8', newline='\n')
        self.assertIn('no findings', self.doctor())


class Delegation(unittest.TestCase):
    REASONS = ('**Exploration**', 'about 5 sequential lookups', '**Parallel writers**',
               'about 100 changed lines', '**Noisy checks**', '**Independent review**',
               'Risk line names an item', '**Context backstop**', 'about 150k tokens')
    GONE = ('Delegation is mandatory, not optional, when any trigger below applies',
            'Proactively delegate', 'required by the selected Standard or Critical assurance level')

    def test_inline_by_default_with_named_reasons(self):
        for agent in ('claude', 'codex'):
            text = harness('render', agent)
            for phrase in self.REASONS:
                self.assertTrue(phrase in text, f'{agent}: missing {phrase!r}')
            self.assertTrue('name the reason in one line' in text, f'{agent}: missing reason rule')
            for phrase in self.GONE:
                self.assertFalse(phrase in text, f'{agent}: still has {phrase!r}')


class Secrets(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_permissions_merge_keeps_user_entries(self):
        settings = self.home / '.claude' / 'settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'permissions': {
            'allow': ['Bash(npm run build)'], 'deny': ['Read(./secret.txt)']}}), encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        permissions = json.loads(settings.read_text(encoding='utf-8'))['permissions']
        self.assertEqual(permissions['allow'][0], 'Bash(npm run build)')
        self.assertIn('mcp__engram__mem_save', permissions['allow'])
        self.assertEqual(len(permissions['allow']), len(set(permissions['allow'])))
        self.assertEqual(permissions['deny'][0], 'Read(./secret.txt)')
        self.assertIn('Read(~/.aws/**)', permissions['deny'])
        self.assertIn('Read(**/.env)', permissions['ask'])
        self.assertEqual(len(permissions['deny']), len(set(permissions['deny'])))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_check_flags_literal_secrets_without_printing_them(self):
        harness('install', '--home', str(self.home))
        settings = self.home / '.claude' / 'settings.json'
        data = json.loads(settings.read_text(encoding='utf-8'))
        data['env'] = {'OPENAI_API_KEY': 'sk-very-secret', 'PATH': '/bin'}
        settings.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'secret: {settings}: env.OPENAI_API_KEY', result.stdout)
        self.assertNotIn('sk-very-secret', result.stdout)

    def test_check_ignores_token_counts_and_env_var_names(self):
        harness('install', '--home', str(self.home))
        settings = self.home / '.claude' / 'settings.json'
        data = json.loads(settings.read_text(encoding='utf-8'))
        data['env'] = {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '32000'}
        settings.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
        config = self.home / '.codex' / 'config.toml'
        config.write_text('[mcp_servers.x]\nurl = "https://x"\nbearer_token_env_var = "X_TOKEN"\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'))

    def test_codex_engram_mcp_receives_the_token_from_the_environment(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('[mcp_servers.engram]\ncommand = "engram"\n\n[mcp_servers.engram.env]\n'
                          'ENGRAM_CLOUD_AUTOSYNC = "1"\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        data = tomllib.loads(config.read_text(encoding='utf-8'))
        self.assertEqual(data['mcp_servers']['engram']['env_vars'], ['ENGRAM_CLOUD_TOKEN'])
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_codex_shell_commands_do_not_inherit_the_engram_token(self):
        # Codex passes the whole environment to its shell by default; only the Engram MCP needs the token.
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        engram = '[mcp_servers.engram]\ncommand = "engram"\n'
        for policy in ('', '\n[shell_environment_policy]\ninherit = "all"\n\n[shell_environment_policy.set ]\nX = "1"\n'):
            with self.subTest(policy=policy):
                config.write_text(engram + policy, encoding='utf-8', newline='\n')
                harness('install', '--home', str(self.home))
                data = tomllib.loads(config.read_text(encoding='utf-8'))
                self.assertEqual(data['shell_environment_policy']['exclude'], ['ENGRAM_CLOUD_TOKEN'])
                self.assertEqual(data['mcp_servers']['engram']['env_vars'], ['ENGRAM_CLOUD_TOKEN'])
                if policy:
                    self.assertEqual((data['shell_environment_policy']['inherit'],
                                      data['shell_environment_policy']['set']), ('all', {'X': '1'}))
                self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_codex_token_exclude_survives_every_policy_layout(self):
        # A layout the installer cannot edit must not cost the rest of the Codex config; doctor reports it.
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        engram = '[mcp_servers.engram]\ncommand = "engram"\n'
        for policy, edited in (('\n[shell_environment_policy]\nexclude = [\n  "AWS_*",\n]\n', True),
                               ('\n[shell_environment_policy] # mine\ninherit = "all"\n', True),
                               ('\n[shell_environment_policy]\nexclude = "a"\n', True),
                               ('shell_environment_policy.inherit = "all"\n', False),
                               ('shell_environment_policy = "x"\n', False)):
            with self.subTest(policy=policy):
                text = policy + engram if not edited else engram + policy
                config.write_text(text, encoding='utf-8', newline='\n')
                harness('install', '--home', str(self.home))
                data = tomllib.loads(config.read_text(encoding='utf-8'))
                self.assertEqual(data['mcp_servers']['engram']['env_vars'], ['ENGRAM_CLOUD_TOKEN'])
                policy_value = data['shell_environment_policy']
                exclude = policy_value.get('exclude', []) if isinstance(policy_value, dict) else []
                self.assertEqual('ENGRAM_CLOUD_TOKEN' in exclude, edited)
                if 'AWS_*' in policy:
                    self.assertEqual(exclude, ['AWS_*', 'ENGRAM_CLOUD_TOKEN'])
                doctor = run('doctor', '--home', str(self.home)).stdout
                self.assertEqual('Codex shell commands inherit ENGRAM_CLOUD_TOKEN' in doctor, not edited)

    def test_engram_token_leaves_codex_config(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('[mcp_servers.engram.env]\nOTHER = "1"\n'
                          'ENGRAM_CLOUD_TOKEN = "s3cr3t"\n\n[agents]\nenabled = true\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(encoding='utf-8'),
                         '[mcp_servers.engram.env]\nOTHER = "1"\n\n[agents]\nenabled = true\n')


class Plugins(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_superpowers_disabled_other_plugins_untouched(self):
        settings = self.home / '.claude' / 'settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'enabledPlugins': {
            'superpowers@claude-plugins-official': True, 'engram@engram': True}}), encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(json.loads(settings.read_text(encoding='utf-8'))['enabledPlugins'], {
            'superpowers@claude-plugins-official': False, 'engram@engram': True})

    def test_systematic_debugging_is_a_harness_skill(self):
        harness('install', '--home', str(self.home))
        for agent_dir in ('.claude', '.agents'):
            self.assertTrue((self.home / agent_dir / 'skills' / 'systematic-debugging' / 'SKILL.md').is_file())
        self.assertIn('core/skills/systematic-debugging', (REPO / 'NOTICE').read_text(encoding='utf-8'))

    def test_check_flags_reenabled_superpowers(self):
        harness('install', '--home', str(self.home))
        settings = self.home / '.claude' / 'settings.json'
        data = json.loads(settings.read_text(encoding='utf-8'))
        data['enabledPlugins']['superpowers@claude-plugins-official'] = True
        settings.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'drift: {settings}', result.stdout)

    def test_instructions_do_not_name_superpowers(self):
        for agent in ('claude', 'codex'):
            self.assertNotIn('Superpowers', harness('render', agent))

    def test_codex_config_changes_one_line(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        before = ('model = "x"\n\n[plugins."superpowers@openai-curated"]\nenabled = true\n\n'
                  '[plugins."other@x"]\nenabled = true\n')
        config.write_text(before, encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(encoding='utf-8'), before.replace('curated"]\nenabled = true', 'curated"]\nenabled = false'))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_codex_config_without_the_plugin_is_left_alone(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('model = "x"\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(encoding='utf-8'), 'model = "x"\n')


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
        (self.home / '.claude' / 'CLAUDE.md').write_text('hand edit\n', encoding='utf-8', newline='\n')
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
        settings.write_text('{"hooks": ', encoding='utf-8', newline='\n')
        config.write_text('model = \n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(settings), result.stdout)
        self.assertIn(str(config), result.stdout)


class Reconcile(unittest.TestCase):
    """`install` also clears what an earlier version installed and this one no longer ships."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / '.claude.json').write_text('{}\n', encoding='utf-8')
        self.record = self.home / '.agent-harness' / 'installed.json'

    def install(self):
        return harness('install', '--home', str(self.home), '--agents', 'claude')

    def test_install_clears_a_file_this_version_no_longer_ships(self):
        self.install()
        dropped = self.home / '.claude' / 'skills' / 'old-skill' / 'SKILL.md'  # an earlier version shipped it
        mine = self.home / '.claude' / 'skills' / 'my-skill' / 'SKILL.md'  # third-party: never recorded
        for path in (dropped, mine):
            path.parent.mkdir(parents=True)
            path.write_text('x\n', encoding='utf-8')
        self.record.write_text(json.dumps([*json.loads(self.record.read_text(encoding='utf-8')),
                                           '.claude/skills/old-skill/SKILL.md']), encoding='utf-8')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'stale: {dropped}', result.stdout)
        self.install()
        self.assertFalse(dropped.parent.exists())
        self.assertTrue(mine.is_file())
        moved = list((self.home / '.agent-harness' / 'backups').glob('*/.claude/skills/old-skill/SKILL.md'))
        self.assertEqual(len(moved), 1)
        self.assertNotIn('.claude/skills/old-skill/SKILL.md', json.loads(self.record.read_text(encoding='utf-8')))
        self.assertEqual(run('check', '--home', str(self.home)).returncode, 0)

    def test_the_record_lists_whole_files_and_no_merged_config(self):
        self.install()
        record = json.loads(self.record.read_text(encoding='utf-8'))
        self.assertIn('.claude/CLAUDE.md', record)
        self.assertIn('.claude/hooks/harness_guards.py', record)
        self.assertNotIn('.claude/settings.json', record)

    def test_install_clears_what_the_harness_left_for_agents_it_dropped(self):
        left = [self.home / '.config' / 'opencode' / 'AGENTS.md',
                self.home / '.pi' / 'agent' / 'extensions' / 'agent-harness.ts']
        own = self.home / '.config' / 'opencode' / 'opencode.json'
        for path in (*left, own):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('x\n', encoding='utf-8')
        self.install()  # a saved choice does not protect what belonged to a dropped agent
        self.assertEqual([path.exists() for path in (*left, own)], [False, False, True])
        self.assertEqual(len(list((self.home / '.agent-harness' / 'backups').glob('*/.config/opencode/AGENTS.md'))), 1)


class Uninstall(unittest.TestCase):
    """`uninstall` takes the harness off the agents you name and leaves the rest working."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / '.claude.json').write_text('{}\n', encoding='utf-8')
        (self.home / '.codex').mkdir()
        self.settings = self.home / '.claude' / 'settings.json'
        self.settings.parent.mkdir()
        self.own_hook = {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'my-own-hook'}]}
        self.settings.write_text(json.dumps({'hooks': {'PreToolUse': [self.own_hook]}}), encoding='utf-8')
        harness('install', '--home', str(self.home), '--agents', 'claude,codex')

    def uninstall(self, *args):
        return harness('uninstall', '--home', str(self.home), *args)

    def exists(self, *paths):
        return [(self.home / path).exists() for path in paths]

    def test_takes_one_agent_off_and_keeps_what_the_other_uses(self):
        gone = ('.claude/CLAUDE.md', '.claude/skills/pair/SKILL.md', '.claude/agents/test-runner.md')
        self.assertIn('CLAUDE.md', self.uninstall('--agents', 'claude', '--dry-run'))
        self.assertEqual(self.exists(*gone), [True] * 3)
        self.uninstall('--agents', 'claude')
        self.assertEqual(self.exists(*gone, '.claude/skills'), [False] * 4)
        self.assertEqual(self.exists('.claude/hooks/harness_guards.py', '.codex/AGENTS.md',
                                     '.agents/skills/pair/SKILL.md'), [True] * 3)
        settings = json.loads(self.settings.read_text(encoding='utf-8'))
        self.assertEqual(settings['hooks'], {'PreToolUse': [self.own_hook]})
        rules = tomllib.loads((REPO / 'core' / 'permissions.toml').read_text(encoding='utf-8'))['claude']['deny']
        self.assertEqual(settings['permissions']['deny'], rules)
        self.assertEqual((self.home / '.agent-harness' / 'agents').read_text(encoding='utf-8').split(), ['codex'])
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'), result.stdout)

    def test_uninstalling_copilot_leaves_its_mcp_servers(self):
        (self.home / '.copilot').mkdir()
        harness('install', '--home', str(self.home), '--agents', 'claude,codex,copilot')
        config = self.home / '.copilot' / 'mcp-config.json'
        servers = json.loads(config.read_text(encoding='utf-8'))['mcpServers']
        self.assertIn('context7', servers)
        self.uninstall('--agents', 'copilot')
        self.assertEqual(json.loads(config.read_text(encoding='utf-8'))['mcpServers'], servers)

    def test_taking_the_last_agent_off_clears_shared_files_and_restore_brings_them_back(self):
        third_party = self.home / '.agents' / 'skills' / 'my-skill' / 'SKILL.md'
        third_party.parent.mkdir(parents=True)
        third_party.write_text('mine\n', encoding='utf-8')
        self.uninstall('--agents', 'claude,codex')
        shared = ('.claude/hooks/harness_guards.py', '.agents/skills/pair/SKILL.md', '.codex/AGENTS.md')
        self.assertEqual(self.exists(*shared), [False] * 3)
        self.assertTrue(third_party.is_file())
        self.assertNotIn('harness_guards', (self.home / '.codex' / 'hooks.json').read_text(encoding='utf-8'))
        self.assertFalse((self.home / '.agent-harness' / 'agents').exists())
        stamp = max(p.parent.name for p in (self.home / '.agent-harness' / 'backups').glob('*/manifest.json'))
        harness('restore', stamp, '--home', str(self.home))
        self.assertEqual(self.exists(*shared), [True] * 3)
        self.assertIn('harness_guards', (self.home / '.codex' / 'hooks.json').read_text(encoding='utf-8'))

    def test_takes_out_the_rules_and_environment_the_harness_set(self):
        (self.home / '.agent-harness' / 'config.toml').write_text('engram_cloud_server = "https://engram.test"\n', encoding='utf-8')
        config = self.home / '.codex' / 'config.toml'
        config.write_text('[mcp_servers.engram]\ncommand = "engram"\n', encoding='utf-8')
        rules = self.home / '.codex' / 'rules' / 'default.rules'
        own_rule = 'prefix_rule(pattern=["rm"], decision="prompt")\n'
        rules.write_text(own_rule + rules.read_text(encoding='utf-8'), encoding='utf-8')
        settings = json.loads(self.settings.read_text(encoding='utf-8'))
        settings['env']['MY_VAR'] = 'mine'
        self.settings.write_text(json.dumps(settings), encoding='utf-8')
        harness('install', '--home', str(self.home))
        self.assertIn('ENGRAM_CLOUD_SERVER', self.settings.read_text(encoding='utf-8') + config.read_text(encoding='utf-8'))
        self.uninstall('--agents', 'claude,codex')
        self.assertEqual(json.loads(self.settings.read_text(encoding='utf-8'))['env'], {'MY_VAR': 'mine'})
        self.assertEqual(rules.read_text(encoding='utf-8'), own_rule)
        engram = tomllib.loads(config.read_text(encoding='utf-8'))['mcp_servers']['engram']
        self.assertEqual((engram['command'], engram['env_vars'], engram.get('env', {})), ('engram', ['ENGRAM_CLOUD_TOKEN'], {}))

    @unittest.skipIf(os.name == 'nt', 'symlinks need a privilege on Windows')
    def test_a_symlinked_skills_folder_survives_and_the_hooks_still_go(self):
        home = Path(tempfile.mkdtemp())
        (home / '.claude.json').write_text('{}\n', encoding='utf-8')
        (home / 'dotfiles' / 'skills').mkdir(parents=True)
        (home / '.claude').mkdir()
        (home / '.claude' / 'skills').symlink_to(home / 'dotfiles' / 'skills')
        harness('install', '--home', str(home), '--agents', 'claude')
        harness('uninstall', '--home', str(home), '--agents', 'claude')
        self.assertTrue((home / '.claude' / 'skills').is_symlink())
        self.assertNotIn('harness_guards', (home / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        self.assertFalse((home / '.claude' / 'hooks').exists())

    def test_leaves_the_files_of_an_agent_the_harness_never_installed(self):
        home = Path(tempfile.mkdtemp())
        (home / '.claude.json').write_text('{}\n', encoding='utf-8')
        own = [home / '.codex' / 'AGENTS.md', home / '.agents' / 'skills' / 'backlog' / 'SKILL.md']
        for path in own:
            path.parent.mkdir(parents=True)
            path.write_text('mine\n', encoding='utf-8')
        harness('install', '--home', str(home), '--agents', 'claude')
        harness('uninstall', '--home', str(home), '--agents', 'codex')
        self.assertEqual([path.read_text(encoding='utf-8') for path in own], ['mine\n', 'mine\n'])

    def test_restore_brings_back_the_choice_and_the_record(self):
        kept = [self.home / '.agent-harness' / 'agents', self.home / '.agent-harness' / 'installed.json']
        before = [path.read_text(encoding='utf-8') for path in kept]
        self.uninstall('--agents', 'claude')
        stamp = max(p.parent.name for p in (self.home / '.agent-harness' / 'backups').glob('*/manifest.json'))
        harness('restore', stamp, '--home', str(self.home))
        self.assertEqual([path.read_text(encoding='utf-8') for path in kept], before)


class Clean(unittest.TestCase):
    """`clean` deletes old harness backups for good, and only when told to."""

    def test_lists_first_and_deletes_only_with_yes_keeping_the_newest(self):
        home = Path(tempfile.mkdtemp())
        installs, copies = home / '.agent-harness' / 'backups', home / '.claude' / 'backups'
        names = {installs: [f'2026010{day}-000000-000000' for day in range(1, 8)],
                 copies: [f'claude__CLAUDE.md.abcd1234.2026010{day}-000000' for day in range(1, 8)]}
        for folder, entries in names.items():
            folder.mkdir(parents=True)
            for age, name in enumerate(entries):
                if folder == installs:
                    (folder / name).mkdir()
                    (folder / name / 'manifest.json').write_text('{}', encoding='utf-8')
                else:
                    (folder / name).write_text('x', encoding='utf-8')
                os.utime(folder / name, (1_700_000_000 + age, 1_700_000_000 + age))
        foreign = copies / '.claude.json.backup.1795271369063'  # Claude Code's own backup, and the oldest file there
        foreign.write_text('{}', encoding='utf-8')
        os.utime(foreign, (1, 1))
        left = lambda folder: sorted(entry.name for entry in folder.iterdir())

        listed = harness('clean', '--home', str(home))
        self.assertIn(str(installs / names[installs][0]), listed)
        self.assertNotIn(str(installs / names[installs][2]), listed)
        self.assertEqual(len(left(installs)), 7)
        harness('clean', '--home', str(home), '--yes')
        self.assertEqual(left(installs), names[installs][2:])
        self.assertEqual(left(copies), [foreign.name, *names[copies][2:]])
        harness('clean', '--home', str(home), '--yes', '--keep', '1')
        self.assertEqual(left(installs), names[installs][-1:])


if __name__ == '__main__':
    unittest.main()
