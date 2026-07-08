# -*- coding: utf-8 -*-
"""ML ensemble testi (keremtuzun/AI-Trading-Bot yaklaşımı): RSI/MACD/Bollinger özellikleri
→ RandomForest + GradientBoosting → yön tahmini. Zaman-ayrımlı OOS (look-ahead YOK),
maliyetli, buy&hold'a karşı. Ayrıca kesitsel: ML en beğendiği hisseler piyasayı geçiyor mu."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
except ImportError:
    print("sklearn yok — pip install scikit-learn"); sys.exit()

px=pd.read_pickle("_bist_px.pkl").sort_index()
LIQ=[s+".IS" for s in "AKBNK GARAN ISCTR YKBNK VAKBN HALKB KCHOL SAHOL EREGL KRDMD "
     "TUPRS PETKM SASA ASELS SISE THYAO PGSUS TAVHL BIMAS MGROS TCELL TTKOM ARCLK "
     "FROTO TOASO TKFEN ENKAI EKGYO KOZAL AEFES ULKER CCOLA DOHOL ALARK GUBRF CIMSA".split()]
LIQ=[s for s in LIQ if s in px.columns]
SPLIT=pd.Timestamp("2019-01-01"); K=5; COST=0.002

def rsi(c,n=14):
    d=c.diff(); u=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); v=(-d).clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+u/v.replace(0,np.nan))

rows=[]
for s in LIQ:
    c=px[s].dropna()
    if len(c)<400: continue
    ema12=c.ewm(span=12,adjust=False).mean(); ema26=c.ewm(span=26,adjust=False).mean()
    macd=ema12-ema26; sig=macd.ewm(span=9,adjust=False).mean()
    ma20=c.rolling(20).mean(); sd20=c.rolling(20).std()
    bbpos=(c-ma20)/(2*sd20)              # bollinger %B benzeri
    df=pd.DataFrame({
        "rsi":rsi(c), "macd":macd/c, "macd_hist":(macd-sig)/c, "bb":bbpos,
        "r1":c.pct_change(), "r5":c.pct_change(5), "r20":c.pct_change(20),
        "vol":c.pct_change().rolling(20).std(), "distma":(c-ma20)/ma20,
    })
    df["fwd"]=(c.shift(-K)/c-1)
    df["y"]=(df["fwd"]>0).astype(int)
    df["date"]=c.index; df["sym"]=s
    rows.append(df.dropna())
D=pd.concat(rows).reset_index(drop=True)
feat=["rsi","macd","macd_hist","bb","r1","r5","r20","vol","distma"]
tr=D[D["date"]<SPLIT]; te=D[D["date"]>=SPLIT]
print(f"{len(LIQ)} sembol · eğitim {len(tr)} satır (<2019) · test {len(te)} satır (OOS 2019+)\n")

rf=RandomForestClassifier(n_estimators=200,max_depth=6,min_samples_leaf=50,n_jobs=-1,random_state=1)
gb=GradientBoostingClassifier(n_estimators=150,max_depth=3,learning_rate=0.05,random_state=1)
print("model eğitiliyor...")
rf.fit(tr[feat],tr["y"]); gb.fit(tr[feat],tr["y"])
proba=(rf.predict_proba(te[feat])[:,1]+gb.predict_proba(te[feat])[:,1])/2
te=te.copy(); te["p"]=proba

base=100*te["y"].mean()
acc=100*((te["p"]>0.5).astype(int)==te["y"]).mean()
print("="*66)
print(f"1) OOS yön doğruluğu: %{acc:.1f}  ·  taban oran (hep-yukarı deseydik): %{base:.1f}")
print(f"   → ML tabanı {'GEÇTİ' if acc>base+1 else 'GEÇEMEDİ'} ({acc-base:+.1f} puan)")

# 2) strateji: ML yukarı derse long, değilse nakit — maliyetli, buy&hold'a karşı
print("\n2) ML long/nakit stratejisi vs buy&hold (maliyetli, OOS):")
cash_d=(1+0.30)**(1/252)-1
srs=[]; bhs=[]
for s in LIQ:
    d=te[te["sym"]==s].sort_values("date")
    if len(d)<50: continue
    c=px[s].reindex(pd.DatetimeIndex(d["date"])); ret=c.pct_change().fillna(0).values
    sigup=(d["p"].values>0.5)
    pos=np.zeros(len(d)); pos[1:]=sigup[:-1]     # dünkü tahminle bugün pozisyon
    flip=np.abs(np.diff(np.concatenate([[0],pos])))
    sr=np.where(pos>0,ret,cash_d)-flip*COST
    srs.append(np.prod(1+sr)); bhs.append(np.prod(1+ret))
srs=np.array(srs); bhs=np.array(bhs)
print(f"   Hisse başı: ML-strateji medyan {np.median(srs):.2f}x · buy&hold medyan {np.median(bhs):.2f}x")
print(f"   ML buy&hold'u geçen hisse: {100*(srs>bhs).mean():.0f}%")

# 3) kesitsel: en yüksek P(up) hisseler piyasayı geçiyor mu (drift'siz gerçek alfa)
print("\n3) Kesitsel alfa: her gün en yüksek P(up) %20 hisse vs piyasa ortalaması (drift'siz):")
te2=te.copy(); exc=[]
for dt,g in te2.groupby("date"):
    if len(g)<10: continue
    thr=g["p"].quantile(0.8); top=g[g["p"]>=thr]
    exc.append(top["fwd"].mean()-g["fwd"].mean())
exc=np.array(exc); exc=exc[np.isfinite(exc)]
t=exc.mean()/(exc.std()/np.sqrt(len(exc)))
print(f"   Üst-%20 piyasa-üstü ort {K}-gün: {exc.mean()*100:+.3f}% · t-stat {t:+.2f} · pozitif gün %{100*(exc>0).mean():.0f}")
print("="*66)
print("EDGE: OOS doğruluk tabanı belirgin geçmeli + kesitsel t>2 + strateji buy&hold'u geçmeli.")
