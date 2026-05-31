"""
GOLD'un tüm timeframe'lerinde sequential optimize.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings("ignore")

import json
from sequential_optimize import sequential_optimize


def main():
    results = {}
    for tf in [5, 15, 30, 60]:
        try:
            best, final, t1, t2, t3 = sequential_optimize("GOLD", tf)
            results[f"GOLD_M{tf}"] = {
                "params": best,
                "stats": {
                    "return": final["total_return"],
                    "pf": final["profit_factor"],
                    "sharpe": final["sharpe"],
                    "max_dd": final["max_drawdown"],
                    "n_trades": final["n_trades"],
                    "win_rate": final["win_rate"],
                }
            }
            t1.to_csv(f"seqopt_GOLD_M{tf}_T1.csv", index=False)
            t2.to_csv(f"seqopt_GOLD_M{tf}_T2.csv", index=False)
            t3.to_csv(f"seqopt_GOLD_M{tf}_T3.csv", index=False)
        except Exception as e:
            print(f"GOLD M{tf} HATA: {e}")

    with open("gold_optimum_params.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "═" * 70)
    print("  GOLD TÜM TF ÖZET")
    print("═" * 70)
    for key, v in results.items():
        s = v["stats"]
        print(f"\n{key}:")
        print(f"  return={s['return']*100:+7.2f}% PF={s['pf']:.2f} "
              f"DD={s['max_dd']*100:+.2f}% trades={s['n_trades']} "
              f"win={s['win_rate']*100:.1f}% sharpe={s['sharpe']:.2f}")
        print(f"  params={v['params']}")


if __name__ == "__main__":
    main()
