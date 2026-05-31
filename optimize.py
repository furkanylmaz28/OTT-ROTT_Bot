"""
Parametre optimizasyonu — .docx 2'deki opt aralıklarıyla grid search.

.docx 2 referansı:
  Bölge testleri:
    Opt1 (trend_length)  : 20 - 40 adım 10
    Opt2 (tott_percent)  : 0.6 - 0.8 adım 0.2
    Opt3 (tott_coeff)    : 0.0004 - 0.0008 adım 0.0002
    Opt4 (sott_period_k) : 200 - 350 adım 50
    Opt5 (sott_smooth_k) : 200 - 250 adım 50
    Opt6 (sott_percent)  : 0.2 - 0.4 adım 0.1

GOLD M15 üzerinde tam sistem çalışır.
Skor : profit_factor × sqrt(n_trades) / (1 + |max_dd|)  — kâr verimliliği × güven × risk-ayarlı.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import time
from itertools import product
import numpy as np
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


def score(stats: dict) -> float:
    n = stats["n_trades"]
    if n < 5:
        return -1e9
    pf = stats["profit_factor"]
    if not np.isfinite(pf):
        pf = 5.0  # inf'i 5'le sınırla
    dd = abs(stats["max_drawdown"])
    ret = stats["total_return"]
    if ret <= 0:
        return -1e9
    return pf * np.sqrt(n) / (1 + dd) * (1 + min(ret, 5))


def optimize(symbol: str, tf: int):
    df = load_symbol("GCM-Demo", symbol, tf)
    print(f"{symbol} M{tf}: {len(df)} bar  ({df.index[0].date()} → {df.index[-1].date()})")

    grid = list(product(
        [20, 30, 40],                  # opt1 trend_length
        [0.6, 0.8],                    # opt2 tott_percent
        [0.0004, 0.0006, 0.0008],      # opt3 tott_coeff
        [200, 300],                    # opt4 sott_period_k
        [200],                         # opt5 sott_smooth_k (tek değer hızlandırma için)
        [0.2, 0.3, 0.4],               # opt6 sott_percent
    ))
    print(f"Grid: {len(grid)} kombinasyon\n")

    results = []
    t0 = time.time()

    for i, (o1, o2, o3, o4, o5, o6) in enumerate(grid):
        s = sig_full.build_signals_full(
            df["close"], df["high"], df["low"],
            trend_length=o1, trend_percent=7.0,
            minor_percent=3.5,
            tott_percent=o2, tott_coeff=o3,
            sott_period_k=o4, sott_smooth_k=o5, sott_percent=o6,
            gate_length=20, gate_percent=0.5,
            rott_x1=30, rott_x2=1000, rott_percent=7.0,
        )
        r = run_backtest(
            df[["open","high","low","close"]],
            s["cond_buy_long"], s["cond_exit_long"],
            s["cond_buy_short"], s["cond_exit_short"],
        )
        sc = score(r.stats)
        results.append({
            "opt1": o1, "opt2": o2, "opt3": o3,
            "opt4": o4, "opt5": o5, "opt6": o6,
            "return": r.stats["total_return"],
            "pf": r.stats["profit_factor"],
            "sharpe": r.stats["sharpe"],
            "dd": r.stats["max_drawdown"],
            "trades": r.stats["n_trades"],
            "win_rate": r.stats["win_rate"],
            "score": sc,
        })
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (len(grid) - i - 1)
        print(f"  [{i+1:3d}/{len(grid)}]  opt1={o1} opt2={o2} opt3={o3} opt4={o4} opt6={o6}"
              f"  ret={r.stats['total_return']*100:+6.1f}%  trades={r.stats['n_trades']:3d}  "
              f"PF={r.stats['profit_factor']:.2f}  score={sc:8.2f}  ETA={eta:.0f}s")

    return pd.DataFrame(results)


def main():
    df_res = optimize("GOLD", 15)
    df_res = df_res.sort_values("score", ascending=False)
    print("\n══════ EN İYİ 10 KOMBİNASYON (GOLD M15) ══════")
    print(df_res.head(10).to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    df_res.to_csv("optimize_gold_m15.csv", index=False)
    print("\nKaydedildi: optimize_gold_m15.csv")

    # .docx default ile karşılaştırma
    default = df_res[(df_res["opt1"]==30) & (df_res["opt2"]==0.8) &
                     (df_res["opt3"]==0.0008) & (df_res["opt4"]==300) &
                     (df_res["opt6"]==0.3)]
    if len(default):
        print("\n.docx default'a en yakın kombinasyon:")
        print(default.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
