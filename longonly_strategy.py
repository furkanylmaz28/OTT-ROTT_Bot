"""
longonly_strategy.py — KANITLANMIŞ sistem: M60 long-only + nakit, SuperTrend.

Walk-forward (8/8 OOS pozitif, 8/8 drawdown al-tut'tan düşük) + Monte Carlo
(medyan +247%, iflas %10.6 kaldıraçsız) ile DOĞRULANDI. Short YOK (rejim-kapılı
bile değer katmadı). Kaldıraç tavanı ~2× (1:7 = iflas).

Mantık: SuperTrend yukarı → LONG. Yön aşağı dönerse → NAKİT (short açma).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

ST_PERIOD = 14
ST_MULT = 3.0
MAX_LEVERAGE = 2.0   # VIOP: toplam notional ≤ 2× hesap (1:7 = iflas)


def supertrend(df, period=ST_PERIOD, mult=ST_MULT):
    """SuperTrend yön dizisi (+1 yukarı / -1 aşağı)."""
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    n = len(c); tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values
    hl2 = (h + l) / 2
    up = hl2 + mult * atr; dn = hl2 - mult * atr
    fu = up.copy(); fd = dn.copy(); d = np.ones(n); line = np.zeros(n)
    for i in range(1, n):
        fu[i] = up[i] if (up[i] < fu[i-1] or c[i-1] > fu[i-1]) else fu[i-1]
        fd[i] = dn[i] if (dn[i] > fd[i-1] or c[i-1] < fd[i-1]) else fd[i-1]
        d[i] = 1 if c[i] > fu[i-1] else (-1 if c[i] < fd[i-1] else d[i-1])
        line[i] = fd[i] if d[i] > 0 else fu[i]
    return d, line


def current_state(df):
    """Sembolün şu anki KANITLANMIŞ-sistem durumu (long-only).
    Döner: dict(pozisyon, cizgi, bars_in_pos, son_donus_fiyat)."""
    if df is None or df.empty or len(df) < 60:
        return None
    d, line = supertrend(df)
    # son KAPANMIŞ bar (oluşan bar değil)
    ix = -2 if len(d) >= 2 else -1
    pos = "LONG" if d[ix] > 0 else "NAKİT"
    cur = float(df["close"].iloc[-1])
    stop = float(line[ix])   # SuperTrend çizgisi = long'da takip stopu
    # kaç bardır bu durumda (ix dahil)
    k = 1
    while (ix - k) >= -len(d) and d[ix - k] == d[ix]:
        k += 1
    # dönüş (sinyal) barı = bu durumun ilk barı
    flip = ix - (k - 1)
    donus = None; donus_tarih = None
    try:
        donus = float(df["close"].iloc[flip])
        donus_tarih = df.index[flip]   # TR-naive timestamp (sinyal tarihi)
    except Exception:
        pass
    # tazelik: kaç bar geçmiş → trene geç mi bindik? (M60: ~8-9 bar = 1 işlem günü)
    if k <= 9:       tazelik = "🟢 TAZE"        # ~1 gün içinde döndü
    elif k <= 27:    tazelik = "🟡 yeni"        # ~1-3 gün
    else:            tazelik = "🔴 olgun (geç)"  # 3+ gün, trend olgunlaşmış
    return {
        "pozisyon": pos, "anlik": cur, "cizgi": stop,
        "tampon": (cur / stop - 1) * 100 if pos == "LONG" else None,
        "bars": k, "donus_fiyat": donus, "donus_tarih": donus_tarih,
        "tazelik": tazelik,
    }
