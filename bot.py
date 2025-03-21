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

        if timedelta(0) <= delta <= timedelta(minutes=3000):
            ready.append(event)

    debug_print(f"Events within 35 minutes: {len(ready)} found.")
    return ready

def filter_special_events(data):
    """
    نحتفظ بالأحداث الخاصة (NFP, CPI, FOMC) التي تكون ليوم الغد حسب التوقيت المحلي
    """
    special_keywords = ['nfp', 'cpi', 'fomc']
    special_events = []
    local_now = datetime.now()
    tomorrow_date = local_now.date() + timedelta(days=1)
    for event in data:
        title = event.get("title", "").lower()
        if any(keyword in title for keyword in special_keywords):
            try:
                event_dt = datetime.fromisoformat(event.get("date"))
                # تحويل التاريخ للتوقيت المحلي
                local_event_dt = event_dt.astimezone()
                if local_event_dt.date() == tomorrow_date:
                    special_events.append(event)
            except Exception as e:
                debug_print(f"Error parsing date for special event: {e}")
                continue
    debug_print(f"Special events for tomorrow: {len(special_events)} found.")
    return special_events

def build_messages(events):
    """
    التنبيه العادي للأحداث التي تحدث خلال 35 دقيقة، بتصميم معتمد باللغة العربية
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
    تنبيه خاص للأحداث (NFP, CPI, FOMC) ليوم الغد عند الساعة 23:00،
    مع رسالة عشوائية من القائمة والتفاصيل الخاصة بالخبر.
    """
    # قائمة الرسائل الخاصة
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
    
    # تصميم التنبيه الخاص باللغة العربية
    msg = (
        "@everyone\n"
        f"{random_message}\n\n"
        "تنبيه: غداً يوجد خبر هام\n\n"
        f"الحدث: {title}\n"
        f"العملة: {currency}\n"
        f"التوقع: {forecast}\n"
        f"السابق: {previous}"
    )
    return msg

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

        # التنبيه العادي للأحداث خلال 35 دقيقة
        high_events = filter_high_impact(data)
        ready_events = filter_events_within_35_minutes(high_events)
        if ready_events:
            messages = build_messages(ready_events)
            for msg in messages:
                await channel.send(msg)

        # التنبيه الخاص للأحداث (NFP, CPI, FOMC) ليوم الغد عند الساعة 23:00
        local_now = datetime.now()
        if local_now.hour == 23:
            special_events = filter_special_events(data)
            if special_events:
                for event in special_events:
                    special_msg = build_special_message(event)
                    await channel.send(special_msg)

        # إذا لم توجد أحداث قادمة خلال 35 دقيقة، أو لا يوجد أحداث خاصة عند 23:00، لا يتم إرسال أي رسالة.
        await self.close()

    async def on_message(self, message):
        pass

if not TOKEN or TOKEN.strip() == "":
    print("❌ Discord bot token is missing or empty!")
else:
    client = MyClient(intents=intents)
    client.run(TOKEN)
