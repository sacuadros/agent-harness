# agent-harness

A single source of rules, skills, subagents, and guard hooks for AI coding agents. The harness renders each piece in the format every agent expects, installs it with backups, and keeps every machine in sync through `git pull`.

- [Supported agents](#supported-agents)
- [What the harness enforces](#what-the-harness-enforces)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Choosing agents](#choosing-agents)
- [Configuration](#configuration)
- [Platform notes](#platform-notes)
- [Codex-only mode](#codex-only-mode)
- [Updating](#updating)
- [Backups and rollback](#backups-and-rollback)
- [Uninstalling](#uninstalling)
- [Scope of management](#scope-of-management)
- [Development](#development)
- [License](#license)

## Supported agents

| Agent | Instructions | Skills | Subagents | Guards |
|---|---|---|---|---|
| Claude Code (CLI and the Claude app's Code tab) | `~/.claude/CLAUDE.md` | `~/.claude/skills` | `~/.claude/agents/*.md` | hooks in `~/.claude/settings.json` |
| Codex | `~/.codex/AGENTS.md` | `~/.agents/skills` | `~/.codex/agents/*.toml` | `~/.codex/hooks.json` and execpolicy rules |
| GitHub Copilot | `~/.copilot/copilot-instructions.md` and the VS Code prompts folder | reads `~/.agents/skills` | `~/.copilot/agents/*.agent.md` | `~/.copilot/hooks/agent-harness.json` |

Some files are shared: every agent's guards run from `~/.claude/hooks`, and every agent except Claude Code reads the skills in `~/.agents/skills`.

## What the harness enforces

- **Slice Flow instead of upfront specs.** Work starts as a backlog of one-line vertical slices, each refined just in time (`story`) and built test by test (`pair`). The user approves the backlog once; the agent then builds every slice and stops only for open requirements or decisions, alarms, or approvals. Commits and pushes always wait for the user. Saying "pair" or "con pausas" slows it down.
- **Shared guards** (`core/hooks/harness_guards.py`): Conventional Commits without AI attribution; approval before push, SSH, PR, publish, or deploy; no reads of credential files or Keychain secrets; no CodeGraph lifecycle commands; and a backup before any edit to global agent config. The same rules apply to MCP tools that run commands, such as Desktop Commander. A guard that errors or cannot start blocks the action rather than allowing it.
- **Least privilege by configuration.** Claude subagents cannot spawn their own (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`), Copilot subagents get an explicit `tools:` list without `agent`, and Codex shell commands do not inherit `ENGRAM_CLOUD_TOKEN`, which only its Engram MCP server receives.
- **Memory and code-graph discipline** (`core/hooks/enforce_memory_graph.py`) in Claude Code, Codex, and Copilot: save Engram memory after substantive turns, and query CodeGraph before broad searches in indexed repositories. In Copilot, CodeGraph runs from the terminal; these hooks have not been observed firing inside VS Code, where agent hooks are still in preview.
- **Evidence gate** (`evidence` mode of the same hook) in Claude Code, Codex, and Copilot. A turn that edited code and ran no command or subagent afterwards is asked once to run the focused check or explain why none applies. It does not verify that the command is a test, and edits made through the shell go unseen. Copilot is untested inside VS Code itself. Rationale and design: [`docs/methodology.md`](docs/methodology.md).
- **Context7 before library code.** Every agent's instructions require reading current documentation through Context7 before writing code against a library, framework, SDK, CLI, or cloud API, and saying so when it is unavailable. `install` adds the server to Copilot's `~/.copilot/mcp-config.json` when none is present, and `doctor` reports a Codex or Copilot setup without it. Claude Code is not checked, because it receives Context7 as a claude.ai connector that no local file shows. No hook enforces this rule.
- **Delegation only for named reasons:** exploration, parallel writers, noisy checks, independent review, and context backstop.

## Requirements

- macOS, Linux, or Windows 10/11 (native, not WSL).
- Git and Python 3.11 or newer. Python 3.14 enables the Codex compressed-transcript checks; older versions skip them.
- Claude Code 2.1.319 or newer. Older versions let a failing guard through and have known permission and sandbox bypasses.
- The agents you use, installed and signed in.
- [Engram](https://github.com/Gentleman-Programming/engram) and [CodeGraph](https://github.com/colbymchenry/codegraph), which the rules expect. Engram cloud sync is optional.

## Quick start

### macOS and Linux

```bash
git clone https://github.com/sacuadros/agent-harness.git ~/personal-repos/agent-harness
cd ~/personal-repos/agent-harness
bin/harness install --dry-run   # preview the changes
bin/harness install             # choose agents and write; replaced files are backed up first
bin/harness check               # verify the installation
bin/harness doctor              # read-only health report
```

### Windows (PowerShell)

In this README, `~` means `%USERPROFILE%`.

```powershell
winget install --id Git.Git -e                # Git, plus the Git Bash that Claude Code uses when present
winget install --id Python.Python.3.14 -e     # Python and the py launcher the hooks run through
git clone https://github.com/sacuadros/agent-harness.git $HOME\personal-repos\agent-harness
cd $HOME\personal-repos\agent-harness
py -3 bin/harness install --dry-run
py -3 bin/harness install
py -3 bin/harness check
py -3 bin/harness doctor
```

On Windows, prefix every `bin/harness` command in this README with `py -3`.

### After the first install

- **Codex** asks you to trust new hooks the first time it sees them. Approve them once in the Codex app. `bin/harness doctor` lists any harness hooks Codex has not trusted yet.
- **The Claude app's Code tab** runs Claude Code on the same `~/.claude` (rules, skills, subagents, hooks, MCP servers), so one install covers both. The app ships its own Claude Code version, which may differ from the `claude` CLI that `doctor` checks.

## Commands

| Command | Purpose |
|---|---|
| `bin/harness install` | Render and install the harness for the selected agents. `--dry-run` previews, `--choose` reopens the agent picker, `--agents claude,codex` skips it. |
| `bin/harness check` | Exit with status 1 on drift, broken config, a failed hook selftest, or literal secrets. |
| `bin/harness doctor` | Read-only report: outdated Claude Code, Engram, and CodeGraph; Engram MCP and cloud status; Codex hook trust; leftover files. |
| `bin/harness render <agent>` | Print the instructions rendered for one agent. |
| `bin/harness restore <timestamp>` | Undo an install from its backup folder. |
| `bin/harness uninstall --agents <list>` | Remove the harness from one or more agents. |
| `bin/harness clean` | List or delete old backups. |

## Choosing agents

The first `install` in a terminal detects the agents on the machine, by their own config or command, shows the folder each one uses, and asks you to pick at least one. The choice is saved in `~/.agent-harness/agents`, and later `install`, `check`, and `doctor` runs follow it. Use `--choose` to change it or `--agents` to skip the picker. Dropping an agent leaves its files in place; `bin/harness uninstall` removes them.

Without a terminal or a saved choice, `install` covers Claude Code, Codex, and Copilot (when its config folder exists). On Windows, where Python ships without `curses`, the picker is a numbered prompt that accepts numbers or names (`claude,codex`) and asks again when an answer matches no agent.

## Configuration

### Per-machine settings

`~/.agent-harness/config.toml` stays local and is never committed:

```toml
python = "/opt/homebrew/bin/python3"                  # hook interpreter; default: python3 on PATH, py -3 on Windows
engram_cloud_server = "https://engram.example.com"   # Engram cloud server; omit to keep Engram local
```

When `engram_cloud_server` is set, `install` gives Claude Code and Codex `ENGRAM_CLOUD_SERVER` and `ENGRAM_CLOUD_AUTOSYNC=1`, and installs the auto-enroll hook (`engram_auto_enroll.py`) that enrolls projects for sync. When it is absent, `install` removes both variables, the hook entries, and the script. The token is never stored in a file; set it as described below. `doctor` prints the cloud status and reports a missing token.

### Engram MCP server

Engram's Claude plugin stopped shipping its MCP server in version 0.1.16. When no `engram` server is registered, or its entry has no command, `install` backs up `~/.claude.json` and registers one with `claude mcp add --scope user`, removing the broken entry first. If the `claude` CLI is not on PATH, it prints that command for you to run. `doctor` reports a missing server.

### Engram cloud token on macOS

Store the token in the Keychain and expose it to every app at login, so it never sits in a config file:

```bash
security add-generic-password -s engram-cloud-token -a "$USER" -w   # prompts for the token
```

Then create a LaunchAgent at `~/Library/LaunchAgents/<your-label>.engram-token.plist` whose program runs
`/bin/launchctl setenv ENGRAM_CLOUD_TOKEN "$(/usr/bin/security find-generic-password -s engram-cloud-token -w)"` with `RunAtLoad` set, and load it with `launchctl load`. Claude Code inherits the variable; Codex receives it through `env_vars` in its Engram MCP config, which the harness manages.

### Engram cloud token on Windows

Store it as a user environment variable. The prompt hides the input, and the token stays out of PowerShell history:

```powershell
$token = Read-Host 'Engram cloud token' -AsSecureString
[Environment]::SetEnvironmentVariable('ENGRAM_CLOUD_TOKEN', [Net.NetworkCredential]::new('', $token).Password, 'User')
Remove-Variable token
```

Restart Claude Code and the ChatGPT app so they pick it up. Codex receives it through the same `env_vars` entry. To sync Engram on Windows, also write `engram_cloud_server` to `$HOME\.agent-harness\config.toml` before running `install`.

## Platform notes

### Windows

- **Claude Code** runs the hooks directly, without a shell, so they work with or without Git Bash. They also guard its PowerShell tool.
- **Codex** runs its hooks through PowerShell in the Codex app, the ChatGPT app, the VS Code extension, and the CLI. Approve them once after the first install, and again whenever an update changes a hook command; `install` lists `.codex/hooks.json` when that happens.
- **Copilot** runs a hook's `powershell` command on Windows and its `bash` command elsewhere; `install` writes the right one for the machine.

### GitHub Copilot in VS Code

- VS Code's local chat reads the rules from the profile's `prompts` folder (for example `%APPDATA%\Code\User\prompts`), which `install` creates. Copilot CLI and VS Code's Copilot session target read `~/.copilot`.
- In VS Code's Migrations view, leave `agent-harness.instructions.md` unchecked. `install` retires a migrated copy, because `copilot-instructions.md` already contains those rules.
- Migrated MCP servers land in `~/.copilot/mcp-config.json`, which Settings Sync does not carry, so migrate them on each machine. `install` adds `engram` and `context7` when either is missing and leaves existing entries and other servers untouched.

## Codex-only mode

To manage only Codex, add `--agent codex` to `install`, `check`, and `doctor`:

```bash
bin/harness install --agent codex --dry-run
bin/harness install --agent codex
bin/harness check --agent codex
bin/harness doctor --agent codex   # same as: bin/harness check --agent codex --runtime
```

This mode installs self-contained hooks under `~/.codex/hooks`, the Codex instructions and subagents, and the harness skills under `~/.agents/skills`. It preserves other agents' files and third-party skills, and backs up replaced files the same way as a full install. When `engram` or `codegraph` is on PATH, it also registers missing local MCP servers while preserving existing entries, including remote or disabled ones. Engram receives `ENGRAM_CLOUD_TOKEN` by variable name; the value is never written to the config.

`check --agent codex` verifies files, config, and hook selftests. `doctor --agent codex` also checks hook activation and integration prerequisites through the local Codex CLI's `hooks/list` API, reports new, modified, disabled, or missing hooks, and exits with status 1 when readiness cannot be verified. It does not start model turns, run hooks, or change trust; installing hooks never grants trust automatically. Review the installed hooks in Codex under Settings > Hooks or with `/hooks`. An older CLI without this API is reported as unverified.

If the machine has compressed Codex transcripts, runtime checks also require Python 3.14 or newer for the hook interpreter. The MCP checks validate registration and executable availability; they do not authenticate to remote MCP servers or test Engram cloud replication.

## Updating

```bash
git pull && bin/harness install && bin/harness check
```

In Windows PowerShell:

```powershell
git pull; if ($?) { py -3 bin/harness install }; if ($?) { py -3 bin/harness check }
```

`install` also removes what newer versions stopped shipping. It records the files it writes in `~/.agent-harness/installed.json` and moves those the repository no longer has to the backup folder; until then, `check` reports them as stale. A machine without that record gets one on its first install, so cleanup starts with the next change.

## Backups and rollback

Before `install` replaces or retires a file, it copies it to `~/.agent-harness/backups/<timestamp>/`, keeping its path relative to your home, and writes a `manifest.json` that also lists the files it created.

- **Restore:** `bin/harness restore <timestamp>` undoes a whole install. Anything it removes moves to a `<timestamp>-before-restore` folder.
- **Not restored:** `~/.claude.json` and the Engram MCP entry. Backups that predate the manifest must be copied back by hand.
- **Codex:** after a restore that touches `~/.codex/hooks.json`, trust the hooks again with `/hooks`.

To prune old backups:

```bash
bin/harness clean                   # list what would be deleted
bin/harness clean --yes             # delete it; this cannot be undone
bin/harness clean --keep 10 --yes   # keep more than the default 5
```

`clean` keeps the 5 newest entries in `~/.agent-harness/backups/` and the 5 newest copies the guard made in `~/.claude/backups/`, and deletes the rest. Backups kept by other tools are left alone.

## Uninstalling

```bash
bin/harness uninstall --agents copilot --dry-run   # preview what would be removed
bin/harness uninstall --agents copilot             # remove the harness from one agent
bin/harness uninstall --agents claude,codex,copilot
```

Uninstalling moves the agent's instructions, skills, and subagents to a backup folder, removes the harness hooks from its config, and removes the Codex rules block and the environment variables the harness set. Hook scripts and skills that another agent still uses stay until that agent is removed too. Permission rules, plugin switches, MCP servers, and the Engram token protection stay, because the harness cannot distinguish yours from its own. The agent is dropped from the saved choice, so a later `install` does not bring it back. To undo, run the `restore` command it prints.

## Scope of management

- **Managed:** the files listed under [Supported agents](#supported-agents); harness hook entries in `settings.json` and `hooks.json`, merged in place so other entries keep their position; one marked block in `~/.codex/rules/default.rules`; and the plugin, permission, and token keys listed in `core/plugins.toml` and `core/permissions.toml`.
- **Retired:** old copies listed in `core/retired.txt`, including what the harness once installed for OpenCode and Pi, are moved to the backup folder.
- **Left alone:** every other setting, plugin, MCP server, skill, and agent, including third-party skills such as HyperFrames.

## Development

| Piece | Source |
|---|---|
| Instructions | `core/instructions/NN-section.md`, with `NN-section.<agent>.md` variants where the text differs by agent |
| Skills | `core/skills/<name>/`, with `name.<agent>.ext` for agent-specific files |
| Subagents | `core/agents/<name>.toml`: one prompt plus a table per agent |
| Guards | `core/hooks/` |
| Rationale for each rule | `docs/methodology.md` |
| Plugins, permissions, retired copies | `core/plugins.toml`, `core/permissions.toml`, `core/retired.txt` |

After editing, run the tests and reinstall:

```bash
python3 -m unittest tests.test_harness
bin/harness install
```

CI runs the hook selftests and the full suite on macOS, Linux, and Windows.

## License

MIT (see `LICENSE`). `NOTICE` credits the vendored skills from gentle-ai (Apache-2.0) and superpowers (MIT).
