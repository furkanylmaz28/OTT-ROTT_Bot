"""
binance_grid_real.py — Crypto GRID · Binance FUTURES GERÇEK HESAP · 2× kaldıraç.

🔴 GERÇEK PARA. Testnet DEĞİL. ~100$ doğrulama sermayesi için boyutlandırıldı.
   Amaç kâr değil: gerçek dolumların (slippage/komisyon) kağıt rakamlarını
   (204 işlem, PF 2.06) doğrulayıp doğrulamadığını ölçmek. 30-50 işlemde kıyas.

Strateji (WF 10/10 + 204 ileri-yönlü kağıt işlemiyle doğrulanmış, crypto paramları):
  - Yatay (Kaufman ER < 0.30): merkez SMA20, altına %2/%4/%6'da LIMIT AL (maker).
  - Birim +%1.5'e ulaşınca TRAILING aktif; peak'in %0.5 altına inince market kapat.
  - Trend (ER ≥ 0.30): açık emirleri iptal + pozisyonu market kapat (reduceOnly).
  - İzole marj, LONG-only, 2× kaldıraç.

100$ boyutlandırma: birim notional = max(6 USDT, cüzdan×%6) → tam grid (10 coin ×
3 seviye = 30 birim) 2× tavana (≈200$) sığar. BTC gibi min-miktarı büyük pariteler
otomatik atlanır (minNotional kontrolü). Cüzdan büyüdükçe birim bileşik büyür.

GÜVENLİK: risk.py zarar freni (gün -%2 / hafta -%5 → yeni giriş YOK) + 2× notional
tavanı + API anahtarında çekim izni YOK + IP kilidi.

KULLANIM:  python binance_grid_real.py          (başlangıçta onay ister)
           python binance_grid_real.py --auto   (onay atlanır — otomasyon için)
"""
import os, sys, json, time, math
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from datetime import datetime, timezone
import numpy as np
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
import risk

load_dotenv()

# ─────────────────────── AYARLAR ───────────────────────
COINS          = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                  "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT"]
LEVERAGE       = 2
UNIT_PCT       = 0.06          # birim notional = cüzdan × bu (bileşik)
UNIT_FLOOR     = 6.0           # ...ama en az 6 USDT (Binance min ~5 + tampon)
ER_WIN         = 20
ER_TH          = 0.30          # crypto grid'in DOĞRULANMIŞ paramı (BIST'inkiyle karıştırma)
LEVELS         = [-0.02, -0.04, -0.06]
TAKE           = 0.015
TRAIL          = 0.005
INTERVAL       = "4h"
LOOP_SEC       = 300
STATE_FILE     = "binance_real_state.json"
TRADES_FILE    = "binance_real_trades.json"
# ───────────────────────────────────────────────────────

client = Client(os.getenv("BINANCE_REAL_KEY"), os.getenv("BINANCE_REAL_SECRET"))


def tg(msg):
    try:
        from notifications import send_telegram
        send_telegram(msg)
    except Exception:
        pass


def sync_time():
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
    if sym in _setup_done:
        return
    try: client.futures_change_margin_type(symbol=sym, marginType="ISOLATED")
    except BinanceAPIException as e:
        if e.code != -4046: print(f"   {sym} marj-tipi: {e.message}")
    try: client.futures_change_leverage(symbol=sym, leverage=LEVERAGE)
    except BinanceAPIException as e: print(f"   {sym} kaldıraç: {e.message}")
    _setup_done.add(sym)


def _dec(x): return max(0, int(round(-math.log10(x)))) if x < 1 else 0
def fmt(val, unit): d = _dec(unit); return f"{math.floor(val / unit) * unit:.{d}f}"


def wallet_info():
    """(bakiye, yüzen K/Z, varlık=bakiye+yüzen) — anlık cüzdan görünümü."""
    bal = 0.0
    for b in client.futures_account_balance():
        if b["asset"] == "USDT":
            bal = float(b["balance"]); break
    unreal = 0.0
    try:
        unreal = sum(float(p["unRealizedProfit"]) for p in client.futures_position_information()
                     if float(p["positionAmt"]) != 0)
    except Exception:
        pass
    return bal, unreal, bal + unreal


def regime(sym):
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
    pnl = (exit_price / entry - 1) * 100 * LEVERAGE
    pnl_usdt = qty * (exit_price - entry)
    trades.append({"sym": sym, "entry": entry, "exit": exit_price, "lev": LEVERAGE,
                   "pnl_pct": round(pnl, 3), "pnl_usdt": round(pnl_usdt, 4), "reason": reason,
                   "ts": datetime.now(timezone.utc).isoformat()})
    _save(TRADES_FILE, trades)
    bal, unreal, eqty = wallet_info()
    print(f"   💰 {sym} KAPANDI ({reason}): {entry:.6g}→{exit_price:.6g} = {pnl:+.2f}% ({pnl_usdt:+.2f}$) · cüzdan {eqty:.2f}$")
    emoji = "✅" if pnl_usdt >= 0 else "🔻"
    tg(f"🔴 <b>GERÇEK</b> · {sym} kapandı ({reason}) {emoji}\n"
       f"{entry:.6g} → {exit_price:.6g} = <b>{pnl_usdt:+.2f}$</b> ({pnl:+.2f}%)\n"
       f"💼 Cüzdan: <b>{eqty:.2f}$</b> (bakiye {bal:.2f} + yüzen {unreal:+.2f})")


def realized_pnl_pct(wallet):
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
    try:
        return sum(abs(float(p["positionAmt"])) * float(p["markPrice"])
                   for p in client.futures_position_information())
    except Exception:
        return 0.0


def manage(sym, state, unit_notional, risk_ctx):
    setup(sym)
    er, center, price = regime(sym)
    step, tick, minN = filters(sym)
    sstate = state.setdefault(sym, {})
    sideways = er < ER_TH
    print(f" {sym:9s} {'🟦 YATAY' if sideways else '📈 TREND'} ER={er:.2f} fiyat={price:.6g}")

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

    for k, lv in enumerate(LEVELS):
        ks = str(k); u = sstate.get(ks)
        lvl_price = math.floor(center * (1 + lv) / tick) * tick
        if u is None:
            if risk_ctx["halted"]: continue
            if unit_notional > risk_ctx["budget"]:
                continue   # kaldıraç tavanı doldu — sessiz atla (log kalabalığı olmasın)
            qty = math.floor((unit_notional / lvl_price) / step) * step
            if qty <= 0 or qty * lvl_price < minN: continue   # BTC gibi min-miktarı büyük pariteler otomatik atlanır
            try:
                o = client.futures_create_order(symbol=sym, side="BUY", type="LIMIT",
                        timeInForce="GTC", quantity=fmt(qty, step), price=fmt(lvl_price, tick))
                sstate[ks] = {"phase": "buy", "order_id": o["orderId"], "qty": qty}
                risk_ctx["budget"] -= unit_notional
                print(f"   📥 AL emri: seviye {k+1} @ {lvl_price:.6g} ({qty} adet, {qty*lvl_price:.1f}$ notional)")
            except BinanceAPIException as e: print(f"   AL hata: {e.message}")
        elif u["phase"] == "buy":
            try: od = client.futures_get_order(symbol=sym, orderId=u["order_id"])
            except BinanceAPIException as e:
                if e.code == -2013: del sstate[ks]   # "Order does not exist" → temizle
                continue   # diğer hatalar (ağ vb.) geçici olabilir → state'e DOKUNMA (çift emir riski)
            if od["status"] == "FILLED":
                entry = float(od["avgPrice"]) or float(od["price"])
                u.update({"phase": "hold", "entry": entry, "active": False, "peak": entry})
                print(f"   ✅ ALINDI {entry:.6g} → trailing bekliyor (+%1.5'te aktif)")
                tg(f"🔴 <b>GERÇEK</b> · {sym} ALINDI @ {entry:.6g} (seviye {int(ks)+1})")
            elif od["status"] in ("CANCELED", "EXPIRED", "REJECTED"):
                # dışarıdan iptal (Cancel All vb.) → state'i temizle; sonraki taramada seviye yeniden değerlendirilir
                print(f"   🧹 seviye {int(ks)+1} emri dışarıdan iptal edilmiş → temizlendi")
                del sstate[ks]
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
    if not os.getenv("BINANCE_REAL_KEY") or not os.getenv("BINANCE_REAL_SECRET"):
        print("HATA: BINANCE_REAL_KEY / BINANCE_REAL_SECRET yok (.env)"); return
    sync_time()
    try:
        bal, unreal, eqty = wallet_info()
    except BinanceAPIException as e:
        print(f"❌ Bağlantı/anahtar hatası: {e.message}")
        print("   (IP kilidi? Binance'te kayıtlı IP ile şu anki IP aynı mı kontrol et.)")
        return
    unit = max(UNIT_FLOOR, eqty * UNIT_PCT)
    print("═" * 60)
    print(f"🔴 GERÇEK HESAP · Binance FUTURES grid · {len(COINS)} coin · {LEVERAGE}×")
    print(f"💼 Cüzdan: {eqty:.2f} USDT (bakiye {bal:.2f} + yüzen {unreal:+.2f})")
    print(f"📏 Birim: {unit:.1f}$ notional · zarar freni: gün -%{risk.MAX_DAILY_LOSS*100:.0f} / hafta -%{risk.MAX_WEEKLY_LOSS*100:.0f}")
    print("═" * 60)
    if "--auto" not in sys.argv:
        cevap = input("GERÇEK PARA ile başlasın mı? (EVET yaz): ").strip()
        if cevap != "EVET":
            print("İptal edildi."); return
    tg(f"🔴 <b>GERÇEK BOT BAŞLADI</b> · {len(COINS)} coin · {LEVERAGE}× · cüzdan <b>{eqty:.2f}$</b>")
    while True:
        sync_time()
        try:
            bal, unreal, eqty = wallet_info()
        except Exception:
            time.sleep(30); continue
        unit_notional = max(UNIT_FLOOR, eqty * UNIT_PCT)
        today_pct, week_pct = realized_pnl_pct(eqty)
        halted, sebep = risk.loss_brake(today_pct, week_pct)
        budget = max(0.0, eqty * risk.MAX_LEVERAGE - total_open_notional())
        risk_ctx = {"halted": halted, "budget": budget}
        if halted:
            print(f"  {sebep}")
        print(f"  💼 CÜZDAN: {eqty:.2f}$ (bakiye {bal:.2f} + yüzen {unreal:+.2f}) · "
              f"bugün {today_pct:+.2f}% · hafta {week_pct:+.2f}% · bütçe {budget:.0f}$")
        state = _load(STATE_FILE, {})
        for sym in COINS:
            try:
                manage(sym, state, unit_notional, risk_ctx); time.sleep(0.3)
            except Exception as e:
                print(f" {sym}: hata {e}")
        _save(STATE_FILE, state)
        print(f"— tarama bitti {datetime.now():%H:%M:%S} · birim {unit_notional:.1f}$ · {LOOP_SEC}sn —\n")
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    main()
