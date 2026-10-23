// agent-harness guards for Pi, installed by bin/harness (edit core/pi/agent-harness.ts).
// Runs the same harness_guards.py as Claude Code. "ask" decisions become a Pi confirmation;
// without a UI (print mode) they are blocked. Any error in the guard fails open.
import { spawnSync } from "node:child_process"

const PYTHON = "{python}"
const HOOKS = "{claude_hooks}"
const SESSION = `pi${Date.now()}` // one backup per file per Pi process

function guard(mode: string, payload: object) {
  const result = spawnSync(PYTHON, [`${HOOKS}/harness_guards.py`, mode], {
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

export default function (pi: any) {
  pi.on("tool_call", async (event: any, ctx: any) => {
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
      guard("backup", { session_id: SESSION, tool_input: { file_path: event.input.path } })
    }
  })
}
