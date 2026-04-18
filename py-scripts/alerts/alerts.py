import json
import os

import requests
from datetime import datetime, timezone, timedelta
from supabase import Client, create_client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
EVENT_PATH = os.getenv('GITHUB_EVENT_PATH')
TZ = "Europe/Kyiv"


def update_fingerprints(fingerprints):
    # Update fingerprints
    old_fingerprints_ts = datetime.now(timezone.utc) - timedelta(hours=5)

    # cleanup old rows
    supabase.table("alerts-fingerprints") \
        .delete() \
        .lt("created_at", old_fingerprints_ts.isoformat()) \
        .execute()

    if fingerprints:
        data = [
            {
                "fingerprint": k,
                "status": v["status"],
                "starts_at": v["starts_at"].isoformat() if v["starts_at"] else None
            }
            for k, v in fingerprints.items()
        ]

        supabase.table("alerts-fingerprints") \
            .upsert(data, on_conflict="fingerprint,starts_at") \
            .execute()


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

def parse_dt(ts: str) -> datetime:
    ts = ts.replace(" UTC", "")
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S %z")

with open(EVENT_PATH) as f:
    payload = json.load(f)

alerts = payload['client_payload']['alerts']
print(alerts)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
response = supabase.table("tg_channels").select('auth_key', 'chat_id', 'tg_topic').execute()
keys_to_channels = {}
for row in response.data:
    keys_to_channels.setdefault(row["auth_key"], []).append({
        "chat_id": row["chat_id"],
        "topic": row["tg_topic"]
    })

# Load stored fingerprints
response = supabase.table("alerts-fingerprints").select('fingerprint', 'status', 'starts_at').execute()
fingerprints = {
    row["fingerprint"]: {
        "status": row["status"],
        "starts_at": row["starts_at"]
    }
    for row in response.data
}

print(f"Old fingerprints: {fingerprints}")

# Common text
info_link = "<i>\n<blockquote expandable>📌Попередження - інформативне, ваша оселя може бути підключена до іншої фази або навіть до іншої підстанціі.\nСприймайте це сповіщення як погоду - загальну картину стану енергоситеми зараз.\nДля надійного захисту використовуйте <b>реле напруги</b> та <b>стабілізатори</b><a href=\"https://voltagetracking.frick.net.ua/voltage-infographic.html?v=1\">.</a></blockquote></i>"

# Process alerts
for alert in alerts:
    status = alert['status']
    value = alert['values']['A']
    fingerprint = alert['fingerprint']
    starts_at = parse_dt(alert['startsAt'])
    key = alert['labels']['key']
    phase = alert['labels']['phase']

    channels = keys_to_channels.get(key)

    print(f"{status} {value} {fingerprint} {starts_at} {key}")

    old = fingerprints.get(fingerprint)

    if status == 'firing':
        # process only NEW alert (new startsAt)
        if not old or old["starts_at"] != starts_at:
            fingerprints[fingerprint] = {
                "status": status,
                "starts_at": starts_at
            }

            if channels:
                txt = "🔺 Підвищена " if value > 230 else "🔻 Знижена "
                send_tg_msgs(
                    channels,
                    f"{txt} напруга: {value} Вольт\nФаза: {phase}\n\n{info_link}\n#voltage #voltage_alerts #voltage_alerts_firing",
                    'HTML'
                )
            else:
                print(f"Channel not found {key} {fingerprint}")
        else:
            print(f"Skipped duplicate firing: {fingerprint}")

    elif status == 'resolved':
        if not old or old["status"] != 'resolved' or old["starts_at"] != starts_at:
            fingerprints[fingerprint] = {
                "status": status,
                "starts_at": starts_at
            }

            if channels:
                send_tg_msgs(
                    channels,
                    f"✅ Напруга стабілізувалась: {value} Вольт\nФаза: {phase}\n\n{info_link}#voltage #voltage_alerts #voltage_alerts_resolved",
                    'HTML'
                )
        else:
            print(f"Fingerprint skipped: {fingerprints[fingerprint]}")
    else:
        print(f"Unknown status: {status}")

update_fingerprints(fingerprints)



