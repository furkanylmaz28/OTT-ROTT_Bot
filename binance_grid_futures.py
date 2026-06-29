"""
binance_grid_futures.py — Crypto GRID stratejisi · Binance FUTURES TESTNET · 2× kaldıraç.

⚠️ FUTURES = LİKİDASYON VAR. Bu DEMO (testnet, sahte para) — gerçek cüzdan etkilenmez.
   2× kaldıraçta ~-50% korelasyonlu kraş pozisyonu TASFİYE eder. Demo'da bunu görmek dersin.

Strateji (WF doğrulanmış, trailing):
  - Yatay (Kaufman ER < 0.30): merkez SMA20, altına %2/%4/%6'da LIMIT AL (maker).
  - Birim +%1.5'e ulaşınca TRAILING aktif; peak'in %0.5 altına inince market kapat.
  - Trend (ER ≥ 0.30): açık emirleri iptal + pozisyonu market kapat (reduceOnly).
  - İzole marj, LONG-only, 2× kaldıraç. Bileşik: birim teminatı cüzdan büyüdükçe artar.

KURULUM:
  1) Anahtarlar Binance FUTURES testnet'ten: https://testnet.binancefuture.com
     .env →  BINANCE_TEST_API_KEY=...   BINANCE_TEST_API_SECRET=...
  2) python binance_grid_futures.py
"""
import os, sys, json, time, math
try: sys.stdout.reconfigure(encoding="utf-8")   # Windows cp1254 emoji hatası
except Exception: pass
from datetime import datetime, timezone
import numpy as np
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
import risk   # pozisyon/zarar yönetimi (sinyal değil)

load_dotenv()

# ─────────────────────── AYARLAR ───────────────────────
COINS          = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                  "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT"]
LEVERAGE       = 2             # ⚠️ kaldıraç (demo). 1 = likidasyon yok; 2 = -50%'de tasfiye
MARGIN_PCT     = 0.02          # birim teminatı = cüzdan × bu (BİLEŞİK: cüzdan büyüdükçe artar)
MIN_MARGIN     = 10.0          # birim başı en az teminat USDT
ER_WIN         = 20
ER_TH          = 0.30          # ER < bu = yatay (grid açık)
LEVELS         = [-0.02, -0.04, -0.06]
TAKE           = 0.015         # +%1.5'te trailing aktif
TRAIL          = 0.005         # peak'in %0.5 altına inince kapat
INTERVAL       = "4h"
LOOP_SEC       = 300           # 5 dk'da bir tarama
STATE_FILE     = "binance_fut_state.json"
TRADES_FILE    = "binance_fut_trades.json"
# ───────────────────────────────────────────────────────

client = Client(os.getenv("BINANCE_TEST_API_KEY"),
                os.getenv("BINANCE_TEST_API_SECRET"), testnet=True)


def sync_time():
    """PC saati Binance'ten kayarsa (-1021) imzalı istekler reddedilir — düzelt."""
    try:
        srv = client.futures_time()["serverTime"]
        client.timestamp_offset = srv - int(time.time() * 1000)
    except Exception:
        pass

_filters = {}
_setup_done = set()


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default


def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception: pass


def filters(sym):
    """Lot adımı, fiyat adımı, min notional (cache)."""
    if not _filters:
        info = client.futures_exchange_info()
        for s in info["symbols"]:
            f = {x["filterType"]: x for x in s["filters"]}
            step = float(f["LOT_SIZE"]["stepSize"])
            tick = float(f["PRICE_FILTER"]["tickSize"])
            notf = f.get("MIN_NOTIONAL") or {"notional": "5"}
            minN = float(notf.get("notional", "5"))
            _filters[s["symbol"]] = (step, tick, minN)
    return _filters[sym]


def setup(sym):
    """Sembol için kaldıraç + izole marj ayarla (bir kez)."""
    if sym in _setup_done:
        return
    try: client.futures_change_margin_type(symbol=sym, marginType="ISOLATED")
    except BinanceAPIException as e:
        if e.code != -4046: print(f"   {sym} marj-tipi: {e.message}")   # -4046 = zaten izole
    try: client.futures_change_leverage(symbol=sym, leverage=LEVERAGE)
    except BinanceAPIException as e: print(f"   {sym} kaldıraç: {e.message}")
    _setup_done.add(sym)


def _dec(x): return max(0, int(round(-math.log10(x)))) if x < 1 else 0
def fmt(val, unit): d = _dec(unit); return f"{math.floor(val / unit) * unit:.{d}f}"


def wallet_usdt():
    for b in client.futures_account_balance():
        if b["asset"] == "USDT":
            return float(b["balance"])
    return 0.0


def regime(sym):
    """ER + merkez (SMA20) + anlık fiyat — son kapanmış futures barlarından."""
    kl = client.futures_klines(symbol=sym, interval=INTERVAL, limit=ER_WIN + 5)
    closes = np.array([float(k[4]) for k in kl[:-1]])
    seg = closes[-(ER_WIN + 1):]
    vol = np.abs(np.diff(seg)).sum()
    er = abs(seg[-1] - seg[0]) / vol if vol > 0 else 1.0
    center = closes[-ER_WIN:].mean()
    price = float(client.futures_symbol_ticker(symbol=sym)["price"])
    return er, center, price


def record_trade(sym, entry, exit_price, reason, qty=0.0):
    trades = _load(TRADES_FILE, [])
    pnl = (exit_price / entry - 1) * 100 * LEVERAGE       # marja göre kaldıraçlı getiri
    pnl_usdt = qty * (exit_price - entry)                 # gerçek USDT K/Z (zarar freni için)
    trades.append({"sym": sym, "entry": entry, "exit": exit_price, "lev": LEVERAGE,
                   "pnl_pct": round(pnl, 3), "pnl_usdt": round(pnl_usdt, 4), "reason": reason,
                   "ts": datetime.now(timezone.utc).isoformat()})
    _save(TRADES_FILE, trades)
    print(f"   💰 {sym} KAPANDI ({reason}): {entry:.6g}→{exit_price:.6g} = {pnl:+.2f}% ({pnl_usdt:+.2f} USDT)")


def realized_pnl_pct(wallet):
    """Bugünkü ve bu haftaki gerçekleşen K/Z — cüzdana oranla %. Zarar freni için."""
    if wallet <= 0:
        return 0.0, 0.0
    trades = _load(TRADES_FILE, [])
    now = datetime.now(timezone.utc)
    bugun = now.date().isoformat(); hafta = now.isocalendar()[:2]
    today_usdt = week_usdt = 0.0
    for t in trades:
        ts = t.get("ts", ""); u = t.get("pnl_usdt", 0)
        try: d = datetime.fromisoformat(ts)
        except Exception: continue
        if ts[:10] == bugun: today_usdt += u
        if d.isocalendar()[:2] == hafta: week_usdt += u
    return today_usdt / wallet * 100, week_usdt / wallet * 100


def total_open_notional():
    """Tüm açık futures pozisyonlarının toplam notional değeri (kaldıraç tavanı için)."""
    try:
        return sum(abs(float(p["positionAmt"])) * float(p["markPrice"])
                   for p in client.futures_position_information())
    except Exception:
        return 0.0


def manage(sym, state, unit_margin, risk_ctx):
    setup(sym)
    er, center, price = regime(sym)
    step, tick, minN = filters(sym)
    sstate = state.setdefault(sym, {})
    sideways = er < ER_TH
    print(f" {sym:9s} {'🟦 YATAY' if sideways else '📈 TREND'} ER={er:.2f} fiyat={price:.6g}")

    # ── TREND: gridi kapat (açık emir iptal + pozisyon market kapat)
    if not sideways:
        for ks in list(sstate.keys()):
            u = sstate[ks]
            if u["phase"] == "buy":
                try: client.futures_cancel_order(symbol=sym, orderId=u["order_id"])
                except BinanceAPIException: pass
            elif u["phase"] == "hold":
                try:
                    client.futures_create_order(symbol=sym, side="SELL", type="MARKET",
                                                quantity=fmt(u["qty"], step), reduceOnly=True)
                    record_trade(sym, u["entry"], price, "trend", u["qty"])
                except BinanceAPIException as e: print(f"   trend-kapat hata: {e.message}")
            del sstate[ks]
        return

    # ── YATAY: her seviyeyi yönet
    for k, lv in enumerate(LEVELS):
        ks = str(k); u = sstate.get(ks)
        lvl_price = math.floor(center * (1 + lv) / tick) * tick
        notional = unit_margin * LEVERAGE
        if u is None:
            # RİSK KAPISI: zarar freni açık ya da kaldıraç tavanı dolduysa YENİ açma (çıkışlar serbest)
            if risk_ctx["halted"]: continue
            if notional > risk_ctx["budget"]:
                print(f"   ⛔ {sym} sev{k+1}: kaldıraç tavanı (kalan bütçe {risk_ctx['budget']:.0f}$ < {notional:.0f}$)"); continue
            qty = math.floor((notional / lvl_price) / step) * step
            if qty * lvl_price < minN: continue
            try:
                o = client.futures_create_order(symbol=sym, side="BUY", type="LIMIT",
                        timeInForce="GTC", quantity=fmt(qty, step), price=fmt(lvl_price, tick))
                sstate[ks] = {"phase": "buy", "order_id": o["orderId"], "qty": qty}
                risk_ctx["budget"] -= notional   # kaldıraç bütçesinden düş
                print(f"   📥 AL emri: seviye {k+1} @ {lvl_price:.6g} ({qty} adet, {notional:.0f}$ notional)")
            except BinanceAPIException as e: print(f"   AL hata: {e.message}")
        elif u["phase"] == "buy":
            try: od = client.futures_get_order(symbol=sym, orderId=u["order_id"])
            except BinanceAPIException: continue
            if od["status"] == "FILLED":
                entry = float(od["avgPrice"]) or float(od["price"])
                u.update({"phase": "hold", "entry": entry, "active": False, "peak": entry})
                print(f"   ✅ ALINDI {entry:.6g} → trailing bekliyor (+%1.5'te aktif)")
        elif u["phase"] == "hold":
            entry = u["entry"]
            if not u.get("active") and price >= entry * (1 + TAKE):
                u["active"] = True; u["peak"] = price
                print(f"   🔥 {sym} trailing AKTİF @ {price:.6g}")
            if u.get("active"):
                u["peak"] = max(u["peak"], price)
                if price <= u["peak"] * (1 - TRAIL):
                    try:
                        client.futures_create_order(symbol=sym, side="SELL", type="MARKET",
                                                    quantity=fmt(u["qty"], step), reduceOnly=True)
                        record_trade(sym, entry, price, "trail", u["qty"])
                        del sstate[ks]
                    except BinanceAPIException as e: print(f"   trailing-kapat hata: {e.message}")


def main():
    if not os.getenv("BINANCE_TEST_API_KEY"):
        print("HATA: BINANCE_TEST_API_KEY yok (.env)"); return
    sync_time()   # PC saati kaymışsa düzelt (-1021 hatasını önler)
    try:
        w = wallet_usdt()
    except BinanceAPIException as e:
        print(f"❌ Bağlantı/anahtar hatası: {e.message}"); return
    print(f"Binance FUTURES TESTNET grid · {len(COINS)} coin · {LEVERAGE}× kaldıraç · cüzdan {w:,.0f} USDT")
    print(f"⚠️ DEMO — sahte para. {LEVERAGE}×'te ~-50% kraş = tasfiye. Ctrl+C ile durdur.\n")
    while True:
        sync_time()   # her turda saat senkronu (uzun çalışmada drift birikir)
        try: w = wallet_usdt()
        except Exception: pass
        unit_margin = max(MIN_MARGIN, w * MARGIN_PCT)   # BİLEŞİK: cüzdanla büyür
        # ── RİSK BAĞLAMI (risk.py): zarar freni + kaldıraç bütçesi
        today_pct, week_pct = realized_pnl_pct(w)
        halted, sebep = risk.loss_brake(today_pct, week_pct)
        budget = max(0.0, w * risk.MAX_LEVERAGE - total_open_notional())
        risk_ctx = {"halted": halted, "budget": budget}
        if halted: print(f"  {sebep}")
        print(f"  📐 risk: bugün {today_pct:+.2f}% · hafta {week_pct:+.2f}% · kaldıraç bütçesi {budget:,.0f}$")
        state = _load(STATE_FILE, {})
        for sym in COINS:
            try:
                manage(sym, state, unit_margin, risk_ctx); time.sleep(0.3)
            except Exception as e:
                print(f" {sym}: hata {e}")
        _save(STATE_FILE, state)
        print(f"— tarama bitti {datetime.now():%H:%M:%S} · birim teminat {unit_margin:.0f}$ · {LOOP_SEC}sn —\n")
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    main()
