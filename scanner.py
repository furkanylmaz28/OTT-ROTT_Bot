"""
OTT SİNYAL TARAYICI — Birden fazla sembolü tarayıp:
  1) Sistemin son 6 ayda o sembolde kâr ediyor mu kontrol et (filtre)
  2) Filtreden geçen sembolün ŞU ANKİ sinyal durumunu çıkar
  3) Tetik fiyat seviyelerini göster (hangi fiyatta yön değişir)

Veri kaynağı: yfinance (BIST .IS, US, forex =X, crypto -USD, futures =F)

Çıktı: Hem konsol tablosu hem CSV (scan_result.csv).
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import time
import pandas as pd
import numpy as np
import yfinance as yf

import signals_full as sig_full
from backtest import run_backtest


# ── Sembol evreni — kategori bazlı
SYMBOLS = {
    "BIST":     ["AKBNK.IS","ASELS.IS","EREGL.IS","GARAN.IS","ISCTR.IS","KCHOL.IS",
                 "KOZAL.IS","SAHOL.IS","SISE.IS","THYAO.IS","TUPRS.IS","YKBNK.IS",
                 "BIMAS.IS","FROTO.IS","TCELL.IS","TOASO.IS","PETKM.IS","ARCLK.IS"],
    "FOREX":    ["EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X","USDCAD=X",
                 "EURGBP=X","NZDUSD=X"],
    "COMMODITY":["GC=F","SI=F","CL=F","NG=F","HG=F"],  # gold silver oil ngas copper
    "CRYPTO":   ["BTC-USD","ETH-USD","SOL-USD","BNB-USD"],
    "US":       ["SPY","QQQ","NVDA","AAPL","TSLA","MSFT","GOOGL","AMZN","META","AMD"],
    "INDEX":    ["^GSPC","^IXIC","^DJI","^N225","^GDAXI","^FTSE","XU100.IS"],
}

# Sistem parametreleri — günlük bar tarama için adapte (intraday tuned değerleri)
# GOLD M15 optimum: M15'ten günlüğe genelleştirme yaklaşımı
PARAMS = dict(
    trend_length=20, trend_percent=8.0, minor_percent=4.0,
    tott_percent=1.0, tott_coeff=0.0004,
    sott_period_k=50, sott_smooth_k=20, sott_percent=0.3,   # günlük için kısaltıldı
    gate_length=20, gate_percent=0.5, gate_shift=0,
    rott_x1=30, rott_x2=200, rott_percent=7.0,              # rott_x2 da kısaltıldı
)


def fetch(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=False, progress=False, threads=False)
    except Exception:
        return pd.DataFrame()
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.lower)
    keep = [c for c in ["open","high","low","close"] if c in df.columns]
    df = df[keep].dropna()
    return df


def analyze(symbol: str, category: str, params: dict):
    df = fetch(symbol, period="2y", interval="1d")
    if df.empty or len(df) < 250:
        return None

    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    st = res.stats

    # Şu anki durum — son bar
    cur_pos = int(res.position.iloc[-1])
    pos_label = "LONG" if cur_pos==1 else ("SHORT" if cur_pos==-1 else "FLAT")

    # En son sinyal bar'ı
    last_buy_l = s["cond_buy_long"].astype(bool)
    last_buy_s = s["cond_buy_short"].astype(bool)
    last_exit_l = s["cond_exit_long"].astype(bool)
    last_exit_s = s["cond_exit_short"].astype(bool)
    last_sig = None
    for t in reversed(df.index[-30:]):
        if last_buy_l.loc[t]:  last_sig = (t, "AL");          break
        if last_buy_s.loc[t]:  last_sig = (t, "AÇIĞA SAT");   break
        if last_exit_l.loc[t]: last_sig = (t, "SAT");         break
        if last_exit_s.loc[t]: last_sig = (t, "POZ KAPAT");   break
    last_sig_str = f"{last_sig[1]} ({last_sig[0].date()})" if last_sig else "yok (30 günde)"

    # Tetik seviyeleri — son bar'ın değerleri
    last = s.iloc[-1]
    cur_price = float(df["close"].iloc[-1])
    trend_ott = float(last["trend_ott"]) if not pd.isna(last["trend_ott"]) else None
    tott_up = float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None
    tott_dn = float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None
    mavg = float(last["mavg"]) if not pd.isna(last["mavg"]) else None

    return {
        "category": category,
        "symbol": symbol,
        "bars": len(df),
        "price": cur_price,
        "mavg": mavg,
        "trend_ott": trend_ott,
        "tott_up": tott_up,
        "tott_dn": tott_dn,
        "position": pos_label,
        "last_signal": last_sig_str,
        "backtest_ret_2y": st["total_return"],
        "backtest_pf": st["profit_factor"],
        "backtest_dd": st["max_drawdown"],
        "backtest_n": st["n_trades"],
        "backtest_win": st["win_rate"],
        "suitable": (st["total_return"] > 0.10 and
                     st["profit_factor"] > 1.5 and
                     st["max_drawdown"] > -0.30 and
                     st["n_trades"] >= 4),
    }


def main():
    rows = []
    total = sum(len(v) for v in SYMBOLS.values())
    done = 0
    t0 = time.time()
    for category, syms in SYMBOLS.items():
        for sym in syms:
            done += 1
            print(f"  [{done:>2d}/{total}] {category:9s} {sym:12s} ...", end=" ", flush=True)
            try:
                r = analyze(sym, category, PARAMS)
                if r is None:
                    print("veri yok")
                    continue
                marker = "★" if r["suitable"] else " "
                print(f"{marker} 2yıl ret={r['backtest_ret_2y']*100:+6.1f}% "
                      f"PF={r['backtest_pf']:.2f} pos={r['position']:5s}")
                rows.append(r)
            except Exception as e:
                print(f"hata: {e}")
    print(f"\n  Tarama süresi: {time.time()-t0:.1f}s")

    if not rows:
        print("Hiç sonuç yok"); return

    df = pd.DataFrame(rows)
    # Skorlama — sonsuz PF'yi 5'e cap, sıralama için
    pf_cap = df["backtest_pf"].clip(upper=5.0).fillna(0)
    df["rank_score"] = df["backtest_ret_2y"] * pf_cap / (1 + df["backtest_dd"].abs())
    df = df.sort_values("rank_score", ascending=False).reset_index(drop=True)
    df.to_csv("scan_result.csv", index=False)

    # ── İlk 15 sembolü detaylı yazdır (en iyi sıralanmış)
    print("\n" + "═"*100)
    print("  EN İYİ SİSTEM PERFORMANSI GÖSTEREN SEMBOLLER (top 15)")
    print("═"*100)
    top = df.head(15)
    for _, r in top.iterrows():
        if r["backtest_ret_2y"] <= 0: continue
        print(f"\n  {r['symbol']:12s} ({r['category']})")
        print(f"     Backtest 2y    : {r['backtest_ret_2y']*100:+7.2f}%  "
              f"PF={r['backtest_pf']:.2f}  DD={r['backtest_dd']*100:+.2f}%  "
              f"n={r['backtest_n']}  win={r['backtest_win']*100:.0f}%")
        print(f"     Şu anki fiyat  : {r['price']:.4f}")
        print(f"     Pozisyon        : {r['position']}    son sinyal: {r['last_signal']}")
        print(f"     Trend OTT       : {r['trend_ott']:.4f}    "
              f"(fiyat > OTT ise yukarı trend)")
        print(f"     Yukarı tetik    : {r['tott_up']:.4f}    "
              f"(fiyat buranın üstüne çıkarsa AL sinyali güçlü)")
        print(f"     Aşağı tetik     : {r['tott_dn']:.4f}    "
              f"(fiyat buranın altına inerse SAT/AÇIĞA SAT)")
        # Uzaklık hesabı
        if r["price"]:
            up_d = (r["tott_up"]/r["price"] - 1) * 100
            dn_d = (r["tott_dn"]/r["price"] - 1) * 100
            print(f"     Uzaklık         : yukarı tetik {up_d:+.2f}%   aşağı tetik {dn_d:+.2f}%")

    print(f"\n  Tam tablo: scan_result.csv")
    print(f"  Toplam: {len(df)} sembol tarandı.")


if __name__ == "__main__":
    main()
