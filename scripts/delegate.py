#!/usr/bin/env python3
"""Delegar una tarea acotada a otro agente (Codex o Claude) en modo no interactivo.

El agente que delega (normalmente Claude) escribe un brief; este script lo envuelve con el contrato del
harness, corre el otro agente en un directorio aislado (idealmente un worktree propio), le exige una
respuesta con schema fijo y devuelve un reporte compacto (estado, validación, diffstat) para que el
delegante gaste pocos tokens revisando. Todo queda en memory/delegations/<id>/ para medir qué conviene
delegar.

Uso:
  delegate.py run --repo projects/X [--base origin/develop] --brief brief.md [--agent codex|claude]
  delegate.py run --dir <worktree existente> --brief - [--mode read]       (brief por stdin)
  delegate.py followup <id> --brief -        # misma sesión del agente: corrige sin recargar contexto
  delegate.py show <id> [--diff]             # reporte (y diff completo) de una corrida
  delegate.py review <id> --verdict accepted|reworked|rejected [--note "..."]
  delegate.py stats                          # tasa de aceptación, duración y tokens por agente
  delegate.py cleanup <id>                   # borra el worktree y la rama creados por `run --repo`

Modos: `write` (default) puede editar archivos dentro del directorio; `read` es análisis/investigación y
el script verifica que el árbol quedó intacto. Nunca commitea, pushea ni toca estado externo: integrar
es trabajo del delegante, después de revisar el diff.
"""
import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
LOGS = os.path.join(WS, "memory", "delegations")
WORKTREES = os.path.join(WS, "worktrees")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "files_changed", "validation", "open_questions"],
    "properties": {
        "status": {"type": "string", "enum": ["done", "partial", "blocked"]},
        "summary": {"type": "string", "description": "Qué se hizo o se encontró, máximo 3 oraciones"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "validation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["command", "passed", "output_tail"],
            "properties": {
                "command": {"type": "string"},
                "passed": {"type": ["boolean", "null"]},
                "output_tail": {"type": "string", "description": "Últimas líneas relevantes, máximo 15"},
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
}

CONTRACT = """Sos un agente al que otro agente del harness MSoftIA le delega una tarea acotada. Reglas:
- Trabajá SOLO dentro del directorio de trabajo actual. No leas ni escribas fuera salvo lo que el brief pida leer.
- No hagas commit, push, merge, cambios de rama, ni operaciones sobre Jira, GitHub, SSH, bases de producción o
  servicios externos. No leas archivos credentials.md, .env ni secretos. No escribas en memory/ del harness.
- No preguntes: si algo bloquea o es ambiguo, resolvé lo razonable y anotalo en open_questions; si no se puede
  avanzar, status=blocked con el motivo.
- Respetá las convenciones del repo (su CLAUDE.md / AGENTS.md) y el alcance del brief: nada de refactors extra.
- Si el brief trae un comando de validación, correlo y reportá el resultado real; nunca lo inventes.
- Respuesta final: solo el JSON del schema, en español, breve.
{mode_rule}
--- BRIEF ---
"""
MODE_RULES = {
    "write": "- Modo escritura: podés editar y crear archivos dentro del directorio de trabajo.",
    "read": "- Modo lectura: NO modifiques ningún archivo. Solo investigá y reportá (files_changed vacío).",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(args, cwd=None, check=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"error: {' '.join(args)}\n{r.stderr.strip()}")
    return r


def run_dir(rid):
    return os.path.join(LOGS, rid)


def load_meta(rid):
    p = os.path.join(run_dir(rid), "meta.json")
    if not os.path.exists(p):
        sys.exit(f"no existe la delegación {rid}")
    return json.load(open(p))


def save_meta(meta):
    d = run_dir(meta["id"])
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".meta.{os.getpid()}.tmp")
    with open(tmp, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(d, "meta.json"))


def git_state(d):
    """Huella del árbol (para verificar modo read) — None si no es un repo git."""
    r = sh(["git", "-C", d, "status", "--porcelain", "--untracked-files=all"])
    if r.returncode != 0:
        return None
    diff = sh(["git", "-C", d, "diff", "HEAD"]).stdout
    return r.stdout + "\n" + str(hash(diff))


def diff_report(d, outfile, own=False):
    if sh(["git", "-C", d, "rev-parse", "--git-dir"]).returncode != 0:
        return "(no es un repo git: sin diff)"
    if own:
        # Worktree propio: intent-to-add para que los archivos nuevos entren al patch y `git apply` lo aplique entero.
        sh(["git", "-C", d, "add", "-A", "-N"])
    stat = sh(["git", "-C", d, "diff", "HEAD", "--stat"]).stdout.strip()
    untracked = [u for u in sh(["git", "-C", d, "ls-files", "--others", "--exclude-standard"]).stdout.splitlines() if u]
    with open(outfile, "w") as f:
        f.write(sh(["git", "-C", d, "diff", "HEAD"]).stdout)
        for u in untracked:
            f.write(f"\n=== archivo nuevo: {u}\n")
            try:
                f.write(open(os.path.join(d, u), errors="replace").read())
            except OSError:
                pass
    lines = stat.splitlines()[-1:] if stat else []
    if untracked:
        lines.append(f"{len(untracked)} archivo(s) nuevo(s): {', '.join(untracked[:6])}{' …' if len(untracked) > 6 else ''}")
    return "\n".join(lines) or "sin cambios"


def exec_agent(meta, prompt, resume=None):
    """Corre el agente; devuelve (result_dict|None, error|None) y completa usage/session en meta."""
    d = run_dir(meta["id"])
    n = meta.get("turns", 0) + 1
    events = os.path.join(d, f"events-{n}.jsonl")
    errf = os.path.join(d, f"stderr-{n}.txt")
    schema_f = os.path.join(d, "schema.json")
    json.dump(SCHEMA, open(schema_f, "w"))
    if meta["agent"] == "codex":
        last = os.path.join(d, f"last-{n}.json")
        # Sandbox de Codex: escritura solo dentro del directorio de trabajo, con red (instalar deps / correr tests).
        # Requiere el perfil AppArmor /etc/apparmor.d/codex-bwrap (kernel.apparmor_restrict_unprivileged_userns=1).
        sandbox = os.environ.get("DELEGATE_CODEX_SANDBOX", "workspace-write")
        common = ["--json", "--output-schema", schema_f, "-o", last, "--skip-git-repo-check",
                  "-c", "sandbox_workspace_write.network_access=true"]
        if meta.get("model"):
            common += ["-m", meta["model"]]
        if meta.get("effort"):
            common += ["-c", f'model_reasoning_effort="{meta["effort"]}"']
        if resume:
            cmd = ["codex", "exec", "resume", resume] + common + ["-c", f'sandbox_mode="{sandbox}"', prompt]
        else:
            cmd = ["codex", "exec", "-s", sandbox, "-C", meta["dir"]] + common + [prompt]
    else:
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
               "--permission-mode", "bypassPermissions"]
        if meta.get("model"):
            cmd += ["--model", meta["model"]]
        if meta.get("effort"):
            cmd += ["--effort", meta["effort"]]
        if resume:
            cmd += ["--resume", resume]
    t0 = time.time()
    with open(events, "w") as out, open(errf, "w") as err:
        p = subprocess.Popen(cmd, cwd=meta["dir"], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                             start_new_session=True)
        try:
            rc = p.wait(timeout=meta["timeout"])
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait()
            rc = "timeout"
    meta["duration_s"] = meta.get("duration_s", 0) + round(time.time() - t0)
    meta["turns"] = n
    usage = meta.setdefault("usage", {"input": 0, "cached_input": 0, "output": 0})
    result, error = None, None
    if meta["agent"] == "codex":
        for line in open(events):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "thread.started":
                meta["session"] = e.get("thread_id")
            elif e.get("type") == "turn.completed":
                u = e.get("usage", {})
                usage["input"] += u.get("input_tokens", 0)
                usage["cached_input"] += u.get("cached_input_tokens", 0)
                usage["output"] += u.get("output_tokens", 0) + u.get("reasoning_output_tokens", 0)
            elif e.get("type") in ("error", "turn.failed"):
                error = json.dumps(e, ensure_ascii=False)[:300]
        try:
            result = json.load(open(last))
        except (OSError, ValueError):
            pass
    else:
        try:
            out = json.load(open(events))
            meta["session"] = out.get("session_id")
            u = out.get("usage", {})
            usage["input"] += u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            usage["cached_input"] += u.get("cache_read_input_tokens", 0)
            usage["output"] += u.get("output_tokens", 0)
            if out.get("total_cost_usd") is not None:
                meta["cost_usd"] = round(meta.get("cost_usd", 0) + out["total_cost_usd"], 4)
            result = out.get("structured_output")
            if result is None and isinstance(out.get("result"), str):
                try:
                    result = json.loads(out["result"])
                except ValueError:
                    pass
            if out.get("is_error"):
                error = str(out.get("result"))[:300]
        except (OSError, ValueError):
            pass
    if rc == "timeout":
        error = f"timeout tras {meta['timeout']} s"
    elif rc != 0 and not error:
        tail = open(errf).read().strip().splitlines()[-3:]
        error = f"exit {rc}: " + " | ".join(tail)
    if result is not None:
        json.dump(result, open(os.path.join(d, f"result-{n}.json"), "w"), ensure_ascii=False, indent=2)
    return result, error


def finish(meta, result, error, before):
    d = run_dir(meta["id"])
    meta["status"] = (result or {}).get("status") or "error"
    meta["error"] = error
    meta["finished_at"] = now()
    if meta["mode"] == "read" and before is not None and git_state(meta["dir"]) != before:
        meta["read_violation"] = True
    meta["diffstat"] = diff_report(meta["dir"], os.path.join(d, "diff.patch"), own=bool(meta.get("worktree")))
    save_meta(meta)
    report(meta, result)


def report(meta, result=None):
    if result is None:
        rs = sorted(f for f in os.listdir(run_dir(meta["id"])) if f.startswith("result-"))
        result = json.load(open(os.path.join(run_dir(meta["id"]), rs[-1]))) if rs else {}
    u = meta.get("usage", {})
    tok = f"{u.get('input', 0) // 1000}k in ({u.get('cached_input', 0) // 1000}k cache) / {u.get('output', 0) // 1000}k out"
    print(f"[{meta['id']}] {meta['agent']} · {meta['status']} · {meta.get('duration_s', 0)} s · {tok}"
          + (f" · ${meta['cost_usd']}" if meta.get("cost_usd") else ""))
    print(f"dir: {meta['dir']}")
    if meta.get("error"):
        print(f"ERROR: {meta['error']}")
    if meta.get("read_violation"):
        print("ALERTA: modo read pero el árbol cambió — revisar el diff antes de cualquier otra cosa")
    if result.get("summary"):
        print(f"resumen: {result['summary']}")
    v = result.get("validation") or {}
    if v.get("command"):
        ok = {True: "OK", False: "FALLA", None: "sin correr"}[v.get("passed")]
        print(f"validación: {v['command']} → {ok}")
        if v.get("passed") is False and v.get("output_tail"):
            print("  " + "\n  ".join(v["output_tail"].splitlines()[-8:]))
    for q in result.get("open_questions") or []:
        print(f"pregunta: {q}")
    print(f"cambios: {meta.get('diffstat', '')}")
    print(f"diff completo: {os.path.join(run_dir(meta['id']), 'diff.patch')}")


def cmd_run(a):
    brief = sys.stdin.read() if a.brief == "-" else open(a.brief).read()
    if not brief.strip():
        sys.exit("brief vacío")
    rid = datetime.now().strftime("d-%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    meta = {"id": rid, "agent": a.agent, "mode": a.mode, "created_at": now(), "timeout": a.timeout,
            "model": a.model, "effort": a.effort, "title": a.title or brief.strip().splitlines()[0][:100],
            "ticket": a.ticket, "worktree": None}
    if a.repo:
        repo = os.path.abspath(a.repo)
        path = os.path.join(WORKTREES, f"delegate-{rid}")
        branch = f"delegate/{rid}"
        sh(["git", "-C", repo, "worktree", "add", "-b", branch, path, a.base], check=True)
        meta.update(dir=path, worktree={"repo": repo, "path": path, "branch": branch, "base": a.base})
    elif a.dir:
        meta["dir"] = os.path.abspath(a.dir)
        if a.mode == "write" and not a.allow_shared:
            # Un checkout compartido (projects/<repo>) puede tener trabajo de otras sesiones o ser prod.
            top = sh(["git", "-C", meta["dir"], "rev-parse", "--show-toplevel"]).stdout.strip()
            if top and os.path.realpath(top).startswith(os.path.realpath(os.path.join(WS, "projects")) + os.sep):
                sys.exit("--dir apunta a un checkout de projects/: usá --repo (worktree propio) o --allow-shared")
    else:
        sys.exit("falta --repo o --dir")
    os.makedirs(run_dir(rid), exist_ok=True)
    open(os.path.join(run_dir(rid), "brief.md"), "w").write(brief)
    save_meta(meta)
    before = git_state(meta["dir"])
    prompt = CONTRACT.format(mode_rule=MODE_RULES[a.mode]) + brief
    result, error = exec_agent(meta, prompt)
    finish(meta, result, error, before)


def cmd_followup(a):
    meta = load_meta(a.id)
    if not meta.get("session"):
        sys.exit("la corrida no registró sesión del agente: lanzar un `run` nuevo")
    brief = sys.stdin.read() if a.brief == "-" else open(a.brief).read()
    open(os.path.join(run_dir(a.id), f"followup-{meta.get('turns', 1) + 1}.md"), "w").write(brief)
    before = git_state(meta["dir"])
    result, error = exec_agent(meta, "Corrección del delegante (mismas reglas y schema de antes):\n" + brief,
                               resume=meta["session"])
    finish(meta, result, error, before)


def cmd_show(a):
    meta = load_meta(a.id)
    report(meta)
    if a.diff:
        print(open(os.path.join(run_dir(a.id), "diff.patch")).read())


def cmd_review(a):
    meta = load_meta(a.id)
    meta["verdict"] = {"value": a.verdict, "note": a.note, "at": now()}
    save_meta(meta)
    print(f"{a.id}: {a.verdict}")


def cmd_cleanup(a):
    meta = load_meta(a.id)
    wt = meta.get("worktree")
    if not wt:
        sys.exit("esta delegación no creó worktree")
    sh(["git", "-C", wt["repo"], "worktree", "remove", "--force", wt["path"]], check=True)
    sh(["git", "-C", wt["repo"], "branch", "-D", wt["branch"]])
    meta["worktree"]["removed_at"] = now()
    save_meta(meta)
    print(f"worktree y rama {wt['branch']} eliminados")


def cmd_stats(a):
    if not os.path.isdir(LOGS):
        print("sin delegaciones registradas")
        return
    agg = {}
    for rid in sorted(os.listdir(LOGS)):
        p = os.path.join(LOGS, rid, "meta.json")
        if not os.path.exists(p):
            continue
        m = json.load(open(p))
        s = agg.setdefault(m["agent"], {"n": 0, "done": 0, "accepted": 0, "reviewed": 0, "dur": 0, "out": 0, "inp": 0})
        s["n"] += 1
        s["done"] += m.get("status") == "done"
        s["dur"] += m.get("duration_s", 0)
        s["inp"] += m.get("usage", {}).get("input", 0)
        s["out"] += m.get("usage", {}).get("output", 0)
        v = (m.get("verdict") or {}).get("value")
        if v:
            s["reviewed"] += 1
            s["accepted"] += v == "accepted"
    for ag, s in agg.items():
        acc = f"{s['accepted']}/{s['reviewed']} aceptadas sin retrabajo" if s["reviewed"] else "sin veredictos"
        print(f"{ag}: {s['n']} corridas · {s['done']} done · {acc} · {s['dur'] // max(s['n'], 1)} s prom · "
              f"{s['inp'] // 1000}k in / {s['out'] // 1000}k out totales")
    pending = [r for r in sorted(os.listdir(LOGS)) if os.path.exists(os.path.join(LOGS, r, "meta.json"))
               and not json.load(open(os.path.join(LOGS, r, "meta.json"))).get("verdict")]
    if pending:
        print(f"sin veredicto: {', '.join(pending[-5:])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--repo", help="repo git: crea worktree propio en worktrees/delegate-<id>")
    g.add_argument("--dir", help="directorio de trabajo existente (ej. el worktree del ticket)")
    r.add_argument("--base", default="HEAD", help="ref base del worktree (default HEAD del repo)")
    r.add_argument("--brief", required=True, help="archivo con el brief, o - para stdin")
    r.add_argument("--agent", choices=["codex", "claude"], default="codex")
    r.add_argument("--mode", choices=["write", "read"], default="write")
    r.add_argument("--timeout", type=int, default=1200)
    r.add_argument("--model")
    r.add_argument("--effort", help="codex: low|medium|high · claude: low|medium|high|max")
    r.add_argument("--title")
    r.add_argument("--ticket")
    r.add_argument("--allow-shared", action="store_true", help="permitir --dir sobre un checkout de projects/")
    r.set_defaults(fn=cmd_run)
    f = sub.add_parser("followup")
    f.add_argument("id")
    f.add_argument("--brief", required=True)
    f.set_defaults(fn=cmd_followup)
    s = sub.add_parser("show")
    s.add_argument("id")
    s.add_argument("--diff", action="store_true")
    s.set_defaults(fn=cmd_show)
    v = sub.add_parser("review")
    v.add_argument("id")
    v.add_argument("--verdict", required=True, choices=["accepted", "reworked", "rejected"])
    v.add_argument("--note")
    v.set_defaults(fn=cmd_review)
    c = sub.add_parser("cleanup")
    c.add_argument("id")
    c.set_defaults(fn=cmd_cleanup)
    st = sub.add_parser("stats")
    st.set_defaults(fn=cmd_stats)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
