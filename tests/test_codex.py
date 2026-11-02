"""Codex-only installation and runtime readiness regressions."""
import json
import os
import runpy
import shutil
import sys
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from tests.test_harness import HARNESS, harness, load_hook, run


class CodexOnly(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_scoped_install_preserves_other_agents_and_checks_itself(self):
        foreign = {
            '.claude/settings.json': b'unrelated invalid config',
            '.claude/CLAUDE.md': b'private Claude instructions',
            '.pi/agent/APPEND_SYSTEM.md': b'keep this retired Pi file',
            '.agents/skills/my-skill/SKILL.md': b'my own skill',
        }
        for rel, content in foreign.items():
            path = self.home / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        harness('install', '--agent', 'codex', '--home', str(self.home))
        for rel, content in foreign.items():
            self.assertEqual((self.home / rel).read_bytes(), content, rel)
        self.assertFalse((self.home / '.claude/hooks').exists())
        self.assertTrue((self.home / '.agents/skills/pair/SKILL.md').is_file())
        self.assertTrue((self.home / '.codex/agents/implementation-worker.toml').is_file())
        hooks = json.loads((self.home / '.codex/hooks.json').read_text(encoding='utf-8'))
        commands = [hook['command'] for entries in hooks['hooks'].values()
                    for entry in entries for hook in entry['hooks']]
        self.assertTrue(all('/.claude/' not in command for command in commands))
        self.assertTrue((self.home / '.codex/hooks/harness_guards.py').is_file())
        checked = run('check', '--agent', 'codex', '--home', str(self.home))
        self.assertEqual((checked.returncode, checked.stdout.strip()), (0, 'ok'), checked.stderr)
        self.assertIn('no changes', harness('install', '--agent', 'codex', '--home', str(self.home)))

    def test_scoped_dry_run_and_retirement_keep_foreign_files(self):
        stale = self.home / '.codex/skills/pair/SKILL.md'
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b'old Codex copy')
        foreign = self.home / '.pi/agent/APPEND_SYSTEM.md'
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b'keep Pi')
        harness('install', '--agent', 'codex', '--dry-run', '--home', str(self.home))
        self.assertTrue(stale.is_file())
        self.assertFalse((self.home / '.codex/AGENTS.md').exists())
        harness('install', '--agent', 'codex', '--home', str(self.home))
        self.assertFalse(stale.exists())
        self.assertEqual(foreign.read_bytes(), b'keep Pi')
        backups = list((self.home / '.agent-harness/backups').glob('*/.codex/skills/pair/SKILL.md'))
        self.assertEqual([path.read_bytes() for path in backups], [b'old Codex copy'])

    def test_relative_home_installs_absolute_hook_paths(self):
        subprocess.run([sys.executable, str(HARNESS), 'install', '--agent', 'codex',
                        '--home', self.home.name], cwd=self.home.parent,
                       capture_output=True, text=True, check=True)
        hooks = json.loads((self.home / '.codex/hooks.json').read_text(encoding='utf-8'))['hooks']
        for entries in hooks.values():
            for entry in entries:
                for handler in entry['hooks']:
                    self.assertIn(self.home.as_posix(), handler['command'])

    def test_cli_preserves_absolute_home_alias_spelling(self):
        main = runpy.run_path(str(HARNESS))['main']
        installed = []
        with mock.patch.dict(main.__globals__, {'install': lambda home, *args: installed.append(home)}), \
                mock.patch.object(Path, 'resolve', return_value=self.home / 'canonical-alias'):
            main(['install', '--agent', 'codex', '--home', str(self.home)])
        self.assertEqual(installed, [self.home])

    def test_engram_env_merge_handles_existing_values_and_quoted_tables(self):
        config = self.home / '.codex/config.toml'
        config.parent.mkdir()
        configure = runpy.run_path(str(HARNESS))['codex_config']
        for header in ('[mcp_servers.engram]', '[mcp_servers."engram"]'):
            with self.subTest(header=header):
                config.write_text('# preserve me\nmodel = "mine"\n' + header + '\ncommand = "engram"\n'
                                  'env_vars = [\n  "PATH",\n]\n', encoding='utf-8')
                output = configure(self.home).decode()
                parsed = tomllib.loads(output)
                self.assertEqual(parsed['mcp_servers']['engram']['env_vars'], ['PATH', 'ENGRAM_CLOUD_TOKEN'])
                self.assertIn('ENGRAM_CLOUD_TOKEN', parsed['shell_environment_policy']['exclude'])
                self.assertEqual(parsed['model'], 'mine')
                self.assertTrue(output.startswith('# preserve me\n'))
                config.write_text(output, encoding='utf-8')
                self.assertEqual(configure(self.home).decode(), output)

    def test_registers_missing_local_mcp_servers_and_preserves_user_entries(self):
        configure = runpy.run_path(str(HARNESS))['codex_config']
        binaries = {'engram': 'C:/tools/engram.exe', 'codegraph': 'C:/tools/codegraph.exe'}
        with mock.patch('shutil.which', side_effect=binaries.get):
            result = configure(self.home, register=True).decode()
        data = tomllib.loads(result)
        self.assertEqual(data['mcp_servers']['engram']['command'], binaries['engram'])
        self.assertEqual(data['mcp_servers']['engram']['args'], ['mcp', '--tools=agent'])
        self.assertEqual(data['mcp_servers']['codegraph']['args'], ['serve', '--mcp'])
        self.assertEqual(data['mcp_servers']['engram']['env_vars'], ['ENGRAM_CLOUD_TOKEN'])
        config = self.home / '.codex/config.toml'
        config.parent.mkdir()
        mine = '[mcp_servers.engram]\nurl = "https://memory.example/mcp"\nenabled = false\n' \
               '[mcp_servers.codegraph]\ncommand = "my-codegraph"\nargs = ["custom"]\n'
        config.write_text(mine, encoding='utf-8')
        with mock.patch('shutil.which', side_effect=binaries.get):
            preserved = tomllib.loads(configure(self.home, register=True).decode())
        self.assertEqual(preserved['mcp_servers'], tomllib.loads(mine)['mcp_servers'])
        config.write_text('model = "mine"\n', encoding='utf-8')
        with mock.patch('shutil.which', return_value=None):
            self.assertEqual(configure(self.home, register=True).decode(), 'model = "mine"\n')

    def test_runtime_hook_assessment_uses_effective_metadata(self):
        assess = runpy.run_path(str(HARNESS))['codex_hook_findings']
        expected = {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'command': 'python guard.py'}]}]}
        source = str(self.home / '.codex/hooks.json')
        base = {'sourcePath': source, 'eventName': 'PreToolUse', 'matcher': 'Bash',
                'command': 'python guard.py', 'enabled': True, 'trustStatus': 'trusted'}
        for trust in ('trusted', 'managed'):
            self.assertEqual(assess(expected, source, [{**base, 'trustStatus': trust}]), [])
        for trust in ('untrusted', 'modified'):
            with self.subTest(trust=trust):
                self.assertIn(trust, ' '.join(assess(expected, source, [{**base, 'trustStatus': trust}])))
        self.assertIn('disabled', ' '.join(assess(expected, source, [{**base, 'enabled': False}])))
        self.assertIn('missing', ' '.join(assess(expected, source, [])))
        self.assertIn('missing', ' '.join(assess(expected, source, [{**base, 'sourcePath': '/other/hooks.json'}])))

    def test_hook_api_camel_case_event_is_assessed_instead_of_reported_missing(self):
        assess = runpy.run_path(str(HARNESS))['codex_hook_findings']
        expected = {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'command': 'python guard.py'}]}]}
        source = str(self.home / '.codex/hooks.json')
        metadata = [{'sourcePath': source, 'eventName': 'preToolUse', 'matcher': 'Bash',
                     'command': 'python guard.py', 'enabled': True, 'trustStatus': 'untrusted'}]
        self.assertIn('untrusted', ' '.join(assess(expected, source, metadata)))

    def test_hook_rpc_handshake_is_read_only_bounded_and_redacts_errors(self):
        query = runpy.run_path(str(HARNESS))['query_codex_hooks']
        server = self.home / 'server.py'
        methods = self.home / 'methods.json'
        server.write_text('''import json, pathlib, sys, time
methods = []
for line in sys.stdin:
    request = json.loads(line)
    methods.append(request['method'])
    if request['method'] == 'hooks/list':
        pathlib.Path(sys.argv[2]).write_text(json.dumps(methods))
        if sys.argv[1] == 'hang': time.sleep(60)
        response = {'error': {'code': -1, 'message': 'secret_sentinel'}} if sys.argv[1] == 'error' else {'result': {'data': []}}
    elif request['method'] == 'initialize': response = {'result': {}}
    else: continue
    print(json.dumps({'id': request['id'], **response}), flush=True)
''', encoding='utf-8')
        command = lambda mode: [sys.executable, '-u', str(server), mode, str(methods)]
        self.assertEqual(query(self.home, command=command('ok')), {'data': []})
        self.assertEqual(json.loads(methods.read_text()), ['initialize', 'initialized', 'hooks/list'])
        with self.assertRaises(RuntimeError) as failed:
            query(self.home, command=command('error'))
        self.assertNotIn('secret_sentinel', str(failed.exception))
        with self.assertRaises(TimeoutError):
            query(self.home, command=command('hang'), timeout=1)

    def test_codex_memory_enforcement_resets_at_actual_user_messages(self):
        hook = load_hook('enforce_memory_graph')
        transcript = self.home / 'turns.jsonl'
        entries = [
            {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
                'type': 'McpToolCall', 'server': 'engram', 'tool': 'mem_save'}}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': []}},
            {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {'type': 'FileChange'}}},
        ]
        transcript.write_text(''.join(json.dumps(entry) + '\n' for entry in entries), encoding='utf-8')
        self.assertEqual(hook.stop_decision({'transcript_path': str(transcript)})['decision'], 'block')

    def test_runtime_diagnostics_reveal_missing_integrations_and_compression(self):
        ns = runpy.run_path(str(HARNESS))
        diagnose = ns['codex_runtime_findings']
        root = self.home / '.codex'
        root.mkdir()
        (root / 'config.toml').write_text('model = "mine"\n', encoding='utf-8')
        desired = json.loads(ns['hook_config']('codex', self.home, standalone=True))['hooks']
        (root / 'hooks.json').write_text(json.dumps({'hooks': desired}), encoding='utf-8')
        (root / 'sessions').mkdir()
        (root / 'sessions/fixture.jsonl.zst').touch()
        metadata = [{'sourcePath': str(root / 'hooks.json'), 'eventName': event,
                     'matcher': entry.get('matcher'), 'command': handler['command'],
                     'enabled': True, 'trustStatus': 'trusted'}
                    for event, entries in desired.items() for entry in entries for handler in entry['hooks']]
        reply = {'data': [{'hooks': metadata, 'warnings': [], 'errors': []}]}
        with mock.patch.dict(diagnose.__globals__, {'query_codex_hooks': lambda home: reply}), \
                mock.patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"zstd": false}', '')):
            issues = diagnose(self.home)
        self.assertTrue(any('engram' in issue for issue in issues))
        self.assertTrue(any('codegraph' in issue for issue in issues))
        self.assertTrue(any('compressed' in issue for issue in issues))
        (root / 'config.toml').write_text('[mcp_servers.engram]\ncommand = "engram"\n'
            'env_vars = ["ENGRAM_CLOUD_TOKEN"]\n[mcp_servers.codegraph]\ncommand = "codegraph"\n'
            '[shell_environment_policy]\nexclude = ["ENGRAM_CLOUD_TOKEN"]\n', encoding='utf-8')
        with mock.patch.dict(diagnose.__globals__, {'query_codex_hooks': lambda home: reply}), \
                mock.patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"zstd": true}', '')), \
                mock.patch('shutil.which', return_value=sys.executable):
            self.assertEqual(diagnose(self.home), [])

    def test_runtime_rejects_missing_windows_mcp_launcher(self):
        ns = runpy.run_path(str(HARNESS))
        diagnose = ns['codex_runtime_findings']
        root = self.home / '.codex'
        root.mkdir()
        (root / 'config.toml').write_text('[mcp_servers.codegraph]\ncommand = "cmd.exe"\n'
            'args = ["/d", "/c", "C:/removed/codegraph.cmd", "serve", "--mcp"]\n', encoding='utf-8')
        with mock.patch.dict(diagnose.__globals__, {'untrusted_codex_hooks': lambda home: []}), \
                mock.patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"zstd": true}', '')), \
                mock.patch('shutil.which', side_effect=lambda command: sys.executable if command == 'cmd.exe' else None):
            issues = diagnose(self.home)
        self.assertTrue(any('codegraph' in issue and 'launcher' in issue for issue in issues), issues)

    @unittest.skipUnless(os.name == 'nt', 'Windows batch MCP launcher')
    def test_registered_batch_launcher_runs_with_native_cmd_path(self):
        configure = runpy.run_path(str(HARNESS))['codex_config']
        shell = str(Path(shutil.which('cmd.exe')).resolve())
        launcher = self.home / 'codegraph.cmd'
        launcher.write_text('@echo launcher-ready\n', encoding='utf-8')
        binaries = {'codegraph': str(launcher), 'cmd.exe': shell}
        with mock.patch('shutil.which', side_effect=binaries.get):
            text = configure(self.home, register=True).decode()
        entry = tomllib.loads(text)['mcp_servers']['codegraph']
        result = subprocess.run([entry['command'], *entry['args']], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'launcher-ready'), result.stderr)
        config = self.home / '.codex/config.toml'
        config.parent.mkdir()
        entry['command'] = shell.replace('\\', '/')
        config.write_text('[mcp_servers.codegraph]\ncommand = ' + json.dumps(entry['command'])
                          + '\nargs = ' + json.dumps(entry['args']) + '\n', encoding='utf-8')
        with mock.patch('shutil.which', side_effect=binaries.get):
            fixed = tomllib.loads(configure(self.home, register=True).decode())['mcp_servers']['codegraph']
        self.assertEqual(fixed['command'], shell)


if __name__ == '__main__':
    unittest.main()
