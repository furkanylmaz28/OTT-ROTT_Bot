# -*- coding: utf-8 -*-
"""Likidite filtresi — YÜKSEK-hacimli (likit, düşük spread proxy'si) hisseler
grid'e daha mı iyi? Gerçek bid-ask spread verisi yok; ORTALAMA HACİM proxy.
Kesitsel: hisseleri hacme göre ikiye böl, OOS'ta PF/getiri kıyasla.
Dürüstlük notu: gerçek slippage'ı ÖLÇMÜYOR, sadece likiditenin edge'e etkisini
kesitsel gösteriyor (MAX filtresi testiyle aynı metodoloji)."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS=["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
      "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","KRDMD","ARCLK","ASTOR","HEKTS",
      "ODAS","KONTR","DOAS","VESTL","ENKAI","TKFEN","ALARK"]
ER_WIN=20; ER_TH=0.30; LEVELS=[0.015,0.030,0.045]; TAKE=0.010; TRAIL=0.003; COST=0.0010

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
def grid(d, a):
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=d["_sma"]; e=d["_er"]; held={};tr=[]
    for i in range(max(ER_WIN,a),len(c)):
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
def rep(tr):
    a=np.array(tr) if len(tr) else np.array([0.0])
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    return len(a),100*(a>0).mean(),pf,a.sum()*100

print("veri çekiliyor (hacim dahil)...")
data={}; liq={}
for s in SYMS:
    d=fetch(s)
    if d is None or "volume" not in d.columns: continue
    d["_er"]=er(d["close"].values,ER_WIN); d["_sma"]=pd.Series(d["close"].values).rolling(ER_WIN).mean()
    # likidite proxy: OOS penceresindeki ortalama GÜNLÜK CİRO (hacim × fiyat)
    n=len(d); oos=d.iloc[int(n*0.5):]
    liq[s] = float((oos["volume"]*oos["close"]).mean())
    data[s]=d
print(f"{len(data)} hisse (hacim verisi mevcut)\n")

med=np.median(list(liq.values()))
high_liq=[s for s in data if liq[s]>=med]; low_liq=[s for s in data if liq[s]<med]
print("=== KESİTSEL: yüksek-likidite vs düşük-likidite (grid, OOS ikinci yarı) ===")
print(f"  Yüksek-likidite: {', '.join(high_liq)}")
print(f"  Düşük-likidite:  {', '.join(low_liq)}")
for nm,grp in [("YÜKSEK-likidite",high_liq),("DÜŞÜK-likidite",low_liq)]:
    allt=[]
    for s in grp:
        d=data[s]; n=len(d); allt+=grid(d, int(n*0.5))
    N,wr,pf,tot=rep(allt)
    print(f"  {nm:16s}: {N:>4} işlem · kazanan %{wr:.0f} · PF {pf:.2f} · toplam {tot:+.0f}%")

# ── Sadece EN likit üst-%25 vs EN illikit alt-%25 (uç karşılaştırma)
srt=sorted(liq.items(), key=lambda x:x[1])
q=len(srt)//4
bottom25=[s for s,_ in srt[:q]]; top25=[s for s,_ in srt[-q:]]
print(f"\n=== UÇ KARŞILAŞTIRMA (en likit %25 vs en illikit %25) ===")
for nm,grp in [(f"EN LİKİT %25 ({len(top25)})",top25),(f"EN İLLİKİT %25 ({len(bottom25)})",bottom25)]:
    allt=[]
    for s in grp:
        d=data[s]; n=len(d); allt+=grid(d, int(n*0.5))
    N,wr,pf,tot=rep(allt)
    print(f"  {nm:24s}: {N:>4} işlem · kazanan %{wr:.0f} · PF {pf:.2f} · toplam {tot:+.0f}%")
