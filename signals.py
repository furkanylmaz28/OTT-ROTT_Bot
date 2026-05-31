"""
Orta seviye sistem — Major trend + TOTT bölgesi + SOTT bölgesi.
.docx 2 ve 3'teki kurgunun, minör trend ve HOTT/LOTT kapıları çıkarılmış hali.

.docx 2'deki orjinal yapı (kısaltma):

    if (Major trend YUKARI):
        AL          = TOTT yukarı band  AND SOTT yukarı
        SAT         = TOTT aşağı band   AND SOTT aşağı
    else (Major trend AŞAĞI):
        AÇIĞA SAT   = TOTT aşağı band   AND SOTT aşağı
        AÇIK POZ K. = TOTT yukarı band  AND SOTT yukarı

Major trend filtresi long/short tarafını seçer; bölge sinyalleri ise açma/kapama
tetiğidir. Minör trend orta seviyede yok, dolayısıyla ana trendin yönü zorunlu.
"""

from __future__ import annotations
import pandas as pd
import indicators as ind


def build_signals(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    trend_length: int = 30,        # .docx opt1
    trend_percent: float = 7.0,    # .docx ana trend sabiti
    tott_percent: float = 0.8,     # .docx opt2
    tott_coeff: float = 0.0008,    # .docx opt3
    sott_period_k: int = 500,      # .docx opt4
    sott_smooth_k: int = 200,      # .docx opt5
    sott_percent: float = 0.3,     # .docx opt6
    shift: int = 2,                # Pine'daki OTT[2] shift'i
) -> pd.DataFrame:
    """
    Tüm indikatörleri hesaplayıp sinyal koşullarını döndürür.
    Çıktı sütunları:
        mavg, trend_ott, tott_up, tott_dn, sott_src, sott_ott
        major_up                          (ana trend yukarı mı)
        zone_up, zone_dn                  (TOTT+SOTT birleşik)
        cond_buy_long, cond_exit_long
        cond_buy_short, cond_exit_short
    """
    df = pd.DataFrame(index=close.index)

    # ── Ana trend katmanı: MOV(C,opt1,VAR) vs OTT(C,opt1,7)
    trend = ind.ott(close, trend_length, trend_percent, shift=shift)
    df["mavg"] = trend["mavg"]
    df["trend_ott"] = trend["ott"]
    df["major_up"] = df["mavg"] > df["trend_ott"]
    df["major_dn"] = df["mavg"] < df["trend_ott"]

    # ── TOTT bölgesi (gövde): MOV vs OTT(C,opt1,opt2)*(1±opt3)
    t = ind.tott(close, trend_length, tott_percent, tott_coeff, shift=shift)
    df["tott_up"] = t["ottup"]
    df["tott_dn"] = t["ottdn"]
    tott_zone_up = df["mavg"] > df["tott_up"]   # yukarı banda kırılım
    tott_zone_dn = df["mavg"] < df["tott_dn"]   # aşağı banda kırılım

    # ── SOTT bölgesi (gövde): STOSK+1000 vs OTT(STOSK+1000, 2, opt6)
    s = ind.sott(close, high, low, sott_period_k, sott_smooth_k,
                 length=2, percent=sott_percent, shift=shift)
    df["sott_src"] = s["src"]
    df["sott_ott"] = s["ott"]
    sott_up = df["sott_src"] > df["sott_ott"]
    sott_dn = df["sott_src"] < df["sott_ott"]

    df["zone_up"] = tott_zone_up & sott_up
    df["zone_dn"] = tott_zone_dn & sott_dn

    # ── Sinyal koşulları
    # AL    : Major yukarı VE Bölge yukarı
    # SAT   : Bölge aşağı (Long pozisyondan çık)
    # AÇIĞA SAT     : Major aşağı VE Bölge aşağı
    # AÇIK POZ KAPAT: Bölge yukarı (Short pozisyondan çık)
    df["cond_buy_long"] = df["major_up"] & df["zone_up"]
    df["cond_exit_long"] = df["zone_dn"]
    df["cond_buy_short"] = df["major_dn"] & df["zone_dn"]
    df["cond_exit_short"] = df["zone_up"]

    return df
