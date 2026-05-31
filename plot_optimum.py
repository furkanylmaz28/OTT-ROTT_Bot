"""
Optimum parametrelerle GOLD'un tüm TF'lerinde equity curve + DD + PnL dağılımı.
JSON'dan optimum parametreleri okur (gold_optimum_params.json).
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import json, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


def plot_one(symbol: str, tf: int, params: dict, save_path: str):
    df = load_symbol("GCM-Demo", symbol, tf)
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )

    fig, axes = plt.subplots(4, 1, figsize=(14, 12),
                             gridspec_kw={"height_ratios": [3, 1.5, 1.5, 2]})

    # Fiyat + işlem
    ax1 = axes[0]
    ax1.plot(df.index, df["close"], color="#444", linewidth=0.7)
    longs = [t for t in res.trades if t.side == "long"]
    shorts = [t for t in res.trades if t.side == "short"]
    if longs:
        ax1.scatter([t.entry_time for t in longs], [t.entry_price for t in longs],
                    marker="^", c="green", s=25, label="Long", zorder=5)
    if shorts:
        ax1.scatter([t.entry_time for t in shorts], [t.entry_price for t in shorts],
                    marker="v", c="red", s=25, label="Short", zorder=5)
    ax1.set_title(f"{symbol} M{tf} — Optimum  ({len(df)} bar)")
    ax1.set_ylabel("Fiyat")
    ax1.legend(fontsize=8); ax1.grid(alpha=0.3)

    # Equity
    ax2 = axes[1]
    ax2.plot(res.equity.index, res.equity.values, color="navy", linewidth=1.2)
    ax2.axhline(10000, color="grey", linestyle="--", linewidth=0.5)
    ax2.set_title(f"Equity — final={res.equity.iloc[-1]:,.0f} "
                  f"ret={res.stats['total_return']*100:+.1f}% "
                  f"PF={res.stats['profit_factor']:.2f} "
                  f"DD={res.stats['max_drawdown']*100:.1f}%")
    ax2.set_ylabel("Equity"); ax2.grid(alpha=0.3)

    # Drawdown
    ax3 = axes[2]
    cm = res.equity.cummax()
    dd = (res.equity/cm - 1) * 100
    ax3.fill_between(dd.index, dd.values, 0, color="red", alpha=0.4)
    ax3.set_title(f"Drawdown (max {res.stats['max_drawdown']*100:.1f}%)")
    ax3.set_ylabel("%"); ax3.grid(alpha=0.3)

    # PnL dağılımı
    ax4 = axes[3]
    closed = [t for t in res.trades if t.exit_price]
    pnls = np.array([t.pnl_pct*100 for t in closed])
    if len(pnls):
        bins = np.linspace(pnls.min(), pnls.max(), 30)
        wins = pnls[pnls>0]; losses = pnls[pnls<=0]
        ax4.hist(losses, bins=bins, color="red", alpha=0.6, label=f"Zarar ({len(losses)})")
        ax4.hist(wins,   bins=bins, color="green", alpha=0.6, label=f"Kazanç ({len(wins)})")
        ax4.axvline(0, color="black", linewidth=0.7)
        ax4.axvline(pnls.mean(), color="blue", linestyle="--", label=f"Ort={pnls.mean():+.2f}%")
        ax4.set_title(f"Trade PnL — N={len(closed)} win={res.stats['win_rate']*100:.0f}% "
                      f"sharpe={res.stats['sharpe']:.2f}")
        ax4.set_xlabel("PnL %"); ax4.legend(); ax4.grid(alpha=0.3)

    for ax in axes[:3]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    plt.tight_layout()
    plt.savefig(save_path, dpi=110, bbox_inches="tight")
    plt.close()
    return res.stats


def main():
    if not os.path.exists("gold_optimum_params.json"):
        print("gold_optimum_params.json YOK — önce gold_optimize.py çalıştır")
        return
    with open("gold_optimum_params.json") as f:
        results = json.load(f)

    os.makedirs("plots_optimum", exist_ok=True)
    summary = []
    for key, v in results.items():
        sym, tfstr = key.split("_")
        tf = int(tfstr[1:])
        params = v["params"]
        # gate_shift JSON'da int olarak gelir — ama params içinde yoksa default 0
        if "gate_shift" not in params:
            params["gate_shift"] = 0
        # rott parametreleri JSON'a girmemişse default ekle
        params.setdefault("rott_x1", 30)
        params.setdefault("rott_x2", 1000)
        params.setdefault("rott_percent", 7.0)
        out = f"plots_optimum/{key}.png"
        print(f"  → {out}")
        stats = plot_one(sym, tf, params, out)
        summary.append((key, stats, params))

    print("\n" + "═" * 70)
    for key, st, p in summary:
        print(f"\n{key}: ret={st['total_return']*100:+.2f}% PF={st['profit_factor']:.2f} "
              f"DD={st['max_drawdown']*100:+.2f}% n={st['n_trades']} "
              f"win={st['win_rate']*100:.1f}%")


if __name__ == "__main__":
    main()
