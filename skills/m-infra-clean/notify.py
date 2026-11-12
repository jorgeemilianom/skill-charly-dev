#!/usr/bin/env python3
"""Envía el aviso de una corrida (memory/infra/last-notify.json) según INFRA_NOTIFY_MODE de config.sh.

Uso: notify.py <last-notify.json>    (las variables INFRA_NOTIFY_* llegan por entorno desde run.sh)

Modos:
- `webhook` (default si solo está INFRA_NOTIFY_WEBHOOK): POST del JSON tal cual
  (project/status/commit/actor/message).
- `evolution-bot`: entrega el texto a un bot de WhatsApp montado en n8n sobre Evolution API, con el
  mismo payload que usa un backoffice para "enviar mensaje inmediato": un evento `messages.upsert` cuyo
  `remoteJid` es el destinatario y `message.conversation` el texto, con `Authorization: Bearer <token>`.
  Requiere INFRA_NOTIFY_BOT_ENDPOINT, INFRA_NOTIFY_BOT_TOKEN, INFRA_NOTIFY_PHONE; opcionales
  INFRA_NOTIFY_BOT_INSTANCE, INFRA_NOTIFY_BOT_SERVER_URL e INFRA_NOTIFY_BOT_TEMPLATE (ruta a una plantilla
  JSON privada con el payload exacto que el flujo del bot ya acepta — ver bot_payload()).

- `mcp-whatsapp`: llama por JSON-RPC (`tools/call`) a una herramienta MCP que agenda un WhatsApp
  (`phone_number`, `message`, `bot_id`, `scheduled_date`), autenticada con `Authorization: Bearer <api_key>`.
  La entrega la hace el propio backend (su cron de mensajes programados), así que puede demorar unos
  minutos. Requiere INFRA_NOTIFY_MCP_URL, INFRA_NOTIFY_MCP_KEY, INFRA_NOTIFY_BOT_ID, INFRA_NOTIFY_PHONE;
  opcional INFRA_NOTIFY_MCP_TOOL (default whatsapp_send_message).

Nunca imprime la URL, el token ni la API key: solo el código HTTP o el error que devuelve el servidor.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone


def post(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          # El UA por defecto (Python-urllib) lo bloquea el WAF de Cloudflare con 403.
                                          "User-Agent": "m-infra-clean/1.0", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        body = e.read(300).decode("utf-8", "replace").strip()
        return f"{e.code} {body}" if body else e.code
    except Exception as e:  # red caída, DNS, timeout
        return f"error ({type(e).__name__})"


def evolution_payload(text, env):
    # Réplica fiel del payload de "enviar mensaje inmediato" del backoffice: los flujos n8n de los
    # bots leen campos de todo el evento (no solo key/message), y con una versión recortada fallan (500).
    phone = env["INFRA_NOTIFY_PHONE"]
    jid = f"{phone}@s.whatsapp.net"
    endpoint = env["INFRA_NOTIFY_BOT_ENDPOINT"]
    server = env.get("INFRA_NOTIFY_BOT_SERVER_URL", "")
    host = server.split("://", 1)[-1].split("/", 1)[0]
    now = int(time.time())
    return [{
        "headers": {"host": host, "content-type": "application/json", "accept": "application/json, text/plain, */*",
                    "x-forwarded-host": host, "x-forwarded-port": "443", "x-forwarded-proto": "https"},
        "params": {},
        "query": {},
        "body": {
            "event": "messages.upsert",
            "instance": env.get("INFRA_NOTIFY_BOT_INSTANCE") or "m-infra-clean",
            "data": {
                "key": {"remoteJid": jid, "fromMe": False, "id": uuid.uuid4().hex[:22].upper(),
                        "senderLid": ""},
                "pushName": "BusinessHubCorp User",
                "status": "DELIVERY_ACK",
                "message": {
                    "messageContextInfo": {
                        "deviceListMetadata": {"senderAccountType": "E2EE", "receiverAccountType": "E2EE",
                                               "senderTimestamp": str(now), "recipientTimestamp": str(now)},
                        "deviceListMetadataVersion": 2,
                    },
                    "conversation": text,
                },
                "contextInfo": {"ephemeralSettingTimestamp": str(now),
                                "disappearingMode": {"initiator": "CHANGED_IN_CHAT", "trigger": "CHAT_SETTING",
                                                     "initiatedByMe": True}},
                "messageType": "conversation",
                "messageTimestamp": now,
                "instanceId": str(uuid.uuid4()),
                "source": "web",
            },
            "destination": endpoint,
            "date_time": datetime.now(timezone.utc).isoformat(),
            "sender": jid,
            "server_url": server,
            "apikey": env["INFRA_NOTIFY_BOT_TOKEN"],
        },
        "webhookUrl": endpoint,
        "executionMode": "production",
    }]


def fill(node, values):
    """Reemplaza {{CLAVE}} en todos los strings; un string que es solo "{{TS}}" pasa a entero."""
    if isinstance(node, dict):
        return {k: fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, values) for v in node]
    if isinstance(node, str):
        if node == "{{TS}}":
            return values["TS"]
        for k, v in values.items():
            node = node.replace("{{" + k + "}}", str(v))
    return node


def bot_payload(text, env):
    """Si INFRA_NOTIFY_BOT_TEMPLATE apunta a un JSON, usa esa plantilla (copia exacta del payload que el
    flujo del bot ya acepta, con {{PHONE}} {{TEXT}} {{TS}} {{DATE}} {{ENDPOINT}} {{TOKEN}} {{INSTANCE}});
    si no, el payload genérico de evolution_payload()."""
    tpl = env.get("INFRA_NOTIFY_BOT_TEMPLATE")
    if not tpl:
        return evolution_payload(text, env)
    return fill(json.load(open(tpl, encoding="utf-8")), {
        "PHONE": env["INFRA_NOTIFY_PHONE"], "TEXT": text, "TS": int(time.time()),
        "DATE": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ENDPOINT": env["INFRA_NOTIFY_BOT_ENDPOINT"], "TOKEN": env["INFRA_NOTIFY_BOT_TOKEN"],
        "INSTANCE": env.get("INFRA_NOTIFY_BOT_INSTANCE") or "m-infra-clean",
    })


def mcp_call(text, env):
    # scheduled_date en hora argentina (UTC-3): queda en el pasado o en el presente para cualquier servidor
    # en UTC-3 o más al este, así que el cron de mensajes programados lo toma en su próxima pasada.
    when = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": env.get("INFRA_NOTIFY_MCP_TOOL") or "whatsapp_send_message",
        "arguments": {"phone_number": env["INFRA_NOTIFY_PHONE"], "message": text,
                      "bot_id": int(env["INFRA_NOTIFY_BOT_ID"]), "scheduled_date": when}}}
    req = urllib.request.Request(env["INFRA_NOTIFY_MCP_URL"], data=json.dumps(rpc, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json",
                                                         "Accept": "application/json, text/event-stream",
                                                         "User-Agent": "m-infra-clean/1.0",
                                                         "Authorization": "Bearer " + env["INFRA_NOTIFY_MCP_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return f"{e.code} {e.read(300).decode('utf-8', 'replace').strip()}"
    except Exception as e:
        return f"error ({type(e).__name__})"
    # Respuesta JSON-RPC (puede venir como evento SSE `data: {...}`): error del protocolo o de la herramienta.
    raw = next((l[5:].strip() for l in body.splitlines() if l.startswith("data:")), body)
    try:
        res = json.loads(raw)
    except ValueError:
        return f"respuesta ilegible: {body[:200]}"
    if "error" in res:
        return f"error MCP: {res['error'].get('message', res['error'])}"
    result = res.get("result", {})
    if result.get("isError"):
        txt = " ".join(c.get("text", "") for c in result.get("content", []))
        return f"error de la herramienta: {txt[:300]}"
    return 200


def main():
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    env = os.environ
    mode = env.get("INFRA_NOTIFY_MODE") or ("webhook" if env.get("INFRA_NOTIFY_WEBHOOK") else "")
    if mode == "evolution-bot":
        missing = [k for k in ("INFRA_NOTIFY_BOT_ENDPOINT", "INFRA_NOTIFY_BOT_TOKEN", "INFRA_NOTIFY_PHONE") if not env.get(k)]
        if missing:
            print("aviso: faltan " + ", ".join(missing) + " en config.sh")
            return 1
        code = post(env["INFRA_NOTIFY_BOT_ENDPOINT"], bot_payload(payload["message"], env),
                    {"Authorization": "Bearer " + env["INFRA_NOTIFY_BOT_TOKEN"]})
    elif mode == "mcp-whatsapp":
        missing = [k for k in ("INFRA_NOTIFY_MCP_URL", "INFRA_NOTIFY_MCP_KEY", "INFRA_NOTIFY_BOT_ID", "INFRA_NOTIFY_PHONE") if not env.get(k)]
        if missing:
            print("aviso: faltan " + ", ".join(missing) + " en config.sh")
            return 1
        code = mcp_call(payload["message"], env)
    elif mode == "webhook":
        code = post(env["INFRA_NOTIFY_WEBHOOK"], payload, {})
    else:
        return 0
    print(f"aviso ({mode}): HTTP {code}")
    return 0 if code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
