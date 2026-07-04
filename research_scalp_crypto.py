# -*- coding: utf-8 -*-
"""SCALPING testi — kripto 5m: klasik scalp arketipi (ani düşüşü al, hızlı kâr al)
+ KOMİSYON SÜPÜRMESİ. Soru: brüt edge var mı, gerçek maliyette (%0.05 taker/yön)
hayatta kalıyor mu? Binance public klines (API key gerekmez, sadece veri).
IS/OOS split + maliyet 0 / 0.04 / 0.10 / 0.20 (gidiş-dönüş %)."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import warnings; warnings.filterwarnings('ignore')
import time
import numpy as np
from binance.client import Client

client = Client()   # public endpoints — anahtar gerekmez
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
DIP    = -0.004    # sinyal: son 3 barda -%0.4 düşüş (panik dip)
TARGET =  0.0015   # hedef +%0.15 (tipik scalp)
TIMEOUT = 6        # 6 bar (30 dk) içinde hedefe gelmezse kapan

def klines_5m(sym, batches=4):
    """4 × 1500 bar = ~20 gün 5m veri (public)."""
    out = []
    end = None
    for _ in range(batches):
        kw = dict(symbol=sym, interval="5m", limit=1500)
        if end: kw["endTime"] = end
        kl = client.futures_klines(**kw)
        if not kl: break
        out = kl + out
        end = kl[0][0] - 1
        time.sleep(0.2)
    return np.array([[float(k[1]),float(k[2]),float(k[3]),float(k[4])] for k in out])  # o,h,l,c

def scalp(ohlc, a, b, cost):
    o,h,l,c = ohlc[:,0], ohlc[:,1], ohlc[:,2], ohlc[:,3]
    tr=[]
    i=a+3
    while i < b-TIMEOUT-1:
        r3 = c[i]/c[i-3]-1
        if r3 <= DIP:                       # panik dip → al (bir sonraki bar açılışı)
            entry=o[i+1]; done=False
            for j in range(i+1, i+1+TIMEOUT):
                if h[j] >= entry*(1+TARGET):        # hedef doldu
                    tr.append(TARGET-cost); done=True; break
            if not done:
                tr.append(c[i+TIMEOUT]/entry-1-cost)  # zaman aşımı → kapan
            i += TIMEOUT                    # pozisyon süresi kadar atla
        else:
            i += 1
    return tr

def rep(tr):
    a=np.array(tr) if len(tr) else np.array([0.0])
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    return len(a),100*(a>0).mean(),pf,a.sum()*100

print("veri çekiliyor (Binance public, 5m × ~20 gün)...")
data={}
for s in COINS:
    k=klines_5m(s)
    if len(k)>2000: data[s]=k
print(f"{len(data)} coin · ~{int(np.mean([len(v) for v in data.values()]))} bar (5m)\n")

print(f"Arketip: son 3 barda ≤{DIP*100:.1f}% düşüş → AL · hedef +{TARGET*100:.2f}% · {TIMEOUT} bar zaman aşımı")
print(f"{'maliyet(GD)':>12}{'bölge':>8}{'işlem':>8}{'kazanan':>9}{'PF':>7}{'toplam':>9}")
for cost in [0.0, 0.0004, 0.0010, 0.0020]:
    for nm,(fa,fb) in [("IS",(0.0,0.5)),("OOS",(0.5,1.0))]:
        allt=[]
        for k in data.values():
            n=len(k); allt+=scalp(k, int(n*fa), int(n*fb), cost)
        N,wr,pf,tot=rep(allt)
        lbl=f"%{cost*100:.2f}" if nm=="IS" else ""
        print(f"{lbl:>12}{nm:>8}{N:>8}{wr:>8.0f}%{pf:>7.2f}{tot:>+8.1f}%")
print("\n(GD = gidiş-dönüş. Binance gerçeği: taker %0.05/yön ≈ %0.10 GD → '%0.10' satırı senin gerçeğin.)")
