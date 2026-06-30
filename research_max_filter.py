# -*- coding: utf-8 -*-
"""MAX etkisi (loto-hisse anomalisi) BIST grid'e yarıyor mu?
Test 1 (kesitsel): hisseleri low-MAX / high-MAX böl → grid hangi grupta iyi?
Test 2 (zaman-serisi kapı): hisse son W barda loto-sıçraması yaptıysa grid girişi engelle.
Hep OOS (ilk yarı / ikinci yarı), senin maliyetin %0.10."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

SYMS = ["GARAN","THYAO","ASELS","EREGL","SISE","KCHOL","AKBNK","SASA","TUPRS","FROTO",
        "PGSUS","TOASO","BIMAS","TCELL","YKBNK","VAKBN","ISCTR","HALKB","PETKM","KRDMD",
        "ARCLK","TKFEN","ALARK","ASTOR","HEKTS","ODAS","KONTR","DOAS","VESTL","ENKAI"]
ER_WIN=20; ER_TH=0.30; LEVELS=[-0.01,-0.02,-0.03]; TAKE=0.015; TRAIL=0.005
MAX_WIN=150          # loto skoru penceresi (~1 ay H1 bar)
COST=0.0010

def fetch(s):
    try:
        d = tv.get_hist(s,'BIST',interval=Interval.in_1_hour,n_bars=5000)
        return d.rename(columns=str.lower).reset_index(drop=True) if d is not None and len(d)>800 else None
    except: return None

def er(c,n):
    o=np.full(len(c),np.nan)
    for i in range(n,len(c)):
        v=np.abs(np.diff(c[i-n:i+1])).sum(); o[i]=abs(c[i]-c[i-n])/v if v>0 else np.nan
    return o

def max_score(c):
    """Her bar: trailing MAX_WIN bardaki en büyük tek-bar getirisi (loto-sıçrama göstergesi)."""
    r=np.zeros(len(c)); r[1:]=c[1:]/c[:-1]-1
    o=np.full(len(c),np.nan)
    for i in range(MAX_WIN,len(c)): o[i]=r[i-MAX_WIN+1:i+1].max()
    return o

def grid(d, sl=None, max_gate=None, mx=None):
    """max_gate: None=kapalı. float=eşik; o bardaki MAX skoru eşiği aşıyorsa YENİ giriş yok."""
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=pd.Series(c).rolling(ER_WIN).mean().values;e=er(c,ER_WIN)
    held={};tr=[]
    rng=range(ER_WIN,len(c)) if sl is None else range(max(ER_WIN,sl.start),sl.stop)
    for i in rng:
        if np.isnan(e[i]) or np.isnan(sma[i]):continue
        gate_ok = True
        if max_gate is not None and mx is not None and not np.isnan(mx[i]):
            gate_ok = (mx[i] <= max_gate)      # loto-sıçraması yoksa giriş serbest
        if e[i]<ER_TH:
            ce=sma[i]
            if gate_ok:
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

def stats(allt):
    a=np.array(allt) if len(allt) else np.array([0.0])
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    return len(a), 100*(a>0).mean(), pf, a.sum()*100

print("veri çekiliyor...")
data={}; mxs={}; lott={}
for s in SYMS:
    d=fetch(s)
    if d is None: continue
    data[s]=d
    mx=max_score(d["close"].values); mxs[s]=mx
    lott[s]=np.nanmean(mx)         # hissenin ortalama loto-luğu
print(f"{len(data)} hisse · ~{int(np.mean([len(v) for v in data.values()]))} bar\n")

# ── TEST 1: KESİTSEL — low-MAX vs high-MAX grup (OOS, ikinci yarı)
med=np.median(list(lott.values()))
low=[s for s in data if lott[s]<=med]; high=[s for s in data if lott[s]>med]
print("=== TEST 1: KESİTSEL (grid, OOS ikinci yarı) ===")
print(f"  low-MAX (sakin) hisseler:  {', '.join(low)}")
print(f"  high-MAX (loto) hisseler:  {', '.join(high)}")
for nm,grp in [("LOW-MAX (sakin)",low),("HIGH-MAX (loto)",high)]:
    allt=[]
    for s in grp:
        d=data[s]; n=len(d); allt+=grid(d, slice(int(n*0.5),n))
    N,wr,pf,tot=stats(allt)
    print(f"  {nm:18s}: {N:>4} işlem · kazanan %{wr:.0f} · PF {pf:.2f} · toplam {tot:+.0f}%")

# ── TEST 2: ZAMAN-SERİSİ KAPI — grid vs grid+MAX-gate (TÜM hisse, OOS)
print("\n=== TEST 2: MAX-KAPISI (grid vs grid+gate, OOS ikinci yarı) ===")
# eşik: tüm hisselerin MAX skorlarının 70. persentili (üst %30 = loto-hâli → engelle)
allmx=np.concatenate([mxs[s][~np.isnan(mxs[s])] for s in data])
thr=np.percentile(allmx,70)
print(f"  loto-eşiği (70p tek-bar getiri): %{thr*100:.2f}")
for nm,gate in [("grid (kapısız)",None),("grid + MAX-kapı",thr)]:
    allt=[]
    for s in data:
        d=data[s]; n=len(d); allt+=grid(d, slice(int(n*0.5),n), max_gate=gate, mx=mxs[s])
    N,wr,pf,tot=stats(allt)
    print(f"  {nm:18s}: {N:>4} işlem · kazanan %{wr:.0f} · PF {pf:.2f} · toplam {tot:+.0f}%")
