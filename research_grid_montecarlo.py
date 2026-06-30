# -*- coding: utf-8 -*-
"""Monte Carlo — YENİ WF-opt grid parametreleri (geniş -1.5/-3/-4.5, take 1.0, trail 0.3).
İşlem havuzunu bootstrap'le (sırayı/şansı karıştır) → dağılım: medyan getiri,
kayıp olasılığı, max drawdown, iflas riski. Tek tarihsel yol değil, BİNLERCE olası yol."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS=["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
      "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","KRDMD","ARCLK"]
ER_WIN=20; ER_TH=0.30; LEVELS=[-0.015,-0.030,-0.045]; TAKE=0.010; TRAIL=0.003; COST=0.0010
UNIT_FRAC=0.10        # işlem başı ~kasanın %10'u (EA'daki InpUnitPct)
HORIZON=300           # MC ufku: bir hesabın ~birkaç aylık işlem sayısı
NRUNS=5000

def fetch(s):
    try:
        d=tv.get_hist(s,'BIST',interval=Interval.in_1_hour,n_bars=5000)
        return d.rename(columns=str.lower).reset_index(drop=True) if d is not None and len(d)>800 else None
    except: return None
def er(c,n):
    o=np.full(len(c),np.nan)
    for i in range(n,len(c)):
        v=np.abs(np.diff(c[i-n:i+1])).sum(); o[i]=abs(c[i]-c[i-n])/v if v>0 else np.nan
    return o
def grid(d, oos_only=True):
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=pd.Series(c).rolling(ER_WIN).mean().values; e=er(c,ER_WIN)
    a = int(len(c)*0.5) if oos_only else ER_WIN     # sadece OOS (ikinci yarı) = muhafazakâr
    held={};tr=[]
    for i in range(max(ER_WIN,a),len(c)):
        if np.isnan(e[i]) or np.isnan(sma[i]):continue
        if e[i]<ER_TH:
            ce=sma[i]
            for k,lv in enumerate(LEVELS):
                px=ce*(1+lv)
                if k not in held and l[i]<=px:held[k]={"e":px,"a":False,"p":px}
            for k in list(held.keys()):
                u=held[k];tgt=u["e"]*(1+TAKE)
                if not u["a"] and h[i]>=tgt:u["a"]=True;u["p"]=h[i]
                if u["a"]:
                    u["p"]=max(u["p"],h[i])
                    if l[i]<=u["p"]*(1-TRAIL):tr.append((u["p"]*(1-TRAIL)/u["e"]-1)-COST);del held[k]
        else:
            for k in list(held.keys()):tr.append((c[i]/held[k]["e"]-1)-COST);del held[k]
    for k in held:tr.append((c[-1]/held[k]["e"]-1)-COST)
    return tr

print("veri çekiliyor + işlem havuzu (OOS)...")
pool=[]
for s in SYMS:
    d=fetch(s)
    if d is not None: pool+=grid(d, oos_only=True)
pool=np.array(pool)
gl=abs(pool[pool<0].sum()); pf=(pool[pool>0].sum()/gl) if gl>0 else 99
print(f"havuz: {len(pool)} işlem · kazanan %{100*(pool>0).mean():.0f} · PF {pf:.2f} · ort/işlem {pool.mean()*100:+.3f}%\n")

# ── MC: her koşu HORIZON işlemi havuzdan rastgele çek, kasayı bileşik büyüt
rng=np.random.default_rng(42)
finals=np.zeros(NRUNS); maxdds=np.zeros(NRUNS)
for j in range(NRUNS):
    samp=rng.choice(pool, size=HORIZON, replace=True)
    eq=np.cumprod(1.0 + UNIT_FRAC*samp)          # kasanın %10'u/işlem
    peak=np.maximum.accumulate(eq); dd=(eq/peak-1.0).min()
    finals[j]=eq[-1]-1.0; maxdds[j]=dd

# ── PF bootstrap (edge sampling'e dayanıklı mı?)
pfs=np.zeros(NRUNS)
for j in range(NRUNS):
    s=rng.choice(pool,size=len(pool),replace=True)
    g=abs(s[s<0].sum()); pfs[j]=(s[s>0].sum()/g) if g>0 else 99

print(f"=== MONTE CARLO ({NRUNS} koşu · {HORIZON} işlem/koşu · %{UNIT_FRAC*100:.0f} birim · 1× kaldıraç) ===")
print(f"  Getiri:   medyan {np.median(finals)*100:+.0f}% · en kötü %5 {np.percentile(finals,5)*100:+.0f}% · en iyi %5 {np.percentile(finals,95)*100:+.0f}%")
print(f"  KAYIP olasılığı (final<0):     %{100*(finals<0).mean():.1f}")
print(f"  Max drawdown: medyan {np.median(maxdds)*100:.0f}% · en kötü %5 {np.percentile(maxdds,5)*100:.0f}%")
print(f"  İFLAS riski (DD < -%50):       %{100*(maxdds<-0.50).mean():.1f}")
print(f"  PF bootstrap: medyan {np.median(pfs):.2f} · en kötü %5 {np.percentile(pfs,5):.2f}  (>1 ise edge dayanıklı)")
print(f"\n  ⚠️ Kaldıraç: bu 1×. VIOP doğal kaldıraçlı → toplam notional ≤2× kuralı (DD 2× büyür).")
