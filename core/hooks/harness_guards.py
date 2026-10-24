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
RSYNC_REMOTE = r'rsync\s[^;&|]*\S+:'
REMOTE = [
    (r'(?:ssh|scp|sftp|mosh)\s', 'conexión remota'),
    (RSYNC_REMOTE, 'transferencia remota con rsync'),
    (GIT + r'push\b', 'git push'),
    (r'gh\s+pr\s+(?:create|merge|close|ready|comment|review)\b', 'operación de PR en GitHub'),
    (r'gh\s+(?:release\s+create|repo\s+(?:create|delete)|workflow\s+run)\b', 'operación en GitHub'),
    (r'(?:npm|pnpm|yarn)\s+publish\b', 'publicación de paquete'),
    (r'(?:wrangler\s+(?:deploy|pages\s+deploy)|vercel(?:\s|$)|netlify\s+deploy|fly\s+deploy)',
     'deploy'),
]
# Credential files, matched on a normalized command (quotes dropped, every home spelling -> ~).
# Private keys, globs and the bare ~/.ssh folder are denied; public keys and config stay readable.
CREDENTIAL = re.compile(
    r'~/(?:\.ssh(?:/(?:id_[\w-]+|[^\s/]*_key|[^\s/]*\.pem|[^\s/]*[*?\[][^\s/]*)(?![\w.-]*\.pub)'
    r'|/?(?=[\s;&|)]|$))'
    r'|\.aws\b|\.gnupg\b|\.netrc\b|\.git-credentials\b|\.docker/config\.json|\.kube/config\b'
    r'|\.config/gh/hosts\.yml|\.config/gcloud\b|\.codex/auth\.json|\.pi/agent/auth\.json'
    r'|AppData/Roaming/(?:GitHub[^/]*/hosts\.yml|(?:gcloud|gnupg)(?=[/\s;&|)]|$)))', re.I)  # Windows and APFS ignore case
# Commands that use a key or name a path without printing secrets.
USES_KEYS = {'ssh', 'ssh-add', 'ssh-keygen', 'scp', 'sftp', 'kubectl'}
# git prints files in too many ways (diff, blame, archive, config -f, -c helpers, ext::) to deny-list,
# so it gets an allow-list: a credential path may appear only inside a quoted commit/tag/notes/merge/
# stash message, or inside the quoted ssh command of core.sshCommand / GIT_SSH_COMMAND. The guard
# does not parse shell quoting, so it trusts those quotes only in one plain git command: no separators,
# substitutions, expansions, bangs (shell aliases), backslashes in double quotes, or stray quotes.
_GIT = r'''^\s*(?:env\s+)?(?:GIT_SSH_COMMAND=(?:'[^']*'|"[^"]*")\s+)?(?:\S*[\\/])?git(?:\.exe)?'''
PLAIN_GIT = re.compile(_GIT + r'''\s[^;&|\n`$!]*$''', re.I)
# Global options before the subcommand: only pager flags. -C, -c, --git-dir, --exec-path, --config-env and
# the like change the repo or config, or run a program; a bare --namespace would make `commit` its value.
GIT_MESSAGE_CMD = re.compile(_GIT + r'''(?:\s+(?:-[pP]|--no-pager|--paginate))*'''
                             r'''\s+(?:commit|tag|notes|merge|stash)(?=\s|$)''', re.I)  # not commit-tree, merge-file
# -m may follow only flags that take no value: in -Fm or -Sm, m is the option's value and the next word
# a pathspec. Case matters there; config keys and GIT_SSH_COMMAND ignore it.
GIT_LITERAL = re.compile(r'''(?P<lead>(?:^|\s)(?:(?-i:-[aqsv]*m\s*|--message[=\s]\s*)|-c\s+core\.sshCommand=|'''
                         r'''core\.sshCommand\s+|GIT_SSH_COMMAND=))(?P<value>'[^']*'|"[^"\\]*")''', re.I)
# Only options that cannot run a command, read or write another file, or forward credentials: no -F config,
# -E log, ProxyCommand, known_hosts files, control sockets, or -A/-K/-X/-Y forwarding. git runs this command
# through sh, so values get no shell characters (redirections, globs, quotes, backslashes).
_SSH_VALUE = r'''[\w./@%:+~-]+'''
# Flags are case-sensitive (-c takes a cipher, -I loads a PKCS#11 library); names and -o keywords are not.
SSH_ONLY = re.compile(r'''^(?:\S*[\\/])?(?i:ssh(?:\.exe)?)(?:\s+(?:-i\s*''' + _SSH_VALUE + r'''|-p\s*\d+|-[46aCkqTtVvx]+'''
                      r'''|-o\s*(?i:IdentitiesOnly|IdentityFile|StrictHostKeyChecking|BatchMode|ConnectTimeout'''
                      r'''|Port|User|LogLevel|ServerAliveInterval)=''' + _SSH_VALUE + r'''))+\s*$''')


def strip_git_literals(cmd):
    if not PLAIN_GIT.match(cmd):
        return cmd
    messages = GIT_MESSAGE_CMD.match(cmd)

    def literal(m):
        if 'ssh' in m['lead'].lower():
            return m['lead'] if SSH_ONLY.match(m['value'][1:-1]) else m[0]
        after_dashes = re.search(r'\s--(?:\s|$)', cmd[:m.start()])  # after --, -m and its value are paths
        return m['lead'] if messages and not after_dashes else m[0]
    stripped = GIT_LITERAL.sub(literal, cmd)
    return cmd if re.search(r'''["']''', stripped) else stripped  # a stray quote: trust none of them
KEYCHAIN_SECRET = re.compile(r'(?:^|[\s/;&|(])security\s+(?:find-(?:generic|internet)-password\b.*'
                             r'\s-\w*[wg]\w*|dump-keychain\b.*\s-d)')


def normalize_paths(cmd):
    cmd = re.sub(r'["\'`]', '', cmd).replace('\\', '/')  # Windows separators, and `\.ssh` escapes
    cmd = re.sub(r'/(?:\./)+', '/', re.sub(r'/{2,}', '/', cmd))
    # Git Bash inherits these as plain $APPDATA and $LOCALAPPDATA.
    cmd = re.sub(r'(?i)%LOCALAPPDATA%|\$\{?(?:env:)?LOCALAPPDATA\b\}?', '~/AppData/Local', cmd)
    cmd = re.sub(r'(?i)%APPDATA%|\$\{?(?:env:)?APPDATA\b\}?', '~/AppData/Roaming', cmd)
    # POSIX spellings stay case-sensitive ($home and src/users/ are ordinary names there).
    cmd = re.sub(r'\$\(\s*echo\s+~\s*\)|\$\{?HOME\}?|/Users/[^/\s]+|/home/[^/\s]+'
                 r'|(?i:%USERPROFILE%|%HOMEDRIVE%%HOMEPATH%|\$\{?env:HOMEDRIVE\}?\$\{?env:HOMEPATH\}?'
                 r'|\$\{?env:(?:USERPROFILE|HOME)\b\}?|[a-z]:/Users/[^/]+)', '~', cmd)
    return re.sub(r'/(?:\./)+', '/', re.sub(r'/{2,}', '/', cmd))


def reads_credentials(cmd):
    cmd = normalize_paths(strip_git_literals(cmd))  # literals first: normalizing drops their quotes
    if KEYCHAIN_SECRET.search(cmd):
        return True
    for segment in re.split(r'[;&|\n]+', cmd):
        words =[w for w in segment.split() if not re.match(r'^\w+=', w)]
        while words and words[0] in ('sudo', 'command', 'env', 'exec'):
            words.pop(0)
        name = words[0].rsplit('/', 1)[-1].lower().removesuffix('.exe') if words else ''
        if words and name not in USES_KEYS and CREDENTIAL.search(segment):
            return True
    return False
CODEGRAPH_FORBIDDEN = re.compile(SEG + r'codegraph\s+(uninit|install|uninstall|upgrade)\b')
# What Codex execpolicy prefix rules can match once it unwraps `bash -lc` into plain commands.
PLAIN_SEG = r'(?:^|[;&|\n]\s*)'
# rsync is left out: execpolicy cannot tell host: from a local path, so the hook handles it.
CODEX_PROMPTED = [p.replace(GIT, r'git\s+') for p, _ in REMOTE if p != RSYNC_REMOTE] + [r'codegraph\s+index\b']
PATCH_FILE = re.compile(r'^\*\*\* (?:Update|Delete) File: (.+)$', re.M)  # Codex apply_patch
CODEGRAPH_INDEX = re.compile(SEG + r'codegraph\s+index\b')
# Matched on normalize_paths(cmd), so Windows homes and %LOCALAPPDATA% already read ~/AppData/Local.
TMP_WORKTREE = re.compile(SEG + GIT + r'worktree\s+add\s+(?:-\S+\s+(?:\S+\s+)?)*'
                          r'(?:(?:/tmp|/var/tmp|/private/tmp|/private/var/tmp|/(?:private/)?var/folders'
                          r'|~/AppData/Local/Temp|\$\{?(?:env:)?TE?MP\b\}?|%TE?MP%|[a-z]:/Windows/Temp)(?=[/\s;&|)]|$)'
                          # macOS $TMPDIR ends in /, so "$TMPDIR"wt (quotes dropped) is a path; mktemp -d uses it.
                          r'|\$\{?TMPDIR|(?:\$\(\s*)?mktemp(?=[\s;&|)]|$))', re.I)


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
        quoted = re.match(r'\s*(["\'])(.*?)\1', line)  # one-line quoted message: stop at its closing quote
        line = (quoted[2] if quoted and quoted[2].strip() else line).strip().strip('"\'')
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
        if re.search(SEG + RSYNC_REMOTE, cmd):
            return decision('deny', 'Regla global: rsync remoto requiere autorización explícita. '
                                    'Pide permiso al usuario y usa `scp`, que Codex sí pide aprobar.')
        return decision('deny', 'Regla global: operación remota en una forma que las reglas de '
                                'Codex no ven (git -C/-c, VAR=, $(), subshell). Reescríbela en '
                                'forma simple (p. ej. `cd repo && git push`) para que Codex pida '
                                'aprobación.')
    return out


def _bash_decision(cmd):
    if reads_credentials(cmd):
        return decision('deny', 'Regla global: no leer credenciales (claves privadas, ~/.aws, '
                                '~/.gnupg, tokens de CLI) ni imprimir secretos del Llavero. Pide al '
                                'usuario que lo haga si es imprescindible.')
    if CODEGRAPH_FORBIDDEN.search(cmd):
        return decision('deny', 'Regla global: nunca ejecutar codegraph uninit/install/'
                                'uninstall/upgrade.')
    if TMP_WORKTREE.search(normalize_paths(cmd)):
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
    ps = bash_decision({'tool_name': 'PowerShell', 'tool_input': {'command': 'git commit -m "Update stuff"'}})
    assert ps['hookSpecificOutput']['permissionDecision'] == 'deny'  # Claude's Windows shell tool
    # The reason quotes only the message, not the commands chained after its closing quote.
    for chained in ('git commit -m "Update stuff"; git log --oneline', "git commit -m 'Update stuff' && git log"):
        reason = _bash_decision(chained)['hookSpecificOutput']['permissionDecisionReason']
        assert reason.endswith('Asunto recibido: "Update stuff"'), reason
    assert bash('git commit -m "fix: ok"; git log --oneline') is None
    assert bash('git commit -m "" -m "Update stuff"') == 'deny'  # git drops the empty paragraph
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
    for secret in ('cat ~/.ssh/id_ed25519', 'cp ~/.aws/credentials /tmp/x', 'base64 $HOME/.netrc',
                   'security find-generic-password -s engram-cloud-token -w',
                   'head ~/.codex/auth.json', 'gpg --export-secret-keys > k; cat ~/.gnupg/x'):
        assert bash(secret) == 'deny', secret
        assert bash_decision({'tool_input': {'command': secret}}, codex=True)[
            'hookSpecificOutput']['permissionDecision'] == 'deny', secret
    for fine in ('cat ~/.ssh/config', 'cat ~/.ssh/id_ed25519.pub', 'ssh-keygen -lf ~/.ssh/known_hosts',
                 'aws s3 ls', 'security find-generic-password -s x'):
        assert bash(fine) in (None, 'ask'), fine
    # Review findings: globs, directories, quoting, Keychain flag variants.
    for secret in ('cat ~/.ssh/*', 'cat ~/.ssh/id_*', 'tar cz ~/.ssh', 'cp -r ~/.aws x',
                   'cat "$HOME"/.ssh/id_rsa', "cat ~/'.ssh'/id_rsa", 'cat ~/.git-credentials',
                   'security find-generic-password -s x -g', 'security find-generic-password -ws x',
                   '/usr/bin/security find-internet-password -s x -w', 'security dump-keychain -d'):
        assert bash(secret) == 'deny', secret
    # Using a key without printing it, or naming a path in a commit message, is fine.
    for fine in ('ssh-add ~/.ssh/id_ed25519', 'ssh -i ~/.ssh/id_ed25519 host uptime',
                 'kubectl --kubeconfig ~/.kube/config get pods',
                 'git commit -m "fix: guard ~/.aws/ reads"', 'cat ~/.ssh/id_ed25519-cert.pub'):
        assert bash(fine) != 'deny', fine
    # Windows: every home spelling, PowerShell readers, and gh's token file under %APPDATA%.
    for secret in (r'Get-Content C:\Users\me\.ssh\id_ed25519', r'gc C:/Users/me/.aws/credentials',
                   r'type %USERPROFILE%\.netrc', r'Get-Content $env:USERPROFILE\.ssh\id_rsa',
                   r'Copy-Item ${env:userprofile}\.codex\auth.json x', r'Get-Content $HOME\.git-credentials',
                   r'gc ~\.ssh\id_ed25519', r'Get-Content "$env:APPDATA\GitHub CLI\hosts.yml"',
                   r'type %APPDATA%\GitHub CLI\hosts.yml', r'gc C:\Users\me\AppData\Roaming\GitHub CLI\hosts.yml',
                   # Review findings: doubled separators, case, more home spellings, spaced profiles.
                   r'gc C:\\Users\\me\\.ssh\\id_rsa', r'Get-Content ~\.SSH\ID_RSA', r'gc $env:USERPROFILE\.AWS\x',
                   r'type %HOMEDRIVE%%HOMEPATH%\.ssh\id_rsa', r'gc $env:HOMEDRIVE$env:HOMEPATH\.ssh\id_rsa',
                   r'gc $env:HOME\.ssh\id_rsa', r'gc "C:\Users\John Doe\.ssh\id_rsa"',
                   r'gc ~\AppData\Roaming\GitHub` CLI\hosts.yml', r'gc ~\AppData\Roaming\GitHub*\hosts.yml',
                   # Every backslash becomes `/`: bash reads `\.` as `.`, so keeping it would let this through.
                   r'cat ~/\.ssh/id_rsa',
                   # gcloud and GnuPG keep their Windows state under %APPDATA%; git can print any file.
                   r'gc $env:APPDATA\gcloud\application_default_credentials.json',
                   r'Copy-Item -Recurse %APPDATA%\gnupg x', r'GIT.exe diff --no-index NUL ~\.ssh\id_rsa',
                   'git diff --no-index /dev/null ~/.ssh/id_ed25519',
                   # Review findings: git prints files in many ways, and Git Bash spells %APPDATA% as $APPDATA.
                   'git diff /dev/null ~/.ssh/id_rsa', 'git blame --contents ~/.ssh/id_rsa README.md',
                   'git merge-file -p ~/.ssh/id_rsa /dev/null /dev/null', 'git archive --add-file=~/.ssh/id_rsa HEAD',
                   'git config -f ~/.aws/credentials --list', 'cat $APPDATA/gcloud/credentials.db',
                   'cat ${APPDATA}/gnupg/pubring.kbx',
                   # Second review: options that take a value, commands git runs, and keys stored with -F.
                   'git --namespace commit diff ~/.ssh/id_rsa', 'git --git-dir commit diff ~/.ssh/id_rsa',
                   "git fetch --upload-pack='cat ~/.ssh/id_rsa 1>&2' .", "git clone -u 'cat ~/.ssh/id_rsa >&2' . x",
                   "git submodule foreach 'cat ~/.ssh/id_rsa'", 'git commit --allow-empty -F ~/.ssh/id_rsa',
                   'git tag -a v1 -F ~/.ssh/id_rsa', 'git notes add -F ~/.aws/credentials',
                   "GIT_SSH_COMMAND='ssh -i ~/.ssh/id_rsa' git diff /dev/null ~/.ssh/id_rsa",
                   # The key-option strip is for git only, and -c/--config/--exec can make git run a command.
                   'grep -r . core.sshCommand ssh -i ~/.ssh/id_rsa',
                   'git -c core.sshCommand="cat ~/.ssh/id_rsa" fetch x:y',
                   'git -c protocol.ext.allow=always fetch "ext::sh -c cat% ~/.ssh/id_rsa"',
                   'git clone --config core.sshCommand="cat ~/.ssh/id_rsa" x:y z', 'git push --exec="cat ~/.ssh/id_rsa" x',
                   # Allow-list: in git a credential path may appear only in a literal message or as ssh's -i key.
                   'git commit -m "$(cat ~/.ssh/id_rsa)"', 'git commit -m "x" -m "`cat ~/.ssh/id_rsa`"',
                   'git stash push -- ~/.aws/credentials', 'git -C ~/.ssh log -p',
                   # Review of the allow-list: quotes are trusted only in one plain git command.
                   '''echo "git commit -m '"; cat ~/.ssh/id_rsa; echo "'"''',
                   "# git commit -m '\ncat ~/.ssh/id_rsa\n# '",
                   "git commit -m \"$(cat <<'EOF'\nfix: msg\nEOF\ncat ~/.ssh/id_rsa >&2\nEOF\n)\"",
                   'git commit -m "fix: a\\" ; Get-Content ~/.ssh/id_rsa ; "x"',
                   "git -c 'alias.x=!cat' x -- GIT_SSH_COMMAND ssh -i ~/.ssh/id_rsa",
                   "git -c 'alias.x=!eval grep .' x core.sshCommand 'ssh -i ~/.ssh/id_rsa'",
                   '''git notes add "x -m 'y" -F ~/.ssh/id_rsa "'"''',
                   "git -c core.sshCommand='ssh -o ProxyCommand=cat -i ~/.ssh/id_rsa' fetch x:y",
                   "git --namespace commit diff -m '~/.ssh/id_rsa'", "git -c core.sshCommand='ssh -F ~/.aws/credentials' fetch o",
                   "git -c core.sshCommand='ssh -E ~/.aws/credentials' fetch o",
                   "GIT_SSH_COMMAND='ssh -o UserKnownHostsFile=~/.aws/credentials' git fetch",
                   # Option audit: git runs the ssh command through sh, so its values must not redirect, and
                   # agent, GSSAPI, and X11 forwarding hand credentials to the remote host.
                   "git -c core.sshCommand='ssh -i x<~/.ssh/id_rsa' fetch o",
                   "GIT_SSH_COMMAND='ssh -o User=me>~/.aws/credentials' git fetch",
                   "git -c core.sshCommand='ssh -A -i ~/.ssh/id_rsa' fetch o",
                   "GIT_SSH_COMMAND='ssh -Y -i ~/.ssh/id_rsa' git fetch",
                   # A literal is a message only after an exact -m, in a plain message subcommand, before --.
                   "git commit -Fm '~/.ssh/id_rsa'", "git commit -Sm '~/.ssh/id_rsa'",
                   "git -c core.sshCommand='ssh -I lib.so -i ~/.ssh/id_rsa' fetch o","git -c core.hooksPath=h commit -m '~/.ssh/id_rsa'",
                   "git commit -- -m '~/.ssh/id_rsa'", "git commit-tree -m '~/.ssh/id_rsa' HEAD"):
        assert bash(secret) == 'deny', secret
    for fine in (r'ssh -i C:\Users\me\.ssh\id_ed25519 host uptime', r'ssh.exe -i ~\.ssh\id_rsa host',
                 r'Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub', r'git -C C:\Users\me\repo status',
                 # POSIX paths that only look like a home, and escaped regexes, stay allowed.
                 'ls ~/Projects/users/x/.ssh', 'ls app/users/fixtures/.ssh', 'ls src/Views/Home/x/.ssh',
                 'cat $home/.aws/notes', 'git diff --no-index a.txt b.txt', 'git diff ~/.ssh/config',
                 'git -C ~/repo push origin main', 'git commit -m "docs: mention ~/.aws/config"',
                 'ls ~/AppData/Roaming/gcloud-sdk-notes',
                 # Telling git which key to use names the key without printing it.
                 "git config --global core.sshCommand 'ssh -i ~/.ssh/id_ed25519'",
                 'git -c core.sshCommand="ssh -i ~/.ssh/id_rsa" fetch origin',
                 "GIT_SSH_COMMAND='ssh -i ~/.ssh/id_rsa' git fetch", 'git push -u origin main',
                 "git commit -m 'fix: guard ~/.netrc reads'", 'git tag -a v1 -m "docs: ~/.aws is denied"',
                 "git commit -am 'fix: guard ~/.aws reads'", 'git commit -qm"fix: guard ~/.aws reads"',
                 "git stash push -m 'wip: ~/.aws notes'", "env GIT_SSH_COMMAND='ssh -i ~/.ssh/id_rsa' git fetch",
                 "GIT_SSH_COMMAND='ssh -o IdentitiesOnly=yes -i ~/.ssh/id_rsa' git fetch",
                 r"git config core.sshCommand 'C:\Windows\System32\OpenSSH\ssh.exe -i ~/.ssh/id_rsa'",
                 "git --no-pager commit -m 'fix: rotate ~/.aws/credentials'", "git -p commit -m 'docs: ~/.aws'",
                 "git --paginate commit -sm 'docs: ~/.aws'","git -c core.sshCommand='ssh -4 -p 22 -i ~/.ssh/id_rsa' fetch"):
        assert bash(fine) != 'deny', fine
    for temp in (r'git worktree add $env:TEMP\wt feature', r'git worktree add %TEMP%\wt',
                 r'git worktree add C:\Users\me\AppData\Local\Temp\wt', r'git worktree add "C:\Windows\Temp\wt"',
                 r'git worktree add C:\\Windows\\Temp\\wt', r'git worktree add "C:\Users\John Doe\AppData\Local\Temp\wt"',
                 r'git worktree add $env:LOCALAPPDATA\Temp\wt', r'git worktree add %LOCALAPPDATA%\Temp\wt',
                 r'git worktree add ~\AppData\Local\Temp\wt', r'git worktree add $env:USERPROFILE\AppData\Local\Temp\wt',
                 # macOS per-user temp: $TMPDIR is /var/folders/<id>/T/.
                 'git worktree add $TMPDIR/wt', 'git worktree add "${TMPDIR}wt" -b x',
                 'git worktree add /var/folders/1s/abc/T/wt', 'git worktree add /private/var/folders/1s/abc/T/wt',
                 'git worktree add "$TMPDIR"wt', 'git worktree add $(mktemp -d)/wt', 'git worktree add $TEMP/wt'):
        assert bash(temp) == 'deny', temp
    assert bash(r'git worktree add ..\repo-worktrees\x') is None
    assert bash('git worktree add mktemp-notes') is None

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

    # Copilot: camelCase payloads carry toolArgs as a JSON string; replies need top-level fields.
    camel = copilot_output({'toolName': 'bash', 'toolArgs': json.dumps({'command': 'git commit -m "wip"'})})
    assert camel['permissionDecision'] == 'deny' and camel['hookSpecificOutput']['permissionDecision'] == 'deny'
    snake = copilot_output({'tool_name': 'Bash', 'tool_input': {'command': 'git push'}})
    assert snake['permissionDecision'] == 'ask'
    assert copilot_output({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}}) is None
    # execpolicy cannot tell host: from a local path, so remote rsync is the hook's job in Codex.
    assert codex('rsync -a dist/ host:/srv') == 'deny'
    assert codex('rsync -a src/ dst/') is None
    assert bash('rsync -a dist/ host:/srv') == 'ask'
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


def copilot_input(data):
    """Copilot sends Claude-style snake_case or its own camelCase with toolArgs as a JSON string."""
    tool_input = data.get('tool_input')
    if tool_input is None:
        raw = data.get('toolArgs') or '{}'
        tool_input = json.loads(raw) if isinstance(raw, str) else raw
    tool_input.setdefault('file_path', tool_input.get('filePath') or tool_input.get('path') or '')
    return {**data, 'tool_input': tool_input, 'session_id': data.get('session_id') or data.get('sessionId')}


def copilot_output(data):
    out = bash_decision(copilot_input(data))
    if not out:
        return None
    spec = out['hookSpecificOutput']
    return {'permissionDecision': spec['permissionDecision'],
            'permissionDecisionReason': spec['permissionDecisionReason'], **out}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'selftest':
        return selftest()
    try:
        data = json.loads(sys.stdin.buffer.read())  # bytes: UTF-8 whatever the locale
        if mode == 'bash' and '--copilot' in sys.argv:
            result = copilot_output(data)
        elif mode == 'backup' and ('toolArgs' in data or 'toolName' in data):
            result = backup(copilot_input(data))
        elif mode == 'bash':
            result = bash_decision(data, codex='--codex' in sys.argv)
        else:
            result = {'backup': backup}[mode](data)
    except Exception:
        return  # fail open: never wedge a session on a hook bug
    if result:
        print(json.dumps(result))  # ASCII-escaped, so a cp1252 stdout cannot fail


if __name__ == '__main__':
    main()
