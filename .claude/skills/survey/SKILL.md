---
name: survey
description: Run an ant-farm survey on a contested question via the dynamic workflow. Use when the user asks to survey a question, run ant-farm, or map an argument space.
---

# Run a survey

Requirements: Claude Code >= 2.1.154 with workflows enabled, `uv` installed,
repo dependencies synced (`uv sync`).

1. Generate the agent output schemas (they are pydantic-derived; never
   hand-write them):

   ```bash
   uv run python -m antfarm schemas
   ```

2. Invoke the Workflow tool with the parsed JSON:

   - `scriptPath`: `workflows/survey.js`
   - `args`:
     - `question` (required): the contested question, verbatim.
     - `schemas` (required): the parsed JSON object from step 1.
     - `mode`: `lean` | `default` | `saturate` (default `default`; see spec §11).
     - `corpusDir`: corpus directory (default `corpus`). One corpus per
       question - reuse the same dir to accumulate across runs (spec §8).
     - `personas` / `families`: optional overrides (mundane personas beat
       exotic ones; families rotate over opus/sonnet/haiku).
     - `stopAfter`: `sentinel` or `framing` to run phases 0-1 standalone
       (the spec's --sentinel-only / --frame-only modes).

3. On a DISSOLVE result, relay the diagnosis and replacement question to the
   user; re-run only if they adopt the replacement.

4. After the run: the map is `corpus/vault/MAP.md`, node pages sit beside it,
   keel exports are under `corpus/exports/<run>/`, and re-running the same
   question warm-starts from the accumulated corpus.
