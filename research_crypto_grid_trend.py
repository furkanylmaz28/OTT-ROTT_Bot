# -*- coding: utf-8 -*-
"""Crypto'da GRID+TREND-LONG vs salt GRID — BIST'te kanıtlanan trend bacağı
crypto'ya da yarıyor mu? Kullanıcının haklı gözlemi: yükselen piyasada grid nakitte
oturuyor (fırsat maliyeti). BIST EA'da çözüm trend-long'du; crypto'da HİÇ test edilmedi.
Not: SuperTrend-tarzı trend TAKİBİ crypto'da elendi (WF 2/9) — ama bu farklı:
rejim zaten ER ile ölçülüyor, sadece 'trend döneminde long tut' bacağı ekleniyor.
OOS (ikinci yarı) · 4h · crypto paramları (-2/-4/-6, take 1.5, trail 0.5) · maliyet %0.10."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
from dotenv import load_dotenv; load_dotenv('.env')
import numpy as np, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()

COINS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT",
         "TRXUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","LTCUSDT","BCHUSDT","ATOMUSDT",
         "NEARUSDT","APTUSDT","SUIUSDT","INJUSDT"]
ER_WIN=20; ER_TH=0.30; LEVELS=[0.02,0.04,0.06]; TAKE=0.015; TRAIL=0.005
TREND_TRAIL=0.03; COST=0.0010

def fetch(s):
    try:
        d=tv.get_hist(s,'BINANCE',interval=Interval.in_4_hour,n_bars=3000)
        return d.rename(columns=str.lower).reset_index(drop=True) if d is not None and len(d)>800 else None
    except: return None
def er(c,n):
    o=np.full(len(c),np.nan)
    for i in range(n,len(c)):
        v=np.abs(np.diff(c[i-n:i+1])).sum(); o[i]=abs(c[i]-c[i-n])/v if v>0 else np.nan
    return o

def simulate(d, trend_long, a):
    """Grid (her zaman) + opsiyonel trend-long bacağı (BIST EA mantığı):
    ER>=eşik & fiyat>SMA → long tut; +%1.5 net'te 3% geniş trailing; rejim/yön dönünce kapat."""
    c=d["close"].values;h=d["high"].values;l=d["low"].values
    sma=d["_sma"]; e=d["_er"]; held={}; trend=None; tr=[]
    for i in range(max(ER_WIN,a),len(c)):
        if np.isnan(e[i]) or np.isnan(sma[i]): continue
        sideways = e[i]<ER_TH; up = c[i]>sma[i]
        # ── trend-long pozisyonu yönet
        if trend is not None:
            trend["p"]=max(trend["p"],h[i])
            gain=(c[i]-trend["e"])/trend["e"]
            exit_now = sideways or (not up)
            if gain>=TAKE and l[i]<=trend["p"]*(1-TREND_TRAIL): exit_now=True
            if exit_now: tr.append((c[i]/trend["e"]-1)-COST); trend=None
        if sideways:
            ce=sma[i]
            for k,lv in enumerate(LEVELS):
                px=ce*(1-lv)
                if k not in held and l[i]<=px: held[k]={"e":px,"a":False,"p":px}
            for k in list(held.keys()):
                u=held[k]
                if not u["a"] and h[i]>=u["e"]*(1+TAKE): u["a"]=True; u["p"]=h[i]
                if u["a"]:
                    u["p"]=max(u["p"],h[i])
                    if l[i]<=u["p"]*(1-TRAIL): tr.append((u["p"]*(1-TRAIL)/u["e"]-1)-COST); del held[k]
        else:
            for k in list(held.keys()): tr.append((c[i]/held[k]["e"]-1)-COST); del held[k]
            if trend_long and up and trend is None:
                trend={"e":c[i],"p":c[i]}
    return tr

def rep(tr):
    a=np.array(tr) if len(tr) else np.array([0.0])
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    return len(a),100*(a>0).mean(),pf,a.sum()*100

print("veri çekiliyor (BINANCE 4h)...")
data={}
for s in COINS:
    d=fetch(s)
    if d is None: continue
    d["_er"]=er(d["close"].values,ER_WIN); d["_sma"]=pd.Series(d["close"].values).rolling(ER_WIN).mean().values
    data[s]=d
print(f"{len(data)} coin · ~{int(np.mean([len(v) for v in data.values()]))} bar (4h)\n")

for nm,tl in [("SALT GRID (mevcut canlı)",False),("GRID + TREND-LONG",True)]:
    ist=[]; oos=[]
    for d in data.values():
        n=len(d); half=int(n*0.5)
        d_is = d.iloc[:half].copy()
        d_is["_er"]=d["_er"][:half]; d_is["_sma"]=d["_sma"][:half]
        ist += simulate(d_is, tl, ER_WIN)   # IS: ilk yarı
        oos += simulate(d, tl, half)        # OOS: ikinci yarı
    Ni,wri,pfi,toti=rep(ist); No,wro,pfo,toto=rep(oos)
    print(f"  {nm:26s}: IS  PF {pfi:.2f} ({toti:+.0f}%, {Ni})  ·  OOS PF {pfo:.2f} ({toto:+.0f}%, {No} işlem, kazanan %{wro:.0f})")
