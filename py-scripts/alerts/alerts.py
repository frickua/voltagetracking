import json
import os
import sys

import requests
from datetime import datetime, date, timezone
from dateutil import parser, tz
from supabase import Client, create_client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
EVENT_PATH = os.getenv('GITHUB_EVENT_PATH')
TZ: "Europe/Kyiv"


###############################################################
###############################################################
###############################################################

with open(EVENT_PATH) as f:
    print('########################')
    print(f.read())
    print('########################')
    payload = json.load(f)

print(payload['client_payload'])

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.table("alerts-fingerprints").select('fingerprint').execute()

fingerprints = {row["fingerprint"] for row in response.data}






