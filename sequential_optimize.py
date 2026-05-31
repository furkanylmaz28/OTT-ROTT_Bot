"""
Anıl Özekşi'nin .docx'inde önerdiği sıralı test prosedürü.

Aşama 1 — TREND TESTİ:
   Sabit gövde + kapı + ROTT default ile,
   Optimize: trend_length, trend_percent, minor_percent
   .docx 1 aralıkları:
     trend_length    : 20, 30, 40 (.docx 2'de: 20-50 step 10)
     trend_percent   : 5.0, 6.0, 7.0, 8.0, 9.0 (.docx: 5-9 step 0.5)
     minor_percent   : 3.0, 3.5, 4.0 (.docx: 3-4 step 0.2)

Aşama 2 — BÖLGE TESTİ:
   Trend (Aşama 1) sabit,
   Optimize: tott_percent, tott_coeff, sott_period_k, sott_smooth_k, sott_percent
   .docx 2 aralıkları (forex/gold için biraz daraltıldı):
     tott_percent    : 0.6, 0.8, 1.0
     tott_coeff      : 0.0004, 0.0006, 0.0008
     sott_period_k   : 200, 300, 500
     sott_smooth_k   : 200
     sott_percent    : 0.2, 0.3, 0.4

Aşama 3 — KAPI TESTİ:
   Trend + Bölge sabit,
   Optimize: gate_length, gate_percent, gate_shift (anlık vs Pine-gecikme)
   .docx aralıkları:
     gate_length     : 10, 16, 22, 28
     gate_percent    : 0.4, 0.5, 0.6
     gate_shift      : 0, 2

Skor:
   filtre: n_trades >= 20, max_dd >= -25%, getiri > 0, profit_factor > 1.2
   filtre geçen sonuçlar arasında: getiri × pf / (1 + |dd|)
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


# ── Skor fonksiyonu
def score(stats: dict, min_trades: int = 20) -> float:
    n = stats["n_trades"]
    pf = stats["profit_factor"]
    dd = abs(stats["max_drawdown"])
    ret = stats["total_return"]
    if n < min_trades or ret <= 0 or dd > 0.25 or pf < 1.2:
        return -1e9
    if not np.isfinite(pf):
        pf = 5.0
    return ret * pf / (1 + dd)


# ── Tek bir parametre setiyle backtest
def run_params(df: pd.DataFrame, params: dict) -> dict:
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    r = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    return r.stats


# ── Aşama 1: Trend testi
def stage1_trend(df: pd.DataFrame, base: dict) -> tuple[dict, pd.DataFrame]:
    grid = list(product(
        [20, 30, 40],            # trend_length
        [5.0, 6.0, 7.0, 8.0],    # trend_percent
        [3.0, 3.5, 4.0],         # minor_percent
    ))
    rows = []
    t0 = time.time()
    for i, (tl, tp, mp) in enumerate(grid):
        params = {**base, "trend_length": tl, "trend_percent": tp, "minor_percent": mp}
        st = run_params(df, params)
        sc = score(st)
        rows.append({**{"trend_length": tl, "trend_percent": tp, "minor_percent": mp},
                     **st, "score": sc})
        print(f"    T1[{i+1:2d}/{len(grid)}] L={tl} p={tp} minor={mp}  "
              f"ret={st['total_return']*100:+6.1f}% n={st['n_trades']:3d} "
              f"PF={st['profit_factor']:.2f} DD={st['max_drawdown']*100:.1f}%  score={sc:.2f}")
    df_res = pd.DataFrame(rows).sort_values("score", ascending=False)
    best = df_res.iloc[0]
    print(f"  Aşama 1 süre: {time.time()-t0:.1f}s")
    return {
        "trend_length": int(best["trend_length"]),
        "trend_percent": float(best["trend_percent"]),
        "minor_percent": float(best["minor_percent"]),
    }, df_res


# ── Aşama 2: Bölge testi
def stage2_zone(df: pd.DataFrame, base: dict) -> tuple[dict, pd.DataFrame]:
    grid = list(product(
        [0.6, 0.8, 1.0],                # tott_percent
        [0.0004, 0.0006, 0.0008],       # tott_coeff
        [200, 300, 500],                # sott_period_k
        [200],                          # sott_smooth_k (tek değer)
        [0.2, 0.3, 0.4],                # sott_percent
    ))
    rows = []
    t0 = time.time()
    for i, (tp, tc, pk, sk, sp) in enumerate(grid):
        params = {**base,
                  "tott_percent": tp, "tott_coeff": tc,
                  "sott_period_k": pk, "sott_smooth_k": sk, "sott_percent": sp}
        st = run_params(df, params)
        sc = score(st)
        rows.append({"tott_percent": tp, "tott_coeff": tc, "sott_period_k": pk,
                     "sott_smooth_k": sk, "sott_percent": sp, **st, "score": sc})
        print(f"    T2[{i+1:2d}/{len(grid)}] tott_p={tp} coeff={tc} sottK={pk} sott_p={sp}  "
              f"ret={st['total_return']*100:+6.1f}% n={st['n_trades']:3d} "
              f"PF={st['profit_factor']:.2f}  score={sc:.2f}")
    df_res = pd.DataFrame(rows).sort_values("score", ascending=False)
    best = df_res.iloc[0]
    print(f"  Aşama 2 süre: {time.time()-t0:.1f}s")
    return {
        "tott_percent": float(best["tott_percent"]),
        "tott_coeff": float(best["tott_coeff"]),
        "sott_period_k": int(best["sott_period_k"]),
        "sott_smooth_k": int(best["sott_smooth_k"]),
        "sott_percent": float(best["sott_percent"]),
    }, df_res


# ── Aşama 3: Kapı testi
def stage3_gate(df: pd.DataFrame, base: dict) -> tuple[dict, pd.DataFrame]:
    grid = list(product(
        [10, 16, 22, 28],            # gate_length
        [0.4, 0.5, 0.6],             # gate_percent
        [0, 2],                      # gate_shift
    ))
    rows = []
    t0 = time.time()
    for i, (gl, gp, gs) in enumerate(grid):
        params = {**base, "gate_length": gl, "gate_percent": gp, "gate_shift": gs}
        st = run_params(df, params)
        sc = score(st)
        rows.append({"gate_length": gl, "gate_percent": gp, "gate_shift": gs,
                     **st, "score": sc})
        print(f"    T3[{i+1:2d}/{len(grid)}] gateL={gl} gateP={gp} shift={gs}  "
              f"ret={st['total_return']*100:+6.1f}% n={st['n_trades']:3d} "
              f"PF={st['profit_factor']:.2f}  score={sc:.2f}")
    df_res = pd.DataFrame(rows).sort_values("score", ascending=False)
    best = df_res.iloc[0]
    print(f"  Aşama 3 süre: {time.time()-t0:.1f}s")
    return {
        "gate_length": int(best["gate_length"]),
        "gate_percent": float(best["gate_percent"]),
        "gate_shift": int(best["gate_shift"]),
    }, df_res


# ── Tüm sıralı süreç
def sequential_optimize(symbol: str, tf: int, max_bars: int = 175_000):
    df = load_symbol("GCM-Demo", symbol, tf)
    if len(df) > max_bars:
        df = df.tail(max_bars)
    print(f"\n{'═'*70}")
    print(f"  {symbol} M{tf}: {len(df)} bar ({df.index[0].date()} → {df.index[-1].date()})")
    print(f"{'═'*70}")

    # Başlangıç parametreleri (default'lar)
    base = dict(
        trend_length=30, trend_percent=7.0,
        minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5, gate_shift=0,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )

    print("\n── AŞAMA 1: TREND TESTİ ──")
    trend_best, t1_res = stage1_trend(df, base)
    print(f"  En iyi trend: {trend_best}")
    base.update(trend_best)

    print("\n── AŞAMA 2: BÖLGE TESTİ ──")
    zone_best, t2_res = stage2_zone(df, base)
    print(f"  En iyi bölge: {zone_best}")
    base.update(zone_best)

    print("\n── AŞAMA 3: KAPI TESTİ ──")
    gate_best, t3_res = stage3_gate(df, base)
    print(f"  En iyi kapı: {gate_best}")
    base.update(gate_best)

    # Final test
    print("\n── FİNAL: tüm parametrelerle tam backtest ──")
    final_stats = run_params(df, base)
    final_score = score(final_stats)
    print(f"  return={final_stats['total_return']*100:+.2f}%  "
          f"PF={final_stats['profit_factor']:.2f}  "
          f"DD={final_stats['max_drawdown']*100:.2f}%  "
          f"trades={final_stats['n_trades']}  "
          f"sharpe={final_stats['sharpe']:.2f}  "
          f"win={final_stats['win_rate']*100:.1f}%")
    print(f"  Final score: {final_score:.2f}")

    # Buy & Hold
    bh = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
    print(f"  Buy & Hold:  {bh*100:+.2f}%")

    return base, final_stats, t1_res, t2_res, t3_res


def main():
    targets = [("GOLD", 15), ("GBPUSD", 15), ("EURGBP", 15)]
    summary = []
    for sym, tf in targets:
        best_params, final, t1, t2, t3 = sequential_optimize(sym, tf)
        summary.append({"symbol": sym, "tf": tf,
                        "params": best_params, "final": final})
        # CSV'leri kaydet
        t1.to_csv(f"seqopt_{sym}_M{tf}_T1_trend.csv", index=False)
        t2.to_csv(f"seqopt_{sym}_M{tf}_T2_zone.csv", index=False)
        t3.to_csv(f"seqopt_{sym}_M{tf}_T3_gate.csv", index=False)

    print("\n" + "═" * 70)
    print("  SIRALI OPTIMIZE ÖZETI")
    print("═" * 70)
    for s in summary:
        fs = s["final"]
        print(f"\n{s['symbol']} M{s['tf']}:")
        print(f"  return = {fs['total_return']*100:+7.2f}%  PF={fs['profit_factor']:.2f}  "
              f"DD={fs['max_drawdown']*100:+.2f}%  trades={fs['n_trades']}  "
              f"win={fs['win_rate']*100:.1f}%  sharpe={fs['sharpe']:.2f}")
        print(f"  params = {s['params']}")


if __name__ == "__main__":
    main()
