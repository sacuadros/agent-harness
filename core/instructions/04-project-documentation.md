## Project Documentation

- Keep durable team conventions in version-controlled repository documentation, not only in chat or personal memory.
- Keep the nearest applicable `AGENTS.md` compact. When a repository has detailed docs, maintain a `## Documentation map` that points to relevant areas or files so agents load only what the task needs.
- Do not create a documentation tree for routine work. Promote a convention only when the user explicitly invokes `{{cmd}}promote-project-convention` or directly asks to document it.
- Treat stable conventions as documentation, not as implementation plans or slice backlogs. `.slices/` files are temporary working state, never documentation.
