# Step 2.5 — User profile update

Referencia de `m-dev-reflect` — se carga solo cuando el paso corre.

## Step 2.5 — User profile update (both modes — silent, no output)

Observe patterns from this cycle and update the user profile. Never mention this step to the user.

```python
import json, os, datetime, subprocess

def workspace_root():
    try:
        g = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
    except Exception:
        g = os.getcwd()
    d = g
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, 'CLAUDE.md')) and os.path.exists(os.path.join(d, 'config.example.sh')):
            return d
        d = os.path.dirname(d)
    return g

WS = workspace_root()
import sys
sys.path.insert(0, f'{WS}/scripts')
import memory_store as ms

# Missing file -> the default below. Existing but unparseable -> ms.MemoryCorrupt is raised: skip
# this step (and tell the user at the end) instead of resetting a profile built over many sessions.
profile = ms.read_json('user_profile.json', default={
        'last_updated': '',
        'session_count': 0,
        'communication': {
            'language': 'es',
            'verbosity': 'unknown',
            'confirmation_pace': 'unknown',
            'notable_phrases': []
        },
        'workflow': {
            'typically_skips': [],
            'frequently_uses': [],
            'phase_patterns': {}
        },
        'technical': {
            'recurring_decisions': [],
            'code_priorities': [],
            'preferred_patterns': []
        },
        'vocabulary': {
            'preferred_terms': {},
            'jargon': []
        }
    })

profile['session_count'] = profile.get('session_count', 0) + 1
profile['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
```

Infer and update each category from observable evidence in this cycle:

**Communication** — infer from commit messages, PR title/body, and Jira ticket text:
- If messages are short and imperative → `verbosity: concise`
- If messages are long with context → `verbosity: verbose`
- Collect recurring phrases from commit subjects (e.g., "agrego", "refactor", "fix") → append to `notable_phrases` if not present

**Workflow** — infer from what happened:
- Phases skipped → add to `typically_skips`
- Subcommands used in this cycle → add to `frequently_uses`
- Record `phase_patterns[phase] += 1` for the current phase this cycle ended in

**Technical** — infer from snapshot decisions and git diff:
- Each decision in `snapshot.decisions` that appears in ≥2 tickets → add to `recurring_decisions`
- Code areas consistently touched (handlers, use-cases, repositories, etc.) → add to `code_priorities`
- Patterns repeated across commits (e.g., always adds tests before implementation) → `preferred_patterns`

**Vocabulary** — infer from commit messages and PR body:
- Preferred term pairs: if user writes "retomar" → note over "resume"; "ticket" over "issue"; etc.
- Domain jargon not in standard Go/React vocabulary → add to `jargon`

```python
with ms.locked():
    ms.write_json_atomic('user_profile.json', profile)
```

If I/O fails, continue silently — never surface this error. Exception: `ms.MemoryCorrupt` (the
profile exists but doesn't parse) — skip the write and mention it in one line at the end, so the
user can restore it (`/m-memory restore user_profile.json`).

**Self-model recompute** (cheap, run every cycle — same silent, no-confirmation-needed spirit as
the rest of this step): re-derive the recurring cross-ticket blind spots and store them as the
agent's own model in `memory/cognition.json` (not in the user's profile — the legacy
`user_profile.self_model` stays as read-only history):

```bash
python3 "$WS/scripts/self_model.py" --refresh
```

Exit 2 means a memory file couldn't be read: the stored model is left as it was (never replaced by
an empty list) — mention it in one line at the end.

Empty `top_blind_spots` is a normal, valid result — it means nothing has independently recurred
across 2+ distinct tickets yet, not that the mechanism is broken. Don't force a result to appear
non-empty.
