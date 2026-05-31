"""
Sadece CRYPTO sembollerini optimize et ve mevcut per_symbol_params.json'a ekle.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import json, time
from per_symbol_optimize import CRYPTO30, optimize_symbol


def main():
    # Mevcut params'ı yükle
    try:
        with open("per_symbol_params.json") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    new_count = 0
    print(f"Crypto sembol sayısı: {len(CRYPTO30)}")
    print(f"Tahmini süre: {len(CRYPTO30) * 15 / 60:.0f} dakika\n")

    t0 = time.time()
    for i, sym in enumerate(CRYPTO30, 1):
        ts = time.time()
        try:
            r = optimize_symbol(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)}
        dt = time.time() - ts

        if r and r.get("ok"):
            s = r["stats"]
            rt = r.get("rating", "?")
            data[sym] = r
            new_count += 1
            pf_str = f"{s['pf']:.2f}" if s['pf'] else "∞"
            print(f"[{i:2d}/{len(CRYPTO30)}] {sym:<12} {rt:<10} "
                  f"ret={s['return']*100:+7.1f}% PF={pf_str:>5} "
                  f"DD={s['max_dd']*100:+6.1f}% n={s['n_trades']:3d}  ({dt:.0f}sn)")
        else:
            reason = r["reason"] if r else "veri yok"
            print(f"[{i:2d}/{len(CRYPTO30)}] {sym:<12} ✗ {reason}  ({dt:.0f}sn)")

        # Ara kayıt
        if i % 5 == 0:
            with open("per_symbol_params.json", "w") as f:
                json.dump(data, f, indent=2, default=str)

    with open("per_symbol_params.json", "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\n  Süre: {(time.time()-t0)/60:.1f} dakika")
    print(f"  Eklendi: {new_count}/{len(CRYPTO30)}")


if __name__ == "__main__":
    main()
