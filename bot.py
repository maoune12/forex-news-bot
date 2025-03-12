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

# إعدادات التوكن والقناة للبوت على Discord
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = 1237965762396946445
DEBUG_MODE = True
intents = discord.Intents.default()

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

# دالة التمرير البطيء
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
    if DEBUG_MODE:
        final_pos = driver.execute_script("return window.pageYOffset;")
        print("Slow scroll completed. Final page Y-offset:", final_pos)

# إزالة الفراغ بين اليوم والشهر (مثلاً "Wed Mar" -> "WedMar")
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
    """
    تبسيط دالة تحويل التاريخ بحيث لا يتم تغيير المنطقة الزمنية.
    """
    raw_date_time = raw_date_time.strip()
    if raw_date_time[:3] not in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
        return raw_date_time
    if "All Day" in raw_date_time or "all day" in raw_date_time.lower():
        date_part = raw_date_time.lower().replace("all day", "").strip()
        date_part = fix_date_string(date_part)
        current_year = datetime.now().year
        try:
            dt = datetime.strptime(f"{date_part} {current_year}", "%a%b %d %Y")
        except Exception:
            return raw_date_time
        return format_arabic_date(dt, all_day=True)
    raw_date_time = fix_date_string(raw_date_time)
    has_time = ":" in raw_date_time
    current_year = datetime.now().year
    if not has_time:
        try:
            dt = datetime.strptime(f"{raw_date_time} {current_year}", "%a%b %d %Y")
        except Exception:
            return raw_date_time
        return format_arabic_date(dt, True)
    else:
        try:
            dt = datetime.strptime(f"{raw_date_time} {current_year}", "%a%b %d %I:%M%p %Y")
        except Exception:
            return raw_date_time
        return format_arabic_date(dt, False)

# تحويل القيم الرقمية مثل "7.74M" إلى رقم
def parse_value(s):
    s = s.strip()
    multiplier = 1.0
    if s.endswith("M"):
        s = s.replace("M", "")
    elif s.endswith("K"):
        s = s.replace("K", "")
    elif s.endswith("B"):
        s = s.replace("B", "")
    return float(s) * multiplier

def scrape_forexfactory():
    """
    تجمع هذه الدالة جميع الأخبار (بجميع أنواع التأثير) من موقع forexfactory.
    إذا كانت خانة التاريخ أو الوقت تحتوي على "n/a" أو "لا يوجد" أو تحتوي على قيمة غير وقت حقيقي
    (مثلاً لا تحتوي على ":"), يتم استخدام آخر قيمة موجودة.
    وفي حال فشل تحليل التاريخ/الوقت يتم تعيين event_dt إلى None.
    """
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
                slow_scroll(driver, step=500, delay=1, down_iterations=5, up_iterations=5)
                print("Waiting for calendar row element (undetected_chromedriver)...")
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
                slow_scroll(driver, step=500, delay=1, down_iterations=5, up_iterations=5)
                print("Waiting for calendar row element (standard Selenium)...")
                WebDriverWait(driver, 45).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr.calendar__row:has(td.calendar__currency)"))
                )
                html = driver.page_source
                driver.quit()
            except Exception as se:
                print(f"⚠️ Selenium fallback failed: {se}")
                return []

    soup = BeautifulSoup(html, "html.parser")
    all_rows = soup.select("tr.calendar__row")
    if DEBUG_MODE:
        print(f"Processing {len(all_rows)} calendar rows.")
    news_data = []
    current_year = datetime.now().year
    last_date = None
    last_time = None

    for row in all_rows:
        # التعامل مع خانة التاريخ
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

        # التعامل مع خانة الوقت
        time_elem = row.select_one("td.calendar__time")
        if time_elem:
            cell_text = time_elem.get_text(strip=True)
            # إذا لم يحتوي على ":" أو كانت القيمة "n/a" أو "لا يوجد" نستخدم آخر وقت صالح
            if cell_text.lower() in ["n/a", "لا يوجد"] or ":" not in cell_text:
                row_time = last_time
            else:
                row_time = cell_text
                last_time = row_time
        else:
            row_time = last_time

        if not row_time or row_time.lower() in ["all day"]:
            continue

        # محاولة إنشاء كائن datetime؛ في حال الفشل نعين event_dt إلى None
        try:
            event_dt = datetime.strptime(f"{current_day} {row_time} {current_year}", "%a%b %d %I:%M%p %Y")
        except Exception as e:
            if DEBUG_MODE:
                print(f"⚠️ Failed to parse datetime for row: {e}")
            event_dt = None

        # إذا كانت خانة العملة موجودة فهذا خبر
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

        if DEBUG_MODE:
            print(f"Row date and time: {current_day} {row_time}")
            print("Row impact text:", impact)

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
    
    if DEBUG_MODE:
        print(f"Found {len(news_data)} news items in total.")
    return news_data

def analyze_news(news_data):
    """
    تصنيف الأخبار بناءً على الفرق بين النتائج والتوقعات لتحديد تأثير الخبر.
    """
    messages = []
    moderate_threshold = 1.0   # عتبة الخبر المعتدل (%)
    strong_threshold = 3.0     # عتبة الخبر القوي (%)
    
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
    """
    تصفي الأخبار لتشمل فقط تلك التي يحتوي نص تأثيرها على كلمة "high" (حالة غير حساسة).
    """
    return [news for news in news_data if "high" in news["impact"].lower()]

def filter_within_one_hour(news_data):
    """
    ترجع فقط الأخبار التي لديها قيمة event_dt صحيحة والموعد خلال ساعة أو أقل من الوقت الحالي.
    """
    now = datetime.now()
    return [n for n in news_data if n["event_dt"] is not None and now <= n["event_dt"] <= now + timedelta(hours=1)]

async def debug_show_events():
    """
    في وضع التصحيح:
      - نجمع كل الأخبار.
      - نعرض جميع الأخبار مع تاريخ ووقت كل خبر.
      - نصنف الأخبار ونظهر الأخبار ذات التأثير العالي مع حساب الوقت المتبقي.
    """
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
    print("انتهاء التصحيح، سيتم إغلاق البوت.")

class MyClient(discord.Client):
    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            print(f"Channel found: {channel.name}")
            await channel.send("🤖 **Forex News Bot Ready!**")
        else:
            print("❌ Channel not found!")
        if DEBUG_MODE:
            await debug_show_events()
            await self.close()
        else:
            self.loop.create_task(self.auto_news())
    
    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.channel.id != CHANNEL_ID:
            return
        if message.content.startswith("!news"):
            news_data = await asyncio.to_thread(scrape_forexfactory)
            high_news = filter_high_impact(news_data)
            ready_news = filter_within_one_hour(high_news)
            if not ready_news:
                await message.channel.send("❌ لا توجد أخبار عالية التأثير خلال الساعة القادمة.")
                return
            news_messages = analyze_news(ready_news)
            for msg in news_messages:
                await message.channel.send(msg)
    
    async def auto_news(self):
        await self.wait_until_ready()
        channel = self.get_channel(CHANNEL_ID)
        while not self.is_closed():
            news_data = await asyncio.to_thread(scrape_forexfactory)
            high_news = filter_high_impact(news_data)
            ready_news = filter_within_one_hour(high_news)
            if ready_news:
                news_messages = analyze_news(ready_news)
                for msg in news_messages:
                    await channel.send(msg)
            await asyncio.sleep(1800)

client = MyClient(intents=intents)
client.run(TOKEN)
