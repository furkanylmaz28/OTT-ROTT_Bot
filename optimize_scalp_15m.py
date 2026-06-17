"""
optimize_scalp_15m.py — 15m "Aktif/Scalp" modu için sembol-bazlı optimize.

OTT+TOTT sıralı teyit (ott_tott_confirm.compute) ile, KISA parametrelerle yüksek
frekanslı sinyal arar. Overfit'e karşı TRAIN/TEST ayrımı:
  - Parametre, verinin ilk %70'inde (train) optimize edilir.
  - Son %30 (test = out-of-sample) ile DOĞRULANIR.
  - Sadece OOS'ta edge'i tutan semboller "İYİ" sayılır → sekmeye o girer.

Maliyet: tek yön %0.05 (kullanıcı GCM VIOP komisyonu) → round-trip ~%0.05 düşülür.
Çıktı: per_symbol_scalp_15m.json
"""
from __future__ import annotations
import sys, json, re, warnings
warnings.filterwarnings("ignore")
from dotenv import load_dotenv; load_dotenv(".env")
import numpy as np, pandas as pd
import ott_tott_confirm as otc
from data_source import fetch_futures

COST = 0.0005   # tek yön %0.05 (giriş+çıkış round-trip'te bir kez düşülür ~yaklaşım)

# Kısa/hızlı parametre gridi (scalp)
LENGTHS = [8, 10, 12, 15, 20]
PERCENTS = [0.5, 1.0, 1.5, 2.0]
COEFFS = [0.001, 0.005, 0.01]


def _bt(close_open: pd.DataFrame, length, pct, coeff):
    """OTT+TOTT sıralı confirm → LONG/SHORT flip backtest. Trade getiri listesi döner."""
    r = otc.compute(close_open["close"], length, pct, coeff)
    sig = r["confirm"]; o = close_open["open"].values
    tr = []; pos = 0; entry = 0.0
    n = len(o)
    for i in range(n):
        s = sig.iloc[i]
        if pd.isna(s) or i + 1 >= n:
            continue
        px = o[i + 1]                       # sinyal bar'ında hesap → sonraki bar açılışı
        if pos != 0 and ((s == "LONG" and pos < 0) or (s == "SHORT" and pos > 0)):
            ret = (px / entry - 1) if pos > 0 else (entry / px - 1)
            tr.append(ret - COST); pos = 0
        if pos == 0:
            pos = 1 if s == "LONG" else -1; entry = px
    return tr


def _pf(tr):
    if not tr:
        return 0.0
    w = sum(x for x in tr if x > 0); l = abs(sum(x for x in tr if x <= 0))
    return (w / l) if l > 0 else 9.0


def _bist_list():
    src = open("app.py", encoding="utf-8").read()
    return re.findall(r'"([^"]+)"', re.search(r'^BIST = \[(.*?)\]', src, re.S | re.M).group(1))


def optimize_symbol(sym):
    d = fetch_futures(sym, "15m", 5000)
    if d is None or d.empty or len(d) < 600:
        return None
    d = d[["open", "high", "low", "close"]].dropna()
    split = int(len(d) * 0.70)
    train, test = d.iloc[:split], d.iloc[split:]
    best = None
    for L in LENGTHS:
        for p in PERCENTS:
            for c in COEFFS:
                tr = _bt(train, L, p, c)
                if len(tr) < 15:               # train'de yeterli işlem yoksa atla
                    continue
                pf = _pf(tr)
                tot = sum(tr)
                # train skoru: PF ağırlıklı, toplam getiriyle desteklenmiş
                score = pf + tot
                if best is None or score > best["score"]:
                    best = {"L": L, "p": p, "c": c, "score": score,
                            "train_pf": round(pf, 2), "train_n": len(tr)}
    if best is None:
        return None
    # OUT-OF-SAMPLE doğrulama
    tr_oos = _bt(test, best["L"], best["p"], best["c"])
    oos_pf = _pf(tr_oos); oos_tot = sum(tr_oos) * 100
    rating = "İYİ" if (oos_pf >= 1.3 and len(tr_oos) >= 8 and oos_tot > 0) else \
             ("ORTA" if (oos_pf >= 1.05 and oos_tot > 0) else "ZAYIF")
    return {
        "params": {"trend_length": best["L"], "trend_percent": best["p"], "tott_coeff": best["c"]},
        "train_pf": best["train_pf"], "train_n": best["train_n"],
        "oos_pf": round(oos_pf, 2), "oos_n": len(tr_oos), "oos_total_pct": round(oos_tot, 1),
        "rating": rating,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    syms = _bist_list()
    print(f"15m scalp optimize — {len(syms)} BIST futures (train %70 / test %30 OOS)\n")
    out = {}
    print(f"{'Sembol':9s} {'Param(L/%/c)':>16s} {'trainPF':>7s} {'oosPF':>6s} {'oosN':>5s} {'oos%':>7s}  Rating")
    for sym in syms:
        try:
            res = optimize_symbol(sym)
        except Exception as e:
            print(f"{sym:9s} HATA {type(e).__name__}"); continue
        if res is None:
            print(f"{sym:9s} veri/sinyal yok"); continue
        out[sym] = res
        pp = res["params"]
        print(f"{sym:9s} {pp['trend_length']:>3d}/{pp['trend_percent']:>3.1f}/{pp['tott_coeff']:<5.3f} "
              f"{res['train_pf']:>7.2f} {res['oos_pf']:>6.2f} {res['oos_n']:>5d} {res['oos_total_pct']:>+7.1f}  {res['rating']}")
    json.dump(out, open("per_symbol_scalp_15m.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    iyi = [s for s, v in out.items() if v["rating"] == "İYİ"]
    orta = [s for s, v in out.items() if v["rating"] == "ORTA"]
    print(f"\n✅ İYİ (sekmeye girer): {len(iyi)} → {', '.join(s[:-3] for s in iyi)}")
    print(f"🟡 ORTA: {len(orta)} → {', '.join(s[:-3] for s in orta)}")
    print(f"Kaydedildi: per_symbol_scalp_15m.json")


if __name__ == "__main__":
    main()
