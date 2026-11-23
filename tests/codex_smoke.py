"""Exercise the installed harness with the real Codex CLI, without model turns."""

import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / 'bin' / 'harness'


class CodexRuntime(unittest.TestCase):
    def test_installed_hooks_and_rules(self):
        codex = shutil.which('codex')
        self.assertIsNotNone(codex, 'Codex CLI must be on PATH for this smoke test')
        harness = runpy.run_path(str(HARNESS))

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            subprocess.run([sys.executable, str(HARNESS), 'install', '--agent', 'codex', '--home', directory],
                           check=True, capture_output=True, text=True, timeout=30)
            codex_home = home / '.codex'
            hooks_file = codex_home / 'hooks.json'
            expected = json.loads(hooks_file.read_text(encoding='utf-8'))['hooks']
            result = harness['query_codex_hooks'](home, check_approvals=True)
            self.assertEqual(set(result['approval']), {'approval_policy', 'approvals_reviewer'})
            self.assertTrue(result['data'])
            for project in result['data']:
                self.assertFalse(project['errors'], project['errors'])
            hooks = [hook for project in result['data'] for hook in project['hooks']]
            findings = harness['codex_hook_findings'](expected, hooks_file, hooks)
            # A fresh installation must be visible to the runtime and still require trust.
            count = sum(len(entry['hooks']) for entries in expected.values() for entry in entries)
            self.assertGreater(count, 0)
            self.assertEqual(len(findings), count, findings)
            self.assertTrue(all(finding.startswith('Codex hook untrusted:') for finding in findings), findings)

            rules = codex_home / 'rules' / 'default.rules'
            env = {**os.environ, 'CODEX_HOME': str(codex_home)}
            for tokens, decision in (
                (['git', 'commit', '-m', 'docs: exercise approval policy'], 'prompt'),
                (['git', 'status'], None),
            ):
                with self.subTest(tokens=tokens):
                    policy = subprocess.check_output(
                        [codex, 'execpolicy', 'check', '--rules', str(rules), '--', *tokens],
                        env=env, encoding='utf-8', timeout=15,
                    )
                    self.assertEqual(json.loads(policy).get('decision'), decision, policy)


if __name__ == '__main__':
    unittest.main()
