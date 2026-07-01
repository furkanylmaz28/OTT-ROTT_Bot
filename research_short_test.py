# -*- coding: utf-8 -*-
"""SHORT eklemek yarıyor mu? Yeni WF-opt param, tam rejim simülasyonu (grid+trend),
long-only vs long+short, OOS (ikinci yarı). EA mantığının birebir backtesti."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS=["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
      "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","KRDMD","ARCLK"]
ER_WIN=20; ER_TH=0.30; LEVELS=[0.015,0.030,0.045]   # ±% (long: alt, short: üst)
TAKE=0.010; TRAIL=0.003; TREND_TRAIL=0.030; COST=0.0010

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

def simulate(d, allow_short, a):
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=pd.Series(c).rolling(ER_WIN).mean().values; e=d["_er"]
    HL={}; HS={}; trend=None        # HL/HS: grid long/short birimleri; trend: {side,e,p}
    tr=[]
    for i in range(max(ER_WIN,a), len(c)):
        if np.isnan(e[i]) or np.isnan(sma[i]): continue
        ce=sma[i]; side_w = e[i] < ER_TH
        up = c[i] > ce
        # ---- TREND pozisyonunu yönet ----
        if trend:
            if trend["side"]=="L":
                trend["p"]=max(trend["p"], h[i])
                gain=(c[i]-trend["e"])/trend["e"]
                exit_now = (not side_w and not up) or side_w   # aşağı trend ya da yataya dönüş
                if gain>=TAKE and l[i]<=trend["p"]*(1-TREND_TRAIL): exit_now=True
                if exit_now: tr.append((c[i]/trend["e"]-1)-COST); trend=None
            else:  # short trend
                trend["p"]=min(trend["p"], l[i])
                gain=(trend["e"]-c[i])/trend["e"]
                exit_now = (not side_w and up) or side_w
                if gain>=TAKE and h[i]>=trend["p"]*(1+TREND_TRAIL): exit_now=True
                if exit_now: tr.append((trend["e"]/c[i]-1)-COST); trend=None
        # ---- YATAY → GRID ----
        if side_w:
            # grid LONG: dipten al
            for k,lv in enumerate(LEVELS):
                px=ce*(1-lv)
                if k not in HL and l[i]<=px: HL[k]={"e":px,"a":False,"p":px}
            for k in list(HL.keys()):
                u=HL[k];
                if not u["a"] and h[i]>=u["e"]*(1+TAKE): u["a"]=True; u["p"]=h[i]
                if u["a"]:
                    u["p"]=max(u["p"],h[i])
                    if l[i]<=u["p"]*(1-TRAIL): tr.append((u["p"]*(1-TRAIL)/u["e"]-1)-COST); del HL[k]
            if allow_short:
                # grid SHORT: tepeden sat
                for k,lv in enumerate(LEVELS):
                    px=ce*(1+lv)
                    if k not in HS and h[i]>=px: HS[k]={"e":px,"a":False,"p":px}
                for k in list(HS.keys()):
                    u=HS[k]
                    if not u["a"] and l[i]<=u["e"]*(1-TAKE): u["a"]=True; u["p"]=l[i]
                    if u["a"]:
                        u["p"]=min(u["p"],l[i])
                        if h[i]>=u["p"]*(1+TRAIL): tr.append((u["e"]/(u["p"]*(1+TRAIL))-1)-COST); del HS[k]
        else:
            # TREND rejimi → grid birimlerini kapat (close'da)
            for k in list(HL.keys()): tr.append((c[i]/HL[k]["e"]-1)-COST); del HL[k]
            for k in list(HS.keys()): tr.append((HS[k]["e"]/c[i]-1)-COST); del HS[k]
            # trend giriş
            if up and trend is None:
                trend={"side":"L","e":c[i],"p":c[i]}
            elif (not up) and allow_short and trend is None:
                trend={"side":"S","e":c[i],"p":c[i]}
    return tr

def rep(tr):
    a=np.array(tr) if len(tr) else np.array([0.0])
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    return len(a),100*(a>0).mean(),pf,a.sum()*100

print("veri çekiliyor...")
data={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    d["_er"]=er(d["close"].values,ER_WIN); data[s]=d
print(f"{len(data)} hisse · OOS (ikinci yarı)\n")

for nm,allow in [("LONG-ONLY (mevcut)",False),("LONG + SHORT",True)]:
    allt=[]
    for d in data.values():
        n=len(d); allt+=simulate(d, allow, int(n*0.5))
    N,wr,pf,tot=rep(allt)
    print(f"  {nm:20s}: {N:>4} işlem · kazanan %{wr:.0f} · PF {pf:.2f} · toplam {tot:+.0f}%")
