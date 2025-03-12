# -*- coding: utf-8 -*-
import os
import discord
import requests
from bs4 import BeautifulSoup
import re
import asyncio
import time
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

# قراءة المتغيرات من البيئة
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "0")
DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

try:
    CHANNEL_ID = int(CHANNEL_ID)
except ValueError:
    CHANNEL_ID = 0

intents = discord.Intents.default()

def debug_print(msg):
    if DEBUG_MODE:
        print("[DEBUG]", msg)

def get_common_chrome_options():
    options = Options()
    # تحديد موقع ملف Chrome الذي ثبتناه
    options.binary_location = "/usr/local/bin/google-chrome"
    debug_print("Setting binary location to /usr/local/bin/google-chrome")
    # لم نستخدم خيار --user-data-dir لتجنب تعارض الجلسات
    if DEBUG_MODE:
        options.headless = False
    else:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    debug_print("Chrome options set: " + str(options.arguments))
    return options

def slow_scroll(driver, step=500, delay=1, down_iterations=5, up_iterations=5):
    debug_print("Starting slow scroll...")
    for i in range(down_iterations):
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(delay)
        offset = driver.execute_script("return window.pageYOffset;")
        debug_print(f"Down scroll {i+1} done. pageYOffset = {offset}")
    for i in range(up_iterations):
        driver.execute_script(f"window.scrollBy(0, -{step});")
        time.sleep(delay)
        offset = driver.execute_script("return window.pageYOffset;")
        debug_print(f"Up scroll {i+1} done. pageYOffset = {offset}")
    final_pos = driver.execute_script("return window.pageYOffset;")
    debug_print("Slow scroll completed. Final page Y-offset: " + str(final_pos))

def fix_date_string(s):
    s = s.strip()
    if len(s) >= 7 and s[0:3].isalpha() and s[3] == " " and s[4:7].isalpha():
        return s[0:3] + s[4:]
    return s

def format_arabic_date(dt, all_day=False):
    weekdays = {
        "Sun": "الأحد", "Mon": "الاثنين", "Tue": "الثلاثاء",
        "Wed": "الأربعاء", "Thu": "الخميس", "Fri": "الجمعة", "Sat": "السبت"
    }
    months = {
        "Jan": "يناير", "Feb": "فبراير", "Mar": "مارس", "Apr": "أبريل",
        "May": "مايو", "Jun": "يونيو", "Jul": "يوليو", "Aug": "أغسطس",
        "Sep": "سبتمبر", "Oct": "أكتوبر", "Nov": "نوفمبر", "Dec": "ديسمبر"
    }
    weekday_en = dt.strftime("%a")
    month_en = dt.strftime("%b")
    day = dt.strftime("%d")
    year = dt.strftime("%Y")
    if not all_day:
        time_str = dt.strftime("%I:%M").lstrip("0")
        ampm = dt.strftime("%p")
        ampm_ar = "صباحًا" if ampm == "AM" else "مساءً"
        time_output = f"{time_str} {ampm_ar}"
    else:
        time_output = "طوال اليوم"
    return f"{weekdays.get(weekday_en, weekday_en)} {int(day)} {months.get(month_en, month_en)} {year} {time_output}"

def convert_to_arabic_date(raw_date_time):
    raw_date_time = raw_date_time.strip()
    if raw_date_time[:3] not in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
        return raw_date_time
    if "All Day" in raw_date_time or "all day" in raw_date_time.lower():
        date_part = raw_date_time.lower().replace("all day", "").strip()
        date_part = fix_date_string(date_part)
        current_year = datetime.now().year
        try:
            dt = datetime.strptime(f"{date_part} {current_year}", "%a%b %d %Y")
        except Exception as e:
            debug_print(f"Failed to parse date part: {e}")
            return raw_date_time
        return format_arabic_date(dt, all_day=True)
    raw_date_time = fix_date_string(raw_date_time)
    has_time = ":" in raw_date_time
    current_year = datetime.now().year
    try:
        if not has_time:
            dt = datetime.strptime(f"{raw_date_time} {current_year}", "%a%b %d %Y")
        else:
            dt = datetime.strptime(f"{raw_date_time} {current_year}", "%a%b %d %I:%M%p %Y")
    except Exception as e:
        debug_print(f"Failed to parse full date time: {e}")
        return raw_date_time
    return format_arabic_date(dt, not has_time)

def parse_value(s):
    s = s.strip()
    if s.endswith("M"):
        s = s.replace("M", "")
    elif s.endswith("K"):
        s = s.replace("K", "")
    elif s.endswith("B"):
        s = s.replace("B", "")
    try:
        return float(s)
    except ValueError:
        return None

def scrape_forexfactory():
    debug_print("Starting to scrape ForexFactory.")
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.89 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive"
    }
    html = None
    try:
        debug_print("Sending requests.get to ForexFactory.")
        response = requests.get(url, headers=headers, timeout=10)
        debug_print(f"Received response with status code: {response.status_code}")
        if response.status_code == 200:
            response.encoding = "utf-8"
            html = response.text
        else:
            raise Exception(f"Status code: {response.status_code}")
    except Exception as e:
        debug_print(f"Requests failed: {e}")

    if html is None:
        try:
            debug_print("Falling back to Selenium.")
            chrome_options = get_common_chrome_options()
            service = Service("/usr/local/bin/chromedriver")
            debug_print("Initializing Selenium WebDriver.")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(url)
            debug_print("Page loaded in Selenium. Performing full scroll.")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            offset = driver.execute_script("return window.pageYOffset;")
            debug_print("Page Y-offset after full scroll: " + str(offset))
            debug_print("Waiting for calendar row element with Selenium...")
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "td.calendar__currency"))
            )
            html = driver.page_source
            driver.quit()
            debug_print("Selenium fallback succeeded.")
        except Exception as se:
            debug_print(f"Selenium fallback failed: {se}")
            return []

    if not html:
        debug_print("No HTML content retrieved.")
        return []

    soup = BeautifulSoup(html, "html.parser")
    all_rows = soup.select("tr.calendar__row")
    debug_print(f"Found {len(all_rows)} calendar rows.")
    news_data = []
    current_year = datetime.now().year
    last_date = None
    last_time = None

    for row in all_rows:
        date_cell = row.select_one("td.calendar__date")
        if date_cell:
            cell_text = date_cell.get_text(strip=True)
            if cell_text.lower() in ["n/a", "لا يوجد"]:
                current_day = last_date
            else:
                current_day = fix_date_string(cell_text)
                last_date = current_day
        else:
            current_day = last_date

        if not current_day:
            continue

        time_elem = row.select_one("td.calendar__time")
        if time_elem:
            cell_text = time_elem.get_text(strip=True)
            if cell_text.lower() in ["n/a", "لا يوجد"] or ":" not in cell_text:
                row_time = last_time
            else:
                row_time = cell_text
                last_time = row_time
        else:
            row_time = last_time

        if not row_time or row_time.lower() in ["all day"]:
            continue

        try:
            event_dt = datetime.strptime(f"{current_day} {row_time} {current_year}", "%a%b %d %I:%M%p %Y")
        except Exception as e:
            debug_print(f"Failed to parse datetime for row: {e}")
            event_dt = None

        currency_elem = row.select_one("td.calendar__currency")
        if not currency_elem:
            continue

        event_elem = row.select_one("td.calendar__event")
        event = event_elem.get_text(strip=True) if event_elem else "لا يوجد"

        impact_elem = row.select_one("td.calendar__impact span")
        if impact_elem:
            impact = impact_elem.get("title", "").strip() or impact_elem.text.strip()
        else:
            impact = "Low Impact Expected"

        debug_print(f"Row: {current_day} {row_time} - Impact: {impact}")

        actual_elem = row.select_one("td.calendar__actual")
        actual = actual_elem.get_text(strip=True) if actual_elem else "لا يوجد"

        forecast_elem = row.select_one("td.calendar__forecast")
        forecast = forecast_elem.get_text(strip=True) if forecast_elem else "لا يوجد"
        if forecast == "لا يوجد":
            forecast = "لا توجد معلومات كافية في التأثير"

        previous_elem = row.select_one("td.calendar__previous")
        previous = previous_elem.get_text(strip=True) if previous_elem else "لا يوجد"

        news_data.append({
            "date_time": f"{current_day} {row_time}",
            "event_dt": event_dt,
            "currency": currency_elem.get_text(strip=True),
            "event": event,
            "impact": impact,
            "actual": actual,
            "forecast": forecast,
            "previous": previous
        })
    
    debug_print(f"Found {len(news_data)} news items in total.")
    return news_data

def analyze_news(news_data):
    messages = []
    moderate_threshold = 1.0
    strong_threshold = 3.0
    
    for idx, news in enumerate(news_data, start=1):
        actual_str = news["actual"] if news["actual"] != "N/A" else "لا يوجد"
        forecast_str = news["forecast"] if news["forecast"] != "N/A" else "لا يوجد"
        previous_str = news["previous"] if news["previous"] != "N/A" else "لا يوجد"
        
        if (not actual_str.strip() or actual_str.strip() == "لا يوجد") and \
           (not forecast_str.strip() or forecast_str.strip() == "لا يوجد") and \
           (not previous_str.strip() or previous_str.strip() == "لا يوجد"):
            sentiment = "لا يوجد بيانات"
        else:
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
        
        tag_str = "@everyone\n" if sentiment not in ["⚪ محايد", "لا يوجد بيانات"] else ""
        arabic_full_date = convert_to_arabic_date(news.get("date_time", "لا يوجد"))
        message = (
            f"{tag_str}"
            f"{idx}. {arabic_full_date}\n\n"
            f"**{news['currency']} - {news['event']}**\n\n"
            f"السابق: {previous_str}\n"
            f"النتائج: {actual_str}\n"
            f"التوقعات: {forecast_str}\n\n"
            f"التأثير: {sentiment}\n"
            f"{'-'*40}\n\n"
        )
        messages.append(message)
    return messages

def filter_high_impact(news_data):
    return [news for news in news_data if "high" in news["impact"].lower()]

def filter_within_one_hour(news_data):
    now = datetime.now()
    return [n for n in news_data if n["event_dt"] is not None and now <= n["event_dt"] <= now + timedelta(hours=1)]

async def debug_show_events():
    news_data = await asyncio.to_thread(scrape_forexfactory)
    if not news_data:
        print("❌ لا توجد أخبار.")
        return
    print("------- جميع الأخبار --------")
    for news in news_data:
        print(f"الحدث: {news['currency']} - {news['event']}")
        print(f"وقت الحدث: {news['date_time']}")
        print(f"نص التأثير: {news['impact']}")
        print("-" * 40)
    
    high_news = filter_high_impact(news_data)
    print(f"\n------- الأخبار ذات التأثير العالي: {len(high_news)} خبر -------")
    now = datetime.now()
    for news in high_news:
        event_dt = news["event_dt"]
        if event_dt:
            delta = event_dt - now
            hours, remainder = divmod(delta.seconds, 3600)
            minutes = remainder // 60
            total_hours = delta.days * 24 + hours
            time_remaining = f"{total_hours} ساعة, {minutes} دقيقة" if delta.total_seconds() > 0 else "انتهى الوقت"
        else:
            time_remaining = "غير متوفر"
        print("=" * 60)
        print(f"الحدث: {news['currency']} - {news['event']}")
        print(f"وقت الحدث: {news['date_time']}")
        print(f"الوقت المتبقي: {time_remaining}")
        if event_dt and event_dt > now and (delta.days == 0 and total_hours < 1):
            print("هذا الخبر جاهز للإرسال (أقل من ساعة).")
        else:
            print("هذا الخبر غير جاهز للإرسال بعد.")
        print("=" * 60)
    ready_news = filter_within_one_hour(high_news)
    print(f"\n------- الأخبار الجاهزة للإرسال: {len(ready_news)} خبر -------")
    print("انتهاء التصحيح.")

class MyClient(discord.Client):
    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            print(f"Channel found: {channel.name}")
            await channel.send("🤖 **Forex News Bot is Running Ephemerally (Debug Mode)**")
        else:
            print("❌ Channel not found!")
        
        if DEBUG_MODE:
            await debug_show_events()
        else:
            news_data = await asyncio.to_thread(scrape_forexfactory)
            high_news = filter_high_impact(news_data)
            ready_news = filter_within_one_hour(high_news)
            if channel and ready_news:
                news_messages = analyze_news(ready_news)
                for msg in news_messages:
                    await channel.send(msg)
        await self.close()
    
    async def on_message(self, message):
        pass

if not TOKEN or TOKEN.strip() == "":
    print("❌ Discord bot token is missing or empty!")
else:
    client = MyClient(intents=intents)
    client.run(TOKEN)
