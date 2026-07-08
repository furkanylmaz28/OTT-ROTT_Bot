# -*- coding: utf-8 -*-
"""Geniş BIST evreni, MAKSİMUM günlük geçmiş — önbelleğe (pickle) alır.
Momentum araştırması bu cache'i okur (tekrar indirmeye gerek yok)."""
import sys; sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, yfinance as yf, time

# Köklü + likit BIST isimleri (uzun geçmiş olması muhtemel). Tekrarlar dedupe edilir.
U = """AKBNK GARAN ISCTR YKBNK VAKBN HALKB TSKB SKBNK ALBRK ICBCT
KCHOL SAHOL DOHOL AGHOL GLYHO ALARK ENKAI TKFEN GESAN
EREGL KRDMD ISDMR KARSN TOASO FROTO OTKAR TTRAK DOAS ASUZU EGEEN
TUPRS PETKM SASA GUBRF BAGFS ALKIM AKSA HEKTS SODA BRISA GOODY KORDS
ASELS OTKAR SISE CIMSA CMBTN NUHCM AKCNS BUCIM KONYA
THYAO PGSUS TAVHL CLEBI
BIMAS MGROS SOKM CCOLA ULKER AEFES BANVT PNSUT TATGD KENT KERVT
TCELL TTKOM
TUPRS AKSEN AYGAZ ZOREN ODAS AKENR ENJSA GWIND SMRTG AKFYE AKSUE
ARCLK VESTL VESBE
EKGYO ISGYO TRGYO SNGYO EMLAK
ASTOR KONTR ENERY EUPWR
MAVI BIZIM SELEC TMSN VAKKO DEVA ECZYT ECILC BERA
KOZAL KOZAA IPEKE GOLTS
BRSAN BRYAT ISMEN OYAKC KLSER"""
SYMS = sorted(set(s.strip()+".IS" for s in U.split() if s.strip()))
print(f"{len(SYMS)} aday sembol\n")

cols={}; ok=0
for i,s in enumerate(SYMS):
    try:
        d=yf.download(s,period="max",interval="1d",progress=False,auto_adjust=True)
        if d is not None and len(d)>400:
            cols[s]=pd.Series(d["Close"].values.astype(float).ravel(), index=d.index)
            ok+=1
    except Exception as e:
        pass
    if (i+1)%15==0: print(f"  {i+1}/{len(SYMS)} işlendi, {ok} geçerli")
    time.sleep(0.1)

px=pd.DataFrame(cols).sort_index()
px.to_pickle("_bist_px.pkl")
span=f"{px.index[0].date()} -> {px.index[-1].date()}"
print(f"\nKaydedildi _bist_px.pkl: {px.shape[1]} sembol × {px.shape[0]} gün ({span})")
# doluluk raporu
filled=px.notna().sum(axis=1)
print(f"Ortalama günlük mevcut sembol: {filled.mean():.0f} (min {filled.min()}, max {filled.max()})")
