# -*- coding: utf-8 -*-
"""thinkoptimize/trade-for-bist100 stratejisini (EMA19 + ADX>18 trend) KENDİ terazimde:
maliyet + benchmark (buy&hold) + OOS. '%695' gerçek edge mi, yoksa maliyetsiz/OOS'suz/
enflasyon-şişkin yanılsama mı? OHLC yfinance'ten (ADX için high/low gerekir)."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

SYMS=[s+".IS" for s in "AKBNK GARAN ISCTR YKBNK VAKBN HALKB KCHOL SAHOL EREGL KRDMD "
     "TUPRS PETKM SASA ASELS SISE THYAO PGSUS TAVHL BIMAS MGROS TCELL TTKOM ARCLK "
     "FROTO TOASO TKFEN ENKAI EKGYO KOZAL AEFES ULKER CCOLA DOHOL ALARK GUBRF GOLTS".split()]
COST=0.002; CASH_YR=0.30; OOS=pd.Timestamp("2020-01-01")

def adx(h,l,c,n=14):
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    up=h.diff(); dn=-l.diff()
    plus=np.where((up>dn)&(up>0),up,0.0); minus=np.where((dn>up)&(dn>0),dn,0.0)
    atr=pd.Series(tr).ewm(alpha=1/n,adjust=False).mean()
    pdi=100*pd.Series(plus,index=c.index).ewm(alpha=1/n,adjust=False).mean()/atr
    mdi=100*pd.Series(minus,index=c.index).ewm(alpha=1/n,adjust=False).mean()/atr
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean(), pdi, mdi

def perf(r):
    r=r.dropna(); eq=(1+r).cumprod(); y=len(r)/252
    return (eq.iloc[-1]**(1/y)-1)*100, r.mean()/r.std()*np.sqrt(252), (1-eq/eq.cummax()).max()*100

print("OHLC iniyor + EMA19/ADX stratejisi (maliyet+benchmark+OOS)...\n")
cash_d=(1+CASH_YR)**(1/252)-1
res=[]; strat_r=[]; bh_r=[]; idx_all=None
for s in SYMS:
    try:
        d=yf.download(s,period="max",interval="1d",progress=False,auto_adjust=True)
        if d is None or len(d)<400: continue
        h,l,c=[d[x].astype(float).squeeze() for x in ["High","Low","Close"]]
    except: continue
    ema=c.ewm(span=19,adjust=False).mean()
    ADX,pdi,mdi=adx(h,l,c)
    # onların ruhu: fiyat>EMA19 (yukarı trend) VE ADX>18 VE +DI>-DI → long, değilse nakit
    long=((c>ema)&(ADX>18)&(pdi>mdi)).shift(1).fillna(False)
    ret=c.pct_change().fillna(0)
    flip=long.ne(long.shift(1)).fillna(False)
    sr=np.where(long,ret,cash_d)-flip*COST
    sr=pd.Series(sr,index=c.index)
    res.append((s,sr,ret))

# birleşik (eşit ağırlık portföy)
allidx=sorted(set().union(*[r[1].index for r in res]))
S=pd.DataFrame({r[0]:r[1] for r in res}).reindex(allidx)
B=pd.DataFrame({r[0]:r[2] for r in res}).reindex(allidx)
sp=S.mean(axis=1); bp=B.mean(axis=1)
print("="*70)
print("EMA19+ADX stratejisi vs BUY&HOLD (eşit-ağırlık portföy, maliyetli):")
for split,so in [("TÜM",False),("OOS 2020+",True)]:
    m=sp.index>=OOS if so else sp.index>=sp.index[0]
    cs,shs,dds=perf(sp[m]); cb,shb,ddb=perf(bp[m])
    print(f"  {split:10s}: strateji CAGR{cs:+6.1f}% Sh{shs:.2f} DD{dds:.0f}% | b&h CAGR{cb:+6.1f}% Sh{shb:.2f} DD{ddb:.0f}%")
# tek tek hisse: kaç tanesi buy&hold'u GEÇTİ (maliyetli)
beat=0; tot=0
print("\n  Hisse bazında (maliyetli strateji vs sadece tut):")
for s,sr,rr in res:
    cs=(1+sr).prod(); cb=(1+rr).prod(); tot+=1; beat+=cs>cb
print(f"  {tot} hissenin {beat}'i strateji ile buy&hold'u geçti = %{100*beat/tot:.0f}")
print("="*70)
print("Onların '%695' benchmark'sız/maliyetsiz/OOS'suz. Gerçek soru: SADECE TUTMAYI geçiyor mu?")
