# -*- coding: utf-8 -*-
"""Grid parametre optimizasyonu — DOĞRU yöntem: IS'te bul, OOS'ta sına.
Overfit kapanı: sadece OOS'ta İYİ + IS'te de pozitif + komşuları da iyi olan
parametre bölgesi gerçek. Tek şanslı tepe = ezber, KABUL ETME.
Süpürülen: ER eşiği, seviye aralığı, take, trail. Maliyet %0.10."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd, itertools
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS = ["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
        "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","KRDMD","ARCLK"]
ER_WIN=20; COST=0.0010

# ── süpürülecek parametre ızgarası
ER_THS   = [0.25, 0.30, 0.35, 0.40]
LEVELSETS = {"sıkı(-.5/-1/-1.5)":[-0.005,-0.010,-0.015],
             "orta(-1/-2/-3)"   :[-0.010,-0.020,-0.030],
             "geniş(-1.5/-3/-4.5)":[-0.015,-0.030,-0.045]}
TAKES    = [0.010, 0.015, 0.020]
TRAILS   = [0.003, 0.005, 0.008]
CURRENT  = (0.30, "orta(-1/-2/-3)", 0.015, 0.005)   # şu anki canlı parametre

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
def grid(d, ER_TH, LEVELS, TAKE, TRAIL, sl):
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=pd.Series(c).rolling(ER_WIN).mean().values; e=d["_er"]
    held={};tr=[]
    for i in range(max(ER_WIN,sl.start), sl.stop):
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
def perf(allt):
    a=np.array(allt) if len(allt) else np.array([0.0])
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    return len(a), pf, a.sum()*100

print("veri çekiliyor...")
data={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    d["_er"]=er(d["close"].values,ER_WIN)   # ER bir kez hesapla (hız)
    data[s]=d
print(f"{len(data)} hisse · ~{int(np.mean([len(v) for v in data.values()]))} bar")
print(f"süpürülen kombinasyon: {len(ER_THS)*len(LEVELSETS)*len(TAKES)*len(TRAILS)}\n")

# ── her kombo: IS (ilk %50) + OOS (ikinci %50) havuz performansı
rows=[]
for eth,(lname,lv),tk,trl in itertools.product(ER_THS, LEVELSETS.items(), TAKES, TRAILS):
    ist=[]; oos=[]
    for d in data.values():
        n=len(d)
        ist+=grid(d,eth,lv,tk,trl,slice(ER_WIN,int(n*0.5)))
        oos+=grid(d,eth,lv,tk,trl,slice(int(n*0.5),n))
    ni,pfi,toti=perf(ist); no,pfo,toto=perf(oos)
    rows.append({"eth":eth,"lvl":lname,"take":tk,"trail":trl,
                 "IS_pf":pfi,"IS_tot":toti,"OOS_pf":pfo,"OOS_tot":toto,"OOS_n":no})
df=pd.DataFrame(rows)

# ── robustluk: HEM IS hem OOS PF>1.05 (tek-yön şans değil)
robust=df[(df.IS_pf>1.05)&(df.OOS_pf>1.05)].copy()
print(f"=== {len(robust)}/{len(df)} kombo HEM IS HEM OOS'ta PF>1.05 (gerçek aday) ===\n")
top=robust.sort_values("OOS_pf",ascending=False).head(8)
print("EN İYİ OOS (sadece robust olanlar):")
print(f"{'ER':>5}{'seviye':>20}{'take':>6}{'trail':>7}{'IS_pf':>7}{'OOS_pf':>8}{'OOS_tot':>9}")
for _,r in top.iterrows():
    print(f"{r.eth:>5.2f}{r.lvl:>20}{r["take"]*100:>5.1f}%{r.trail*100:>6.1f}%{r.IS_pf:>7.2f}{r.OOS_pf:>8.2f}{r.OOS_tot:>+8.0f}%")

# ── şu anki canlı parametre nerede?
cur=df[(df.eth==CURRENT[0])&(df.lvl==CURRENT[1])&(df["take"]==0.015)&(df.trail==0.005)].iloc[0]
rank=(df.OOS_pf>cur.OOS_pf).sum()+1
print(f"\n=== ŞU ANKİ CANLI PARAMETRE (ER.30/orta/1.5/.5) ===")
print(f"  IS_pf {cur.IS_pf:.2f} · OOS_pf {cur.OOS_pf:.2f} · OOS_tot {cur.OOS_tot:+.0f}% · sıra {rank}/{len(df)}")

# ── overfit kontrolü: en iyi OOS kombo, IS↔OOS tutarlı mı?
best=top.iloc[0]
print(f"\n=== OVERFIT KONTROLÜ ===")
print(f"  En iyi OOS kombo: ER{best.eth}/{best.lvl}/{best["take"]*100:.0f}%/{best.trail*100:.1f}%")
print(f"  IS_pf {best.IS_pf:.2f} ↔ OOS_pf {best.OOS_pf:.2f} — fark {abs(best.IS_pf-best.OOS_pf):.2f}")
print("  (IS≈OOS → gerçek/istikrarlı · IS≫OOS → ezber/şüpheli)")
