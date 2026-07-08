# -*- coding: utf-8 -*-
"""Giriş sinyallerinin TAHMİN GÜCÜ testi — hata girişte mi diye ölçer.
Her sinyal için: fire olduğunda ileri getiri (K bar sonra), maliyet sonrası,
IS/OOS ayrımıyla. 'dip-al' (bot) gerçekten sıçrama mı öngörüyor, yoksa
'kırılınca sat' mı daha iyi? Yazı-turadan (hit%50) iyi olan var mı?
Veri: yfinance BIST H1. Maliyet: gidiş-dönüş %0.2 varsayımı."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

SYMS = ["AKBNK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","DOHOL.IS","ENJSA.IS",
    "EKGYO.IS","ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","GUBRF.IS",
    "HALKB.IS","ISCTR.IS","KCHOL.IS","KRDMD.IS","MGROS.IS","OYAKC.IS",
    "PETKM.IS","PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TOASO.IS","TKFEN.IS","TSKB.IS",
    "TTKOM.IS","TUPRS.IS","VAKBN.IS","VESTL.IS","YKBNK.IS","AEFES.IS",
    "HEKTS.IS","ODAS.IS","ASTOR.IS","AKSEN.IS","ALARK.IS","KONTR.IS",
    "DOAS.IS","CIMSA.IS","ULKER.IS"]

ERW=20; SMAW=20; COST=0.002   # gidiş-dönüş maliyet
K=3                            # ileri getiri ufku (bar) — gridin ~1-3h tutmasına yakın

def er(c,n):
    o=np.full(len(c),np.nan)
    for i in range(n,len(c)):
        v=np.abs(np.diff(c[i-n:i+1])).sum(); o[i]=abs(c[i]-c[i-n])/v if v>0 else np.nan
    return o

def load(s):
    try:
        d=yf.download(s,period="6mo",interval="1h",progress=False,auto_adjust=True)
        if d is None or len(d)<300: return None
        c=d["Close"].values.astype(float).ravel()
        return c
    except: return None

print("veri iniyor (yfinance BIST H1)...")
data={}
for s in SYMS:
    c=load(s)
    if c is not None: data[s]=c
print(f"{len(data)} sembol yüklendi\n")

# her sinyal: (isim, yön['L'/'S'], koşul-fonksiyonu(close,sma,er,i))
def dip(c,sma,e,i):   return c[i] < sma[i]*(1-0.015)          # ortalama %1.5 altı
def dip_range(c,sma,e,i): return c[i]<sma[i]*(1-0.015) and e[i]<0.30
def mom_up(c,sma,e,i): return c[i]>sma[i] and i>=5 and c[i]>c[i-5]
def mom_dn(c,sma,e,i): return c[i]<sma[i] and i>=5 and c[i]<c[i-5]
def breakdown(c,sma,e,i): return c[i]<sma[i]*(1-0.015)         # aynı dip ama SAT

SIGNALS=[
    ("DİP-AL (botun mantığı)","L",dip),
    ("DİP-AL + yatay rejim","L",dip_range),
    ("DİP → SAT (kırılım-short)","S",breakdown),
    ("MOMENTUM yukarı → AL","L",mom_up),
    ("MOMENTUM aşağı → SAT","S",mom_dn),
]

def evaluate(split):  # split: 'IS' ilk %70, 'OOS' son %30, 'ALL'
    res={}
    for name,side,cond in SIGNALS:
        rets=[]
        for s,c in data.items():
            n=len(c)
            sma=pd.Series(c).rolling(SMAW).mean().values
            e=er(c,ERW)
            lo=max(ERW,SMAW); hi=n-K
            a,b=lo,hi
            if split=="IS": b=lo+int((hi-lo)*0.7)
            elif split=="OOS": a=lo+int((hi-lo)*0.7)
            for i in range(a,b):
                if np.isnan(sma[i]) or np.isnan(e[i]): continue
                if cond(c,sma,e,i):
                    fwd=c[i+K]/c[i]-1
                    rets.append(fwd if side=="L" else -fwd)   # short için işareti çevir
        r=np.array(rets)
        if len(r)==0: res[name]=(0,0,0,0); continue
        net=r.mean()-COST
        hit=100*(r>0).mean()
        res[name]=(len(r), r.mean()*100, net*100, hit)
    return res

for split in ["ALL","IS","OOS"]:
    print(f"===== {split} =====")
    print(f"{'SİNYAL':30s}{'n':>7}{'ham%':>8}{'net%':>8}{'isabet':>8}")
    r=evaluate(split)
    for name,(n,raw,net,hit) in r.items():
        flag=" <<< POZİTİF" if net>0 and hit>50 else ""
        print(f"{name:30s}{n:>7}{raw:>8.3f}{net:>8.3f}{hit:>7.0f}%{flag}")
    print()
print(f"(ham%=sinyal başına ort ileri {K}-bar getiri, net%=maliyet sonrası, isabet=yön doğruluğu)")
print("EDGE VARSA: net%>0 VE isabet>50 VE IS≈OOS. Aksi halde yazı-tura.")
