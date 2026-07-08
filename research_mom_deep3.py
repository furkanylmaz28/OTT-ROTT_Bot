# -*- coding: utf-8 -*-
"""TS-momentum, GERÇEKÇİ nakit faizi ile — Türkiye'de cash=0 büyük hata.
Nakitteyken TL mevduat faizi kazanılır. Bu, trend-filtresinin gerçek değerini gösterir."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
px=pd.read_pickle("_bist_px.pkl").sort_index()
OOS=pd.Timestamp("2018-01-01")
LIQ=[s+".IS" for s in "AKBNK GARAN ISCTR YKBNK VAKBN HALKB KCHOL SAHOL EREGL KRDMD "
     "TUPRS PETKM SASA ASELS SISE THYAO PGSUS TAVHL BIMAS MGROS TCELL TTKOM ARCLK "
     "FROTO TOASO TKFEN ENKAI EKGYO KOZAL AEFES ULKER CCOLA DOHOL ALARK GUBRF AKSEN "
     "ODAS TSKB OYAKC KONTR ASTOR HEKTS DOAS CIMSA".split()]
LIQ=[s for s in LIQ if s in px.columns]
d1=px[LIQ].pct_change().fillna(0)

def perf(r):
    r=r.dropna(); eq=(1+r).cumprod(); yrs=len(r)/252
    return (eq.iloc[-1]**(1/yrs)-1)*100, r.mean()/r.std()*np.sqrt(252), (1-eq/eq.cummax()).max()*100

def ts_mom(lb, cash_yr, so):
    cash_d=(1+cash_yr)**(1/252)-1                      # günlük nakit getirisi
    sig=((px[LIQ]/px[LIQ].shift(lb)-1)>0).shift(1).fillna(False)
    pos=sig.astype(float)
    # her hisse: long ise hisse getirisi, değilse nakit faizi
    per=d1*pos + (1-pos)*cash_d
    port=per.mean(axis=1)                              # eşit ağırlık, hep yatırımda (long veya nakit)
    bh=d1.mean(axis=1)
    mask=px.index>=OOS if so else px.index>=px.index[0]
    return port[mask], bh[mask]

print(f"Likit {len(LIQ)} sembol · nakit faizi duyarlılığı\n")
print("="*76)
print("TS-momentum (long-or-nakit), NAKİT FAİZİYLE — risk-ayarlı, buy&hold'a karşı")
for cash in [0.0, 0.20, 0.35, 0.45]:
    print(f"\n  --- nakit faizi = %{cash*100:.0f}/yıl ---")
    for lb in [150,200,250]:
        for split,so in [("TÜM",False),("OOS",True)]:
            p,b=ts_mom(lb,cash,so); cp,shp,ddp=perf(p); cb,shb,ddb=perf(b)
            edge=cp-cb
            flag="  <<<" if (shp>shb and cp>=cb) else ""
            print(f"    lb{lb} {split:4s}: mom CAGR{cp:+6.1f}% Sh{shp:.2f} DD{ddp:.0f}% | b&h CAGR{cb:+6.1f}% Sh{shb:.2f} DD{ddb:.0f}% | fazla{edge:+5.1f}%{flag}")
print("\n"+"="*76)
print("<<< = momentum HEM Sharpe HEM getiride buy&hold'u geçti (gerçekçi nakitle).")
