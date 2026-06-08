"""
Tam sistem — .docx 4'teki (TOTT+SOTT+HOTT+LOTT, minör trendli) yapının ROTT yamalı versiyonu.

Katmanlar:
  1) Ana trend     : MOV(C,opt1,VAR) vs OTT(C,opt1,7)        [if koşulu]
  2) Minör trend   : MOV(C,opt1,VAR) vs OTT(C,opt1,3.5)      [sadece pozisyon AÇAN]
  3) Bölge (gövde) : TOTT bandı + SOTT trendi                [her durumda]
  4) Kapı          : HOTT (yukarı) / LOTT (aşağı)            [her durumda]
  5) ROTT yaması   : 2*VAR(close,X2) vs OTT(.,X1,%)          [sadece pozisyon AÇAN]
  6) Saat (ops.)   : BIST/VİOP saat aralığı                  [opsiyonel]

Açma kuralları (.docx 2 mantığı):
  Ana trend YUKARI iken AL:  bölge_yukarı AND HOTT
  Ana trend AŞAĞI iken AL :  minör_yukarı AND bölge_yukarı AND HOTT
  Her durumda AL ek şartı :  ROTT_up

Kapama kuralları:
  SAT (long çıkış)        : bölge_aşağı AND LOTT
  AÇIK POZ KAPAT (short çıkış): bölge_yukarı AND HOTT
"""

from __future__ import annotations
import pandas as pd
import indicators as ind


def _gate(high: pd.Series, low: pd.Series, n: int, percent: float, gate_shift: int = 0):
    """HOTT (yukarı) ve LOTT (aşağı) kapı koşullarını döndürür.

    .docx formülü:
       HOTT: H > OTT(HHV(H,N/2), 2, percent) AND H > REF(HHV(H,N), -1)
       LOTT: L < OTT(LLV(L,N/2), 2, percent) AND L < REF(LLV(L,N), -1)

    gate_shift: HOTT/LOTT OTT bileşeni için bar shift. .docx (MetaStock) anlık,
    Pine'da görsel 2-bar gecikme var. Default=0 (.docx'e sadık).
    """
    half = max(int(n // 2), 1)
    # HOTT
    hhv_half = high.rolling(half).max()
    hott_line = ind.ott(hhv_half, 2, percent, shift=gate_shift)["ott" if gate_shift else "ott_raw"]
    hhv_full = high.rolling(n).max().shift(1)
    hott_ok = (high > hott_line) & (high > hhv_full)

    # LOTT
    llv_half = low.rolling(half).min()
    lott_line = ind.ott(llv_half, 2, percent, shift=gate_shift)["ott" if gate_shift else "ott_raw"]
    llv_full = low.rolling(n).min().shift(1)
    lott_ok = (low < lott_line) & (low < llv_full)

    return hott_ok, lott_ok


def build_signals_full(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    # ── ana trend
    trend_length: int = 30,
    trend_percent: float = 7.0,
    # ── minör trend (statik)
    minor_percent: float = 3.5,
    # ── bölge TOTT
    tott_percent: float = 0.8,
    tott_coeff: float = 0.0008,
    # ── bölge SOTT
    sott_period_k: int = 500,
    sott_smooth_k: int = 200,
    sott_percent: float = 0.3,
    # ── kapı HOTT/LOTT
    gate_length: int = 20,
    gate_percent: float = 0.5,
    gate_shift: int = 0,           # HOTT/LOTT OTT bileşeni shift (default .docx)
    # ── ROTT yaması (Pine formu)
    rott_x1: int = 30,
    rott_x2: int = 1000,
    rott_percent: float = 7.0,
    # ── opsiyonel saat filtresi
    apply_time_filter: bool = False,
    time_start_hour: int = 10, time_start_min: int = 3,
    time_end_hour: int = 16, time_end_min: int = 58,
    shift: int = 2,
) -> pd.DataFrame:
    df = pd.DataFrame(index=close.index)

    # ── Ana trend
    main_trend = ind.ott(close, trend_length, trend_percent, shift=shift)
    df["mavg"] = main_trend["mavg"]
    df["trend_ott"] = main_trend["ott"]
    df["major_up"] = df["mavg"] > df["trend_ott"]
    df["major_dn"] = df["mavg"] < df["trend_ott"]

    # ── Minör trend (statik 3.5)
    minor = ind.ott(close, trend_length, minor_percent, shift=shift)
    df["minor_up"] = df["mavg"] > minor["ott"]
    df["minor_dn"] = df["mavg"] < minor["ott"]

    # ── Bölge TOTT
    t = ind.tott(close, trend_length, tott_percent, tott_coeff, shift=shift)
    df["tott_up"] = t["ottup"]
    df["tott_dn"] = t["ottdn"]
    tott_up = df["mavg"] > df["tott_up"]
    tott_dn = df["mavg"] < df["tott_dn"]

    # ── Bölge SOTT
    s = ind.sott(close, high, low, sott_period_k, sott_smooth_k,
                 length=2, percent=sott_percent, shift=shift)
    df["sott_src"] = s["src"]
    df["sott_ott"] = s["ott"]
    sott_up = df["sott_src"] > df["sott_ott"]
    sott_dn = df["sott_src"] < df["sott_ott"]

    df["zone_up"] = tott_up & sott_up
    df["zone_dn"] = tott_dn & sott_dn

    # ── Kapı HOTT/LOTT
    hott_ok, lott_ok = _gate(high, low, gate_length, gate_percent, gate_shift=gate_shift)
    df["hott_ok"] = hott_ok
    df["lott_ok"] = lott_ok

    # ── ROTT yaması (Pine formu)
    r = ind.rott(close, x1=rott_x1, x2=rott_x2, percent=rott_percent, shift=shift)
    df["rott_perfect"] = r["perfect_ma2"]
    df["rott_line"] = r["ott"]
    df["rott_up"] = df["rott_perfect"] > df["rott_line"]   # long açmaya izin
    df["rott_dn"] = df["rott_perfect"] < df["rott_line"]   # short açmaya izin

    # ── AL koşulları (.docx 2 if mantığı + ROTT)
    al_main_up = df["zone_up"] & df["hott_ok"]
    al_main_dn = df["minor_up"] & df["zone_up"] & df["hott_ok"]
    cond_open_long = (
        ((df["major_up"] & al_main_up) | (df["major_dn"] & al_main_dn))
        & df["rott_up"]
    )

    # ── SAT (long çıkış) — bölge aşağı + kapı
    cond_close_long = df["zone_dn"] & df["lott_ok"]

    # ── AÇIĞA SAT
    as_main_dn = df["zone_dn"] & df["lott_ok"]
    as_main_up = df["minor_dn"] & df["zone_dn"] & df["lott_ok"]
    cond_open_short = (
        ((df["major_dn"] & as_main_dn) | (df["major_up"] & as_main_up))
        & df["rott_dn"]
    )

    # ── AÇIK POZ KAPAT (short çıkış)
    cond_close_short = df["zone_up"] & df["hott_ok"]

    # ── Opsiyonel saat filtresi
    if apply_time_filter:
        idx = close.index
        if idx.tz is None:
            t_local = idx
        else:
            t_local = idx.tz_convert(None)
        h = t_local.hour
        m = t_local.minute
        in_window = (
            ((h > time_start_hour) | ((h == time_start_hour) & (m >= time_start_min)))
            & ((h < time_end_hour) | ((h == time_end_hour) & (m <= time_end_min)))
        )
        in_window_s = pd.Series(in_window, index=idx)
        cond_open_long = cond_open_long & in_window_s
        cond_open_short = cond_open_short & in_window_s
        cond_close_long = cond_close_long & in_window_s
        cond_close_short = cond_close_short & in_window_s

    df["cond_buy_long"] = cond_open_long.fillna(False)
    df["cond_exit_long"] = cond_close_long.fillna(False)
    df["cond_buy_short"] = cond_open_short.fillna(False)
    df["cond_exit_short"] = cond_close_short.fillna(False)
    return df
