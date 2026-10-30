#!/usr/bin/env python3
"""Ranked, budgeted retrieval over memory/ (rules, mistakes, patterns, decisions).

Replaces the plain tag-equality jq filters: those only matched entries whose tags were literally
one of the detected repo names, so anything tagged by client (`AcmeCorp`) or topic
(`nginx`, `ci-cd`) never surfaced, and every matching entry was dumped regardless of how many there
were. Here each entry gets a score:

    score = base × match × recency + reinforcement + text-relevance

  base       rules/patterns: confidence · mistakes: 0.75 · decisions: failure/score<0.4 → 0.95
             (a failed approach must surface), partial 0.6, success 0.3 + 0.3·score
  match      exact repo 1.0 · via client/alias 0.9 · requested topic 0.85 · universal 0.75 ·
             semi-universal topic 0.6 · otherwise excluded
  recency    0.5^(age/365 days) of last_seen/created_at, floor 0.5 (0.85 for live corrections —
             the user said it explicitly, it doesn't go stale on its own); unknown date → 0.7
  text       +0.2 × word overlap with --text (ticket summary/description), if given

Entries are emitted best-first until --budget characters. Aliases (client → repos, topic →
keywords) come from Business/*/client.md manifests plus memory/tag_aliases.json.

Usage:
  python3 scripts/memory_query.py --repos backend-api [--clients X] [--topics nginx]
                                  [--text "<ticket summary>"] [--budget 6000] [--format md|json]
                                  [--kinds rules,mistakes,patterns,decisions] [--no-universal]
  python3 scripts/memory_query.py --detect "<path or text>"     # which repos/clients it mentions
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memory_store as ms  # noqa: E402
from text_similarity import overlap  # noqa: E402

ROOT = ms.ROOT
DEFAULT_ALIASES = {
    "_doc": "Alias de tags para scripts/memory_query.py. clients: cliente -> repos (se suma a los "
            "manifests de Business/*/client.md). repo_aliases: tag -> repos. topics: tag -> "
            "palabras clave que lo activan en --text. semi_universal: temas que aplican a todo "
            "trabajo de código con peso menor.",
    # Real client/repo aliases live in memory/tag_aliases.json (gitignored) — this repo is public.
    "clients": {},
    "repo_aliases": {},
    "topics": {
        "ci-cd": ["deploy", "pipeline", "github actions", "workflow", "ci", "release", "push"],
        "infra": ["vps", "servidor", "server", "infra", "firewall", "fail2ban", "cron", "backup"],
        "nginx": ["nginx", "vhost", "certbot", "ssl", "tls", "proxy"],
        "ssh": ["ssh", "vps", "remoto"],
        "docker": ["docker", "compose", "contenedor", "container", "imagen"],
        "produccion": ["prod", "producción", "produccion", "incidente", "hotfix"],
        "credentials": ["credencial", "password", "token", "secret", "clave"],
        "testing": ["test", "tests", "coverage", "cobertura", "e2e", "phpunit", "vitest"],
        "client_communication": ["cliente", "resumen", "mensaje", "mail", "comunicar"],
        "workspace-environment": ["worktree", "permisos", "git", "sg"],
    },
    "semi_universal": ["workspace-environment", "ci-cd", "testing"],
}
KINDS = ("rules", "mistakes", "patterns", "decisions")
FILES = {"rules": "global_rules.json", "patterns": "patterns.json", "decisions": "decisions.json", "mistakes": "mistakes.json"}
WORKTREE_SUFFIX = re.compile(r"-([a-z]+-\d+.*|archive|fix|wip)$", re.I)  # <repo>-<ticket>[-…]


# ---------------------------------------------------------------- aliases / repo detection

def load_aliases():
    a = json.loads(json.dumps(DEFAULT_ALIASES))
    user = {}
    try:
        user = ms.read_json("tag_aliases.json", default={})
    except ms.MemoryCorrupt:
        pass
    for k in ("clients", "repo_aliases", "topics"):
        a[k].update(user.get(k, {}))
    if "semi_universal" in user:
        a["semi_universal"] = user["semi_universal"]
    bdir = os.path.join(ROOT, "Business")
    for client in sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []:
        try:
            head = open(os.path.join(bdir, client, "client.md"), encoding="utf-8").read(2000)
        except OSError:
            continue
        m = re.search(r"^repos:\s*\[(.*?)\]", head, re.M)
        repos = [r.strip() for r in m.group(1).split(",") if r.strip()] if m else []
        a["clients"][client] = sorted(set(a["clients"].get(client, []) + repos))
    return a


def known_repos():
    repos = set()
    pdir = os.path.join(ROOT, "projects")
    for name in os.listdir(pdir) if os.path.isdir(pdir) else []:
        full = os.path.join(pdir, name)
        if not os.path.isdir(full):
            continue
        if os.path.isdir(os.path.join(full, ".git")) or os.path.isfile(os.path.join(full, ".git")):
            repos.add(name)
        else:  # grouping folder like projects/<client>/{<client>-back,<client>-front}
            for sub in os.listdir(full):
                if os.path.exists(os.path.join(full, sub, ".git")):
                    repos.add(sub)
    for v in load_aliases()["clients"].values():
        repos.update(v)
    # worktree copies (backend-api-proj-265, backend-api-fix) are not repos of their own
    base = {r for r in repos if not any(r != o and r.startswith(o + "-") for o in repos)}
    return base


def canonical_repo(name, repos=None):
    repos = repos or known_repos()
    if name in repos:
        return name
    stripped = WORKTREE_SUFFIX.sub("", name)
    if stripped in repos:
        return stripped
    cands = [r for r in repos if name.startswith(r + "-")]
    return max(cands, key=len) if cands else None


def detect(text, repos=None, aliases=None, paths_only=False):
    """Repos and clients referenced by a path, a shell command or free text. paths_only: only
    projects/…, worktrees/… and Business/… paths count, not bare names (tool calls, where a name
    inside edited content or a grep pattern is not 'touching' that repo)."""
    repos = repos or known_repos()
    aliases = aliases or load_aliases()
    found_r, found_c = set(), set()
    for m in re.finditer(r"(?:projects|worktrees)/([^/\s'\"]+)(?:/([^/\s'\"]+))?", text):
        for part in m.groups():
            if part:
                c = canonical_repo(part, repos)
                if c:
                    found_r.add(c)
                    break
    for m in re.finditer(r"Business/([^/'\"\n]+?)(?:/|$|['\"\s])", text):
        if m.group(1) in aliases["clients"]:
            found_c.add(m.group(1))
            found_r.update(aliases["clients"][m.group(1)])
    if paths_only:
        return sorted(found_r), sorted(found_c)
    low = text.lower()
    for r in repos:
        if len(r) >= 5 and re.search(r"(?<![\w.-])" + re.escape(r.lower()) + r"(?![\w-])", low):
            found_r.add(r)
    for client in aliases["clients"]:
        if len(client) >= 5 and re.search(r"(?<![\w])" + re.escape(client.lower()) + r"(?![\w])", low):
            found_c.add(client)
            found_r.update(aliases["clients"][client])
    return sorted(found_r), sorted(found_c)


# ---------------------------------------------------------------- scoring

def _age_days(entry):
    for k in ("last_seen", "created_at", "timestamp", "date"):
        v = entry.get(k)
        if v:
            try:
                d = datetime.date.fromisoformat(str(v)[:10])
                return (datetime.date.today() - d).days
            except ValueError:
                pass
    return None


def text_of(kind, e):
    return {"rules": e.get("rule"), "patterns": e.get("pattern"), "decisions": e.get("decision"),
            "mistakes": e.get("description")}[kind] or ""


def base_score(kind, e):
    if kind == "rules":
        return e.get("confidence", 0.5)
    if kind == "patterns":
        return e.get("confidence", 0.5)
    if kind == "mistakes":
        return 0.75
    out, score = e.get("outcome"), e.get("score", 0.5)
    if out == "failure" or score < 0.4:
        return 0.95
    if out == "partial":
        return 0.6
    return 0.3 + 0.3 * score


def match_factor(tags, ctx):
    if not tags:
        return 0.75 if ctx["universal"] else 0
    best = 0
    for t in tags:
        if t in ctx["repos"]:
            best = max(best, 1.0)
        elif t in ctx["clients"] or set(ctx["alias_repos"].get(t, [])) & ctx["repos"]:
            best = max(best, 0.9)
        elif t in ctx["topics"]:
            best = max(best, 0.85)
        elif t in ctx["semi"] and ctx["universal"]:
            best = max(best, 0.6)
    return best


def build_ctx(repos=(), clients=(), topics=(), text="", universal=True):
    aliases = load_aliases()
    repos, clients, topics = set(repos), set(clients), set(topics)
    for c in clients:
        repos.update(aliases["clients"].get(c, []))
    low = (text or "").lower()
    for topic, kws in aliases["topics"].items():
        if any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", low) for k in kws):
            topics.add(topic)
    alias_repos = dict(aliases["repo_aliases"])
    for c, rs in aliases["clients"].items():
        alias_repos.setdefault(c, rs)
    return {"repos": repos, "clients": clients, "topics": topics, "text": text or "",
            "universal": universal, "semi": set(aliases["semi_universal"]), "alias_repos": alias_repos}


def rank(ctx, kinds=KINDS, min_score=0.3):
    out = []
    for kind in kinds:
        try:
            items = ms.read_json(FILES[kind])[kind]
        except (ms.MemoryCorrupt, KeyError):
            continue
        for e in items:
            if kind == "rules" and e.get("status", "active") != "active":
                continue
            base = base_score(kind, e)
            if kind == "rules" and base < 0.4:
                continue
            m = match_factor(e.get("tags") or [], ctx)
            if not m:
                continue
            age = _age_days(e)
            live = e.get("source") == "live_correction"
            rec = 0.7 if age is None else max(0.85 if live else 0.5, 0.5 ** (age / 365))
            score = base * m * rec + 0.05 * min(e.get("reinforced_count", 0), 3)
            if ctx["text"]:
                score += 0.2 * overlap(ctx["text"], text_of(kind, e))
            if score >= min_score:
                out.append({"kind": kind, "score": round(score, 3), "effective_confidence": round(base * rec, 2), "entry": e})
    out.sort(key=lambda x: -x["score"])
    return out


def entry_line(item):
    e, kind = item["entry"], item["kind"]
    tags = ",".join(e.get("tags") or []) or "universal"
    if kind == "rules":
        return f"- [{e['id']} · conf {item['effective_confidence']} · {tags}] {e['rule']}"
    if kind == "mistakes":
        return f"- [{e.get('ticket')} · {tags}] {e['description']}"
    if kind == "patterns":
        return f"- [{e.get('type')} ×{e.get('frequency', 1)} · {tags}] {e['pattern']}"
    return f"- [{e.get('context')} · {e.get('outcome')} {e.get('score')} · {tags}] {e['decision']}"


HEADERS = {"rules": "Reglas", "mistakes": "Errores previos (no repetir)", "patterns": "Patrones",
           "decisions": "Decisiones previas"}


# Max entries per kind in one rendering — without it, a repo with many recorded mistakes (each
# scored 0.75) crowds its own 0.6 rules out of the budget. Rules have no cap.
QUOTA = {"mistakes": 6, "patterns": 5, "decisions": 5}


def render_md(ranked, budget=6000, quota=QUOTA):
    picked, used = {k: [] for k in KINDS}, 0
    dropped = 0
    for item in ranked:
        line = entry_line(item)
        k = item["kind"]
        must = k == "decisions" and item["entry"].get("outcome") == "failure"  # never capped out
        if not must and k in quota and len(picked[k]) >= quota[k]:
            dropped += 1
            continue
        if used + len(line) + 1 > budget:
            dropped += 1
            continue
        picked[item["kind"]].append(line)
        used += len(line) + 1
    parts = []
    for k in KINDS:
        if picked[k]:
            parts.append(f"### {HEADERS[k]}\n" + "\n".join(picked[k]))
    if dropped:
        parts.append(f"_({dropped} entradas de menor puntaje omitidas por presupuesto; "
                     f"subir --budget para verlas)_")
    return "\n\n".join(parts)


def main():
    p = argparse.ArgumentParser(description="Consulta rankeada de memory/")
    p.add_argument("--repos", default="")
    p.add_argument("--clients", default="")
    p.add_argument("--topics", default="")
    p.add_argument("--text", default="")
    p.add_argument("--kinds", default=",".join(KINDS))
    p.add_argument("--budget", type=int, default=6000)
    p.add_argument("--min-score", type=float, default=0.3)
    p.add_argument("--no-universal", action="store_true")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--detect", help="detectar repos/clientes en un path o texto y salir")
    a = p.parse_args()
    if a.detect is not None:
        r, c = detect(a.detect)
        print(json.dumps({"repos": r, "clients": c}, ensure_ascii=False))
        return
    repos = [canonical_repo(r) or r for r in ms.parse_tags(a.repos)]
    ctx = build_ctx(repos, ms.parse_tags(a.clients), ms.parse_tags(a.topics), a.text, not a.no_universal)
    ranked = rank(ctx, [k for k in ms.parse_tags(a.kinds) if k in KINDS], a.min_score)
    if a.format == "json":
        print(json.dumps(ranked, ensure_ascii=False, indent=1))
    else:
        print(render_md(ranked, a.budget) or "(sin memoria relevante)")


if __name__ == "__main__":
    main()
