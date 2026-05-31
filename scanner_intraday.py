"""
GÜN-İÇİ TARAYICI — 5-dk veriyle (son 60 gün) anlık sinyal durumu.

Çıktı:
  - Her sembolün ŞU ANKİ pozisyonu (LONG/SHORT/FLAT)
  - Yukarı tetik fiyatı + uzaklık (% olarak)
  - Aşağı tetik fiyatı + uzaklık
  - Trend yönü
  - Son sinyal zamanı

Hız: yaklaşık 1-2 saniye/sembol. 20 sembol ≈ 30 saniye.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import time
import pandas as pd
import yfinance as yf

import signals_full as sig_full


# Tarayacağımız sembollerin alt-listesi (günlük scanner'da iyi çalışanlar)
INTRADAY_SYMBOLS = [
    "GC=F",        # Gold futures (en güvenilir — sistem GOLD'da kanıtlanmış)
    "SI=F",        # Silver futures
    "QQQ",         # Nasdaq 100 ETF
    "SPY",         # S&P 500 ETF
    "NVDA", "AMD", "GOOGL", "MSFT", "AAPL", "TSLA", "META", "AMZN",
    "BTC-USD", "ETH-USD",
    "EURUSD=X", "GBPUSD=X",  # forex (kanıtlanmamış ama izlemek için)
]

PARAMS = dict(
    trend_length=20, trend_percent=8.0, minor_percent=4.0,
    tott_percent=1.0, tott_coeff=0.0004,
    sott_period_k=300, sott_smooth_k=200, sott_percent=0.2,
    gate_length=10, gate_percent=0.4, gate_shift=0,
    rott_x1=30, rott_x2=1000, rott_percent=7.0,
)


def fetch_5m(symbol: str) -> pd.DataFrame:
    df = yf.download(symbol, period="60d", interval="5m",
                     auto_adjust=False, progress=False, threads=False)
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.lower)[["open","high","low","close"]].dropna()
    return df


def analyze(symbol: str):
    df = fetch_5m(symbol)
    if df.empty or len(df) < 2000:
        return None
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **PARAMS)
    last = s.iloc[-1]
    cur_price = float(df["close"].iloc[-1])
    last_time = df.index[-1]

    # Pozisyon yönü — son barda yeni-açma şartı var mı yoksa zaten major_up mu?
    if last["cond_buy_long"]: pos = "AL SİNYAL"
    elif last["cond_buy_short"]: pos = "AÇIĞA SAT SİNYAL"
    elif last["cond_exit_long"]: pos = "SAT (LONG ÇIK)"
    elif last["cond_exit_short"]: pos = "POZ KAPAT (SHORT ÇIK)"
    elif last["major_up"] and last["zone_up"]: pos = "LONG açık (tut)"
    elif last["major_dn"] and last["zone_dn"]: pos = "SHORT açık (tut)"
    elif last["major_up"]: pos = "Yukarı trend (bekliyor)"
    elif last["major_dn"]: pos = "Aşağı trend (bekliyor)"
    else: pos = "Belirsiz"

    trend_ott = float(last["trend_ott"]) if not pd.isna(last["trend_ott"]) else None
    tott_up = float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None
    tott_dn = float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None

    return {
        "symbol": symbol, "time": last_time,
        "price": cur_price,
        "trend_ott": trend_ott, "tott_up": tott_up, "tott_dn": tott_dn,
        "position": pos,
        "up_dist": (tott_up/cur_price - 1)*100 if tott_up else None,
        "dn_dist": (tott_dn/cur_price - 1)*100 if tott_dn else None,
        "trend_dist": (trend_ott/cur_price - 1)*100 if trend_ott else None,
    }


def main():
    print(f"  Gün-içi tarama başlıyor — {len(INTRADAY_SYMBOLS)} sembol\n")
    t0 = time.time()
    rows = []
    for sym in INTRADAY_SYMBOLS:
        print(f"  {sym:12s} ...", end=" ", flush=True)
        try:
            r = analyze(sym)
            if r is None: print("veri yok"); continue
            print(f"{r['position']}")
            rows.append(r)
        except Exception as e:
            print(f"hata: {e}")
    print(f"\n  Süre: {time.time()-t0:.1f}s\n")

    if not rows:
        print("Sonuç yok"); return

    print("═"*120)
    print(f"  GÜN-İÇİ (5-dk) ANLIK DURUM   (son veri: {rows[0]['time']})")
    print("═"*120)
    print(f"  {'Sembol':<12} {'Fiyat':>12} {'Pozisyon':<22} "
          f"{'Trend OTT':>12} {'(trend %)':>10} "
          f"{'Tetik ↑':>10} {'(%)':>7} {'Tetik ↓':>10} {'(%)':>7}")
    print("  " + "─"*116)
    # Önce pozisyonel olarak sırala (sinyal/long/short/bekleyenler)
    order = {"AL SİNYAL":0, "AÇIĞA SAT SİNYAL":1, "SAT (LONG ÇIK)":2,
             "POZ KAPAT (SHORT ÇIK)":3,
             "LONG açık (tut)":4, "SHORT açık (tut)":5,
             "Yukarı trend (bekliyor)":6, "Aşağı trend (bekliyor)":7, "Belirsiz":8}
    rows.sort(key=lambda x: order.get(x["position"], 9))
    for r in rows:
        td = f"{r['trend_dist']:+6.2f}%" if r['trend_dist'] is not None else "  n/a"
        ud = f"{r['up_dist']:+6.2f}%" if r['up_dist'] is not None else "  n/a"
        dd = f"{r['dn_dist']:+6.2f}%" if r['dn_dist'] is not None else "  n/a"
        to = f"{r['trend_ott']:>12.4f}" if r['trend_ott'] is not None else "         n/a"
        tu = f"{r['tott_up']:>10.4f}" if r['tott_up'] is not None else "       n/a"
        td2 = f"{r['tott_dn']:>10.4f}" if r['tott_dn'] is not None else "       n/a"
        print(f"  {r['symbol']:<12} {r['price']:>12.4f} {r['position']:<22} "
              f"{to} {td:>10} {tu} {ud:>7} {td2} {dd:>7}")

    # CSV
    pd.DataFrame(rows).to_csv("scan_intraday.csv", index=False)
    print(f"\n  CSV: scan_intraday.csv")


if __name__ == "__main__":
    main()
