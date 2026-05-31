"""
Orta seviye vs Tam sistem karşılaştırması — tüm geçmiş + son 30 gün dilimi.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

import signals as sig_mid
import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


def summarize(label, res, df, cutoff=None):
    eq = res.equity
    if cutoff is not None:
        eq = eq[eq.index >= cutoff]
        period_ret = (eq.iloc[-1] / eq.iloc[0]) - 1
        cummax = eq.cummax()
        dd = ((eq / cummax) - 1).min()
        trades_in = [t for t in res.trades if (t.entry_time >= cutoff) or
                     (t.exit_time is not None and t.exit_time >= cutoff)]
        return {
            "label": label,
            "return": period_ret,
            "dd": dd,
            "trades": len(trades_in),
            "wins": sum(1 for t in trades_in if t.exit_price and t.pnl_pct > 0),
            "losses": sum(1 for t in trades_in if t.exit_price and t.pnl_pct <= 0),
            "final_eq": eq.iloc[-1],
        }
    s = res.stats
    return {
        "label": label,
        "return": s["total_return"],
        "dd": s["max_drawdown"],
        "trades": s["n_trades"],
        "wins": int(s["win_rate"] * s["n_trades"]),
        "losses": s["n_trades"] - int(s["win_rate"] * s["n_trades"]),
        "final_eq": s["final_equity"],
        "sharpe": s["sharpe"],
        "pf": s["profit_factor"],
    }


def run_pair(symbol: str, tf: int):
    df = load_symbol("GCM-Demo", symbol, tf)
    if len(df) < 2000:
        print(f"\n── {symbol} M{tf}: az veri ({len(df)})")
        return

    common = dict(trend_length=30, trend_percent=7.0,
                  tott_percent=0.8, tott_coeff=0.0008,
                  sott_period_k=500, sott_smooth_k=200, sott_percent=0.3)

    # Orta seviye
    s1 = sig_mid.build_signals(df["close"], df["high"], df["low"], **common)
    r1 = run_backtest(df[["open","high","low","close"]],
                     s1["cond_buy_long"], s1["cond_exit_long"],
                     s1["cond_buy_short"], s1["cond_exit_short"])

    # Tam sistem
    s2 = sig_full.build_signals_full(
        df["close"], df["high"], df["low"],
        **common,
        minor_percent=3.5,
        gate_length=20, gate_percent=0.5,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )
    r2 = run_backtest(df[["open","high","low","close"]],
                     s2["cond_buy_long"], s2["cond_exit_long"],
                     s2["cond_buy_short"], s2["cond_exit_short"])

    print(f"\n══════ {symbol} M{tf} ({len(df)} bar, {df.index[0].date()} → {df.index[-1].date()}) ══════")

    # ── Full history
    a = summarize("Orta", r1, df)
    b = summarize("Tam",  r2, df)
    print(f"\n  Tüm Geçmiş:")
    print(f"  {'':10s} {'Return':>10} {'Sharpe':>8} {'MaxDD':>8} {'Trade':>6} {'Win/Loss':>10} {'PF':>6}")
    for x in (a, b):
        print(f"  {x['label']:10s} {x['return']*100:9.2f}% {x['sharpe']:8.2f} {x['dd']*100:7.2f}% "
              f"{x['trades']:6d} {x['wins']:4d}/{x['losses']:<4d}{'':2s}{x['pf']:6.2f}")

    # ── Son 30 gün
    cutoff = df.index[-1] - pd.Timedelta(days=30)
    a30 = summarize("Orta", r1, df, cutoff)
    b30 = summarize("Tam",  r2, df, cutoff)
    bh30 = (df["close"][df.index >= cutoff].iloc[-1] /
            df["close"][df.index >= cutoff].iloc[0] - 1)
    print(f"\n  Son 30 gün ({cutoff.date()} → {df.index[-1].date()}):  Buy&Hold {bh30*100:+.2f}%")
    print(f"  {'':10s} {'Return':>10} {'MaxDD':>8} {'Trade':>6} {'Win/Loss':>10}")
    for x in (a30, b30):
        print(f"  {x['label']:10s} {x['return']*100:+9.2f}% {x['dd']*100:7.2f}% "
              f"{x['trades']:6d} {x['wins']:4d}/{x['losses']:<4d}")


def main():
    for sym, tf in [("GOLD", 5), ("GOLD", 15), ("GOLD", 60),
                    ("EURUSD", 5), ("GBPUSD", 5)]:
        run_pair(sym, tf)


if __name__ == "__main__":
    main()
