"""
GOLD M5 ve M15 — son 1 ay (30 gün) optimum parametrelerle backtest.
Trade-by-trade liste ile birlikte.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import json
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


def slice_last_days(symbol: str, tf: int, params: dict, days: int = 30):
    df = load_symbol("GCM-Demo", symbol, tf)
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )

    cutoff = df.index[-1] - pd.Timedelta(days=days)
    eq = res.equity[res.equity.index >= cutoff]
    px = df["close"][df.index >= cutoff]
    period_ret = (eq.iloc[-1] / eq.iloc[0]) - 1
    bh = (px.iloc[-1] / px.iloc[0]) - 1
    cm = eq.cummax()
    dd = ((eq / cm) - 1).min()

    trades_in = [t for t in res.trades
                 if (t.entry_time >= cutoff) or
                    (t.exit_time is not None and t.exit_time >= cutoff)]
    closed = [t for t in trades_in if t.exit_price]
    wins = sum(1 for t in closed if t.pnl_pct > 0)
    losses = sum(1 for t in closed if t.pnl_pct <= 0)
    pos_son = "FLAT"
    if res.position.iloc[-1] == 1: pos_son = "LONG (açık)"
    elif res.position.iloc[-1] == -1: pos_son = "SHORT (açık)"

    print(f"\n══════ {symbol} M{tf} — Son {days} gün "
          f"({cutoff.date()} → {df.index[-1].date()}) ══════")
    print(f"Sistem getirisi  : {period_ret*100:+8.2f}%")
    print(f"Buy & Hold       : {bh*100:+8.2f}%")
    print(f"Max Drawdown     : {dd*100:+8.2f}%")
    print(f"İşlem sayısı     : {len(trades_in):>3d}  ({wins} kazanç / {losses} zarar)")
    print(f"Son pozisyon     : {pos_son}")

    if trades_in:
        print(f"\n  İşlem detayı:")
        hdr = f"  {'Yön':<6} {'Giriş':<17} {'Giriş₣':<10} {'Çıkış':<17} {'Çıkış₣':<10} {'PnL %':<8}"
        print(hdr)
        print("  " + "─" * (len(hdr)-2))
        for t in trades_in:
            exit_str = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "AÇIK"
            exit_p = f"{t.exit_price:.2f}" if t.exit_price else "-"
            pnl_str = f"{t.pnl_pct*100:+6.2f}%" if t.exit_time else "  AÇIK"
            print(f"  {t.side:<6} {t.entry_time.strftime('%Y-%m-%d %H:%M'):<17} "
                  f"{t.entry_price:<10.2f} {exit_str:<17} {exit_p:<10} {pnl_str:<8}")


def main():
    with open("gold_optimum_params.json") as f:
        opt = json.load(f)

    for key in ["GOLD_M15", "GOLD_M5"]:
        params = opt[key]["params"]
        params.setdefault("rott_x1", 30)
        params.setdefault("rott_x2", 1000)
        params.setdefault("rott_percent", 7.0)
        sym, tfstr = key.split("_")
        tf = int(tfstr[1:])
        slice_last_days(sym, tf, params, days=30)


if __name__ == "__main__":
    main()
