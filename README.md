# agent-harness

One source of rules, skills, subagents, and guard hooks for the coding agents I use, rendered for each agent and installed with backups. Edit it here, sync it with `git pull`, and every agent on every PC follows the same workflow.

| Agent | Instructions | Skills | Subagents | Guards |
|---|---|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude/skills` | `~/.claude/agents/*.md` | hooks in `~/.claude/settings.json` |
| Codex | `~/.codex/AGENTS.md` | `~/.codex/skills` | `~/.codex/agents/*.toml` | `~/.codex/hooks.json` + execpolicy rules |
| OpenCode | `~/.config/opencode/AGENTS.md` | reads `~/.claude/skills` | `~/.config/opencode/agents/*.md` | plugin + `permission.bash` asks |
| Pi | `~/.pi/agent/AGENTS.md` | reads `~/.claude/skills` | `~/.pi/agent/agents/*.md` (pi-subagents) | extension with confirmations |
| GitHub Copilot | `~/.copilot/copilot-instructions.md` and the VS Code prompts folder | reads `~/.claude/skills` | `~/.copilot/agents/*.agent.md` | `~/.copilot/hooks/agent-harness.json` |

OpenCode, Pi, and Copilot are managed only on PCs where their config folder already exists.

## What the harness enforces

- **Slice Flow** instead of upfront specs: a backlog of one-line vertical slices, refined just in time (`story`) and built test by test (`pair`). You approve the backlog once; the agent builds every slice on its own and stops only for product decisions, alarms, or approvals. Commits and pushes always wait for you. Say "pair" or "con pausas" to slow it down.
- **Guards** shared by every agent (`core/hooks/harness_guards.py`): Conventional Commits without AI attribution, approval for push/SSH/PR/publish/deploy, no reads of credential files or Keychain secrets, no CodeGraph lifecycle commands, and a backup before editing global agent config. The same rules cover MCP tools that run commands (such as Desktop Commander). A guard that errors or cannot start blocks the action instead of allowing it; Claude Code needs 2.1.295 or newer for the second part.
- **Least privilege by configuration:** Claude subagents cannot spawn their own (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`), and Codex shell commands do not inherit `ENGRAM_CLOUD_TOKEN`, which only its Engram MCP receives.
- **Memory and code-graph discipline** in Claude Code and Codex (`core/hooks/enforce_memory_graph.py`): save Engram memory after substantive turns, and query CodeGraph before broad searches in indexed repos.
- **Delegation only for named reasons** (exploration, parallel writers, noisy checks, independent review, context backstop).

## Requirements

- macOS, Linux, or Windows 10/11 (native, not WSL), Git, and Python 3.11 or newer. Python 3.14 adds the Codex compressed-transcript checks; on older versions the hook skips them.
- On Windows the harness manages Claude Code, Codex, and GitHub Copilot; OpenCode and Pi are macOS and Linux for now.
- The agents you use, already installed and signed in.
- Optional: [Engram](https://github.com/Gentleman-Programming/engram) and [CodeGraph](https://github.com/colbymchenry/codegraph), which the rules expect.

## Set up a PC

```bash
git clone <this repo> ~/personal-repos/agent-harness
cd ~/personal-repos/agent-harness
bin/harness install --dry-run   # see what would change
bin/harness install             # write it; replaced files are backed up first
bin/harness check               # exit 1 on drift, broken config, failed hook selftest, or literal secrets
bin/harness doctor              # read-only report: leftovers, PATH duplicates, version drift
```

Codex asks you to trust new hooks the first time it sees them. Approve them once in the Codex app.

### Windows

In PowerShell; `~` in this README means `%USERPROFILE%`:

```powershell
winget install --id Git.Git -e                # Git, plus the Git Bash that Claude Code uses when present
winget install --id Python.Python.3.14 -e     # Python and the py launcher the hooks run through
git clone <this repo> $HOME\personal-repos\agent-harness
cd $HOME\personal-repos\agent-harness
py -3 bin/harness install --dry-run
py -3 bin/harness install
py -3 bin/harness check
py -3 bin/harness doctor
```

- Claude Code runs the hooks directly, with no shell, so they work with or without Git Bash. They also guard its PowerShell tool.
- To sync Engram, write `engram_cloud_server = "<your server>"` to `$HOME\.agent-harness\config.toml` before `install` (see Per-PC settings), then set the token as in "Engram cloud token (Windows)".
- Codex runs its hooks through PowerShell, in the Codex app, the ChatGPT app, the VS Code extension, and the CLI alike. Approve them once in Codex after the first install. Approve them again whenever an update changes a hook command; `bin/harness install` lists `.codex/hooks.json` when that happens.
- Copilot runs the `powershell` command of a hook on Windows and the `bash` one elsewhere; `install` writes the one for this PC. VS Code's local chat reads the rules from your profile's `prompts` folder (`%APPDATA%\Code\User\prompts`), which `install` creates; Copilot CLI reads `~/.copilot`.

### Per-PC settings

`~/.agent-harness/config.toml` is never committed:

```toml
python = "/opt/homebrew/bin/python3"   # interpreter for the hooks; default: python3 on PATH, py -3 on Windows
engram_cloud_server = "https://engram.example.com"   # your Engram cloud server; omit to keep Engram local
```

With `engram_cloud_server` set, `bin/harness install` gives Claude Code and Codex `ENGRAM_CLOUD_SERVER` and `ENGRAM_CLOUD_AUTOSYNC=1`; without it, install removes both. The token never goes in a file; set it as described below. `bin/harness doctor` prints the cloud status and reports a missing token.

Engram's Claude plugin stopped shipping its MCP server in 0.1.16. When no `engram` server is registered, or its entry has no command, `bin/harness install` backs up `~/.claude.json` and registers one with `claude mcp add --scope user`, removing the broken entry first. Without the `claude` CLI on PATH, it prints that command for you to run. `bin/harness doctor` reports the missing server.

### Engram cloud token (macOS)

Keep the token in the Keychain and expose it to every app at login, so it never sits in a config file:

```bash
security add-generic-password -s engram-cloud-token -a "$USER" -w   # prompts for the token
```

Then add a LaunchAgent at `~/Library/LaunchAgents/<your-label>.engram-token.plist` whose program runs
`/bin/launchctl setenv ENGRAM_CLOUD_TOKEN "$(/usr/bin/security find-generic-password -s engram-cloud-token -w)"` with `RunAtLoad` set, and load it with `launchctl load`. Codex receives the variable through `env_vars` in its Engram MCP config, which the harness manages; Claude Code inherits it.

### Engram cloud token (Windows)

Store it as a user environment variable. The prompt hides what you type, and the token stays out of your PowerShell history:

```powershell
$token = Read-Host 'Engram cloud token' -AsSecureString
[Environment]::SetEnvironmentVariable('ENGRAM_CLOUD_TOKEN', [Net.NetworkCredential]::new('', $token).Password, 'User')
Remove-Variable token
```

Restart Claude Code and the ChatGPT app so they pick it up. Codex receives it through the same `env_vars` entry.

## Sync

```bash
git pull && bin/harness install && bin/harness check
```

In Windows PowerShell:

```powershell
git pull; if ($?) { py -3 bin/harness install }; if ($?) { py -3 bin/harness check }
```

## Backups and rollback

Every file `install` replaces or retires is copied first to `~/.agent-harness/backups/<timestamp>/`, keeping its path under your home. To roll back one file, copy it back from there.

## What is managed and what is left alone

- **Managed:** the files in the table above; harness hook entries inside `settings.json` and `hooks.json`, which are merged in place so other entries keep their position; one marked block in `~/.codex/rules/default.rules`; and the plugin, permission, and token keys listed in `core/plugins.toml` and `core/permissions.toml`.
- **Retired:** old copies listed in `core/retired.txt` are moved to the backup folder.
- **Left alone:** every other setting, plugin, MCP server, skill, and agent you have, including third-party skills such as HyperFrames.

## Where to edit

| Piece | Source |
|---|---|
| Instructions | `core/instructions/NN-section.md`, with `NN-section.<agent>.md` variants where the text differs by agent |
| Skills | `core/skills/<name>/`, with `name.<agent>.ext` for agent-specific files |
| Subagents | `core/agents/<name>.toml`: one prompt plus a table per agent |
| Guards | `core/hooks/`, `core/opencode/agent-harness.ts`, `core/pi/agent-harness.ts` |
| Plugins, permissions, retired copies | `core/plugins.toml`, `core/permissions.toml`, `core/retired.txt` |

After editing, run `python3 -m unittest tests.test_harness` and `bin/harness install`.

## License

MIT for this repo (see `LICENSE`). `NOTICE` credits the vendored skills from gentle-ai (Apache-2.0) and superpowers (MIT).
