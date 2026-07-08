# -*- coding: utf-8 -*-
"""RSI sinyalinin tahmin gücü — aynı dürüst terazi (26yıl BIST günlük, OOS+maliyet).
Hem klasik (aşırı-satım=AL bounce) hem momentum yorumu (RSI>50=AL) test edilir."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
px=pd.read_pickle("_bist_px.pkl").sort_index()
OOS=pd.Timestamp("2018-01-01"); COST=0.002

def rsi(s, n=14):
    d=s.diff(); up=d.clip(lower=0); dn=(-d).clip(lower=0)
    ru=up.ewm(alpha=1/n,adjust=False).mean(); rd=dn.ewm(alpha=1/n,adjust=False).mean()
    rs=ru/rd.replace(0,np.nan)
    return 100-100/(1+rs)

# her sembol için RSI + forward
R={}
for c in px.columns:
    s=px[c].dropna()
    if len(s)<300: continue
    R[c]=pd.DataFrame({"c":s,"rsi":rsi(s)})
print(f"{len(R)} sembol\n")

def test(name, cond, side, K):
    rets=[]
    for c,df in R.items():
        cv=df["c"].values; rv=df["rsi"].values; n=len(cv)
        for i in range(20,n-K):
            if np.isnan(rv[i]): continue
            if cond(rv,i):
                fwd=cv[i+K]/cv[i]-1
                rets.append(fwd if side=="L" else -fwd)
    return np.array(rets)

def rep(name, arr):
    if len(arr)==0: print(f"  {name:34s} veri yok"); return
    net=arr.mean()-COST; hit=100*(arr>0).mean()
    f="  <<< POZİTİF" if net>0 and hit>50 else ""
    print(f"  {name:34s} n={len(arr):>6}  net {net*100:+.3f}%  isabet {hit:.0f}%{f}")

SIG=[
 ("RSI<30 → AL (klasik oversold)", lambda r,i: r[i]<30, "L"),
 ("RSI>70 → SAT (klasik overbought)", lambda r,i: r[i]>70, "S"),
 ("RSI<30 → SAT (momentum: düşen düşer)", lambda r,i: r[i]<30, "S"),
 ("RSI>50 → AL (momentum)", lambda r,i: r[i]>50 and r[i-1]<=50, "L"),
 ("RSI yukarı 30 keser → AL", lambda r,i: r[i]>30 and r[i-1]<=30, "L"),
]
for K in [3,5,10]:
    print(f"===== forward {K} gün =====")
    for split in ["TÜM","OOS"]:
        # OOS filtresi için basitçe son ~%40'ı OOS say (tarih indeksleri sembol-bazlı farklı, oran kullan)
        print(f"  --- {split} ---")
        for name,cond,side in SIG:
            arr=[]
            for c,df in R.items():
                cv=df["c"].values; rv=df["rsi"].values; nn=len(cv); cut=int(nn*0.6)
                lo,hi=(20,nn-K) if split=="TÜM" else (cut,nn-K)
                for i in range(lo,hi):
                    if i<1 or np.isnan(rv[i]): continue
                    if cond(rv,i): arr.append((cv[i+K]/cv[i]-1) if side=="L" else -(cv[i+K]/cv[i]-1))
            rep(name, np.array(arr))
    print()
print("Beklenti: klasik oversold-AL negatif (BIST momentum). Sürpriz varsa görürüz.")
