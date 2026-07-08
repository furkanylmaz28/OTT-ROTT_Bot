# -*- coding: utf-8 -*-
"""Momentum — ek testler: (A) likit-filtre kesitsel, (B) mutlak/time-series momentum.
Kirli outlier'ları ve TL-enflasyon yanılgısını ele alır. Risk-ayarlı (Sharpe/MaxDD)
odak, çünkü TL'de nominal getiri yanıltıcı — asıl soru: piyasayı RİSK-AYARLI geçer mi."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

px=pd.read_pickle("_bist_px.pkl").sort_index()
dates=px.index
OOS=pd.Timestamp("2018-01-01")

# Likit büyük-cap çekirdek (bilinen BIST-30/50 isimleri) — outlier kirini azaltır
LIQ=[s+".IS" for s in "AKBNK GARAN ISCTR YKBNK VAKBN HALKB KCHOL SAHOL EREGL KRDMD "
     "TUPRS PETKM SASA ASELS SISE THYAO PGSUS TAVHL BIMAS MGROS TCELL TTKOM ARCLK "
     "FROTO TOASO TKFEN ENKAI EKGYO KOZAL AEFES ULKER CCOLA DOHOL ALARK GUBRF AKSEN "
     "ODAS TSKB OYAKC KONTR ASTOR HEKTS DOAS CIMSA".split()]
LIQ=[s for s in LIQ if s in px.columns]
print(f"Likit çekirdek: {len(LIQ)} sembol\n")

def stats(a):
    a=np.array(a); n=len(a)
    if n<2: return n,0,0,0
    return n, a.mean()*100, a.mean()/(a.std(ddof=1)/np.sqrt(n)), 100*(a>0).mean()

# ── A) LİKİT kesitsel momentum (winsorize: forward getiriyi ±%50 kırp) ──
print("="*74)
print("A) LİKİT kesitsel momentum, forward winsorize ±50% (outlier temizliği)")
print("   long-only üst-tercile FAZLA getiri (net%/t) — TÜM vs OOS")
sub=px[LIQ]
for lb,hz in [(120,20),(180,20),(120,60),(250,60)]:
    for split in ["TÜM","OOS"]:
        recs=[]
        for t in range(lb+21,len(dates)-hz,hz):
            sig=sub.iloc[t-21]/sub.iloc[t-21-lb]-1
            fwd=(sub.iloc[t+hz]/sub.iloc[t]-1).clip(-0.5,0.5)   # winsorize
            m=sig.notna()&fwd.notna()&(sub.iloc[t]>0)
            if m.sum()<12: continue
            s=sig[m]; f=fwd[m]
            q=pd.qcut(s.rank(method="first"),3,labels=False)
            recs.append((dates[t], f[q==2].mean()-f.mean()-0.002))
        if split=="OOS": recs=[r for r in recs if r[0]>=OOS]
        n,mean,tt,hit=stats([r[1] for r in recs])
        tag=f"lb{lb}/hz{hz}"
        print(f"   {tag:12s} {split:4s}: {mean:+.2f}%/reb · t={tt:+.2f} · isabet={hit:.0f}% · n={n}")
    print()

# ── B) MUTLAK (time-series) momentum: her hisse kendi geçmişi + trend → long/cash ──
# TL'de 'cash' faiz getirir; muhafazakar olarak cash=0 (TS-momentum'u OLDUĞUNDAN KÖTÜ gösterir).
# Asıl soru: RİSK-AYARLI (Sharpe/MaxDD) buy&hold'u geçer mi?
print("="*74)
print("B) MUTLAK momentum (long-or-CASH, cash=0 muhafazakar) — RİSK-AYARLI")
print("   Portföy: likit evren, hisse kendi 'lb-gün getirisi>0' ise long, değilse cash")
d1=px[LIQ].pct_change().fillna(0)
def ts_mom(lb, split_oos=False):
    sig=(px[LIQ]/px[LIQ].shift(lb)-1)>0            # mutlak momentum sinyali
    sig=sig.shift(1).fillna(False)                 # bir gün gecikme (lookahead yok)
    pos=sig.astype(float)
    active=pos.sum(axis=1).clip(lower=1)
    port=(d1*pos).sum(axis=1)/active               # sadece long olanlar, eşit ağırlık
    bh=d1.mean(axis=1)                             # buy&hold eşit ağırlık
    mask=px.index>=OOS if split_oos else px.index>=px.index[0]
    return port[mask], bh[mask]
def perf(r):
    r=r.dropna(); eq=(1+r).cumprod()
    yrs=len(r)/252; cagr=(eq.iloc[-1]**(1/yrs)-1)*100
    sh=r.mean()/r.std()*np.sqrt(252)
    dd=(1-eq/eq.cummax()).max()*100
    return cagr,sh,dd,eq.iloc[-1]
for lb in [120,200,250]:
    for split,so in [("TÜM",False),("OOS",True)]:
        p,b=ts_mom(lb,so); cp,shp,ddp,_=perf(p); cb,shb,ddb,_=perf(b)
        print(f"   lb{lb} {split:4s}: momentum CAGR{cp:+6.1f}% Sharpe{shp:.2f} MaxDD{ddp:.0f}%  |  buy&hold CAGR{cb:+6.1f}% Sharpe{shb:.2f} MaxDD{ddb:.0f}%")
    print()
print("="*74)
print("YORUM: TS-momentum'un değeri genelde MaxDD düşürmek. Sharpe(mom)>Sharpe(bh)")
print("ve MaxDD(mom)<MaxDD(bh) ise risk-ayarlı fayda var (cash=0 olduğu halde).")
