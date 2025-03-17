# -*- coding: utf-8 -*-
import os
import json
import discord
import asyncio
import requests
from datetime import datetime, timedelta, timezone

# قراءة المتغيرات من البيئة
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "0")
DATA_URL = os.getenv("DATA_URL")
DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

if not DATA_URL or not DATA_URL.strip():
    print("❌ Data URL is missing or empty!")
    exit(1)

try:
    CHANNEL_ID = int(CHANNEL_ID)
except ValueError:
    CHANNEL_ID = 0

intents = discord.Intents.default()

def debug_print(msg):
    if DEBUG_MODE:
        print("[DEBUG]", msg)

def fetch_data():
    debug_print("Fetching data from JSON endpoint.")
    try:
        response = requests.get(DATA_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        debug_print(f"Retrieved {len(data)} items from JSON endpoint.")
        return data
    except Exception as e:
        debug_print(f"Error fetching data: {e}")
        return []

def filter_high_impact(data):
    high_events = [event for event in data if event.get("impact", "").strip().lower() == "high"]
    debug_print(f"Filtered high impact events: {len(high_events)} found.")
    return high_events

def filter_events_within_35_minutes(events):
    """
    نحتفظ بالأحداث التي ستحدث خلال 35 دقيقة أو أقل
    """
    ready = []
    now = datetime.now(timezone.utc)
    debug_print(f"Current UTC time: {now.isoformat()}")

    for event in events:
        date_str = event.get("date")
        try:
            event_dt = datetime.fromisoformat(date_str)
        except Exception as e:
            debug_print(f"Error parsing date '{date_str}': {e}")
            continue

        event_utc = event_dt.astimezone(timezone.utc)
        delta = event_utc - now
        debug_print(f"Event '{event.get('title')}' at {event_utc.isoformat()} (delta: {delta})")

        if timedelta(0) <= delta <= timedelta(minutes=35):
            ready.append(event)

    debug_print(f"Events within 35 minutes: {len(ready)} found.")
    return ready

def build_messages(events):
    messages = []
    now = datetime.now(timezone.utc)
    for idx, event in enumerate(events, start=1):
        title = event.get("title", "لا يوجد")
        # استخدام حقل 'country' كعملة (currency)
        currency = event.get("country", "غير محدد")
        forecast = event.get("forecast", "لا يوجد")
        previous = event.get("previous", "لا يوجد")
        try:
            event_dt = datetime.fromisoformat(event.get("date"))
            event_utc = event_dt.astimezone(timezone.utc)
            delta = event_utc - now
            minutes = int(delta.total_seconds() // 60)
        except Exception:
            minutes = "غير متوفر"

        msg = (
            "@everyone\n"
            "╔═══════════════════════════════╗\n"
            f"   🚨 تنبيه اقتصادي بعد {minutes} دقيقة 🚨\n"
            "╚═══════════════════════════════╝\n"
            f"**Event**: {title}\n"
            f"**Currency**: {currency}\n"
            f"**Forecast**: {forecast}\n"
            f"**Previous**: {previous}"
        )
        messages.append(msg)
    return messages

class MyClient(discord.Client):
    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            print("❌ Channel not found!")
            await self.close()
            return

        data = fetch_data()
        if not data:
            await self.close()
            return

        high_events = filter_high_impact(data)
        ready_events = filter_events_within_35_minutes(high_events)
        if ready_events:
            messages = build_messages(ready_events)
            for msg in messages:
                await channel.send(msg)

        # إذا لم توجد أحداث قادمة خلال 35 دقيقة، لن يتم إرسال أي رسالة.
        await self.close()

    async def on_message(self, message):
        pass

if not TOKEN or TOKEN.strip() == "":
    print("❌ Discord bot token is missing or empty!")
else:
    client = MyClient(intents=intents)
    client.run(TOKEN)
