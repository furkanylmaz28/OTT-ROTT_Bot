"""
Look-ahead-bias-free, event-driven minimal backtest motoru.

Sinyaller bar t'de hesaplanır → bar t+1'in açılışında işlem girer/çıkar.
Komisyon ve slippage parametrik. Long ve short ayrı yönetilir.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import pandas as pd


@dataclass
class Trade:
    side: str           # 'long' veya 'short'
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_pct: float = 0.0
    bars_held: int = 0


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: List[Trade]
    position: pd.Series  # +1 long, -1 short, 0 flat
    stats: dict = field(default_factory=dict)


def run_backtest(
    ohlc: pd.DataFrame,                # open, high, low, close columns
    cond_buy_long: pd.Series,
    cond_exit_long: pd.Series,
    cond_buy_short: pd.Series,
    cond_exit_short: pd.Series,
    initial_capital: float = 10_000.0,
    commission: float = 0.0002,        # tek taraflı (round-trip 4 bps default)
    slippage: float = 0.0001,          # her giriş/çıkışta açılış üzerine eklenir
    allow_short: bool = True,
) -> BacktestResult:
    """
    Bar t'deki koşul → bar t+1 open'da işlem. Pozisyon flat'tan girer veya tersine döner
    (long→short ve short→long doğrudan flip yapar — eski pozisyonu kapatıp yenisini açar).
    """
    o = ohlc["open"].to_numpy(dtype=float)
    idx = ohlc.index
    n = len(o)

    buy_l = cond_buy_long.reindex(idx).fillna(False).to_numpy(dtype=bool)
    exit_l = cond_exit_long.reindex(idx).fillna(False).to_numpy(dtype=bool)
    buy_s = cond_buy_short.reindex(idx).fillna(False).to_numpy(dtype=bool)
    exit_s = cond_exit_short.reindex(idx).fillna(False).to_numpy(dtype=bool)

    position = np.zeros(n, dtype=int)
    equity = np.full(n, initial_capital, dtype=float)
    trades: List[Trade] = []
    cur_pos = 0
    entry_price = 0.0
    entry_idx = -1
    cash = initial_capital
    units = 0.0  # pozisyon büyüklüğü (parçası fiyat * adet)

    for i in range(n):
        # Sinyal i-1'de oluşur, i bar'ının açılışında işle
        if i > 0:
            want_close_long = (cur_pos == 1) and exit_l[i - 1]
            want_close_short = (cur_pos == -1) and exit_s[i - 1]
            want_open_long = (cur_pos == 0) and buy_l[i - 1]
            want_open_short = allow_short and (cur_pos == 0) and buy_s[i - 1]
            want_flip_to_short = allow_short and (cur_pos == 1) and buy_s[i - 1]
            want_flip_to_long = (cur_pos == -1) and buy_l[i - 1]

            exec_price = o[i]

            # 1) Kapanış işlemleri
            if want_close_long or want_flip_to_short:
                fill = exec_price * (1 - slippage)
                pnl = units * (fill - entry_price) - units * fill * commission - units * entry_price * commission
                cash += units * entry_price + pnl  # geri al + kâr/zarar
                trades[-1].exit_time = idx[i]
                trades[-1].exit_price = fill
                trades[-1].pnl_pct = (fill - entry_price) / entry_price - 2 * commission
                trades[-1].bars_held = i - entry_idx
                cur_pos = 0
                units = 0.0

            elif want_close_short or want_flip_to_long:
                fill = exec_price * (1 + slippage)
                pnl = units * (entry_price - fill) - units * fill * commission - units * entry_price * commission
                cash += units * entry_price + pnl
                trades[-1].exit_time = idx[i]
                trades[-1].exit_price = fill
                trades[-1].pnl_pct = (entry_price - fill) / entry_price - 2 * commission
                trades[-1].bars_held = i - entry_idx
                cur_pos = 0
                units = 0.0

            # 2) Açılış işlemleri (flip durumunda da)
            if want_open_long or want_flip_to_long:
                fill = exec_price * (1 + slippage)
                units = cash / fill
                cash = 0.0
                entry_price = fill
                entry_idx = i
                cur_pos = 1
                trades.append(Trade(side="long", entry_time=idx[i], entry_price=fill))

            elif want_open_short or want_flip_to_short:
                fill = exec_price * (1 - slippage)
                units = cash / fill
                cash = 0.0
                entry_price = fill
                entry_idx = i
                cur_pos = -1
                trades.append(Trade(side="short", entry_time=idx[i], entry_price=fill))

        # mark-to-market equity
        if cur_pos == 1:
            equity[i] = units * ohlc["close"].iloc[i]
        elif cur_pos == -1:
            # short: entry value + (entry - current) * units
            equity[i] = units * entry_price + units * (entry_price - ohlc["close"].iloc[i])
        else:
            equity[i] = cash

        position[i] = cur_pos

    eq_series = pd.Series(equity, index=idx, name="equity")
    pos_series = pd.Series(position, index=idx, name="position")

    return BacktestResult(
        equity=eq_series,
        trades=trades,
        position=pos_series,
        stats=compute_stats(eq_series, trades, initial_capital),
    )


def compute_stats(equity: pd.Series, trades: List[Trade], initial: float) -> dict:
    closed = [t for t in trades if t.exit_price is not None]
    n_trades = len(closed)
    wins = [t for t in closed if t.pnl_pct > 0]
    losses = [t for t in closed if t.pnl_pct <= 0]

    total_return = (equity.iloc[-1] / initial) - 1
    daily_ret = equity.pct_change().fillna(0)
    sharpe = 0.0
    if daily_ret.std() > 0:
        sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252)

    cummax = equity.cummax()
    drawdown = equity / cummax - 1
    max_dd = drawdown.min()

    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0.0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0.0
    win_rate = len(wins) / n_trades if n_trades else 0.0
    profit_factor = (sum(t.pnl_pct for t in wins) / -sum(t.pnl_pct for t in losses)) if losses and sum(t.pnl_pct for t in losses) < 0 else float("inf")

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "final_equity": equity.iloc[-1],
    }


def print_stats(result: BacktestResult, symbol: str = "") -> None:
    s = result.stats
    print(f"\n── {symbol} ──")
    print(f"Toplam Getiri      : {s['total_return']*100:8.2f}%")
    print(f"Final Equity       : {s['final_equity']:10,.2f}")
    print(f"Sharpe (annualised): {s['sharpe']:8.2f}")
    print(f"Max Drawdown       : {s['max_drawdown']*100:8.2f}%")
    print(f"İşlem Sayısı       : {s['n_trades']:8d}")
    print(f"Kazanma Oranı      : {s['win_rate']*100:8.2f}%")
    print(f"Ort. Kazanç        : {s['avg_win']*100:8.2f}%")
    print(f"Ort. Kayıp         : {s['avg_loss']*100:8.2f}%")
    print(f"Profit Factor      : {s['profit_factor']:8.2f}")
