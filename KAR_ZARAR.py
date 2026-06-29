"""KAR_ZARAR.py — Binance futures testnet bot durumu: cüzdan, açık pozisyon, kapanmış işlemler."""
import os, sys, json, time
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from dotenv import load_dotenv; load_dotenv(".env", override=True)
from binance.client import Client

BASLANGIC = 4750.0
c = Client(os.getenv("BINANCE_TEST_API_KEY"), os.getenv("BINANCE_TEST_API_SECRET"), testnet=True)
try:  # PC saati kaymışsa düzelt (-1021)
    c.timestamp_offset = c.futures_time()["serverTime"] - int(time.time() * 1000)
except Exception: pass

# 1) Cüzdan
wallet = next((float(b["balance"]) for b in c.futures_account_balance() if b["asset"] == "USDT"), 0)

# 2) Açık pozisyonlar + yüzen PnL
pos = [p for p in c.futures_position_information() if float(p["positionAmt"]) != 0]
floating = sum(float(p["unRealizedProfit"]) for p in pos)

# 3) Kapanmış işlemler (bot kaydı)
try: trades = json.load(open("binance_fut_trades.json", encoding="utf-8"))
except Exception: trades = []
realized = sum(t["pnl_pct"] for t in trades)
wins = [t for t in trades if t["pnl_pct"] > 0]

print("=" * 52)
print("  💰 BINANCE FUTURES TESTNET — KÂR/ZARAR DURUMU")
print("=" * 52)
print(f"  Cüzdan (equity)   : {wallet:,.2f} USDT")
print(f"  Başlangıç         : {BASLANGIC:,.2f} USDT")
toplam = wallet + floating - BASLANGIC
print(f"  TOPLAM K/Z        : {toplam:+,.2f} USDT  (%{toplam/BASLANGIC*100:+.2f})")
print("-" * 52)
print(f"  Açık pozisyon     : {len(pos)} adet · yüzen {floating:+.2f} USDT")
for p in pos:
    amt = float(p["positionAmt"])
    print(f"     {p['symbol']:9s} {amt:>8.2f} adet  giriş {float(p['entryPrice']):.5g}  yüzen {float(p['unRealizedProfit']):+.2f}")
print("-" * 52)
print(f"  Kapanmış işlem    : {len(trades)} · kazanan %{(100*len(wins)/len(trades) if trades else 0):.0f}")
if trades:
    print(f"     son 5 işlem:")
    for t in trades[-5:]:
        print(f"     {t['sym']:9s} {t['pnl_pct']:+.2f}%  ({t.get('reason','')})")
print("=" * 52)
