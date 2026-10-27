// agent-harness guards for Pi, installed by bin/harness (edit core/pi/agent-harness.ts).
// Runs the same harness_guards.py as Claude Code. "ask" decisions become a Pi confirmation;
// without a UI (print mode) they are blocked. A guard that fails or times out blocks the call.
import { spawnSync } from "node:child_process"

const PYTHON: string[] = {python}
const HOOKS = "{claude_hooks}"
const SESSION = `pi${Date.now()}` // one backup per file per Pi process

function guard(mode: string, payload: object) {
  const result = spawnSync(PYTHON[0], [...PYTHON.slice(1), `${HOOKS}/harness_guards.py`, mode], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    timeout: 5000,
  })
  if (result.error || result.status !== 0) throw new Error(result.error?.message ?? `exit ${result.status}`)
  return result.stdout?.trim() ? JSON.parse(result.stdout) : null // no output: allowed
}

export default function (pi: any) {
  pi.on("tool_call", async (event: any, ctx: any) => {
    try {
      return await check(event, ctx)
    } catch (error: any) {
      return { block: true, reason: `agent-harness guard failed: ${error?.message ?? error}` }
    }
  })
}

async function check(event: any, ctx: any) {
  if (event.toolName === "bash") {
    const command = event.input?.command ?? ""
    const out = guard("bash", { session_id: SESSION, tool_input: { command } })?.hookSpecificOutput
    if (out?.permissionDecision === "deny") return { block: true, reason: out.permissionDecisionReason }
    if (out?.permissionDecision === "ask") {
      if (!ctx.hasUI) return { block: true, reason: `${out.permissionDecisionReason} (no UI to confirm)` }
      const ok = await ctx.ui.confirm("agent-harness", `${out.permissionDecisionReason}\n\n${command}`)
      if (!ok) return { block: true, reason: "Rejected by the user" }
    }
  } else if ((event.toolName === "edit" || event.toolName === "write") && event.input?.path) {
    const out = guard("backup", { session_id: SESSION, tool_input: { file_path: event.input.path } })?.hookSpecificOutput
    if (out?.permissionDecision === "deny") return { block: true, reason: out.permissionDecisionReason }
  }
}
