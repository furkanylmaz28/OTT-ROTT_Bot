"""
notify_scheduled.py — saate göre Telegram bildirim dispatcher.

Her tetiklenmede şu anki TR saatine göre hangi taramaları yapacağına karar verir.

Zaman çizelgesi (TR saati):

BIST (Türkiye piyasa saatleri 10:00–18:00)
  Konsensüs    : 11:00, 14:00, 17:00
  Bugün Öneri  : 10:10, 12:10, 15:10, 17:10
  Anlık Tarama : 10:30, 12:30, 15:30, 17:30

NASDAQ (US piyasa saatleri TR 17:30–24:00)
  Konsensüs    : 17:30, 20:30, 22:00
  Bugün Öneri  : 16:40, 18:40, 20:40, 22:40
  Anlık Tarama : 17:00, 19:00, 21:00, 23:00

Filtre: Güven ORTA + İYİ + MÜKEMMEL (MARJINAL/VERİ_AZ/UYUMSUZ atlanır).
Mesaj: Sembol · Güven · Yön (LONG/SHORT) · Fiyat · Stop · BT istatistik.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import os, json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import signals_full as sig_full
from data_source import fetch as ds_fetch, best_interval_for, category_of
from notifications import send_telegram, is_configured


def _load_gcm_set():
    """GCM Forex MetaTrader'daki hisselerin yfinance ticker seti."""
    try:
        with open("gcm_to_yf_map.json", encoding="utf-8") as f:
            d = json.load(f)
        return set(d["mapping"].values())
    except Exception:
        return set()


GCM_TICKERS = _load_gcm_set()

# TR saat dilimi (UTC+3, DST yok)
TR = timezone(timedelta(hours=3))

# Saat → (mode, category) eşleştirmesi
SCHEDULE = [
    # BIST
    (11, 0,  "konsensus", "BIST"),
    (14, 0,  "konsensus", "BIST"),
    (17, 0,  "konsensus", "BIST"),
    (10, 10, "morning",   "BIST"),
    (12, 10, "morning",   "BIST"),
    (15, 10, "morning",   "BIST"),
    (17, 10, "morning",   "BIST"),
    (10, 30, "scan",      "BIST"),
    (12, 30, "scan",      "BIST"),
    (15, 30, "scan",      "BIST"),
    (17, 30, "scan",      "BIST"),
    # NASDAQ — bazı saatler BIST ile çakışır (ikisi de yapılır)
    (17, 30, "konsensus", "NASDAQ"),
    (20, 30, "konsensus", "NASDAQ"),
    (22, 0,  "konsensus", "NASDAQ"),
    (16, 40, "morning",   "NASDAQ"),
    (18, 40, "morning",   "NASDAQ"),
    (20, 40, "morning",   "NASDAQ"),
    (22, 40, "morning",   "NASDAQ"),
    (17, 0,  "scan",      "NASDAQ"),
    (19, 0,  "scan",      "NASDAQ"),
    (21, 0,  "scan",      "NASDAQ"),
    (23, 0,  "scan",      "NASDAQ"),
]

# Rating sıralaması — ORTA ve üstü kabul
RT_SCORE = {"MÜKEMMEL": 5, "İYİ": 4, "ORTA": 3,
            "MARJINAL": 2, "VERİ_AZ": 1, "UYUMSUZ": 0}
MIN_RT = 3   # ORTA ve üstü


def load_param_files():
    """Grid + Bayes JSON'larını yükle."""
    grid, bayes = {}, {}
    try:
        with open("per_symbol_params.json") as f: grid = json.load(f)
    except Exception: pass
    try:
        with open("per_symbol_params_bayes.json") as f: bayes = json.load(f)
    except Exception: pass
    return grid, bayes


def get_best_params(sym, grid, bayes):
    """Bayes önceliği, yoksa grid."""
    if sym in bayes and bayes[sym].get("ok"):
        return bayes[sym], "Bayes"
    if sym in grid and grid[sym].get("ok"):
        return grid[sym], "Grid"
    return None, None


def filter_symbols_by_category(syms, category):
    """BIST veya NASDAQ kategorisine göre filtre.

    NASDAQ = sadece GCM Forex MetaTrader'da işlem gören hisseler.
    (gcm_to_yf_map.json'daki ticker'lar — Türkiye'den GCM ile alıp satılabilir.)
    """
    out = []
    for s in syms:
        if category == "BIST":
            if s.upper().endswith(".IS"):
                out.append(s)
        elif category == "NASDAQ":
            # Sadece GCM MetaTrader'da gerçekten olan hisseler
            if s in GCM_TICKERS:
                out.append(s)
    return out


def signal_label(last, side_pref=None):
    """Son bar sinyal etiketi."""
    if last["cond_buy_long"]:        return "🟢 LONG AÇ"
    if last["cond_buy_short"]:       return "🔴 SHORT AÇ"
    if last["cond_exit_long"]:       return "🟡 LONG ÇIK"
    if last["cond_exit_short"]:      return "🟡 SHORT ÇIK"
    if last["major_up"] and last["zone_up"]:    return "🟢 LONG TUT"
    if last["major_dn"] and last["zone_dn"]:    return "🔴 SHORT TUT"
    return None


def analyze_one(sym, params):
    """Bir sembolün sinyal + fiyat + stop + güven detayını döndür."""
    try:
        df = ds_fetch(sym, interval=best_interval_for(sym), n_bars=2500)
        if df.empty or len(df) < 1500:
            return None
        p = params.copy()
        p.setdefault("rott_x1", 30); p.setdefault("rott_x2", 1000)
        p.setdefault("rott_percent", 7.0)
        s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **p)
        last = s.iloc[-1]
        cur = float(df["close"].iloc[-1])
        sig = signal_label(last)
        if sig is None:
            return None
        # Yöne göre stop seviyesi (TOTT karşı tetik)
        if "LONG" in sig:
            stop = float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None
            yon = "LONG"
        elif "SHORT" in sig:
            stop = float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None
            yon = "SHORT"
        else:
            stop = None; yon = None
        return {
            "sym": sym,
            "signal": sig,
            "yon": yon,
            "price": cur,
            "stop": stop,
            "is_fresh": ("AÇ" in sig or "ÇIK" in sig),  # taze sinyal mi
        }
    except Exception:
        return None


def scan_category(category, mode, grid, bayes):
    """Kategorideki sembolleri tara → mode'a göre filtrele."""
    syms = sorted(set(list(grid.keys()) + list(bayes.keys())))
    syms = filter_symbols_by_category(syms, category)

    results = []
    for sym in syms:
        # Bayes önceliği
        params_info, src = get_best_params(sym, grid, bayes)
        if not params_info:
            continue
        rating = params_info.get("rating", "?")
        rt_score = RT_SCORE.get(rating, 0)
        if rt_score < MIN_RT:   # ORTA altı atla
            continue

        a = analyze_one(sym, params_info["params"])
        if not a:
            continue

        # Mode'a göre filtre
        if mode == "konsensus":
            # Hem Grid hem Bayes aynı yön AÇ sinyali vermeli
            if sym not in grid or sym not in bayes:
                continue
            if not (grid[sym].get("ok") and bayes[sym].get("ok")):
                continue
            ag = analyze_one(sym, grid[sym]["params"])
            ab = analyze_one(sym, bayes[sym]["params"])
            if not ag or not ab:
                continue
            # Sadece taze AÇ konsensüsleri
            if ("AÇ" in ag["signal"]) and ("AÇ" in ab["signal"]) and (ag["yon"] == ab["yon"]):
                a["signal"] = ag["signal"]   # konsensus sinyali
                a["yon"]    = ag["yon"]
                a["stop"]   = ag["stop"] or ab["stop"]
            else:
                continue
        elif mode == "morning":
            # Bugünün önerileri — sadece taze AÇ sinyalleri (top-5)
            if not a["is_fresh"] or "ÇIK" in a["signal"]:
                continue
        elif mode == "scan":
            # Tüm aktif sinyaller — TUT da dahil, ÇIK dahil
            pass

        # Backtest stats (None değerleri 0'a çevir)
        stats = params_info.get("stats", {})
        a["rating"]   = rating
        a["bt_ret"]   = (stats.get("ret_pct") or 0) * 100  # yüzde
        a["bt_pf"]    = stats.get("pf") or 0
        a["bt_win"]   = (stats.get("win_rate") or 0) * 100
        a["bt_n"]     = stats.get("n_trades") or 0
        a["params_src"] = src
        results.append(a)

    # Sıralama: rating yüksek + BT getiri yüksek
    results.sort(key=lambda r: (RT_SCORE.get(r["rating"], 0), r["bt_ret"]),
                  reverse=True)
    # Morning modunda top-5
    if mode == "morning":
        results = results[:5]
    return results


def format_message(results, mode, category, scan_time):
    """Telegram mesajı oluştur — HTML format."""
    if not results:
        return None
    mode_labels = {
        "konsensus": "Konsensüs Mod",
        "morning":   "Bugünün Önerileri",
        "scan":      "Anlık Tarayıcı",
    }
    title = f"🤖 OTT Bot · <b>{category} {mode_labels[mode]}</b>"
    lines = [title, f"<i>{scan_time.strftime('%d/%m/%Y %H:%M')} TR · "
                     f"{len(results)} sinyal</i>", ""]

    for r in results:
        emoji_rt = {"MÜKEMMEL": "🏆", "İYİ": "⭐", "ORTA": "🟢"}.get(r["rating"], "•")
        lines.append(f"{emoji_rt} <b>{r['sym']}</b> · <i>{r['rating']}</i>")
        lines.append(f"   {r['signal']}")
        lines.append(f"   💰 Fiyat: <b>{r['price']:.4f}</b>")
        if r["stop"]:
            stop_pct = (abs(r["price"] - r["stop"]) / r["price"] * 100)
            lines.append(f"   🛑 Stop:  <b>{r['stop']:.4f}</b>  "
                          f"({stop_pct:.2f}% uzak · TOTT karşı tetik)")
        pf_str = "∞" if r["bt_pf"] >= 900 else f"{r['bt_pf']:.2f}"
        lines.append(f"   📊 BT: Ret {r['bt_ret']:+.1f}% · PF {pf_str} · "
                      f"Win {r['bt_win']:.0f}% · {int(r['bt_n'])} trade")
        lines.append("")

    lines.append("📱 https://furkanyilmaz.streamlit.app")
    return "\n".join(lines)


def run_task(mode, category, scan_time, grid, bayes):
    """Belirli mode + kategori için tarama + Telegram gönder."""
    print(f"\n▶ {category} {mode} taraması başladı")
    results = scan_category(category, mode, grid, bayes)
    print(f"  Sonuç: {len(results)} sinyal (ORTA+ güven)")
    if not results:
        print(f"  Mesaj atlandı (uygun sinyal yok)")
        return
    msg = format_message(results, mode, category, scan_time)
    if msg:
        ok = send_telegram(msg)
        print(f"  Telegram: {'✓ gönderildi' if ok else '✗ HATA'}")
        for r in results[:10]:
            print(f"    • {r['sym']} {r['signal']} ({r['rating']})")


def main():
    now_tr = datetime.now(TR)
    h, m = now_tr.hour, now_tr.minute
    print(f"[notify_scheduled] {now_tr.strftime('%Y-%m-%d %H:%M')} TR")

    cfg = is_configured()
    if not cfg["telegram"]:
        print("✗ Telegram yapılandırılmamış, çıkılıyor")
        return

    # Şu anki saate uyan görevleri bul.
    # Cron her 10 dk'da bir çalışıyor → tolerans 5 dk olmalı (10 dk pencere içinde
    # tarama saati varsa yakala). Hedef saatten ÖNCE 5 dk içinde olmalı —
    # geçmişe doğru tolerans yok ki aynı tarama tekrar tetiklenmesin.
    matches = []
    for sh, sm, mode, cat in SCHEDULE:
        if sh != h:
            continue
        # Hedef dakikaya 0-9 dakika içindeyse (içinde 1 cron tetiği vardır)
        # m hedef sm'den önce: GitHub henüz tetiklemedi, atla
        # m hedef sm'den 0-9 sonra: tetikle
        diff = m - sm
        if 0 <= diff < 10:
            matches.append((mode, cat))

    if not matches:
        print(f"  Bu saatte ({h:02d}:{m:02d}) tarama yok")
        return

    print(f"  Eşleşen görev sayısı: {len(matches)}")
    grid, bayes = load_param_files()
    print(f"  Veri: Grid={len(grid)}, Bayes={len(bayes)}")

    for mode, cat in matches:
        try:
            run_task(mode, cat, now_tr, grid, bayes)
        except Exception as e:
            import traceback
            print(f"  HATA ({mode} {cat}): {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
