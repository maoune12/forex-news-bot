# bot.py
# -*- coding: utf-8 -*-
import os
import discord
import requests
from bs4 import BeautifulSoup
import re
import asyncio
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    import undetected_chromedriver as uc
    USE_UC = True
except ImportError:
    USE_UC = False

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

import chromedriver_autoinstaller

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")  # احصل على التوكن من متغير البيئة
CHANNEL_ID = 1237965762396946445
DEBUG_MODE = True

def get_common_chrome_options():
    options = Options()
    if DEBUG_MODE:
        options.headless = False
    else:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options

def slow_scroll(driver, step=500, delay=1, down_iterations=5, up_iterations=5):
    if DEBUG_MODE:
        print("Starting slow scroll.")
    for i in range(down_iterations):
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(delay)
        if DEBUG_MODE:
            print(f"Down scroll {i+1} done.")
    for i in range(up_iterations):
        driver.execute_script(f"window.scrollBy(0, -{step});")
        time.sleep(delay)
        if DEBUG_MODE:
            print(f"Up scroll {i+1} done.")
    final_pos = driver.execute_script("return window.pageYOffset;")
    if DEBUG_MODE:
        print("Slow scroll completed. Final Y-offset:", final_pos)

def fix_date_string(s):
    s = s.strip()
    if len(s) >= 7 and s[0:3].isalpha() and s[3] == " " and s[4:7].isalpha():
        return s[0:3] + s[4:]
    return s

def parse_event_datetime(dt_str):
    dt_str = dt_str.replace("All Day", "").strip()
    current_year = datetime.now().year
    for fmt in ("%a%b%d %H:%M", "%a%b%d %I:%M %p"):
        try:
            return datetime.strptime(f"{dt_str} {current_year}", f"{fmt} %Y")
        except Exception:
            continue
    if DEBUG_MODE:
        print("Failed to parse event datetime for:", dt_str)
    return None

def parse_value(s):
    s = s.strip()
    if s.endswith("M"):
        s = s.replace("M", "")
    elif s.endswith("K"):
        s = s.replace("K", "")
    elif s.endswith("B"):
        s = s.replace("B", "")
    return float(s) if s else 0.0

def scrape_forexfactory():
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive"
    }
    html = None
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            response.encoding = "utf-8"
            html = response.text
        else:
            raise Exception(f"Status code: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Requests failed: {e}")

    if html is None:
        # fallback to Selenium if needed
        if USE_UC:
            try:
                print("Using undetected_chromedriver for fallback.")
                uc_options = uc.ChromeOptions()
                if DEBUG_MODE:
                    uc_options.headless = False
                else:
                    uc_options.add_argument("--headless=new")
                uc_options.add_argument("--no-sandbox")
                uc_options.add_argument("--disable-dev-shm-usage")
                uc_options.add_argument("--disable-blink-features=AutomationControlled")
                driver = uc.Chrome(options=uc_options)
                driver.get(url)
                slow_scroll(driver)
                WebDriverWait(driver, 45).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr.calendar__row:has(td.calendar__currency)"))
                )
                html = driver.page_source
                driver.quit()
            except Exception as e_uc:
                print(f"undetected_chromedriver failed: {e_uc}. Trying standard Selenium fallback.")
        if html is None:
            try:
                print("Using standard Selenium fallback.")
                chrome_options = get_common_chrome_options()
                driver_path = chromedriver_autoinstaller.install()
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.get(url)
                slow_scroll(driver)
                WebDriverWait(driver, 45).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr.calendar__row:has(td.calendar__currency)"))
                )
                html = driver.page_source
                driver.quit()
            except Exception as se:
                print(f"⚠️ Selenium fallback failed: {se}")
                return []

    if not html:
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    all_rows = soup.select("tr.calendar__row")
    if DEBUG_MODE:
        print(f"Processing {len(all_rows)} calendar rows.")

    news_data = []
    for row in all_rows:
        currency_elem = row.select_one("td.calendar__currency")
        if not currency_elem:
            continue

        time_elem = row.select_one("td.calendar__time")
        row_time = time_elem.get_text(strip=True) if time_elem else ""
        date_cell = row.select_one("td.calendar__date")
        if not date_cell:
            continue
        current_day = fix_date_string(date_cell.get_text(strip=True))

        if row_time.lower() == "all day":
            date_time_str = f"{current_day} All Day"
        elif row_time and row_time.lower() not in ["n/a", "لا يوجد"]:
            date_time_str = f"{current_day} {row_time}"
        else:
            date_time_str = current_day

        event_elem = row.select_one("td.calendar__event")
        event = event_elem.get_text(strip=True) if event_elem else "لا يوجد"

        impact_elem = row.select_one("td.calendar__impact span")
        if impact_elem:
            impact = impact_elem.get("title", "").strip()
            if not impact:
                impact = impact_elem.text.strip()
        else:
            impact = "Low Impact Expected"
        if DEBUG_MODE:
            print("Row impact text:", impact)
        if "high" not in impact.lower():
            continue

        impact_symbol = "🔴" if "high" in impact.lower() else ("🟡" if "medium" in impact.lower() else "⚪")

        actual_elem = row.select_one("td.calendar__actual")
        actual = actual_elem.get_text(strip=True) if actual_elem else "لا يوجد"

        forecast_elem = row.select_one("td.calendar__forecast")
        forecast = forecast_elem.get_text(strip=True) if forecast_elem else "لا يوجد"
        if forecast == "لا يوجد":
            forecast = "لا توجد معلومات كافية في التأثير"

        previous_elem = row.select_one("td.calendar__previous")
        previous = previous_elem.get_text(strip=True) if previous_elem else "لا يوجد"

        news_data.append({
            "date_time": date_time_str,
            "currency": currency_elem.get_text(strip=True),
            "event": event,
            "impact": impact,
            "impact_symbol": impact_symbol,
            "actual": actual,
            "forecast": forecast,
            "previous": previous
        })

    if DEBUG_MODE:
        print(f"Found {len(news_data)} news items after filtering.")
    return news_data

def analyze_news(news_data):
    now = datetime.now()
    upcoming_events = []
    for ev in news_data:
        event_dt = parse_event_datetime(ev["date_time"])
        if event_dt and event_dt > now:
            ev["parsed_time"] = event_dt
            upcoming_events.append(ev)
    if not upcoming_events:
        print("No upcoming events found.")
        return []
    upcoming_events.sort(key=lambda x: x["parsed_time"])
    next_event = upcoming_events[0]
    time_diff = (next_event["parsed_time"] - now).total_seconds()
    print(f"Next event at {next_event['parsed_time']} (in {time_diff/60:.2f} minutes).")

    # إذا تبقى ساعة أو أقل
    if time_diff <= 360000:
        actual_str = next_event["actual"] if next_event["actual"] != "N/A" else "لا يوجد"
        forecast_str = next_event["forecast"] if next_event["forecast"] != "N/A" else "لا يوجد"
        previous_str = next_event["previous"] if next_event["previous"] != "N/A" else "لا يوجد"

        sentiment = "لا يوجد بيانات"
        try:
            actual_value = parse_value(actual_str) if actual_str.strip() and actual_str.strip() != "لا يوجد" else None
        except ValueError:
            actual_value = None
        try:
            forecast_value = parse_value(forecast_str) if forecast_str.strip() and forecast_str.strip() != "لا يوجد" else None
        except ValueError:
            forecast_value = None
        try:
            previous_value = parse_value(previous_str) if previous_str.strip() and previous_str.strip() != "لا يوجد" else None
        except ValueError:
            previous_value = None

        if actual_value is None or forecast_value is None or previous_value is None:
            effective_diff = 0
        else:
            diff_forecast = ((actual_value - forecast_value) / forecast_value) * 100
            diff_previous = ((actual_value - previous_value) / previous_value) * 100
            effective_diff = (diff_forecast + diff_previous) / 2

        moderate_threshold = 1.0
        strong_threshold = 3.0

        if abs(effective_diff) < moderate_threshold:
            sentiment = "⚪ محايد"
        elif effective_diff > 0:
            if effective_diff >= strong_threshold:
                sentiment = "🔵 إيجابي (خبر قوي)"
            else:
                sentiment = "🔵 إيجابي (خبر معتدل)"
        else:
            if effective_diff <= -strong_threshold:
                sentiment = "🔴 سلبي (خبر قوي)"
            else:
                sentiment = "🔴 سلبي (خبر معتدل)"

        # إضافة تاغ @everyone لكل خبر
        tag_str = "@everyone\n"
        message = (
            f"{tag_str}"
            f"**{next_event['currency']} - {next_event['event']}** {next_event['impact_symbol']}\n\n"
            f"السابق: {previous_str}\n"
            f"النتائج: {actual_str}\n"
            f"التوقعات: {forecast_str}\n\n"
            f"التأثير: {sentiment}\n"
            f"(Scheduled for: {next_event['parsed_time']})"
        )
        return [message]
    else:
        print("Next event is not due within one hour. No event sent.")
        return []

def send_event_manual(message):
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        asyncio.run_coroutine_threadsafe(channel.send(message), client.loop)
    else:
        print("Channel not found.")

async def main_scheduler_async():
    """نستعمل دالة غير متزامنة حتى نتمكن من إغلاق البوت بعد انتهاء المهمة."""
    news = scrape_forexfactory()
    messages = analyze_news(news)
    if messages:
        for msg in messages:
            print("Sending scheduled event:")
            print(msg)
            send_event_manual(msg)
    else:
        print("No event to send at this time.")
    # بعد الانتهاء من الإرسال ننتظر قليلًا ثم نغلق البوت
    await asyncio.sleep(5)
    await client.close()  # إغلاق البوت حتى ينتهي السكربت

class MyClient(discord.Client):
    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            print(f"Channel found: {channel.name}")
            await channel.send("🤖 **Forex News Bot Ready! Checking for upcoming High Impact news.**")
        else:
            print("❌ Channel not found!")
        # شغل الجدولة غير المتزامنة
        await main_scheduler_async()

    async def on_message(self, message):
        if message.author == self.user:
            return
        # يمكنك إضافة أوامر إضافية هنا

client = MyClient(intents=discord.Intents.default())

# نستخدم asyncio.run بدل client.run حتى نتحكم بإغلاقه
# ولكن client.run هو الأسهل. إذا أردت الخروج بعد انتهاء on_ready:
# يمكنك عمل await client.close() بعد main_scheduler_async
# ولكن هنا سنستعمل client.run عادي.
client.run(TOKEN)
