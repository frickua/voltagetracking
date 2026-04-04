import requests
import os
import uuid
import base64
import time

from postgrest import APIError
from supabase import create_client, Client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

def get_tg_updates(offset):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    resp = requests.get(URL, params=params).json()
    print(f"{resp}")
    return resp

def generate_auth_key():
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).rstrip(b'=').decode('ascii')

def send_tg_msg(chat_id, txt, parse_mode='TEXT'):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": txt,
        "parse_mode": parse_mode
    }
    response = requests.post(url, data=payload)
    print(response.json())

def send_welcome_msg(chat_id, auth_key):
    send_tg_msg(chat_id,
"👋 Привіт! Дякую, за цікавість до проєкту моніторингу напруги в енергосистемі.\n "
                "Цей проєкт дозволить тобі та твоїм сусідам, слідкувати за рівнем напруги у вашій оселі, та попередити аварійні ситуації.\n\n"
                f"Твій унікальний ключ для надсилання даних: {auth_key}\n"
                f"Тепер ти можеш надсилати дані своєї напруги в ситему\n\n"
                f"Для цього використовуй HTTP POST запит https://metrics.voltagetracking.frick.net.ua/api/v1/push/influx/write\n"
                "Обов'язково додай заголовок, для авторизаціі"
                "<pre>Authorization: Basic {TOKEN}</pre>"
                f"Тіло запиту(body):"
                f"<pre><code>voltage,key={auth_key},phase=1 value=242.7</code></pre>\n\n"
                "❗️Звернись за секретним токеном {TOKEN} до @frickua, наразі це відбувається вручну\n\n"
                "❔Більше інформаціі тут: https://voltagetracking.frick.net.ua", 'HTML')


offset = None

resp = get_tg_updates(offset)

for update in resp["result"]:
    offset = update["update_id"] + 1

    if "my_chat_member" in update:
        chat_member = update["my_chat_member"]

        chat_member_from = chat_member['from']
        chat = chat_member["chat"]
        new_status = chat_member["new_chat_member"]["status"]
        old_status = chat_member["old_chat_member"]["status"]

        #TODO: verify that bot has admin rights
        if new_status in ["administrator", "member"]:
            print(f"✅ Bot added to channel: {chat['title']} ({chat['id']})")
            auth_key = generate_auth_key()
            try:
                response = supabase.table("tg_channels").insert(
                    {"chat_id": chat['id'],
                     "chat_name": chat['title'],
                     "chat_type": chat['type'],
                     "tg_user_id": chat_member_from['id'],
                     "tg_user_info": f"@{chat_member_from['username']} ({chat_member_from['first_name']})",
                     "auth_key": auth_key}).execute()
            except APIError as e:
                if e.message and 'duplicate key' in e.message:
                    response = supabase.table("tg_channels").select('auth_key').eq("chat_id", chat['id']).execute()
                auth_key = response.data[0]['auth_key']

            print(response)

            send_welcome_msg(chat_member_from['id'], auth_key)

        elif new_status in ["left", "kicked"]:
            print(f"❌ Bot removed from channel: {chat['title']} ({chat['id']})")
            response = (
                supabase.table("tg_channels")
                .update({"removed_at": time.time()})
                .eq("chat_id", chat['id'])
                .execute()
            )
            print(response)

    if 'message' in update:
        msg = update['message']
        if 'text' in msg and msg['text'] == '/start':
            response = supabase.table("tg_channels").select('auth_key', 'tg_user_id').eq("tg_user_id", msg['from']['id']).execute()
            if response and len(response.data) == 1:
                data = response.data[0]
                if  data['auth_key'] and data['tg_user_id']:
                    send_welcome_msg(data['tg_user_id'], data['auth_key'])
            else:
                send_tg_msg(msg['from']['id'],
                            "😔 Вибач, я не знайшов твій канал або групу. Додай мене адміністратором до каналу або групи в якій ти хочеш бачити графіки та сповіщення про напругу.\n"
                            "Наразі лише той адміністратор який додав бота \"прив'язується\" до системи.\n"
                            "Чекаю☺️")

# Consume(mark as dispatched) all received updates
get_tg_updates(offset)