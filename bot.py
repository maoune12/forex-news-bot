# -*- coding: utf-8 -*-
import os
import discord
from bs4 import BeautifulSoup
import asyncio
import time
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import chromedriver_autoinstaller

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ يجب تعيين توكن البوت في المتغيرات البيئية!")

CHANNEL_ID = 1237965762396946445  # استبدل بمعرف قناتك في ديسكورد
DEBUG_MODE = True

def get_chrome_options():
    options = Options()
    options.headless = not DEBUG_MODE
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    return options

def slow_scroll(driver, step=500, delay=1, down_iterations=5, up_iterations=5):
    for _ in range(down_iterations):
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(delay)
    for _ in range(up_iterations):
        driver.execute_script(f"window.scrollBy(0, -{step});")
        time.sleep(delay)

def parse_forex_time(time_str):
    """ يحلل وقت الخبر من الموقع """
    now = datetime.now()
    print(f"🔎 قراءة وقت الخبر: {time_str}")  # ✅ تصحيح الأخطاء

    if time_str.lower() == "all day":
        return now.replace(hour=23, minute=59)

    # تحقق مما إذا كان الوقت بتنسيق AM/PM
    try:
        event_time = datetime.strptime(time_str, "%I:%M%p").time()
    except ValueError:
        try:
            event_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            print(f"⚠️ لم يتمكن من تحليل الوقت: {time_str}")
            return None
    
    full_event_time = now.replace(hour=event_time.hour, minute=event_time.minute, second=0, microsecond=0)
    if "pm" in time_str.lower() and event_time.hour != 12:
        full_event_time += timedelta(hours=12)
    
    print(f"✅ وقت الخبر: {full_event_time.strftime('%Y-%m-%d %H:%M')}")
    return full_event_time

def scrape_forexfactory():
    url = "https://www.forexfactory.com/calendar"
    
    print("🟡 تشغيل Selenium لاستخراج الأخبار...")
    options = get_chrome_options()
    driver_path = chromedriver_autoinstaller.install()
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    
    slow_scroll(driver)
    time.sleep(3)
    
    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    all_rows = soup.select("tr.calendar__row")

    news_data = []
    now = datetime.now()
    ten_hours_later = now + timedelta(hours=10)

    for row in all_rows:
        time_elem = row.select_one("td.calendar__time")
        currency_elem = row.select_one("td.calendar__currency")
        event_elem = row.select_one("td.calendar__event")
        impact_elem = row.select_one("td.calendar__impact span")
        actual_elem = row.select_one("td.calendar__actual")
        forecast_elem = row.select_one("td.calendar__forecast")
        previous_elem = row.select_one("td.calendar__previous")

        if time_elem and currency_elem and event_elem:
            event_time = parse_forex_time(time_elem.get_text(strip=True))

            if event_time and now <= event_time <= ten_hours_later:
                news_data.append({
                    "time": event_time.strftime("%I:%M %p"),  # تحويله لـ AM/PM
                    "currency": currency_elem.get_text(strip=True),
                    "event": event_elem.get_text(strip=True),
                    "impact": impact_elem.get("title", "").strip() if impact_elem else "No Impact",
                    "actual": actual_elem.get_text(strip=True) if actual_elem else "N/A",
                    "forecast": forecast_elem.get_text(strip=True) if forecast_elem else "N/A",
                    "previous": previous_elem.get_text(strip=True) if previous_elem else "N/A"
                })

    print(f"📊 تم العثور على {len(news_data)} أخبار خلال الـ 10 ساعات القادمة.")
    return news_data

async def send_news_to_discord():
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        print(f"✅ بوت متصل كـ {client.user}")
        channel = client.get_channel(CHANNEL_ID)
        if not channel:
            print("❌ لم يتم العثور على القناة!")
            await client.close()
            return

        news_data = scrape_forexfactory()

        if news_data:
            for news in news_data:
                message = (
                    f"**📢 {news['event']} ({news['currency']})**\n"
                    f"🕒 **التوقيت:** {news['time']}\n"
                    f"🔥 **التأثير:** {news['impact']}\n"
                    f"📊 **النتيجة الفعلية:** {news['actual']}\n"
                    f"📈 **التوقع:** {news['forecast']}\n"
                    f"📉 **القيمة السابقة:** {news['previous']}\n"
                    f"----------------------------------------"
                )
                await channel.send(message)
                await asyncio.sleep(1)

        await client.close()

    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_news_to_discord())
