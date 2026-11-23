"""Claude Code hooks that enforce Engram and CodeGraph usage.

  stop     Stop hook: blocks once when a substantive turn ends without an Engram write.
  evidence Stop hook: blocks once when a turn edited code and ran no command or subagent afterwards.
  pretool  PreToolUse hook (Grep|Glob|Bash): denies broad search in a CodeGraph-indexed
           repo until the session has queried CodeGraph at least once.

Reads Claude Code transcripts and Codex rollouts (.jsonl or .jsonl.zst), so
~/.codex/hooks.json can call it too. Run with `selftest` to check the transcript logic.
Fails open: any unexpected error allows the action."""
import json
import os
import re
import sys
from pathlib import Path

ENGRAM_WRITES = ('mem_save', 'mem_update', 'mem_session_summary')
EDIT_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
COPILOT_EDITS = {'apply_patch', 'create_file', 'replace_string_in_file', 'multi_replace_string_in_file'}
COPILOT_SEARCH = ('grep_search', 'file_search', 'semantic_search')
SUBSTANTIVE_TOOL_CALLS = 8
# Tools that organize or recall work without producing anything worth remembering.
BOOKKEEPING = ('mcp__ccd_turn__', 'mcp__ccd_session__', 'ToolSearch', 'Skill', 'TodoWrite',
               'Subagent', 'manage_todo_list', 'tool_search', 'task_complete', 'vscode_askQuestions', 'memory')  # Codex and Copilot subagents: only the evidence gate counts them
MEMORY_READS = ('mem_search', 'mem_context', 'mem_get_observation', 'mem_judge', 'mem_current_project')  # ponytail: tool count as a proxy for "a finding happened"
CLI_WRITE = re.compile(r'(?:^|[;&|\n]\s*)engram\s+(?:save|update)\b')
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


def stop_decision(data):
    if data.get('stop_hook_active'):
        return None
    turn = last_turn_tools(data.get('transcript_path', ''))
    names = [t.get('name', '') for t in turn]
    if any(n.endswith(ENGRAM_WRITES) for n in names) or any(
            CLI_WRITE.search(t.get('input', {}).get('command', '')) for t in turn if t.get('name') in SHELLS):
        return None
    names = [n for n in names if not n.startswith(BOOKKEEPING) and not n.endswith(MEMORY_READS)]
    waiting = any(t.get('name') == 'Agent' or (t.get('name') in SHELLS and t.get('input', {}).get(
        'run_in_background')) for t in turn)
    if waiting and not (EDIT_TOOLS & set(names)):
        return None  # results arrive in a later turn; that turn decides what to remember
    if not (EDIT_TOOLS & set(names)) and len(names) < SUBSTANTIVE_TOOL_CALLS:
        return None
    return {'decision': 'block', 'reason': (
        'Engram: este turno hizo cambios o trabajo sustantivo sin guardar memoria. '
        'Si hubo una decisión, hallazgo, bugfix o convención, llama mem_save ahora. '
        'Si no hay nada durable, dilo en una línea. No repitas la respuesta anterior.')}


def codegraph_used(path):
    for e in entries(path):
        for t in tool_uses(e):
            name = t.get('name', '')
            cmd = t.get('input', {}).get('command', '') if name in SHELLS else ''
            if 'codegraph' in name or re.search(r'(?:^|[;&|\n]\s*)codegraph\s', cmd):
                return True
    return False


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
    if not files or any(t.get('name') in (*SHELLS, 'Agent', 'Subagent') for t in turn[last + 1:]):
        return None
    n = len(files)
    return {'decision': 'block', 'reason': (
        f'Evidencia: este turno editó {n} archivo{"s" if n > 1 else ""} de código y no ejecutó ningún comando '
        'después de la última edición. Corre la verificación enfocada (test, build o el comando que muestre que '
        'funciona) o di en una línea por qué no aplica. No repitas la respuesta anterior.')}


def pretool_decision(data):
    tool = data.get('tool_name')
    # VS Code Copilot: its terminal is a shell, and its three search tools are Grep/Glob.
    copilot = tool == 'run_in_terminal' or tool in COPILOT_SEARCH
    tool = 'Bash' if tool == 'run_in_terminal' else 'Grep' if copilot else tool
    if tool in SHELLS and not SEARCH_CMD.match(data.get('tool_input', {}).get('command', '')):
        return None
    if tool not in ('Grep', 'Glob', *SHELLS) or not indexed_root(data.get('cwd') or '.'):
        return None
    transcript = data.get('transcript_path') or ''
    if not Path(transcript).is_file() or codegraph_used(transcript):
        return None  # fail open when the transcript cannot be read
    return {'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': (
            'CodeGraph primero: este repo tiene índice .codegraph. '
            + ('Corre `codegraph explore "<pregunta>"` en la terminal antes de buscar. ' if copilot else
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

    edit = transcript(('prompt', 'corrige la acción → ñandú'), ('Edit', {}))
    assert stop_decision({'transcript_path': edit})['decision'] == 'block'
    assert stop_decision({'transcript_path': edit, 'stop_hook_active': True}) is None
    saved = transcript(('prompt', 'x'), ('Edit', {}), ('mcp__plugin_engram_engram__mem_save', {}))
    assert stop_decision({'transcript_path': saved}) is None
    old_edit = transcript(('Edit', {}), ('prompt', 'y'), ('Read', {}))
    assert stop_decision({'transcript_path': old_edit}) is None
    many = transcript(('prompt', 'x'), *[('Bash', {'command': 'ls'})] * SUBSTANTIVE_TOOL_CALLS)
    assert stop_decision({'transcript_path': many})['decision'] == 'block'
    bookkeeping = transcript(('prompt', 'x'), *[('mcp__ccd_turn__update_plan', {}), ('ToolSearch', {}),
                                                 ('mcp__plugin_engram_engram__mem_judge', {}),
                                                 ('Skill', {}), ('mcp__ccd_turn__wrap_up', {})] * 2)
    assert stop_decision({'transcript_path': bookkeeping}) is None
    reads = [('Read', {})] * SUBSTANTIVE_TOOL_CALLS
    for launch in (('Agent', {'prompt': 'research'}), ('Bash', {'command': 'pytest', 'run_in_background': True})):
        waiting = transcript(('prompt', 'x'), launch, *reads)
        assert stop_decision({'transcript_path': waiting}) is None, launch
    edited_while_waiting = transcript(('prompt', 'x'), ('Agent', {}), ('Edit', {}))
    assert stop_decision({'transcript_path': edited_while_waiting})['decision'] == 'block'
    cli_save = transcript(('prompt', 'x'), ('Edit', {}), *[('Bash', {'command': 'ls'})] * SUBSTANTIVE_TOOL_CALLS,
                          ('Bash', {'command': 'cd repo && engram save "t" "c" --project p'}))
    assert stop_decision({'transcript_path': cli_save}) is None
    after_heredoc = transcript(('prompt', 'x'), ('Edit', {}),
                               ('Bash', {'command': "python3 - <<'EOF'\nprint(1)\nEOF\nengram save t c"}))
    assert stop_decision({'transcript_path': after_heredoc}) is None
    ps_save = transcript(('prompt', 'x'), ('Edit', {}), ('PowerShell', {'command': 'engram save t c'}))
    assert stop_decision({'transcript_path': ps_save}) is None
    cli_read = transcript(('prompt', 'x'), ('Edit', {}), ('Bash', {'command': 'engram search harness'}))
    assert stop_decision({'transcript_path': cli_read})['decision'] == 'block'

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
    cx_edit = codex_transcript(prompt, {'type': 'FileChange', 'changes': {}})
    assert stop_decision({'transcript_path': cx_edit})['decision'] == 'block'
    cx_saved = codex_transcript(prompt, {'type': 'FileChange'},
                                {'type': 'McpToolCall', 'server': 'engram', 'tool': 'mem_save'}, zst=True)
    assert stop_decision({'transcript_path': cx_saved}) is None
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
    cx_src = {'type': 'FileChange', 'changes': {'src/a.py': {'type': 'update', 'unified_diff': '+x\n'}}}
    assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src)})['decision'] == 'block'
    cx_run = {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'pytest']}
    assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src, cx_run)}) is None
    # A Codex subagent after the edit counts as verification, and never as work for the Engram stop hook.
    for delegated in ('SubAgentActivity', 'CollabAgentToolCall'):
        assert evidence_decision({'transcript_path': codex_transcript(prompt, cx_src, {'type': delegated})}) is None, delegated
    assert stop_decision({'transcript_path': codex_transcript(prompt, *[{'type': 'SubAgentActivity'}] * 9)}) is None
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
    # Copilot Engram stop rule: edits and 8+ work calls need an Engram write; housekeeping does not count.
    def cp_stop(*items, **extra):
        return stop_decision({'transcript_path': copilot_transcript(('prompt', {}), *items), **extra})

    assert cp_stop(cp_src)['decision'] == 'block'
    assert cp_stop(cp_src, ('mcp_engram_mem_save', {})) is None
    read = ('read_file', {'filePath': 'a.py'})
    assert cp_stop(*[read] * SUBSTANTIVE_TOOL_CALLS)['decision'] == 'block'
    assert cp_stop(*[read] * (SUBSTANTIVE_TOOL_CALLS - 1)) is None
    quiet = [('manage_todo_list', {}), ('tool_search', {}), ('task_complete', {}), ('vscode_askQuestions', {}),
             ('memory', {}), ('mcp_engram_mem_search', {}), ('mcp_engram_mem_context', {}),
             ('runSubagent', {}), ('execution_subagent', {})]
    assert cp_stop(*quiet * 2) is None
    assert cp_stop(('runSubagent', {}), *[read] * SUBSTANTIVE_TOOL_CALLS)['decision'] == 'block'  # not "arrives later"
    assert cp_stop(cp_src, stop_hook_active=True) is None
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
        result = {'stop': stop_decision, 'evidence': evidence_decision, 'pretool': pretool_decision}[mode](data)
    except Exception:
        return  # fail open: never wedge a session on a hook bug
    if result and '--copilot' in sys.argv and mode in ('stop', 'evidence'):
        # VS Code's Copilot reads a Stop decision only inside hookSpecificOutput; Copilot CLI documents the top level.
        result = {**result, 'hookSpecificOutput': {'hookEventName': 'Stop', **result}}
    if result:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
