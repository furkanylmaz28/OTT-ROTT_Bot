"""
Bildirim daemon'u — saatte bir konsensüs sinyallerini kontrol eder.
Yeni AÇ veya ÇIK sinyali görürse Telegram + Email gönderir.

Lokal çalıştırma:  python notify_daemon.py
Veya Windows Task Scheduler ile her saat tetikle.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import os, json, time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import signals_full as sig_full
from data_source import fetch as ds_fetch, best_interval_for, category_of
from notifications import notify, is_configured

STATE_FILE = "notify_state.json"        # son sinyaller (yenisini farkına varmak için)
CHECK_INTERVAL_SEC = 3600                # saatte bir kontrol
SLEEP_SEC = 60


def _signal_label(last):
    if last["cond_buy_long"]:        return "🟢 LONG AÇ"
    if last["cond_buy_short"]:       return "🔴 SHORT AÇ"
    if last["cond_exit_long"]:       return "🟡 LONG ÇIK"
    if last["cond_exit_short"]:      return "🟡 SHORT ÇIK"
    if last["major_up"] and last["zone_up"]:    return "🟢 LONG TUT"
    if last["major_dn"] and last["zone_dn"]:    return "🔴 SHORT TUT"
    if last["major_up"]:             return "⏳ LONG bekle"
    if last["major_dn"]:             return "⏳ SHORT bekle"
    return "—"


def scan_consensus():
    """Konsensüs sinyallerini bul."""
    try:
        with open("per_symbol_params.json") as f: grid = json.load(f)
    except Exception:
        return []
    try:
        with open("per_symbol_params_bayes.json") as f: bayes = json.load(f)
    except Exception:
        bayes = {}

    fresh = []
    for sym, gr in grid.items():
        if not gr.get("ok"): continue
        rating = gr.get("rating", "?")
        if rating not in ("MÜKEMMEL", "İYİ"): continue  # sadece güvenli

        try:
            df = ds_fetch(sym, interval=best_interval_for(sym), n_bars=2500)
            if df.empty or len(df) < 1500: continue
            gp = gr["params"].copy()
            gp.setdefault("rott_x1", 30); gp.setdefault("rott_x2", 1000)
            gp.setdefault("rott_percent", 7.0)
            sg = sig_full.build_signals_full(df["close"], df["high"], df["low"], **gp)
            fy = _signal_label(sg.iloc[-2] if len(sg) >= 2 else sg.iloc[-1])  # kapanmış bar

            # Bayes varsa çek
            bs_sig = None
            if sym in bayes and bayes[sym].get("ok"):
                bp = bayes[sym]["params"].copy()
                bp.setdefault("rott_x1", 30); bp.setdefault("rott_x2", 1000)
                bp.setdefault("rott_percent", 7.0)
                sb = sig_full.build_signals_full(df["close"], df["high"], df["low"], **bp)
                bs_sig = _signal_label(sb.iloc[-2] if len(sb) >= 2 else sb.iloc[-1])  # kapanmış bar

            # Konsensüs türü
            kind = None
            if "AÇ" in fy and bs_sig and "AÇ" in bs_sig and \
               ("LONG" in fy) == ("LONG" in bs_sig):
                kind = "GÜÇLÜ_AÇ"
            elif "AÇ" in fy and not bs_sig:
                kind = "TEK_AÇ"  # bayes yok
            elif "ÇIK" in fy:
                kind = "ÇIK"

            if kind:
                cur = float(df["close"].iloc[-1])
                fresh.append({
                    "sym": sym, "kind": kind, "fy": fy, "bayes": bs_sig,
                    "price": cur, "rating": rating,
                    "category": category_of(sym),
                })
        except Exception:
            continue
    return fresh


def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def format_message(new_signals):
    """HTML format, Telegram + Email uyumlu."""
    if not new_signals:
        return None
    lines = [f"<b>🤖 OTT Bot — {len(new_signals)} yeni sinyal</b>\n"]
    for s in new_signals:
        kind_emoji = "⭐" if s["kind"] == "GÜÇLÜ_AÇ" else "🟡" if s["kind"] == "ÇIK" else "🔵"
        lines.append(f"\n{kind_emoji} <b>{s['sym']}</b> ({s['category']}) — {s['rating']}")
        lines.append(f"   Sinyal: {s['fy']}")
        if s["bayes"]:
            lines.append(f"   Bayes:  {s['bayes']}")
        lines.append(f"   Fiyat:  {s['price']:.4f}")
    lines.append(f"\n<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>")
    lines.append("\n📱 Dashboard: https://furkanyilmaz.streamlit.app")
    return "\n".join(lines)


def main():
    cfg = is_configured()
    print(f"Telegram: {'✓' if cfg['telegram'] else '✗'}  Email: {'✓' if cfg['email'] else '✗'}")
    if not any(cfg.values()):
        print("✗ Hiç bildirim kanalı yapılandırılmamış. .env dosyasına ekle:")
        print("  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        print("  veya NOTIFY_EMAIL, NOTIFY_EMAIL_PASSWORD, NOTIFY_EMAIL_TO")
        return

    print("Bildirim daemon başladı — saatte 1 kontrol")
    last_check = 0
    while True:
        now = time.time()
        if now - last_check >= CHECK_INTERVAL_SEC:
            print(f"\n[{datetime.now()}] Konsensüs taraması...")
            try:
                fresh = scan_consensus()
                state = load_state()
                new = [s for s in fresh
                       if state.get(s["sym"]) != f"{s['kind']}_{s['fy']}"]
                # State güncelle
                for s in fresh:
                    state[s["sym"]] = f"{s['kind']}_{s['fy']}"
                save_state(state)
                if new:
                    msg = format_message(new)
                    r = notify("OTT Bot — Yeni Sinyal", msg, msg.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>",""))
                    print(f"  {len(new)} yeni sinyal — Telegram:{r['telegram']} Email:{r['email']}")
                else:
                    print(f"  {len(fresh)} aktif sinyal var, yeni yok")
            except Exception as e:
                print(f"  HATA: {e}")
            last_check = now
        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
