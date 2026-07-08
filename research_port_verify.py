# -*- coding: utf-8 -*-
"""PORT DOĞRULAMA: BIST_TrendFilter.mq5'teki fonksiyonları BİREBİR Python'a çevirip
orijinal indicators.py ile karşılaştır. Eşleşirse MQL5 portu doğru = live ≈ backtest."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import indicators as ind

px=pd.read_pickle("_bist_px.pkl").sort_index()
SYM="GARAN.IS"; c=px[SYM].dropna().values[-500:]   # son 500 gün
n=len(c); L=40; P=2.0

# ── MQL5 ComputeVAR'ın birebir Python kopyası ──
def mql_var(close, length):
    n=len(close); out=np.full(n,np.nan)
    if length<=1: return close.copy()
    alpha=2.0/(length+1.0)
    up=np.zeros(n); dn=np.zeros(n)
    for i in range(1,n):
        d=close[i]-close[i-1]; up[i]=d if d>0 else 0; dn[i]=-d if d<0 else 0
    vidya=np.nan; started=False
    for i in range(n):
        su=sd=0.0
        if i>=8:
            for k in range(i-8,i+1): su+=up[k]; sd+=dn[k]
        denom=su+sd; cmo=(abs((su-sd)/denom) if denom>0 else 0.0)
        if not started:
            if i>=length-1:
                s=sum(close[i-length+1:i+1]); vidya=s/length; out[i]=vidya; started=True
            continue
        vidya=cmo*alpha*(close[i]-vidya)+vidya; out[i]=vidya
    return out

# ── MQL5 ComputeOTT birebir ──
def mql_ott(close, length, percent):
    mavg=mql_var(close,length); n=len(close); ott=np.full(n,np.nan)
    ls_prev=ss_prev=np.nan; dir_prev=1
    for i in range(n):
        if np.isnan(mavg[i]): continue
        fark=mavg[i]*percent*0.01; ls=mavg[i]-fark; ss=mavg[i]+fark
        if np.isnan(ls_prev): ls_prev=ls
        if np.isnan(ss_prev): ss_prev=ss
        if mavg[i]>ls_prev and ls<ls_prev: ls=ls_prev
        if mavg[i]<ss_prev and ss>ss_prev: ss=ss_prev
        if dir_prev==-1 and mavg[i]>ss_prev: d=1
        elif dir_prev==1 and mavg[i]<ls_prev: d=-1
        else: d=dir_prev
        mt=ls if d==1 else ss
        ott[i]=mt*(200+percent)/200.0 if mavg[i]>mt else mt*(200-percent)/200.0
        ls_prev=ls; ss_prev=ss; dir_prev=d
    return ott

# ── karşılaştır: VAR ──
cs=pd.Series(c)
py_var=ind.var_func(cs,L).values
mq_var=mql_var(c,L)
v_diff=np.nanmax(np.abs(py_var-mq_var))
print(f"VAR  max fark (Python vs MQL5-port): {v_diff:.2e}")

# ── OTT (indicators shift=2 uygular; ham karşılaştıralım shift=0) ──
py_ott_raw=ind.ott(cs,L,P,shift=0)["ott_raw"].values
mq_ott=mql_ott(c,L,P)
o_diff=np.nanmax(np.abs(py_ott_raw-mq_ott))
print(f"OTT  max fark (ham, shift=0):        {o_diff:.2e}")

# ── sinyal seviyesinde: close>OTT[shift2] kaç barda AYNI ──
py_ott_s2=pd.Series(py_ott_raw).shift(2).values
mq_ott_s2=pd.Series(mq_ott).shift(2).values
py_sig=(c>py_ott_s2); mq_sig=(c>mq_ott_s2)
valid=~np.isnan(py_ott_s2)&~np.isnan(mq_ott_s2)
agree=100*(py_sig[valid]==mq_sig[valid]).mean()
print(f"OTT sinyal (close>OTT) uyum:         %{agree:.1f}  ({valid.sum()} bar)")

print()
if v_diff<1e-6 and o_diff<1e-4 and agree>99.5:
    print("✅ PORT DOĞRU — MQL5 fonksiyonları Python orijinaliyle eşleşiyor.")
    print("   Live EA, doğrulanmış backtest ile aynı sinyali üretecek.")
else:
    print("⚠️ FARK VAR — port'ta düzeltme gerekebilir (yukarıdaki farklara bak).")
