"""
gcm_bot.py — GCM (MetaTrader 5) demo hesabını yöneten harici otomatik bot.

MİMARİ:
   Python (bizim signals_full.py sinyalleri) → MetaTrader5 paketi → GCM MT5 demo
   → otomatik emir aç/kapat + trailing stop (TOTT bandı).

GÜVENLİK:
   - SADECE DEMO hesapta çalışır (gerçek hesapta otomatik DURUR).
   - DRY_RUN=True iken hiç emir GÖNDERMEZ, sadece ne yapacağını loglar (ilk test).
   - Sabit lot (config), her sembolde tek pozisyon, magic number ile sadece kendi
     açtığı emirleri yönetir.

KURULUM:
   1. GCM MT5 demo terminalini aç + login ol (terminal AÇIK kalmalı).
   2. pip install MetaTrader5
   3. python gcm_bot.py            (önce DRY_RUN=True ile izle)
   4. Güvendiğinde DRY_RUN=False yap.

NOT: Bu bot sinyalleri MT5'in kendi barlarından (broker verisi) hesaplar →
     execution ile tam tutarlı. Parametreler per_symbol_params_bayes.json'dan.
"""
from __future__ import annotations
import sys, time, json, os
from datetime import datetime, timezone, timedelta

import pandas as pd
import signals_full as sig_full

TR = timezone(timedelta(hours=3))

# ──────────────────────────────────────────────────────────────────
#  AYARLAR
# ──────────────────────────────────────────────────────────────────
DRY_RUN       = True          # True: emir GÖNDERME, sadece logla (İLK TEST İÇİN)
LOT           = 0.10          # sabit lot (kullanıcı tercihi)
TIMEFRAME     = "H1"          # sinyal zaman dilimi (hisse/metal = H1)
N_BARS        = 2500          # sinyal için bar sayısı
POLL_SECONDS  = 900           # 15 dk'da bir tarama
MAGIC         = 20260608      # bu botun emir kimliği (sadece kendi emirlerini yönetir)
MAX_POSITIONS = 8             # aynı anda en fazla açık pozisyon (risk sınırı)
DEVIATION     = 20            # izin verilen slippage (puan)

LOG_FILE      = "gcm_bot.log"
MAP_FILE      = "gcm_mt5_symbols.json"   # {yf_ticker: gcm_mt5_symbol} override


def log(msg: str):
    line = f"{datetime.now(TR):%Y-%m-%d %H:%M:%S} | {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────
#  EVREN — "seninle belirlediğimiz hisseler" = GCM'deki Grid İYİ+ hisseler
# ──────────────────────────────────────────────────────────────────
def load_universe():
    """Grid İYİ+ olan GCM hisseleri (konsensüs kalitesi)."""
    try:
        with open("per_symbol_params.json", encoding="utf-8") as f:
            grid = json.load(f)
        with open("per_symbol_params_bayes.json", encoding="utf-8") as f:
            bayes = json.load(f)
        with open("gcm_to_yf_map.json", encoding="utf-8") as f:
            gcm = set(json.load(f)["mapping"].values())
    except Exception as e:
        log(f"Param dosyaları okunamadı: {e}")
        return {}, {}
    GOOD = {"İYİ", "MÜKEMMEL"}
    uni = {}
    for s, v in grid.items():
        if s in gcm and v.get("ok") and v.get("rating") in GOOD:
            # Bayes önceliği (yoksa grid) parametre
            params = (bayes.get(s, {}).get("params")
                      if bayes.get(s, {}).get("ok") else None) or v["params"]
            uni[s] = params
    return uni, grid


def load_symbol_map():
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("map", {}) if isinstance(d, dict) else {}
        except Exception:
            pass
    return {}


# ──────────────────────────────────────────────────────────────────
#  MT5 BAĞLANTI
# ──────────────────────────────────────────────────────────────────
def mt5_connect():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        log(f"❌ MT5 initialize başarısız: {mt5.last_error()}. "
            f"GCM MT5 terminali açık + login mi?")
        return None
    acc = mt5.account_info()
    if acc is None:
        log("❌ Hesap bilgisi alınamadı."); mt5.shutdown(); return None
    # GÜVENLİK: sadece DEMO
    if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        log(f"⛔ GÜVENLİK: hesap DEMO değil (trade_mode={acc.trade_mode}). "
            f"Bot DURDU — gerçek hesapta otomatik işlem yapmaz.")
        mt5.shutdown(); return None
    log(f"✅ Bağlandı: {acc.login} ({acc.server}) DEMO · "
        f"bakiye={acc.balance:.2f} {acc.currency}")
    return mt5


def resolve_symbol(mt5, yf_ticker, smap):
    """yf ticker'ı GCM MT5 sembol adına çöz. Önce override, sonra otomatik eşleştir."""
    if yf_ticker in smap:
        return smap[yf_ticker]
    base = yf_ticker.split(".")[0].upper()   # ASML.AS → ASML
    # MT5'te bu tabanı içeren sembolü ara
    try:
        for s in mt5.symbols_get():
            nm = s.name.upper()
            if nm == base or nm.startswith(base + ".") or nm.startswith(base + "_") \
               or nm == base + ".US" or nm == base + "US":
                return s.name
    except Exception:
        pass
    return None


def get_bars(mt5, symbol):
    tf = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
          "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1
          }.get(TIMEFRAME, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, N_BARS)
    if rates is None or len(rates) < 1500:
        return None
    df = pd.DataFrame(rates)
    df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})
    return df[["open", "high", "low", "close"]]


# ──────────────────────────────────────────────────────────────────
#  SİNYAL — bizim test edilmiş kodumuz (signals_full)
# ──────────────────────────────────────────────────────────────────
def compute_signal(df, params):
    p = dict(params)
    p.setdefault("rott_x1", 30); p.setdefault("rott_x2", 1000); p.setdefault("rott_percent", 7.0)
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **p)
    last = s.iloc[-2]   # son KAPANMIŞ bar (oluşan mum değil)
    if last["cond_buy_long"]:   return "LONG_AC", float(last["tott_dn"])
    if last["cond_buy_short"]:  return "SHORT_AC", float(last["tott_up"])
    if last["cond_exit_long"] or last["cond_exit_short"]:  return "EXIT", None
    if last["major_up"] and last["zone_up"]:   return "LONG_TUT", float(last["tott_dn"])
    if last["major_dn"] and last["zone_dn"]:   return "SHORT_TUT", float(last["tott_up"])
    return "FLAT", None


# ──────────────────────────────────────────────────────────────────
#  EMİR YÖNETİMİ
# ──────────────────────────────────────────────────────────────────
def my_position(mt5, symbol):
    try:
        ps = mt5.positions_get(symbol=symbol)
        for p in (ps or []):
            if p.magic == MAGIC:
                return p
    except Exception:
        pass
    return None


def open_order(mt5, symbol, side, sl):
    if DRY_RUN:
        log(f"  [DRY] AÇ {side} {symbol} lot={LOT} sl={sl}")
        return
    info = mt5.symbol_info_tick(symbol)
    if not info:
        log(f"  ✗ {symbol} fiyat yok, atla"); return
    if side == "LONG":
        otype, price = mt5.ORDER_TYPE_BUY, info.ask
    else:
        otype, price = mt5.ORDER_TYPE_SELL, info.bid
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(LOT),
        "type": otype, "price": price, "sl": float(sl) if sl else 0.0,
        "deviation": DEVIATION, "magic": MAGIC, "comment": "ott_bot",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    r = mt5.order_send(req)
    ok = r and r.retcode == mt5.TRADE_RETCODE_DONE
    log(f"  {'✅' if ok else '✗'} AÇ {side} {symbol} @ {price} sl={sl} "
        f"ret={getattr(r,'retcode',None)} {getattr(r,'comment','')}")


def close_position(mt5, pos):
    if DRY_RUN:
        log(f"  [DRY] KAPAT {pos.symbol} ({'LONG' if pos.type==0 else 'SHORT'})")
        return
    info = mt5.symbol_info_tick(pos.symbol)
    otype = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    price = info.bid if pos.type == 0 else info.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": pos.symbol, "volume": pos.volume,
        "type": otype, "position": pos.ticket, "price": price,
        "deviation": DEVIATION, "magic": MAGIC, "comment": "ott_bot_close",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    r = mt5.order_send(req)
    ok = r and r.retcode == mt5.TRADE_RETCODE_DONE
    log(f"  {'✅' if ok else '✗'} KAPAT {pos.symbol} ret={getattr(r,'retcode',None)}")


def update_sl(mt5, pos, sl):
    if not sl or sl <= 0:
        return
    # Trailing: SL'yi sadece lehe yönde güncelle
    if pos.type == 0 and sl <= pos.sl:   # LONG: sadece yukarı
        return
    if pos.type == 1 and pos.sl and sl >= pos.sl:  # SHORT: sadece aşağı
        return
    if DRY_RUN:
        log(f"  [DRY] SL güncelle {pos.symbol} → {sl:.4f}")
        return
    req = {"action": mt5.TRADE_ACTION_SLTP, "symbol": pos.symbol,
           "position": pos.ticket, "sl": float(sl), "tp": 0.0}
    mt5.order_send(req)


# ──────────────────────────────────────────────────────────────────
#  ANA DÖNGÜ
# ──────────────────────────────────────────────────────────────────
def cycle(mt5, universe, smap):
    open_count = len([p for p in (mt5.positions_get() or []) if p.magic == MAGIC])
    for yf_sym, params in universe.items():
        gcm_sym = resolve_symbol(mt5, yf_sym, smap)
        if not gcm_sym:
            continue
        if not mt5.symbol_select(gcm_sym, True):
            continue
        df = get_bars(mt5, gcm_sym)
        if df is None:
            continue
        try:
            sig, sl = compute_signal(df, params)
        except Exception as e:
            log(f"  {gcm_sym} sinyal hatası: {e}"); continue

        pos = my_position(mt5, gcm_sym)
        # Açık pozisyon yönetimi
        if pos:
            pside = "LONG" if pos.type == 0 else "SHORT"
            if sig == "EXIT" or sig == "FLAT" \
               or (pside == "LONG" and "SHORT" in sig) \
               or (pside == "SHORT" and "LONG" in sig):
                log(f"{gcm_sym}: {pside} → çıkış sinyali ({sig}), kapatılıyor")
                close_position(mt5, pos)
            else:
                update_sl(mt5, pos, sl)   # trailing
        else:
            # Yeni pozisyon — sadece TAZE AÇ + pozisyon limiti
            if sig in ("LONG_AC", "SHORT_AC") and open_count < MAX_POSITIONS:
                side = "LONG" if sig == "LONG_AC" else "SHORT"
                log(f"{gcm_sym}: TAZE {side} AÇ sinyali → açılıyor (sl={sl})")
                open_order(mt5, gcm_sym, side, sl)
                open_count += 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import warnings; warnings.filterwarnings("ignore")
    log("=" * 60)
    log(f"OTT GCM Bot başlıyor — DRY_RUN={DRY_RUN}, lot={LOT}, TF={TIMEFRAME}")
    universe, grid = load_universe()
    smap = load_symbol_map()
    log(f"Evren: {len(universe)} GCM hissesi (Grid İYİ+). Sembol override: {len(smap)}")
    if not universe:
        log("Evren boş — param dosyaları?"); return

    mt5 = mt5_connect()
    if mt5 is None:
        return
    try:
        while True:
            t0 = time.time()
            log(f"── Tarama başladı ({len(universe)} sembol) ──")
            try:
                cycle(mt5, universe, smap)
            except Exception as e:
                log(f"Döngü hatası: {e}")
            log(f"── Tarama bitti ({time.time()-t0:.0f}sn). {POLL_SECONDS}sn uyku ──")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        log("Kullanıcı durdurdu (Ctrl+C).")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
