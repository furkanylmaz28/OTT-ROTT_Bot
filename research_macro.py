# -*- coding: utf-8 -*-
"""Piyasalar-arası ÖNCÜLÜK — hissenin kendi fiyatı değil, DIŞ sinyaller.
Dün: USD/TL, S&P500, altın, VIX → bugün BIST'i tahmin ediyor mu?
Emerging market'ler global risk iştahını gecikmeli takip eder (test edilebilir hipotez).
Piyasa-üstü değil ama yön-tahmini + koşullu getiri; işlem-günü hizası dikkatli."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf
px=pd.read_pickle("_bist_px.pkl").sort_index()
bist=(1+px.pct_change().mean(axis=1)).cumprod()          # eşit-ağ. BIST
bist_r=bist.pct_change()

print("dış seriler iniyor...")
ext={}
for tk,nm in [("USDTRY=X","USDTRY"),("^GSPC","SP500"),("GC=F","GOLD"),("^VIX","VIX"),("^XU100.IS","XU100")]:
    try:
        d=yf.download(tk,period="max",interval="1d",progress=False,auto_adjust=True)
        if d is not None and len(d)>200: ext[nm]=pd.Series(d["Close"].values.astype(float).ravel(),index=d.index)
    except: pass
print(f"{list(ext.keys())}\n")

df=pd.DataFrame({"bist":bist_r})
for nm,s in ext.items(): df[nm]=s.pct_change()
df=df.dropna(how="all")

OOS=pd.Timestamp("2018-01-01")
def leadlag(pred, K=1):
    """pred: dış seri getiri, K gün ÖNCEDEN (shift). bist bugünü tahmin ediyor mu."""
    x=df[pred].shift(K); y=df["bist"]
    d2=pd.concat([x,y],axis=1).dropna()
    d2.columns=["x","y"]
    for split,mask in [("TÜM",d2.index>=d2.index[0]),("OOS",d2.index>=OOS)]:
        s=d2[mask]
        if len(s)<50: continue
        # korelasyon + koşullu: dış-yukarı günlerde BIST ertesi getiri
        corr=s["x"].corr(s["y"])
        up=s[s["x"]>0]["y"].mean()*100; dn=s[s["x"]<=0]["y"].mean()*100
        # basit strateji: dış-yukarıysa BIST long ertesi gün
        strat=np.where(s["x"]>0, s["y"], 0)
        base=s["y"].mean()
        hit=100*((np.sign(s["x"])==np.sign(s["y"])).mean())
        print(f"    {split:4s}: korelasyon {corr:+.3f} · dış↑sonrası {up:+.3f}% vs dış↓sonrası {dn:+.3f}% · yön-isabet {hit:.0f}%")

print("="*70)
print("Dün DIŞ SİNYAL → bugün BIST (1 gün gecikme):")
for p in [c for c in df.columns if c!="bist"]:
    print(f"  {p}:")
    leadlag(p,1)
print("\n"+"="*70)
print("EDGE VARSA: korelasyon|>0.1| tutarlı + dış↑/dış↓ getirileri belirgin ayrışır + OOS'ta da.")
print("(Küçük korelasyon bile düşük-frekansta değerli olabilir; ama TÜM≈OOS şart.)")
