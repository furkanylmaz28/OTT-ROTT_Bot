"""
Bildirim sistemi — yeni AÇ / ÇIK sinyali geldiğinde email veya Telegram.

KURULUM — Telegram (önerilen — anlık + ücretsiz):
  1. Telegram'da @BotFather'ı bul → /newbot komutuyla yeni bot oluştur
  2. Bot Token al (örn: 1234567890:ABC...)
  3. @userinfobot'a yaz → kendi user ID'ni al
  4. .env'e ekle:
       TELEGRAM_BOT_TOKEN=1234567890:ABC...
       TELEGRAM_CHAT_ID=123456789
  5. Streamlit Cloud secrets'a da aynı şeyi ekle

KURULUM — Email (Gmail SMTP):
  1. Gmail → Hesap → Güvenlik → "Uygulama Şifreleri" oluştur (2FA gerek)
  2. .env'e ekle:
       NOTIFY_EMAIL=senin@gmail.com
       NOTIFY_EMAIL_PASSWORD=app_sifresi
       NOTIFY_EMAIL_TO=hedef@gmail.com
"""
from __future__ import annotations
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _try_streamlit_secrets(keys: list[str]) -> dict[str, str]:
    """Streamlit Cloud'da secrets.toml'dan oku."""
    out = {}
    try:
        import streamlit as st
        for k in keys:
            if k in st.secrets:
                out[k] = str(st.secrets[k])
    except Exception:
        pass
    return out


def send_telegram(message: str) -> bool:
    """Telegram bot ile mesaj gönder. True → başarılı."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or \
            _try_streamlit_secrets(["TELEGRAM_BOT_TOKEN"]).get("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or \
              _try_streamlit_secrets(["TELEGRAM_CHAT_ID"]).get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def send_email(subject: str, body: str) -> bool:
    """SMTP üzerinden email gönder. True → başarılı."""
    cfg = {
        "NOTIFY_EMAIL": os.getenv("NOTIFY_EMAIL"),
        "NOTIFY_EMAIL_PASSWORD": os.getenv("NOTIFY_EMAIL_PASSWORD"),
        "NOTIFY_EMAIL_TO": os.getenv("NOTIFY_EMAIL_TO"),
    }
    if not all(cfg.values()):
        cfg.update(_try_streamlit_secrets(list(cfg.keys())))
    if not all(cfg.values()):
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["NOTIFY_EMAIL"]
        msg["To"] = cfg["NOTIFY_EMAIL_TO"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(cfg["NOTIFY_EMAIL"], cfg["NOTIFY_EMAIL_PASSWORD"])
            s.send_message(msg)
        return True
    except Exception:
        return False


def notify(subject: str, body_html: str, plain_text: str = None) -> dict:
    """Hem Telegram hem Email — kurulu olan(lar)a gönder."""
    plain = plain_text or body_html
    result = {
        "telegram": send_telegram(plain),
        "email": send_email(subject, body_html),
    }
    return result


def is_configured() -> dict[str, bool]:
    """Hangi kanallar aktif?"""
    return {
        "telegram": bool(
            (os.getenv("TELEGRAM_BOT_TOKEN") or
             _try_streamlit_secrets(["TELEGRAM_BOT_TOKEN"]).get("TELEGRAM_BOT_TOKEN")) and
            (os.getenv("TELEGRAM_CHAT_ID") or
             _try_streamlit_secrets(["TELEGRAM_CHAT_ID"]).get("TELEGRAM_CHAT_ID"))
        ),
        "email": bool(
            (os.getenv("NOTIFY_EMAIL") or
             _try_streamlit_secrets(["NOTIFY_EMAIL"]).get("NOTIFY_EMAIL")) and
            (os.getenv("NOTIFY_EMAIL_PASSWORD") or
             _try_streamlit_secrets(["NOTIFY_EMAIL_PASSWORD"]).get("NOTIFY_EMAIL_PASSWORD"))
        ),
    }


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    load_dotenv()
    status = is_configured()
    print(f"Telegram yapılandırma: {'✓' if status['telegram'] else '✗'}")
    print(f"Email yapılandırma   : {'✓' if status['email'] else '✗'}")
    if status["telegram"]:
        r = send_telegram("🤖 OTT Bot test mesajı — bağlantı çalışıyor!")
        print(f"Telegram test: {'✓ gönderildi' if r else '✗ hata'}")
    if status["email"]:
        r = send_email("OTT Bot Test", "<b>Bağlantı çalışıyor!</b>")
        print(f"Email test: {'✓ gönderildi' if r else '✗ hata'}")
