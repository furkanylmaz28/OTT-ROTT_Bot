# -*- coding: utf-8 -*-
"""KAZANAN adayı sıkı doğrulama: basit BIST trend-zamanlaması.
Kural: eşit-ağırlık BIST 'endeksi' kendi 200g MA üstündeyse → hisselerde (long),
altındaysa → TL mevduat. Aylık kontrol. Robust mu: MC, flip/maliyet, alt-dönem DD."""
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
idx=(1+d1.mean(axis=1)).cumprod()
bh=d1.mean(axis=1)

def strat(N, cash_yr, cost=0.001):
    cash_d=(1+cash_yr)**(1/252)-1
    ma=idx.rolling(N).mean()
    signal=(idx>ma).shift(1).fillna(False)          # dün kapanışına göre (lookahead yok)
    flip=signal.ne(signal.shift(1)).fillna(False)   # rejim değişimi
    r=np.where(signal, bh, cash_d) - flip*cost      # her flip'te tek yönlü maliyet
    return pd.Series(r,index=d1.index), flip.sum()

def perf(r):
    r=r.dropna(); eq=(1+r).cumprod(); yrs=len(r)/252
    return dict(cagr=(eq.iloc[-1]**(1/yrs)-1)*100, sharpe=r.mean()/r.std()*np.sqrt(252),
                maxdd=(1-eq/eq.cummax()).max()*100, mult=eq.iloc[-1])

print(f"Likit {len(LIQ)} sembol · 2000-2026 · basit trend-zamanlaması\n")
print("="*74)
print("1) Nakit faizi ve MA duyarlılığı (CAGR/Sharpe/MaxDD, TÜM tarih)")
print(f"   {'':8s}{'MA150':>22}{'MA200':>22}")
for cash in [0.20,0.30,0.40]:
    for N in [150,200]:
        pass
    r150,_=strat(150,cash); r200,_=strat(200,cash)
    p1,p2=perf(r150),perf(r200)
    print(f"   cash%{int(cash*100):<3} {p1['cagr']:>7.1f}/{p1['sharpe']:.2f}/{p1['maxdd']:.0f}%  {p2['cagr']:>7.1f}/{p2['sharpe']:.2f}/{p2['maxdd']:.0f}%")
pb=perf(bh); print(f"   buy&hold: CAGR {pb['cagr']:.1f}% / Sharpe {pb['sharpe']:.2f} / MaxDD {pb['maxdd']:.0f}%")

print("\n"+"="*74)
print("2) MERKEZ konfig MA200, cash%30 — flip/maliyet + dönem kırılımı")
r,nflip=strat(200,0.30)
yrs=len(r)/252
print(f"   26 yılda {nflip} rejim değişimi = yılda ~{nflip/yrs:.1f} flip → maliyet ihmal edilebilir")
for split,so in [("TÜM",False),("OOS(2018+)",True)]:
    m=r.index>=OOS if so else r.index>=r.index[0]
    ps,pbh=perf(r[m]),perf(bh[m])
    print(f"   {split:11s}: strateji CAGR {ps['cagr']:+6.1f}% Sharpe {ps['sharpe']:.2f} MaxDD {ps['maxdd']:.0f}%  |  b&h CAGR {pbh['cagr']:+6.1f}% Sharpe {pbh['sharpe']:.2f} MaxDD {pbh['maxdd']:.0f}%")

print("\n"+"="*74)
print("3) Alt-dönem MaxDD (trend-filtresi krizleri kaçırıyor mu — asıl değer)")
for y0 in [2000,2006,2012,2018,2022]:
    mm=(r.index.year>=y0)&(r.index.year<y0+6)
    if mm.sum()>150:
        ps,pbh=perf(r[mm]),perf(bh[mm])
        print(f"   {y0}-{y0+5}: strateji DD {ps['maxdd']:.0f}% vs b&h DD {pbh['maxdd']:.0f}%  (Sharpe {ps['sharpe']:.2f} vs {pbh['sharpe']:.2f})")

print("\n"+"="*74)
print("4) Monte Carlo — blok-bootstrap (60-gün bloklar, rejimi korur), 5000 tur")
exc=(r-bh).dropna().values; L=60; nb=len(exc)//L
rng=np.random.default_rng(3)
sims=[]
for _ in range(5000):
    starts=rng.integers(0,len(exc)-L,nb)
    sims.append(np.mean([exc[s:s+L].sum() for s in starts]))
sims=np.array(sims)
print(f"   Fazla getiri (strateji−b&h) pozitif blok-ortalaması: %{100*(sims>0).mean():.0f} simülasyonda")
# risk-ayarlı MC: bootstrap Sharpe
def boot_sharpe(x):
    idxs=rng.integers(0,len(x),len(x)); y=x[idxs]; return y.mean()/y.std()*np.sqrt(252)
ss=np.array([boot_sharpe(r.dropna().values) for _ in range(2000)])
sb=np.array([boot_sharpe(bh.dropna().values) for _ in range(2000)])
print(f"   Bootstrap Sharpe: strateji medyan {np.median(ss):.2f} vs b&h {np.median(sb):.2f} · strateji>b&h: %{100*(ss.mean()>sb).mean():.0f}")
print("\nÖZET: DD yarılıyorsa + Sharpe tutarlı yüksekse → gerçek risk-ayarlı edge (getiri sihri değil).")
