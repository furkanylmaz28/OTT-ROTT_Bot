# -*- coding: utf-8 -*-
"""PORTFOLIO-SEVİYESİ simülasyon — EA'nın gerçekte yaptığı gibi TEK ortak kasa,
TÜM semboller AYNI ANDA. Soru: BIST çapında genel düşüşte %20 rezerv yeterli mi,
yoksa korelasyonlu risk ondan sızıyor mu? Bağımsız-sembol testlerinin GÖRMEDİĞİ şey.
WF-opt param. OOS = ortak takvimin ikinci yarısı.
Not: unit_val her BAR'da equity*%10 olarak sabitlenir (o bar için); açık birim
SAYISI persistent takip edilir ki bir bar içindeki semboller birbirinin
kapasitesini gerçek zamanlı görsün (EA'nın TotalNotional() sorgusu gibi)."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS=["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
      "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","KRDMD","ARCLK"]
ER_WIN=20; ER_TH=0.30; LEVELS=[0.015,0.030,0.045]; TAKE=0.010; TRAIL=0.003
TREND_TRAIL=0.030; COMM=0.0010; UNIT_PCT=0.10; RESERVE_PCT=0.20

def fetch(s):
    try:
        d=tv.get_hist(s,'BIST',interval=Interval.in_1_hour,n_bars=5000)
        return d if d is not None and len(d)>800 else None
    except: return None
def er(c,n):
    o=np.full(len(c),np.nan)
    for i in range(n,len(c)):
        v=np.abs(np.diff(c[i-n:i+1])).sum(); o[i]=abs(c[i]-c[i-n])/v if v>0 else np.nan
    return o

print("veri çekiliyor (index korunuyor, hizalama için)...")
raw={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    d=d.rename(columns=str.lower)
    d["_er"]=er(d["close"].values,ER_WIN)
    d["_sma"]=d["close"].rolling(ER_WIN).mean()
    raw[s]=d
print(f"{len(raw)} hisse çekildi. Ortak takvime hizalanıyor (inner join)...")

common_idx=None
for s,d in raw.items():
    common_idx = d.index if common_idx is None else common_idx.intersection(d.index)
common_idx=common_idx.sort_values()
print(f"ortak bar sayısı: {len(common_idx)}")
data={s: d.loc[common_idx] for s,d in raw.items()}
N=len(common_idx); oos_start=int(N*0.5)
print(f"OOS penceresi: {N-oos_start} bar (~%50)\n")

eqclose = {s: data[s]["close"].values for s in data}
eqhigh  = {s: data[s]["high"].values for s in data}
eqlow   = {s: data[s]["low"].values for s in data}
eqsma   = {s: data[s]["_sma"].values for s in data}
eqer    = {s: data[s]["_er"].values for s in data}

equity=1.0
pos = {s:{"G":{}, "T":None} for s in data}
open_units=0
eq_curve=[]; notional_pct=[]; n_open_list=[]

print("simülasyon çalışıyor (tek ortak kasa)...")
for i in range(ER_WIN, N):
    unit_val = equity*UNIT_PCT
    usable = equity*(1-RESERVE_PCT)
    for s in data:
        c=eqclose[s][i]; h=eqhigh[s][i]; l=eqlow[s][i]; sma=eqsma[s][i]; e=eqer[s][i]
        if np.isnan(e) or np.isnan(sma): continue
        p=pos[s]; sideways=e<ER_TH; up=c>sma
        # ---- TREND poz yönet ----
        if p["T"] is not None:
            tr=p["T"]; tr["p"]=max(tr["p"],h)
            gain=(c-tr["e"])/tr["e"]
            exitn = (not sideways and not up) or sideways
            if gain>=TAKE and l<=tr["p"]*(1-TREND_TRAIL): exitn=True
            if exitn:
                pnl=(c/tr["e"]-1)-COMM
                equity += unit_val*pnl; open_units-=1; p["T"]=None
        # ---- GRID (yatay) ----
        if sideways:
            for k,lv in enumerate(LEVELS):
                px=sma*(1-lv)
                if k not in p["G"] and l<=px and (open_units*unit_val)<usable:
                    p["G"][k]={"e":px,"a":False,"p":px}; open_units+=1
            for k in list(p["G"].keys()):
                u=p["G"][k]
                if not u["a"] and h>=u["e"]*(1+TAKE): u["a"]=True; u["p"]=h
                if u["a"]:
                    u["p"]=max(u["p"],h)
                    if l<=u["p"]*(1-TRAIL):
                        pnl=(u["p"]*(1-TRAIL)/u["e"]-1)-COMM
                        equity += unit_val*pnl; open_units-=1; del p["G"][k]
        else:
            for k in list(p["G"].keys()):
                pnl=(c/p["G"][k]["e"]-1)-COMM
                equity += unit_val*pnl; open_units-=1; del p["G"][k]
            if up and p["T"] is None and (open_units*unit_val)<usable:
                p["T"]={"e":c,"p":c}; open_units+=1
    eq_curve.append(equity)
    notional_pct.append(100*open_units*unit_val/equity if equity>0 else 0)
    n_open_list.append(open_units)

eq_curve=np.array(eq_curve); notional_pct=np.array(notional_pct); n_open=np.array(n_open_list)
eqc_oos = eq_curve[oos_start:]/eq_curve[oos_start]
peak=np.maximum.accumulate(eqc_oos); dd=(eqc_oos/peak-1)*100

print("\n=== PORTFÖY SİMÜLASYONU (tek ortak kasa, tüm semboller EA gibi paylaşıyor) ===")
print(f"  OOS toplam getiri: {(eqc_oos[-1]-1)*100:+.0f}%")
print(f"  Max drawdown (portföy, OOS): {dd.min():.1f}%")
print(f"  Ortalama toplam notional: %{notional_pct[oos_start:].mean():.0f} · en yüksek: %{notional_pct[oos_start:].max():.0f} (kap=%80)")
print(f"  %80 kapasitesini AŞAN bar sayısı: {(notional_pct[oos_start:]>80).sum()} / {len(notional_pct[oos_start:])}")
print(f"  Ortalama eşzamanlı açık birim: {n_open[oos_start:].mean():.1f} · en yüksek: {n_open[oos_start:].max()} (toplam {len(data)} hisse × en fazla 4 birim=grid3+trend1)")

# ── en kötü dönem: en büyük tepe-dip düşüşü nerede, o anda notional/açık birim ne?
worst_i = np.argmin(eqc_oos - peak)   # en negatif fark = en dip nokta
print(f"\n  En dip nokta (bar {worst_i}, OOS içinde): drawdown {dd[worst_i]:.1f}%")
print(f"    O anda notional: %{notional_pct[oos_start+worst_i]:.0f} · açık birim: {n_open[oos_start+worst_i]}")
