# -*- coding: utf-8 -*-
import os
import json
import discord
import asyncio
import requests
import random
from datetime import datetime, timedelta, timezone

# قراءة المتغيرات من البيئة
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
# Accept comma-separated CHANNEL_IDs, e.g. "12345,67890"
CHANNEL_IDS = os.getenv("CHANNEL_ID", "").split(",")
DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

try:
    # keep only valid integers
    CHANNEL_IDS = [int(cid.strip()) for cid in CHANNEL_IDS if cid.strip().isdigit()]
except ValueError:
    CHANNEL_IDS = []


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

def filter_special_events_week(data):
    """
    تجمع جميع الأحداث الخاصة (NFP, CPI, FOMC) للأسبوع القادم (7 أيام) بشرط أن تكون High impact.
    """
    special_keywords = ['nfp', 'cpi', 'fomc']
    special_events = []
    local_now = datetime.now()
    week_end_date = local_now.date() + timedelta(days=7)
    for event in data:
        if event.get("impact", "").strip().lower() != "high":
            continue
        title = event.get("title", "").lower()
        if any(keyword in title for keyword in special_keywords):
            try:
                event_dt = datetime.fromisoformat(event.get("date"))
                local_event_dt = event_dt.astimezone()  # تحويل للتوقيت المحلي
                if local_now.date() <= local_event_dt.date() <= week_end_date:
                    special_events.append(event)
            except Exception as e:
                debug_print(f"Error parsing date for special event: {e}")
                continue
    debug_print(f"Special events for week: {len(special_events)} found.")
    for idx, event in enumerate(special_events, start=1):
        debug_print(f"Week event {idx}: {event.get('title', 'لا يوجد')}")
    return special_events

def filter_special_events_for_tomorrow(special_events_week):
    """
    من القائمة الأسبوعية، نحتفظ بالأحداث التي ستحدث غدًا فقط.
    """
    local_now = datetime.now()
    tomorrow_date = local_now.date() + timedelta(days=1)
    events_tomorrow = []
    for event in special_events_week:
        try:
            event_dt = datetime.fromisoformat(event.get("date"))
            local_event_dt = event_dt.astimezone()
            if local_event_dt.date() == tomorrow_date:
                events_tomorrow.append(event)
        except Exception as e:
            debug_print(f"Error parsing date for special event (tomorrow filter): {e}")
            continue
    debug_print(f"Special events for tomorrow: {len(events_tomorrow)} found.")
    return events_tomorrow

def build_messages(events):
    """
    التنبيه العادي للأحداث التي تحدث خلال 35 دقيقة، بتصميم معتمد باللغة العربية.
    """
    messages = []
    now = datetime.now(timezone.utc)
    for event in events:
        title = event.get("title", "لا يوجد")
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
            f"تنبيه اقتصادي بعد {minutes} دقيقة\n\n"
            f"الحدث: {title}\n"
            f"العملة: {currency}\n"
            f"التوقع: {forecast}\n"
            f"السابق: {previous}"
        )
        messages.append(msg)
    return messages

def build_special_message(event):
    """
    تنبيه خاص للأحداث (NFP, CPI, FOMC) التي ستحدث غدًا،
    مع رسالة عشوائية من القائمة والتفاصيل الخاصة بالخبر.
    """
    special_messages = [
        "السوق اليوم يشبه فيلم رعب، وانت بطل القصة الغبي اللي يدخل القبو.",
        "السوق اليوم مو مزاجه حلو، خذلك راحة.",
        "لو تفكر تفتح صفقة، فكر مرتين.",
        "السيولة اليوم تلعب كورة، انتبه لا تكون الكرة.",
        "لو محفظتك غالية عليك، خليك متفرج اليوم.",
        "اليوم السوق يوزع دروس مجانية، بس مو شرط تكون ممتعة.",
        "ترى الستوب ما رح يكون صديقك اليوم، دير بالك.",
        "السوق عنده حفلة اليوم، وانت مو مدعو.",
        "اذا كنت تحب الأدرينالين، افتح صفقة وشوف.",
        "اليوم يوم أخبار ما رأيكم ان نأخذه اجازة؟",
        "اذا كنت حاب محفظتك روح تداول اليوم",
        "ريسك مناجمنت تاعك ما رح يحميك اليوم",
        "إذا شفت فرصة اليوم، اسأل نفسك: \"فرصة لمين؟ لي ولا للسوق؟\"",
        "لو عندك إحساس إن اليوم يوم ربح، تأكد إنه مجرد إحساس.",
        "لو كنت تفكر تربح اليوم، فكر مرة ثانية… وثالثة… وبعدين انسَ",
        "لو شفت فرصة واضحة اليوم، فاعرف أنها فخ أنيق.",
        "لو حسابك فيه شوية أمل، لا تضيعه اليوم.",
        "ستوب لوس تاعك ما رح يساعدك اليوم"
    ]
    random_message = random.choice(special_messages)
    
    title = event.get("title", "لا يوجد")
    currency = event.get("country", "غير محدد")
    forecast = event.get("forecast", "لا يوجد")
    previous = event.get("previous", "لا يوجد")
    
    msg = (
        "@everyone\n"
        f"{random_message}\n\n"
        "تنبيه: هناك خبر هام غدًا\n\n"
        f"الحدث: {title}\n"
        f"العملة: {currency}\n"
        f"التوقع: {forecast}\n"
        f"السابق: {previous}"
    )
    return msg

class MyClient(discord.Client):
    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")

        # === get all valid channel objects ===
        channels = []
        for cid in CHANNEL_IDS:
            ch = self.get_channel(cid)
            if ch:
                channels.append(ch)
            else:
                print(f"❌ Channel {cid} not found!")
        if not channels:
            await self.close()
            return

        # === fetch data once ===
        data = fetch_data()
        if not data:
            await self.close()
            return

        # === Normal alerts for high-impact events within 35 minutes ===
        high_events = filter_high_impact(data)
        ready_events = filter_events_within_35_minutes(high_events)
        if ready_events:
            messages = build_messages(ready_events)
            for ch in channels:
                for msg in messages:
                    await ch.send(msg)

        # === Gather special events (NFP, CPI, FOMC) for the week ===
        special_events_week = filter_special_events_week(data)
        special_events_tomorrow = filter_special_events_for_tomorrow(special_events_week)

        # === Between 22:00 and 22:05 local, send tomorrow’s special events ===
        local_now = datetime.now()
        if local_now.hour == 22 and local_now.minute < 5:
            debug_print(f"Special events to be sent (22:00 - 22:05): {len(special_events_tomorrow)} found.")
            for idx, event in enumerate(special_events_tomorrow, start=1):
                debug_print(f"Special event {idx}: {event.get('title', 'لا يوجد')}")
            if special_events_tomorrow:
                for ch in channels:
                    for event in special_events_tomorrow:
                        special_msg = build_special_message(event)
                        await ch.send(special_msg)

        await self.close()


    async def on_message(self, message):
        pass

if not TOKEN or TOKEN.strip() == "":
    print("❌ Discord bot token is missing or empty!")
else:
    client = MyClient(intents=intents)
    client.run(TOKEN)
