import json
import os

import requests
from datetime import datetime, date, timezone
from dateutil import parser, tz
from supabase import Client, create_client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
GRAFANA_TOKEN = os.getenv('GRAFANA_TOKEN')
TZ: "Europe/Kyiv" #TODO: move to env variables
def parse_db_timestamp(db):
    if not db:
        return None
    db_utc = parser.isoparse(db)
    return db_utc.astimezone(tz.tzlocal())

def local_midnight():
    return datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def generate_channel_chart(key):

    grafana_url = (
        "https://voltagetracking.grafana.net/render/d-solo/vogh9ws/voltage"
        f"?orgId=1&from={local_midnight()}&to=now&panelId=1&tz=Europe%2FKyiv&var-key={key}&var-phase=$__all"
    )

    headers = {
        "Authorization": f"Bearer {GRAFANA_TOKEN}"
    }

    with requests.get(grafana_url, headers=headers, stream=True) as response:
        response.raise_for_status()
        image_path = f"{key}.png"
        with open(image_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

def update_chart_tg(msg_id, chat_id, key, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageMedia"
    files = {'photo': open(f"{key}.png", 'rb')}
    data = {
        'chat_id': chat_id,
        'message_id': msg_id,
        'media': json.dumps({
            'type': 'photo',
            'media': 'attach://photo',
            'caption': caption
        })
    }
    r = requests.post(url, data=data, files=files)
    print(r.json())

def send_chart_tg(chat_id, key, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(f"{key}.png", 'rb') as f:
        r = requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files={'photo': f})
    print(r.json())
    msg_id = r.json().get('result', {}).get('message_id')
    return msg_id

def pin_tg_msg(chat_id, msg_id, unpin=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{ 'un' if unpin else '' }pinChatMessage"

    data = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "disable_notification": True
    }
    r = requests.post(url, data=data)
    print(r.json())



supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.table("tg_channels").select('*').execute()
db_updates = []
    # {"id": 1, "value": "foo", "status": "active"},
    # {"id": 2, "value": "bar", "status": "inactive"},

for row in response.data:
    print(row)
    key = row['auth_key'];
    generate_channel_chart(key)
    caption = f"📊 Статистика напруги. Оновлено: {datetime.now().strftime('%H:%M')} (Дата: {date.today()})"
    msg_updated = parse_db_timestamp(row['chart_msg_updated'])
    if row['chart_msg_id'] and msg_updated and msg_updated.date() == date.today():
        update_chart_tg(row['chart_msg_id'], row['chat_id'], key, caption)
        db_updates.append({"id": row['id'], "chart_msg_updated": datetime.now(tz.tzlocal()).isoformat()})
    else:
        msg_id = send_chart_tg(row['chat_id'], key, caption)
        db_updates.append({"id": row['id'], "chart_msg_id": msg_id, "chart_msg_updated": datetime.now(tz.tzlocal()).isoformat()})
        if row['chart_msg_id'] :
            pin_tg_msg(row['chat_id'], row['chart_msg_id'], True)
        pin_tg_msg(row['chat_id'], msg_id)

supabase.table("tg_channels").upsert(db_updates, on_conflict="id").execute()

