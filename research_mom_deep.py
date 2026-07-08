# -*- coding: utf-8 -*-
"""Kapsamlı kesitsel MOMENTUM araştırması — 26 yıl BIST, dürüst holdout.
Ragged panel (her tarihte mevcut hisseleri sıralar). Skip-month standardı.
long-only top (retail-gerçekçi) + long-short. Monotonluk, t-stat, IS/OOS,
alt-dönem, maliyet duyarlılığı, Monte Carlo. Kendini kandırmama disiplini:
tüm ızgara raporlanır (cherry-pick yok), holdout ayrı tutulur."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

px=pd.read_pickle("_bist_px.pkl").sort_index()
rets_all=px.pct_change()
dates=px.index
OOS_START=pd.Timestamp("2018-01-01")   # 2000-2017 geliştirme / 2018-2026 dürüst holdout
print(f"Veri: {px.shape[1]} sembol × {px.shape[0]} gün ({dates[0].date()}->{dates[-1].date()})")
print(f"Holdout (OOS) başlangıcı: {OOS_START.date()}\n")

def run(lookback, skip, horizon, ngroups=5, cost=0.002, min_names=20):
    """Kesitsel momentum. Her 'horizon' günde bir rebalans (çakışmasız).
       Dönen: rebalans bazında (tarih, long_only_excess, long_short)."""
    idx=np.arange(lookback+skip, len(dates)-horizon, horizon)
    recs=[]
    for t in idx:
        sig=px.iloc[t-skip]/px.iloc[t-skip-lookback]-1        # skip-month: son 'skip' gün hariç
        fwd=px.iloc[t+horizon]/px.iloc[t]-1
        m=sig.notna()&fwd.notna()&(px.iloc[t]>0)
        if m.sum()<min_names: continue
        s=sig[m]; f=fwd[m]
        try: q=pd.qcut(s.rank(method="first"), ngroups, labels=False)
        except: continue
        gmeans=[f[q==g].mean() for g in range(ngroups)]
        top=f[q==ngroups-1].mean(); bot=f[q==0].mean(); mkt=f.mean()
        recs.append((dates[t], top-mkt-cost, top-bot-2*cost, gmeans))
    return recs

def stats(vals):
    a=np.array(vals); n=len(a)
    if n<2: return (n,0,0,0)
    t=a.mean()/(a.std(ddof=1)/np.sqrt(n))
    return n, a.mean()*100, t, 100*(a>0).mean()

# ═══ 1) IZGARA: lookback × horizon (long-only excess), IS ve OOS ayrı ═══
print("="*78)
print("1) MOMENTUM IZGARASI — hücre: long-only üst-quintile FAZLA getiri (net%/t-stat)")
print("   skip=21g (son ay hariç, akademik standart). SOL=tüm, SAĞ=OOS(2018+)\n")
LBs=[60,120,180,250]; HZs=[10,20,60]
for split in ["TÜM","OOS"]:
    print(f"  --- {split} ---")
    hdr="  LB\\HZ" + "".join(f"{h:>16}g" for h in HZs)
    print(hdr)
    for lb in LBs:
        row=f"  {lb:>5}"
        for hz in HZs:
            recs=run(lb,21,hz)
            if split=="OOS": recs=[r for r in recs if r[0]>=OOS_START]
            n,mean,t,hit=stats([r[1] for r in recs])
            row+=f"{mean:>8.2f}/{t:>5.1f}"
        print(row)
    print()

# ═══ 2) EN İYİ ADAY — monotonluk + long-short + alt dönemler ═══
print("="*78)
best=(120,21,20)   # akademik klasik ~6ay lookback, 1ay hold — önden seçili (data-snoop değil)
recs=run(*best,ngroups=5)
print(f"2) KLASİK KONFİG lookback={best[0]} skip={best[1]} horizon={best[2]} (önden seçili, akademik):")
n,mL,tL,hL=stats([r[1] for r in recs]); _,mS,tS,hS=stats([r[2] for r in recs])
print(f"   Long-only fazla:  {mL:+.2f}%/reb · t={tL:.2f} · isabet={hL:.0f}% · n={n}")
print(f"   Long-short:       {mS:+.2f}%/reb · t={tS:.2f} · isabet={hS:.0f}%")
# quintile monotonluk (ortalama gradyan)
gm=np.array([r[3] for r in recs])
qavg=np.nanmean(gm,axis=0)*100
print(f"   Quintile gradyan (düşük→yüksek mom): "+" ".join(f"{x:+.2f}" for x in qavg)+
      ("  MONOTON✓" if all(qavg[i]<=qavg[i+1] for i in range(len(qavg)-1)) else "  monoton değil"))
# alt-dönemler (5'er yıl)
print("   Alt-dönem long-only fazla (kararlılık):")
for y0 in [2000,2006,2012,2018,2022]:
    y1=y0+6
    sub=[r[1] for r in recs if y0<=r[0].year<y1]
    if len(sub)>=3:
        _,m,t,h=stats(sub); print(f"     {y0}-{y1-1}: {m:+.2f}%/reb (t={t:.1f}, n={len(sub)})")

# ═══ 3) GERÇEK BACKTEST long-only top-quintile, aylık, equity ═══
print("="*78)
print("3) GERÇEK BACKTEST — long-only üst quintile, ~aylık, eşit ağırlık")
port=[]; mkt=[]; ts=[]
lb,skip,hz=best
for t in range(lb+skip, len(dates)-hz, hz):
    sig=px.iloc[t-skip]/px.iloc[t-skip-lb]-1; fwd=px.iloc[t+hz]/px.iloc[t]-1
    m=sig.notna()&fwd.notna()&(px.iloc[t]>0)
    if m.sum()<20: continue
    s=sig[m]; f=fwd[m]
    q=pd.qcut(s.rank(method="first"),5,labels=False)
    port.append(f[q==4].mean()-0.002); mkt.append(f.mean()); ts.append(dates[t])
port=np.array(port); mkt=np.array(mkt)
eq=np.cumprod(1+port); eqm=np.cumprod(1+mkt)
yrs=(ts[-1]-ts[0]).days/365.25
cagr=(eq[-1]**(1/yrs)-1)*100; cagrm=(eqm[-1]**(1/yrs)-1)*100
sharpe=port.mean()/port.std()*np.sqrt(len(port)/yrs)
dd=1-eq/np.maximum.accumulate(eq); maxdd=dd.max()*100
print(f"   Momentum portföyü: CAGR {cagr:+.1f}% · Sharpe {sharpe:.2f} · MaxDD {maxdd:.0f}% · {len(port)} rebalans/{yrs:.0f}yıl")
print(f"   Piyasa (eşit ağ.):  CAGR {cagrm:+.1f}%")
print(f"   Toplam: momentum {eq[-1]:.1f}x · piyasa {eqm[-1]:.1f}x")
# OOS dilim
oi=[i for i,d in enumerate(ts) if d>=OOS_START]
if oi:
    po=port[oi[0]:]; eqo=np.cumprod(1+po)
    yo=(ts[-1]-ts[oi[0]]).days/365.25
    print(f"   >>> OOS (2018+): momentum {(eqo[-1]**(1/yo)-1)*100:+.1f}%/yıl vs piyasa {(np.cumprod(1+mkt[oi[0]:])[-1]**(1/yo)-1)*100:+.1f}%/yıl")

# ═══ 4) MONTE CARLO (rebalans getirilerini bootstrap) ═══
print("="*78)
exc=port-mkt   # piyasa-üstü fazla getiri serisi
rng=np.random.default_rng(1)
sims=np.array([rng.choice(exc,len(exc),replace=True).mean()*100 for _ in range(5000)])
print(f"4) Monte Carlo (5000, {len(exc)} rebalans fazla-getiri):")
print(f"   Pozitif fazla getiri: {100*(sims>0).mean():.0f}% · medyan {np.median(sims):+.3f}%/reb · %5 {np.percentile(sims,5):+.3f}%")
print("\nKARAR: t>2 (long-only fazla) + monoton + OOS≈TÜM + MC>90% → GERÇEK edge adayı.")
