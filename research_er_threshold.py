# -*- coding: utf-8 -*-
"""ER eşiği (InpER_Th=0.30) doğru mu? Diğer parametreler EA'daki gibi SABİT
(geniş -1.5/-3/-4.5, take 1.0, trail 0.3) — sadece ER eşiği süpürülüyor.
Rolling-WF (her pencerede hangi ER kazanıyor?) + kilitli final holdout."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS=["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
      "PGSUS","TOASO","BIMAS","TCELL"]
ER_WIN=20; LEVELS=[0.015,0.030,0.045]; TAKE=0.010; TRAIL=0.003; COST=0.0010
ER_CANDIDATES=[0.20,0.25,0.30,0.35,0.40,0.45]
NWIN=6

def fetch(s):
    try:
        d=tv.get_hist(s,'BIST',interval=Interval.in_1_hour,n_bars=5000)
        return d.rename(columns=str.lower).reset_index(drop=True) if d is not None and len(d)>1200 else None
    except: return None
def er(c,n):
    o=np.full(len(c),np.nan)
    for i in range(n,len(c)):
        v=np.abs(np.diff(c[i-n:i+1])).sum(); o[i]=abs(c[i]-c[i-n])/v if v>0 else np.nan
    return o
def grid(d, ER_TH, a, b):
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=d["_sma"]; e=d["_er"]; held={};tr=[]
    for i in range(max(ER_WIN,a),b):
        if np.isnan(e[i]) or np.isnan(sma[i]):continue
        if e[i]<ER_TH:
            ce=sma[i]
            for k,lv in enumerate(LEVELS):
                px=ce*(1-lv)
                if k not in held and l[i]<=px:held[k]={"e":px,"a":False,"p":px}
            for k in list(held.keys()):
                u=held[k]
                if not u["a"] and h[i]>=u["e"]*(1+TAKE): u["a"]=True; u["p"]=h[i]
                if u["a"]:
                    u["p"]=max(u["p"],h[i])
                    if l[i]<=u["p"]*(1-TRAIL): tr.append((u["p"]*(1-TRAIL)/u["e"]-1)-COST); del held[k]
        else:
            for k in list(held.keys()): tr.append((c[i]/held[k]["e"]-1)-COST); del held[k]
    for k in held: tr.append((c[-1]/held[k]["e"]-1)-COST)
    return tr
def pf_of(allt):
    a=np.array(allt) if len(allt) else np.array([0.0])
    gl=abs(a[a<0].sum()); return (a[a>0].sum()/gl) if gl>0 else (99 if a.sum()>0 else 0), a.sum()*100, len(a)
def runset(eth,a,b):
    allt=[]
    for d in data.values(): allt+=grid(d,eth,a,b)
    return allt

print("veri çekiliyor...")
data={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    d["_er"]=er(d["close"].values,ER_WIN); d["_sma"]=pd.Series(d["close"].values).rolling(ER_WIN).mean().values
    data[s]=d
N=min(len(v) for v in data.values())
print(f"{len(data)} hisse · min {N} bar\n")
edges=[int(N*i/NWIN) for i in range(NWIN+1)]

print("=== ROLLING WF — sadece ER eşiği seçiliyor (diğerleri sabit: geniş/1.0/0.3) ===")
chosen=[]
for t in range(1, NWIN-1):
    tr_a,tr_b=edges[0],edges[t]; te_a,te_b=edges[t],edges[t+1]
    best=None;bestpf=-9
    for eth in ER_CANDIDATES:
        pf,tot,nn=pf_of(runset(eth,tr_a,tr_b))
        if nn>=30 and pf>bestpf: bestpf=pf;best=eth
    pf,tot,nn=pf_of(runset(best,te_a,te_b))
    chosen.append(best)
    print(f"  pencere {t}: seçilen ER<{best:.2f} (train PF {bestpf:.2f}) → OOS PF {pf:.2f} ({tot:+.0f}%, {nn} işlem)")
from collections import Counter
print(f"  ► seçilen ER dağılımı: {Counter(chosen)}")

print(f"\n=== KİLİTLİ FINAL HOLDOUT — her ER adayı, mühürlü veride ===")
h_a,h_b=edges[NWIN-1],edges[NWIN]
for eth in ER_CANDIDATES:
    pf,tot,nn=pf_of(runset(eth,h_a,h_b))
    mark = "  <- ŞU AN CANLI" if eth==0.30 else ""
    print(f"  ER<{eth:.2f}: PF {pf:.2f} · {tot:+.0f}% · {nn} işlem{mark}")

print(f"\n=== TAM OOS (ikinci yarı, tüm veri) — her ER adayı ===")
for eth in ER_CANDIDATES:
    pf,tot,nn=pf_of(runset(eth,int(N*0.5),N))
    mark = "  <- ŞU AN CANLI" if eth==0.30 else ""
    print(f"  ER<{eth:.2f}: PF {pf:.2f} · {tot:+.0f}% · {nn} işlem{mark}")
