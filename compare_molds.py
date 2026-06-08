"""
compare_molds.py — KIYAS: serbest grid (overfit) vs eşli-kalıp (İlerleyen yöntem).

Gerçek soru: hangisi GÖRÜLMEMİŞ veride (out-of-sample) daha iyi genelliyor?
- Veriyi böl: in-sample (eski %70) | out-of-sample (son %30)
- Her iki yöntem de SADECE in-sample'da optimize eder, OOS'ta ölçülür.
- Overfit'in imzası: in-sample harika, OOS çöküyor.

Eğitimin tezi: eşli-kalıp in-sample'da daha mütevazı ama OOS'ta DAHA STABİL.
"""
from __future__ import annotations
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
from dotenv import load_dotenv; load_dotenv(".env")

import numpy as np, pandas as pd
import signals_full as sig_full
from backtest import run_backtest
from data_source import fetch as ds_fetch, best_interval_for
import equivalence as eq


def ev(df, p):
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **p)
    res = run_backtest(df[["open","high","low","close"]],
                       s["cond_buy_long"], s["cond_exit_long"],
                       s["cond_buy_short"], s["cond_exit_short"])
    st = res.stats
    return st["total_return"], st["n_trades"], st["profit_factor"]


def score(ret, n):
    return ret if n >= 3 else -1e9   # min 3 trade, yoksa geçersiz


def pick_best(df_is, combos):
    best, bsc = None, -1e9
    for c in combos:
        try:
            ret, n, pf = ev(df_is, c["params"])
        except Exception:
            continue
        sc = score(ret, n)
        if sc > bsc:
            bsc, best = sc, c
    return best


def main():
    SYMS = ["BTC-USD", "ASELS.IS", "ARCLK.IS", "GARAN.IS", "THYAO.IS", "EREGL.IS"]
    print(f"{'Sembol':10s} | {'SERBEST grid':28s} | {'EŞLİ kalıp':28s}")
    print(f"{'':10s} | {'in-sample → OOS':28s} | {'in-sample → OOS':28s}")
    print("-" * 78)

    free = eq.free_grid()
    molds = eq.all_molds()
    agg = {"free_is": [], "free_oos": [], "mold_is": [], "mold_oos": []}

    for sym in SYMS:
        df = ds_fetch(sym, interval=best_interval_for(sym), n_bars=5000)
        if df.empty or len(df) < 2000:
            print(f"{sym:10s} | veri yok ({len(df)} bar)"); continue
        df = df[["open","high","low","close"]].dropna()
        cut = int(len(df) * 0.70)
        df_is, df_oos = df.iloc[:cut], df.iloc[cut:]

        # SERBEST: in-sample'da en iyiyi seç → OOS'ta ölç
        bf = pick_best(df_is, free)
        f_is_r, _, _ = ev(df_is, bf["params"]) if bf else (0,0,0)
        f_oos_r, f_oos_n, _ = ev(df_oos, bf["params"]) if bf else (0,0,0)

        # EŞLİ KALIP: in-sample'da en iyi kalıbı seç → OOS'ta ölç
        bm = pick_best(df_is, molds)
        m_is_r, _, _ = ev(df_is, bm["params"]) if bm else (0,0,0)
        m_oos_r, m_oos_n, _ = ev(df_oos, bm["params"]) if bm else (0,0,0)
        mold_name = bm["mold"] if bm else "-"

        f_is, f_oos, m_is, m_oos = (f_is_r*100, f_oos_r*100, m_is_r*100, m_oos_r*100)
        agg["free_is"].append(f_is); agg["free_oos"].append(f_oos)
        agg["mold_is"].append(m_is); agg["mold_oos"].append(m_oos)

        print(f"{sym:10s} | {f_is:+6.0f}%→{f_oos:+6.0f}% (t{f_oos_n}) "
              f"| {m_is:+6.0f}%→{m_oos:+6.0f}% (t{m_oos_n}) [{mold_name}] ({len(df)}bar)")

    print("-" * 78)
    def avg(x): return sum(x)/len(x) if x else 0
    print(f"ORTALAMA   | IS {avg(agg['free_is']):+6.0f}% OOS {avg(agg['free_oos']):+6.0f}% "
          f"| IS {avg(agg['mold_is']):+6.0f}% OOS {avg(agg['mold_oos']):+6.0f}%")
    print(f"\nOOS = gerçeğe en yakın. Yüksek OOS + küçük düşüş (degradation) = az overfit = iyi.")


if __name__ == "__main__":
    main()
