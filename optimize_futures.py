"""
optimize_futures.py — BIST VIOP FUTURES verisiyle sembol-bazlı optimize.

per_symbol_optimize.py ile AYNI 3 aşamalı yöntem (trend → bölge → kapı) ve aynı
signals_full, ama veri kaynağı SPOT yerine FUTURES (SEMBOL1!). Kullanıcı VIOP
futures işlemi yaptığı için parametreler de futures'a optimize edilir.

Çıktı: per_symbol_params_futures.json (bot + dashboard buna geçecek).
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import json, time
from itertools import product
import numpy as np

from per_symbol_optimize import BIST30, score, rating, evaluate
from data_source import fetch_futures, best_interval_for, category_of


def optimize_symbol_fut(symbol):
    df = fetch_futures(symbol, best_interval_for(symbol), 5000)
    if df is None or df.empty or len(df) < 2000:
        return None
    df = df[["open", "high", "low", "close"]].dropna()

    base = dict(
        trend_length=30, trend_percent=7.0, minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5, gate_shift=0,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )
    # Aşama 1 — Trend
    best, best_sc = base.copy(), -1e9
    for tl, tp, mp in product([20, 30, 35], [5.0, 7.0, 8.0], [3.0, 3.5, 4.0]):
        p = {**base, "trend_length": tl, "trend_percent": tp, "minor_percent": mp}
        sc = score(evaluate(df, p))
        if sc > best_sc:
            best_sc, best = sc, p.copy()
    if best_sc <= -1e9:
        return {"symbol": symbol, "ok": False, "reason": "n_trades yetersiz"}
    base = best
    # Aşama 2 — Bölge
    best_sc = -1e9
    for tp, tc, pk, sp in product([0.6, 0.8, 1.0], [0.0004, 0.0006, 0.0008],
                                   [200, 300, 500], [0.2, 0.3, 0.4]):
        p = {**base, "tott_percent": tp, "tott_coeff": tc, "sott_period_k": pk, "sott_percent": sp}
        sc = score(evaluate(df, p))
        if sc > best_sc:
            best_sc, best = sc, p.copy()
    base = best
    # Aşama 3 — Kapı
    best_sc = -1e9
    for gl, gp, gs in product([10, 16, 22, 28], [0.4, 0.5, 0.6], [0, 2]):
        p = {**base, "gate_length": gl, "gate_percent": gp, "gate_shift": gs}
        sc = score(evaluate(df, p))
        if sc > best_sc:
            best_sc, best = sc, p.copy()

    final = evaluate(df, best)
    return {
        "symbol": symbol, "ok": True, "bars": len(df),
        "rating": rating(final),
        "interval": best_interval_for(symbol),
        "category": "BIST_FUTURES",
        "params": best,
        "stats": {
            "return": final["total_return"],
            "pf": final["profit_factor"] if np.isfinite(final["profit_factor"]) else None,
            "sharpe": final["sharpe"], "max_dd": final["max_drawdown"],
            "n_trades": final["n_trades"], "win_rate": final["win_rate"],
            "avg_trade_bars": final.get("avg_trade_bars", 0),
        },
    }


def main():
    syms = BIST30   # sadece BIST (VIOP futures)
    print(f"FUTURES optimize — {len(syms)} BIST sembolü (1h). Tahmini ~{len(syms)*20/60:.0f} dk\n")
    out = {}; t0 = time.time()
    for i, sym in enumerate(syms, 1):
        ts = time.time()
        try:
            r = optimize_symbol_fut(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)}
        dt = time.time() - ts
        if r and r.get("ok"):
            out[sym] = r; s = r["stats"]
            pf = f"{s['pf']:.2f}" if s["pf"] else "∞"
            print(f"[{i:2d}/{len(syms)}] {sym:<10} {r['rating']:<10} "
                  f"ret={s['return']*100:+7.1f}% PF={pf:>5} DD={s['max_dd']*100:+6.1f}% "
                  f"n={s['n_trades']:3d} win={s['win_rate']*100:.0f}% ({dt:.0f}sn)")
        else:
            print(f"[{i:2d}/{len(syms)}] {sym:<10} ATLANDI ({r.get('reason','veri yok') if r else 'veri yok'})")
        json.dump(out, open("per_symbol_params_futures.json", "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
    from collections import Counter
    rc = Counter(v["rating"] for v in out.values())
    print(f"\nTamam ({time.time()-t0:.0f}sn). {len(out)} sembol. Rating: {dict(rc)}")
    print("Kaydedildi: per_symbol_params_futures.json")


if __name__ == "__main__":
    main()
