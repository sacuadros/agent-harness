import importlib.util
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
    'backlog', 'story', 'pair', 'brand-graphic-design', 'dependency-safety',
    'performance-marketing-senior', 'promote-project-convention', 'secure-development',
    'seo-copy-senior', 'software-architecture', 'unslop', 'work-unit-commits', 'chained-pr',
    'cognitive-doc-design', 'systematic-debugging',
}


def tree(root):
    """Relative path -> bytes for every file under root, skipping old .bak leftovers."""
    return {str(f.relative_to(root)): f.read_bytes() for f in root.rglob('*')
            if f.is_file() and '.bak' not in f.name}


def harness(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args],
                          capture_output=True, encoding='utf-8', check=True).stdout


def run(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args], capture_output=True, encoding='utf-8')


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
        out = harness('install', '--home', str(self.home))
        self.assertIn('no changes', out)
        self.assertFalse((self.home / '.agent-harness' / 'backups').exists())

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
        self.assert_matches_installed('.codex')

    def test_agent_specific_files_go_only_to_their_agent(self):
        claude = self.home / '.claude' / 'skills' / 'secure-development'
        codex = self.home / '.codex' / 'skills' / 'secure-development'
        self.assertFalse((claude / 'agents' / 'openai.yaml').exists())
        self.assertTrue((codex / 'agents' / 'openai.yaml').is_file())
        self.assertIn('/security-review', (claude / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('codex-security', (codex / 'SKILL.md').read_text(encoding='utf-8'))
        leftovers = [f for f in self.home.rglob('*') if '.claude.' in f.name or '.codex.' in f.name]
        self.assertEqual(leftovers, [])

    def test_hand_edited_skill_fails_check(self):
        edited = self.home / '.codex' / 'skills' / 'pair' / 'SKILL.md'
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


class Hooks(unittest.TestCase):
    SCRIPTS = ('harness_guards.py', 'enforce_memory_graph.py', 'engram_auto_enroll.py')

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def install(self):
        harness('install', '--home', str(self.home))

    def test_scripts_are_installed(self):
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

    def commands(self, entries):
        return [' '.join([h['command'], *h.get('args', [])]) for entry in entries for h in entry['hooks']]

    def test_claude_hooks_run_without_a_shell(self):
        # Exec form: Claude spawns the interpreter itself, so zsh, Git Bash and PowerShell behave alike.
        (self.home / '.agent-harness').mkdir()
        (self.home / '.agent-harness' / 'config.toml').write_text('python = "/usr/bin/python3"\n', encoding='utf-8', newline='\n')
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
        (self.home / '.agent-harness').mkdir()
        (self.home / '.agent-harness' / 'config.toml').write_text('python = "/usr/bin/python3"\n', encoding='utf-8', newline='\n')
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
        self.assertEqual(data['env'], {'X': '1'})
        self.assertEqual(data['hooks']['UserPromptSubmit'], [foreign])
        hooks = (self.home / '.claude' / 'hooks').as_posix()
        self.assertEqual(self.commands(data['hooks']['Stop']), [
            f'/usr/bin/python3 {hooks}/enforce_memory_graph.py stop',
            f'/usr/bin/python3 {hooks}/engram_auto_enroll.py'])
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
        self.assertEqual(len(stop), 3)
        self.assertEqual(stop[1], foreign)
        self.assertTrue(self.commands([stop[0]])[0].endswith('/.codex/hooks/engram_auto_enroll.py'))
        self.assertTrue(self.commands([stop[2]])[0].endswith('/.claude/hooks/enforce_memory_graph.py stop'))
        self.assertEqual(len(hooks['PreToolUse']), 3)

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


class OpenCode(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_render_has_every_section_and_its_own_orchestration(self):
        text = harness('render', 'opencode')
        self.assertEqual(len(re.findall(r'<!-- opencode-native:[a-z-]+ -->', text)), 10)
        self.assertIn('## Native OpenCode Orchestration', text)
        for name in ('implementation-worker', 'independent-reviewer', 'test-runner'):
            self.assertIn(f'`{name}`', text)
        self.assertNotIn('Claude Code', text)

    def test_subagents_and_config_merge(self):
        config = self.home / '.config' / 'opencode' / 'opencode.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'model': 'x/y', 'agent': {'orchestrator': {
            'permission': {'task': {'*': 'deny', 'explore': 'allow'}}}}}), encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        agents = self.home / '.config' / 'opencode' / 'agents'
        reviewer = (agents / 'independent-reviewer.md').read_text(encoding='utf-8')
        self.assertTrue(reviewer.startswith('---\ndescription: '))
        self.assertIn('mode: subagent\n', reviewer)
        self.assertIn('  edit: deny\n', reviewer)
        self.assertIn('the primary agent', (agents / 'test-runner.md').read_text(encoding='utf-8'))
        self.assertNotIn('  edit: deny\n', (agents / 'implementation-worker.md').read_text(encoding='utf-8'))
        data = json.loads(config.read_text(encoding='utf-8'))
        self.assertEqual(data['model'], 'x/y')
        task = data['agent']['orchestrator']['permission']['task']
        self.assertEqual(task['explore'], 'allow')
        self.assertEqual(task['implementation-worker'], 'allow')
        self.assertEqual(data['permission']['bash']['git push*'], 'ask')
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_guard_plugin_is_filled_in_and_checked(self):
        (self.home / '.config' / 'opencode').mkdir(parents=True)
        harness('install', '--home', str(self.home))
        plugin = self.home / '.config' / 'opencode' / 'plugins' / 'agent-harness.ts'
        text = plugin.read_text(encoding='utf-8')
        self.assertIn(f'"{self.home.as_posix()}/.claude/hooks"', text)
        self.assertNotIn('{python}', text)
        plugin.write_text(text + '// hand edit\n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'drift: {plugin}', result.stdout)

    def test_stale_skill_copies_are_retired_to_a_backup(self):
        stale = self.home / '.agents' / 'skills' / 'chained-pr' / 'SKILL.md'
        stale.parent.mkdir(parents=True)
        stale.write_text('old\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertFalse(stale.parent.exists())
        moved = list((self.home / '.agent-harness' / 'backups').glob('*/.agents/skills/chained-pr/SKILL.md'))
        self.assertEqual([m.read_text(encoding='utf-8') for m in moved], ['old\n'])
        stale.parent.mkdir(parents=True)
        stale.write_text('back again\n', encoding='utf-8', newline='\n')
        result = run('check', '--home', str(self.home))
        self.assertIn(f'stale: {stale.parent}', result.stdout)

    def test_nothing_for_opencode_when_it_is_not_installed(self):
        harness('install', '--home', str(self.home))
        self.assertFalse((self.home / '.config' / 'opencode').exists())


class Pi(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_render_uses_pi_skill_syntax_and_its_own_orchestration(self):
        text = harness('render', 'pi')
        self.assertEqual(len(re.findall(r'<!-- pi-native:[a-z-]+ -->', text)), 10)
        self.assertIn('## Native Pi Orchestration', text)
        self.assertIn('`/skill:promote-project-convention`', text)
        self.assertNotIn('Claude Code', text)

    def test_settings_subagents_and_append_system(self):
        agent_dir = self.home / '.pi' / 'agent'
        agent_dir.mkdir(parents=True)
        (agent_dir / 'settings.json').write_text(json.dumps({'defaultModel': 'm', 'packages': ['npm:x']}), encoding='utf-8', newline='\n')
        (agent_dir / 'APPEND_SYSTEM.md').write_text('old codegraph block\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        settings = json.loads((agent_dir / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['defaultModel'], 'm')
        self.assertEqual(settings['packages'], ['npm:x'])
        self.assertEqual(settings['skills'], ['~/.claude/skills'])
        reviewer = (agent_dir / 'agents' / 'independent-reviewer.md').read_text(encoding='utf-8')
        self.assertTrue(reviewer.startswith('---\nname: independent-reviewer\n'))
        self.assertIn('tools: read, grep, find, ls, bash\n', reviewer)
        self.assertIn('edit, write', (agent_dir / 'agents' / 'implementation-worker.md').read_text(encoding='utf-8'))
        self.assertFalse((agent_dir / 'APPEND_SYSTEM.md').exists())
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_guard_extension_is_filled_in_and_checked(self):
        (self.home / '.pi' / 'agent').mkdir(parents=True)
        harness('install', '--home', str(self.home))
        extension = self.home / '.pi' / 'agent' / 'extensions' / 'agent-harness.ts'
        text = extension.read_text(encoding='utf-8')
        self.assertIn(f'"{self.home.as_posix()}/.claude/hooks"', text)
        self.assertIn('ctx.ui.confirm', text)
        extension.write_text(text + '// hand edit\n', encoding='utf-8', newline='\n')
        self.assertIn(f'drift: {extension}', run('check', '--home', str(self.home)).stdout)

    def test_nothing_for_pi_when_it_is_not_installed(self):
        harness('install', '--home', str(self.home))
        self.assertFalse((self.home / '.pi').exists())


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
        harness('install', '--home', str(self.home))
        self.assertEqual((self.home / '.copilot' / 'copilot-instructions.md').read_text(encoding='utf-8'),
                         harness('render', 'copilot'))
        local = (prompts / 'agent-harness.instructions.md').read_text(encoding='utf-8')
        self.assertTrue(local.startswith("---\napplyTo: '**'\n"))
        self.assertFalse((prompts / 'gentle-ai.instructions.md').exists())
        self.assertTrue((prompts / 'sonar-fix.prompt.md').exists())
        agent = (self.home / '.copilot' / 'agents' / 'test-runner.agent.md').read_text(encoding='utf-8')
        self.assertTrue(agent.startswith('---\nname: test-runner\ndescription: '))
        hooks = json.loads((self.home / '.copilot' / 'hooks' / 'agent-harness.json').read_text(encoding='utf-8'))
        commands = [h['bash'] for h in hooks['hooks']['PreToolUse']]
        self.assertIn(f'{self.home.as_posix()}/.claude/hooks/harness_guards.py bash --copilot', ' '.join(commands))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_nothing_for_copilot_when_it_is_not_installed(self):
        harness('install', '--home', str(self.home))
        self.assertFalse((self.home / '.copilot').exists())


class NewPC(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_clean_install_with_every_agent_passes_check(self):
        for folder in ('.config/opencode', '.pi/agent', '.copilot', 'Library/Application Support/Code/User/prompts'):
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

    def test_linux_vscode_profile_gets_the_prompt_file(self):
        (self.home / '.copilot').mkdir()
        prompts = self.home / '.config' / 'Code' / 'User' / 'prompts'
        prompts.mkdir(parents=True)
        harness('install', '--home', str(self.home))
        self.assertTrue((prompts / 'agent-harness.instructions.md').is_file())

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
        for folder in ('.config/opencode', '.pi/agent', '.copilot'):
            (home / folder).mkdir(parents=True)
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


class Doctor(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {**os.environ, 'PATH': os.pathsep.join(['/usr/bin', '/bin'])}

    def doctor(self, **env):
        result = subprocess.run([sys.executable, str(HARNESS), 'doctor', '--home', str(self.home)],
                                capture_output=True, encoding='utf-8', env={**self.env, **env})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

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

    def test_clean_setup_has_no_findings(self):
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
        self.assertEqual(permissions['allow'], ['Bash(npm run build)'])
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

    def test_engram_token_leaves_codex_config(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('[mcp_servers.engram.env]\nENGRAM_CLOUD_AUTOSYNC = "1"\n'
                          'ENGRAM_CLOUD_TOKEN = "s3cr3t"\n\n[agents]\nenabled = true\n', encoding='utf-8', newline='\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(encoding='utf-8'),
                         '[mcp_servers.engram.env]\nENGRAM_CLOUD_AUTOSYNC = "1"\n\n[agents]\nenabled = true\n')


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
        for agent_dir in ('.claude', '.codex'):
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


if __name__ == '__main__':
    unittest.main()
