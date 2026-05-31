"""
Sıralı optimize tabanlı walk-forward.

Her pencerede:
  1) Train periyodu üzerinde sıralı optimize çalıştır (trend → bölge → kapı)
  2) Bulunan en iyi parametrelerle Test periyodunda backtest
  3) OOS sonuçlarını kaydet

Hızlı numba-tabanlı indikatörlerle bu artık makul sürede çalışıyor.
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
from sequential_optimize import stage1_trend, stage2_zone, stage3_gate, run_params, score


def run_window(df: pd.DataFrame, train_start, train_end, test_start, test_end,
               warmup_bars: int = 4000) -> dict:
    train = df[(df.index >= train_start) & (df.index < train_end)]
    # Test dilimi + warmup_bars önceden — TF bağımsız bar-based
    test_pos = df.index.searchsorted(test_start)
    end_pos  = df.index.searchsorted(test_end)
    start_pos = max(0, test_pos - warmup_bars)
    test_with_warmup = df.iloc[start_pos:end_pos]

    base = dict(
        trend_length=30, trend_percent=7.0,
        minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5, gate_shift=0,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )

    print(f"  Train: {train_start.date()} → {train_end.date()}  ({len(train)} bar)")

    # ── Sıralı optimize (train üzerinde, çıktısız mod)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        t1, _ = stage1_trend(train, base); base.update(t1)
        t2, _ = stage2_zone(train, base);  base.update(t2)
        t3, _ = stage3_gate(train, base);  base.update(t3)
    in_sample_stats = run_params(train, base)

    # ── OOS test (warmup dahil indikatörler için, sonra test dilimi)
    s = sig_full.build_signals_full(test_with_warmup["close"],
                                     test_with_warmup["high"],
                                     test_with_warmup["low"], **base)
    r = run_backtest(
        test_with_warmup[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    eq_test = r.equity[r.equity.index >= test_start]
    if len(eq_test) < 2:
        return None
    oos_ret = (eq_test.iloc[-1] / eq_test.iloc[0]) - 1
    cummax = eq_test.cummax()
    oos_dd = ((eq_test / cummax) - 1).min()
    trades_in = [t for t in r.trades
                 if t.entry_time >= test_start and t.entry_time < test_end]
    closed = [t for t in trades_in if t.exit_price]
    wins = sum(1 for t in closed if t.pnl_pct > 0)
    bh = (df["close"][(df.index >= test_start) & (df.index < test_end)].iloc[-1] /
          df["close"][(df.index >= test_start) & (df.index < test_end)].iloc[0] - 1)

    return {
        "train_start": train_start, "train_end": train_end,
        "test_start": test_start, "test_end": test_end,
        "params": base.copy(),
        "is_return": in_sample_stats["total_return"],
        "is_pf": in_sample_stats["profit_factor"],
        "is_dd": in_sample_stats["max_drawdown"],
        "is_trades": in_sample_stats["n_trades"],
        "oos_return": oos_ret,
        "oos_dd": oos_dd,
        "oos_trades": len(trades_in),
        "oos_wins": wins,
        "bh_return": bh,
    }


def walk_forward(symbol: str, tf: int,
                 train_months: int = 12, test_months: int = 3, step_months: int = 3,
                 max_bars: int = 175_000) -> pd.DataFrame:
    df = load_symbol("GCM-Demo", symbol, tf)
    if len(df) > max_bars:
        df = df.tail(max_bars)
    print(f"\n{'═'*70}")
    print(f"  WALK-FORWARD: {symbol} M{tf}  {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  Train={train_months}ay  Test={test_months}ay  Step={step_months}ay")
    print(f"{'═'*70}")

    start = df.index[0] + pd.DateOffset(months=train_months)
    end_data = df.index[-1]
    records = []
    test_starts = []
    cur = start
    while cur + pd.DateOffset(months=test_months) <= end_data:
        test_starts.append(cur)
        cur = cur + pd.DateOffset(months=step_months)

    print(f"  {len(test_starts)} pencere\n")

    t0 = time.time()
    for wi, ts in enumerate(test_starts):
        train_start = ts - pd.DateOffset(months=train_months)
        train_end = ts
        test_end = ts + pd.DateOffset(months=test_months)
        print(f"\n[{wi+1:2d}/{len(test_starts)}] " + "─" * 50)
        r = run_window(df, train_start, train_end, ts, test_end)
        if r is None:
            continue
        records.append(r)
        elapsed = time.time() - t0
        eta = elapsed / (wi + 1) * (len(test_starts) - wi - 1)
        print(f"  IS:  ret={r['is_return']*100:+6.1f}% PF={r['is_pf']:.2f} "
              f"DD={r['is_dd']*100:.1f}% n={r['is_trades']}")
        print(f"  OOS: ret={r['oos_return']*100:+6.1f}% DD={r['oos_dd']*100:.1f}% "
              f"n={r['oos_trades']}/{r['oos_wins']}wins  BH={r['bh_return']*100:+.1f}%")
        print(f"  ETA: {eta:.0f}s")

    return pd.DataFrame(records)


def summarize(df_wf: pd.DataFrame, label: str):
    print(f"\n══════ ÖZET: {label} ══════")
    n = len(df_wf)
    if n == 0:
        print("Yok")
        return
    avg_is = df_wf["is_return"].mean()
    avg_oos = df_wf["oos_return"].mean()
    pos_oos = (df_wf["oos_return"] > 0).sum()
    sum_oos = (1 + df_wf["oos_return"]).prod() - 1
    sum_bh = (1 + df_wf["bh_return"]).prod() - 1
    avg_dd = df_wf["oos_dd"].mean()
    worst = df_wf["oos_return"].min()
    best = df_wf["oos_return"].max()
    wfe = avg_oos / avg_is if avg_is > 0 else 0
    print(f"  pencere   : {n}")
    print(f"  ort IS    : {avg_is*100:+8.2f}%")
    print(f"  ort OOS   : {avg_oos*100:+8.2f}%")
    print(f"  WF eff    : {wfe*100:8.1f}%  (OOS/IS — %50+ makul)")
    print(f"  pozitif   : {pos_oos}/{n}  ({pos_oos/n*100:.0f}%)")
    print(f"  toplam OOS: {sum_oos*100:+8.2f}%")
    print(f"  Buy&Hold  : {sum_bh*100:+8.2f}%")
    print(f"  ort DD    : {avg_dd*100:+8.2f}%")
    print(f"  worst/best: {worst*100:+.2f}% / {best*100:+.2f}%")


def main():
    # GOLD odaklı — forex pariteleri bu sistemde çalışmıyor.
    # M15: 29 ay veri — train=8 test=2 step=2 → 10 pencere
    df_wf = walk_forward("GOLD", 15, train_months=8, test_months=2, step_months=2)
    summarize(df_wf, "GOLD M15")
    df_wf.to_csv("wfseq_GOLD_M15.csv", index=False)
    # M5: 11 ay veri — train=6 test=1 step=1 → 4-5 pencere
    df_wf2 = walk_forward("GOLD", 5, train_months=6, test_months=1, step_months=1)
    summarize(df_wf2, "GOLD M5")
    df_wf2.to_csv("wfseq_GOLD_M5.csv", index=False)


if __name__ == "__main__":
    main()
