import json
import os

import requests
from datetime import datetime, timezone, timedelta
from supabase import Client, create_client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
EVENT_PATH = os.getenv('GITHUB_EVENT_PATH')
TZ: "Europe/Kyiv"


def update_fingerprints(fingerprints):
    # Update fingerprints
    old_fingerprints_ts = datetime.now(timezone.utc) - timedelta(hours=5)

    # Delete rows older than 5 hours
    supabase.table("alerts-fingerprints").delete().lt("created_at", old_fingerprints_ts.isoformat()).execute()
    if len(fingerprints) > 0:
        data = [{"fingerprint": k, "status": v} for k, v in fingerprints.items()]
        supabase.table("alerts-fingerprints").upsert(data, on_conflict="fingerprint,status").execute()

def send_tg_msgs(chats, txt, parse_mode='TEXT'):
    for chat in chats:
        send_tg_msg(chat['chat_id'], chat['topic'], txt, parse_mode)

def send_tg_msg(chat_id, topic=None, txt=None, parse_mode='TEXT'):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": txt,
        "message_thread_id": topic,
        "parse_mode": parse_mode
    }
    response = requests.post(url, data=payload)
    print(response.json())

with open(EVENT_PATH) as f:
    payload = json.load(f)

alerts = payload['client_payload']['alerts']
print(payload['client_payload']['alerts'])

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
response = supabase.table("tg_channels").select('auth_key', 'chat_id', 'tg_topic').execute()
keys_to_channels = {}
for row in response.data:
    keys_to_channels.setdefault(row["auth_key"], []).append({
        "chat_id": row["chat_id"],
        "topic": row["tg_topic"]
    })

response = supabase.table("alerts-fingerprints").select('fingerprint', 'status').execute()
fingerprints = {row["fingerprint"]: row["status"] for row in response.data}

for alert in alerts:
    status = alert['status']
    value = alert['values']['A']
    fingerprint = alert['fingerprint']
    key = alert['labels']['key']
    phase = alert['labels']['phase']
    channels = keys_to_channels.get(key)
    print(f"{status} {value} {fingerprint} {key}")
    info_link = "<i>\n<blockquote expandable>📌Попередження - інформативне, ваша оселя може бути підключена до іншої фази або навіть до іншої підстанціі.\nСприймайте це сповіщення як погоду - загальну картину стану енергоситеми зараз.\nДля надійного захисту використовуйте <b>реле напруги</b> та <b>стабілізатори</b><a href=\"https://voltagetracking.frick.net.ua/voltage-infographic.html?v=1\">.</a></blockquote></i>"
    if status == 'firing':
        if fingerprint not in fingerprints: # Verify that alert already processed
            fingerprints[fingerprint] = status # Add new fingerprint
            if channels and len(channels) > 0:
                txt = ""
                if value > 230:
                    txt = "🔺 Підвищена "
                else:
                    txt = "🔻 Знижена "
                send_tg_msgs(channels, f"{txt} напруга: {value} Вольт\nФаза: {phase}\n\n{info_link}\n#voltage #voltage_alerts #voltage_alerts_firing", 'HTML')
            else:
                print(f"Channel not found {key} {fingerprint}")
    elif status == 'resolved':
        if fingerprint not in fingerprints or fingerprints[fingerprint] != 'resolved':
            fingerprints[fingerprint] = status
            send_tg_msgs(channels, f"✅ Напруга стабілізувалась: {value} Вольт\nФаза: {phase}\n\n{info_link}#voltage #voltage_alerts #voltage_alerts_resolved", 'HTML')
    else:
        print(f"Unknown status: {status}")

update_fingerprints(fingerprints)



