"""Claude Code PreToolUse guards for the global CLAUDE.md delivery rules.

  bash    (matcher Bash) commit hygiene, remote/delivery operations, CodeGraph lifecycle,
          worktrees under temporary directories.
  backup  (matcher Edit|Write|MultiEdit|NotebookEdit) timestamped backup of global agent
          configuration before the first edit of each file in a session.

Codex (~/.codex/hooks.json): `bash --codex` drops "ask" results, which Codex rejects; the
prompt cases live in ~/.codex/rules/default.rules. `backup` also reads apply_patch input.

Run with `selftest` to check the rules. Fails open: any unexpected error allows the action.
Limit: Bash commands that write global config (sed -i, redirects) are not backed up."""
import json
import re
import shutil
import sys
import time
from pathlib import Path

HOME = Path.home()
CONFIG_ROOTS = [HOME / '.claude', HOME / '.codex', HOME / '.agents']
RUNTIME_DIRS = {'projects', 'file-history', 'cache', 'sessions', 'debug', 'backups',
                'shell-snapshots', 'paste-cache', 'session-env', 'todos', 'plugins',
                'downloads', 'ide', 'statsig', 'telemetry', 'history.jsonl',
                'archived_sessions', '.tmp', 'log', 'attachments', 'worktrees'}  # Codex
BACKUP_DIR = HOME / '.claude' / 'backups'

# A command segment starts at the beginning or after a shell separator.
SEG = r'(?:^|[;&|(\n]\s*|\$\(\s*)(?:\w+=\S+\s+)*'
GIT = r'git\s+(?:-[Cc]\s+\S+\s+|-\S+\s+)*'  # global options, incl. -C <path>
CONVENTIONAL = re.compile(
    r'^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: \S')
ATTRIBUTION = re.compile(r'co-authored-by|generated with \[?claude|🤖', re.I)
REMOTE = [
    (r'(?:ssh|scp|sftp|mosh)\s', 'conexión remota'),
    (r'rsync\s[^;&|]*\S+:', 'transferencia remota con rsync'),
    (GIT + r'push\b', 'git push'),
    (r'gh\s+pr\s+(?:create|merge|close|ready|comment|review)\b', 'operación de PR en GitHub'),
    (r'gh\s+(?:release\s+create|repo\s+(?:create|delete)|workflow\s+run)\b', 'operación en GitHub'),
    (r'(?:npm|pnpm|yarn)\s+publish\b', 'publicación de paquete'),
    (r'(?:wrangler\s+(?:deploy|pages\s+deploy)|vercel(?:\s|$)|netlify\s+deploy|fly\s+deploy)',
     'deploy'),
]
CODEGRAPH_FORBIDDEN = re.compile(SEG + r'codegraph\s+(uninit|install|uninstall|upgrade)\b')
# What Codex execpolicy prefix rules can match once it unwraps `bash -lc` into plain commands.
PLAIN_SEG = r'(?:^|[;&|\n]\s*)'
CODEX_PROMPTED = [p.replace(GIT, r'git\s+') for p, _ in REMOTE] + [r'codegraph\s+index\b']
PATCH_FILE = re.compile(r'^\*\*\* (?:Update|Delete) File: (.+)$', re.M)  # Codex apply_patch
CODEGRAPH_INDEX = re.compile(SEG + r'codegraph\s+index\b')
TMP_WORKTREE = re.compile(SEG + GIT + r'worktree\s+add\s+(?:-\S+\s+(?:\S+\s+)?)*'
                          r'["\']?(?:/tmp|/var/tmp|/private/tmp|/private/var/tmp)\b')


def decision(kind, reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                   'permissionDecision': kind,
                                   'permissionDecisionReason': reason}}


def commit_subject(cmd):
    """First line of the first -m message, or None when the message comes from elsewhere."""
    m = re.search(r'\s(?:-[a-zA-Z]*m|--message)(?:=|\s+)(.*)', cmd, re.S)  # -m, -am, -qm
    if not m:
        return None
    body = re.sub(r'^\s*["\']?\$\(\s*cat\s*<<-?\s*["\']?(\w+)["\']?\s*\n', '', m.group(1))
    for line in body.splitlines():
        line = line.strip().strip('"\'')
        if line:
            return line
    return None


def bash_decision(data, codex=False):
    cmd = data.get('tool_input', {}).get('command', '')
    out = _bash_decision(cmd)
    if codex and out and out['hookSpecificOutput']['permissionDecision'] == 'ask':
        # Codex rejects "ask"; ~/.codex/rules/default.rules prompts, but only for plain forms.
        if any(re.search(PLAIN_SEG + p, cmd) for p in CODEX_PROMPTED):
            return None
        return decision('deny', 'Regla global: operación remota en una forma que las reglas de '
                                'Codex no ven (git -C/-c, VAR=, $(), subshell). Reescríbela en '
                                'forma simple (p. ej. `cd repo && git push`) para que Codex pida '
                                'aprobación.')
    return out


def _bash_decision(cmd):
    if CODEGRAPH_FORBIDDEN.search(cmd):
        return decision('deny', 'Regla global: nunca ejecutar codegraph uninit/install/'
                                'uninstall/upgrade.')
    if TMP_WORKTREE.search(cmd):
        return decision('deny', 'Regla global: los worktrees que pueden usar CodeGraph van '
                                'bajo el home (<repo-parent>/<repo>-worktrees/<nombre>), '
                                'nunca en /tmp.')
    commit = re.search(SEG + GIT + r'commit\b', cmd)
    if commit:
        if ATTRIBUTION.search(cmd):
            return decision('deny', 'Regla global: los commits no llevan Co-Authored-By ni '
                                    'atribución a IA. Quita esas líneas.')
        subject = commit_subject(cmd[commit.start():])  # ignore -m of earlier commands (python3 -m)
        if subject is not None and not CONVENTIONAL.match(subject):
            return decision('deny', f'Regla global: usa Conventional Commits '
                                    f'(tipo(scope): resumen). Asunto recibido: "{subject[:80]}"')
    for pattern, label in REMOTE:
        if re.search(SEG + pattern, cmd):
            return decision('ask', f'Regla global: {label} requiere autorización explícita '
                                   f'del usuario para destino y operación.')
    if CODEGRAPH_INDEX.search(cmd):
        return decision('ask', 'Regla global: codegraph index solo para recuperar un índice '
                               'corrupto. Confirma que es el caso.')
    return None


def config_path(path):
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    for root in CONFIG_ROOTS:
        try:
            rel = p.relative_to(root.resolve())
        except ValueError:
            continue
        if rel.parts and rel.parts[0] not in RUNTIME_DIRS:
            return root, rel
    return None


def edited_paths(data):
    tool_input = data.get('tool_input', {})
    if data.get('tool_name') != 'apply_patch':
        return [tool_input.get('file_path') or tool_input.get('notebook_path') or '']
    cwd = Path(data.get('cwd') or '.')
    return [str(cwd / p.strip()) for p in PATCH_FILE.findall(tool_input.get('command', ''))]


def backup(data, backup_dir=BACKUP_DIR, now=None):
    session = (data.get('session_id') or 'nosession')[:8]
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(now))
    targets = []
    for path in edited_paths(data):
        found = config_path(path) if path else None
        if not found or not Path(path).is_file():
            continue
        root, rel = found
        stem = f'{root.name.lstrip(".")}__{"__".join(rel.parts)}'
        if any(backup_dir.glob(f'{stem}.{session}.*')):
            continue  # already backed up in this session
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f'{stem}.{session}.{stamp}'
        shutil.copy2(path, target)
        targets.append(str(target))
    if not targets:
        return None
    return {'systemMessage': f'Respaldo de configuración global: {", ".join(targets)}'}


def selftest():
    import tempfile

    def bash(cmd):
        out = bash_decision({'tool_input': {'command': cmd}})
        return out and out['hookSpecificOutput']['permissionDecision']

    heredoc = "git commit -m \"$(cat <<'EOF'\nfeat(app): add thing\n\nbody\nEOF\n)\""
    assert bash(heredoc) is None
    assert bash(heredoc.replace('body', 'Co-Authored-By: Claude <x@y>')) == 'deny'
    assert bash('git commit -m "Update stuff"') == 'deny'
    assert bash('git add -A && git commit -m "fix: handle nil"') is None
    assert bash('git commit --amend --no-edit') is None
    assert bash('python3 -m unittest t && git commit -m "fix: ok"') is None
    assert bash('python3 -m unittest t && git commit -m "wip"') == 'deny'
    assert bash('git commit -qm "update stuff"') == 'deny'
    assert bash('git commit -am "chore: bump"') is None
    assert bash('git push origin main') == 'ask'
    assert bash('git status && git push') == 'ask'
    assert bash('git -C ../repo push origin x') == 'ask'
    assert bash('git -C ../repo commit -m "wip"') == 'deny'
    assert bash('ssh host uptime') == 'ask'
    assert bash('rsync -a dist/ host:/srv') == 'ask'
    assert bash('rsync -a src/ dst/') is None
    assert bash('gh pr create --fill') == 'ask'
    assert bash('gh pr view 3') is None
    assert bash('pnpm publish') == 'ask'
    assert bash('echo "git push is blocked"') is None
    assert bash('codegraph uninstall') == 'deny'
    assert bash('codegraph index') == 'ask'
    assert bash('codegraph query Foo') is None
    assert bash('git worktree add /tmp/wt feature') == 'deny'
    assert bash('git worktree add -b x ../repo-worktrees/x') is None
    assert bash('ls -la') is None

    tmp = Path(tempfile.mkdtemp())
    cfg = HOME / '.claude' / 'settings.json'
    if cfg.is_file():
        data = {'session_id': 'abcdef123', 'tool_input': {'file_path': str(cfg)}}
        assert backup(data, tmp)['systemMessage']
        assert backup(data, tmp) is None  # once per session and file
        assert len(list(tmp.iterdir())) == 1
    runtime = {'session_id': 'x', 'tool_input': {'file_path': str(HOME / '.claude' / 'projects' / 'm.md')}}
    assert backup(runtime, tmp) is None
    assert backup({'tool_input': {'file_path': '/etc/hosts'}}, tmp) is None

    # Codex: "ask" is unsupported in PreToolUse; execpolicy rules prompt instead.
    def codex(cmd):
        out = bash_decision({'tool_input': {'command': cmd}}, codex=True)
        return out and out['hookSpecificOutput']['permissionDecision']

    assert codex('git push') is None
    assert codex('cd ../repo && git push origin x') is None
    assert codex('ssh host uptime') is None
    # Forms execpolicy prefix rules cannot see: deny and ask for the plain form.
    assert codex('git -C ../repo push origin x') == 'deny'
    assert codex('FOO=1 git push') == 'deny'
    assert codex('echo $(gh pr create --fill)') == 'deny'
    out = bash_decision({'tool_input': {'command': 'git commit -m "wip"'}}, codex=True)
    assert out['hookSpecificOutput']['permissionDecision'] == 'deny'
    # Codex edits arrive as apply_patch text; relative paths resolve against cwd.
    agents = HOME / '.codex' / 'AGENTS.md'
    if agents.is_file():
        tmp = Path(tempfile.mkdtemp())
        patch = (f'*** Begin Patch\n*** Update File: {agents}\n@@\n-a\n+b\n'
                 f'*** Add File: {HOME}/.codex/new-file.md\n+x\n*** End Patch\n')
        data = {'session_id': 'codex1234', 'tool_name': 'apply_patch', 'tool_input': {'command': patch}}
        assert backup(data, tmp)['systemMessage']
        assert [p.name.split('.')[0] for p in tmp.iterdir()] == ['codex__AGENTS']
        rel = {'session_id': 'codex5678', 'cwd': str(HOME / '.codex'), 'tool_name': 'apply_patch',
               'tool_input': {'command': '*** Begin Patch\n*** Update File: AGENTS.md\n*** End Patch\n'}}
        assert backup(rel, tmp)['systemMessage']
    print('harness_guards selftest: ok')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'selftest':
        return selftest()
    try:
        data = json.load(sys.stdin)
        if mode == 'bash':
            result = bash_decision(data, codex='--codex' in sys.argv)
        else:
            result = {'backup': backup}[mode](data)
    except Exception:
        return  # fail open: never wedge a session on a hook bug
    if result:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
