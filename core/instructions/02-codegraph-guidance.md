## CodeGraph

When answering structural or codebase questions, use CodeGraph before broad filesystem searches. This is a hard ordering rule for repo maps, architecture, call flow, dependencies, symbol references, impact analysis, and “how does X work” questions.

Every Git worktree needs its own `.codegraph/` index. Never copy, symlink, or reuse another checkout's index.

CodeGraph intelligence surface:

- Prefer the `codegraph_explore` MCP tool when it is available; it returns relevant source, call paths, and blast-radius context in one call.
- If the MCP tool is unavailable, invoke the upstream `codegraph` CLI directly, not through wrapper tools. Agents may use its read-only intelligence commands: `codegraph status`, `codegraph query`, `codegraph explore`, `codegraph node`, `codegraph files`, `codegraph callers`, `codegraph callees`, `codegraph impact`, and `codegraph affected`.
- Use only those read-only commands; never run or recommend `codegraph uninit`, `install`, `uninstall`, or `upgrade`, and use `codegraph index` only to recover a corrupt index or after an upgrade that asks for it.

Required order for structural/codebase questions:

1. Resolve the project root with `git rev-parse --show-toplevel || pwd`. Initialize CodeGraph without asking in a real project, never in `$HOME`, temporary directories, or non-project folders.
2. Check for `<project-root>/.codegraph/` before any broad Read/Glob/Grep exploration. If it is missing and CodeGraph is available, run `codegraph init` from `<project-root>` once.
3. After edits, rely on watcher auto-sync by default. Run `codegraph sync` only when the watcher is disabled or CodeGraph reports stale files that do not refresh normally.
4. Only fall back to normal filesystem tools after CodeGraph initialization or use fails, and briefly explain the fallback.
