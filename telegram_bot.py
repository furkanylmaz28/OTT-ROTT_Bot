"""
Telegram bot polling — sembol sorgusu için interaktif cevap.

Kullanım (Telegram'da):
    AKBNK              → AKBNK.IS analiz
    AKBNK.IS           → AKBNK.IS analiz
    aapl               → AAPL analiz
    /help              → komut listesi
    /portfoy           → açık pozisyonlar (Google Sheets'ten)
    /tara bist         → BIST sinyalleri
    /tara nasdaq       → NASDAQ sinyalleri

Streamlit Cloud içinde APScheduler ile her 30 sn polling.
"""
from __future__ import annotations
import os
import json
import re
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

log = logging.getLogger("telegram_bot")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    log.addHandler(h)

TR = timezone(timedelta(hours=3))
STATE_FILE = "telegram_bot_state.json"


def _get_creds():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token:
        try:
            import streamlit as st
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", None)
            chat = chat or st.secrets.get("TELEGRAM_CHAT_ID", None)
        except Exception:
            pass
    return token, chat


def _load_state():
    if not Path(STATE_FILE).exists():
        return {"last_update_id": 0}
    try:
        return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {"last_update_id": 0}


def _save_state(state):
    try:
        Path(STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        log.warning(f"state kaydı başarısız: {e}")


def send_reply(chat_id, text):
    """Mesajı gönder — HTML format, web preview kapalı."""
    token, _ = _get_creds()
    if not token:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        log.exception(f"sendMessage hata: {e}")
        return False


def get_updates(offset: int = 0):
    """Telegram getUpdates — yeni mesajları çek. timeout=0 (instant return)."""
    token, _ = _get_creds()
    if not token:
        return []
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "timeout": 0, "limit": 20,
                    "allowed_updates": json.dumps(["message"])},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        return r.json().get("result", [])
    except Exception as e:
        log.warning(f"getUpdates hata: {e}")
        return []


# ── SEMBOL ALGILAMA ──────────────────────────────────────────────────
def _all_known_symbols():
    """Tüm dashboard sembollerini cache'le (Bayes + Grid'den)."""
    syms = set()
    for fn in ("per_symbol_params.json", "per_symbol_params_bayes.json"):
        try:
            with open(fn, encoding="utf-8") as f:
                syms.update(json.load(f).keys())
        except Exception:
            pass
    return syms


_KNOWN_SYMS_CACHE = None
def known_symbols():
    global _KNOWN_SYMS_CACHE
    if _KNOWN_SYMS_CACHE is None:
        _KNOWN_SYMS_CACHE = _all_known_symbols()
    return _KNOWN_SYMS_CACHE


def parse_symbol(text: str):
    """Mesajdan sembol çıkar. 'AKBNK' → 'AKBNK.IS', 'aapl' → 'AAPL'."""
    text = text.strip().upper().lstrip("/?")
    text = text.split()[0] if text else ""   # ilk kelime
    if not text:
        return None
    syms = known_symbols()
    # 1) Tam eşleşme
    if text in syms:
        return text
    # 2) .IS uzantısı dene (BIST için)
    if f"{text}.IS" in syms:
        return f"{text}.IS"
    # 3) -USD dene (crypto)
    if f"{text}-USD" in syms:
        return f"{text}-USD"
    return None


# ── ANALİZ + CEVAP ──────────────────────────────────────────────────
def analyze_and_format(sym: str) -> str:
    """Sembolü analiz et, Telegram mesajı olarak formatla."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import signals_full as sig_full
        from data_source import fetch as ds_fetch, best_interval_for, category_of
    except Exception as e:
        return f"❌ Analiz modülü yüklenemedi: {e}"

    # Parametreleri yükle (Bayes önceliği)
    params_info = None
    src = None
    try:
        with open("per_symbol_params_bayes.json", encoding="utf-8") as f:
            b = json.load(f)
        if sym in b and b[sym].get("ok"):
            params_info = b[sym]
            src = "Bayes"
    except Exception:
        pass
    if params_info is None:
        try:
            with open("per_symbol_params.json", encoding="utf-8") as f:
                g = json.load(f)
            if sym in g and g[sym].get("ok"):
                params_info = g[sym]
                src = "Grid"
        except Exception:
            pass

    if not params_info:
        return f"❌ <b>{sym}</b> için optimize parametre yok.\nDashboard'da Anlık Tarayıcı kullan."

    # Veri çek
    try:
        df = ds_fetch(sym, interval=best_interval_for(sym), n_bars=2500)
        if df.empty or len(df) < 1500:
            return f"❌ <b>{sym}</b> veri çekilemedi (yeterli bar yok)."
    except Exception as e:
        return f"❌ <b>{sym}</b> veri hatası: {str(e)[:100]}"

    # Sinyal hesapla
    try:
        p = params_info["params"].copy()
        p.setdefault("rott_x1", 30); p.setdefault("rott_x2", 1000)
        p.setdefault("rott_percent", 7.0)
        s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **p)
        last = s.iloc[-1]
        cur = float(df["close"].iloc[-1])
    except Exception as e:
        return f"❌ <b>{sym}</b> hesaplama hatası: {str(e)[:100]}"

    # Sinyal etiketi
    if last["cond_buy_long"]:        sig_text = "🟢 LONG AÇ (taze sinyal)"
    elif last["cond_buy_short"]:     sig_text = "🔴 SHORT AÇ (taze sinyal)"
    elif last["cond_exit_long"]:     sig_text = "🟡 LONG ÇIK — kapat"
    elif last["cond_exit_short"]:    sig_text = "🟡 SHORT ÇIK — kapat"
    elif last["major_up"] and last["zone_up"]:
        sig_text = "🟢 LONG TUT — devam"
    elif last["major_dn"] and last["zone_dn"]:
        sig_text = "🔴 SHORT TUT — devam"
    elif last["major_up"]:
        sig_text = "⏳ LONG BEKLE — major yukarı ama bölge kapalı"
    elif last["major_dn"]:
        sig_text = "⏳ SHORT BEKLE — major aşağı ama bölge kapalı"
    else:
        sig_text = "❓ Belirsiz"

    # Stop seviyesi
    tott_up = float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None
    tott_dn = float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None
    if "LONG" in sig_text:
        stop = tott_dn
    elif "SHORT" in sig_text:
        stop = tott_up
    else:
        stop = None

    # ÇIK YAKIN kontrolü
    warn = ""
    if "TUT" in sig_text and stop:
        if "LONG" in sig_text:
            dpct = (cur / stop - 1) * 100
        else:
            dpct = (stop / cur - 1) * 100
        if 0 < dpct < 1.0:
            warn = f"\n⚠️ <b>ÇIK YAKIN!</b> ({dpct:.2f}% mesafe)"

    # Backtest istatistik
    stats = params_info.get("stats", {})
    win  = (stats.get("win_rate") or 0) * 100
    pf   = stats.get("pf") or 0
    ret  = (stats.get("ret_pct") or 0) * 100
    n    = int(stats.get("n_trades") or 0)
    rating = params_info.get("rating", "?")
    rt_emoji = {"MÜKEMMEL": "🏆", "İYİ": "⭐", "ORTA": "🟢",
                 "MARJINAL": "🟡", "VERİ_AZ": "⚠️", "UYUMSUZ": "❌"}.get(rating, "•")

    # Kategori bayrak
    cat = category_of(sym)
    flag = "🇹🇷" if cat == "BIST" else "🇺🇸"

    # Mesaj
    pf_str = "∞" if pf >= 900 else f"{pf:.2f}"
    lines = [
        f"{flag} <b>{sym}</b>  {rt_emoji} <code>{rating}</code>",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{sig_text}{warn}",
        f"",
        f"💰 Fiyat: <code>{cur:.4f}</code>",
    ]
    if stop:
        stop_pct = abs(cur - stop) / cur * 100
        lines.append(f"🛑 Stop:  <code>{stop:.4f}</code> ({stop_pct:.2f}%)")
    if tott_up and tott_dn:
        lines.append(f"📍 TOTT ↑/↓: <code>{tott_up:.4f}</code> / <code>{tott_dn:.4f}</code>")

    lines.append("")
    lines.append(f"📊 BT: Win <b>{win:.0f}%</b> · PF <b>{pf_str}</b> · "
                  f"Ret <b>{ret:+.1f}%</b> · {n} trade")
    lines.append(f"<i>{src} parametreleriyle · {datetime.now(TR):%H:%M TR}</i>")
    return "\n".join(lines)


# ── KOMUTLAR ───────────────────────────────────────────────────────
HELP_TEXT = """\
🤖 <b>OTT Bot — Komutlar</b>

📌 <b>Sembol sorgu:</b>
   <code>AKBNK</code> · <code>AAPL</code> · <code>BTC</code>
   → Anlık sinyal + Stop + BT istatistik

📋 <b>Komutlar:</b>
   <code>/help</code>       — bu menü
   <code>/portfoy</code>    — açık pozisyonlar
   <code>/tara bist</code>  — anlık BIST taraması (top sinyaller)
   <code>/tara nasdaq</code> — anlık NASDAQ taraması

💡 <i>Bot saate göre otomatik bildirimleri de gönderir.</i>
📱 Dashboard: https://furkanyilmaz.streamlit.app
"""


def cmd_portfolio() -> str:
    """Google Sheets'ten açık pozisyonlar."""
    try:
        from gsheets_storage import load_portfolio_sheets
        df = load_portfolio_sheets()
        if df is None or len(df) == 0:
            return "📭 Açık pozisyon yok."
        open_df = df[df.get("Durum", "") == "Açık"] if "Durum" in df.columns else df
        if len(open_df) == 0:
            return "📭 Açık pozisyon yok."
        lines = [f"💼 <b>Açık Pozisyonlar ({len(open_df)})</b>", ""]
        for _, row in open_df.iterrows():
            sym = row.get("Sembol", "?")
            yon = row.get("Yön", "?")
            entry = row.get("Giriş Fiyatı", 0)
            sl    = row.get("Stop Loss", 0)
            tp    = row.get("Take Profit", 0)
            yon_emo = "🟢" if yon == "LONG" else "🔴"
            lines.append(f"{yon_emo} <b>{sym}</b> · {yon}")
            lines.append(f"   Giriş: <code>{entry}</code> · "
                          f"SL: <code>{sl}</code> · TP: <code>{tp}</code>")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Portföy okuma hatası: {str(e)[:200]}"


def cmd_scan(category: str) -> str:
    """Tek seferlik tarama — top sinyaller."""
    try:
        import notify_scheduled as ns
        grid, bayes = ns.load_param_files()
        results = ns.scan_category(category.upper(), "scan", grid, bayes)
        if not results:
            return f"📭 <b>{category.upper()}</b> — şu an aktif sinyal yok (ORTA+)."
        top = results[:5]
        lines = [f"📡 <b>{category.upper()} — Top {len(top)} sinyal</b>", ""]
        for r in top:
            lines.append(f"• <b>{r['sym']}</b> <code>{r['rating']}</code>")
            lines.append(f"  {r['signal']} · Fiyat {r['price']:.4f}")
            if r.get("stop"):
                lines.append(f"  🛑 Stop: <code>{r['stop']:.4f}</code>")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Tarama hatası: {str(e)[:200]}"


# pandas için lazy import
try:
    import pandas as pd
except ImportError:
    pd = None


def handle_message(text: str, chat_id) -> str | None:
    """Mesajı işle, cevap üret."""
    text = text.strip()
    if not text:
        return None
    lower = text.lower()

    # Komut
    if lower.startswith("/help") or lower in ("/start", "help"):
        return HELP_TEXT
    if lower.startswith("/portfoy") or lower.startswith("/portföy"):
        return cmd_portfolio()
    if lower.startswith("/tara"):
        parts = lower.split()
        cat = parts[1] if len(parts) > 1 else "bist"
        return cmd_scan(cat)

    # Sembol algıla
    sym = parse_symbol(text)
    if sym:
        return analyze_and_format(sym)

    # Bilinmeyen
    return (f"❓ Anlamadım: <code>{text[:50]}</code>\n\n"
             f"<code>/help</code> yaz, komut listesini gör.")


# ── POLLING ────────────────────────────────────────────────────────
def poll_once():
    """Bir tur polling — yeni mesajları işle. Streamlit scheduler'dan çağrılır."""
    token, _ = _get_creds()
    if not token:
        return

    state = _load_state()
    offset = state.get("last_update_id", 0) + 1
    updates = get_updates(offset=offset)

    for upd in updates:
        try:
            uid = upd.get("update_id", 0)
            if uid > state.get("last_update_id", 0):
                state["last_update_id"] = uid

            msg = upd.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")
            if not chat_id or not text:
                continue

            log.info(f"[bot] mesaj: {text[:50]} (chat {chat_id})")
            reply = handle_message(text, chat_id)
            if reply:
                send_reply(chat_id, reply)
        except Exception as e:
            log.exception(f"update işleme hatası: {e}")

    _save_state(state)


if __name__ == "__main__":
    # CLI test
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        # `python telegram_bot.py AKBNK` → analiz konsola
        sym = parse_symbol(sys.argv[1])
        if sym:
            print(analyze_and_format(sym))
        else:
            print(f"Sembol bulunamadı: {sys.argv[1]}")
    else:
        # Polling test
        print("Polling testi (Ctrl+C ile dur)...")
        import time
        while True:
            poll_once()
            time.sleep(5)
