"""
Son 3 ay backtest — GBPUSD, EURGBP, GOLD üzerinde M5/M15/M60.
Warmup için son 6 ay yüklenir, sinyaller tüm 6 ayda hesaplanır,
istatistikler son 3 aylık dilimden çıkarılır.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


# .docx default parametreleri
DEFAULT = dict(
    trend_length=30, trend_percent=7.0,
    minor_percent=3.5,
    tott_percent=0.8, tott_coeff=0.0008,
    sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
    gate_length=20, gate_percent=0.5,
    rott_x1=30, rott_x2=1000, rott_percent=7.0,
)

# Optimize edilmiş (GOLD M15'te bulduğumuz)
OPTIMIZED = dict(
    trend_length=20, trend_percent=7.0,
    minor_percent=3.5,
    tott_percent=0.8, tott_coeff=0.0006,
    sott_period_k=300, sott_smooth_k=200, sott_percent=0.4,
    gate_length=20, gate_percent=0.5,
    rott_x1=30, rott_x2=1000, rott_percent=7.0,
)


def run_one(symbol: str, tf: int, params: dict, label: str):
    df_full = load_symbol("GCM-Demo", symbol, tf)
    cutoff_test = df_full.index[-1] - pd.Timedelta(days=90)
    cutoff_warmup = df_full.index[-1] - pd.Timedelta(days=180)
    df = df_full[df_full.index >= cutoff_warmup]
    if len(df) < 3000:
        print(f"  {symbol} M{tf:<4d}: az veri ({len(df)})")
        return None

    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )

    eq_slice = res.equity[res.equity.index >= cutoff_test]
    px_slice = df_full["close"][df_full.index >= cutoff_test]
    if len(eq_slice) < 2:
        return None
    period_ret = (eq_slice.iloc[-1] / eq_slice.iloc[0]) - 1
    bh = (px_slice.iloc[-1] / px_slice.iloc[0]) - 1
    cummax = eq_slice.cummax()
    dd = ((eq_slice / cummax) - 1).min()
    trades_in = [t for t in res.trades
                 if t.entry_time >= cutoff_test or
                 (t.exit_time is not None and t.exit_time >= cutoff_test)]
    closed = [t for t in trades_in if t.exit_price]
    wins = sum(1 for t in closed if t.pnl_pct > 0)
    losses = len(closed) - wins
    return {
        "symbol": symbol, "tf": tf, "label": label,
        "return": period_ret, "bh": bh, "dd": dd,
        "trades": len(trades_in), "closed": len(closed),
        "wins": wins, "losses": losses,
        "trades_list": trades_in,
    }


def fmt_row(r):
    if r is None:
        return ""
    return (f"  {r['symbol']:8s} M{r['tf']:<3d} {r['label']:9s} "
            f"{r['return']*100:+8.2f}%  BH={r['bh']*100:+7.2f}%  "
            f"DD={r['dd']*100:7.2f}%  trade={r['trades']:>3d}  "
            f"{r['wins']:>2d}/{r['losses']:<2d}")


def main():
    targets = [
        ("GOLD", 5), ("GOLD", 15), ("GOLD", 60),
        ("GBPUSD", 5), ("GBPUSD", 15), ("GBPUSD", 60),
        ("EURGBP", 5), ("EURGBP", 15), ("EURGBP", 60),
    ]

    print("══════ SON 3 AY — .docx DEFAULT PARAMETRELERİ ══════\n")
    rows_def = []
    for sym, tf in targets:
        r = run_one(sym, tf, DEFAULT, "default")
        if r:
            rows_def.append(r)
            print(fmt_row(r))

    print("\n══════ SON 3 AY — OPTIMIZE EDİLMİŞ PARAMETRELER (GOLD M15) ══════\n")
    rows_opt = []
    for sym, tf in targets:
        r = run_one(sym, tf, OPTIMIZED, "opt")
        if r:
            rows_opt.append(r)
            print(fmt_row(r))

    # GBPUSD M15 default ile trade detayları
    print("\n══════ DETAY: GBPUSD M15 default — son 3 ay trade listesi ══════\n")
    for r in rows_def:
        if r["symbol"] == "GBPUSD" and r["tf"] == 15:
            print(f"  {'Yön':<6} {'Giriş':<17} {'Giriş₣':<10} {'Çıkış':<17} {'Çıkış₣':<10} {'PnL %':<8}")
            for t in r["trades_list"]:
                exit_str = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "AÇIK"
                exit_p = f"{t.exit_price:.5f}" if t.exit_price else "-"
                pnl_str = f"{t.pnl_pct*100:+6.2f}%" if t.exit_time else "  AÇIK"
                print(f"  {t.side:<6} {t.entry_time.strftime('%Y-%m-%d %H:%M'):<17} "
                      f"{t.entry_price:<10.5f} {exit_str:<17} {exit_p:<10} {pnl_str:<8}")


if __name__ == "__main__":
    main()
