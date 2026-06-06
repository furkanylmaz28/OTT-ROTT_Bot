"""
Crypto'yu 4h'de yeniden optimize et (Grid + Bayes), mevcut JSON'lara MERGE et.
Formül değişmez — sadece timeframe 30dk → 4h.
"""
from __future__ import annotations
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import json, time

import per_symbol_optimize as pso
import bayesian_optimize as bo
from per_symbol_optimize import CRYPTO30

GRID_FILE = "per_symbol_params.json"
BAYES_FILE = "per_symbol_params_bayes.json"


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def main():
    grid = _load(GRID_FILE)
    bayes = _load(BAYES_FILE)
    n = len(CRYPTO30)
    print(f"Crypto 4h optimize — {n} coin (Grid + Bayes)\n")

    for i, sym in enumerate(CRYPTO30, 1):
        t0 = time.time()
        # ── Grid
        g_str = "✗"
        try:
            r = pso.optimize_symbol(sym)
            if r and r.get("ok"):
                grid[sym] = r
                s = r["stats"]; pf = s["pf"] if s["pf"] else 999
                g_str = f"{r['rating']:8s} {s['return']*100:+5.0f}% PF{pf:.1f} t{s['n_trades']}"
        except Exception as e:
            g_str = f"HATA {e}"
        # ── Bayes
        b_str = "✗"
        try:
            rb = bo.optimize_symbol(sym)
            if rb and rb.get("ok"):
                bayes[sym] = rb
                s = rb["stats"]; pf = s["pf"] if s["pf"] else 999
                b_str = f"{rb['rating']:8s} {s['return']*100:+5.0f}% PF{pf:.1f} t{s['n_trades']}"
        except Exception as e:
            b_str = f"HATA {e}"

        dt = time.time() - t0
        print(f"[{i:2d}/{n}] {sym:<10} GRID:{g_str:30s} | BAYES:{b_str:30s} ({dt:.0f}sn)")

        # ara kayıt + rate-limit nezaketi
        _save(GRID_FILE, grid)
        _save(BAYES_FILE, bayes)
        time.sleep(6)

    _save(GRID_FILE, grid)
    _save(BAYES_FILE, bayes)
    print(f"\n✅ Bitti — {GRID_FILE} + {BAYES_FILE} güncellendi (4h crypto).")


if __name__ == "__main__":
    main()
