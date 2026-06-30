@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OTT Bulut Cron (LOKAL) - 30 dk'da bir tarar + push - kapatma: pencereyi kapat
echo ============================================================
echo   OTT LOKAL CRON - GitHub Actions yerine PC'den besler
echo   Her 30 dk: BIST + crypto grid tarar, repo'ya push eder
echo   Dashboard (furkanyilmaz.streamlit.app) bundan beslenir
echo   Durdurmak icin: bu pencereyi kapat
echo ============================================================
:loop
echo.
echo [%date% %time%] Tarama basliyor...
python notify_scheduled.py
python daily_report.py --cron
python borsa_mudur.py --cron
echo [%date% %time%] Repo'ya yaziliyor...
git add notify_state_scheduled.json live_positions.json live_trades.json lo_positions.json lo_trades.json lo_breadth.json cg_positions.json cg_trades.json daily_report_state.json borsa_mudur_state.json 2>nul
git commit -m "auto: lokal cron %time%" 2>nul
git pull --rebase -X theirs origin main 2>nul
git push 2>nul
echo [%date% %time%] Bitti. 30 dk bekleniyor...
timeout /t 1800 /nobreak >nul
goto loop
