# -*- coding: utf-8 -*-
"""MIX testi: OTT trend-filtresi (senin sistem) vs EMA+ADX (repo) vs İKİSİ-BİREN.
Her biri long-or-nakit, maliyetli, buy&hold'a karşı, OOS. Birleştirmek tek başına
en iyisini geçiyor mu, yoksa sadece daha muhafazakar mı (overfit riski)?"""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf
import indicators as ind

SYMS=[s+".IS" for s in "AKBNK GARAN ISCTR YKBNK VAKBN HALKB KCHOL SAHOL EREGL KRDMD "
     "TUPRS PETKM SASA ASELS SISE THYAO PGSUS TAVHL BIMAS MGROS TCELL TTKOM ARCLK "
     "FROTO TOASO TKFEN ENKAI EKGYO AEFES ULKER CCOLA DOHOL ALARK GUBRF CIMSA".split()]
COST=0.002; CASH_YR=0.30; OOS=pd.Timestamp("2020-01-01"); cash_d=(1+CASH_YR)**(1/252)-1

def adx(h,l,c,n=14):
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    up=h.diff(); dn=-l.diff()
    p=np.where((up>dn)&(up>0),up,0.0); m=np.where((dn>up)&(dn>0),dn,0.0)
    atr=pd.Series(tr).ewm(alpha=1/n,adjust=False).mean()
    pdi=100*pd.Series(p,index=c.index).ewm(alpha=1/n,adjust=False).mean()/atr
    mdi=100*pd.Series(m,index=c.index).ewm(alpha=1/n,adjust=False).mean()/atr
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean(),pdi,mdi

def perf(r):
    r=r.dropna(); eq=(1+r).cumprod(); y=len(r)/252
    return (eq.iloc[-1]**(1/y)-1)*100, r.mean()/r.std()*np.sqrt(252), (1-eq/eq.cummax()).max()*100

print("OHLC iniyor + OTT & EMA+ADX filtreleri...\n")
filt={"OTT":{}, "EMA+ADX":{}, "İKİSİ(AND)":{}, "YADA(OR)":{}}
rets={}
for s in SYMS:
    try:
        d=yf.download(s,period="max",interval="1d",progress=False,auto_adjust=True)
        if d is None or len(d)<400: continue
        h,l,c=[d[x].astype(float).squeeze() for x in ["High","Low","Close"]]
    except: continue
    # OTT filtresi
    o=ind.ott(c,40,2.0,shift=2)
    ott_up=(c>o["ott"]).fillna(False)
    # EMA+ADX filtresi
    ema=c.ewm(span=19,adjust=False).mean(); A,pdi,mdi=adx(h,l,c)
    ea_up=((c>ema)&(A>18)&(pdi>mdi)).fillna(False)
    rets[s]=c.pct_change().fillna(0)
    filt["OTT"][s]=ott_up.shift(1).fillna(False)
    filt["EMA+ADX"][s]=ea_up.shift(1).fillna(False)
    filt["İKİSİ(AND)"][s]=(ott_up&ea_up).shift(1).fillna(False)
    filt["YADA(OR)"][s]=(ott_up|ea_up).shift(1).fillna(False)

R=pd.DataFrame(rets)
def portfolio(sig_dict):
    P={}
    for s in R.columns:
        if s not in sig_dict: continue
        pos=sig_dict[s].reindex(R.index).fillna(False).astype(float)
        flip=pos.diff().abs().fillna(0)
        P[s]=np.where(pos>0,R[s],cash_d)-flip*COST
    return pd.DataFrame(P,index=R.index).mean(axis=1)

print("="*72)
print(f"{'Sistem':14s}{'  TÜM: CAGR/Sh/DD':>22}{'  OOS2020+: CAGR/Sh/DD':>26}")
bh=R.mean(axis=1)
for name in ["OTT","EMA+ADX","İKİSİ(AND)","YADA(OR)"]:
    p=portfolio(filt[name])
    a=perf(p); a2=perf(p[p.index>=OOS])
    print(f"{name:14s}  {a[0]:+6.1f}/{a[1]:.2f}/{a[2]:.0f}%      {a2[0]:+6.1f}/{a2[1]:.2f}/{a2[2]:.0f}%")
b=perf(bh); b2=perf(bh[bh.index>=OOS])
print(f"{'BUY&HOLD':14s}  {b[0]:+6.1f}/{b[1]:.2f}/{b[2]:.0f}%      {b2[0]:+6.1f}/{b2[1]:.2f}/{b2[2]:.0f}%")
print("="*72)
print("SORU: 'İKİSİ' tek başına en iyisini GEÇİYOR mu (mix işe yarıyor), yoksa sadece")
print("daha muhafazakar mı? Geçmiyorsa → basit tek filtre yeter, mix overfitّtir.")
