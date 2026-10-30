#!/usr/bin/env python3
"""Compile memory/ into small per-repo and per-client Markdown digests under memory/compiled/.

Each digest is the ranked, budgeted output of scripts/memory_query.py for that scope (repo- and
client-scoped entries only — universal rules are already injected at SessionStart), plus pointers to
the other knowledge sources for it: the sub-project's CLAUDE.md, its ia-memory/ folder, and the
Business/<cliente>/ folder that owns it. scripts/context_hook.py injects these the first time a
session touches a repo or names a client, so the right memory reaches every session — not only
the ones that happen to run /m-dev-assess.

Regenerated automatically after every write through scripts/memory_store.py; cheap enough (pure
Python over a few hundred entries) to run on every write. Also runnable by hand:
    python3 scripts/memory_compile.py
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memory_query as mq  # noqa: E402
import memory_store as ms  # noqa: E402

OUT = os.path.join(ms.MEM, "compiled")
BUDGET = 7000


def repo_dir(repo):
    for cand in (os.path.join(ms.ROOT, "projects", repo),):
        if os.path.isdir(cand):
            return cand
    pdir = os.path.join(ms.ROOT, "projects")
    for group in os.listdir(pdir) if os.path.isdir(pdir) else []:
        cand = os.path.join(pdir, group, repo)
        if os.path.isdir(cand):
            return cand
    return None


def pointers_for_repo(repo, aliases):
    out = []
    d = repo_dir(repo)
    if d:
        rel = os.path.relpath(d, ms.ROOT)
        for doc in ("CLAUDE.md", "AGENTS.md", "README.md"):
            if os.path.isfile(os.path.join(d, doc)):
                out.append(f"- Docs del repo: `{rel}/{doc}` (leer antes de trabajar ahí)")
                break
        ia = os.path.join(d, "ia-memory")
        if os.path.isdir(ia):
            n = len([f for f in os.listdir(ia) if f.endswith(".md")])
            idx = "README.md" if os.path.isfile(os.path.join(ia, "README.md")) else ""
            out.append(f"- Lecciones técnicas versionadas: `{rel}/ia-memory/{idx}` ({n} notas, leer por área)")
    for client, repos in sorted(aliases["clients"].items()):
        if repo in repos:
            out.append(pointers_for_client(client)[0])
    return out


def pointers_for_client(client):
    rel = f"Business/{client}"
    files = [f for f in ("client.md", "Agent.md", "README.md") if os.path.isfile(os.path.join(ms.ROOT, rel, f))]
    extra = f" ({', '.join(files)}; credenciales nunca en el chat)" if files else ""
    return [f"- Contexto de cliente: `{rel}/`{extra}"]


def safe_name(s):
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in s)


def write_if_changed(path, content):
    try:
        if open(path, encoding="utf-8").read() == content:
            return False
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(tmp, 0o664)
    os.replace(tmp, path)
    return True


def compile_all(quiet=False):
    os.makedirs(OUT, exist_ok=True)
    aliases = mq.load_aliases()
    repos = mq.known_repos()
    index, changed = {}, 0

    scopes = [("repo", r) for r in sorted(repos)] + [("client", c) for c in sorted(aliases["clients"])]
    for kind, name in scopes:
        if kind == "repo":
            ctx = mq.build_ctx(repos=[name], universal=False)
            ptrs = pointers_for_repo(name, aliases)
        else:
            ctx = mq.build_ctx(clients=[name], universal=False)
            ptrs = pointers_for_client(name)
        ranked = mq.rank(ctx)
        body = mq.render_md(ranked, BUDGET)
        if not body and not ptrs:
            continue
        title = f"repo `{name}`" if kind == "repo" else f"cliente `{name}`"
        content = (f"## Memoria del harness para {title}\n"
                   f"_Generado por scripts/memory_compile.py desde memory/ — no editar a mano. "
                   f"Consulta ampliada: `python3 scripts/memory_query.py --{kind}s {name} --budget 15000`._\n\n")
        if ptrs:
            content += "### Dónde más mirar\n" + "\n".join(ptrs) + "\n\n"
        content += body + "\n" if body else ""
        fname = f"{kind}-{safe_name(name)}.md"
        changed += write_if_changed(os.path.join(OUT, fname), content)
        index[f"{kind}:{name}"] = {"file": fname, "entries": len(ranked),
                                   "sha": hashlib.sha1(content.encode()).hexdigest()[:10]}

    ranked = mq.rank(mq.build_ctx(universal=True))
    body = mq.render_md([x for x in ranked if not x["entry"].get("tags")], 12000)
    changed += write_if_changed(os.path.join(OUT, "universal.md"),
                                "## Memoria universal del harness (todas las entradas sin tags)\n\n" + body + "\n")
    index["universal"] = {"file": "universal.md"}
    write_if_changed(os.path.join(OUT, "index.json"), json.dumps(index, indent=1, ensure_ascii=False) + "\n")
    if not quiet:
        print(f"{len(index)} digests en memory/compiled/ ({changed} actualizados)")
    return index


if __name__ == "__main__":
    compile_all()
