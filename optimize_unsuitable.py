"""
UYUMSUZ sembolleri GENİŞLETİLMİŞ grid ile yeniden optimize et.

Standart sıralı optimize'da bulduğumuz "en iyi" bile negatif kalan sembollere
daha geniş parametre uzayı uygula. Belki bazıları kurtarılabilir.

Strateji: standart 3 aşama (trend → bölge → kapı) AMA aralıklar geniş.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import json, time
from itertools import product
import numpy as np
import pandas as pd
import yfinance as yf

import signals_full as sig_full
from backtest import run_backtest
from per_symbol_optimize import score, rating, evaluate, fetch


def optimize_wider(symbol: str):
    df = fetch(symbol)
    if df.empty or len(df) < 2000:
        return None

    base = dict(
        trend_length=30, trend_percent=7.0, minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5, gate_shift=0,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )

    # AŞAMA 1 — TREND (geniş)  — 7×5×4 = 140 kombinasyon
    best, best_sc = base.copy(), -1e9
    for tl, tp, mp in product(
        [15, 20, 25, 30, 40, 50, 60],          # trend_length
        [4.0, 6.0, 8.0, 10.0, 12.0],           # trend_percent
        [2.5, 3.5, 4.5, 5.5],                  # minor_percent
    ):
        p = {**base, "trend_length": tl, "trend_percent": tp, "minor_percent": mp}
        st = evaluate(df, p); sc = score(st)
        if sc > best_sc: best_sc, best = sc, p.copy()
    if best_sc <= -1e9:
        return {"symbol": symbol, "ok": False, "reason": "n_trades < 3 her durumda"}
    base = best

    # AŞAMA 2 — BÖLGE (geniş)  — 5×4×5×4 = 400 kombinasyon (sott_smooth tek değer)
    best_sc = -1e9
    for tp, tc, pk, sp in product(
        [0.4, 0.6, 0.8, 1.0, 1.2],                          # tott_percent
        [0.0002, 0.0006, 0.001, 0.002],                     # tott_coeff
        [100, 200, 300, 400, 500],                          # sott_period_k
        [0.1, 0.2, 0.3, 0.4],                               # sott_percent
    ):
        p = {**base, "tott_percent": tp, "tott_coeff": tc,
             "sott_period_k": pk, "sott_percent": sp}
        st = evaluate(df, p); sc = score(st)
        if sc > best_sc: best_sc, best = sc, p.copy()
    base = best

    # AŞAMA 3 — KAPI (geniş)  — 5×3×2 = 30 kombinasyon
    best_sc = -1e9
    for gl, gp, gs in product(
        [8, 14, 20, 26, 32],
        [0.3, 0.5, 0.7],
        [0, 2],
    ):
        p = {**base, "gate_length": gl, "gate_percent": gp, "gate_shift": gs}
        st = evaluate(df, p); sc = score(st)
        if sc > best_sc: best_sc, best = sc, p.copy()

    final = evaluate(df, best)
    rt = rating(final)
    return {
        "symbol": symbol, "ok": True, "bars": len(df),
        "rating": rt,
        "params": best,
        "stats": {
            "return": final["total_return"],
            "pf": final["profit_factor"] if np.isfinite(final["profit_factor"]) else None,
            "sharpe": final["sharpe"],
            "max_dd": final["max_drawdown"],
            "n_trades": final["n_trades"],
            "win_rate": final["win_rate"],
        },
    }


def main():
    # UYUMSUZ olanları bul
    with open("per_symbol_params.json") as f:
        data = json.load(f)
    unsuitable = [s for s, r in data.items()
                  if r.get("ok") and r.get("rating") == "UYUMSUZ"]
    print(f"UYUMSUZ sembol sayısı: {len(unsuitable)}")
    print(f"Geniş grid (~570 kombinasyon/sembol) ile yeniden optimize...")
    print(f"Tahmini süre: {len(unsuitable) * 90 / 60:.0f} dakika\n")

    improved = 0
    t0 = time.time()
    for i, sym in enumerate(unsuitable, 1):
        ts = time.time()
        old = data[sym]["stats"]
        try:
            r = optimize_wider(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)}
        dt = time.time() - ts

        if not r.get("ok"):
            print(f"[{i:2d}/{len(unsuitable)}] {sym:<10} ✗ {r.get('reason','?')}  ({dt:.0f}sn)")
            continue

        new = r["stats"]
        new_rt = r["rating"]
        old_ret = old["return"] * 100
        new_ret = new["return"] * 100
        delta = new_ret - old_ret
        improved_mark = " ★ İYİLEŞTİ" if new_rt != "UYUMSUZ" else ""
        if new_rt != "UYUMSUZ":
            improved += 1
        print(f"[{i:2d}/{len(unsuitable)}] {sym:<10} eski={old_ret:+5.1f}% → "
              f"yeni={new_ret:+5.1f}% ({delta:+5.1f}) {new_rt:<10}{improved_mark}  ({dt:.0f}sn)")

        # Güncelle (eğer yeni daha iyiyse veya en azından farklı değilse)
        if new_ret > old_ret:
            data[sym] = r

        # Ara kayıt
        if i % 5 == 0:
            with open("per_symbol_params.json", "w") as f:
                json.dump(data, f, indent=2, default=str)

    with open("per_symbol_params.json", "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\n  Toplam süre: {(time.time()-t0)/60:.1f} dakika")
    print(f"  Kurtarılan sembol: {improved}/{len(unsuitable)}")
    print(f"  Sonuçlar per_symbol_params.json içinde güncel.")


if __name__ == "__main__":
    main()
