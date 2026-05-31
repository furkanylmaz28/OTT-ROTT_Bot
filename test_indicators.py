"""
İndikatör portu sağlık kontrolü — değerler hesaplanıyor mu, NaN-shift'ler doğru mu.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
import indicators as ind


rng = np.random.default_rng(42)
n = 300
close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)), name="close")
high = close + rng.uniform(0, 1, n)
low = close - rng.uniform(0, 1, n)

print("=== VAR ===")
v30 = ind.var_func(close, 30)
print(f"first non-NaN idx={v30.first_valid_index()}  last={v30.iloc[-1]:.4f}  NaN count={v30.isna().sum()}")

print("\n=== OTT(close, 30, 7) ===")
o = ind.ott(close, 30, 7.0, shift=2)
print(f"mavg[-1]={o['mavg'].iloc[-1]:.4f}  ott[-1]={o['ott'].iloc[-1]:.4f}  dir[-1]={o['dir'].iloc[-1]}")
print(f"ott raw NaN={o['ott_raw'].isna().sum()}  ott shifted NaN={o['ott'].isna().sum()} (shift=2 -> +2 NaN beklenir)")

print("\n=== TOTT(close, 30, 1, 0.001) ===")
t = ind.tott(close, 30, 1.0, 0.001)
print(f"ott[-1]={t['ott'].iloc[-1]:.4f}  ottup[-1]={t['ottup'].iloc[-1]:.4f}  ottdn[-1]={t['ottdn'].iloc[-1]:.4f}")
print(f"band genişliği: {(t['ottup'].iloc[-1] - t['ottdn'].iloc[-1]):.4f}")

print("\n=== ROTT(close, x1=30, x2=1000, percent=7) ===")
# x2=1000 üretilmiş veride çok büyük, x2=100 ile dene
r = ind.rott(close, x1=30, x2=100, percent=7.0)
print(f"perfect_ma2[-1]={r['perfect_ma2'].iloc[-1]:.4f}  ott[-1]={r['ott'].iloc[-1]:.4f}")
print(f"trend yönü (perfect_ma2 > ott): {r['perfect_ma2'].iloc[-1] > r['ott'].iloc[-1]}")

print("\n=== SOTT(close, high, low, periodK=50, smoothK=20) ===")
s = ind.sott(close, high, low, period_k=50, smooth_k=20, length=2, percent=0.5)
print(f"k[-1]={s['k'].iloc[-1]:.4f}  src[-1]={s['src'].iloc[-1]:.4f}  ott[-1]={s['ott'].iloc[-1]:.4f}")
print(f"stoch yukarı trendde mi: {s['src'].iloc[-1] > s['ott'].iloc[-1]}")

print("\n=== HOTT/LOTT(20) ===")
h = ind.hott(high, 20, 0.5)
l = ind.lott(low, 20, 0.5)
print(f"hott[-1]={h.iloc[-1]:.4f}  lott[-1]={l.iloc[-1]:.4f}  high[-1]={high.iloc[-1]:.4f}  low[-1]={low.iloc[-1]:.4f}")

print("\nTUMU GEÇTI ✓")
