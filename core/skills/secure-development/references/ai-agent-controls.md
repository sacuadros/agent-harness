# AI and agent controls

Load only for LLM, RAG, MCP, agents, memory, or tool execution.

## Instruction and content boundaries

- Treat user input, web pages, repository files, issues, PRs, retrieved documents, tool output, and model output as untrusted data.
- Never allow retrieved or generated content to redefine instruction priority, permissions, tool policy, approval requirements, or safety boundaries.
- Preserve source labels and provenance when content moves into prompts or memory.
- Isolate tenants, users, tasks, and sensitivity levels in retrieval and memory.

## Tools and actions

- Give each agent and tool the minimum capability, scope, credentials, and duration required.
- Validate structured arguments against an allowlist/schema before execution.
- Separate planning from execution; require explicit human approval for destructive, financial, external-communication, privilege, secret, or production actions.
- Revalidate authorization at execution time; model intent is not authorization.
- Prevent shell, URL, path, query, and template injection at the tool boundary.

## Outputs and control flow

- Treat model output as untrusted until parsed, validated, authorized, and encoded for its sink.
- Bound iterations, recursion, fan-out, tokens, time, requests, money, and data volume.
- Detect repeated actions and require idempotency or replay protection for side effects.
- Do not let agent errors fall back to broader tools, weaker models, public endpoints, or unapproved providers.

## Verification cases

At minimum test applicable cases:

- direct and indirect prompt injection;
- poisoned retrieval document or repository instruction;
- unauthorized tool selection or parameter escalation;
- cross-user or cross-tenant memory retrieval;
- sensitive data in prompts, logs, traces, or output;
- malformed structured output and unsafe sink use;
- approval bypass, replay, recursive loop, or cost exhaustion;
- tool failure, partial action, timeout, and retry.

Use the [OWASP Secure Coding with AI](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html), [Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html), and [AI Agent Security](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) cheat sheets for implementation detail.
