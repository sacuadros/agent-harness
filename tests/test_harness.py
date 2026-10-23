import json
import re
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

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
        self.assertIn('/security-review', (claude / 'SKILL.md').read_text())
        self.assertIn('codex-security', (codex / 'SKILL.md').read_text())
        leftovers = [f for f in self.home.rglob('*') if '.claude.' in f.name or '.codex.' in f.name]
        self.assertEqual(leftovers, [])

    def test_hand_edited_skill_fails_check(self):
        edited = self.home / '.codex' / 'skills' / 'pair' / 'SKILL.md'
        edited.write_text('hand edit\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(edited), result.stdout)

    def test_unmanaged_skill_survives_install(self):
        mine = self.home / '.claude' / 'skills' / 'hyperframes' / 'SKILL.md'
        mine.parent.mkdir(parents=True)
        mine.write_text('third party\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(mine.read_text(), 'third party\n')


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
                expected = installed.read_text()
                for old, new in self.FIXES.items():
                    expected = expected.replace(old, new)
                self.assertEqual((self.home / rel).read_text(), expected, rel)


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
        path.write_text(json.dumps(data))
        return path

    def commands(self, entries):
        return [h['command'] for entry in entries for h in entry['hooks']]

    def test_settings_merge_keeps_foreign_parts(self):
        (self.home / '.agent-harness').mkdir()
        (self.home / '.agent-harness' / 'config.toml').write_text('python = "/usr/bin/python3"\n')
        foreign = {'hooks': [{'type': 'command', 'command': 'codegraph prompt-hook'}]}
        settings = self.write_json('.claude/settings.json', {
            'env': {'X': '1'},
            'hooks': {
                'UserPromptSubmit': [foreign],
                'Stop': [{'hooks': [{'type': 'command', 'timeout': 5,
                                     'command': 'python3 /old/.claude/hooks/enforce_memory_graph.py stop'}]}],
            }})
        self.install()
        data = json.loads(settings.read_text())
        self.assertEqual(data['env'], {'X': '1'})
        self.assertEqual(data['hooks']['UserPromptSubmit'], [foreign])
        hooks = str(self.home / '.claude' / 'hooks')
        self.assertEqual(self.commands(data['hooks']['Stop']), [
            f'/usr/bin/python3 {hooks}/enforce_memory_graph.py stop',
            f'/usr/bin/python3 {hooks}/engram_auto_enroll.py'])
        self.assertIn(f'/usr/bin/python3 {hooks}/harness_guards.py bash',
                      self.commands(data['hooks']['PreToolUse']))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_codex_hooks_keep_foreign_entries_at_their_index(self):
        foreign = {'hooks': [{'type': 'command', 'command': 'impeccable hook', 'timeout': 30}]}
        old = lambda cmd: {'hooks': [{'type': 'command', 'command': cmd}]}
        hooks_json = self.write_json('.codex/hooks.json', {'hooks': {
            'PostToolUse': [foreign],
            'Stop': [old('python3 /x/.codex/hooks/engram_auto_enroll.py'), foreign,
                     old('python3 /x/.claude/hooks/enforce_memory_graph.py stop')],
        }})
        self.install()
        hooks = json.loads(hooks_json.read_text())['hooks']
        self.assertEqual(hooks['PostToolUse'], [foreign])
        stop = hooks['Stop']
        self.assertEqual(len(stop), 3)
        self.assertEqual(stop[1], foreign)
        self.assertTrue(self.commands([stop[0]])[0].endswith('/.codex/hooks/engram_auto_enroll.py'))
        self.assertTrue(self.commands([stop[2]])[0].endswith('/.claude/hooks/enforce_memory_graph.py stop'))
        self.assertEqual(len(hooks['PreToolUse']), 3)

    def test_rules_block_keeps_codex_added_rules(self):
        block = (REPO / 'core' / 'hooks' / 'codex.rules').read_text()
        rules = self.home / '.codex' / 'rules' / 'default.rules'
        rules.parent.mkdir(parents=True)
        mine = 'prefix_rule(pattern=["npm", "run", "build"], decision="allow")\n'
        old_copy = next(line for line in block.splitlines() if line.startswith('prefix_rule'))
        rules.write_text(mine + old_copy + '\n')
        self.install()
        text = rules.read_text()
        self.assertTrue(text.startswith(mine))
        self.assertEqual(text.count(old_copy), 1)
        self.assertEqual(text.count('# >>> agent-harness'), 1)
        added = 'prefix_rule(pattern=["make"], decision="allow")\n'
        rules.write_text(text + added)
        self.assertIn('no changes', harness('install', '--home', str(self.home)))
        self.assertTrue(rules.read_text().endswith(added))

    def test_repo_hook_selftests_pass(self):
        for script in ('harness_guards.py', 'enforce_memory_graph.py'):
            result = subprocess.run([sys.executable, str(REPO / 'core' / 'hooks' / script), 'selftest'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f'{script}: {result.stdout}{result.stderr}')

    def test_failing_selftest_fails_check(self):
        self.install()
        broken = self.home / '.claude' / 'hooks' / 'harness_guards.py'
        broken.write_text('import sys\nsys.exit(1)\n')
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
            'permission': {'task': {'*': 'deny', 'explore': 'allow'}}}}}))
        harness('install', '--home', str(self.home))
        agents = self.home / '.config' / 'opencode' / 'agents'
        reviewer = (agents / 'independent-reviewer.md').read_text()
        self.assertTrue(reviewer.startswith('---\ndescription: '))
        self.assertIn('mode: subagent\n', reviewer)
        self.assertIn('  edit: deny\n', reviewer)
        self.assertIn('the primary agent', (agents / 'test-runner.md').read_text())
        self.assertNotIn('  edit: deny\n', (agents / 'implementation-worker.md').read_text())
        data = json.loads(config.read_text())
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
        text = plugin.read_text()
        self.assertIn(f'"{self.home}/.claude/hooks"', text)
        self.assertNotIn('{python}', text)
        plugin.write_text(text + '// hand edit\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'drift: {plugin}', result.stdout)

    def test_stale_skill_copies_are_retired_to_a_backup(self):
        stale = self.home / '.agents' / 'skills' / 'chained-pr' / 'SKILL.md'
        stale.parent.mkdir(parents=True)
        stale.write_text('old\n')
        harness('install', '--home', str(self.home))
        self.assertFalse(stale.parent.exists())
        moved = list((self.home / '.agent-harness' / 'backups').glob('*/.agents/skills/chained-pr/SKILL.md'))
        self.assertEqual([m.read_text() for m in moved], ['old\n'])
        stale.parent.mkdir(parents=True)
        stale.write_text('back again\n')
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
        (agent_dir / 'settings.json').write_text(json.dumps({'defaultModel': 'm', 'packages': ['npm:x']}))
        (agent_dir / 'APPEND_SYSTEM.md').write_text('old codegraph block\n')
        harness('install', '--home', str(self.home))
        settings = json.loads((agent_dir / 'settings.json').read_text())
        self.assertEqual(settings['defaultModel'], 'm')
        self.assertEqual(settings['packages'], ['npm:x'])
        self.assertEqual(settings['skills'], ['~/.claude/skills'])
        reviewer = (agent_dir / 'agents' / 'independent-reviewer.md').read_text()
        self.assertTrue(reviewer.startswith('---\nname: independent-reviewer\n'))
        self.assertIn('tools: read, grep, find, ls, bash\n', reviewer)
        self.assertIn('edit, write', (agent_dir / 'agents' / 'implementation-worker.md').read_text())
        self.assertFalse((agent_dir / 'APPEND_SYSTEM.md').exists())
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_guard_extension_is_filled_in_and_checked(self):
        (self.home / '.pi' / 'agent').mkdir(parents=True)
        harness('install', '--home', str(self.home))
        extension = self.home / '.pi' / 'agent' / 'extensions' / 'agent-harness.ts'
        text = extension.read_text()
        self.assertIn(f'"{self.home}/.claude/hooks"', text)
        self.assertIn('ctx.ui.confirm', text)
        extension.write_text(text + '// hand edit\n')
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
        (prompts / 'gentle-ai.instructions.md').write_text('old\n')
        (prompts / 'sonar-fix.prompt.md').write_text('mine\n')
        harness('install', '--home', str(self.home))
        self.assertEqual((self.home / '.copilot' / 'copilot-instructions.md').read_text(),
                         harness('render', 'copilot'))
        local = (prompts / 'agent-harness.instructions.md').read_text()
        self.assertTrue(local.startswith("---\napplyTo: '**'\n"))
        self.assertFalse((prompts / 'gentle-ai.instructions.md').exists())
        self.assertTrue((prompts / 'sonar-fix.prompt.md').exists())
        agent = (self.home / '.copilot' / 'agents' / 'test-runner.agent.md').read_text()
        self.assertTrue(agent.startswith('---\nname: test-runner\ndescription: '))
        hooks = json.loads((self.home / '.copilot' / 'hooks' / 'agent-harness.json').read_text())
        commands = [h['bash'] for h in hooks['hooks']['PreToolUse']]
        self.assertIn(f'{self.home}/.claude/hooks/harness_guards.py bash --copilot', ' '.join(commands))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_nothing_for_copilot_when_it_is_not_installed(self):
        harness('install', '--home', str(self.home))
        self.assertFalse((self.home / '.copilot').exists())


class Doctor(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {**os.environ, 'PATH': '/usr/bin:/bin'}

    def doctor(self, **env):
        result = subprocess.run([sys.executable, str(HARNESS), 'doctor', '--home', str(self.home)],
                                capture_output=True, text=True, env={**self.env, **env})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_orphan_skill_overrides(self):
        (self.home / '.claude' / 'skills' / 'present').mkdir(parents=True)
        command = self.home / '.claude/plugins/cache/market/tool/1.0/commands/tool-review.md'
        command.parent.mkdir(parents=True)
        command.write_text('# review\n')
        (self.home / '.claude' / 'settings.json').write_text(json.dumps({'skillOverrides': {
            'present': 'off', 'ghost': 'off', 'init': 'user-invocable-only', 'tool:tool-review': 'off'}}))
        out = self.doctor()
        self.assertIn('orphan skill override: ghost', out)
        self.assertNotIn('present', out)
        self.assertNotIn('tool-review', out)
        self.assertNotIn(': init', out)

    def test_duplicate_path_entries(self):
        out = self.doctor(PATH='/a:/usr/bin:/a:/bin')
        self.assertEqual(out.count('duplicate PATH entry: /a'), 1)

    def test_engram_plugin_versions_differ(self):
        plugins = self.home / '.claude' / 'plugins'
        plugins.mkdir(parents=True)
        (plugins / 'installed_plugins.json').write_text(json.dumps(
            {'plugins': {'engram@engram': [{'version': '0.1.0'}]}}))
        (self.home / '.codex' / 'plugins' / 'cache' / 'engram' / 'engram' / '0.1.5').mkdir(parents=True)
        out = self.doctor()
        self.assertIn('engram plugins differ: claude 0.1.0, codex 0.1.5', out)

    def test_vscode_setting_pointing_to_a_missing_file(self):
        settings = self.home / 'Library/Application Support/Code/User/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{\n  // comment\n  "github.copilot.chat.instructions": [\n'
                            '    "Lee y sigue las reglas definidas en ~/.config/copilot/instructions.md",\n  ],\n}\n')
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
            'allow': ['Bash(npm run build)'], 'deny': ['Read(./secret.txt)']}}))
        harness('install', '--home', str(self.home))
        permissions = json.loads(settings.read_text())['permissions']
        self.assertEqual(permissions['allow'], ['Bash(npm run build)'])
        self.assertEqual(permissions['deny'][0], 'Read(./secret.txt)')
        self.assertIn('Read(~/.aws/**)', permissions['deny'])
        self.assertIn('Read(**/.env)', permissions['ask'])
        self.assertEqual(len(permissions['deny']), len(set(permissions['deny'])))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_check_flags_literal_secrets_without_printing_them(self):
        harness('install', '--home', str(self.home))
        settings = self.home / '.claude' / 'settings.json'
        data = json.loads(settings.read_text())
        data['env'] = {'OPENAI_API_KEY': 'sk-very-secret', 'PATH': '/bin'}
        settings.write_text(json.dumps(data, indent=2) + '\n')
        result = run('check', '--home', str(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'secret: {settings}: env.OPENAI_API_KEY', result.stdout)
        self.assertNotIn('sk-very-secret', result.stdout)

    def test_check_ignores_token_counts_and_env_var_names(self):
        harness('install', '--home', str(self.home))
        settings = self.home / '.claude' / 'settings.json'
        data = json.loads(settings.read_text())
        data['env'] = {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '32000'}
        settings.write_text(json.dumps(data, indent=2) + '\n')
        config = self.home / '.codex' / 'config.toml'
        config.write_text('[mcp_servers.x]\nurl = "https://x"\nbearer_token_env_var = "X_TOKEN"\n')
        harness('install', '--home', str(self.home))
        result = run('check', '--home', str(self.home))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'))

    def test_codex_engram_mcp_receives_the_token_from_the_environment(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('[mcp_servers.engram]\ncommand = "engram"\n\n[mcp_servers.engram.env]\n'
                          'ENGRAM_CLOUD_AUTOSYNC = "1"\n')
        harness('install', '--home', str(self.home))
        data = tomllib.loads(config.read_text())
        self.assertEqual(data['mcp_servers']['engram']['env_vars'], ['ENGRAM_CLOUD_TOKEN'])
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_engram_token_leaves_codex_config(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('[mcp_servers.engram.env]\nENGRAM_CLOUD_AUTOSYNC = "1"\n'
                          'ENGRAM_CLOUD_TOKEN = "s3cr3t"\n\n[agents]\nenabled = true\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(),
                         '[mcp_servers.engram.env]\nENGRAM_CLOUD_AUTOSYNC = "1"\n\n[agents]\nenabled = true\n')


class Plugins(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_superpowers_disabled_other_plugins_untouched(self):
        settings = self.home / '.claude' / 'settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'enabledPlugins': {
            'superpowers@claude-plugins-official': True, 'engram@engram': True}}))
        harness('install', '--home', str(self.home))
        self.assertEqual(json.loads(settings.read_text())['enabledPlugins'], {
            'superpowers@claude-plugins-official': False, 'engram@engram': True})

    def test_systematic_debugging_is_a_harness_skill(self):
        harness('install', '--home', str(self.home))
        for agent_dir in ('.claude', '.codex'):
            self.assertTrue((self.home / agent_dir / 'skills' / 'systematic-debugging' / 'SKILL.md').is_file())
        self.assertIn('core/skills/systematic-debugging', (REPO / 'NOTICE').read_text())

    def test_check_flags_reenabled_superpowers(self):
        harness('install', '--home', str(self.home))
        settings = self.home / '.claude' / 'settings.json'
        data = json.loads(settings.read_text())
        data['enabledPlugins']['superpowers@claude-plugins-official'] = True
        settings.write_text(json.dumps(data, indent=2) + '\n')
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
        config.write_text(before)
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(), before.replace('curated"]\nenabled = true', 'curated"]\nenabled = false'))
        self.assertIn('no changes', harness('install', '--home', str(self.home)))

    def test_codex_config_without_the_plugin_is_left_alone(self):
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('model = "x"\n')
        harness('install', '--home', str(self.home))
        self.assertEqual(config.read_text(), 'model = "x"\n')


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
