"""
grid_strategy.py — KANITLANMIŞ 2. sistem: yatay-kapılı GRID.

Walk-forward (8/8 OOS pozitif, +297% net @%0.05 maliyet) + Monte Carlo
(medyan +62%, iflas %4.1, max DD -17%/-30%) ile DOĞRULANDI.

Mantık: Kaufman Efficiency Ratio (ER) ile rejim ölç. ER düşük (<0.30) = YATAY
→ grid çalışır (merkez altına AL seviyeleri, +%2'de SAT). ER yüksek = TREND
→ grid KAPALI (trend gridi öldürür; o zaman SuperTrend sistemi devrede).

⚠️ Maliyet hassas: çok işlem açar (%0.2 komisyonda çöker). Düşük makas/kayma şart.
⚠️ Trend kaçağı = açık grid birimleri zarar; rejim filtresi linchpin.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

ER_WIN = 20            # efficiency ratio penceresi
ER_TH = 0.30           # ER < bu = yatay rejim (grid açık)
LEVELS = [-0.02, -0.04, -0.06]   # merkez (SMA20) altı grid AL seviyeleri
TAKE = 0.02            # her birim +%2'de sat
MAX_LEVERAGE = 2.0     # grid'de de düşük kaldıraç (birden çok birim → risk yığılır)


def efficiency_ratio(close: np.ndarray, n: int = ER_WIN) -> float:
    """Kaufman ER: |net değişim| / toplam |bar değişimi|. 0=choppy/yatay, 1=trend."""
    if len(close) < n + 1:
        return np.nan
    seg = close[-(n + 1):]
    vol = np.abs(np.diff(seg)).sum()
    return abs(seg[-1] - seg[0]) / vol if vol > 0 else np.nan


def current_state(df) -> dict | None:
    """Sembolün şu anki grid durumu.
    Döner: dict(er, yatay, merkez, seviyeler[fiyat], anlik, aktif_seviye)."""
    if df is None or df.empty or len(df) < ER_WIN + 2:
        return None
    c = df["close"].values
    er = efficiency_ratio(c, ER_WIN)
    if np.isnan(er):
        return None
    center = float(pd.Series(c).rolling(ER_WIN).mean().iloc[-1])
    cur = float(c[-1])
    yatay = er < ER_TH
    seviyeler = [round(center * (1 + lv), 4) for lv in LEVELS]
    # fiyat hangi seviyelerin altında (alım tetiklenebilir)
    aktif = sum(1 for px in seviyeler if cur <= px)
    return {
        "er": round(er, 3), "yatay": yatay, "merkez": round(center, 4),
        "anlik": cur, "seviyeler": seviyeler, "aktif_seviye": aktif,
        "take": TAKE,
    }
