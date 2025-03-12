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
DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

try:
    CHANNEL_ID = int(CHANNEL_ID)
except ValueError:
    CHANNEL_ID = 0

# رابط البيانات بصيغة JSON
DATA_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

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
    # نحتفظ فقط بالأحداث التي يكون تأثيرها "High" (بالحروف الصغيرة)
    high_events = [event for event in data if event.get("impact", "").strip().lower() == "high"]
    debug_print(f"Filtered high impact events: {len(high_events)} found.")
    return high_events

def filter_events_within_one_hour(events):
    ready = []
    now = datetime.now(timezone.utc)
    debug_print(f"Current UTC time: {now.isoformat()}")
    for event in events:
        date_str = event.get("date")
        try:
            # تحويل التاريخ بصيغة ISO مع الـ offset
            event_dt = datetime.fromisoformat(date_str)
        except Exception as e:
            debug_print(f"Error parsing date '{date_str}': {e}")
            continue
        event_utc = event_dt.astimezone(timezone.utc)
        delta = event_utc - now
        debug_print(f"Event '{event.get('title')}' at {event_utc.isoformat()} (delta: {delta})")
        # نحتفظ بالأحداث التي ستكون خلال الساعة القادمة (بعد الآن وأقل من ساعة)
        if timedelta(0) <= delta <= timedelta(hours=1):
            ready.append(event)
    debug_print(f"Events within one hour: {len(ready)} found.")
    return ready

def build_messages(events):
    messages = []
    for idx, event in enumerate(events, start=1):
        title = event.get("title", "لا يوجد")
        country = event.get("country", "غير محدد")
        forecast = event.get("forecast", "لا يوجد")
        previous = event.get("previous", "لا يوجد")
        try:
            event_dt = datetime.fromisoformat(event.get("date"))
            # تنسيق التاريخ - يمكنك تعديل التنسيق حسب رغبتك
            date_formatted = event_dt.strftime("%a %d %b %Y %I:%M %p")
        except Exception:
            date_formatted = event.get("date", "غير متوفر")
        msg = (
            "@everyone\n"
            f"{idx}. **{title}** ({country})\n"
            f"التاريخ: {date_formatted}\n"
            f"التوقع: {forecast}\n"
            f"السابق: {previous}\n"
            f"التأثير: High\n"
            "--------------------------------------\n"
        )
        messages.append(msg)
    return messages

class MyClient(discord.Client):
    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            print(f"Channel found: {channel.name}")
            await channel.send("🤖 **Forex News Bot is Running (JSON Version)**")
        else:
            print("❌ Channel not found!")
            await self.close()
            return

        data = fetch_data()
        if not data:
            await channel.send("❌ لا توجد بيانات.")
            await self.close()
            return

        high_events = filter_high_impact(data)
        ready_events = filter_events_within_one_hour(high_events)
        if ready_events:
            messages = build_messages(ready_events)
            for msg in messages:
                await channel.send(msg)
        else:
            await channel.send("❌ لا توجد أخبار عالية التأثير خلال الساعة القادمة.")
        await self.close()

    async def on_message(self, message):
        pass

if not TOKEN or TOKEN.strip() == "":
    print("❌ Discord bot token is missing or empty!")
else:
    client = MyClient(intents=intents)
    client.run(TOKEN)
