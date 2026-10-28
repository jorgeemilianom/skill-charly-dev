#!/usr/bin/env bash
# Colector de solo lectura para /m-infra-clean. Se ejecuta EN el host auditado:
#   ssh <host> 'bash -s' < collect.sh        (remoto)
#   bash collect.sh                           (host local)
#
# No modifica nada: solo lee estado del sistema. Funciona con o sin root — si no es root y hay
# `sudo -n` disponible lo usa; si no, las secciones que necesitan root salen marcadas `N/A (root)`.
# Soporta Debian/Ubuntu y RHEL/Amazon Linux. Salida: secciones `### <nombre>` en texto plano,
# acotadas con head para que el reporte entre en contexto. Todo pasa por redact() antes de salir:
# valores de token/password/secret/key en crons, procesos o configs nunca se imprimen.

set -u
export LC_ALL=C
T="timeout 20"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; ROOT=yes
elif sudo -n true 2>/dev/null; then SUDO="sudo -n"; ROOT=yes
else SUDO=""; ROOT=no
fi

redact() {
  sed -E \
    -e 's/((token|passw(or)?d|pass|pwd|secret|api_?key|apikey|auth|access_key|private_key)["'"'"']?[[:space:]]*[=:][[:space:]]*["'"'"']?)[^[:space:]&"'"'"',;]+/\1***/Ig' \
    -e 's/((mysql|mysqldump|mariadb|mariadb-dump|mysqladmin)[^|;]*[[:space:]]-p)[^[:space:]]+/\1***/g' \
    -e 's#(://[^:/@[:space:]]+:)[^@[:space:]]+@#\1***@#g'
}
sec() { echo; echo "### $1"; }
need_root() { [ "$ROOT" = yes ] || { echo "N/A (root)"; return 1; }; }
have() { command -v "$1" >/dev/null 2>&1; }

{
sec meta
echo "hostname=$(hostname 2>/dev/null)"
echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "root=$ROOT user=$(id -un)"
[ -r /etc/os-release ] && . /etc/os-release && echo "os=${PRETTY_NAME:-unknown}"
echo "kernel_running=$(uname -r)"
echo "cores=$(nproc 2>/dev/null)"
echo "uptime=$(uptime -p 2>/dev/null || uptime)"

sec load_mem
cat /proc/loadavg
free -m 2>/dev/null
swapon --show 2>/dev/null || echo "swap=none"

sec disk
df -hP -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null
echo "-- inodes"
df -iP -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null | awk 'NR==1 || $5+0>=50'

sec reboot_updates
[ -f /var/run/reboot-required ] && echo "reboot_required=yes" || echo "reboot_required=no"
if have apt; then
  # Lista de lo actualizable según el último `apt update` del propio host (no lo corremos: escribe).
  echo "apt_lists_age_days=$(( ( $(date +%s) - $(stat -c %Y /var/lib/apt/lists/ 2>/dev/null || date +%s) ) / 86400 ))"
  UPG=$($T apt list --upgradable 2>/dev/null | tail -n +2)
  echo "upgradable=$(printf '%s' "$UPG" | grep -c .)"
  echo "security=$(printf '%s' "$UPG" | grep -c -- '-security')"
  printf '%s\n' "$UPG" | grep -- '-security' | cut -d/ -f1 | head -40 | sed 's/^/sec_pkg: /'
elif have dnf || have yum; then
  PM=$(have dnf && echo dnf || echo yum)
  echo "security=$($T $SUDO $PM -q updateinfo list security 2>/dev/null | grep -c .)"
  echo "upgradable=$($T $SUDO $PM -q check-update 2>/dev/null | grep -c '^[a-zA-Z0-9]')"
  $T $SUDO $PM -q updateinfo list security 2>/dev/null | awk '{print "sec_pkg: "$3}' | head -40
  echo "kernel_latest_installed=$(rpm -q kernel --last 2>/dev/null | head -1 | awk '{print $1}')"
  # Amazon Linux 2023 usa repos versionados: los parches nuevos llegan como "release update".
  if grep -q 'Amazon Linux 2023' /etc/os-release 2>/dev/null; then
    $T $SUDO dnf -q check-release-update 2>&1 | grep -oE 'Version [0-9.]+' | head -1 | sed 's/^Version /release_update_available=/'
  fi
fi
echo "-- versiones de software expuesto"
for b in nginx apache2 httpd php mysql mysqld mariadb psql node openssl docker sshd; do
  have "$b" || continue
  case "$b" in
    nginx) v=$(nginx -v 2>&1) ;; sshd) v=$(sshd -V 2>&1 | head -1) ;; apache2|httpd) v=$($b -v 2>/dev/null | head -1) ;;
    openssl) v=$(openssl version) ;; php) v=$(php -r 'echo PHP_VERSION;' 2>/dev/null) ;; *) v=$($b --version 2>/dev/null | head -1) ;;
  esac
  echo "$b: $v"
done

sec access_auth
if have sshd; then
  if [ "$ROOT" = yes ]; then
    $SUDO sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|maxauthtries|allowusers|kbdinteractiveauthentication) '
  else
    grep -hEi '^[[:space:]]*(Port|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|MaxAuthTries|AllowUsers)' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null
  fi
fi
echo "-- usuarios uid 0"
awk -F: '$3==0{print $1}' /etc/passwd
echo "-- usuarios con shell de login"
awk -F: '$7 !~ /(nologin|false|sync|halt|shutdown)$/ {print $1" uid="$3" home="$6}' /etc/passwd
echo "-- grupos sudo/wheel/adm/docker"
getent group sudo wheel adm docker 2>/dev/null
echo "-- authorized_keys (solo fingerprints)"
for h in /root $(awk -F: '$3>=1000 && $3<65534 {print $6}' /etc/passwd) /home/ec2-user; do
  f="$h/.ssh/authorized_keys"
  $SUDO test -r "$f" 2>/dev/null || continue
  $SUDO cat "$f" 2>/dev/null | grep -v '^#' | grep . | while read -r line; do
    fp=$(printf '%s\n' "$line" | ssh-keygen -lf - 2>/dev/null | awk '{print $2" "$NF}')
    case "$line" in *command=*) fc=" forced-command" ;; *) fc="" ;; esac
    echo "$f: ${fp:-unparseable}$fc"
  done
done
echo "-- últimos logins"
$T last -n 15 -w 2>/dev/null | grep -v '^$' | head -15
echo "-- intentos fallidos SSH (7 días)"
FAILS=""
if have journalctl && [ "$ROOT" = yes ]; then
  FAILS=$($T $SUDO journalctl -q --since "7 days ago" -u ssh -u sshd --no-pager 2>/dev/null | grep -E 'Failed password|Invalid user|authentication failure')
elif [ -r /var/log/auth.log ] || [ -r /var/log/secure ]; then
  FAILS=$(cat /var/log/auth.log /var/log/secure 2>/dev/null | grep -E 'Failed password|Invalid user')
else
  echo "N/A (root)"
fi
if [ -n "$FAILS" ]; then
  echo "failed_total=$(printf '%s\n' "$FAILS" | grep -c .)"
  echo "top_ips:"; printf '%s\n' "$FAILS" | grep -oE 'from [0-9a-f.:]+' | awk '{print $2}' | sort | uniq -c | sort -rn | head -8
fi
echo "-- logins exitosos SSH (7 días, por usuario/IP)"
if have journalctl && [ "$ROOT" = yes ]; then
  $T $SUDO journalctl -q --since "7 days ago" -u ssh -u sshd --no-pager 2>/dev/null | grep -oE 'Accepted [a-z-]+ for [^ ]+ from [0-9a-f.:]+' | awk '{print $4" "$6" "$2}' | sort | uniq -c | sort -rn | head -12
fi

sec firewall
if have ufw; then need_root && $SUDO ufw status verbose 2>/dev/null | head -25; fi
if have firewall-cmd; then $SUDO firewall-cmd --state 2>/dev/null; $SUDO firewall-cmd --list-all 2>/dev/null | head -15; fi
if [ "$ROOT" = yes ] && have iptables; then echo "iptables_input_rules=$($SUDO iptables -S INPUT 2>/dev/null | grep -c .)"; fi
if have fail2ban-client && [ "$ROOT" = yes ]; then $SUDO fail2ban-client status 2>/dev/null | tail -2; fi
echo "-- puertos escuchando"
$SUDO ss -Htlnp 2>/dev/null | awk '{p=$6; gsub(/users:\(\("|".*/,"",p); print $4" "p}' | sort -u | head -40

sec services
echo "-- unidades systemd fallidas"
systemctl --failed --no-legend --plain 2>/dev/null | head -15
if have docker && docker ps >/dev/null 2>&1; then
  echo "-- contenedores (no healthy / reiniciando / exited)"
  docker ps -a --format '{{.Names}}|{{.Status}}|{{.Image}}' 2>/dev/null | grep -Ei 'unhealthy|restarting|exited|dead' | head -20
  echo "containers_running=$(docker ps -q 2>/dev/null | grep -c .)"
  echo "-- contenedores de DB"
  docker ps --format '{{.Names}}|{{.Image}}' 2>/dev/null | grep -Ei 'mysql|mariadb|postgres|mongo|redis' | head -15
  echo "-- docker disco"
  $T docker system df 2>/dev/null
else
  echo "docker=no-disponible"
fi

sec anomalies
echo "-- top CPU"
ps -eo pid,user,pcpu,pmem,etime,comm --sort=-pcpu 2>/dev/null | head -8
echo "-- top MEM"
ps -eo pid,user,pmem,rss,comm --sort=-pmem 2>/dev/null | head -6
echo "-- procesos ejecutando desde /tmp, /dev/shm o /var/tmp (posible compromiso)"
for p in /proc/[0-9]*; do
  exe=$($SUDO readlink "$p/exe" 2>/dev/null) || continue
  case "$exe" in /tmp/*|/dev/shm/*|/var/tmp/*|*"(deleted)"*) echo "pid=${p#/proc/} exe=$exe" ;; esac
done | head -15
echo "-- ejecutables en /tmp /dev/shm /var/tmp"
# Excluye scratchpads de agentes IA y node_modules: ruido conocido, no ejecutables sueltos.
# Solo binarios ELF (droppers típicos); scripts con +x son ruido habitual en builds temporales.
$SUDO find /tmp /dev/shm /var/tmp -xdev \( -path '/tmp/claude-*' -o -name node_modules \) -prune -o -type f -perm -u+x -print 2>/dev/null \
  | while read -r f; do [ "$($SUDO head -c4 "$f" 2>/dev/null | od -An -c | tr -d ' ')" = '177ELF' ] && echo "$f"; done | head -15
echo "-- OOM kills (7 días)"
if have journalctl && [ "$ROOT" = yes ]; then $T $SUDO journalctl -k -q --since "7 days ago" --no-pager 2>/dev/null | grep -ci 'out of memory\|oom-kill' ; else echo "N/A (root)"; fi
echo "-- crontabs (todas las entradas activas)"
for f in /etc/crontab /etc/cron.d/*; do [ -r "$f" ] && grep -vE '^\s*(#|$|[A-Z_]+=)' "$f" | sed "s#^#$f: #"; done 2>/dev/null | head -40
if [ "$ROOT" = yes ]; then
  for u in $(cut -d: -f1 /etc/passwd); do $SUDO crontab -l -u "$u" 2>/dev/null | grep -vE '^\s*(#|$)' | sed "s#^#crontab[$u]: #"; done | head -60
else
  crontab -l 2>/dev/null | grep -vE '^\s*(#|$)' | sed "s#^#crontab[$(id -un)]: #" | head -40
fi
echo "-- binarios/config del sistema modificados en las últimas 48 h"
$SUDO find /etc /usr/bin /usr/sbin /usr/local/bin /bin /sbin -xdev -type f -mmin -2880 2>/dev/null | grep -vE '^/etc/(ld\.so\.cache|mtab|resolv\.conf|letsencrypt/)' | head -25
echo "-- conexiones salientes establecidas (destinos únicos, sin 80/443)"
# Columnas: Recv-Q Send-Q Local Peer Process. Se descartan las entrantes (puerto local escuchando)
# y las salientes a 80/443; queda lo saliente a puertos raros, que es donde se ve un C2 o un minero.
LISTEN=$(ss -Htln 2>/dev/null | awk '{n=split($4,a,":"); print a[n]}' | sort -u | tr '\n' ' ')
$SUDO ss -Htnp state established 2>/dev/null | awk -v L=" $LISTEN " '{n=split($3,l,":"); m=split($4,p,":"); if (index(L," "l[n]" ")) next; if (p[m]==443||p[m]==80) next; pr=$5; gsub(/users:\(\("|",.*/,"",pr); print $4" "pr}' | sort | uniq -c | sort -rn | head -15

sec logs
echo "journal=$(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9.]+[KMGT]' | head -1)"
echo "-- /var/log más pesados"
$SUDO du -xsh /var/log/* 2>/dev/null | sort -rh | head -10
echo "-- archivos de log > 200 MB (cualquier parte del disco raíz, excepto docker overlay)"
$SUDO find / -xdev \( -path /proc -o -path /var/lib/docker/overlay2 \) -prune -o -type f \( -name '*.log' -o -name '*.log.*' -o -name '*-json.log' \) -size +200M -printf '%s %p\n' 2>/dev/null | sort -rn | head -12 | awk '{printf "%.0fMB %s\n",$1/1048576,$2}'
echo "-- errores de logrotate (7 días)"
if have journalctl && [ "$ROOT" = yes ]; then $T $SUDO journalctl -q -u logrotate --since "7 days ago" --no-pager 2>/dev/null | grep -iE 'error|duplicate' | tail -5
else grep -hiE 'logrotate.*(error|duplicate)' /var/log/syslog /var/log/messages 2>/dev/null | tail -5; fi
echo "-- tamaño de logs de contenedores"
if [ "$ROOT" = yes ]; then $SUDO find /var/lib/docker/containers -name '*-json.log' -size +100M -printf '%s %p\n' 2>/dev/null | sort -rn | head -8 | awk '{printf "%.0fMB %s\n",$1/1048576,$2}'; fi

sec tls
# Certificados de letsencrypt locales: días hasta vencer.
for c in $($SUDO find /etc/letsencrypt/live -name cert.pem 2>/dev/null); do
  end=$($SUDO openssl x509 -enddate -noout -in "$c" 2>/dev/null | cut -d= -f2)
  [ -n "$end" ] && echo "$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))d $(basename "$(dirname "$c")")"
done | sort -n | head -20
have certbot && [ "$ROOT" = yes ] && { systemctl is-active certbot.timer 2>/dev/null | sed 's/^/certbot_timer=/'; }

sec backups
# Último dump por directorio (30 días); el SKILL cruza esto con los backups esperados del inventario.
# Solo archivos > 100 KB (descarta migraciones/fixtures .sql del código) y fuera de /tmp.
$SUDO find / -xdev \( -path /proc -o -path /var/lib/docker -o -path /usr -o -path /snap -o -path /tmp -o -name node_modules \) -prune -o -type f \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.dump' -o -name '*.sql.zst' \) -size +100k -mtime -30 -printf '%TY-%Tm-%Td %s %p\n' 2>/dev/null | sort -r \
  | awk '{d=$3; sub(/\/[^\/]*$/,"",d); if (!(d in seen)) {seen[d]=1; printf "%s %.1fMB %s\n",$1,$2/1048576,$3}}' | head -20
} 2>/dev/null | redact
