#!/usr/bin/env python3
"""Detecta correcciones del usuario en los transcripts y mide qué reglas de memoria sirven.

Las correcciones en vivo ("no, hacelo así", "eso está mal", "te dije que…") son la mejor señal de
aprendizaje, pero hoy solo quedan si el agente las guarda en el momento. Este script recorre los
transcripts de Claude Code (~/.claude/projects/<workspace>/*.jsonl) y de Codex (~/.codex/sessions, solo
los de este workspace) y:

1. Agrega a memory/corrections/inbox.jsonl cada mensaje del usuario que parece una corrección, con el
   final del mensaje previo del agente y las reglas activas más parecidas. `/m-memory consolidate` lo
   revisa: convertir en regla, reforzar una existente o descartar.
2. Lleva memory/evidence/rule_stats.json: en cuántas sesiones se inyectó cada regla (por los ids
   `[ID · conf …]` que imprimen los hooks) y cuántas veces, en esas sesiones, hubo una corrección parecida
   a la regla (= la regla estaba en contexto y no evitó el error: reescribirla o convertirla en hook).

Incremental: recuerda hasta qué byte leyó cada transcript (memory/corrections/.state.json).
Uso: correction_miner.py [--since-days 3] [--dry-run]     (minar transcripts recientes)
     correction_miner.py session [<transcript.jsonl>]      (hook SessionEnd; transcript por stdin)
     correction_miner.py list | pending                    (revisar el inbox)
     correction_miner.py mark <ruled:ID|discarded> <id>... (cerrar entradas tras revisarlas)
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
MEM = os.path.join(WS, "memory")
COR = os.path.join(MEM, "corrections")
STATE = os.path.join(COR, ".state.json")
INBOX = os.path.join(COR, "inbox.jsonl")
STATS = os.path.join(MEM, "evidence", "rule_stats.json")
sys.path.insert(0, HERE)
from text_similarity import overlap, words  # noqa: E402

CORRECTION = re.compile(
    r"^\s*(no[,.!]|no (era|es|est[aá]|hagas|uses|toques|quiero|me gusta|funciona|anda|sirve)|eso no|"
    r"est[aá] mal|mal[,.!]|te equivocaste|equivocad|incorrect|al rev[eé]s|"
    r"te dije|ya te dije|otra vez|de nuevo (lo|te)|por qu[eé] (hiciste|cambiaste|borraste|tocaste|pusiste)|"
    r"nunca |siempre |no vuelvas|deja de|dej[aá] de|par[aá],|fren[aá]|esper[aá],|en realidad|"
    r"no (te )?(ped[ií]|dije)|eso no (era|es)|revert[ií]|deshac[eé])",
    re.IGNORECASE)
SKIP = re.compile(r"^\s*(<|\[|caveat:|/|!|```)", re.IGNORECASE)
RULE_ID = re.compile(r"\[([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-r\d+) · ")


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    json.dump(data, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def active_rules():
    d = load(os.path.join(MEM, "global_rules.json"), {"rules": []})
    return [r for r in d.get("rules", []) if r.get("status", "active") == "active"]


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") in ("text", "input_text", "output_text"))
    return ""


def parse_claude(lines):
    """→ (eventos [(rol, texto)], ids de reglas inyectadas)"""
    events, injected = [], set()
    for line in lines:
        injected.update(RULE_ID.findall(line))
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message")
        if not isinstance(m, dict) or e.get("isMeta"):
            continue
        if e.get("type") == "user" and isinstance(m.get("content"), str):
            events.append(("user", m["content"]))
        elif e.get("type") == "user" and isinstance(m.get("content"), list) and \
                all(isinstance(c, dict) and c.get("type") == "text" for c in m["content"]):
            events.append(("user", text_of(m["content"])))
        elif e.get("type") == "assistant":
            t = text_of(m.get("content"))
            if t.strip():
                events.append(("assistant", t))
    return events, injected


def parse_codex(lines):
    events, injected = [], set()
    for line in lines:
        injected.update(RULE_ID.findall(line))
        try:
            e = json.loads(line)
        except ValueError:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "response_item" and p.get("type") == "message" and p.get("role") in ("user", "assistant"):
            t = text_of(p.get("content"))
            if t.strip() and not t.lstrip().startswith("<"):
                events.append((p["role"], t))
    return events, injected


def transcripts(since_days):
    cutoff = time.time() - since_days * 86400
    proj = os.path.expanduser("~/.claude/projects/" + WS.replace("/", "-"))
    out = [("claude", p) for p in glob.glob(os.path.join(proj, "*.jsonl")) if os.path.getmtime(p) >= cutoff]
    for p in glob.glob(os.path.expanduser("~/.codex/sessions/*/*/*/*.jsonl")):
        if os.path.getmtime(p) < cutoff:
            continue
        try:
            head = open(p).readline()
        except OSError:
            continue
        # Solo sesiones de este workspace; las delegaciones (worktrees/delegate-*) no tienen usuario humano.
        if WS in head and "worktrees/delegate-" not in head:
            out.append(("codex", p))
    return out


def mine(kind, path, state, rules, stats, dry):
    size = os.path.getsize(path)
    start = state.get(path, 0)
    if size <= start:
        return []
    with open(path, errors="replace") as f:
        f.seek(start)
        lines = f.read().splitlines()
    events, injected = (parse_claude if kind == "claude" else parse_codex)(lines)
    sid = os.path.basename(path)[:-6]
    rule_words = {r["id"]: words(r["rule"]) for r in rules}
    for rid in injected:
        s = stats.setdefault(rid, {"sessions_injected": [], "violations": []})
        if sid not in s["sessions_injected"]:
            s["sessions_injected"].append(sid)
    found, prev = [], ""
    for role, text in events:
        if role == "assistant":
            prev = text
            continue
        t = text.strip()
        answered_question = prev.rstrip().endswith("?") and re.match(r"(?i)\s*no\b", t)  # "no" a una pregunta del agente
        if len(t) < 6 or len(t) > 2000 or SKIP.match(t) or not CORRECTION.search(t) or answered_question:
            prev = ""
            continue
        w = words(t + " " + prev[-400:])
        sims = sorted(((overlap(w, rw), rid) for rid, rw in rule_words.items()), reverse=True)[:3]
        similar = [{"id": rid, "score": round(sc, 2)} for sc, rid in sims if sc >= 0.12]
        violated = [x["id"] for x in similar if x["id"] in injected and x["score"] >= 0.2]
        for rid in violated:
            stats.setdefault(rid, {"sessions_injected": [], "violations": []})["violations"].append(sid)
        h = hashlib.sha1((sid + t).encode()).hexdigest()[:12]
        found.append({"id": h, "source": kind, "session": sid, "at": time.strftime("%Y-%m-%d"),
                      "user": t[:600], "agent_before": prev[-300:], "similar_rules": similar,
                      "violated_injected_rules": violated, "status": "new"})
        prev = ""
    if not dry:
        state[path] = size
    return found


def run(since_days, dry, only=None):
    state = load(STATE, {})
    stats = load(STATS, {})
    rules = active_rules()
    known = set()
    if os.path.exists(INBOX):
        known = {json.loads(l)["id"] for l in open(INBOX) if l.strip()}
    items = []
    for kind, path in ([("claude", only)] if only else transcripts(since_days)):
        items += [i for i in mine(kind, path, state, rules, stats, dry) if i["id"] not in known]
    if dry:
        for i in items:
            print(f"- [{i['source']}] {i['user'][:140]!r} similar={[s['id'] for s in i['similar_rules']]}")
        print(f"{len(items)} corrección(es) candidata(s) [dry-run]")
        return
    os.makedirs(COR, exist_ok=True)
    with open(INBOX, "a") as f:
        for i in items:
            f.write(json.dumps(i, ensure_ascii=False) + "\n")
    save(STATE, state)
    save(STATS, stats)
    print(f"correcciones: {len(items)} nueva(s) en memory/corrections/inbox.jsonl")


def pending_count():
    if not os.path.exists(INBOX):
        return 0
    return sum(1 for l in open(INBOX) if l.strip() and json.loads(l).get("status") == "new")


def cmd_list():
    if not os.path.exists(INBOX):
        return
    for l in open(INBOX):
        if l.strip():
            i = json.loads(l)
            if i.get("status") == "new":
                sim = ",".join(x["id"] for x in i.get("similar_rules", []))
                viol = " VIOLADA:" + ",".join(i["violated_injected_rules"]) if i.get("violated_injected_rules") else ""
                print(f"{i['id']} [{i['source']} {i['at']}] {i['user'][:220]!r}"
                      + (f" | antes: {i['agent_before'][-120:]!r}" if i.get("agent_before") else "")
                      + (f" | similares: {sim}" if sim else "") + viol)


def cmd_mark(ids, status):
    items = [json.loads(l) for l in open(INBOX) if l.strip()]
    hit = 0
    for i in items:
        if i["id"] in ids:
            i["status"] = status
            hit += 1
    tmp = f"{INBOX}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        for i in items:
            f.write(json.dumps(i, ensure_ascii=False) + "\n")
    os.replace(tmp, INBOX)
    print(f"{hit} marcada(s) como {status}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        return cmd_list()
    if len(sys.argv) > 3 and sys.argv[1] == "mark":
        return cmd_mark(set(sys.argv[3:]), sys.argv[2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since-days", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("cmd", nargs="?", choices=["session", "pending"])
    ap.add_argument("path", nargs="?")
    a = ap.parse_args()
    if a.cmd == "pending":
        print(pending_count())
    elif a.cmd == "session":
        # Hook SessionEnd: el transcript llega por stdin (JSON del hook) o como argumento.
        path = a.path
        if not path:
            try:
                path = json.load(sys.stdin).get("transcript_path")
            except Exception:
                path = None
        if path and os.path.exists(path):
            run(0, a.dry_run, only=path)
    else:
        run(a.since_days, a.dry_run)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
