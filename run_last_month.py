"""
Son N gün dilim analizi — tüm geçmişle indikatörler hesaplanıp son dilimde
neler olduğuna bakar.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

import signals as sig
from backtest import run_backtest
from mt4_hst import load_symbol


def slice_last_days(server: str, symbol: str, tf: int, days: int, **params) -> None:
    df = load_symbol(server, symbol, tf)
    if len(df) < 1500:
        print(f"── {symbol} M{tf}: yetersiz veri ({len(df)})")
        return

    # Tüm veriyle backtest (warmup dahil)
    s = sig.build_signals(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open", "high", "low", "close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )

    # Son N gün dilimi
    cutoff = df.index[-1] - pd.Timedelta(days=days)
    eq_slice = res.equity[res.equity.index >= cutoff]
    pos_slice = res.position[res.position.index >= cutoff]
    px_slice = df["close"][df.index >= cutoff]

    period_ret = (eq_slice.iloc[-1] / eq_slice.iloc[0]) - 1
    period_bh = (px_slice.iloc[-1] / px_slice.iloc[0]) - 1
    cummax = eq_slice.cummax()
    period_dd = ((eq_slice / cummax) - 1).min()

    # Bu pencerede kapanan / açılan trade'ler
    trades_in_period = []
    for t in res.trades:
        # Son 30 günde girişi VEYA çıkışı olan trade'ler
        entered_in = t.entry_time >= cutoff
        exited_in = (t.exit_time is not None and t.exit_time >= cutoff)
        if entered_in or exited_in:
            trades_in_period.append(t)

    print(f"\n══════ {symbol} M{tf} — Son {days} gün ({cutoff.date()} → {df.index[-1].date()}) ══════")
    print(f"Dönem Getirisi    : {period_ret*100:+8.2f}%")
    print(f"Buy & Hold        : {period_bh*100:+8.2f}%")
    print(f"Dönem Max DD      : {period_dd*100:+8.2f}%")
    print(f"Dönemdeki İşlem   : {len(trades_in_period)}")
    print(f"Equity ilk → son  : {eq_slice.iloc[0]:,.2f} → {eq_slice.iloc[-1]:,.2f}")
    print(f"Pozisyon (son bar): {'LONG' if pos_slice.iloc[-1]==1 else 'SHORT' if pos_slice.iloc[-1]==-1 else 'FLAT'}")

    if trades_in_period:
        print(f"\n  İşlem detayı:")
        print(f"  {'Yön':<6} {'Giriş':<20} {'Giriş₣':<10} {'Çıkış':<20} {'Çıkış₣':<10} {'PnL %':<8} {'Bar':<5}")
        for t in trades_in_period:
            exit_str = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "AÇIK"
            exit_p = f"{t.exit_price:.2f}" if t.exit_price else "-"
            pnl_str = f"{t.pnl_pct*100:+6.2f}%" if t.exit_time else "  AÇIK"
            print(f"  {t.side:<6} {t.entry_time.strftime('%Y-%m-%d %H:%M'):<20} "
                  f"{t.entry_price:<10.2f} {exit_str:<20} {exit_p:<10} "
                  f"{pnl_str:<8} {t.bars_held if t.exit_time else '-':<5}")


def main() -> None:
    docx_params = dict(
        trend_length=30, trend_percent=7.0,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
    )

    targets = [
        ("GOLD", 5),
        ("GOLD", 15),
        ("GOLD", 60),
        ("EURUSD", 5),
        ("GBPUSD", 5),
    ]
    for sym, tf in targets:
        slice_last_days("GCM-Demo", sym, tf, days=30, **docx_params)


if __name__ == "__main__":
    main()
