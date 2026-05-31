"""
yfinance ile veri çek → sinyal kur → backtest çalıştır → istatistikleri yazdır.

NOT: .docx'teki parametreler intraday (5-dk) için tunelenmiş. Günlük barda
istatistikler yön gösterir ama optimal olmayabilir. İlk amaç sistemin
çalıştığını ve mantığın doğru hesaplandığını görmek.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

import signals as sig
from backtest import run_backtest, print_stats


SYMBOLS = [
    # Nasdaq
    "QQQ",        # Nasdaq 100 ETF
    "AAPL",
    "NVDA",
    # BIST  (yfinance .IS uzantısıyla)
    "ASELS.IS",
    "THYAO.IS",
    "GARAN.IS",
]


def fetch(symbol: str, period: str = "5y", interval: str = "1d") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval,
                     auto_adjust=False, progress=False)
    if df.empty:
        return df
    # multi-index sütunları düzleştir
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.lower)
    df = df[["open", "high", "low", "close"]].dropna()
    return df


def run_one(symbol: str, period: str = "5y", interval: str = "1d", **params) -> None:
    df = fetch(symbol, period, interval)
    if df.empty or len(df) < 600:
        print(f"\n── {symbol} —— yeterli veri yok ({len(df)} bar) ──")
        return

    s = sig.build_signals(df["close"], df["high"], df["low"], **params)
    result = run_backtest(
        df[["open", "high", "low", "close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    print_stats(result, f"{symbol}  ({len(df)} bar, {interval})")
    # buy & hold ile karşılaştır
    bh = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
    print(f"Buy & Hold        : {bh*100:8.2f}%")


def main() -> None:
    # .docx 2'deki orjinal parametreler (5-dk için tunelenmiş)
    docx_params = dict(
        trend_length=30, trend_percent=7.0,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
    )
    # günlük bar için daha mantıklı versiyon
    daily_params = dict(
        trend_length=30, trend_percent=7.0,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=60, sott_smooth_k=20, sott_percent=0.3,
    )

    print("=" * 60)
    print("ÇALIŞTIRMA 1: .docx orjinal parametreleri (intraday için)")
    print("=" * 60)
    for sym in SYMBOLS:
        run_one(sym, period="5y", interval="1d", **docx_params)

    print("\n")
    print("=" * 60)
    print("ÇALIŞTIRMA 2: günlük bar için yeniden ölçeklenmiş")
    print("=" * 60)
    for sym in SYMBOLS:
        run_one(sym, period="5y", interval="1d", **daily_params)


if __name__ == "__main__":
    main()
