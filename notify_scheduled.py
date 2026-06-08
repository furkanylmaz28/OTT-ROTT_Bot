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
    # Gece raporu — sabah hazırlığı için (BIST kapalı, son veriler)
    (1, 45,  "konsensus", "BIST"),
]

# Rating sıralaması — ORTA ve üstü kabul
RT_SCORE = {"MÜKEMMEL": 5, "İYİ": 4, "ORTA": 3,
            "MARJINAL": 2, "VERİ_AZ": 1, "UYUMSUZ": 0}
MIN_RT = 3   # ORTA ve üstü

# ÇIK YAKIN uyarı eşiği (%) — açık pozisyon trailing stop'a bu kadar yaklaşınca uyar
EXIT_WARN_PCT = 1.0


def market_open_categories(now_tr):
    """Şu an hangi piyasa(lar) açık? (hafta içi). Dayanıklı fallback için.
    BIST 10:00-18:00, NASDAQ 16:30-23:00 TR. CRYPTO/EMTIA hafta içi ~tüm gün.
    Hafta sonu kapalı (main()'de zaten engellenir; emtia/forex hafta sonu kapalı,
    crypto 7/24 ama hafta sonu takibi v1'de yok)."""
    if now_tr.weekday() >= 5:
        return []
    hm = now_tr.hour * 60 + now_tr.minute
    out = []
    if 10 * 60 <= hm <= 18 * 60:            # BIST
        out.append("BIST")
    if 16 * 60 + 30 <= hm <= 23 * 60:       # NASDAQ (TR saati)
        out.append("NASDAQ")
    # Crypto (7/24) ve Emtia/Forex (metaller+forex, hafta içi ~24h) → her zaman aç
    out.append("CRYPTO")
    out.append("EMTIA")
    return out


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


def _bist_set():
    """BIST 45 VIOP listesi (per_symbol_optimize.BIST30)."""
    try:
        from per_symbol_optimize import BIST30
        return set(BIST30)
    except Exception:
        return set()


def _crypto_set():
    try:
        from per_symbol_optimize import CRYPTO30
        return set(CRYPTO30)
    except Exception:
        return set()


def _emtia_set():
    try:
        from per_symbol_optimize import EMTIA_FX
        return set(EMTIA_FX)
    except Exception:
        return {"GC=F", "SI=F", "PA=F", "EURUSD=X", "GBPUSD=X"}


def filter_symbols_by_category(syms, category):
    """Kategoriye göre filtre.

    BIST   = sadece tanımlı 45 VIOP hissesi (JSON'daki eski semboller HARİÇ).
    NASDAQ = sadece GCM Forex MetaTrader'da işlem gören hisseler.
    CRYPTO = -USD coinleri.   EMTIA = metaller + forex (=F / =X).
    """
    out = []
    bset = _bist_set()
    cset = _crypto_set()
    eset = _emtia_set()
    for s in syms:
        if category == "BIST":
            if s in bset:   # sadece 45 VIOP hissesi
                out.append(s)
        elif category == "NASDAQ":
            if s in GCM_TICKERS:
                out.append(s)
        elif category == "CRYPTO":
            if s in cset:
                out.append(s)
        elif category == "EMTIA":
            if s in eset:
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
        last = s.iloc[-2] if len(s) >= 2 else s.iloc[-1]  # son KAPANMIŞ bar (oluşan mum değil)
        cur = float(df["close"].iloc[-1])
        sig = signal_label(last)
        if sig is None:
            return None
        # Yöne göre stop seviyesi (TOTT karşı tetik)
        # closed = kapanmış bar (sistem bunu kullanır), forming = oluşan bar (canlı önizleme)
        forming = s.iloc[-1]
        if "LONG" in sig:
            stop = float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None
            stop_live = float(forming["tott_dn"]) if not pd.isna(forming["tott_dn"]) else None
            yon = "LONG"
        elif "SHORT" in sig:
            stop = float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None
            stop_live = float(forming["tott_up"]) if not pd.isna(forming["tott_up"]) else None
            yon = "SHORT"
        else:
            stop = None; stop_live = None; yon = None

        # Stop yönü: oluşan stop kapanmış stop'a göre sıkışıyor mu? (ratchet)
        #   LONG: stop yükseliyorsa lehine (sıkışıyor) ; SHORT: stop düşüyorsa lehine
        stop_trend = None
        if stop is not None and stop_live is not None:
            if yon == "LONG":
                stop_trend = "tighten" if stop_live > stop else ("flat" if stop_live == stop else "loosen")
            elif yon == "SHORT":
                stop_trend = "tighten" if stop_live < stop else ("flat" if stop_live == stop else "loosen")

        # ── ÇIK YAKIN: açık pozisyon (TUT) trailing stop'a yaklaştı mı?
        #    LONG TUT: fiyat tott_dn'e (aşağı stop) yaklaşırsa
        #    SHORT TUT: fiyat tott_up'a (yukarı stop) yaklaşırsa
        #    Stop YEMEDEN önce uyarı (kullanıcı talebi).
        exit_warn = False
        exit_dist = None
        if "TUT" in sig and stop and stop > 0:
            if yon == "LONG":
                exit_dist = (cur / stop - 1) * 100      # stop altta, pozitif mesafe
            elif yon == "SHORT":
                exit_dist = (stop / cur - 1) * 100      # stop üstte, pozitif mesafe
            if exit_dist is not None and 0 < exit_dist < EXIT_WARN_PCT:
                exit_warn = True

        return {
            "sym": sym,
            "signal": sig,
            "yon": yon,
            "price": cur,
            "stop": stop,
            "is_fresh": ("AÇ" in sig or "ÇIK" in sig),  # taze sinyal mi
            "exit_warn": exit_warn,
            "exit_dist": exit_dist,
            "stop_live": stop_live,     # oluşan-bar canlı stop (bu bar kapanınca kilitlenecek)
            "stop_trend": stop_trend,   # tighten / flat / loosen
        }
    except Exception:
        return None


def _fv_telegram_on_open(sym, side, price, stop):
    """Forward-validation yeni pozisyon açınca Telegram'a bildir (#8)."""
    flag = "🇹🇷" if sym.upper().endswith(".IS") else "🇺🇸"
    yon = "🟢 LONG AÇILDI" if side == "LONG" else "🔴 SHORT AÇILDI"
    lines = [f"{flag} <b>{sym}</b> — {yon}",
             f"📈 Giriş: <code>{price:.4f}</code>"]
    if stop:
        sp = abs(price - stop) / price * 100
        lines.append(f"🛑 Stop: <code>{stop:.4f}</code> ({sp:.2f}%)")
    lines.append(f"<i>{datetime.now(TR):%d/%m %H:%M} TR · canlı takip</i>")
    try:
        send_telegram("\n".join(lines))
    except Exception:
        pass


def scan_category(category, mode, grid, bayes):
    """Kategorideki sembolleri tara → mode'a göre filtrele."""
    syms = sorted(set(list(grid.keys()) + list(bayes.keys())))
    syms = filter_symbols_by_category(syms, category)

    results = []
    for sym in syms:
        # Grid (FY) UYUMSUZ ise hiç gösterme (kullanıcı talebi)
        if grid.get(sym, {}).get("ok") and grid[sym].get("rating") == "UYUMSUZ":
            continue
        # ── NASDAQ evreni çok büyük (416) → sadece GRID İYİ+ takip et.
        #    Grid muhafazakâr → konsensüs kalitesi. Tarama hızlanır, koşular
        #    iptal olmaz, Telegram spam'i azalır. (BIST/Crypto/Emtia küçük → ORTA+ kalır.)
        if category == "NASDAQ":
            grt = grid.get(sym, {}).get("rating") if grid.get(sym, {}).get("ok") else None
            if grt not in ("İYİ", "MÜKEMMEL"):
                continue
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

        # ── FORWARD-VALIDATION: profesyonel trader takibi (sadece taze AÇ, seans içi)
        try:
            import forward_validation as fv
            fv.record_observation(
                sym, a["signal"], a["price"], stop=a.get("stop"),
                on_open=_fv_telegram_on_open,   # yeni pozisyon → Telegram (#8)
            )
        except Exception:
            pass

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
        elif mode == "warn":
            # ÇIK YAKIN — sadece trailing stop'a yaklaşan açık pozisyonlar (TUT)
            if not a.get("exit_warn"):
                continue

        # Backtest stats (None değerleri 0'a çevir)
        stats = params_info.get("stats", {})
        a["rating"]   = rating
        a["bt_ret"]   = (stats.get("return") or 0) * 100  # yüzde (JSON key: "return")
        # PF None → JSON'da kayıp yok demek (sonsuz). 999 sentinel ile işaretle.
        _pf = stats.get("pf")
        a["bt_pf"]    = 999 if _pf is None else _pf
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
    # ── ÇIK YAKIN uyarısı — ayrı, vurgulu format (stop yemeden önce)
    if mode == "warn":
        flag = "🇹🇷" if category == "BIST" else "🇺🇸"
        lines = [f"⚠️ {flag} <b>{category} — STOP YAKLAŞIYOR</b>",
                 f"<i>{scan_time.strftime('%d/%m/%Y · %H:%M')} TR · "
                 f"{len(results)} pozisyon stop'a yakın</i>",
                 "━━━━━━━━━━━━━━━━━━━━"]
        for r in results:
            yon_emo = "🟢" if r["yon"] == "LONG" else "🔴"
            dist = r.get("exit_dist")
            dist_str = f"{dist:.2f}%" if dist is not None else "?"
            lines.append("")
            lines.append(f"{yon_emo} <b>{r['sym']}</b> — {r['yon']} pozisyon")
            lines.append(f"   Fiyat: <code>{r['price']:.4f}</code>")
            if r["stop"]:
                lines.append(f"   🛑 Trailing stop: <code>{r['stop']:.4f}</code>  "
                              f"<b>(yalnız {dist_str} uzakta!)</b>")
            # Canlı (oluşan-bar) stop — bu bar kapanınca kilitlenecek seviye
            sl = r.get("stop_live"); strend = r.get("stop_trend")
            if sl:
                arrow = {"tighten": "↓ sıkışıyor (lehine)", "loosen": "↑ gevşiyor",
                         "flat": "= sabit"}.get(strend, "")
                lines.append(f"   🔮 Oluşan stop: <code>{sl:.4f}</code>  <i>{arrow}</i>")
            lines.append(f"   → Stop yakın. Yönet: ya çık ya SL'yi sıkılaştır.")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Fiyat stop'u kırarsa sinyal çıkışa döner. Stop YEMEDEN karar ver.</i>")
        lines.append("📱 https://furkanyilmaz.streamlit.app")
        return "\n".join(lines)

    mode_labels = {
        "konsensus": "Konsensüs Mod ⭐⭐",
        "morning":   "Bugünün Önerileri 🌅",
        "scan":      "Anlık Tarayıcı 📡",
    }
    flag = "🇹🇷" if category == "BIST" else "🇺🇸"
    title = f"{flag} <b>{category} {mode_labels[mode]}</b>"
    lines = [title,
             f"<i>{scan_time.strftime('%d/%m/%Y · %H:%M')} TR · "
             f"<b>{len(results)} sinyal</b></i>",
             "━━━━━━━━━━━━━━━━━━━━"]

    for i, r in enumerate(results, 1):
        emoji_rt = {"MÜKEMMEL": "🏆", "İYİ": "⭐", "ORTA": "🟢"}.get(r["rating"], "•")
        # Yön emojisi
        yon_emo = "🟢" if r["yon"] == "LONG" else "🔴" if r["yon"] == "SHORT" else "🟡"

        # Başlık satırı
        lines.append(f"")
        lines.append(f"{emoji_rt} <b>{r['sym']}</b>  <code>{r['rating']}</code>")
        # Sinyal — vurgulu
        lines.append(f"   {yon_emo} <b>{r['signal'].replace(yon_emo + ' ', '')}</b>")

        # FİYAT + STOP — yan yana, vurgulu (broker'a koyacağı emir bilgisi)
        if r["stop"]:
            stop_pct = (abs(r["price"] - r["stop"]) / r["price"] * 100)
            lines.append(f"   ┌ <b>Giriş:</b> <code>{r['price']:.4f}</code>")
            lines.append(f"   └ <b>STOP:</b>  <code>{r['stop']:.4f}</code>  "
                          f"<i>({stop_pct:.2f}% mesafe)</i>")
        else:
            lines.append(f"   <b>Fiyat:</b> <code>{r['price']:.4f}</code>")

        # BT istatistik — kompakt
        pf_str = "∞" if r["bt_pf"] >= 900 else f"{r['bt_pf']:.2f}"
        lines.append(f"   📊 Win <b>{r['bt_win']:.0f}%</b> · "
                      f"PF <b>{pf_str}</b> · "
                      f"Ret {r['bt_ret']:+.1f}% · "
                      f"{int(r['bt_n'])} trade")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Broker'da SL emrini yukarıdaki STOP seviyesine koy.</i>")
    lines.append("📱 https://furkanyilmaz.streamlit.app")
    return "\n".join(lines)


STATE_FILE = "notify_state_scheduled.json"
SPAM_WINDOW_HOURS = 3   # aynı sembol+sinyal bu kadar saat içinde tekrar gönderilmez


def _load_state():
    """{sym+signal: iso_timestamp} formatı."""
    import os
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  State kaydı başarısız: {e}")


def _filter_new_signals(results, mode, category, scan_time):
    """Son 3 saat içinde gönderilen aynı (sembol + sinyal) çiftlerini ele.
    Yeni sinyaller geri döner + state güncellenir."""
    from datetime import timedelta
    state = _load_state()
    cutoff = scan_time - timedelta(hours=SPAM_WINDOW_HOURS)
    fresh = []
    for r in results:
        # Key: sembol + sinyal yönü/durumu (mode+kat farklı olabilir ama sinyal aynıysa spam)
        # warn modu AYRI anahtar kullanır → normal TUT sinyaliyle çakışmaz
        # (yoksa scan TUT gönderince warn uyarısı bastırılırdı).
        if mode == "warn":
            key = f"{r['sym']}|EXIT_WARN"
        else:
            key = f"{r['sym']}|{r['signal']}"
        last_ts_str = state.get(key)
        if last_ts_str:
            try:
                last_ts = datetime.fromisoformat(last_ts_str)
                if last_ts > cutoff:
                    # Son 3 saat içinde gönderilmiş, atla
                    continue
            except Exception:
                pass
        fresh.append(r)
        state[key] = scan_time.isoformat()
    # Eski kayıtları temizle (24 saat öncesi)
    cleanup_cutoff = scan_time - timedelta(hours=24)
    state = {k: v for k, v in state.items()
             if datetime.fromisoformat(v) > cleanup_cutoff}
    _save_state(state)
    return fresh


def prune_untracked_positions(grid):
    """Artık takip etmediğimiz sembollerin açık pozisyonlarını sil (yetim temizliği).
    NASDAQ: sadece Grid İYİ+ takip edilir; altında kalan NASDAQ pozisyonları
    bir daha taranmaz → silinmezse sonsuza dek açık kalır."""
    try:
        import forward_validation as fv
    except Exception:
        return
    pos = fv.open_positions()
    if not pos:
        return
    gcm = GCM_TICKERS
    removed = []
    for sym in list(pos.keys()):
        # NASDAQ (GCM hissesi) ve Grid İYİ+ değilse → yetim, sil
        if sym in gcm:
            grt = grid.get(sym, {}).get("rating") if grid.get(sym, {}).get("ok") else None
            if grt not in ("İYİ", "MÜKEMMEL"):
                removed.append(sym)
        # Grid UYUMSUZ olan her şey
        elif grid.get(sym, {}).get("ok") and grid[sym].get("rating") == "UYUMSUZ":
            removed.append(sym)
    if removed:
        positions = fv._load(fv.POS_FILE, {})
        for s in removed:
            positions.pop(s, None)
        fv._save(fv.POS_FILE, positions)
        print(f"  🧹 Yetim pozisyon temizlendi ({len(removed)}): {removed[:10]}")


def run_task(mode, category, scan_time, grid, bayes):
    """Belirli mode + kategori için tarama + Telegram gönder."""
    print(f"\n▶ {category} {mode} taraması başladı")
    results = scan_category(category, mode, grid, bayes)
    print(f"  Sonuç: {len(results)} sinyal (ORTA+ güven)")
    if not results:
        print(f"  Mesaj atlandı (uygun sinyal yok)")
        return

    # Spam koruması — son 3 saat içinde aynı sinyali gönderme
    fresh = _filter_new_signals(results, mode, category, scan_time)
    print(f"  Yeni (son {SPAM_WINDOW_HOURS}sa içinde gönderilmemiş): {len(fresh)}")
    if not fresh:
        print(f"  Tüm sinyaller son {SPAM_WINDOW_HOURS} saatte gönderildi, mesaj atlandı")
        return

    msg = format_message(fresh, mode, category, scan_time)
    if msg:
        ok = send_telegram(msg)
        print(f"  Telegram: {'✓ gönderildi' if ok else '✗ HATA'}")
        for r in fresh[:10]:
            print(f"    • {r['sym']} {r['signal']} ({r['rating']})")


def main():
    now_tr = datetime.now(TR)
    h, m = now_tr.hour, now_tr.minute
    print(f"[notify_scheduled] {now_tr.strftime('%Y-%m-%d %H:%M')} TR")

    cfg = is_configured()
    if not cfg["telegram"]:
        print("✗ Telegram yapılandırılmamış, çıkılıyor")
        return

    # ── HAFTA SONU KORUMASI ──────────────────────────────────────────
    # Cumartesi/Pazar her iki borsa da kapalı → sinyaller bayat (Cuma kapanış)
    # verisinden gelir. record_observation hafta sonu zaten kayıt açmıyor;
    # bildirim yolu da yapmamalı (yoksa kullanıcıya yanıltıcı/bayat mesaj gider).
    # (BIST=.IS ve NASDAQ hisseleri hafta içi işler; crypto bildirimi yok.)
    if now_tr.weekday() >= 5:
        print(f"  Hafta sonu ({now_tr.strftime('%A')}) — borsalar kapalı, bildirim yok")
        return

    # Şu anki saate uyan görevleri bul.
    # Cron her 10 dk'da bir çalışıyor → tolerans 5 dk olmalı (10 dk pencere içinde
    # tarama saati varsa yakala). Hedef saatten ÖNCE 5 dk içinde olmalı —
    # geçmişe doğru tolerans yok ki aynı tarama tekrar tetiklenmesin.
    matches = []
    for sh, sm, mode, cat in SCHEDULE:
        if sh != h:
            continue
        # Pipedream 15 dk aralıkla tetikliyor (offset :11,:26,:41,:56).
        # Hedef saate 0-14 dk içindeki ilk tetik yakalar.
        # Spam koruması (3 saat) tekrar göndermeyi zaten engelliyor.
        diff = m - sm
        if 0 <= diff < 15:
            matches.append((mode, cat))

    # TEST MODU — env var WORKFLOW_TEST=1 ise şu anki saati ekle
    if os.getenv("WORKFLOW_TEST") == "1":
        matches.append(("scan", "BIST"))
        matches.append(("scan", "NASDAQ"))
        print(f"  ⚠️ TEST MODU — şu anki saatte BIST + NASDAQ scan zorla tetiklendi")

    # ── DAYANIKLI FALLBACK ───────────────────────────────────────────
    # GitHub Actions cron'u (*/10) güvenilmez — günde sadece birkaç kez,
    # RASTGELE dakikalarda ateşliyor → sabit SCHEDULE saatlerinin 0-15 dk
    # penceresini sürekli kaçırıyor (gözlemlendi: hiç mesaj gitmedi).
    # Çözüm: bu tetikte tam saat eşleşmesi YOKSA ve piyasa AÇIKSA, yine de
    # konsensüs + morning tara. 3 saatlik spam koruması (sym|signal bazlı)
    # tekrar göndermeyi zaten engelliyor → cron-job.org tam saatte gönderse
    # bile burada tekrar gitmez.
    if not matches:
        open_cats = market_open_categories(now_tr)
        for cat in open_cats:
            matches.append(("konsensus", cat))
            matches.append(("morning", cat))
        if matches:
            print(f"  ⚠️ Tam saat eşleşmesi yok ama piyasa açık ({', '.join(open_cats)}) "
                  f"→ dayanıklı fallback devrede (spam koruması tekrarı engeller)")

    # ── ÇIK YAKIN KONTROLÜ — her tetikte (piyasa açıkken) ────────────
    # Stop'a yaklaşma zaman-hassas → 15 dk'da bir kontrol edilmeli, sabit
    # saate bağlı değil. Açık piyasadaki her sembolü tarar, trailing stop'a
    # %1 yaklaşan TUT pozisyonları için "STOP YAKLAŞIYOR" uyarısı gönderir.
    # Spam koruması (3 saat) sürekli tekrarı engeller.
    for cat in market_open_categories(now_tr):
        if ("warn", cat) not in matches:
            matches.append(("warn", cat))

    if not matches:
        print(f"  Bu saatte ({h:02d}:{m:02d}) tarama yok (piyasa da kapalı)")
        return

    print(f"  Eşleşen görev sayısı: {len(matches)}")
    grid, bayes = load_param_files()
    print(f"  Veri: Grid={len(grid)}, Bayes={len(bayes)}")

    # ── YETİM POZİSYON TEMİZLİĞİ ─────────────────────────────────────
    # 416-NASDAQ rejiminde açılmış ama artık takip etmediğimiz (Grid İYİ+ değil)
    # pozisyonlar bir daha taranmaz → asla kapanmaz. Bunları sil (kendiliğinden
    # düzelir). Sadece güncel takip evreni dışındaki NASDAQ pozisyonları.
    try:
        prune_untracked_positions(grid)
    except Exception as e:
        print(f"  Prune hatası: {e}")

    for mode, cat in matches:
        try:
            run_task(mode, cat, now_tr, grid, bayes)
        except Exception as e:
            import traceback
            print(f"  HATA ({mode} {cat}): {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
