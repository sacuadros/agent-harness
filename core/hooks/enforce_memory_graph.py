"""Claude Code hooks that enforce the evidence gate and CodeGraph usage.

  evidence Stop hook: blocks once when a turn edited code and ran no command that can fail, or subagent, afterwards.
  pretool  PreToolUse hook (Grep|Glob|Bash): denies broad search in a CodeGraph-indexed
           repo until the session has queried CodeGraph at least once.
  posttool / sessionend: record and clear Copilot's per-session CodeGraph use.

Reads Claude Code transcripts and Codex rollouts (.jsonl or .jsonl.zst), so
~/.codex/hooks.json can call it too. Run with `selftest` to check the transcript logic.
Copilot pretool errors deny the action; other agents keep the existing fail-open behavior."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

EDIT_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
COPILOT_EDITS = {'apply_patch', 'create_file', 'replace_string_in_file', 'multi_replace_string_in_file'}
COPILOT_SEARCH = ('grep_search', 'file_search', 'semantic_search')
SEARCH_CMD = re.compile(r'^\s*(?:rg|grep|egrep|ag|find|fd|git\s+grep)\b'  # PowerShell below
                        # PowerShell takes any unambiguous parameter prefix; -Depth implies -Recurse.
                        # ls/dir need -rec or longer: POSIX `ls -r` only reverses the sort.
                        r'|^\s*(?i:select-string|findstr'
                        # It also takes en and em dashes as the parameter prefix, and -s for -Recurse.
                        r'|(?:get-childitem|gci)\b.*\s[-–—](?:r(?:e(?:c(?:u(?:r(?:se?)?)?)?)?)?|de(?:p(?:th?)?)?|s)'
                        r'|(?:ls|dir)\b.*\s[-–—](?:rec(?:u(?:r(?:se?)?)?)?|depth))\b')


def entries(path):
    opener = open
    if str(path).endswith('.zst'):  # Codex rollouts
        from compression import zstd  # Python 3.14+
        opener = zstd.open
    try:
        with opener(path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except Exception:  # missing file, or a zstd frame still being written
        return


def codex_item(entry):
    payload = entry.get('payload')
    if entry.get('type') == 'event_msg' and isinstance(payload, dict) \
            and payload.get('type') == 'item_completed':
        return payload.get('item') or {}
    return None


def codex_tool_uses(item):
    kind = item.get('type')
    if kind == 'CommandExecution':
        cmd = item.get('command') or ['']
        return [{'name': 'Bash', 'input': {'command': cmd[-1] if isinstance(cmd, list) else cmd}}]
    if kind == 'McpToolCall':
        return [{'name': f'mcp__{item.get("server")}__{item.get("tool")}', 'input': {}}]
    if kind in ('SubAgentActivity', 'CollabAgentToolCall'):
        return [{'name': 'Subagent', 'input': {}}]
    if kind == 'FileChange':
        return [{'name': 'Edit', 'input': {'changes': item.get('changes') or {}}}]
    return []


def copilot_tool_uses(data):
    args = data.get('arguments') or {}
    if data.get('toolName') == 'run_in_terminal':
        return [{'name': 'Bash', 'input': {'command': args.get('command') or ''}}]
    if data.get('toolName') in ('runSubagent', 'execution_subagent'):
        return [{'name': 'Subagent', 'input': {}}]  # runs inside the turn: nothing arrives later, unlike Claude's Agent
    if data.get('toolName') not in COPILOT_EDITS:
        return [{'name': data.get('toolName') or '', 'input': args}]
    # An edit whose path cannot be read still counts as code ('?'): one extra ask beats a missed edit.
    paths = [args.get('filePath'), *(r.get('filePath') for r in args.get('replacements') or []),
             *re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+?)\r?$', str(args.get('input') or ''), re.M)]
    return [{'name': 'Edit', 'input': {'changes': {p: {} for p in paths if p} or {'?': {}}}}]


def tool_uses(entry):
    item = codex_item(entry)
    if item is not None:
        return codex_tool_uses(item)
    if entry.get('type') == 'tool.execution_start':
        return copilot_tool_uses(entry.get('data') or {})
    content = entry.get('message', {}).get('content')
    if entry.get('type') != 'assistant' or not isinstance(content, list):
        return []
    return [c for c in content if c.get('type') == 'tool_use']


def is_user_prompt(entry):
    if entry.get('type') == 'user.message':
        return True  # Copilot
    payload = entry.get('payload')
    if entry.get('type') == 'response_item' and isinstance(payload, dict) \
            and payload.get('type') == 'message' and payload.get('role') == 'user':
        return True  # Codex persists user messages separately from item_completed events
    item = codex_item(entry)
    if item is not None:
        return item.get('type') == 'UserMessage'
    # Tool results arrive as user entries with list content; real prompts are strings.
    return entry.get('type') == 'user' and isinstance(entry.get('message', {}).get('content'), str)


def last_turn_tools(path):
    turn = []
    for e in entries(path):
        if is_user_prompt(e):
            turn = []
        turn.extend(tool_uses(e))
    return turn


SHELLS = ('Bash', 'PowerShell')  # Claude Code on Windows has a separate PowerShell tool


def codegraph_used(path):
    for e in entries(path):
        for t in tool_uses(e):
            name = t.get('name', '')
            if codegraph_call(name, t.get('input', {})):
                return True
    return False


def codegraph_call(name, tool_input):
    cmd = tool_input.get('command', '') if name in (*SHELLS, 'run_in_terminal') else ''
    return 'codegraph' in name or bool(re.search(r'(?:^|[;&|\n]\s*)codegraph\s', cmd))


def codegraph_marker(data):
    session = data.get('session_id')
    if not isinstance(session, str) or not session:
        raise ValueError('missing session_id')
    name = hashlib.sha256(session.encode('utf-8')).hexdigest()
    return Path.home() / '.agent-harness' / 'state' / 'codegraph' / name


def posttool_decision(data):
    result = data.get('tool_result')
    name = data.get('tool_name', '')
    if not (isinstance(result, dict) and result.get('result_type') == 'success'
            and codegraph_call(name, data.get('tool_input', {}))):
        return
    if name in (*SHELLS, 'run_in_terminal'):
        text = result.get('text_result_for_llm')
        if not isinstance(text, str):
            raise ValueError('missing tool result')
        # The SDK shell can report tool success when its command exited nonzero.
        exit_code = re.search(r'<shellId: [^>\r\n]+ completed with exit code (-?\d+)>\s*$', text)
        if exit_code and int(exit_code[1]) != 0:
            return
    marker = codegraph_marker(data)
    marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker.touch(mode=0o600)


def sessionend(data):
    codegraph_marker(data).unlink(missing_ok=True)


def indexed_root(cwd):
    home = Path.home()  # ~/.codegraph holds the CLI's global state, not an index
    for d in [Path(cwd), *Path(cwd).parents]:
        if d != home and (d / '.codegraph').is_dir():
            return d
        if (d / '.git').exists():
            return None
    return None


DOC_SUFFIXES = ('.md', '.mdx', '.txt', '.rst')


def code_paths(tool):
    given = tool.get('input', {})
    if 'changes' in given:  # Codex: path -> {type, ...}
        paths = list(given['changes'])
    else:
        paths = [given.get('file_path') or given.get('notebook_path') or '']
    return [p for p in paths if not p.lower().endswith(DOC_SUFFIXES) and '.slices' not in Path(p).parts]


# Commands that pass whether or not the change works, so they are no evidence.
# ponytail: a list of names, not a classifier; a repo whose real check is on it answers with the one-line reason.
READ_ONLY = re.compile(r'(?i)(?:ls|ll|dir|cat|type|head|tail|less|more|wc|pwd|cd|echo|printf|stat|file|which|tree|date|true'
                       r'|grep|egrep|rg|ag|find|fd|codegraph|get-content|gc|get-childitem|gci|get-location|select-string'
                       r'|findstr|git\s+(?:-[Cc]\s+\S+\s+|-\S+\s+)*(?:status|diff|log|show|branch|rev-parse|ls-files|blame'
                       r'|remote|grep))(?=\s|$)')


def can_fail(tool):
    if tool.get('name') not in SHELLS:
        return tool.get('name') in ('Agent', 'Subagent')
    cmd = str(tool.get('input', {}).get('command') or '')
    # A command that cannot be read still counts: one missed ask beats a block the agent cannot answer.
    return not cmd.strip() or any(seg.strip() and not READ_ONLY.match(seg.strip()) for seg in re.split(r'[;&|\n]+', cmd))


def evidence_decision(data):
    if data.get('stop_hook_active'):
        return None
    turn = last_turn_tools(data.get('transcript_path', ''))
    files, last = set(), -1
    for i, t in enumerate(turn):
        if t.get('name') in EDIT_TOOLS:
            if code_paths(t):
                files.update(code_paths(t))
                last = i
    if not files or any(can_fail(t) for t in turn[last + 1:]):
        return None
    n = len(files)
    return {'decision': 'block', 'reason': (
        f'Evidencia: este turno editó {n} archivo{"s" if n > 1 else ""} de código y no ejecutó ningún comando '
        'que pueda fallar después de la última edición. Corre la verificación enfocada (test, build o el comando que muestre que '
        'funciona) o di en una línea por qué no aplica. No repitas la respuesta anterior.')}


def pretool_decision(data, copilot=False):
    tool = data.get('tool_name')
    # VS Code Copilot: its terminal is a shell, and its three search tools are Grep/Glob.
    copilot_tool = tool == 'run_in_terminal' or tool in COPILOT_SEARCH
    tool = 'Bash' if tool == 'run_in_terminal' else 'Grep' if copilot_tool else tool
    if tool in SHELLS and not SEARCH_CMD.match(data.get('tool_input', {}).get('command', '')):
        return None
    if tool not in ('Grep', 'Glob', *SHELLS) or not indexed_root(data.get('cwd') or '.'):
        return None
    if copilot:
        if codegraph_marker(data).is_file():
            return None
    else:
        transcript = data.get('transcript_path') or ''
        if not Path(transcript).is_file() or codegraph_used(transcript):
            return None  # fail open when a Claude/Codex transcript cannot be read
    return {'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': (
            'CodeGraph primero: este repo tiene índice .codegraph. '
            + ('Corre `codegraph explore "<pregunta>"` en la terminal antes de buscar. ' if copilot_tool else
               'Usa codegraph_explore (o el CLI `codegraph explore/query`) antes de buscar con Grep/Glob/grep/find. ')
            + 'Después de una consulta a CodeGraph la búsqueda queda permitida.')}}


def selftest():
    import tempfile

    def transcript(*items):
        # Real transcripts are raw UTF-8 (accents, arrows), not ASCII-escaped JSON.
        f = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False, encoding='utf-8')
        for kind, payload in items:
            if kind == 'prompt':
                f.write(json.dumps({'type': 'user', 'message': {'content': payload}}, ensure_ascii=False) + '\n')
            else:
                f.write(json.dumps({'type': 'assistant', 'message': {'content': [
                    {'type': 'tool_use', 'name': kind, 'input': payload}]}}, ensure_ascii=False) + '\n')
        f.close()
        return f.name


    repo = tempfile.mkdtemp()
    (Path(repo) / '.git').mkdir()
    (Path(repo) / '.codegraph').mkdir()
    fresh = transcript(('prompt', 'x'))
    deny = pretool_decision({'tool_name': 'Grep', 'cwd': repo, 'transcript_path': fresh})
    assert deny['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert pretool_decision({'tool_name': 'Bash', 'cwd': repo, 'transcript_path': fresh,
                             'tool_input': {'command': 'grep -rn foo .'}})
    assert pretool_decision({'tool_name': 'Bash', 'cwd': repo, 'transcript_path': fresh,
                             'tool_input': {'command': 'git status'}}) is None
    # Claude Code on Windows runs commands through a separate PowerShell tool.
    assert pretool_decision({'tool_name': 'PowerShell', 'cwd': repo, 'transcript_path': fresh,
                             'tool_input': {'command': 'grep -rn foo .'}})
    for search in ('Select-String -Path *.py -Pattern foo', 'findstr /s foo *',
                   'Get-ChildItem -Recurse -Filter *.py', 'gci -r', 'ls -Recurse',
                   # PowerShell accepts any unambiguous parameter prefix; -Depth implies -Recurse.
                   'gci -rec', 'Get-ChildItem -Recu', 'gci -Depth 3', 'dir -rec *.py', 'ls -Depth 2',
                   'gci -s *.py', 'Get-ChildItem –Recurse'):  # -s alias; en dash prefix
        assert pretool_decision({'tool_name': 'PowerShell', 'cwd': repo, 'transcript_path': fresh,
                                 'tool_input': {'command': search}}), search
    # POSIX `ls -r` only reverses the sort; `sls` is also the Serverless Framework CLI.
    for listing in ('Get-ChildItem', 'ls -r', 'sls deploy'):
        assert pretool_decision({'tool_name': 'PowerShell', 'cwd': repo, 'transcript_path': fresh,
                                 'tool_input': {'command': listing}}) is None, listing
    ps_used = transcript(('prompt', 'x'), ('PowerShell', {'command': 'codegraph query x'}))
    assert pretool_decision({'tool_name': 'Grep', 'cwd': repo, 'transcript_path': ps_used}) is None
    for used in (('mcp__codegraph__codegraph_explore', {}), ('Bash', {'command': 'codegraph query x'}),
                 ('Bash', {'command': 'cd repo && codegraph query x'})):
        path = transcript(('prompt', 'x'), used)
        assert pretool_decision({'tool_name': 'Grep', 'cwd': repo, 'transcript_path': path}) is None
    # Codex rollouts: event_msg/item_completed items, optionally zstd-compressed (Python 3.14+).
    try:
        from compression import zstd as _zstd  # noqa: F401
        has_zstd = True
    except ImportError:
        has_zstd = False

    def codex_transcript(*items, zst=False):
        zst = zst and has_zstd
        f = tempfile.NamedTemporaryFile('wb', suffix='.jsonl.zst' if zst else '.jsonl', delete=False)
        f.close()
        lines = ''.join(json.dumps({'type': 'event_msg', 'payload': {
            'type': 'item_completed', 'item': item}}) + '\n' for item in items)
        if zst:
            from compression import zstd
            with zstd.open(f.name, 'wt', encoding='utf-8') as out:
                out.write(lines)
        else:
            Path(f.name).write_text(lines, encoding='utf-8')
        return f.name

    prompt = {'type': 'UserMessage'}
    cx_fresh = codex_transcript(prompt)
    assert pretool_decision({'tool_name': 'Bash', 'cwd': repo, 'transcript_path': cx_fresh,
                             'tool_input': {'command': 'rg foo'}})
    for used in ({'type': 'McpToolCall', 'server': 'codegraph', 'tool': 'codegraph_explore'},
                 {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'codegraph query x']}):
        path = codex_transcript(prompt, used, zst=True)
        assert pretool_decision({'tool_name': 'Bash', 'cwd': repo, 'transcript_path': path,
                                 'tool_input': {'command': 'rg foo'}}) is None
    src = ('Edit', {'file_path': 'src/a.py'})
    no_check = evidence_decision({'transcript_path': transcript(('prompt', 'x'), src)})
    assert no_check['decision'] == 'block' and 'editó 1 archivo' in no_check['reason']
    test_cmd = ('Bash', {'command': 'pytest'})
    assert evidence_decision({'transcript_path': transcript(('prompt', 'x'), src, test_cmd)}) is None
    assert evidence_decision({'transcript_path': transcript(('prompt', 'x'), test_cmd, src)})['decision'] == 'block'
    assert evidence_decision({'transcript_path': transcript(('prompt', 'x'), src, ('Agent', {}))}) is None
    notes = [('Edit', {'file_path': 'README.md'}), ('Write', {'file_path': '/r/.slices/x.md'})]
    assert evidence_decision({'transcript_path': transcript(('prompt', 'x'), *notes)}) is None
    assert evidence_decision({'transcript_path': transcript(('prompt', 'x'), ('Read', {}))}) is None
    assert evidence_decision({'transcript_path': transcript(('prompt', 'x'), src), 'stop_hook_active': True}) is None
    assert evidence_decision({'transcript_path': '/nonexistent'}) is None
    # A command that cannot fail is not evidence: only read-only commands after the edit still blocks.
    for looked in ('ls -la', 'cat src/a.py', 'git status', 'git diff', 'git -C repo log --oneline | head -5',
                   'grep -n foo src/a.py', 'cd src && ls', 'Get-Content src/a.py'):
        path = transcript(('prompt', 'x'), src, ('Bash', {'command': looked}))
        assert evidence_decision({'transcript_path': path})['decision'] == 'block', looked
    for ran in ('pytest', 'cd app && npm test', 'git status && pytest', 'python3 -m unittest tests.test_x',
                'make build', 'git commit -m "fix: x"', './run.sh'):
        path = transcript(('prompt', 'x'), src, ('Bash', {'command': ran}))
        assert evidence_decision({'transcript_path': path}) is None, ran
    cx_src = {'type': 'FileChange', 'changes': {'src/a.py': {'type': 'update', 'unified_diff': '+x\n'}}}
    assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src)})['decision'] == 'block'
    cx_run = {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'pytest']}
    assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src, cx_run)}) is None
    cx_look = {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'git status']}
    assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src, cx_look)})['decision'] == 'block'
    # A Codex subagent after the edit counts as verification.
    for delegated in ('SubAgentActivity', 'CollabAgentToolCall'):
        assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src, {'type': delegated})}) is None, delegated
    # Copilot (VS Code) transcripts: user.message and tool.execution_start events.
    def copilot_transcript(*items):
        f = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False, encoding='utf-8')
        for name, args in items:
            event = {'type': 'user.message', 'data': {}} if name == 'prompt' else {
                'type': 'tool.execution_start', 'data': {'toolName': name, 'arguments': args}}
            f.write(json.dumps(event) + '\n')
        f.close()
        return f.name

    cp_src = ('replace_string_in_file', {'filePath': 'src/a.py'})
    cp_block = evidence_decision({'transcript_path': copilot_transcript(('prompt', {}), cp_src)})
    assert cp_block['decision'] == 'block' and 'editó 1 archivo' in cp_block['reason']
    cp_run = ('run_in_terminal', {'command': 'pytest'})
    assert evidence_decision({'transcript_path': copilot_transcript(('prompt', {}), cp_src, cp_run)}) is None
    assert evidence_decision({'transcript_path': copilot_transcript(('prompt', {}), cp_run, cp_src)})['decision'] == 'block'
    def cp_decision(*items):
        return evidence_decision({'transcript_path': copilot_transcript(('prompt', {}), *items)})

    assert cp_decision(('create_file', {'filePath': 'README.md'}), ('read_file', {'filePath': 'a.py'})) is None
    multi = ('multi_replace_string_in_file', {'replacements': [{'filePath': 'README.md'}, {'filePath': 'src/b.py'}]})
    assert 'editó 1 archivo' in cp_decision(multi)['reason']
    assert cp_decision(('apply_patch', {'input': '*** Begin Patch'}))['decision'] == 'block'
    # Real Copilot patches name their files in the patch text; real turns also delegate to subagents.
    assert cp_decision(('apply_patch', {'input': '*** Begin Patch\n*** Update File: /r/docs/x.md\n@@\n'})) is None
    two = ('apply_patch', {'input': '*** Begin Patch\n*** Add File: /r/a.py\n+x\n*** Update File: /r/b.py\n@@\n'})
    assert 'editó 2 archivos' in cp_decision(two)['reason']
    assert cp_decision(('apply_patch', {'input': '*** Update File: docs/x.md\r\n@@\r\n'})) is None  # CRLF patch
    for delegate in ('runSubagent', 'execution_subagent'):
        assert cp_decision(cp_src, (delegate, {'description': 'run the tests'})) is None, delegate
    old_turn = copilot_transcript(('prompt', {}), cp_src, ('prompt', {}), ('read_file', {'filePath': 'a.py'}))
    assert evidence_decision({'transcript_path': old_turn}) is None
    plain = tempfile.mkdtemp()
    (Path(plain) / '.git').mkdir()
    # Copilot CodeGraph rule: VS Code names tools in tool_name/tool_input; CodeGraph runs in the terminal.
    def cp_pre(tool, tool_input, *before, cwd=repo, transcript_path=None):
        return pretool_decision({'tool_name': tool, 'tool_input': tool_input, 'cwd': cwd,
                                 'transcript_path': transcript_path or copilot_transcript(('prompt', {}), *before)})

    for searcher in ('grep_search', 'file_search', 'semantic_search'):
        assert cp_pre(searcher, {'query': 'foo'})['hookSpecificOutput']['permissionDecision'] == 'deny', searcher
    assert cp_pre('run_in_terminal', {'command': 'rg foo'})
    # Copilot has no CodeGraph MCP tool: its deny must point at the terminal, not at codegraph_explore.
    for told in (cp_pre('grep_search', {'query': 'foo'}), cp_pre('run_in_terminal', {'command': 'rg foo'})):
        reason = told['hookSpecificOutput']['permissionDecisionReason']
        assert 'terminal' in reason and 'codegraph_explore' not in reason, reason
    assert cp_pre('run_in_terminal', {'command': 'npm test'}) is None
    assert cp_pre('read_file', {'filePath': 'a.py'}) is None
    cp_graph = ('run_in_terminal', {'command': 'codegraph explore x'})
    assert cp_pre('grep_search', {'query': 'foo'}, cp_graph) is None
    assert cp_pre('run_in_terminal', {'command': 'rg foo'}, cp_graph) is None
    assert cp_pre('grep_search', {'query': 'foo'}, cwd=plain) is None  # no index
    assert cp_pre('grep_search', {'query': 'foo'}, transcript_path='/nonexistent') is None
    assert pretool_decision({'toolName': 'grep_search', 'toolArgs': '{}', 'cwd': repo,
                             'transcript_path': copilot_transcript(('prompt', {}))}) is None  # Copilot CLI shape
    # An unreadable transcript fails open instead of blocking every search.
    assert pretool_decision({'tool_name': 'Grep', 'cwd': repo, 'transcript_path': '/nonexistent'}) is None
    assert pretool_decision({'tool_name': 'Grep', 'cwd': plain, 'transcript_path': fresh}) is None
    # ~/.codegraph is the CLI's global state dir, not a project index.
    home = Path(tempfile.mkdtemp())
    (home / '.codegraph').mkdir()
    (home / 'scratch').mkdir()
    (home / '.git').mkdir()  # Windows: %TEMP% sits inside the real profile, whose ~/.codegraph must not count
    os.environ['HOME'] = os.environ['USERPROFILE'] = str(home)  # Path.home() reads USERPROFILE on Windows
    assert pretool_decision({'tool_name': 'Grep', 'cwd': str(home / 'scratch'),
                             'transcript_path': fresh}) is None
    print('enforce_memory_graph selftest: ok' + ('' if has_zstd else ' (skipped zstd cases: needs Python 3.14+)'))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'selftest':
        return selftest()
    try:
        data = json.loads(sys.stdin.buffer.read())  # bytes: UTF-8 whatever the locale
        if mode == 'pretool':
            result = pretool_decision(data, copilot='--copilot' in sys.argv)
        else:
            result = {'evidence': evidence_decision, 'posttool': posttool_decision,
                      'sessionend': sessionend}[mode](data)
    except Exception as error:
        if '--copilot' not in sys.argv:
            return  # preserve Claude/Codex fail-open behavior
        if mode == 'pretool':
            result = {'hookSpecificOutput': {
                'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                'permissionDecisionReason': f'No se pudo comprobar CodeGraph ({type(error).__name__}). '
                                            'Revisa el hook del harness antes de continuar.'}}
        elif mode == 'posttool':
            result = {'additionalContext': f'No se pudo guardar el uso de CodeGraph ({type(error).__name__}). '
                                           'Las búsquedas seguirán bloqueadas hasta resolver el hook.'}
        elif mode == 'sessionend':
            print(f'No se pudo limpiar el estado de CodeGraph ({type(error).__name__}).', file=sys.stderr)
            return
        else:
            return
    if result and '--copilot' in sys.argv and mode == 'pretool':
        spec = result['hookSpecificOutput']
        result = {**result, 'permissionDecision': spec['permissionDecision'],
                  'permissionDecisionReason': spec['permissionDecisionReason']}
    if result and '--copilot' in sys.argv and mode == 'evidence':
        # VS Code's Copilot reads a Stop decision only inside hookSpecificOutput; Copilot CLI documents the top level.
        result = {**result, 'hookSpecificOutput': {'hookEventName': 'Stop', **result}}
    if result:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
