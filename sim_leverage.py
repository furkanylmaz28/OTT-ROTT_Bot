"""
KALDIRAÇLI SİMÜLASYON — son 30 günde gerçek sinyalleri farklı kaldıraçlarla
çalıştırınca hesap ne yaşardı?

Yöntem:
   her trade için PnL yüzde olarak ele alınır
   leveraged_pnl = pnl × leverage
   equity *= (1 + leveraged_pnl)
   eğer leveraged_pnl <= -1.0 olursa MARGIN CALL → hesap sıfır

Sermaye başlangıç: 10,000 (örnek, oran değişmez)

GCM'in tipik kaldıraç oranları:
   XAU/USD (GOLD)  : 1:50  (margin %2)
   EUR/USD          : 1:100 (margin %1)
   GBP/USD          : 1:50  (margin %2)
   Endeks CFD'leri  : 1:20-50

Sembol her ne ise, kullanıcı broker'ında ne lot büyüklüğü kullanacaksa
oraya göre değerlendirmek lazım. Burada ham PnL × leverage simülasyonu.
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


def simulate_leverage(trades_pnl: list, leverages: list, initial: float = 10000):
    """Trade'lerin PnL'leriyle her leverage için final equity hesapla."""
    results = {}
    for lev in leverages:
        eq = initial
        margin_call = False
        peak = initial
        max_dd = 0
        for pnl in trades_pnl:
            lev_pnl = pnl * lev
            if lev_pnl <= -1.0:
                eq = 0
                margin_call = True
                break
            eq *= (1 + lev_pnl)
            if eq > peak: peak = eq
            dd = (eq / peak - 1)
            if dd < max_dd: max_dd = dd
        results[lev] = {
            "final": eq, "return_pct": (eq/initial - 1)*100,
            "margin_call": margin_call, "max_dd": max_dd*100,
        }
    return results


def run_symbol(server: str, symbol: str, tf: int, params: dict, days: int = 30,
                label: str = ""):
    df = load_symbol(server, symbol, tf)
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    cutoff = df.index[-1] - pd.Timedelta(days=days)
    trades_in = [t for t in res.trades
                 if (t.entry_time >= cutoff and t.exit_price is not None)]
    pnls = [t.pnl_pct for t in trades_in]

    leverages = [1, 5, 10, 25, 50, 100]
    sim = simulate_leverage(pnls, leverages)

    print(f"\n══════ {label or f'{symbol} M{tf}'} — Son {days} gün ══════")
    print(f"  Kapanmış trade sayısı : {len(trades_in)}")
    print(f"  Trade-by-trade PnL    : {[f'{p*100:+.2f}%' for p in pnls]}")
    sum_pnl = sum(pnls) * 100
    print(f"  Trade'lerin toplamı   : {sum_pnl:+.2f}%")
    print(f"\n  {'Kaldıraç':>10} | {'Final':>10} | {'Getiri':>10} | {'Max DD':>9} | Durum")
    print(f"  {'-'*65}")
    for lev in leverages:
        s = sim[lev]
        status = "MARGIN CALL ✗" if s["margin_call"] else "OK"
        print(f"  {f'1:{lev}':>10} | {s['final']:>10,.0f} | "
              f"{s['return_pct']:+10.2f}% | {s['max_dd']:8.2f}% | {status}")


def main():
    with open("gold_optimum_params.json") as f:
        opt = json.load(f)

    # GCM-Demo'da indirilen semboller — backtest'te denenmiş
    targets = [
        ("GOLD", 15, opt["GOLD_M15"]["params"], "GOLD M15 (sistemin uzmanı)"),
        ("GOLD", 5,  opt["GOLD_M5"]["params"],  "GOLD M5"),
        # Forex pariteler aynı GOLD parametreleriyle (uygun değil ama referans için)
        ("GBPUSD", 15, opt["GOLD_M15"]["params"], "GBPUSD M15 (UYUMSUZ)"),
        ("EURGBP", 15, opt["GOLD_M15"]["params"], "EURGBP M15 (UYUMSUZ)"),
    ]

    for sym, tf, params, label in targets:
        params.setdefault("rott_x1", 30)
        params.setdefault("rott_x2", 1000)
        params.setdefault("rott_percent", 7.0)
        run_symbol("GCM-Demo", sym, tf, params, days=30, label=label)


if __name__ == "__main__":
    main()
