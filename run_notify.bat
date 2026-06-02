@echo off
REM OTT Bot — Telegram bildirim dispatcher (Windows Task Scheduler için)
REM Her 10 dakikada bir çalışır, notify_scheduled.py karar verir
cd /d "C:\Users\furka\Desktop\ott_bot"
python notify_scheduled.py >> notify_scheduled.log 2>&1
