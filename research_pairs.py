# -*- coding: utf-8 -*-
"""PAIRS TRADING — Gatev-Goetzmann-Rouwenhorst mesafe yöntemi, walk-forward.
Çift seçimi FORMASYON penceresinde (geçmiş), işlem TRADING penceresinde (gelecek)
= otomatik OOS. Market-neutral (long-short) → TL drift tuzağına DÜŞMEZ.
Kural: normalize fiyat farkı (spread) formasyon std'sinin ±2'sini aşınca aç,
0'a dönünce kapat. Maliyet: bacak başına %0.2."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
px=pd.read_pickle("_bist_px.pkl").sort_index()
LIQ=[s+".IS" for s in "AKBNK GARAN ISCTR YKBNK VAKBN HALKB KCHOL SAHOL EREGL KRDMD "
     "TUPRS PETKM SASA ASELS SISE THYAO PGSUS TAVHL BIMAS MGROS TCELL TTKOM ARCLK "
     "FROTO TOASO TKFEN ENKAI EKGYO KOZAL AEFES ULKER CCOLA DOHOL ALARK GUBRF AKSEN "
     "ODAS TSKB OYAKC KONTR ASTOR HEKTS DOAS CIMSA".split()]
LIQ=[s for s in LIQ if s in px.columns]
P=px[LIQ]
COST=0.002; ENTRY=2.0; NP=20     # ±2σ giriş, en iyi 20 çift
FORM=252; TRADE=126              # 1yıl formasyon, 6ay işlem, kaydırmalı

def walk():
    days=P.index; trades=[]; daily=[]
    t=FORM
    while t+TRADE<len(days):
        form=P.iloc[t-FORM:t]; trade=P.iloc[t:t+TRADE]
        # normalize (formasyon başı=1), sadece dolu seriler
        f0=form.iloc[0]; norm=form.div(f0)
        valid=[c for c in LIQ if norm[c].notna().all() and (form[c]>0).all()]
        if len(valid)<10: t+=TRADE; continue
        # tüm çiftlerin SSD'si → en düşük NP
        ssd=[]
        for i in range(len(valid)):
            for j in range(i+1,len(valid)):
                a,b=valid[i],valid[j]
                d=((norm[a]-norm[b])**2).sum()
                ssd.append((d,a,b))
        ssd.sort(); pairs=ssd[:NP]
        # işlem penceresi
        for _,a,b in pairs:
            fa=form[a].iloc[0]; fb=form[b].iloc[0]
            sp_form=(form[a]/fa - form[b]/fb)
            mu,sd=sp_form.mean(), sp_form.std()
            if sd<=0: continue
            ta=trade[a]/fa; tb=trade[b]/fb
            sp=(ta-tb); z=(sp-mu)/sd
            ra=trade[a].pct_change().fillna(0).values
            rb=trade[b].pct_change().fillna(0).values
            zv=z.values; pos=0; pnl_open=0
            for k in range(1,len(zv)):
                if pos==0:
                    if zv[k]>ENTRY: pos=-1; pnl_open=-COST*2   # spread yüksek→short spread
                    elif zv[k]<-ENTRY: pos=1; pnl_open=-COST*2
                else:
                    day=pos*(ra[k]-rb[k])/2   # dolar-nötr, yarı-yarı
                    daily.append(day)
                    pnl_open+=day
                    if (pos==-1 and zv[k]<=0) or (pos==1 and zv[k]>=0):
                        pnl_open-=COST*2; trades.append(pnl_open); pos=0
            if pos!=0: pnl_open-=COST*2; trades.append(pnl_open)   # pencere sonu kapat
        t+=TRADE
    return np.array(trades), np.array(daily)

print(f"Likit {len(LIQ)} sembol · pairs trading walk-forward (formasyon {FORM}g / işlem {TRADE}g)\n")
tr,dl=walk()
tr=np.clip(tr,-0.30,0.30)   # işlem başı ±%30 kırp (uç/ıraksama artefaktı temizle)
n=len(tr); wr=100*(tr>0).mean() if n else 0; tot=tr.sum()*100; avg=tr.mean()*100 if n else 0
gl=abs(tr[tr<0].sum()); pf=(tr[tr>0].sum()/gl) if gl>0 else 99
tstat=tr.mean()/(tr.std(ddof=1)/np.sqrt(n)) if n>1 else 0
print("="*66)
print(f"İşlem sayısı: {n}")
print(f"Kazanan: %{wr:.0f} · ort/işlem: {avg:+.3f}% · PF: {pf:.2f} · t-stat: {tstat:.2f}")
print(f"Toplam (basit): {tot:+.0f}%")
# günlük seriden Sharpe (market-neutral olduğu için drift'siz)
if len(dl)>20:
    sh=dl.mean()/dl.std()*np.sqrt(252)
    print(f"Günlük strateji Sharpe (yıllık): {sh:.2f}")
# Monte Carlo
if n>20:
    rng=np.random.default_rng(5)
    sims=np.array([rng.choice(tr,n,replace=True).sum()*100 for _ in range(5000)])
    print(f"Monte Carlo pozitif: %{100*(sims>0).mean():.0f} · medyan {np.median(sims):+.0f}%")
print("="*66)
print("EDGE: PF>1.1 + t>2 + Sharpe>0.7 + MC>90%. Market-neutral → drift yanılgısı YOK.")
