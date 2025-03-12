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

# التأكد من توكن البوت في المتغيرات البيئية
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

def slow_scroll(driver, delay=2):
    """
    تمرير الصفحة حتى نهاية المستند للتأكد من تحميل كل البيانات.
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def parse_forex_time(time_str, now):
    """
    تحليل وقت الخبر من الموقع.
    نرجع tuple من الشكل (time_value, display_time)
    حيث time_value هو datetime للتحقق من النطاق الزمني،
    و display_time هو النص الذي سيظهر عند الإرسال.
    """
    print(f"🔎 قراءة وقت الخبر: {time_str}")

    # حالة "all day" نعرض "كل اليوم" ونحسب وقت افتراضي للتصفية
    if time_str.lower() == "all day":
        computed_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
        return computed_time, "كل اليوم"

    # محاولة تحليل الوقت بصيغة AM/PM أو 24 ساعة
    try:
        event_time = datetime.strptime(time_str, "%I:%M%p").time()
    except ValueError:
        try:
            event_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            print(f"⚠️ لم يتمكن من تحليل الوقت: {time_str}")
            return None, None

    full_event_time = now.replace(hour=event_time.hour, minute=event_time.minute, second=0, microsecond=0)
    # إذا كان الوقت بصيغة AM/PM والنص يحتوي على "pm" نضيف 12 ساعة (مع استثناء 12 PM)
    if "pm" in time_str.lower() and event_time.hour != 12:
        full_event_time += timedelta(hours=12)

    display_time = full_event_time.strftime("%Y-%m-%d %I:%M %p")
    print(f"✅ وقت الخبر: {full_event_time.strftime('%Y-%m-%d %H:%M')}")
    return full_event_time, display_time

def scrape_forexfactory():
    url = "https://www.forexfactory.com/calendar"
    print("🟡 تشغيل Selenium لاستخراج الأخبار...")

    options = get_chrome_options()
    driver_path = chromedriver_autoinstaller.install()
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)

    # تمرير الصفحة حتى نهاية المستند لضمان تحميل كل الصفوف
    slow_scroll(driver, delay=2)
    time.sleep(3)

    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    all_rows = soup.select("tr.calendar__row")
    print(f"📄 تم تحميل {len(all_rows)} صفًا من الصفحة.")

    news_data = []
    now = datetime.now()
    # تحديد الفترة الزمنية: الأخبار التي تقع خلال ساعة واحدة من الوقت الحالي
    one_hour_later = now + timedelta(hours=1)

    previous_time_value = None  # لتخزين الوقت الصحيح للخبر السابق في حال كان الوقت "n/a"

    for row in all_rows:
        time_elem = row.select_one("td.calendar__time")
        currency_elem = row.select_one("td.calendar__currency")
        event_elem = row.select_one("td.calendar__event")
        impact_elem = row.select_one("td.calendar__impact span")
        actual_elem = row.select_one("td.calendar__actual")
        forecast_elem = row.select_one("td.calendar__forecast")
        previous_elem = row.select_one("td.calendar__previous")

        if time_elem and currency_elem and event_elem:
            time_text = time_elem.get_text(strip=True)
            event_time_value, display_time = parse_forex_time(time_text, now)

            # إذا لم يتم تحليل الوقت واستخدام القيمة السابقة
            if event_time_value is None and previous_time_value is not None:
                event_time_value = previous_time_value
                display_time = previous_time_value.strftime("%Y-%m-%d %I:%M %p")
            elif event_time_value is None:
                continue

            previous_time_value = event_time_value

            # احتفظ بالأخبار التي تقع بين الآن وساعة واحدة لاحقاً
            if now <= event_time_value <= one_hour_later:
                # المهمة الثالثة: احتفظ فقط بالأخبار ذات التأثير العالي ("high") أو اللون الأحمر ("red")
                impact_text = impact_elem.get("title", "").strip() if impact_elem else ""
                if not ("high" in impact_text.lower() or "red" in impact_text.lower()):
                    continue

                news_data.append({
                    "time_value": event_time_value,
                    "time": display_time,
                    "currency": currency_elem.get_text(strip=True),
                    "event": event_elem.get_text(strip=True),
                    "impact": impact_text if impact_text != "" else "No Impact",
                    "actual": actual_elem.get_text(strip=True) if actual_elem and actual_elem.get_text(strip=True) != "" else "N/A",
                    "forecast": forecast_elem.get_text(strip=True) if forecast_elem and forecast_elem.get_text(strip=True) != "" else "N/A",
                    "previous": previous_elem.get_text(strip=True) if previous_elem and previous_elem.get_text(strip=True) != "" else "N/A"
                })

    # ترتيب الأخبار بحسب الوقت (تصاعدياً)
    news_data.sort(key=lambda x: x["time_value"])
    print(f"📊 تم العثور على {len(news_data)} أخبار خلال الساعة القادمة (تأثير عالي أو أحمر فقط).")
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
                    f"🕒 **التاريخ والوقت:** {news['time']}\n"
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
