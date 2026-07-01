# -*- coding: utf-8 -*-
"""Felaket-stop testi: grid birimi girişin -%STOP altına inerse piyasadan kapat.
Yeni WF-opt param (geniş -1.5/-3/-4.5, take 1.0, trail 0.3). Stopsuz vs -4/-6/-8%.
OOS (ikinci yarı). Amaç: yavaş sızıntıyı kesip edge'i BOZMADAN korumak mümkün mü?"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS=["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
      "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","KRDMD","ARCLK"]
ER_WIN=20; ER_TH=0.30; LEVELS=[-0.015,-0.030,-0.045]; TAKE=0.010; TRAIL=0.003; COST=0.0010

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
def grid(d, STOP, a):
    """STOP=None → stopsuz. float → girişin -%STOP altında piyasadan kapat."""
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=d["_sma"]; e=d["_er"]; held={};tr=[]
    for i in range(max(ER_WIN,a),len(c)):
        if np.isnan(e[i]) or np.isnan(sma[i]):continue
        if e[i]<ER_TH:
            ce=sma[i]
            for k,lv in enumerate(LEVELS):
                px=ce*(1+lv)
                if k not in held and l[i]<=px:held[k]={"e":px,"a":False,"p":px}
            for k in list(held.keys()):
                u=held[k]
                # 1) FELAKET STOP (önce kontrol et)
                if STOP is not None and l[i] <= u["e"]*(1-STOP):
                    tr.append((-STOP)-COST); del held[k]; continue
                # 2) trailing
                if not u["a"] and h[i]>=u["e"]*(1+TAKE): u["a"]=True; u["p"]=h[i]
                if u["a"]:
                    u["p"]=max(u["p"],h[i])
                    if l[i]<=u["p"]*(1-TRAIL): tr.append((u["p"]*(1-TRAIL)/u["e"]-1)-COST); del held[k]
        else:
            for k in list(held.keys()):tr.append((c[i]/held[k]["e"]-1)-COST);del held[k]
    for k in held:tr.append((c[-1]/held[k]["e"]-1)-COST)
    return tr

print("veri çekiliyor...")
data={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    d["_er"]=er(d["close"].values,ER_WIN); d["_sma"]=pd.Series(d["close"].values).rolling(ER_WIN).mean().values
    data[s]=d
print(f"{len(data)} hisse · OOS (ikinci yarı)\n")
print(f"{'stop':>10}{'işlem':>8}{'kazanan':>9}{'PF':>7}{'toplam':>9}{'en kötü işlem':>15}")
for STOP in [None, 0.04, 0.06, 0.08]:
    allt=[]
    for d in data.values():
        n=len(d); allt+=grid(d, STOP, int(n*0.5))
    a=np.array(allt); gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    lbl = "STOPSUZ" if STOP is None else f"-%{STOP*100:.0f}"
    print(f"{lbl:>10}{len(a):>8}{100*(a>0).mean():>8.0f}%{pf:>7.2f}{a.sum()*100:>+8.0f}%{a.min()*100:>+13.1f}%")
