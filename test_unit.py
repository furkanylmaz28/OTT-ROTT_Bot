"""
İndikatör birim testleri — sentetik veriyle manuel hesap doğrulaması.

Pine kaynak kodundaki algoritmayı NumPy ile saf, basit halde yeniden uygula
(referans implementasyon) ve bizim port ile karşılaştır.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import indicators as ind


def ref_var(data: np.ndarray, length: int) -> np.ndarray:
    """
    Referans VAR — Pine f_var'ı satır satır yeniden uygula, vectorize etmeden.
    Pine:
       a = 9
       b[i] = data[i]>data[i-1] ? data[i]-data[i-1] : 0
       c[i] = data[i]<data[i-1] ? data[i-1]-data[i] : 0
       d[i] = sum(b, 9)  -- son 9 bar, ilk 8 bar NaN
       e[i] = sum(c, 9)
       f[i] = nz((d-e)/(d+e))
       g[i] = |f[i]|
       h = 2/(length+1)
       x[i] = sma(data, length)
       vidya[i] = u1==1 ? data[i] :
                  na(vidya[i-1]) ? x[i] :
                  g[i]*h*(data[i]-vidya[i-1]) + vidya[i-1]
    """
    n = len(data)
    if length == 1:
        return data.copy()

    b = np.zeros(n)
    c = np.zeros(n)
    for i in range(1, n):
        d_diff = data[i] - data[i - 1]
        if d_diff > 0:
            b[i] = d_diff
        elif d_diff < 0:
            c[i] = -d_diff

    d = np.full(n, np.nan)
    e = np.full(n, np.nan)
    for i in range(8, n):
        d[i] = b[i - 8:i + 1].sum()  # son 9 bar
        e[i] = c[i - 8:i + 1].sum()

    g = np.zeros(n)
    for i in range(n):
        if np.isnan(d[i]) or (d[i] + e[i]) == 0:
            g[i] = 0.0
        else:
            g[i] = abs((d[i] - e[i]) / (d[i] + e[i]))

    alpha = 2.0 / (length + 1)
    sma = np.full(n, np.nan)
    for i in range(length - 1, n):
        sma[i] = data[i - length + 1:i + 1].mean()

    vidya = np.full(n, np.nan)
    for i in range(n):
        if i == 0 or np.isnan(vidya[i - 1]):
            vidya[i] = sma[i]
        else:
            vidya[i] = g[i] * alpha * (data[i] - vidya[i - 1]) + vidya[i - 1]
    return vidya


def ref_ott(data: np.ndarray, length: int, percent: float) -> dict:
    """Pine OTT'yi referans olarak uygula."""
    n = len(data)
    mavg = ref_var(data, length)
    long_stop = np.full(n, np.nan)
    short_stop = np.full(n, np.nan)
    direction = np.full(n, 1, dtype=int)
    ott_raw = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(mavg[i]):
            continue
        fark = mavg[i] * percent * 0.01
        ls = mavg[i] - fark
        ss = mavg[i] + fark
        ls_prev = ls if (i == 0 or np.isnan(long_stop[i - 1])) else long_stop[i - 1]
        ss_prev = ss if (i == 0 or np.isnan(short_stop[i - 1])) else short_stop[i - 1]
        if mavg[i] > ls_prev:
            ls = max(ls, ls_prev)
        if mavg[i] < ss_prev:
            ss = min(ss, ss_prev)
        d_prev = direction[i - 1] if i > 0 else 1
        if d_prev == -1 and mavg[i] > ss_prev:
            d = 1
        elif d_prev == 1 and mavg[i] < ls_prev:
            d = -1
        else:
            d = d_prev
        mt = ls if d == 1 else ss
        if mavg[i] > mt:
            ott_raw[i] = mt * (200 + percent) / 200
        else:
            ott_raw[i] = mt * (200 - percent) / 200
        long_stop[i] = ls
        short_stop[i] = ss
        direction[i] = d

    return {"mavg": mavg, "ott_raw": ott_raw, "dir": direction}


def assert_series_eq(name: str, a: np.ndarray, b: np.ndarray, tol: float = 1e-9):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    both_nan = np.isnan(a) & np.isnan(b)
    diff = np.where(both_nan, 0.0, np.where(np.isnan(a) | np.isnan(b), np.inf, np.abs(a - b)))
    max_diff = np.nanmax(diff) if len(diff) else 0.0
    n_diff = int(np.sum(diff > tol))
    status = "OK " if n_diff == 0 else "FAIL"
    print(f"  {status}  {name:30s}  max_diff={max_diff:.2e}  fark olan bar={n_diff}/{len(a)}")
    if n_diff > 0:
        # ilk 5 farkı yazdır
        idxs = np.where(diff > tol)[0][:5]
        for idx in idxs:
            print(f"        bar {idx}: ref={a[idx]}  port={b[idx]}  diff={diff[idx]:.4e}")
    return n_diff == 0


def test_var_various_lengths():
    print("\n=== TEST 1: VAR farklı length'lerle ===")
    rng = np.random.default_rng(7)
    n = 200
    data_np = 100 + np.cumsum(rng.normal(0, 1, n))
    data_pd = pd.Series(data_np, name="data")

    ok = True
    for length in [1, 5, 9, 14, 30, 60, 100]:
        ref = ref_var(data_np, length)
        port = ind.var_func(data_pd, length).to_numpy()
        ok &= assert_series_eq(f"VAR(length={length})", ref, port)
    return ok


def test_ott_various_params():
    print("\n=== TEST 2: OTT raw farklı (length, percent) ===")
    rng = np.random.default_rng(13)
    n = 250
    data_np = 100 + np.cumsum(rng.normal(0, 1, n))
    data_pd = pd.Series(data_np, name="data")

    ok = True
    for length, percent in [(2, 0.5), (5, 1.0), (30, 7.0), (30, 0.8), (50, 3.5)]:
        ref = ref_ott(data_np, length, percent)
        port = ind.ott(data_pd, length, percent, shift=0)
        ok &= assert_series_eq(f"MAvg(L={length})", ref["mavg"], port["mavg"].to_numpy())
        ok &= assert_series_eq(f"OTT(L={length},p={percent})",
                                ref["ott_raw"], port["ott_raw"].to_numpy())
        # dir kontrolü
        ref_dir = ref["dir"].astype(float)
        port_dir = port["dir"].astype(float).to_numpy()
        # ilk birkaç barda dir'in varsayılan 1 olması beklenir
        match = np.sum(ref_dir == port_dir)
        print(f"        dir eşleşmesi: {match}/{n}")
    return ok


def test_edge_cases():
    print("\n=== TEST 3: Edge case'ler ===")
    ok = True

    # Sabit fiyat — diff hep 0 → CMO=0 → vidya değişmez (sma'da kalır)
    data = pd.Series(np.full(50, 100.0))
    var = ind.var_func(data, 10)
    expected = np.full(50, 100.0)
    expected[:9] = np.nan  # ilk 9 bar NaN beklenir (length=10, sma'nın min_periods=10)
    diff_count = np.sum((~np.isnan(var.to_numpy()[9:]) & (var.to_numpy()[9:] != 100.0)))
    if diff_count == 0:
        print("  OK   Sabit fiyat → VAR sabit 100")
    else:
        print(f"  FAIL Sabit fiyat → bazı barlarda 100 değil")
        ok = False

    # length=1 → vidya = data
    data2 = pd.Series([100.0, 101.0, 99.0, 102.0])
    var2 = ind.var_func(data2, 1)
    if np.allclose(var2.to_numpy(), data2.to_numpy()):
        print("  OK   length=1 → vidya = data")
    else:
        print(f"  FAIL length=1 → {var2.tolist()}")
        ok = False

    return ok


def test_real_gold():
    """Gerçek GOLD verisiyle ref vs port karşılaştır."""
    print("\n=== TEST 4: Gerçek GOLD M15 verisiyle ===")
    from mt4_hst import load_symbol
    df = load_symbol("GCM-Demo", "GOLD", 15).tail(5000)
    data_np = df["close"].to_numpy()
    data_pd = df["close"].reset_index(drop=True)

    ok = True
    ref_v = ref_var(data_np, 30)
    port_v = ind.var_func(data_pd, 30).to_numpy()
    ok &= assert_series_eq("VAR(close, 30) [5000 bar]", ref_v, port_v)

    ref_o = ref_ott(data_np, 30, 7.0)
    port_o = ind.ott(data_pd, 30, 7.0, shift=0)
    ok &= assert_series_eq("OTT(close, 30, 7)", ref_o["ott_raw"],
                            port_o["ott_raw"].to_numpy())

    return ok


def main():
    results = []
    results.append(("VAR various lengths", test_var_various_lengths()))
    results.append(("OTT various params", test_ott_various_params()))
    results.append(("Edge cases", test_edge_cases()))
    results.append(("Real GOLD data", test_real_gold()))

    print("\n" + "=" * 50)
    print("SONUÇ")
    print("=" * 50)
    for name, ok in results:
        status = "✓ GEÇTI" if ok else "✗ BAŞARISIZ"
        print(f"  {status:10s}  {name}")
    return all(ok for _, ok in results)


if __name__ == "__main__":
    main()
