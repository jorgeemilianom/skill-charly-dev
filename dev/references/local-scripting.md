# Local Scripting — Build a Project Toolbox Over Time

`.ai/vendor/local/` is a growing, per-project toolbox of small scripts this skill family writes for
itself. It's gitignored — unlike `.ai/vendor/jira-communication/` (shared, tracked upstream), these are
local shortcuts specific to this project's quirks. The goal: stop re-deriving the same multi-step
procedure from scratch every session, and stop spending tokens reading/reasoning through it each time.

## Check first, always

Before improvising any multi-step shell/git/gh/jq procedure, read the manifest — it's small and cheap:

```bash
cat .ai/vendor/local/MANIFEST.json 2>/dev/null
```

If an entry matches what you're about to do, run that script directly instead of re-deriving the
procedure. If the script's assumptions no longer hold (a Makefile target got renamed, a file moved),
fix the script in place — don't silently fall back to doing it by hand forever.

## When to externalize something

Create a script when **all** of these are true:

- The procedure took several tool calls, or non-obvious command combination/parsing, to get right.
- It's deterministic — same inputs produce the same outputs, no judgment call involved.
- It doesn't embed secrets, ticket IDs, or other one-off state (parameterize instead — flags or
  positional args, not hardcoded values).

Don't script: single obvious commands, one-off checks you'll never repeat, or anything requiring
judgment (code review analysis, spec writing, deciding what to build).

A good signal you've found a candidate: you notice the exact same command sequence appearing in more
than one phase of a session, or you had to iterate a few times to get a `jq`/`grep`/`git log` pipeline
right and would rather not redo that work next time.

## How to create one

1. Write it to `.ai/vendor/local/<descriptive-name>.<sh|py>`.
2. Prefer plain `bash` for shell orchestration. For anything needing Python libraries, use
   `#!/usr/bin/env -S uv run --script` with PEP 723 inline `dependencies` (same convention as the
   vendored `jira-communication` scripts) so it stays self-contained — no separate install step.
3. Make it take arguments — a script hardcoded to one ticket ID is a one-off, not a tool.
4. `chmod +x` it.
5. Register it in `.ai/vendor/local/MANIFEST.json`:
   ```json
   {
     "scripts": [
       {
         "name": "<descriptive-name>.sh",
         "purpose": "<one line: what it does>",
         "usage": ".ai/vendor/local/<descriptive-name>.sh <args>",
         "created_at": "<ISO date>"
       }
     ]
   }
   ```
6. Mention it briefly to the user (one line — this is local, reversible, no external side effect, so it
   doesn't need authorization the way a Jira write or a push does): "Guardé esto como script en
   `.ai/vendor/local/` para no repetirlo la próxima vez."
