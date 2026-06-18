"""
optimize_bayes_futures.py — Bayes (optuna/TPE) optimize, FUTURES verisiyle.

bayesian_optimize.py ile AYNI objective/skor ve arama uzayı, ama veri SPOT yerine
FUTURES (SEMBOL1!). Sadece BIST. Çıktı: per_symbol_params_bayes.json (futures).
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import json, time
import optuna
import numpy as np

from bayesian_optimize import objective, evaluate, MIN_BARS
from per_symbol_optimize import BIST30, rating
from data_source import fetch_futures, best_interval_for

optuna.logging.set_verbosity(optuna.logging.WARNING)
N_TRIALS = 150
TIMEOUT = 150


def optimize_symbol_fut(sym):
    df = fetch_futures(sym, best_interval_for(sym), 5000)
    if df is None or df.empty or len(df) < MIN_BARS:
        return None
    df = df[["open", "high", "low", "close"]].dropna()
    sampler = optuna.samplers.TPESampler(seed=42, n_startup_trials=20)
    study = optuna.create_study(direction="maximize", sampler=sampler,
                                 pruner=optuna.pruners.MedianPruner(n_warmup_steps=30))
    study.optimize(lambda t: objective(t, df), n_trials=N_TRIALS, timeout=TIMEOUT,
                   show_progress_bar=False, catch=(Exception,))
    if not study.best_trial or study.best_value < 0:
        return {"symbol": sym, "ok": False, "reason": "kötü skor"}
    bp = dict(study.best_params)
    if "gate_shift" in bp:
        bp["gate_shift"] = int(bp["gate_shift"])
    fs = evaluate(df, bp)
    return {
        "symbol": sym, "ok": True, "bars": len(df),
        "rating": rating(fs), "interval": best_interval_for(sym),
        "category": "BIST_FUTURES", "params": bp,
        "n_trials": len(study.trials), "best_score": study.best_value,
        "stats": {
            "return": fs["total_return"],
            "pf": fs["profit_factor"] if np.isfinite(fs["profit_factor"]) else None,
            "sharpe": fs["sharpe"], "max_dd": fs["max_drawdown"],
            "n_trades": fs["n_trades"], "win_rate": fs["win_rate"],
        },
    }


def main():
    print(f"Bayes FUTURES optimize — {len(BIST30)} BIST × {N_TRIALS} trial\n")
    out = {}; t0 = time.time()
    for i, sym in enumerate(BIST30, 1):
        ts = time.time()
        try:
            r = optimize_symbol_fut(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)[:80]}
        dt = time.time() - ts
        if r and r.get("ok"):
            out[sym] = r; s = r["stats"]
            pf = f"{s['pf']:.2f}" if s["pf"] else "∞"
            print(f"[{i:2d}/{len(BIST30)}] {sym:<10} {r['rating']:<10} "
                  f"ret={s['return']*100:+7.1f}% PF={pf:>5} n={s['n_trades']:3d} "
                  f"win={s['win_rate']*100:.0f}% ({dt:.0f}sn)")
        else:
            print(f"[{i:2d}/{len(BIST30)}] {sym:<10} ATLANDI ({r.get('reason','veri') if r else 'veri'})")
        json.dump(out, open("per_symbol_params_bayes.json", "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
    from collections import Counter
    rc = Counter(v["rating"] for v in out.values())
    print(f"\nTamam ({time.time()-t0:.0f}sn). {len(out)} sembol. Rating: {dict(rc)}")


if __name__ == "__main__":
    main()
