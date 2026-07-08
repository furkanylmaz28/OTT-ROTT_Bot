# -*- coding: utf-8 -*-
"""OTT+TOTT tam doğrulama — kullanıcının asıl sistemi, sonuna kadar dürüst.
2 yıl GÜNLÜK (büyük örneklem + çoklu rejim). Gerçek backtest: giriş=TOTT teyidi,
çıkış=ters teyit (stop-and-reverse). Ölçülen: istatistik anlamlılık, parametre
sağlamlığı (curve-fit mi?), IS/OOS, Monte Carlo. Maliyet gidiş-dönüş %0.2."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf
import indicators as ind

SYMS = ["AKBNK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","DOHOL.IS","ENJSA.IS",
    "EKGYO.IS","ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","GUBRF.IS",
    "HALKB.IS","ISCTR.IS","KCHOL.IS","KRDMD.IS","MGROS.IS","OYAKC.IS",
    "PETKM.IS","PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TOASO.IS","TKFEN.IS","TSKB.IS",
    "TTKOM.IS","TUPRS.IS","VAKBN.IS","VESTL.IS","YKBNK.IS","AEFES.IS",
    "HEKTS.IS","ODAS.IS","ASTOR.IS","AKSEN.IS","ALARK.IS","KONTR.IS",
    "DOAS.IS","CIMSA.IS","ULKER.IS"]
COST=0.002

def load(s):
    try:
        d=yf.download(s,period="2y",interval="1d",progress=False,auto_adjust=True)
        if d is None or len(d)<150: return None
        return pd.Series(d["Close"].values.astype(float).ravel())
    except: return None

print("2 yıl günlük veri iniyor..."); DATA={}
for s in SYMS:
    c=load(s)
    if c is not None: DATA[s]=c
print(f"{len(DATA)} sembol\n")

def signals(c,L,P,C):
    """TOTT teyitli LONG/SHORT sinyal barları (kanonik crossover mantığı)."""
    o=ind.ott(c,L,P,shift=2); t=ind.tott(c,L,P,C,shift=2)
    mavg=o["mavg"]; up=t["ottup"]; dn=t["ottdn"]
    a=(mavg>up).astype(bool); b=(mavg<dn).astype(bool)
    buy=(a&~a.shift(1,fill_value=False)).values
    sell=(b&~b.shift(1,fill_value=False)).values
    return buy,sell

def trades(c,L,P,C,lo=0,hi=None):
    """Stop-and-reverse: teyitte gir, ters teyitte çık. Her işlemin net getirisi."""
    cv=c.values; n=len(cv); hi=hi or n
    buy,sell=signals(c,L,P,C)
    pos=0; ent=0.0; tr=[]
    for i in range(max(L+9,lo),hi):
        sig = 1 if buy[i] else (-1 if sell[i] else 0)
        if sig!=0 and sig!=pos:
            if pos!=0 and ent>0:
                r=(cv[i]/ent-1)*pos - COST
                tr.append(r)
            pos=sig; ent=cv[i]
    return tr

def stats(tr):
    a=np.array(tr) if tr else np.array([0.0])
    n=len(a); wr=100*(a>0).mean(); tot=a.sum()*100; avg=a.mean()*100
    gl=abs(a[a<0].sum()); pf=(a[a>0].sum()/gl) if gl>0 else 99
    tstat=a.mean()/(a.std(ddof=1)/np.sqrt(n)) if n>1 and a.std()>0 else 0
    return n,wr,avg,tot,pf,tstat

# ── 1) KANONİK param, tüm/IS/OOS
print("="*68)
print("1) OTT+TOTT (kanonik L=40 %=1 coeff=0.001) — gerçek stop-and-reverse")
print(f"{'dönem':6s}{'işlem':>7}{'kazanan%':>10}{'ort%':>8}{'toplam%':>9}{'PF':>6}{'t-stat':>8}")
allt=[]
for split,frac in [("TÜM",None),("IS",(0,0.7)),("OOS",(0.7,1.0))]:
    tr=[]
    for s,c in DATA.items():
        n=len(c)
        if frac is None: tr+=trades(c,40,1.0,0.001)
        else: tr+=trades(c,40,1.0,0.001,int(n*frac[0]),int(n*frac[1]))
    if split=="TÜM": allt=tr
    n,wr,avg,tot,pf,ts=stats(tr)
    print(f"{split:6s}{n:>7}{wr:>9.0f}%{avg:>8.2f}{tot:>9.0f}{pf:>6.2f}{ts:>8.2f}")
print("  (t-stat>2 ≈ %95 anlamlı; PF>1 kârlı; ort%>0.2 maliyeti geçer)")

# ── 2) PARAMETRE SAĞLAMLIĞI (curve-fit mi tek nokta mı?)
print("\n"+"="*68)
print("2) Parametre taraması — çoğu pozitifse SAĞLAM, tek nokta ise curve-fit")
print(f"{'L\\%':>6}", end="")
Ps=[0.5,1.0,2.0,3.0]
for P in Ps: print(f"{('%'+str(P)):>10}", end="")
print("  (hücre: toplam% / PF)")
for L in [20,30,40,50]:
    print(f"{L:>6}", end="")
    for P in Ps:
        tr=[]
        for s,c in DATA.items(): tr+=trades(c,L,P,0.001)
        _,_,_,tot,pf,_=stats(tr)
        print(f"{tot:>6.0f}/{pf:>3.1f}", end="")
    print()

# ── 3) SEMBOL TUTARLILIĞI
print("\n"+"="*68)
pos_syms=0; tot_syms=0
for s,c in DATA.items():
    tr=trades(c,40,1.0,0.001)
    if len(tr)>=2:
        tot_syms+=1
        if np.array(tr).sum()>0: pos_syms+=1
print(f"3) Sembol tutarlılığı: {tot_syms} sembolün {pos_syms}'i pozitif ({100*pos_syms/max(1,tot_syms):.0f}%)")

# ── 4) MONTE CARLO (işlemleri bootstrap)
print("\n"+"="*68)
a=np.array(allt)
if len(a)>10:
    rng=np.random.default_rng(42)
    sims=[rng.choice(a,len(a),replace=True).sum()*100 for _ in range(3000)]
    sims=np.array(sims)
    print(f"4) Monte Carlo (3000 bootstrap, {len(a)} işlem):")
    print(f"   Pozitif biten simülasyon: {100*(sims>0).mean():.0f}%")
    print(f"   Medyan toplam: {np.median(sims):+.0f}% · %5 kötü: {np.percentile(sims,5):+.0f}% · %95 iyi: {np.percentile(sims,95):+.0f}%")
print("\nKARAR: t-stat>2 + PF>1.3 + parametre çoğu pozitif + MC %80+ pozitif → gerçek edge adayı.")
