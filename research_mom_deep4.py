# -*- coding: utf-8 -*-
"""Momentum edge'ini kırmaya/sağlamlaştırmaya devam:
A) EN BASİT: piyasa 200g MA üstündeyse yatır, değilse nakit (DD faydası nereden?)
B) BİRLEŞİK CS+TS: aylık, üst-tercile momentum hisseleri + uptrend filtresi, gerçek
   backtest (maliyet, turnover, Monte Carlo, alt-dönemler). cash=%30 (26yıl merkez tahmin)."""
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
sub=px[LIQ]; d1=sub.pct_change().fillna(0)
CASH_YR=0.30; cash_d=(1+CASH_YR)**(1/252)-1
def perf(r):
    r=r.dropna(); eq=(1+r).cumprod(); yrs=len(r)/252
    return (eq.iloc[-1]**(1/yrs)-1)*100, r.mean()/r.std()*np.sqrt(252), (1-eq/eq.cummax()).max()*100, eq

# ── A) EN BASİT: eşit-ağırlık endeks kendi 200g MA üstünde mi? ──
print("="*76); print("A) EN BASİT piyasa-zamanlaması: eşit-ağ. endeks > kendi N-gün MA → yatır")
idx=(1+d1.mean(axis=1)).cumprod()             # eşit-ağırlık 'endeks'
for N in [100,150,200]:
    ma=idx.rolling(N).mean()
    inmkt=(idx>ma).shift(1).fillna(False)
    port=np.where(inmkt, d1.mean(axis=1), cash_d)
    port=pd.Series(port,index=d1.index)
    for split,so in [("TÜM",False),("OOS",True)]:
        m=port.index>=OOS if so else port.index>=port.index[0]
        cp,shp,ddp,_=perf(port[m]); cb,shb,ddb,_=perf(d1.mean(axis=1)[m])
        f="  <<<" if shp>shb and cp>=cb else ""
        print(f"   MA{N} {split:4s}: mom CAGR{cp:+6.1f}% Sh{shp:.2f} DD{ddp:.0f}% | b&h CAGR{cb:+6.1f}% Sh{shb:.2f} DD{ddb:.0f}%{f}")
    print()

# ── B) BİRLEŞİK CS+TS, gerçek aylık backtest, maliyet+turnover ──
print("="*76); print("B) BİRLEŞİK: aylık, üst-tercile momentum(180g) VE fiyat>200g MA olan hisseler,")
print("   değilse nakit. Maliyet %0.2/işlem, turnover ölçülü.")
ma200=sub.rolling(200).mean()
mom=sub/sub.shift(180)-1
HZ=20
def backtest(so):
    days=sub.index; rows=[]; prev=set(); turn=[]
    ret=[]
    for t in range(220, len(days)-1):
        # aylık rebalans günlerinde seçimi güncelle
        if (t-220)%HZ==0:
            s=mom.iloc[t]; up=sub.iloc[t]>ma200.iloc[t]
            valid=s.notna()&up&(sub.iloc[t]>0)
            sv=s[valid]
            if len(sv)>=6:
                thr=sv.quantile(2/3)
                sel=set(sv[sv>=thr].index)
            else: sel=set()
            turn.append(len(sel^prev)/max(1,len(sel|prev))); prev=sel
        # günlük getiri: seçili hisseler eşit ağırlık, boşsa nakit
        if prev:
            r=d1[list(prev)].iloc[t].mean()
        else:
            r=cash_d
        ret.append((days[t], r))
    R=pd.Series(dict(ret))
    # maliyet: her rebalansta turnover kadar, ay başına düş
    R2=R.copy()
    return R, np.mean(turn)
R,turn=backtest(False)
# maliyet uygula (ayda bir, ortalama turnover*0.002)
recost=turn*0.002/HZ
R_net=R-recost
bh=d1.mean(axis=1).reindex(R.index).fillna(0)
for split,so in [("TÜM",False),("OOS",True)]:
    m=R.index>=OOS if so else R.index>=R.index[0]
    cp,shp,ddp,eqp=perf(R_net[m]); cb,shb,ddb,_=perf(bh[m])
    print(f"   {split:4s}: strateji CAGR{cp:+6.1f}% Sharpe{shp:.2f} MaxDD{ddp:.0f}% | b&h CAGR{cb:+6.1f}% Sharpe{shb:.2f} DD{ddb:.0f}%")
print(f"   ort. aylık turnover: %{turn*100:.0f} · yıllık ~%{turn*100*12:.0f} devir (maliyet-dostu)")
# alt-dönem
print("   Alt-dönem Sharpe (strateji vs b&h):")
for y0 in [2001,2007,2013,2019]:
    mm=(R.index.year>=y0)&(R.index.year<y0+6)
    if mm.sum()>200:
        _,sp,_,_=perf(R_net[mm]); _,sb,_,_=perf(bh[mm])
        print(f"     {y0}-{y0+5}: {sp:.2f} vs {sb:.2f}")
# Monte Carlo (aylık fazla getiri blok-bootstrap)
exc=(R_net-bh).dropna()
mo=exc.resample("21D").sum().dropna().values if hasattr(exc,'resample') else exc.values
rng=np.random.default_rng(7)
sims=np.array([rng.choice(mo,len(mo),replace=True).mean() for _ in range(5000)])
print(f"   Monte Carlo fazla getiri pozitif: %{100*(sims>0).mean():.0f}")
print("\nKARAR: DD yarıya + Sharpe>b&h her rejimde + MC>90% → uygulanabilir edge.")
