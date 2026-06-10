"""
ott_tott_confirm.py — Sadece OTT + TOTT sıralı teyit sinyali (kullanıcı sekmesi).

KURAL (kullanıcı tanımı):
  - OTT bir sinyal verir (LONG/SHORT). Bundan sonraki İLK TOTT sinyali AYNI yönde
    gelirse → onaylı sinyal (LONG/SHORT göster).
  - OTT sinyali verdikten sonra OTT TERS dönerse (long→short), bekleyen iptal olur;
    sonra gelen ters-yön TOTT teyidi SAYILMAZ.
  - Yani: OTT sinyalini, hemen peşindeki TOTT AYNI yönde onaylamalı.

Aynı formüller/timeframe (indicators.ott + indicators.tott, shift=2) — sistemin
geri kalanıyla birebir. Sadece bu iki indikatöre bakar; SOTT/HOTT/ROTT/rejim YOK.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import indicators as ind

# Teyit görünümü için sabit coeff — 0.0004 (ana sistem) band oluşturmaz, TOTT≈OTT.
# 0.01 (≈%1) anlamlı teyit bandı verir (TOTT, OTT'den sonra onaylar). Bu, ANALİZ
# görünümü içindir; ana sistem (signals_full) kendi optimize coeff'ini kullanır.
CONFIRM_COEFF = 0.01


def compute(close: pd.Series, length: int, percent: float, coeff: float, shift: int = 2):
    """OTT çizgisi + TOTT bandı + sıralı-teyitli sinyalleri döndür."""
    o = ind.ott(close, length, percent, shift=shift)
    t = ind.tott(close, length, percent, coeff, shift=shift)
    mavg = o["mavg"]
    ott_line = o["ott"]
    tott_up = t["ottup"]
    tott_dn = t["ottdn"]

    # ── Kesişimler (crossover) — bool dtype korunmalı (shift fill_value=False),
    #    yoksa object-dtype'ta '~True' Python'da -2 olur (bitwise) → bug.
    above_ott = (mavg > ott_line).astype(bool)
    above_tup = (mavg > tott_up).astype(bool)
    below_tdn = (mavg < tott_dn).astype(bool)

    ott_long  = above_ott & ~above_ott.shift(1, fill_value=False)        # mavg OTT'yi yukarı kesti
    ott_short = ~above_ott & above_ott.shift(1, fill_value=False)        # mavg OTT'yi aşağı kesti
    tott_long  = above_tup & ~above_tup.shift(1, fill_value=False)       # mavg TOTT_up'ı yukarı kesti
    tott_short = below_tdn & ~below_tdn.shift(1, fill_value=False)       # mavg TOTT_dn'i aşağı kesti

    # ── Sıralı teyit durum makinesi
    idx = close.index
    n = len(idx)
    ol = ott_long.values; os_ = ott_short.values
    tl = tott_long.values; ts = tott_short.values
    pending = None              # 'LONG' / 'SHORT' / None
    sig = [None] * n            # onaylı sinyal barı: 'LONG'/'SHORT'
    for i in range(n):
        # OTT sinyali bekleyeni günceller (ters OTT → eskisini iptal eder)
        if ol[i]:
            pending = "LONG"
        elif os_[i]:
            pending = "SHORT"
        # TOTT teyidi — sadece bekleyenle AYNI yönde ise onayla
        if tl[i] and pending == "LONG":
            sig[i] = "LONG"; pending = None
        elif ts[i] and pending == "SHORT":
            sig[i] = "SHORT"; pending = None

    df = pd.DataFrame({
        "close": close, "mavg": mavg,
        "ott": ott_line, "tott_up": tott_up, "tott_dn": tott_dn,
        "ott_long": ott_long, "ott_short": ott_short,
        "tott_long": tott_long, "tott_short": tott_short,
        "confirm": pd.Series(sig, index=idx),
    }, index=idx)
    return df


def confirmed_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Sadece onaylı sinyal barlarını döndür (tarih, yön, fiyat)."""
    c = df[df["confirm"].notna()].copy()
    return c[["close", "confirm"]].rename(columns={"close": "price", "confirm": "yon"})


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    import warnings; warnings.filterwarnings("ignore")
    from dotenv import load_dotenv; load_dotenv(".env")
    import json
    from data_source import fetch as ds_fetch, best_interval_for

    # VESTL params (mold/grid)
    g = json.load(open("per_symbol_params.json", encoding="utf-8"))
    for sym in ["VESTL.IS", "ASELS.IS"]:
        p = g.get(sym, {}).get("params", {})
        L = p.get("trend_length", 40); P = p.get("trend_percent", 7.0); C = p.get("tott_coeff", 0.0004)
        df = ds_fetch(sym, interval=best_interval_for(sym), n_bars=2500)
        if df.empty:
            print(f"{sym}: veri yok"); continue
        r = compute(df["close"], L, P, C)
        cs = confirmed_signals(r)
        print(f"\n{sym} (L={L} %={P} coeff={C}) — son 8 onaylı sinyal:")
        for ts, row in cs.tail(8).iterrows():
            print(f"  {ts:%d/%m %H:%M}  {row['yon']:5s}  @ {row['price']:.2f}")
        print(f"  Toplam onaylı sinyal: {len(cs)}")
