"""
optimize_molds.py — ADIM 2: her sembole 500/200 KALIBI ata (serbest optimize yerine).

İlerleyen Algo Trading yöntemi: serbest grid (overfit) yerine frekans-eşli az sayıda
kalıbı dene, sembolün tercih ettiği kalıbı (500 dengeli / 200 dengesiz) ata.
Az parametre = az overfit.

ÇIKTI: per_symbol_params_mold.json (MEVCUT dosyaları BOZMAZ — kıyas için ayrı).
"""
from __future__ import annotations
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
from dotenv import load_dotenv; load_dotenv(".env")

import json, time
import numpy as np
import signals_full as sig_full
from backtest import run_backtest
from data_source import fetch as ds_fetch, best_interval_for, category_of
import equivalence as eq
from per_symbol_optimize import rating, BIST30, CRYPTO30, EMTIA_FX


def evaluate(df, p):
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **p)
    res = run_backtest(df[["open","high","low","close"]],
                       s["cond_buy_long"], s["cond_exit_long"],
                       s["cond_buy_short"], s["cond_exit_short"])
    return res.stats


def score(st, min_trades=3):
    n = st["n_trades"]; pf = st["profit_factor"]; dd = abs(st["max_drawdown"]); ret = st["total_return"]
    if n < min_trades: return -1e9
    if not np.isfinite(pf): pf = 5.0
    if ret <= 0: return ret / (1 + dd)
    return ret * max(pf, 0.5) / (1 + dd)


def optimize_symbol_mold(symbol):
    df = ds_fetch(symbol, interval=best_interval_for(symbol), n_bars=5000)
    if df.empty or len(df) < 2000:
        return None
    df = df[["open","high","low","close"]].dropna()

    molds = eq.all_molds()
    best, bsc, best_st = None, -1e9, None
    for c in molds:
        try:
            st = evaluate(df, c["params"])
        except Exception:
            continue
        sc = score(st)
        if sc > bsc:
            bsc, best, best_st = sc, c, st
    if best is None:
        return {"symbol": symbol, "ok": False, "reason": "min trade < 3 her kalıpta"}

    rt = rating(best_st)
    return {
        "symbol": symbol, "ok": True, "bars": len(df),
        "rating": rt,
        "kalip": best["kalip"], "mold": best["mold"],
        "interval": best_interval_for(symbol),
        "category": category_of(symbol),
        "params": best["params"],
        "stats": {
            "return": best_st["total_return"],
            "pf": best_st["profit_factor"] if np.isfinite(best_st["profit_factor"]) else None,
            "sharpe": best_st["sharpe"],
            "max_dd": best_st["max_drawdown"],
            "n_trades": best_st["n_trades"],
            "win_rate": best_st["win_rate"],
        },
    }


def main():
    syms = BIST30 + CRYPTO30 + EMTIA_FX
    print(f"Kalıp-optimize: {len(syms)} sembol (BIST+CRYPTO+EMTIA), kalıp başına 12 eşli kombinasyon\n")
    out = {}
    t0 = time.time()
    from collections import Counter
    kc = Counter()
    for i, sym in enumerate(syms, 1):
        try:
            r = optimize_symbol_mold(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)}
        if r and r.get("ok"):
            out[sym] = r
            s = r["stats"]; pf = s["pf"] if s["pf"] else 999
            kc[r["kalip"]] += 1
            print(f"[{i:2d}/{len(syms)}] {sym:11s} {r['rating']:9s} {r['kalip']:3s}/{r['mold']:8s} "
                  f"ret={s['return']*100:+6.0f}% PF={pf:4.1f} n={s['n_trades']:3d}")
        else:
            print(f"[{i:2d}/{len(syms)}] {sym:11s} ✗ {r.get('reason','?') if r else 'veri yok'}")
        if i % 10 == 0:
            json.dump(out, open("per_symbol_params_mold.json","w",encoding="utf-8"),
                      indent=2, ensure_ascii=False, default=str)
    json.dump(out, open("per_symbol_params_mold.json","w",encoding="utf-8"),
              indent=2, ensure_ascii=False, default=str)
    print(f"\nBitti ({(time.time()-t0)/60:.1f}dk). Başarılı: {len(out)}/{len(syms)}")
    print(f"Kalıp dağılımı: {dict(kc)}")


if __name__ == "__main__":
    main()
