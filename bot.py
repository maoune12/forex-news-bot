name: Run Discord Bot

on:
  push:
    branches: [ main ]
  workflow_dispatch:
  schedule:
    - cron: "0 * * * 1-5"  # تشغيل كل ساعة من الاثنين إلى الجمعة

jobs:
  run-bot:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v2

      - name: Install Google Chrome stable (v134.0.6998.88-1)
        run: |
          sudo apt-get update
          sudo apt-get install -y wget gnupg
          wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
          sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
          sudo apt-get update
          sudo apt-get install -y google-chrome-stable=134.0.6998.88-1
          google-chrome --version

      - name: Install pinned ChromeDriver (v134.0.6998.88)
        run: |
          CHROMEDRIVER_VERSION="134.0.6998.88"
          wget https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip
          unzip chromedriver_linux64.zip
          sudo mv chromedriver /usr/local/bin/chromedriver
          sudo chmod +x /usr/local/bin/chromedriver
          chromedriver --version

      - name: Set up Python 3.9
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          # نحذف chromedriver_autoinstaller لأننا سنستخدم الإصدار المثبت يدويًا
          pip install discord.py requests beautifulsoup4 selenium

      - name: Run Discord Bot with xvfb
        env:
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
          CHANNEL_ID: ${{ secrets.CHANNEL_ID }}
          DEBUG_MODE: "False"
        run: |
          xvfb-run --auto-servernum --server-args='-screen 0 1024x768x24' python bot.py
