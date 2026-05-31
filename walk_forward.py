"""
Walk-forward analizi — overfitting'i ölçer.

Yöntem (anchored walk-forward):
  1) Veriyi N+1 pencereye böl. İlk N pencere = train (in-sample = IS).
  2) Train üzerinde grid search → en iyi parametre.
  3) O parametreyle bir sonraki pencerede test (out-of-sample = OOS).
  4) Pencere kayar.

Train uzunluğu: 8 ay (~22000 M15 bar)
Test uzunluğu : 2 ay  (~5500 M15 bar)
Step          : 2 ay

Her OOS pencerede getiri, DD, trade sayısı kaydedilir.
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import time
from itertools import product
import numpy as np
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from mt4_hst import load_symbol


GRID = list(product(
    [20, 30],                          # opt1
    [0.6, 0.8],                        # opt2
    [0.0004, 0.0006, 0.0008],          # opt3
    [200, 300],                        # opt4
    [0.2, 0.3, 0.4],                   # opt6
))


def score(stats: dict) -> float:
    n = stats["n_trades"]
    if n < 3:
        return -1e9
    pf = stats["profit_factor"]
    if not np.isfinite(pf):
        pf = 5.0
    dd = abs(stats["max_drawdown"])
    ret = stats["total_return"]
    if ret <= 0:
        return -1e9
    return pf * np.sqrt(n) / (1 + dd) * (1 + min(ret, 5))


def eval_params(df: pd.DataFrame, p: tuple):
    o1, o2, o3, o4, o6 = p
    s = sig_full.build_signals_full(
        df["close"], df["high"], df["low"],
        trend_length=o1, trend_percent=7.0,
        minor_percent=3.5,
        tott_percent=o2, tott_coeff=o3,
        sott_period_k=o4, sott_smooth_k=200, sott_percent=o6,
        gate_length=20, gate_percent=0.5,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )
    return run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )


def walk_forward(symbol: str, tf: int,
                 train_months: int = 8, test_months: int = 2, step_months: int = 2):
    df_full = load_symbol("GCM-Demo", symbol, tf)
    print(f"{symbol} M{tf}: {len(df_full)} bar  "
          f"({df_full.index[0].date()} → {df_full.index[-1].date()})")

    start = df_full.index[0] + pd.DateOffset(months=train_months)
    end_data = df_full.index[-1]
    test_starts = []
    cur = start
    while cur + pd.DateOffset(months=test_months) <= end_data:
        test_starts.append(cur)
        cur = cur + pd.DateOffset(months=step_months)

    print(f"Walk-forward: {len(test_starts)} pencere, "
          f"train={train_months}ay, test={test_months}ay, step={step_months}ay\n")

    records = []
    t0 = time.time()
    for wi, t_start in enumerate(test_starts):
        train_start = t_start - pd.DateOffset(months=train_months)
        train_end = t_start
        test_end = t_start + pd.DateOffset(months=test_months)

        # IS: ilk bar'dan train_end'e kadar (anchored — büyüyen pencere yerine sabit train)
        # Sabit pencere kullanıyorum (rolling, daha temiz)
        df_train = df_full[(df_full.index >= train_start) & (df_full.index < train_end)]
        df_test = df_full[(df_full.index >= t_start) & (df_full.index < test_end)]

        if len(df_train) < 2000 or len(df_test) < 500:
            continue

        # IS optimizasyon — grid'in en iyisini bul
        best_p = None
        best_score = -1e9
        best_is = None
        for p in GRID:
            r = eval_params(df_train, p)
            sc = score(r.stats)
            if sc > best_score:
                best_score = sc
                best_p = p
                best_is = r.stats

        # OOS test — train indikatörleri kullanmadan, sadece test diliminde
        # Önemli: warmup için biraz öncesini dahil edelim
        warmup_start = t_start - pd.DateOffset(months=2)  # warmup
        df_test_with_warmup = df_full[(df_full.index >= warmup_start) &
                                       (df_full.index < test_end)]
        r_oos_all = eval_params(df_test_with_warmup, best_p)
        # OOS dilimini ayıkla
        eq_oos = r_oos_all.equity[r_oos_all.equity.index >= t_start]
        if len(eq_oos) < 2:
            continue
        oos_ret = (eq_oos.iloc[-1] / eq_oos.iloc[0]) - 1
        cummax = eq_oos.cummax()
        oos_dd = ((eq_oos / cummax) - 1).min()
        oos_trades = [t for t in r_oos_all.trades
                      if t.entry_time >= t_start and t.entry_time < test_end]
        oos_wins = sum(1 for t in oos_trades if t.exit_price and t.pnl_pct > 0)

        bh = (df_test["close"].iloc[-1] / df_test["close"].iloc[0]) - 1

        records.append({
            "win": wi + 1,
            "train": f"{train_start.date()} → {train_end.date()}",
            "test": f"{t_start.date()} → {test_end.date()}",
            "best_p": best_p,
            "is_return": best_is["total_return"],
            "is_pf": best_is["profit_factor"],
            "is_dd": best_is["max_drawdown"],
            "oos_return": oos_ret,
            "oos_dd": oos_dd,
            "oos_trades": len(oos_trades),
            "oos_wins": oos_wins,
            "bh_return": bh,
        })

        elapsed = time.time() - t0
        eta = elapsed / (wi + 1) * (len(test_starts) - wi - 1)
        print(f"[{wi+1:2d}/{len(test_starts)}]  test={t_start.date()}→{test_end.date()}  "
              f"best_p={best_p}  IS={best_is['total_return']*100:+6.1f}%  "
              f"OOS={oos_ret*100:+6.1f}%  BH={bh*100:+6.1f}%  "
              f"trade={len(oos_trades)}  ETA={eta:.0f}s")

    return pd.DataFrame(records)


def summarize(df_wf: pd.DataFrame, symbol: str, tf: int):
    print(f"\n══════ {symbol} M{tf} WALK-FORWARD ÖZET ══════")
    n = len(df_wf)
    if n == 0:
        print("Yeterli pencere yok.")
        return

    avg_is = df_wf["is_return"].mean()
    avg_oos = df_wf["oos_return"].mean()
    sum_oos = (1 + df_wf["oos_return"]).prod() - 1   # bileşik OOS getirisi
    sum_bh = (1 + df_wf["bh_return"]).prod() - 1
    wf_efficiency = avg_oos / avg_is if avg_is > 0 else 0
    oos_pos = (df_wf["oos_return"] > 0).sum()
    avg_oos_dd = df_wf["oos_dd"].mean()
    worst_oos = df_wf["oos_return"].min()
    best_oos = df_wf["oos_return"].max()

    print(f"Pencere sayısı       : {n}")
    print(f"Ort. IS getirisi     : {avg_is*100:+8.2f}%   (her pencere)")
    print(f"Ort. OOS getirisi    : {avg_oos*100:+8.2f}%   (her pencere)")
    print(f"WF Verimliliği       : {wf_efficiency*100:8.1f}%   (OOS / IS — %50 üzeri makul)")
    print(f"Toplam OOS bileşik   : {sum_oos*100:+8.2f}%")
    print(f"Toplam Buy & Hold    : {sum_bh*100:+8.2f}%")
    print(f"Pozitif OOS pencere  : {oos_pos}/{n}  ({oos_pos/n*100:.0f}%)")
    print(f"Ort. OOS Max DD      : {avg_oos_dd*100:8.2f}%")
    print(f"En iyi / En kötü OOS : {best_oos*100:+.2f}%  /  {worst_oos*100:+.2f}%")


def main():
    for sym, tf in [("GOLD", 15)]:
        df_wf = walk_forward(sym, tf, train_months=8, test_months=2, step_months=2)
        summarize(df_wf, sym, tf)
        df_wf.to_csv(f"walk_forward_{sym}_M{tf}.csv", index=False)
        print(f"Kaydedildi: walk_forward_{sym}_M{tf}.csv")


if __name__ == "__main__":
    main()
