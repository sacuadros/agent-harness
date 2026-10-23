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

- **Slice Flow** instead of upfront specs: a backlog of one-line vertical slices, refined just in time (`story`) and built test by test (`pair`).
- **Guards** shared by every agent (`core/hooks/harness_guards.py`): Conventional Commits without AI attribution, approval for push/SSH/PR/publish/deploy, no reads of credential files or Keychain secrets, no CodeGraph lifecycle commands, and a backup before editing global agent config.
- **Memory and code-graph discipline** in Claude Code and Codex (`core/hooks/enforce_memory_graph.py`): save Engram memory after substantive turns, and query CodeGraph before broad searches in indexed repos.
- **Delegation only for named reasons** (exploration, parallel writers, noisy checks, independent review, context backstop).

## Requirements

- macOS or Linux, Git, and Python 3.11 or newer. Python 3.14 adds the Codex compressed-transcript checks; on older versions the hook skips them.
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

### Per-PC settings

`~/.agent-harness/config.toml` is never committed:

```toml
python = "/opt/homebrew/bin/python3"   # interpreter for the hooks; default: python3 on PATH
```

### Engram cloud token (macOS)

Keep the token in the Keychain and expose it to every app at login, so it never sits in a config file:

```bash
security add-generic-password -s engram-cloud-token -a "$USER" -w   # prompts for the token
```

Then add a LaunchAgent at `~/Library/LaunchAgents/<your-label>.engram-token.plist` whose program runs
`/bin/launchctl setenv ENGRAM_CLOUD_TOKEN "$(/usr/bin/security find-generic-password -s engram-cloud-token -w)"` with `RunAtLoad` set, and load it with `launchctl load`. Codex receives the variable through `env_vars` in its Engram MCP config, which the harness manages; Claude Code inherits it.

## Sync

```bash
git pull && bin/harness install && bin/harness check
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
