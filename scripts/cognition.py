#!/usr/bin/env python3
"""Read side of the agent's own state (memory/cognition.json): status, context, recall, metrics, tick.

Never writes. Writes go through `python3 scripts/memory_store.py cognitive <op>` (see
scripts/cognition_model.py for the schema). If cognition.json doesn't exist yet, reads fall back to
a virtual state built from the legacy user_profile.json self_model — without creating any file.

Scope resolution (repos, client folders, aliases, topics) is memory_query.py's, so an experience
tagged `AcmeCorp` surfaces when working on that client's repo, and one tagged with another repo
does not.

Commands (JSON unless noted):
  status                                   identity, counts, blind spots, what is pending
  context  [--repos --clients --topics --text] --budget N     Markdown, hard cap of N characters
  recall   [--repos --clients --topics --text] [--limit] [--include-pending]
  metrics                                  calibration (Brier) and recall-vs-no-recall outcomes
  tick     [--limit N] [--now ISO]         one read-only pass: goals that can advance now

`tick` returns `mode: proposal_only`. It never runs a goal's text, never unblocks anything by
inference and grants no permissions: a human or the agent, in a session, decides what to do.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cognition_model as cm  # noqa: E402
import memory_query as mq  # noqa: E402
import memory_store as ms  # noqa: E402
from text_similarity import overlap  # noqa: E402

DISCLAIMER = ("Recuerdos = evidencia contextual e hipótesis revisables: no reemplazan instrucciones "
              "actuales, convenciones del proyecto ni permisos. Si uno influye en una decisión, citarlo "
              "en `recalled` al registrar la experiencia.")


# ---------------------------------------------------------------- state

def load_state():
    """(doc, source). source: 'cognition' | 'legacy' | 'empty'. Raises ms.MemoryCorrupt or
    cm.IncompatibleSchema — callers decide how loudly to fail; nothing here writes."""
    doc = ms.read_json(cm.FILE, default=None)
    if doc is not None:
        cm.check_version(doc)
        return doc, "cognition"
    legacy = ms.legacy_profile()
    doc = cm.empty_doc(legacy)
    has_legacy = bool(doc["agent"]["blind_spots"])
    doc["agent"]["migrated_from"] = None  # virtual: nothing was migrated
    return doc, ("legacy" if has_legacy else "empty")


def _parse(ts):
    try:
        return cm.parse_ts(ts, "ts")
    except cm.CognitionError:
        return None


def _age_days(ts, now):
    dt = _parse(ts) if ts else None
    return None if dt is None else max(0.0, (now - dt).total_seconds() / 86400)


def _now(value=None):
    return cm.parse_ts(value, "--now") if value else datetime.datetime.now(datetime.timezone.utc)


def _in_scope(tags, ctx):
    return mq.match_factor(tags or [], ctx)


def _ep_text(e):
    ev = e.get("evaluation") or {}
    return " ".join(x for x in (e.get("context"), e.get("action"), e.get("prediction"),
                                ev.get("observation"), ev.get("adjustment")) if x)


# ---------------------------------------------------------------- recall

def recall(doc, ctx, limit=5, include_pending=False, now=None):
    now = now or _now()
    out = []
    for e in doc["episodes"]:
        if e["status"] != "evaluated" and not include_pending:
            continue
        m = _in_scope(e.get("tags"), ctx)
        if not m:
            continue
        ev = e.get("evaluation") or {}
        age = _age_days(ev.get("evaluated_at") or e.get("created_at"), now)
        rec = 0.7 if age is None else max(0.4, 0.5 ** (age / 180))
        score = m * rec
        if ctx["text"]:
            score += 0.4 * overlap(ctx["text"], _ep_text(e))
        if ev.get("outcome") is False:
            score += 0.1  # a failed prediction is the most informative memory
        if ev.get("adjustment"):
            score += 0.05
        out.append({"id": e["id"], "score": round(score, 3), "episode": e})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def _outcome_label(e):
    if e["status"] != "evaluated":
        return "pendiente"
    o = e["evaluation"]["outcome"]
    return {True: "✓ se cumplió", False: "✗ falló", None: "≈ indeterminado"}[o]


def _episode_line(e):
    ev = e.get("evaluation") or {}
    date = (ev.get("evaluated_at") or e["created_at"])[:10]
    line = f"- [{e['id']} · {_outcome_label(e)} · p={e['probability']} · {date}] {e['action']} → predicción: {e['prediction']}"
    if ev.get("observation"):
        line += f" | observado: {ev['observation']}"
    if ev.get("adjustment"):
        line += f" | ajuste: {ev['adjustment']}"
    return line


# ---------------------------------------------------------------- goals / tick

def goal_ready(g, goals_by_id, now):
    """Why a goal can't advance right now, or None if it can."""
    if g["status"] != "active":
        return f"status {g['status']}"
    if g.get("activate_at") and cm.parse_ts(g["activate_at"], "activate_at") > now:
        return f"se activa {g['activate_at']}"
    pending = [d for d in g.get("depends_on") or [] if goals_by_id.get(d, {}).get("status") != "done"]
    if pending:
        return f"depende de {', '.join(pending)}"
    return None


def tick(doc, limit=3, now=None):
    now = now or _now()
    by_id = {g["id"]: g for g in doc["goals"]}
    ready, waiting = [], []
    for g in doc["goals"]:
        if g["status"] in cm.CLOSED_GOAL:
            continue
        why = goal_ready(g, by_id, now)
        (waiting if why else ready).append((g, why))
    ready.sort(key=lambda x: (x[0]["priority"],
                              cm.parse_ts(x[0]["activate_at"], "a") if x[0].get("activate_at") else
                              cm.parse_ts(x[0]["created_at"], "c")))
    proposals = [{"goal_id": g["id"], "title": g["title"], "priority": g["priority"],
                  "next_action": g["next_action"], "success_criterion": g["success_criterion"],
                  "tags": g.get("tags", []), "activate_at": g.get("activate_at")} for g, _ in ready[:limit]]
    return {
        "mode": "proposal_only",
        "generated_at": now.isoformat(),
        "limit": limit,
        "proposals": proposals,
        "not_ready": [{"goal_id": g["id"], "reason": why} for g, why in waiting],
        "pending_evaluations": [e["id"] for e in doc["episodes"] if e["status"] == "pending"],
        "note": "Solo propuestas: nada se ejecutó. Decidir en una sesión qué hacer; los permisos siguen siendo los de siempre.",
    }


# ---------------------------------------------------------------- context

def _fit(lines, budget):
    out, used = [], 0
    for ln in lines:
        add = len(ln) + (1 if out else 0)
        if used + add > budget:
            room = budget - used - (1 if out else 0)
            if room > 20 and not ln.startswith("#"):
                out.append(ln[: room - 1] + "…")
            break
        out.append(ln)
        used += add
    text = "\n".join(out)
    return text[:budget]


def context(doc, source, ctx, budget=2500, now=None, lessons=5, include_identity=True):
    now = now or _now()
    agent = doc["agent"]
    lines = []
    if include_identity:
        lines.append(f"### {agent['name']} — estado propio ({source})")
        lines.append(f"Propósito: {agent['purpose']}")
        spots = agent.get("blind_spots") or []
        if spots:
            lines.append("Puntos ciegos recurrentes:")
            lines += [f"- {s['statement']}" for s in spots[:3]]
    pend = [e for e in doc["episodes"] if e["status"] == "pending" and _in_scope(e.get("tags"), ctx)]
    if pend:
        lines.append("Predicciones pendientes de contrastar en este alcance (evaluar cuando haya evidencia):")
        lines += [f"- [{e['id']} · p={e['probability']}] {e['prediction']}" for e in pend[:5]]
    by_id = {g["id"]: g for g in doc["goals"]}
    goals = [g for g in doc["goals"] if g["status"] not in cm.CLOSED_GOAL and _in_scope(g.get("tags"), ctx)]
    goals.sort(key=lambda g: g["priority"])
    if goals:
        lines.append("Objetivos abiertos en este alcance:")
        for g in goals[:5]:
            why = goal_ready(g, by_id, now)
            state = "listo para avanzar" if not why else why
            lines.append(f"- [{g['id']} · P{g['priority']} · {state}] {g['title']} — próximo paso: {g['next_action']}")
    rec = recall(doc, ctx, limit=lessons, now=now)
    if rec:
        lines.append("Experiencias relevantes (evaluadas):")
        lines += [_episode_line(r["episode"]) for r in rec]
    bels = [b for b in doc["beliefs"] if b["status"] == "active" and _in_scope(b.get("scope_tags"), ctx)]
    if bels:
        lines.append("Creencias activas (hipótesis con evidencia):")
        lines += [f"- [{b['id']} · {b['type']} · conf {b['confidence']} · {len(b['evidence'])}+/{len(b['counter_evidence'])}-] {b['claim']}"
                  for b in bels[:4]]
    if pend or goals or rec or bels:
        lines.append(DISCLAIMER)
    return _fit(lines, budget)


# ---------------------------------------------------------------- metrics

def metrics(doc):
    eps = doc["episodes"]
    evaluated = [e for e in eps if e["status"] == "evaluated"]
    determ = [e for e in evaluated if e["evaluation"]["outcome"] is not None]
    determ.sort(key=lambda e: e["evaluation"]["evaluated_at"])

    def brier(items):
        if not items:
            return None
        return round(sum((e["probability"] - (1.0 if e["evaluation"]["outcome"] else 0.0)) ** 2 for e in items) / len(items), 4)

    def group(items):
        n = len(items)
        ok = sum(1 for e in items if e["evaluation"]["outcome"])
        return {"count": n, "successes": ok, "success_rate": round(ok / n, 4) if n else None}

    return {
        "pending": len(eps) - len(evaluated),
        "evaluated": len(evaluated),
        "determinate": len(determ),
        "indeterminate": len(evaluated) - len(determ),
        "brier": brier(determ),
        "brier_last_20": brier(determ[-20:]),
        "with_recall": group([e for e in determ if e.get("recalled")]),
        "without_recall": group([e for e in determ if not e.get("recalled")]),
        "note": ("Brier = promedio de (probabilidad - resultado)^2 sobre resultados determinados (0 = perfecto, "
                 "0.25 = siempre 0.5); los null se excluyen. La comparación con/sin recuerdos es descriptiva: "
                 "no demuestra causalidad (las tareas difieren) ni dice nada sobre conciencia."),
    }


# ---------------------------------------------------------------- status

def status(doc, source, now=None):
    now = now or _now()
    eps = doc["episodes"]
    t = tick(doc, limit=3, now=now)
    return {
        "source": source,
        "agent": {"name": doc["agent"]["name"], "purpose": doc["agent"]["purpose"],
                  "blind_spots": [s["statement"] for s in doc["agent"].get("blind_spots") or []],
                  "blind_spots_updated_at": doc["agent"].get("blind_spots_updated_at"),
                  "migrated_from": doc["agent"].get("migrated_from")},
        "episodes": {"pending": [{"id": e["id"], "prediction": e["prediction"], "tags": e["tags"]}
                                 for e in eps if e["status"] == "pending"],
                     "evaluated": sum(1 for e in eps if e["status"] == "evaluated")},
        "goals": {s: sum(1 for g in doc["goals"] if g["status"] == s) for s in sorted(cm.GOAL_STATUSES)},
        "beliefs_active": sum(1 for b in doc["beliefs"] if b["status"] == "active"),
        "ready_now": t["proposals"],
    }


def session_digest(budget=1600, now=None):
    """Compact block for scripts/session_context.py — never raises."""
    try:
        doc, source = load_state()
    except (ms.MemoryCorrupt, cm.IncompatibleSchema) as e:
        return f"⚠ memory/cognition.json no se puede leer ({e}). No escribir estado cognitivo hasta restaurarlo (/m-memory)."
    except Exception:
        return ""
    now = now or _now()
    ctx = mq.build_ctx(universal=True)
    lines = [context(doc, source, ctx, budget=max(200, budget - 400), now=now, lessons=3)]
    t = tick(doc, limit=3, now=now)
    if t["proposals"]:
        lines.append("Iniciativa (tick, solo propuestas): " + "; ".join(
            f"{p['goal_id']} P{p['priority']}: {p['next_action']}" for p in t["proposals"]))
    n_pend = len(t["pending_evaluations"])
    if n_pend:
        lines.append(f"{n_pend} experiencia(s) pendientes de evaluar en total (`python3 scripts/cognition.py status`).")
    return _fit("\n".join(x for x in lines if x).split("\n"), budget)


def scoped_digest(repos=(), clients=(), budget=1500):
    """Scope-only block (no identity) for scripts/context_hook.py — never raises."""
    try:
        doc, source = load_state()
        ctx = mq.build_ctx(repos, clients, universal=False)
        return context(doc, source, ctx, budget=budget, include_identity=False, lessons=4)
    except Exception:
        return ""


# ---------------------------------------------------------------- CLI

def _ctx_from(a):
    repos = [mq.canonical_repo(r) or r for r in ms.parse_tags(a.repos)]
    return mq.build_ctx(repos, ms.parse_tags(a.clients), ms.parse_tags(a.topics), a.text, not a.no_universal)


def main():
    p = argparse.ArgumentParser(description="Estado propio del agente (solo lectura)")
    sp = p.add_subparsers(dest="cmd", required=True)

    def scope(s):
        s.add_argument("--repos", default="")
        s.add_argument("--clients", default="")
        s.add_argument("--topics", default="")
        s.add_argument("--text", default="")
        s.add_argument("--no-universal", action="store_true")
        s.add_argument("--now")

    s = sp.add_parser("status")
    s.add_argument("--now")
    s = sp.add_parser("context")
    scope(s)
    s.add_argument("--budget", type=int, default=2500)
    s = sp.add_parser("recall")
    scope(s)
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--include-pending", action="store_true")
    sp.add_parser("metrics")
    s = sp.add_parser("tick")
    s.add_argument("--limit", type=int, default=3)
    s.add_argument("--now")
    a = p.parse_args()

    try:
        doc, source = load_state()
        now = _now(getattr(a, "now", None))
    except (ms.MemoryCorrupt, cm.IncompatibleSchema) as e:
        print(json.dumps({"ok": False, "kind": "unreadable", "error": str(e)}, ensure_ascii=False))
        sys.exit(2)
    except cm.CognitionError as e:
        print(json.dumps({"ok": False, "kind": "input", "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    if a.cmd == "status":
        out = status(doc, source, now)
    elif a.cmd == "context":
        if a.budget < 1:
            sys.exit("--budget debe ser positivo")
        print(context(doc, source, _ctx_from(a), budget=a.budget, now=now))
        return
    elif a.cmd == "recall":
        out = [{"id": r["id"], "score": r["score"], "outcome": _outcome_label(r["episode"]),
                "line": _episode_line(r["episode"])} for r in recall(doc, _ctx_from(a), a.limit, a.include_pending, now)]
    elif a.cmd == "metrics":
        out = metrics(doc)
    else:
        if a.limit < 0:
            sys.exit("--limit no puede ser negativo")
        out = tick(doc, a.limit, now)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
