"""Claude Code hooks that enforce Engram and CodeGraph usage.

  stop     Stop hook: blocks once when a substantive turn ends without an Engram write.
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
SUBSTANTIVE_TOOL_CALLS = 8  # ponytail: tool count as a proxy for "a finding happened"
SEARCH_CMD = re.compile(r'^\s*(?:rg|grep|egrep|ag|find|fd|git\s+grep)\b')


def entries(path):
    opener = open
    if str(path).endswith('.zst'):  # Codex rollouts
        from compression import zstd  # Python 3.14+
        opener = zstd.open
    try:
        with opener(path, 'rt') as f:
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
    if kind == 'FileChange':
        return [{'name': 'Edit', 'input': {}}]
    return []


def tool_uses(entry):
    item = codex_item(entry)
    if item is not None:
        return codex_tool_uses(item)
    content = entry.get('message', {}).get('content')
    if entry.get('type') != 'assistant' or not isinstance(content, list):
        return []
    return [c for c in content if c.get('type') == 'tool_use']


def is_user_prompt(entry):
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


def stop_decision(data):
    if data.get('stop_hook_active'):
        return None
    turn = last_turn_tools(data.get('transcript_path', ''))
    names = [t.get('name', '') for t in turn]
    if any(n.endswith(ENGRAM_WRITES) for n in names):
        return None
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
            cmd = t.get('input', {}).get('command', '') if name == 'Bash' else ''
            if 'codegraph' in name or re.match(r'^\s*codegraph\s', cmd):
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


def pretool_decision(data):
    tool = data.get('tool_name')
    if tool == 'Bash' and not SEARCH_CMD.match(data.get('tool_input', {}).get('command', '')):
        return None
    if tool not in ('Grep', 'Glob', 'Bash') or not indexed_root(data.get('cwd') or '.'):
        return None
    transcript = data.get('transcript_path') or ''
    if not Path(transcript).is_file() or codegraph_used(transcript):
        return None  # fail open when the transcript cannot be read
    return {'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': (
            'CodeGraph primero: este repo tiene índice .codegraph. Usa codegraph_explore '
            '(o el CLI `codegraph explore/query`) antes de buscar con Grep/Glob/grep/find. '
            'Después de una consulta a CodeGraph la búsqueda queda permitida.')}}


def selftest():
    import tempfile

    def transcript(*items):
        f = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False)
        for kind, payload in items:
            if kind == 'prompt':
                f.write(json.dumps({'type': 'user', 'message': {'content': payload}}) + '\n')
            else:
                f.write(json.dumps({'type': 'assistant', 'message': {'content': [
                    {'type': 'tool_use', 'name': kind, 'input': payload}]}}) + '\n')
        f.close()
        return f.name

    edit = transcript(('prompt', 'x'), ('Edit', {}))
    assert stop_decision({'transcript_path': edit})['decision'] == 'block'
    assert stop_decision({'transcript_path': edit, 'stop_hook_active': True}) is None
    saved = transcript(('prompt', 'x'), ('Edit', {}), ('mcp__plugin_engram_engram__mem_save', {}))
    assert stop_decision({'transcript_path': saved}) is None
    old_edit = transcript(('Edit', {}), ('prompt', 'y'), ('Read', {}))
    assert stop_decision({'transcript_path': old_edit}) is None
    many = transcript(('prompt', 'x'), *[('Bash', {'command': 'ls'})] * SUBSTANTIVE_TOOL_CALLS)
    assert stop_decision({'transcript_path': many})['decision'] == 'block'

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
    for used in (('mcp__codegraph__codegraph_explore', {}), ('Bash', {'command': 'codegraph query x'})):
        path = transcript(('prompt', 'x'), used)
        assert pretool_decision({'tool_name': 'Grep', 'cwd': repo, 'transcript_path': path}) is None
    # Codex rollouts: event_msg/item_completed items, optionally zstd-compressed.
    def codex_transcript(*items, zst=False):
        f = tempfile.NamedTemporaryFile('wb', suffix='.jsonl.zst' if zst else '.jsonl', delete=False)
        f.close()
        lines = ''.join(json.dumps({'type': 'event_msg', 'payload': {
            'type': 'item_completed', 'item': item}}) + '\n' for item in items)
        if zst:
            from compression import zstd
            with zstd.open(f.name, 'wt') as out:
                out.write(lines)
        else:
            Path(f.name).write_text(lines)
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
    # An unreadable transcript fails open instead of blocking every search.
    assert pretool_decision({'tool_name': 'Grep', 'cwd': repo, 'transcript_path': '/nonexistent'}) is None
    plain = tempfile.mkdtemp()
    (Path(plain) / '.git').mkdir()
    assert pretool_decision({'tool_name': 'Grep', 'cwd': plain, 'transcript_path': fresh}) is None
    # ~/.codegraph is the CLI's global state dir, not a project index.
    home = Path(tempfile.mkdtemp())
    (home / '.codegraph').mkdir()
    (home / 'scratch').mkdir()
    os.environ['HOME'] = str(home)
    assert pretool_decision({'tool_name': 'Grep', 'cwd': str(home / 'scratch'),
                             'transcript_path': fresh}) is None
    print('enforce_memory_graph selftest: ok')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'selftest':
        return selftest()
    try:
        data = json.load(sys.stdin)
        result = {'stop': stop_decision, 'pretool': pretool_decision}[mode](data)
    except Exception:
        return  # fail open: never wedge a session on a hook bug
    if result:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
