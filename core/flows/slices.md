Build it in small vertical slices. Plan only what the next slice needs; never write a full upfront spec.
   - **Backlog.** Load the `backlog` skill yourself. The working file is `.slices/<feature>.md`; the `backlog` skill defines its layout. Mirror it to Engram (`topic_key: slices/<feature>`, `capture_prompt: false`) after each slice; on resume read Engram, then the file, and reconcile. Delete the file when the feature closes; commits keep the history.
   - **Checkpoint.** Large work has one checkpoint before building: backlog approval. After it, write each story and build every slice in order without waiting, recording decisions in the Log.
   - **Refine just in time.** Load the `story` skill for the next slice only.
   - **Build with the `pair` skill.** It holds the mechanics: one test at a time, RED before GREEN.
   - Repositories that already contain `openspec/` keep it as project history; continue an OpenSpec change there only when the user asks.
