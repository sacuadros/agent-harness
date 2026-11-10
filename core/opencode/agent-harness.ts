// agent-harness guards for OpenCode, installed by bin/harness (edit core/opencode/agent-harness.ts).
// Runs the same harness_guards.py as Claude Code and Codex. Approval prompts live in
// opencode.json `permission.bash`; this plugin only denies, and it fails open on any error.
import { spawnSync } from "node:child_process"

const PYTHON: string[] = {python}
const HOOKS = "{claude_hooks}"

function guard(mode: string, payload: object, extra: string[] = []) {
  const result = spawnSync(PYTHON[0], [...PYTHON.slice(1), `${HOOKS}/harness_guards.py`, mode, ...extra], {
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

function before(tool: string, sessionID: string, command?: string, filePath?: string, patchText?: string) {
  if (tool === "bash" || tool === "shell") {  // V2 names it shell; OpenCode 2.2.5 ran V1 bash calls as shell too
    const out = guard("bash", { tool_input: { command: command ?? "" } }, ["--codex"])
    if (out?.hookSpecificOutput?.permissionDecision === "deny") {
      throw new Error(out.hookSpecificOutput.permissionDecisionReason)
    }
  } else if ((tool === "edit" || tool === "write") && filePath) {
    guard("backup", { session_id: sessionID, tool_input: { file_path: filePath } })
  } else if ((tool === "patch" || tool === "apply_patch") && patchText) {  // relative paths resolve from cwd
    guard("backup", { session_id: sessionID, tool_name: "apply_patch", cwd: process.cwd(), tool_input: { command: patchText } })
  }
}

export const AgentHarness = async () => ({
  "tool.execute.before": async (input: { tool: string; sessionID: string }, output: { args: any }) =>
    before(input.tool, input.sessionID, output.args?.command, output.args?.filePath, output.args?.patchText),
})

// OpenCode 1.x with a default export calls its server(); OpenCode 2 loads only the id and setup(),
// and a throw in execute.before fails that call.
export default {
  id: "agent-harness",
  server: AgentHarness,
  async setup(ctx: any) {
    await ctx.tool.hook("execute.before", async (event: { tool: string; sessionID: string; input: any }) =>
      before(event.tool, event.sessionID, event.input?.command, event.input?.path, event.input?.patchText))
  },
}
