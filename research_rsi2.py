# -*- coding: utf-8 -*-
"""RSI — DÜZELTİLMİŞ: piyasa-üstü (excess) getiri. TL enflasyon drift'ini çıkarır.
Her tarihte RSI-sinyalli hisselerin ileri getirisi vs o tarihteki TÜM hisse ortalaması.
Gerçek soru: RSI<30 hisseler piyasayı GEÇİYOR mu, yoksa sadece drift mi?"""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
px=pd.read_pickle("_bist_px.pkl").sort_index()
OOS=pd.Timestamp("2018-01-01"); COST=0.002

def rsi_panel(P,n=14):
    d=P.diff(); up=d.clip(lower=0); dn=(-d).clip(lower=0)
    ru=up.ewm(alpha=1/n,adjust=False).mean(); rd=dn.ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+ru/rd.replace(0,np.nan))

RS=rsi_panel(px)
print(f"{px.shape[1]} sembol × {px.shape[0]} gün · piyasa-ÜSTÜ (excess) RSI testi\n")

def excess_test(name, mask_fn, K):
    fwd=px.shift(-K)/px-1                      # ileri K-gün getiri (panel)
    mkt=fwd.mean(axis=1)                       # o tarihteki piyasa ortalaması (drift)
    exc=fwd.sub(mkt,axis=0)                    # piyasa-üstü getiri
    mask=mask_fn(RS)                           # sinyal barları
    for split in ["TÜM","OOS"]:
        m=mask.copy()
        if split=="OOS": m=m & (px.index>=OOS).reshape(-1,1) if False else m.loc[px.index>=OOS]
        e=(exc.loc[m.index] if split=="OOS" else exc)[m if split!="OOS" else m]
        vals=e.values[np.asarray(m.values)]
        vals=vals[np.isfinite(vals)]
        if len(vals)==0: print(f"    {split}: veri yok"); continue
        net=vals.mean()-COST; hit=100*(vals>0).mean()
        f="  <<< PİYASAYI GEÇİYOR" if net>0 and hit>50 else ""
        print(f"    {split:4s}: n={len(vals):>6}  piyasa-üstü net {net*100:+.3f}%  isabet {hit:.0f}%{f}")

SIG=[
 ("RSI<30 (oversold)", lambda R: R<30),
 ("RSI<25 (derin oversold)", lambda R: R<25),
 ("RSI>70 (overbought) — geçen ay?", lambda R: R>70),
 ("RSI>55 (momentum bölgesi)", lambda R: R>55),
]
for K in [3,5,10,20]:
    print(f"===== ileri {K} gün =====")
    for name,fn in SIG:
        print(f"  {name}")
        excess_test(name, fn, K)
    print()
print("EDGE VARSA: piyasa-üstü net%>0 VE isabet>50 VE TÜM≈OOS. Drift değil, GERÇEK seçim.")
