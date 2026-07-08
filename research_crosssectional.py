# -*- coding: utf-8 -*-
"""Kesitsel (cross-sectional) test — hisseyi zamanla değil BİRBİRİNE GÖRE sıralar.
Denediğimiz her şeyden yapısal olarak farklı. Akademik olarak en sağlam anomali ailesi.
Sinyaller: momentum (kazananı al), kısa-vade dönüş (kaybedeni al-bounce).
Ölçüm: üst quintile vs alt quintile ileri getiri farkı, monotonluk, IS/OOS, maliyet."""
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
COST=0.002   # devir başına yaklaşık gidiş-dönüş

print("2 yıl günlük iniyor + hizalanıyor...")
cols={}
for s in SYMS:
    try:
        d=yf.download(s,period="2y",interval="1d",progress=False,auto_adjust=True)
        if d is not None and len(d)>200: cols[s]=pd.Series(d["Close"].values.astype(float).ravel(), index=d.index)
    except: pass
px=pd.DataFrame(cols).dropna(how="all").ffill().dropna()
print(f"{px.shape[1]} sembol × {px.shape[0]} gün hizalandı\n")

def test_signal(name, lookback, horizon, long_winners):
    """Her 'horizon' günde bir: geçmiş 'lookback' getiriye göre sırala, quintile'lara böl,
       ileri 'horizon' getiriyi ölç. long_winners=True → kazananı al, False → kaybedeni al."""
    dates=px.index; N=len(dates)
    # rebalans noktaları (çakışmasız)
    qfwd={q:[] for q in range(5)}; ls=[]
    for t in range(lookback, N-horizon, horizon):
        past=px.iloc[t]/px.iloc[t-lookback]-1
        fwd =px.iloc[t+horizon]/px.iloc[t]-1
        valid=past.dropna().index.intersection(fwd.dropna().index)
        if len(valid)<10: continue
        past=past[valid]; fwd=fwd[valid]
        order=past.sort_values(ascending=not long_winners).index   # winners->False sıra üst; ama biz index quintile
        ranks=past.rank(ascending=long_winners)   # long_winners: yüksek getiri yüksek rank
        # quintile: 5 grup
        q=pd.qcut(ranks, 5, labels=False, duplicates="drop")
        for qi in range(5):
            members=fwd[q==qi]
            if len(members)>0: qfwd[qi].append(members.mean())
        top=fwd[q==4].mean(); bot=fwd[q==0].mean()   # q=4 en yüksek sinyal
        if not np.isnan(top) and not np.isnan(bot): ls.append(top-bot-COST)
    qmeans=[100*np.mean(qfwd[qi]) if qfwd[qi] else 0 for qi in range(5)]
    lsa=np.array(ls); n=len(lsa)
    net=lsa.mean()*100 if n else 0
    tstat=lsa.mean()/(lsa.std(ddof=1)/np.sqrt(n)) if n>1 and lsa.std()>0 else 0
    hit=100*(lsa>0).mean() if n else 0
    mono = all(qmeans[i]<=qmeans[i+1] for i in range(4))  # artan gradyan var mı
    print(f"{name}")
    print(f"  quintile ileri getiri (düşük→yüksek sinyal): "+" ".join(f"{x:+.2f}" for x in qmeans))
    print(f"  üst-alt fark (net, maliyet sonrası): {net:+.3f}% · devir={n} · t-stat={tstat:.2f} · isabet={hit:.0f}% · monoton={'EVET' if mono else 'hayır'}")
    return net,tstat,mono

print("="*70)
print("MOMENTUM (kazananı al — orta vade):")
test_signal("  mom_60g → ileri 20g", 60, 20, True)
test_signal("  mom_120g → ileri 20g", 120, 20, True)
print()
print("KISA-VADE DÖNÜŞ (kaybedeni al — bounce):")
test_signal("  rev_5g → ileri 5g", 5, 5, False)
test_signal("  rev_10g → ileri 10g", 10, 10, False)
print()
print("="*70)
print("EDGE VARSA: net%>0, t-stat>2, monoton=EVET (gradyan quintile'lar boyunca tutarlı).")
print("qcut monotonluğu quintile'ların rastgele değil sistematik olduğunu gösterir.")
