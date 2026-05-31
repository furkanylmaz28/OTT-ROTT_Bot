"""
Equity curve + drawdown + trade PnL dağılımı + fiyat üzerinde işlemler.
GOLD M5 ve M15 için tam sistem.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


def plot_one(symbol: str, tf: int, save_path: str):
    df = load_symbol("GCM-Demo", symbol, tf)
    s = sig_full.build_signals_full(
        df["close"], df["high"], df["low"],
        trend_length=30, trend_percent=7.0,
        minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=False,
                             gridspec_kw={"height_ratios": [3, 1.5, 1.5, 2]})

    # ── 1) Fiyat + işlem noktaları
    ax1 = axes[0]
    ax1.plot(df.index, df["close"], color="#444", linewidth=0.8, label="Close")
    long_entries = [t for t in res.trades if t.side == "long"]
    short_entries = [t for t in res.trades if t.side == "short"]
    if long_entries:
        x = [t.entry_time for t in long_entries]
        y = [t.entry_price for t in long_entries]
        ax1.scatter(x, y, marker="^", c="green", s=30, zorder=5, label="Long")
    if short_entries:
        x = [t.entry_time for t in short_entries]
        y = [t.entry_price for t in short_entries]
        ax1.scatter(x, y, marker="v", c="red", s=30, zorder=5, label="Short")
    # exit points
    exits_w = [t for t in res.trades if t.exit_price and t.pnl_pct > 0]
    exits_l = [t for t in res.trades if t.exit_price and t.pnl_pct <= 0]
    if exits_w:
        ax1.scatter([t.exit_time for t in exits_w], [t.exit_price for t in exits_w],
                    marker="o", c="lime", s=15, alpha=0.7, label="Kazanan çıkış")
    if exits_l:
        ax1.scatter([t.exit_time for t in exits_l], [t.exit_price for t in exits_l],
                    marker="x", c="darkred", s=20, alpha=0.7, label="Kayıp çıkış")
    ax1.set_title(f"{symbol} M{tf} — Fiyat + İşlemler  ({len(df)} bar)")
    ax1.set_ylabel("Fiyat")
    ax1.legend(loc="best", fontsize=8)
    ax1.grid(alpha=0.3)

    # ── 2) Equity
    ax2 = axes[1]
    ax2.plot(res.equity.index, res.equity.values, color="navy", linewidth=1.2)
    ax2.axhline(10000, color="grey", linestyle="--", linewidth=0.6)
    ax2.set_title(f"Equity Curve  (final={res.equity.iloc[-1]:,.0f}, "
                  f"return={res.stats['total_return']*100:+.1f}%)")
    ax2.set_ylabel("Equity")
    ax2.grid(alpha=0.3)

    # ── 3) Drawdown
    ax3 = axes[2]
    cummax = res.equity.cummax()
    dd = (res.equity / cummax) - 1
    ax3.fill_between(dd.index, dd.values * 100, 0, color="red", alpha=0.4)
    ax3.set_title(f"Drawdown  (max={res.stats['max_drawdown']*100:.1f}%)")
    ax3.set_ylabel("DD %")
    ax3.grid(alpha=0.3)

    # ── 4) Trade PnL dağılımı
    ax4 = axes[3]
    closed = [t for t in res.trades if t.exit_price]
    pnls = np.array([t.pnl_pct * 100 for t in closed])
    if len(pnls):
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        bins = np.linspace(pnls.min(), pnls.max(), 30)
        ax4.hist(losses, bins=bins, color="red", alpha=0.6, label=f"Zarar ({len(losses)})")
        ax4.hist(wins, bins=bins, color="green", alpha=0.6, label=f"Kazanç ({len(wins)})")
        ax4.axvline(0, color="black", linewidth=0.8)
        ax4.axvline(pnls.mean(), color="blue", linestyle="--", linewidth=1,
                    label=f"Ortalama={pnls.mean():+.2f}%")
        ax4.set_title(f"Trade PnL Dağılımı  (N={len(closed)}, "
                      f"win%={res.stats['win_rate']*100:.1f}, PF={res.stats['profit_factor']:.2f})")
        ax4.set_xlabel("PnL %")
        ax4.set_ylabel("Frekans")
        ax4.legend()
        ax4.grid(alpha=0.3)

    for ax in axes[:3]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.tick_params(axis="x", labelrotation=0)

    plt.tight_layout()
    plt.savefig(save_path, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {save_path}")


def main():
    out_dir = "plots"
    import os
    os.makedirs(out_dir, exist_ok=True)
    for sym, tf in [("GOLD", 5), ("GOLD", 15), ("GOLD", 60)]:
        try:
            print(f"\n── {sym} M{tf} ──")
            plot_one(sym, tf, f"{out_dir}/{sym}_M{tf}.png")
        except Exception as e:
            print(f"  HATA: {e}")


if __name__ == "__main__":
    main()
