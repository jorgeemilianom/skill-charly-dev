#!/usr/bin/env python3
"""Colector de evidencia: cierra el ciclo de aprendizaje sin depender de que el agente se acuerde.

`harvest` (cron nocturno, o a mano) junta para cada ticket reciente o con predicciones pendientes lo que
pasó afuera:
  - PRs (gh search por el id del ticket): mergeado, rondas de CHANGES_REQUESTED, commits empujados después
    de abrir el PR (retrabajo), estado del CI del último commit, PR de revert posterior.
  - Commits locales en projects/ que nombran el ticket (flujos sin PR, ej. trabajo directo en main) y
    commits que los revierten.
Guarda memory/evidence/<TICKET>.json y **evalúa solo** las experiencias pendientes que declararon un
chequeo verificable con un tag `check:*`:
  - `check:pr-clean`  → true: mergeado, sin cambios pedidos, CI verde, ≤1 commit tras abrir y sin revert a
                         7 días del merge · false: revert, CI rojo, cambios pedidos o ≥3 commits de retrabajo.
  - `check:no-revert` → true: hay commits del ticket con ≥7 días y ninguno revertido · false: alguno revertido.
  - `check:ci-green`  → true/false según el CI del último commit del PR.
El resto de las pendientes queda con la evidencia adjunta en el reporte para que el agente la evalúe.

`calibration` → memory/evidence/calibration.json: Brier y sesgo (prob. media − tasa de acierto) por tag.
`report` → resumen corto (lo usa session_context.py).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
MEM = os.path.join(WS, "memory")
EVD = os.path.join(MEM, "evidence")
OWNERS = os.environ.get("EVIDENCE_GH_OWNERS", "MSoftIA,jorgeemilianom").split(",")
REVERT_WINDOW = timedelta(days=7)
TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def now():
    return datetime.now(timezone.utc)


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def run(args, cwd=None, timeout=60):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cognition():
    try:
        return json.load(open(os.path.join(MEM, "cognition.json")))
    except Exception:
        return {"episodes": []}


def candidate_tickets(days):
    """Tickets con predicciones pendientes + tickets tocados en memory/ en los últimos `days` días."""
    out = {e["ticket"] for e in cognition().get("episodes", []) if e.get("status") == "pending" and e.get("ticket")}
    cutoff = time.time() - days * 86400
    for sub in ("tickets", "snapshots", "assessments"):
        for p in glob.glob(os.path.join(MEM, sub, "*.json")):
            if os.path.getmtime(p) >= cutoff:
                tid = os.path.basename(p)[:-5].upper()
                if TICKET_RE.match(tid):
                    out.add(tid)
    return sorted(t for t in out if TICKET_RE.match(t))


def local_repos():
    seen, repos = set(), []
    for d in sorted(glob.glob(os.path.join(WS, "projects", "*")) + glob.glob(os.path.join(WS, "projects", "*", "*"))):
        if os.path.isdir(os.path.join(d, ".git")) or os.path.isfile(os.path.join(d, ".git")):
            url = run(["git", "-C", d, "remote", "get-url", "origin"]).strip()
            if url and url not in seen and "skill-charly-dev" not in url:
                seen.add(url)
                repos.append(d)
    return repos


def commit_evidence(ticket, repos):
    commits, reverted = [], []
    for d in repos:
        out = run(["git", "-C", d, "log", "--all", "-i", f"--grep={ticket}", "--format=%H%x09%cI%x09%s", "-n", "50"])
        for line in out.splitlines():
            sha, date, subj = line.split("\t", 2)
            if subj.lower().startswith("revert"):
                continue
            commits.append({"repo": os.path.basename(d), "sha": sha[:10], "date": date, "subject": subj[:100]})
            if run(["git", "-C", d, "log", "--all", f"--grep=This reverts commit {sha}", "--format=%h", "-n", "1"]).strip():
                reverted.append(sha[:10])
    return commits, reverted


def pr_evidence(ticket):
    args = ["gh", "search", "prs", ticket, "--json", "url,title,state,repository", "--limit", "10"]
    for o in OWNERS:
        args += ["--owner", o]
    try:
        found = json.loads(run(args) or "[]")
    except ValueError:
        return []
    prs = []
    for p in found:
        try:
            v = json.loads(run(["gh", "pr", "view", p["url"], "--json",
                                "number,title,state,createdAt,mergedAt,reviews,commits,statusCheckRollup,baseRefName"]) or "{}")
        except ValueError:
            continue
        if not v:
            continue
        created = parse_ts(v.get("createdAt"))
        after = [c for c in v.get("commits", []) if created and parse_ts(c.get("committedDate")) and parse_ts(c["committedDate"]) > created]
        checks = v.get("statusCheckRollup") or []
        concl = [(c.get("conclusion") or c.get("state") or "").upper() for c in checks]
        ci = None if not concl else (False if any(x in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED") for x in concl)
                                     else True if all(x in ("SUCCESS", "NEUTRAL", "SKIPPED") for x in concl) else None)
        repo = p["repository"]["nameWithOwner"]
        rev = run(["gh", "search", "prs", f'Revert "{v["title"]}"', "--repo", repo, "--json", "url", "--limit", "1"])
        prs.append({
            "url": p["url"], "repo": repo, "title": v["title"][:120], "state": v["state"],
            "merged_at": v.get("mergedAt"), "changes_requested": sum(r.get("state") == "CHANGES_REQUESTED" for r in v.get("reviews", [])),
            "commits_after_open": len(after), "ci_green": ci, "reverted": bool(rev.strip() not in ("", "[]")),
        })
    return prs


def verdict(check, ev):
    """(outcome, motivo) o (None, motivo) si todavía no es concluyente."""
    prs = [p for p in ev["prs"] if p["state"] == "MERGED"] or ev["prs"]
    if check == "pr-clean":
        if not prs:
            return None, "sin PR"
        bad = [p for p in prs if p["reverted"] or p["ci_green"] is False or p["changes_requested"] or p["commits_after_open"] >= 3]
        if bad:
            p = bad[0]
            why = "revert" if p["reverted"] else "CI rojo" if p["ci_green"] is False else \
                  f"{p['changes_requested']} pedido(s) de cambios" if p["changes_requested"] else f"{p['commits_after_open']} commits de retrabajo"
            return False, f"{p['url']}: {why}"
        if all(p["merged_at"] for p in prs) and all(p["ci_green"] for p in prs) and \
           all(now() - parse_ts(p["merged_at"]) >= REVERT_WINDOW for p in prs):
            return True, f"{len(prs)} PR mergeado(s) limpio(s), sin revert a 7 días"
        return None, "PR abierto, CI pendiente o dentro de la ventana de revert"
    if check == "ci-green":
        if not prs or all(p["ci_green"] is None for p in prs):
            return None, "sin CI concluyente"
        return all(p["ci_green"] is not False for p in prs), "CI del último commit del PR"
    if check == "no-revert":
        if ev["reverted_commits"]:
            return False, f"commits revertidos: {', '.join(ev['reverted_commits'])}"
        old = [c for c in ev["commits"] if now() - parse_ts(c["date"]) >= REVERT_WINDOW]
        if old:
            return True, f"{len(ev['commits'])} commit(s), ninguno revertido a 7 días"
        return None, "commits demasiado recientes" if ev["commits"] else "sin commits del ticket"
    return None, f"chequeo desconocido: {check}"


def evaluate(ep, outcome, why, ev):
    refs = [p["url"] for p in ev["prs"]][:3] + [f"{c['repo']}@{c['sha']}" for c in ev["commits"]][:3]
    payload = {"id": ep["id"], "outcome": outcome, "observation": why,
               "interpretation": "Evaluado automáticamente por scripts/evidence.py según el chequeo declarado.",
               "evidence": refs or [why]}
    r = subprocess.run([sys.executable, os.path.join(HERE, "memory_store.py"), "cognitive", "evaluate"],
                       input=json.dumps(payload), capture_output=True, text=True)
    return r.returncode == 0


def cmd_harvest(a):
    repos = local_repos()
    tickets = a.tickets or candidate_tickets(a.days)
    pending = [e for e in cognition().get("episodes", []) if e.get("status") == "pending"]
    evaluated, attached = [], []
    for t in tickets:
        commits, reverted = commit_evidence(t, repos)
        ev = {"ticket": t, "harvested_at": now().isoformat(timespec="seconds"), "commits": commits,
              "reverted_commits": reverted, "prs": [] if a.no_gh else pr_evidence(t)}
        write_json(os.path.join(EVD, f"{t}.json"), ev)
        for ep in [e for e in pending if e.get("ticket") == t]:
            checks = [x.split(":", 1)[1] for x in ep.get("tags", []) if x.startswith("check:")]
            if not checks:
                attached.append(ep["id"])
                continue
            results = [verdict(c, ev) for c in checks]
            if any(o is False for o, _ in results):
                o, why = next(r for r in results if r[0] is False)
            elif all(o is True for o, _ in results):
                o, why = True, "; ".join(w for _, w in results)
            else:
                continue
            if a.dry_run or evaluate(ep, o, why, ev):
                evaluated.append(f"{ep['id']} ({t}) → {o}: {why}")
    cmd_calibration(a, quiet=True)
    print(f"evidencia: {len(tickets)} ticket(s) · {len(evaluated)} predicción(es) evaluada(s)"
          + (" [dry-run]" if a.dry_run else ""))
    for line in evaluated:
        print(f"  {line}")
    if attached:
        print(f"  pendientes sin check:* con evidencia nueva (evaluar a mano): {', '.join(attached)}")


def cmd_calibration(a, quiet=False):
    eps = [e for e in cognition().get("episodes", []) if e.get("status") == "evaluated"
           and (e.get("evaluation") or {}).get("outcome") is not None and e.get("probability") is not None]
    groups = {"(todas)": eps}
    for e in eps:
        for t in e.get("tags", []):
            if not t.startswith("check:"):
                groups.setdefault(t, []).append(e)
    out = {}
    for k, es in groups.items():
        n = len(es)
        if not n:
            continue
        hits = sum(bool(e["evaluation"]["outcome"]) for e in es) / n
        mp = sum(e["probability"] for e in es) / n
        brier = sum((e["probability"] - (1 if e["evaluation"]["outcome"] else 0)) ** 2 for e in es) / n
        out[k] = {"n": n, "mean_prob": round(mp, 2), "hit_rate": round(hits, 2), "bias": round(mp - hits, 2), "brier": round(brier, 3)}
    write_json(os.path.join(EVD, "calibration.json"), {"updated_at": now().isoformat(timespec="seconds"), "groups": out})
    if not quiet:
        for k, v in sorted(out.items(), key=lambda kv: -kv[1]["n"]):
            print(f"{k:28} n={v['n']:3} prob={v['mean_prob']:.2f} acierto={v['hit_rate']:.2f} sesgo={v['bias']:+.2f} brier={v['brier']:.3f}")


def report_lines(min_n=3, min_bias=0.15):
    """Líneas cortas para el digest de arranque (vacío si no hay nada que decir)."""
    lines = []
    try:
        cal = json.load(open(os.path.join(EVD, "calibration.json")))["groups"]
        for k, v in cal.items():
            if k != "(todas)" and v["n"] >= min_n and abs(v["bias"]) >= min_bias:
                kind = "sobreestimás" if v["bias"] > 0 else "subestimás"
                lines.append(f"- {k}: {kind} (prob. media {v['mean_prob']:.2f} vs acierto {v['hit_rate']:.2f}, n={v['n']})"
                             + (" → verificar más antes de dar por hecho" if v["bias"] > 0 else ""))
    except Exception:
        pass
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("tickets", nargs="*")
    h.add_argument("--days", type=int, default=30)
    h.add_argument("--dry-run", action="store_true")
    h.add_argument("--no-gh", action="store_true")
    h.set_defaults(fn=cmd_harvest)
    c = sub.add_parser("calibration")
    c.set_defaults(fn=cmd_calibration)
    r = sub.add_parser("report")
    r.set_defaults(fn=lambda a: print("\n".join(report_lines()) or "sin sesgos de calibración relevantes"))
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
