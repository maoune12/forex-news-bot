# -*- coding: utf-8 -*-
import os
import discord
import requests
from bs4 import BeautifulSoup
import asyncio
import time

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

# تحميل توكن البوت من المتغيرات البيئية
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ يجب تعيين توكن البوت في المتغيرات البيئية!")

CHANNEL_ID = 1237965762396946445  # استبدل بمعرف قناتك في ديسكورد
DEBUG_MODE = True  # تشغيل وضع التصحيح لرؤية التفاصيل

# إعدادات Selenium
def get_chrome_options():
    options = Options()
    options.headless = not DEBUG_MODE
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    return options

# تحميل الصفحة بالكامل لضمان جلب جميع الأخبار
def slow_scroll(driver, step=500, delay=1, down_iterations=5, up_iterations=5):
    for _ in range(down_iterations):
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(delay)
    for _ in range(up_iterations):
        driver.execute_script(f"window.scrollBy(0, -{step});")
        time.sleep(delay)

# جلب الأخبار من ForexFactory بدون تصفية التأثير
def scrape_forexfactory():
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    html = None

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            html = response.text
        else:
            print(f"⚠️ فشل الطلب، الرمز: {response.status_code}")
    except requests.RequestException as e:
        print(f"⚠️ خطأ في الطلب: {e}")

    if html is None and USE_UC:
        try:
            print("🟡 تجربة undetected_chromedriver...")
            options = uc.ChromeOptions()
            options.headless = not DEBUG_MODE
            driver = uc.Chrome(options=options)
            driver.get(url)
            slow_scroll(driver)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr.calendar__row")))
            html = driver.page_source
            driver.quit()
        except Exception as e:
            print(f"⚠️ فشل undetected_chromedriver: {e}")

    if html is None:
        try:
            print("🟡 تجربة Selenium العادية...")
            options = get_chrome_options()
            driver_path = chromedriver_autoinstaller.install()
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)
            slow_scroll(driver)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr.calendar__row")))
            html = driver.page_source
            driver.quit()
        except Exception as e:
            print(f"⚠️ فشل Selenium: {e}")
            return []

    soup = BeautifulSoup(html, "html.parser")
    all_rows = soup.select("tr.calendar__row")

    news_data = []

    for row in all_rows:
        time_elem = row.select_one("td.calendar__time")
        currency_elem = row.select_one("td.calendar__currency")
        event_elem = row.select_one("td.calendar__event")
        impact_elem = row.select_one("td.calendar__impact span")

        if time_elem and currency_elem and event_elem:
            news_data.append({
                "time": time_elem.get_text(strip=True),
                "currency": currency_elem.get_text(strip=True),
                "event": event_elem.get_text(strip=True),
                "impact": impact_elem.get("title", "").strip() if impact_elem else "No Impact"
            })

    print(f"📊 تم العثور على {len(news_data)} أخبار من جميع الأنواع.")
    return news_data

# إرسال الأخبار إلى ديسكورد
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
                message = f"**🕒 {news['time']} | {news['currency']} - {news['event']} | 📊 {news['impact']}**"
                await channel.send(message)
                await asyncio.sleep(1)

        await client.close()

    await client.start(TOKEN)

# تشغيل البوت
if __name__ == "__main__":
    asyncio.run(send_news_to_discord())
