# -*- coding: utf-8 -*-
"""Fiyat-temelli FAKTÖR testi — momentum'dan farklı anomaliler.
Düşük-volatilite (akademik: düşük-vol hisseler risk-ayarlı üstün), düşük-beta.
Piyasa-üstü (drift'siz), OOS, gerçek portföy (CAGR/Sharpe/MaxDD)."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
px=pd.read_pickle("_bist_px.pkl").sort_index()
OOS=pd.Timestamp("2018-01-01")
ret=px.pct_change()
mkt=ret.mean(axis=1)                     # eşit-ağırlık piyasa
HZ=20; CASH=0

def perf(r):
    r=r.dropna(); eq=(1+r).cumprod(); yrs=len(r)/252
    return (eq.iloc[-1]**(1/yrs)-1)*100, r.mean()/r.std()*np.sqrt(252), (1-eq/eq.cummax()).max()*100

def factor_bt(score, pick_low, name):
    """score: panel (dates×syms). pick_low=True → en düşük skorlu quintile al.
       Aylık rebalans, seçili hisseler eşit ağırlık. Piyasaya karşı."""
    days=px.index; sel=[]; port=[]
    cur=[]
    for t in range(250,len(days)-1):
        if (t-250)%HZ==0:
            s=score.iloc[t].dropna()
            valid=s.index[np.isfinite(s.values)]
            s=s[valid]
            if len(s)>=15:
                thr=s.quantile(0.2 if pick_low else 0.8)
                cur=list(s[s<=thr].index) if pick_low else list(s[s>=thr].index)
        port.append(ret[cur].iloc[t].mean() if cur else 0.0)
    R=pd.Series(port,index=days[250:len(days)-1])
    B=mkt.reindex(R.index)
    print(f"  {name}")
    for split,so in [("TÜM",False),("OOS",True)]:
        m=R.index>=OOS if so else R.index>=R.index[0]
        cp,shp,ddp=perf(R[m]); cb,shb,ddb=perf(B[m])
        exc=(R[m]-B[m]); t=exc.mean()/(exc.std()/np.sqrt(len(exc)))
        flag="  <<<" if shp>shb and cp>=cb else ""
        print(f"    {split:4s}: faktör CAGR{cp:+6.1f}% Sh{shp:.2f} DD{ddp:.0f}% | piyasa CAGR{cb:+6.1f}% Sh{shb:.2f} DD{ddb:.0f}% | excess-t={t:+.1f}{flag}")

# volatilite (düşük al)
vol=ret.rolling(60).std()
# beta (60g, düşük al)
cov=ret.rolling(120).cov(mkt); beta=cov.div(mkt.rolling(120).var(),axis=0)
# idiyosinkratik momentum: 120g getiri - beta*piyasa120g (kalıntı momentum, yüksek al)
m120=px/px.shift(120)-1; mkt120=(1+mkt).rolling(120).apply(np.prod,raw=True)-1
resid=m120.sub(beta.mul(mkt120,axis=0))

print(f"{px.shape[1]} sembol · fiyat-temelli faktörler (piyasaya karşı)\n"+"="*76)
factor_bt(vol, True,  "DÜŞÜK VOLATİLİTE (en düşük %20 vol'ü al)")
print()
factor_bt(beta, True, "DÜŞÜK BETA (en düşük %20 beta'yı al)")
print()
factor_bt(resid, False, "KALINTI MOMENTUM (beta-nötr, en yüksek %20)")
print("\n"+"="*76)
factor_bt(-vol, False, "YÜKSEK VOLATİLİTE (kontrol — kötü olmalı)")
print("\n<<< = faktör HEM Sharpe HEM getiride piyasayı geçti. excess-t>2 anlamlı.")
