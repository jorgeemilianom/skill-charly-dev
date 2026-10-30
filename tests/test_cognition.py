"""Tests for the agent's own state (memory/cognition.json) and its integration with the harness.

Every test builds a throwaway workspace (memory/, projects/<repo>/.git, Business/<client>/client.md)
and runs the real scripts as separate processes with CLAUDE_PROJECT_DIR pointing at it — so
"another process later" is literal, and the developer's real memory/ is never touched.

Run: python3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")

LEGACY_PROFILE = {
    "communication": {"language": "es"},
    "self_model": {"top_blind_spots": [{"statement": "Revisar permisos de .git/objects antes de commitear",
                                        "distinct_tickets": ["T-1", "T-2"]}],
                   "last_computed": "2026-10-01T00:00:00Z"},
}


class Workspace:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="charly-ws-")
        self.mem = os.path.join(self.root, "memory")
        os.makedirs(self.mem)
        for repo in ("repo-a", "repo-b"):
            os.makedirs(os.path.join(self.root, "projects", repo, ".git"))
        os.makedirs(os.path.join(self.root, "Business", "AcmeCorp"))
        with open(os.path.join(self.root, "Business", "AcmeCorp", "client.md"), "w") as f:
            f.write("---\nrepos: [repo-a]\n---\n# AcmeCorp\n")
        self.write("user_profile.json", LEGACY_PROFILE)

    def path(self, rel):
        return os.path.join(self.mem, rel)

    def write(self, rel, data):
        with open(self.path(rel), "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def read(self, rel):
        with open(self.path(rel)) as f:
            return json.load(f)

    def raw(self, rel):
        with open(self.path(rel), "rb") as f:
            return f.read()

    def run(self, script, *args, stdin=None, check=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], input=stdin,
                           capture_output=True, text=True, env=env, cwd=self.root, timeout=60)
        if check is not None:
            assert p.returncode == check, f"{script} {args} -> {p.returncode}\n{p.stdout}\n{p.stderr}"
        return p

    def cog(self, op, payload=None, check=0):
        p = self.run("memory_store.py", "cognitive", op, stdin=json.dumps(payload or {}), check=check)
        return json.loads(p.stdout)

    def read_cmd(self, *args, check=0):
        p = self.run("cognition.py", *args, check=check)
        return json.loads(p.stdout) if args[0] != "context" else p.stdout

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()

    def tearDown(self):
        self.ws.cleanup()

    def experience(self, tags=("repo-a",), p=0.8, **extra):
        payload = {"context": "Ticket de prueba en repo-a", "action": "Aplicar el fix en la capa de dominio",
                   "prediction": "Los tests de integración pasan al primer intento", "probability": p,
                   "tags": list(tags)}
        payload.update(extra)
        return self.ws.cog("experience", payload)["result"]["id"]

    def evaluate(self, ep, outcome, evidence=("CI run #1",)):
        return self.ws.cog("evaluate", {"id": ep, "observation": "resultado observado", "outcome": outcome,
                                        "interpretation": "posible causa", "adjustment": "qué cambiar",
                                        "evidence": list(evidence)})


class AcceptanceTest(Base):
    def test_predict_fail_recall_in_scope_then_improve(self):
        # 1. prediction
        ep1 = self.ws.cog("experience", {
            "context": "Migración de esquema en repo-a", "tags": ["repo-a"], "ticket": "T-10",
            "action": "Correr la migración sin backup previo de la tabla",
            "prediction": "La migración termina sin errores en staging", "probability": 0.9})["result"]["id"]
        # 2. failure observed, with evidence and adjustment
        self.ws.cog("evaluate", {"id": ep1, "outcome": False,
                                 "observation": "La migración falló por un índice duplicado en staging",
                                 "interpretation": "Staging tenía datos que dev no",
                                 "adjustment": "Validar contra un snapshot de prod antes de migrar",
                                 "evidence": ["log de staging 2026-10-30", "PR #12"]})
        # 3. a different process later: recall in the right scope only
        hits = [h["id"] for h in self.ws.read_cmd("recall", "--repos", "repo-a", "--text", "migración de esquema")]
        self.assertIn(ep1, hits)
        self.assertNotIn(ep1, [h["id"] for h in self.ws.read_cmd("recall", "--repos", "repo-b")])
        self.assertIn(ep1, [h["id"] for h in self.ws.read_cmd("recall", "--clients", "AcmeCorp")])
        ctx = self.ws.read_cmd("context", "--repos", "repo-a", "--budget", "2000")
        self.assertIn("Validar contra un snapshot de prod", ctx)
        # 4. an action influenced by that memory
        ep2 = self.ws.cog("experience", {
            "context": "Segunda migración en repo-a", "tags": ["repo-a"], "recalled": [ep1],
            "action": "Validar la migración contra un snapshot de prod antes de correrla",
            "prediction": "La migración termina sin errores en staging", "probability": 0.75})["result"]["id"]
        # 5. evaluate the new outcome
        self.ws.cog("evaluate", {"id": ep2, "outcome": True, "observation": "Migró sin errores",
                                 "evidence": ["log de staging 2026-11-02"]})
        m = self.ws.read_cmd("metrics")
        self.assertEqual(m["evaluated"], 2)
        self.assertEqual(m["with_recall"], {"count": 1, "successes": 1, "success_rate": 1.0})
        self.assertEqual(m["without_recall"]["successes"], 0)
        self.assertAlmostEqual(m["brier"], ((0.9 - 0) ** 2 + (0.75 - 1) ** 2) / 2, places=4)


class MigrationTest(Base):
    def test_legacy_read_before_init_writes_nothing(self):
        before = self.ws.raw("user_profile.json")
        st = self.ws.read_cmd("status")
        self.assertEqual(st["source"], "legacy")
        self.assertEqual(st["agent"]["blind_spots"], ["Revisar permisos de .git/objects antes de commitear"])
        self.assertFalse(os.path.exists(self.ws.path("cognition.json")))
        self.assertEqual(before, self.ws.raw("user_profile.json"))

    def test_init_is_idempotent_and_preserves_profile(self):
        before = self.ws.raw("user_profile.json")
        r1 = self.ws.cog("init")["result"]
        self.assertTrue(r1["created"])
        self.assertTrue(r1["migrated_legacy"])
        mtime = os.path.getmtime(self.ws.path("cognition.json"))
        r2 = self.ws.cog("init")["result"]
        self.assertFalse(r2["created"])
        self.assertEqual(mtime, os.path.getmtime(self.ws.path("cognition.json")))
        doc = self.ws.read("cognition.json")
        self.assertEqual(len(doc["agent"]["blind_spots"]), 1)
        self.assertEqual(before, self.ws.raw("user_profile.json"))

    def test_new_state_takes_precedence(self):
        self.ws.cog("init")
        self.ws.cog("set-blind-spots", {"blind_spots": [{"statement": "punto ciego nuevo"}]})
        st = self.ws.read_cmd("status")
        self.assertEqual(st["source"], "cognition")
        self.assertEqual(st["agent"]["blind_spots"], ["punto ciego nuevo"])
        self.assertIn("self_model", self.ws.read("user_profile.json"))  # legacy kept, untouched


class RobustnessTest(Base):
    def test_concurrent_writes_lose_nothing(self):
        self.ws.cog("init")
        with ThreadPoolExecutor(max_workers=12) as ex:
            ids = list(ex.map(lambda i: self.experience(p=0.5, context=f"ctx {i}"), range(24)))
        self.assertEqual(len(set(ids)), 24)
        self.assertEqual(len(self.ws.read("cognition.json")["episodes"]), 24)
        self.ws.run("memory_store.py", "validate", check=0)

    def test_corrupt_file_is_never_reinitialised(self):
        self.ws.write("cognition.json", '{"schema_version": 1, "episodes": [')
        before = self.ws.raw("cognition.json")
        out = self.ws.cog("experience", {"context": "x", "action": "y", "prediction": "z", "probability": 0.5}, check=2)
        self.assertEqual(out["kind"], "corrupt")
        self.ws.run("cognition.py", "status", check=2)
        self.ws.run("memory_store.py", "validate", check=1)
        self.assertEqual(before, self.ws.raw("cognition.json"))

    def test_incompatible_schema_is_preserved(self):
        self.ws.cog("init")
        doc = self.ws.read("cognition.json")
        doc["schema_version"] = 99
        self.ws.write("cognition.json", doc)
        before = self.ws.raw("cognition.json")
        self.assertEqual(self.ws.cog("goal", {"title": "t", "reason": "r", "next_action": "n",
                                              "success_criterion": "s"}, check=2)["kind"], "incompatible_schema")
        self.assertEqual(before, self.ws.raw("cognition.json"))

    def test_validation_rejects_bad_input(self):
        self.ws.cog("init")
        base = {"context": "c", "action": "a", "prediction": "p", "probability": 0.5}
        cases = [
            dict(base, probability=1.5),
            dict(base, probability=True),
            dict(base, unknown_field=1),
            dict(base, recalled=["ep-9999"]),
            dict(base, context="password: hunter2hunter2"),
            dict(base, context="x" * 5000),
        ]
        for c in cases:
            with self.subTest(c=list(c)[-1]):
                self.assertEqual(self.ws.cog("experience", c, check=1)["kind"], "validation")
        ep = self.experience()
        self.ws.cog("evaluate", {"id": ep, "observation": "o", "outcome": True}, check=1)  # no evidence
        self.ws.cog("evaluate", {"id": ep, "observation": "o", "outcome": "yes", "evidence": ["e"]}, check=1)
        self.ws.cog("experience", dict(base, corrects=ep), check=1)  # correcting a pending one
        self.evaluate(ep, None, evidence=())  # indeterminate needs no evidence
        self.ws.cog("evaluate", {"id": ep, "observation": "otra", "outcome": True, "evidence": ["e"]}, check=1)
        fix = self.ws.cog("experience", dict(base, corrects=ep))["result"]["id"]
        self.assertEqual(self.ws.read("cognition.json")["episodes"][-1]["corrects"], ep)
        self.assertNotEqual(fix, ep)


class GoalsTest(Base):
    def goal(self, **kw):
        p = {"title": "Objetivo", "reason": "Porque sí", "next_action": "Revisar el estado",
             "success_criterion": "Criterio verificable"}
        p.update(kw)
        return self.ws.cog("goal", p)

    def test_dependencies_cycles_blocking_and_reopen(self):
        g1 = self.goal(title="Base", priority=2)["result"]["id"]
        self.ws.cog("goal", {"title": "x", "reason": "r", "next_action": "n", "success_criterion": "s",
                             "depends_on": ["goal-9999"]}, check=1)
        g2 = self.goal(title="Depende", depends_on=[g1])["result"]["id"]
        self.ws.cog("update-goal", {"id": g1, "depends_on": [g2]}, check=1)  # cycle
        self.ws.cog("update-goal", {"id": g1, "status": "blocked"}, check=1)  # no reason
        self.ws.cog("update-goal", {"id": g1, "status": "blocked", "blocked_reason": "esperando acceso"})
        self.ws.cog("update-goal", {"id": g1, "status": "active", "note": "acceso concedido"})
        self.ws.cog("update-goal", {"id": g1, "status": "done"}, check=1)  # no evidence
        self.ws.cog("update-goal", {"id": g1, "status": "done", "evidence": ["PR #3 mergeado"]})
        self.ws.cog("update-goal", {"id": g1, "next_action": "otra"}, check=1)  # closed, no reopen
        self.ws.cog("update-goal", {"id": g1, "status": "active"}, check=1)
        self.ws.cog("update-goal", {"id": g1, "status": "active", "reopen": True, "note": "regresión"})
        g = next(x for x in self.ws.read("cognition.json")["goals"] if x["id"] == g1)
        self.assertEqual([h["to"] for h in g["history"]], ["active", "blocked", "active", "done", "active"])
        self.assertEqual(g["history"][3]["evidence"], ["PR #3 mergeado"])

    def test_timezones_and_tick(self):
        self.ws.cog("goal", {"title": "x", "reason": "r", "next_action": "n", "success_criterion": "s",
                             "activate_at": "2026-11-05T09:00:00"}, check=1)  # naive date rejected
        later = self.goal(title="Más tarde", priority=1, activate_at="2026-11-05T09:00:00-03:00")["result"]["id"]
        low = self.goal(title="Baja", priority=4)["result"]["id"]
        high = self.goal(title="Alta", priority=2)["result"]["id"]
        dep = self.goal(title="Con dependencia", priority=1, depends_on=[high])["result"]["id"]
        paused = self.goal(title="Pausada", priority=1, status="paused")["result"]["id"]
        # 11:59 UTC = 08:59 ART, one minute before activation
        t = self.ws.read_cmd("tick", "--now", "2026-11-05T11:59:00Z", "--limit", "5")
        self.assertEqual(t["mode"], "proposal_only")
        self.assertEqual([p["goal_id"] for p in t["proposals"]], [high, low])
        reasons = {x["goal_id"]: x["reason"] for x in t["not_ready"]}
        self.assertIn(later, reasons)
        self.assertIn(dep, reasons)
        self.assertIn(paused, reasons)
        t = self.ws.read_cmd("tick", "--now", "2026-11-05T12:00:00Z", "--limit", "2")
        self.assertEqual([p["goal_id"] for p in t["proposals"]], [later, high])
        self.assertEqual(len(t["proposals"]), 2)

    def test_tick_never_executes_or_writes(self):
        marker = os.path.join(self.ws.root, "PWNED")
        self.goal(next_action=f"$(touch {marker}); `touch {marker}`; touch {marker}")
        before = self.ws.raw("cognition.json")
        mtime = os.path.getmtime(self.ws.path("cognition.json"))
        t = self.ws.read_cmd("tick")
        self.assertEqual(len(t["proposals"]), 1)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(before, self.ws.raw("cognition.json"))
        self.assertEqual(mtime, os.path.getmtime(self.ws.path("cognition.json")))


class BeliefsTest(Base):
    def test_evidence_caps_and_revision_history(self):
        e1, e2, e3 = self.experience(), self.experience(), self.experience()
        pend = self.experience()
        for e in (e1, e2):
            self.evaluate(e, True)
        self.evaluate(e3, False)
        b = {"type": "capability", "claim": "Puedo migrar esquemas en repo-a", "scope_tags": ["repo-a"]}
        self.ws.cog("belief", dict(b, confidence=0.6, evidence=[e1]), check=1)            # single case
        self.ws.cog("belief", dict(b, confidence=0.6, evidence=[e1, pend]), check=1)      # pending evidence
        self.ws.cog("belief", dict(b, confidence=0.9, evidence=[e1, e2]), check=1)        # above cap 0.75
        self.ws.cog("belief", dict(b, confidence=0.6, evidence=[e1, e1, e1]), check=1)    # repetition ≠ evidence
        b1 = self.ws.cog("belief", dict(b, confidence=0.75, evidence=[e1, e2]))["result"]["id"]
        # counter-evidence lowers the cap: (2+1)/(2+1+2) = 0.6
        self.ws.cog("belief", dict(b, confidence=0.7, evidence=[e1, e2], counter_evidence=[e3], supersedes=b1), check=1)
        r = self.ws.cog("belief", dict(b, claim="Puedo migrar esquemas en repo-a si valido contra prod",
                                       confidence=0.6, evidence=[e1, e2], counter_evidence=[e3], supersedes=b1))["result"]
        bels = {x["id"]: x for x in self.ws.read("cognition.json")["beliefs"]}
        self.assertEqual(bels[b1]["status"], "superseded")
        self.assertEqual(bels[b1]["superseded_by"], r["id"])
        self.assertEqual(bels[r["id"]]["supersedes"], b1)
        self.ws.cog("archive-belief", {"id": r["id"], "reason": "el repo cambió de motor"})
        self.ws.cog("archive-belief", {"id": r["id"], "reason": "otra vez"}, check=1)
        s = self.ws.cog("belief", {"type": "strategy", "claim": "Validar contra snapshot", "confidence": 0.6,
                                   "evidence": [e1]})
        self.assertEqual(s["result"]["confidence_cap"], 0.6667)


class ContextAndHooksTest(Base):
    def test_context_budget_is_strict(self):
        for i in range(30):
            ep = self.experience(context=f"contexto largo número {i} " + "detalle " * 40)
            self.evaluate(ep, i % 2 == 0)
        for budget in (120, 300, 900):
            out = self.ws.read_cmd("context", "--repos", "repo-a", "--budget", str(budget))
            self.assertLessEqual(len(out.rstrip("\n")), budget)
        self.assertLessEqual(len(self.ws.read_cmd("recall", "--repos", "repo-a", "--limit", "3")), 3)

    def test_hooks_inject_scoped_state(self):
        ep = self.experience(tags=["repo-a"])
        self.evaluate(ep, False)
        other = self.experience(tags=["repo-b"])
        self.evaluate(other, False)
        event = {"hook_event_name": "PostToolUse", "session_id": f"t-{os.getpid()}-{id(self)}",
                 "tool_name": "Read", "tool_input": {"file_path": f"{self.ws.root}/projects/repo-a/main.go"}}
        p = self.ws.run("memory_compile.py", check=0)
        p = self.ws.run("context_hook.py", stdin=json.dumps(event), check=0)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(ep, ctx)
        self.assertNotIn(other, ctx)
        ss = self.ws.run("session_context.py", stdin=json.dumps(
            {"hook_event_name": "SessionStart", "session_id": event["session_id"], "source": "startup",
             "cwd": self.ws.root}), check=0)
        self.assertIn("Charly — estado propio", ss.stdout)


class CompatibilityTest(Base):
    def test_existing_commands_backup_and_restore(self):
        self.ws.run("memory_store.py", "add-rule", "--ticket", "T-1", "--type", "verify", "--rule", "regla", check=0)
        self.ws.run("memory_store.py", "similar-rules", "--rule", "regla", check=0)
        self.ws.run("memory_store.py", "upsert-pattern", "--pattern", "p", "--type", "error", "--ticket", "T-1", check=0)
        ep1 = self.experience()
        self.ws.run("memory_store.py", "backup", check=0)
        name = sorted(os.listdir(self.ws.path(".backups")))[-1]
        import tarfile
        with tarfile.open(self.ws.path(f".backups/{name}")) as t:
            self.assertIn("memory/cognition.json", t.getnames())
        self.experience()
        dry = self.ws.run("memory_store.py", "restore", name, "cognition.json", check=0)
        self.assertIn('"applied": false', dry.stdout)
        self.assertEqual(len(self.ws.read("cognition.json")["episodes"]), 2)
        self.ws.run("memory_store.py", "restore", name, "cognition.json", "--apply", check=0)
        self.assertEqual([e["id"] for e in self.ws.read("cognition.json")["episodes"]], [ep1])
        self.ws.run("memory_store.py", "restore", name, "../outside.json", check=None)
        self.assertFalse(os.path.exists(os.path.join(self.ws.root, "outside.json")))

    def test_self_model_refresh_and_historic_query(self):
        self.ws.write("global_rules.json", {"rules": [
            {"id": "T-1-r1", "rule": "verificar permisos de git objects antes de commitear en la vps", "type": "verify",
             "status": "active", "confidence": 0.6, "source": "retrospective", "origin_ticket": "T-1", "tags": []},
            {"id": "T-2-r1", "rule": "verificar permisos de git objects antes de commitear en repos compartidos",
             "type": "verify", "status": "active", "confidence": 0.6, "source": "retrospective",
             "origin_ticket": "T-2", "tags": []}]})
        hist = json.loads(self.ws.run("self_model.py", self.ws.mem, check=0).stdout)
        self.assertEqual(len(hist), 1)
        self.assertFalse(os.path.exists(self.ws.path("cognition.json")))  # historic query writes nothing
        self.ws.run("self_model.py", "--refresh", check=0)
        spots = self.ws.read("cognition.json")["agent"]["blind_spots"]
        self.assertEqual(len(spots), 1)
        self.ws.write("patterns.json", "{broken")
        self.ws.run("self_model.py", "--refresh", check=2)
        self.assertEqual(self.ws.read("cognition.json")["agent"]["blind_spots"], spots)
        self.assertEqual(self.ws.read("user_profile.json"), LEGACY_PROFILE)


if __name__ == "__main__":
    unittest.main()
