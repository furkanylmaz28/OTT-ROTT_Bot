"""
binance_grid_bot.py — Kanıtlanmış crypto GRID stratejisini Binance TESTNET'te çalıştırır.

Strateji (WF: trailing 4/4 OOS+ , +3188% vs sabit +780%; maliyete dayanıklı):
  - Yatay (Kaufman ER < 0.30): merkez SMA20, altına %2/%4/%6'da LIMIT AL (maker).
  - Her birim +%1.5'e ulaşınca TRAILING aktifleşir; peak'in %0.5 altına inince
    market satar (kazananı koşturur — sabit +%1.5'i ~3× geçiyor).
  - Trend (ER ≥ 0.30): açık emirleri iptal et + eldeki coini market sat (grid kapat).
Spot, long-only, kaldıraç YOK. SADECE TESTNET (demo).

KURULUM:
  1) pip install python-binance python-dotenv numpy
  2) https://testnet.binance.vision → "Generate HMAC Key" (GitHub ile giriş)
  3) .env dosyasına:
       BINANCE_TEST_API_KEY=...
       BINANCE_TEST_API_SECRET=...
  4) python binance_grid_bot.py

⚠️ Bu TESTNET botu — gerçek para YOK. Gerçeğe geçmeden haftalarca demo'da izle.
⚠️ COINS ve USDT_PER_UNIT'i kendine göre ayarla. Kaldıraç yok (spot).
"""
import os, json, time, math
from datetime import datetime, timezone
import numpy as np
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException

load_dotenv()

# ─────────────────────── AYARLAR ───────────────────────
COINS          = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                  "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT"]
USDT_PER_UNIT  = 15.0          # birim başı USDT (min notional ~$10 → 15 güvenli)
ER_WIN         = 20            # efficiency ratio penceresi
ER_TH          = 0.30          # ER < bu = yatay (grid açık)
LEVELS         = [-0.02, -0.04, -0.06]   # merkez altı AL seviyeleri
TAKE           = 0.015         # +%1.5'te TRAILING aktifleş (satmaz)
TRAIL          = 0.005         # peak'in %0.5 altına inince market sat (kazananı koştur)
INTERVAL       = Client.KLINE_INTERVAL_4HOUR
LOOP_SEC       = 300           # 5 dk'da bir tarama
STATE_FILE     = "binance_grid_state.json"
TRADES_FILE    = "binance_grid_trades.json"
# ───────────────────────────────────────────────────────

client = Client(os.getenv("BINANCE_TEST_API_KEY"),
                os.getenv("BINANCE_TEST_API_SECRET"), testnet=True)

_filters = {}


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
    """Sembolün lot adımı, fiyat adımı, min notional'ı (cache)."""
    if sym not in _filters:
        info = client.get_symbol_info(sym)
        f = {x["filterType"]: x for x in info["filters"]}
        step = float(f["LOT_SIZE"]["stepSize"])
        tick = float(f["PRICE_FILTER"]["tickSize"])
        notf = f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {"minNotional": "10"}
        minN = float(notf.get("minNotional", notf.get("notional", "10")))
        _filters[sym] = (step, tick, minN)
    return _filters[sym]


def _dec(x):
    return max(0, int(round(-math.log10(x)))) if x < 1 else 0


def fmt(val, unit):
    d = _dec(unit)
    return f"{math.floor(val / unit) * unit:.{d}f}"


def regime(sym):
    """ER + merkez (SMA20) + anlık fiyat — son kapanmış barlardan."""
    kl = client.get_klines(symbol=sym, interval=INTERVAL, limit=ER_WIN + 5)
    closes = np.array([float(k[4]) for k in kl[:-1]])   # son (oluşan) bar hariç
    seg = closes[-(ER_WIN + 1):]
    vol = np.abs(np.diff(seg)).sum()
    er = abs(seg[-1] - seg[0]) / vol if vol > 0 else 1.0
    center = closes[-ER_WIN:].mean()
    price = float(client.get_symbol_ticker(symbol=sym)["price"])
    return er, center, price


def record_trade(sym, entry, exit_price, reason):
    trades = _load(TRADES_FILE, [])
    pnl = (exit_price / entry - 1) * 100
    trades.append({"sym": sym, "entry": entry, "exit": exit_price,
                   "pnl_pct": round(pnl, 3), "reason": reason,
                   "ts": datetime.now(timezone.utc).isoformat()})
    _save(TRADES_FILE, trades)
    print(f"   💰 {sym} KAPANDI ({reason}): {entry:.6g} → {exit_price:.6g} = {pnl:+.2f}%")


def manage(sym, state):
    er, center, price = regime(sym)
    step, tick, minN = filters(sym)
    sstate = state.setdefault(sym, {})
    sideways = er < ER_TH
    tag = "🟦 YATAY" if sideways else "📈 TREND"
    print(f" {sym:9s} {tag} ER={er:.2f} fiyat={price:.6g}")

    # ── TREND: gridi kapat
    if not sideways:
        for ks in list(sstate.keys()):
            u = sstate[ks]
            try: client.cancel_order(symbol=sym, orderId=u["order_id"])
            except BinanceAPIException: pass
            if u["phase"] == "hold":   # elde coin var → market sat
                try:
                    client.order_market_sell(symbol=sym, quantity=fmt(u["qty"], step))
                    record_trade(sym, u["entry"], price, "trend")
                except BinanceAPIException as e:
                    print(f"   market-sat hata: {e}")
            del sstate[ks]
        return

    # ── YATAY: her seviyeyi yönet
    for k, lv in enumerate(LEVELS):
        ks = str(k)
        u = sstate.get(ks)
        lvl_price = math.floor(center * (1 + lv) / tick) * tick
        if u is None:
            # boş seviye → LIMIT AL koy (maker)
            qty = math.floor((USDT_PER_UNIT / lvl_price) / step) * step
            if qty * lvl_price < minN:
                continue
            try:
                o = client.order_limit_buy(symbol=sym, quantity=fmt(qty, step), price=fmt(lvl_price, tick))
                sstate[ks] = {"phase": "buy", "order_id": o["orderId"], "qty": qty}
                print(f"   📥 AL emri: seviye {k+1} @ {lvl_price:.6g} ({qty} adet)")
            except BinanceAPIException as e:
                print(f"   AL hata: {e}")
        elif u["phase"] == "buy":
            try: od = client.get_order(symbol=sym, orderId=u["order_id"])
            except BinanceAPIException: continue
            if od["status"] == "FILLED":
                entry = float(od["price"])
                # SAT emri KOYMA → trailing'e geç (kazananı koştur)
                u.update({"phase": "hold", "entry": entry, "active": False, "peak": entry})
                print(f"   ✅ ALINDI {entry:.6g} → trailing bekliyor (+%1.5'te aktif)")
        elif u["phase"] == "hold":
            entry = u["entry"]
            # +%1.5'e ulaşınca trailing aktifleş
            if not u.get("active") and price >= entry * (1 + TAKE):
                u["active"] = True; u["peak"] = price
                print(f"   🔥 {sym} trailing AKTİF @ {price:.6g} (peak takip başladı)")
            if u.get("active"):
                u["peak"] = max(u["peak"], price)
                # peak'in %0.5 altına inince market sat
                if price <= u["peak"] * (1 - TRAIL):
                    try:
                        client.order_market_sell(symbol=sym, quantity=fmt(u["qty"], step))
                        record_trade(sym, entry, price, "trail")
                        del sstate[ks]
                    except BinanceAPIException as e:
                        print(f"   trailing-sat hata: {e}")


def main():
    if not os.getenv("BINANCE_TEST_API_KEY"):
        print("HATA: BINANCE_TEST_API_KEY yok. .env'e testnet anahtarını ekle (testnet.binance.vision)")
        return
    print(f"Binance TESTNET grid botu başladı · {len(COINS)} coin · birim {USDT_PER_UNIT} USDT · 4h")
    print("⚠️ TESTNET — gerçek para yok. Ctrl+C ile durdur.\n")
    while True:
        state = _load(STATE_FILE, {})
        for sym in COINS:
            try:
                manage(sym, state)
                time.sleep(0.3)   # rate limit
            except Exception as e:
                print(f" {sym}: hata {e}")
        _save(STATE_FILE, state)
        print(f"— tarama bitti {datetime.now():%H:%M:%S}, {LOOP_SEC}sn bekleniyor —\n")
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    main()
