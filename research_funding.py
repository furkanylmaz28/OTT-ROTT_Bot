# -*- coding: utf-8 -*-
"""CRYPTO FUNDING carry — perp funding rate hasadı. Delta-nötr (long spot + short perp)
→ funding topla, piyasa yönünden bağımsız. Halka açık Binance verisi (auth yok).
Soru: funding tutarlı pozitif + ücret sonrası anlamlı bir getiri mi?"""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, urllib.request, json, time

COINS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT"]
FEE=0.0004   # taker ~%0.04; carry giriş+çıkış tek sefer, funding periyodik

def fetch_funding(sym):
    """Funding rate geçmişi (8 saatte bir), sayfalı."""
    out=[]; end=int(time.time()*1000)
    for _ in range(30):   # ~30k kayıt = yıllar
        url=f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1000&endTime={end}"
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            d=json.load(urllib.request.urlopen(req,timeout=20))
        except Exception as e:
            break
        if not d: break
        out=d+out
        end=d[0]["fundingTime"]-1
        if len(d)<1000: break
        time.sleep(0.15)
    return out

print("Binance funding geçmişi iniyor (halka açık)...\n")
print("="*70)
print(f"{'COIN':9s}{'kayıt':>7}{'yıl':>6}{'ort funding/8s':>16}{'yıllık%':>9}{'poz%':>7}")
all_ann=[]
for c in COINS:
    d=fetch_funding(c)
    if not d: print(f"{c:9s} veri yok"); continue
    fr=np.array([float(x["fundingRate"]) for x in d])
    times=np.array([x["fundingTime"] for x in d])
    yrs=(times[-1]-times[0])/(1000*3600*24*365)
    ann=fr.mean()*3*365*100   # 8s'te bir → günde 3, yılda ~1095 periyot
    pos=100*(fr>0).mean()
    all_ann.append(ann)
    print(f"{c:9s}{len(fr):>7}{yrs:>6.1f}{fr.mean()*100:>15.4f}%{ann:>8.1f}%{pos:>6.0f}%")
print("="*70)
if all_ann:
    m=np.mean(all_ann)
    print(f"Ortalama yıllık funding getirisi (ham): %{m:.1f}")
    print(f"Delta-nötr carry (long spot+short perp): funding'i toplar, YÖNDEN bağımsız")
    print(f"  ≈ ham funding − giriş/çıkış ücreti ({FEE*4*100:.1f}% tek sefer) − ~spread")
    print(f"  Kabaca net yıllık: ~%{m-2:.0f} (USD cinsi, market-neutral)")
    print()
    print("DEĞERLENDİRME:")
    print(f"  • USD risksiz (~%4-5) ile karşılaştır: {'GEÇİYOR' if m>6 else 'zayıf'}")
    print(f"  • Ama: funding negatife dönebilir (2022 ayı), basis riski, likidasyon riski")
    print(f"  • TL mevduat %40 ile karşılaştır: USD getirisi + TL değer kaybı hesaba katılmalı")
