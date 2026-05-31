"""
SON 30 GÜN ODAKLI sıralı optimize — overfit göstermek için.

İndikatörler tüm veride hesaplanır (warmup), sinyaller ve istatistikler
sadece son 30 günlük dilimden çıkarılır. Optimize bu dilimi maksimize eder.

Sonra:
  (a) Son 30 gün optimum parametreleriyle son 30 günü test et
  (b) Aynı parametrelerle TÜM veriyi test et — overfit oranını gör
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import json
import time
from itertools import product
import numpy as np
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


def stats_in_window(res, df, cutoff):
    eq = res.equity[res.equity.index >= cutoff]
    if len(eq) < 2:
        return None
    ret = (eq.iloc[-1] / eq.iloc[0]) - 1
    cm = eq.cummax()
    dd = ((eq / cm) - 1).min()
    trades_in = [t for t in res.trades
                 if (t.entry_time >= cutoff) or
                    (t.exit_time is not None and t.exit_time >= cutoff)]
    closed = [t for t in trades_in if t.exit_price]
    wins = sum(1 for t in closed if t.pnl_pct > 0)
    losses = sum(1 for t in closed if t.pnl_pct <= 0)
    pos_pnl = sum(t.pnl_pct for t in closed if t.pnl_pct > 0)
    neg_pnl = sum(t.pnl_pct for t in closed if t.pnl_pct <= 0)
    pf = (pos_pnl / -neg_pnl) if neg_pnl < 0 else (float("inf") if pos_pnl > 0 else 0)
    return {
        "return": ret, "max_dd": dd, "n_trades": len(trades_in),
        "n_closed": len(closed), "wins": wins, "losses": losses,
        "win_rate": wins / max(len(closed), 1), "pf": pf,
    }


def score_window(st):
    """Esnek skor — negatif return de tolere et (sıralama için)."""
    if st is None: return -1e9
    if st["n_closed"] < 2: return -1e9
    ret = st["return"]; dd = abs(st["max_dd"])
    pf = st["pf"] if np.isfinite(st["pf"]) else 5.0
    # Risk-adjusted: getiri / (1+DD); negatif getiriyi penalize et
    if ret <= 0:
        return ret / (1 + dd)  # negatif sıralama
    return ret * max(pf, 0.5) / (1 + dd)


def evaluate(df, cutoff, params):
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    return stats_in_window(res, df, cutoff), res


def optimize_last1m(symbol: str, tf: int, days: int = 30):
    df = load_symbol("GCM-Demo", symbol, tf)
    cutoff = df.index[-1] - pd.Timedelta(days=days)
    print(f"\n{'═'*70}")
    print(f"  {symbol} M{tf}: optimize edilen dilim {cutoff.date()} → {df.index[-1].date()}")
    print(f"  toplam veri: {len(df)} bar, dilim: ~{(df.index >= cutoff).sum()} bar")
    print(f"{'═'*70}")

    base = dict(
        trend_length=30, trend_percent=7.0,
        minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5, gate_shift=0,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )

    # AŞAMA 1 — trend
    print("\n── AŞAMA 1: TREND ──")
    t0 = time.time()
    grid1 = list(product([20,30,40], [5.0,6.0,7.0,8.0], [3.0,3.5,4.0]))
    best, best_sc = None, -1e9
    for tl, tp, mp in grid1:
        p = {**base, "trend_length": tl, "trend_percent": tp, "minor_percent": mp}
        st, _ = evaluate(df, cutoff, p)
        sc = score_window(st)
        if sc > best_sc:
            best_sc, best = sc, p.copy()
    print(f"  süre: {time.time()-t0:.1f}s  best: tl={best['trend_length']} tp={best['trend_percent']} mp={best['minor_percent']}")
    base = best

    # AŞAMA 2 — bölge
    print("\n── AŞAMA 2: BÖLGE ──")
    t0 = time.time()
    grid2 = list(product([0.6,0.8,1.0], [0.0004,0.0006,0.0008],
                         [200,300,500], [200], [0.2,0.3,0.4]))
    best_sc = -1e9
    for tp, tc, pk, sk, sp in grid2:
        p = {**base, "tott_percent": tp, "tott_coeff": tc,
             "sott_period_k": pk, "sott_smooth_k": sk, "sott_percent": sp}
        st, _ = evaluate(df, cutoff, p)
        sc = score_window(st)
        if sc > best_sc:
            best_sc, best = sc, p.copy()
    print(f"  süre: {time.time()-t0:.1f}s")
    base = best

    # AŞAMA 3 — kapı
    print("\n── AŞAMA 3: KAPI ──")
    t0 = time.time()
    grid3 = list(product([10,16,22,28], [0.4,0.5,0.6], [0,2]))
    best_sc = -1e9
    for gl, gp, gs in grid3:
        p = {**base, "gate_length": gl, "gate_percent": gp, "gate_shift": gs}
        st, _ = evaluate(df, cutoff, p)
        sc = score_window(st)
        if sc > best_sc:
            best_sc, best = sc, p.copy()
    print(f"  süre: {time.time()-t0:.1f}s")

    # Final
    st_window, res = evaluate(df, cutoff, best)
    full_stats = res.stats
    px = df["close"][df.index >= cutoff]
    bh = (px.iloc[-1]/px.iloc[0]) - 1

    print(f"\n══ FİNAL — son {days} gün optimum ══")
    print(f"  params: {best}")
    print(f"\n  ► Son {days} gün performansı:")
    print(f"      Sistem ret = {st_window['return']*100:+.2f}%   "
          f"BH = {bh*100:+.2f}%   "
          f"DD = {st_window['max_dd']*100:+.2f}%")
    print(f"      trade = {st_window['n_trades']}  "
          f"({st_window['wins']} kazanç / {st_window['losses']} zarar)  "
          f"PF = {st_window['pf']:.2f}")
    print(f"\n  ► AYNI parametrelerle TÜM veri (overfit kontrolü):")
    print(f"      return = {full_stats['total_return']*100:+.2f}%   "
          f"PF = {full_stats['profit_factor']:.2f}   "
          f"DD = {full_stats['max_drawdown']*100:+.2f}%   "
          f"n = {full_stats['n_trades']}")
    print(f"      sharpe = {full_stats['sharpe']:.2f}   win = {full_stats['win_rate']*100:.1f}%")
    return best, st_window, full_stats


def main():
    results = {}
    for tf in [15, 5]:
        params, w, full = optimize_last1m("GOLD", tf, days=30)
        results[f"GOLD_M{tf}"] = {"params": params, "window": w, "full": full}

    # Karşılaştırma — önceki uzun-vadeli optimum vs şimdiki son-1-ay optimum
    print("\n" + "═"*70)
    print("  KARŞILAŞTIRMA — uzun-vadeli optimum vs son-1-ay optimum")
    print("═"*70)
    with open("gold_optimum_params.json") as f:
        long_opt = json.load(f)
    for tf in [15, 5]:
        key = f"GOLD_M{tf}"
        long_p = long_opt[key]["params"]
        long_st = long_opt[key]["stats"]
        new_full = results[key]["full"]
        new_w = results[key]["window"]
        print(f"\n{key}:")
        print(f"  UZUN-VADELI OPTIMUM (tam veri):")
        print(f"    return={long_st['return']*100:+.2f}%  PF={long_st['pf']:.2f}  "
              f"DD={long_st['max_dd']*100:+.2f}%  n={long_st['n_trades']}")
        print(f"  SON-1-AY OPTIMUM:")
        print(f"    son 30 gün : ret={new_w['return']*100:+.2f}%  PF={new_w['pf']:.2f}  n={new_w['n_trades']}")
        print(f"    tüm veri   : ret={new_full['total_return']*100:+.2f}%  "
              f"PF={new_full['profit_factor']:.2f}  DD={new_full['max_drawdown']*100:+.2f}%  "
              f"n={new_full['n_trades']}")


if __name__ == "__main__":
    main()
