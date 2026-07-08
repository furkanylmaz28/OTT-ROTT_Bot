# -*- coding: utf-8 -*-
"""OTT (+TOTT teyit) sinyalinin TAHMİN GÜCÜ — kullanıcının ASIL sistemi, aynı terazi.
Dip/momentum ile bire bir aynı test: 45 BIST H1, OOS ayrımı, maliyet sonrası, çoklu ufuk.
OTT trend-takipçisi olduğu için ufukları uzun da tutuyorum (trend persistence)."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf
import indicators as ind
import ott_tott_confirm as otc

SYMS = ["AKBNK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","DOHOL.IS","ENJSA.IS",
    "EKGYO.IS","ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","GUBRF.IS",
    "HALKB.IS","ISCTR.IS","KCHOL.IS","KRDMD.IS","MGROS.IS","OYAKC.IS",
    "PETKM.IS","PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TOASO.IS","TKFEN.IS","TSKB.IS",
    "TTKOM.IS","TUPRS.IS","VAKBN.IS","VESTL.IS","YKBNK.IS","AEFES.IS",
    "HEKTS.IS","ODAS.IS","ASTOR.IS","AKSEN.IS","ALARK.IS","KONTR.IS",
    "DOAS.IS","CIMSA.IS","ULKER.IS"]
L,P,C = otc.TV_LENGTH, otc.TV_PERCENT, otc.TV_COEFF   # 40, 1.0, 0.001 (kanonik)
COST=0.002

def load(s):
    try:
        d=yf.download(s,period="6mo",interval="1h",progress=False,auto_adjust=True)
        if d is None or len(d)<300: return None
        return pd.Series(d["Close"].values.astype(float).ravel())
    except: return None

print("veri iniyor + OTT hesaplanıyor...")
frames={}
for s in SYMS:
    c=load(s)
    if c is None: continue
    o=ind.ott(c,L,P,shift=2); t=ind.tott(c,L,P,C,shift=2)
    mavg=o["mavg"]; ott=o["ott"]; up=t["ottup"]; dn=t["ottdn"]
    # OTT trend durumu (mavg > OTT çizgisi)
    state=(mavg>ott).astype(float)   # 1 uptrend, 0 downtrend
    # OTT crossover giriş
    ol=(state==1)&(state.shift(1)==0)
    os_=(state==0)&(state.shift(1)==1)
    # OTT+TOTT kanonik teyit
    a_up=(mavg>up).astype(bool); b_dn=(mavg<dn).astype(bool)
    buy=a_up&~a_up.shift(1,fill_value=False)
    sell=b_dn&~b_dn.shift(1,fill_value=False)
    frames[s]=dict(c=c,state=state,ol=ol.values,os=os_.values,buy=buy.values,sell=sell.values)
print(f"{len(frames)} sembol\n")

def collect(kind, split, K):
    rets=[]
    for s,f in frames.items():
        c=f["c"].values; n=len(c); hi=n-K; lo=L+9
        a,b=lo,hi
        if split=="IS": b=lo+int((hi-lo)*0.7)
        elif split=="OOS": a=lo+int((hi-lo)*0.7)
        for i in range(a,b):
            fwd=c[i+K]/c[i]-1
            if kind=="state":                     # o an uptrend'deysek long, değilse short
                if np.isnan(f["state"].values[i]): continue
                rets.append(fwd if f["state"].values[i]==1 else -fwd)
            elif kind=="cross":                    # OTT crossover girişleri
                if f["ol"][i]: rets.append(fwd)
                elif f["os"][i]: rets.append(-fwd)
            elif kind=="confirm":                  # OTT+TOTT teyitli
                if f["buy"][i]: rets.append(fwd)
                elif f["sell"][i]: rets.append(-fwd)
    return np.array(rets)

tests=[("OTT trend DURUMU (long/short)","state"),
       ("OTT crossover GİRİŞ","cross"),
       ("OTT+TOTT TEYİTLİ (asıl sistem)","confirm")]
for K in [3,6,12]:
    print(f"########## İLERİ UFUK = {K} bar ##########")
    for split in ["ALL","OOS"]:
        print(f"  --- {split} ---")
        print(f"  {'SİNYAL':32s}{'n':>7}{'ham%':>8}{'net%':>8}{'isabet':>8}")
        for name,kind in tests:
            r=collect(kind,split,K)
            if len(r)==0: print(f"  {name:32s}{'0':>7}"); continue
            net=r.mean()-COST; hit=100*(r>0).mean()
            flag="  <<< POZİTİF" if net>0 and hit>50 else ""
            print(f"  {name:32s}{len(r):>7}{r.mean()*100:>8.3f}{net*100:>8.3f}{hit:>7.0f}%{flag}")
    print()
print("EDGE VARSA: net%>0 VE isabet>50 VE ALL≈OOS. (net%=maliyet sonrası işlem başı)")
