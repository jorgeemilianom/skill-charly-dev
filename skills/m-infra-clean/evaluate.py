#!/usr/bin/env python3
"""Evalúa la salida de collect.sh y devuelve hallazgos como JSON, sin LLM de por medio.

Uso: evaluate.py <run.txt> [<run_anterior.txt>] [--expected-ports 22,80,443] [--max-backup-age-h 26]

Cada hallazgo: {"severity": "alta|media|baja", "area": ..., "finding": ..., "evidence": ..., "fix": <id|null>}
`fix` referencia el catálogo de fixes del SKILL.md (solo para hallazgos con una acción mecánica
conocida). Si se pasa la corrida anterior, además marca diferencias de seguridad (usuarios uid 0 o con
shell nuevos, claves SSH nuevas, puertos nuevos, crons nuevos) como anomalías: el baseline es la
corrida previa del mismo host, no una lista fija.
"""
import json
import re
import sys
from datetime import datetime, timezone


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^### (\S+)", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return out


def sub(lines, header):
    """Líneas debajo de un sub-encabezado `-- <header>` hasta el siguiente `-- `."""
    res, on = [], False
    for l in lines:
        if l.startswith("-- "):
            on = l[3:].startswith(header)
            continue
        if on and l.strip():
            res.append(l.strip())
    return res


def kv(lines):
    d = {}
    for l in lines:
        for m in re.finditer(r"(\w+)=(\S+)", l):
            d[m.group(1)] = m.group(2)
    return d


def size_mb(s):
    m = re.match(r"([\d.]+)\s*([KMGT])?B?", s or "")
    if not m:
        return 0.0
    return float(m.group(1)) * {"K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 ** 2, None: 1 / 1048576}[m.group(2)]


def evaluate(text, prev=None, expected_ports=(22, 80, 443), max_backup_age_h=26):
    S = sections(text)
    F = []

    def add(sev, area, finding, evidence="", fix=None):
        F.append({"severity": sev, "area": area, "finding": finding, "evidence": evidence[:300], "fix": fix})

    meta = kv(S.get("meta", []))
    root = meta.get("root") == "yes"
    cores = int(meta.get("cores", "1") or 1)

    # --- carga / memoria
    lm = S.get("load_mem", [])
    if lm:
        try:
            l1, l5, l15 = map(float, lm[0].split()[:3])
            if l15 > cores * 1.5:
                add("alta", "recursos", f"Load sostenido alto: {l15} en 15 min con {cores} cores", lm[0])
            elif l15 > cores:
                add("media", "recursos", f"Load por encima de los cores: {l15} con {cores} cores", lm[0])
        except ValueError:
            pass
    for l in lm:
        if l.startswith("Mem:"):
            p = l.split()
            total, avail = int(p[1]), int(p[-1])
            if total and avail / total < 0.10:
                add("alta", "recursos", f"Memoria disponible baja: {avail} de {total} MB", l)
        if l.startswith("Swap:"):
            p = l.split()
            total, used = int(p[1]), int(p[2])
            if total == 0:
                add("baja", "recursos", "Sin swap configurado", l, "add-swap")
            elif used / total > 0.9:
                add("media", "recursos", f"Swap casi lleno: {used} de {total} MB", l)

    # --- disco
    for l in S.get("disk", []):
        m = re.match(r"^(\S+)\s+\S+\s+\S+\s+\S+\s+(\d+)%\s+(\S+)$", l)
        if m and not l.startswith("Filesystem"):
            pct, mnt = int(m.group(2)), m.group(3)
            inodes = "inodes" in "\n".join(S["disk"][: S["disk"].index(l)])
            what = "Inodos" if inodes else "Disco"
            if pct >= 90:
                add("alta", "disco", f"{what} de {mnt} al {pct}%", l, "disk-cleanup")
            elif pct >= 80:
                add("media", "disco", f"{what} de {mnt} al {pct}%", l, "disk-cleanup")

    # --- updates / reboot / versiones
    ru = S.get("reboot_updates", [])
    rk = kv(ru)
    if rk.get("reboot_required") == "yes":
        add("media", "vulnerabilidades", "Reinicio pendiente (kernel o librerías actualizadas sin aplicar)", "", "reboot-window")
    sec_n = int(rk.get("security", "0") or 0)
    if sec_n:
        pk = ", ".join(l.split(": ", 1)[1] for l in ru if l.startswith("sec_pkg: "))[:250]
        add("alta" if sec_n >= 5 else "media", "vulnerabilidades", f"{sec_n} actualizaciones de seguridad pendientes", pk, "security-updates")
    if rk.get("release_update_available"):
        add("media", "vulnerabilidades", f"Amazon Linux: release {rk['release_update_available']} disponible (parches no aplicados)", "", "security-updates")
    if int(rk.get("apt_lists_age_days", "0") or 0) > 7:
        add("baja", "vulnerabilidades", f"Índice de apt sin refrescar hace {rk['apt_lists_age_days']} días: el conteo de updates puede estar subestimado", "", "apt-refresh")
    for l in ru:
        m = re.match(r"php: (\d+)\.(\d+)", l)
        if m and (int(m.group(1)), int(m.group(2))) < (8, 1):
            add("alta", "vulnerabilidades", f"PHP {m.group(1)}.{m.group(2)} fuera de soporte de seguridad", l)

    # --- acceso
    acc = S.get("access_auth", [])
    accl = "\n".join(acc).lower()
    if re.search(r"permitrootlogin\s+yes", accl) and re.search(r"passwordauthentication\s+yes", accl):
        add("alta", "accesos", "SSH acepta login de root con contraseña", "PermitRootLogin yes + PasswordAuthentication yes")
    elif re.search(r"passwordauthentication\s+yes", accl):
        add("media", "accesos", "SSH acepta autenticación por contraseña", "PasswordAuthentication yes")
    uid0 = sub(acc, "usuarios uid 0")
    if [u for u in uid0 if u != "root"]:
        add("alta", "accesos", "Usuarios con uid 0 además de root", ", ".join(uid0))
    fk = kv(sub(acc, "intentos fallidos"))
    failed = int(fk.get("failed_total", "0") or 0)
    if failed > 500:
        add("media", "accesos", f"{failed} intentos fallidos de SSH en 7 días", " ".join(sub(acc, "intentos fallidos")[1:5]), "fail2ban")
    if not root:
        add("baja", "cobertura", "Colector sin root: auth logs, firewall, OOM y claves de otros usuarios no se pudieron leer", "")

    # --- firewall / puertos
    fw = S.get("firewall", [])
    fwl = "\n".join(fw).lower()
    if root and "status: inactive" in fwl:
        add("alta", "accesos", "Firewall (ufw) inactivo", "ufw status: inactive")
    exposed = []
    for l in sub(fw, "puertos escuchando"):
        addr = l.split()[0]
        if addr.startswith(("127.", "[::1]", "::1")) or "%lo" in addr:
            continue
        port = addr.rsplit(":", 1)[-1]
        if port.isdigit() and int(port) not in expected_ports:
            exposed.append(l)
    if exposed:
        add("media", "accesos", "Puertos escuchando en todas las interfaces fuera de los esperados (verificar que el firewall los filtre)", "; ".join(exposed[:8]))

    # --- servicios
    svc = S.get("services", [])
    failed_units = [l for l in sub(svc, "unidades systemd fallidas") if "systemd-networkd-wait-online" not in l]
    if failed_units:
        add("media", "servicios", f"{len(failed_units)} unidades systemd en estado failed", "; ".join(failed_units[:5]))
    bad = [c for c in sub(svc, "contenedores (no healthy") if "|" in c]
    unhealthy = [c for c in bad if re.search(r"unhealthy|restarting", c, re.I)]
    if unhealthy:
        add("alta", "servicios", "Contenedores unhealthy o reiniciando en loop", "; ".join(unhealthy[:5]))
    exited = [c for c in bad if c not in unhealthy and "Exited (0)" not in c]
    if exited:
        add("baja", "servicios", "Contenedores detenidos con error", "; ".join(exited[:5]))
    for l in sub(svc, "docker disco"):
        m = re.match(r"^(Images|Build Cache)\s+.*?([\d.]+[KMGT]?B)\s+\(?\d*%?\)?$", l)
        if m:
            mb = size_mb(m.group(2))
            if mb > 5120:
                add("baja", "disco", f"Docker {m.group(1)}: {m.group(2)} recuperables", l, "docker-prune")

    # --- anomalías
    an = S.get("anomalies", [])
    tmpproc = sub(an, "procesos ejecutando desde")
    if tmpproc:
        add("alta", "anomalías", "Procesos ejecutándose desde /tmp, /dev/shm o binarios borrados (posible compromiso)", "; ".join(tmpproc[:5]))
    tmpbin = sub(an, "ejecutables en")
    if tmpbin:
        add("media", "anomalías", "Binarios ELF en directorios temporales", "; ".join(tmpbin[:5]))
    oom = sub(an, "OOM kills")
    if oom and oom[0].isdigit() and int(oom[0]) > 0:
        add("media", "recursos", f"{oom[0]} OOM kills en 7 días", "")
    crons = sub(an, "crontabs")
    sus = [c for c in crons if re.search(r"(curl|wget)[^|]*\|\s*(ba)?sh|base64\s+-d|/dev/tcp/|\bnc\s+-e|xmrig|\.onion", c)]
    if sus:
        add("alta", "anomalías", "Entradas de cron con patrón de descarga y ejecución / ofuscación", "; ".join(sus[:3]))
    changed = [c for c in sub(an, "binarios/config") if c.startswith(("/usr/bin", "/usr/sbin", "/bin", "/sbin", "/usr/local/bin"))]
    if changed:
        add("media", "anomalías", "Binarios del sistema modificados en las últimas 48 h (normal si hubo apt upgrade)", "; ".join(changed[:6]))
    outbound = sub(an, "conexiones salientes")
    odd = [o for o in outbound if not re.search(r"\s(127\.|\[::1\])", " " + o)]
    if odd:
        add("baja", "anomalías", "Conexiones salientes a puertos no web (revisar si son esperables)", "; ".join(odd[:6]))

    # --- logs
    lg = S.get("logs", [])
    jk = kv(lg)
    if size_mb(jk.get("journal")) > 2048:
        add("media", "logs", f"journald ocupa {jk['journal']}", "", "journal-vacuum")
    big = sub(lg, "archivos de log > 200 MB")
    if big:
        add("media", "logs", f"{len(big)} archivos de log de más de 200 MB", "; ".join(big[:5]), "log-rotate")
    lr = sub(lg, "errores de logrotate")
    if lr:
        add("alta", "logs", "logrotate reporta errores (las rotaciones pueden estar salteándose)", "; ".join(lr[:3]), None)
    dl = sub(lg, "tamaño de logs de contenedores")
    if dl:
        add("media", "logs", "Logs de contenedores sin límite de tamaño (> 100 MB)", "; ".join(dl[:4]), "docker-log-limits")

    # --- TLS
    for l in S.get("tls", []):
        m = re.match(r"^(-?\d+)d (\S+)", l)
        if m:
            d = int(m.group(1))
            if d < 14:
                add("alta", "tls", f"Certificado de {m.group(2)} vence en {d} días", l, "certbot-renew")
            elif d < 30:
                add("media", "tls", f"Certificado de {m.group(2)} vence en {d} días", l)

    # --- backups: solo dice qué hay; el SKILL cruza con los esperados del inventario.
    now = datetime.now(timezone.utc)
    newest = None
    for l in S.get("backups", []):
        m = re.match(r"^(\d{4}-\d{2}-\d{2}) ", l)
        if m:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            newest = d if not newest or d > newest else newest
    dbs = sub(svc, "contenedores de DB")
    if dbs and (not newest or (now - newest).total_seconds() / 3600 > max_backup_age_h + 24):
        add("alta", "backups", "Hay contenedores de DB pero ningún dump reciente en disco", "; ".join(dbs[:4]), "db-backup-now")

    # --- diferencias contra la corrida anterior
    if prev:
        P = sections(prev)
        def diff(sec, header, label, sev):
            new = set(sub(S.get(sec, []), header)) - set(sub(P.get(sec, []), header))
            if new:
                add(sev, "anomalías", f"{label} desde la corrida anterior", "; ".join(sorted(new)[:6]))
        diff("access_auth", "usuarios uid 0", "Usuarios uid 0 nuevos", "alta")
        diff("access_auth", "usuarios con shell", "Usuarios con shell de login nuevos", "alta")
        diff("access_auth", "authorized_keys", "Claves SSH autorizadas nuevas", "alta")
        diff("access_auth", "grupos sudo", "Cambios en grupos privilegiados", "media")
        diff("firewall", "puertos escuchando", "Puertos escuchando nuevos", "media")
        diff("anomalies", "crontabs", "Entradas de cron nuevas", "media")

    order = {"alta": 0, "media": 1, "baja": 2}
    F.sort(key=lambda f: order[f["severity"]])
    return {"host": meta.get("hostname"), "collected_at": meta.get("date_utc"), "root": root, "findings": F}


def main():
    args = sys.argv[1:]
    ports, age = (22, 80, 443), 26
    if "--expected-ports" in args:
        i = args.index("--expected-ports")
        ports = tuple(int(p) for p in args[i + 1].split(",") if p)
        del args[i:i + 2]
    if "--max-backup-age-h" in args:
        i = args.index("--max-backup-age-h")
        age = int(args[i + 1])
        del args[i:i + 2]
    if not args:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    cur = open(args[0], encoding="utf-8", errors="replace").read()
    prev = open(args[1], encoding="utf-8", errors="replace").read() if len(args) > 1 else None
    print(json.dumps(evaluate(cur, prev, ports, age), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
