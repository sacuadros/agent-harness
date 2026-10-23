// agent-harness guards for OpenCode, installed by bin/harness (edit core/opencode/agent-harness.ts).
// Runs the same harness_guards.py as Claude Code and Codex. Approval prompts live in
// opencode.json `permission.bash`; this plugin only denies, and it fails open on any error.
import { spawnSync } from "node:child_process"

const PYTHON = "{python}"
const HOOKS = "{claude_hooks}"

function guard(mode: string, payload: object, extra: string[] = []) {
  const result = spawnSync(PYTHON, [`${HOOKS}/harness_guards.py`, mode, ...extra], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    timeout: 5000,
  })
  if (result.status !== 0 || !result.stdout?.trim()) return null
  try {
    return JSON.parse(result.stdout)
  } catch {
    return null
  }
}

export const AgentHarness = async () => ({
  "tool.execute.before": async (input: { tool: string; sessionID: string }, output: { args: any }) => {
    if (input.tool === "bash") {
      const out = guard("bash", { tool_input: { command: output.args?.command ?? "" } }, ["--codex"])
      if (out?.hookSpecificOutput?.permissionDecision === "deny") {
        throw new Error(out.hookSpecificOutput.permissionDecisionReason)
      }
    } else if ((input.tool === "edit" || input.tool === "write") && output.args?.filePath) {
      guard("backup", { session_id: input.sessionID, tool_input: { file_path: output.args.filePath } })
    }
  },
})
