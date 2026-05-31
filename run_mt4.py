"""
MT4 .hst (GCM-Demo) verisiyle orta seviye sistem backtest'i.

GOLD ve EURUSD/GBPUSD M5 — .docx orjinal parametreleriyle (intraday için tunelenmiş)
ve daha kısa SOTT alternatifiyle.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

import signals as sig
from backtest import run_backtest, print_stats
from mt4_hst import load_symbol


# (sembol, timeframe) çiftleri
TARGETS = [
    ("GOLD", 5),
    ("EURUSD", 5),
    ("GBPUSD", 5),
    ("GOLD", 15),
    ("GOLD", 60),
]


def run_one(server: str, symbol: str, tf: int, **params) -> None:
    try:
        df = load_symbol(server, symbol, tf)
    except FileNotFoundError as e:
        print(f"\n── {symbol} M{tf} —— {e}")
        return

    if len(df) < 1500:
        print(f"\n── {symbol} M{tf} —— yeterli veri yok ({len(df)} bar)")
        return

    s = sig.build_signals(df["close"], df["high"], df["low"], **params)
    result = run_backtest(
        df[["open", "high", "low", "close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    label = f"{symbol} M{tf}  ({len(df)} bar, {df.index[0].date()} → {df.index[-1].date()})"
    print_stats(result, label)
    bh = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
    print(f"Buy & Hold        : {bh*100:8.2f}%")


def main() -> None:
    docx_params = dict(
        trend_length=30, trend_percent=7.0,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
    )
    # M5'te 500 bar = ~42 saat → çok kısa; daha hızlı SOTT da deneyelim
    fast_sott = dict(
        trend_length=30, trend_percent=7.0,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=288, sott_smooth_k=72, sott_percent=0.3,  # 1 gün / 6 saat
    )

    print("=" * 70)
    print(".docx orjinal parametreleri (intraday için tunelenmiş)")
    print("=" * 70)
    for sym, tf in TARGETS:
        run_one("GCM-Demo", sym, tf, **docx_params)

    print("\n")
    print("=" * 70)
    print("Hızlandırılmış SOTT (1 gün periyot, 6 saat smoothing)")
    print("=" * 70)
    for sym, tf in TARGETS:
        run_one("GCM-Demo", sym, tf, **fast_sott)


if __name__ == "__main__":
    main()
