"""
Streamlit Cloud içi background scheduler.

Streamlit app yüklendiğinde APScheduler başlatılır. Her 10 dakikada bir
notify_scheduled.main()'i çağırır. notify_scheduled.py kendisi şu anki
TR saatine göre hangi BIST/NASDAQ taramayı yapacağına karar verir.

UptimeRobot ile Streamlit Cloud app'i uyumaması için her 5 dk'da bir ping
atılmalı — yoksa free tier 7 gün inaktiviteden sonra uyur.

Kullanım (app.py'ın en üstünde):
    from streamlit_scheduler import start_scheduler
    start_scheduler()
"""
from __future__ import annotations
import logging
import os
import threading
from datetime import datetime, timezone, timedelta

import streamlit as st

# Logger
log = logging.getLogger("streamlit_scheduler")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    log.addHandler(h)

TR = timezone(timedelta(hours=3))


def _notify_tick():
    """Her 10 dakikada bir çağrılır. notify_scheduled mantığı."""
    try:
        # Tembel import — Streamlit yüklenirken yavaşlatmaz
        import notify_scheduled
        log.info(f"[scheduler] notify tick @ {datetime.now(TR):%Y-%m-%d %H:%M} TR")
        notify_scheduled.main()
    except Exception as e:
        log.exception(f"[scheduler] notify HATA: {e}")


def _bot_polling_tick():
    """Her 30 saniyede bir çağrılır. Telegram'a gelen mesajları işle."""
    try:
        import telegram_bot
        telegram_bot.poll_once()
    except Exception as e:
        log.warning(f"[scheduler] polling HATA: {e}")


@st.cache_resource(show_spinner=False)
def _get_scheduler():
    """Streamlit @st.cache_resource → tek process içinde tek instance.
    Sayfa açılışında bir kez çağrılır, sonra cache'li döner."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        log.warning("APScheduler kurulu değil, scheduler atlandı")
        return None

    sched = BackgroundScheduler(timezone="UTC", daemon=True)
    # 1) Notify (her 10 dk) — saate göre tarama + Telegram bildirim
    sched.add_job(
        _notify_tick,
        trigger="cron",
        minute="*/10",
        id="ott_notify",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    # 2) Bot polling (her 30 sn) — kullanıcının Telegram mesajlarını işle
    sched.add_job(
        _bot_polling_tick,
        trigger="interval",
        seconds=30,
        id="ott_bot_polling",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    sched.start()
    log.info("[scheduler] Background scheduler başladı "
             "(notify: 10 dk · bot polling: 30 sn)")
    return sched


def start_scheduler():
    """app.py'dan çağrılır. Sadece TELEGRAM_BOT_TOKEN ayarlıysa çalışır."""
    # Telegram konfigüre değilse skip
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        # Streamlit secrets'tan dene
        try:
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", None)
        except Exception:
            pass
    if not token:
        return None
    return _get_scheduler()
