# -*- coding: utf-8 -*-
"""ROLLING walk-forward — "binlerce kombo"nun kendini kandırmayan hâli.
Parametreyi GENİŞLEYEN geçmişte seç → HEP bir sonraki görülmemiş pencerede ölç.
Kazanan combo birçok OOS penceresinde tutmalı. + KİLİTLİ final holdout (son dilim,
seçimde HİÇ kullanılmaz; kazanan orada bir kez sınanır).
Karşılaştırma: (a) her pencere yeniden-seç (gerçek WF), (b) sabit WF-opt param,
(c) eski param. Combo STABİLİTESİ de raporlanır (zıplıyorsa overfit)."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd, itertools
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS = ["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
        "PGSUS","TOASO","BIMAS","TCELL"]
ER_WIN=20; COST=0.0010
ER_THS=[0.25,0.30,0.35,0.40]
LEVELSETS={"sıkı":[-0.005,-0.010,-0.015],"orta":[-0.010,-0.020,-0.030],"geniş":[-0.015,-0.030,-0.045]}
TAKES=[0.010,0.015,0.020]; TRAILS=[0.003,0.005,0.008]
COMBOS=list(itertools.product(ER_THS,LEVELSETS.items(),TAKES,TRAILS))
OLD=(0.30,("orta",LEVELSETS["orta"]),0.015,0.005); FIXED=(0.30,("geniş",LEVELSETS["geniş"]),0.010,0.003)   # eski vs WF-opt sabit
NWIN=6                 # pencere sayısı (son = kilitli holdout)

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
def grid(d,ER_TH,LEVELS,TAKE,TRAIL,a,b):
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=d["_sma"]; e=d["_er"]; held={};tr=[]
    for i in range(max(ER_WIN,a),b):
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
def pf_of(allt):
    a=np.array(allt) if len(allt) else np.array([0.0])
    gl=abs(a[a<0].sum()); return (a[a>0].sum()/gl) if gl>0 else (99 if a.sum()>0 else 0), a.sum()*100, len(a)
def runset(combo,a,b):
    eth,(ln,lv),tk,trl=combo; allt=[]
    for d in data.values(): allt+=grid(d,eth,lv,tk,trl,a,b)
    return allt

print("veri çekiliyor...")
data={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    d["_er"]=er(d["close"].values,ER_WIN); d["_sma"]=pd.Series(d["close"].values).rolling(ER_WIN).mean().values
    data[s]=d
N=min(len(v) for v in data.values())
print(f"{len(data)} hisse · min {N} bar · {len(COMBOS)} kombo · {NWIN} pencere\n")
edges=[int(N*i/NWIN) for i in range(NWIN+1)]

# ── ROLLING WF: pencere t için, [0..t) eğit (en iyi PF combo), [t..t+1) ölç (OOS)
print("=== ROLLING WALK-FORWARD (her pencere yeniden seç, hep görülmemişte ölç) ===")
wf=[]; chosen=[]
for t in range(1, NWIN-1):              # son pencereyi (NWIN-1) holdout'a sakla
    tr_a,tr_b=edges[0],edges[t]; te_a,te_b=edges[t],edges[t+1]
    best=None;bestpf=-9
    for cb in COMBOS:
        pf,tot,nn=pf_of(runset(cb,tr_a,tr_b))
        if nn>=30 and pf>bestpf: bestpf=pf;best=cb
    pf,tot,nn=pf_of(runset(best,te_a,te_b))    # OOS ölç
    wf+=runset(best,te_a,te_b)
    eth,(ln,lv),tk,trl=best; chosen.append((ln,tk,trl))
    print(f"  pencere {t}: seçilen=geniş?{ln}/take{tk*100:.0f}/trail{trl*100:.1f} (train PF {bestpf:.2f}) → OOS PF {pf:.2f} ({tot:+.0f}%, {nn} işlem)")
wpf,wtot,wn=pf_of(wf)
print(f"  ► BİRLEŞİK rolling-WF OOS: PF {wpf:.2f} · {wtot:+.0f}% · {wn} işlem")
# stabilite
from collections import Counter
print(f"  ► seçilen seviye-seti dağılımı: {Counter([c[0] for c in chosen])}  (hep aynı = istikrarlı/gerçek)")

# ── KİLİTLİ HOLDOUT: son dilim, seçimde HİÇ kullanılmadı
h_a,h_b=edges[NWIN-1],edges[NWIN]
print(f"\n=== KİLİTLİ FINAL HOLDOUT (son {h_b-h_a} bar, seçimde hiç görülmedi) ===")
for nm,cb in [("ESKİ param",OLD),("WF-opt SABİT",FIXED)]:
    pf,tot,nn=pf_of(runset(cb,h_a,h_b))
    print(f"  {nm:14s}: PF {pf:.2f} · {tot:+.0f}% · {nn} işlem")
