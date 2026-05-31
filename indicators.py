"""
Anıl Özekşi OTT-ailesi indikatörlerinin Python portu.
Pine Script kaynakları:
  - OTT.txt     (v4) — temel OTT
  - TOTT.txt    (v5) — Twin OTT (±coeff bantlı)
  - ROTT.txt    (v5) — Relative OTT (2*VAR üzerine OTT)
  - SOTT.txt    (v4) — Stochastic OTT

Bu modül yalnızca indikatör hesabını yapar. Sinyal mantığı signals.py'da.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

try:
    from numba import njit
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False
    def njit(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def wrap(f):
            return f
        return wrap


@njit(cache=True)
def _var_loop(data: np.ndarray, init_sma: np.ndarray, abs_cmo: np.ndarray, alpha: float) -> np.ndarray:
    n = data.shape[0]
    out = np.full(n, np.nan)
    started = False
    prev = np.nan
    for i in range(n):
        if not started:
            if not np.isnan(init_sma[i]):
                prev = init_sma[i]
                out[i] = prev
                started = True
            continue
        cur = abs_cmo[i] * alpha * (data[i] - prev) + prev
        out[i] = cur
        prev = cur
    return out


@njit(cache=True)
def _ott_loop(mavg: np.ndarray, percent: float):
    n = mavg.shape[0]
    long_stop = np.full(n, np.nan)
    short_stop = np.full(n, np.nan)
    direction = np.ones(n, dtype=np.int64)
    ott_raw = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(mavg[i]):
            continue
        fark = mavg[i] * percent * 0.01
        ls = mavg[i] - fark
        ss = mavg[i] + fark
        if i == 0 or np.isnan(long_stop[i - 1]):
            ls_prev = ls
        else:
            ls_prev = long_stop[i - 1]
        if i == 0 or np.isnan(short_stop[i - 1]):
            ss_prev = ss
        else:
            ss_prev = short_stop[i - 1]
        if mavg[i] > ls_prev and ls < ls_prev:
            ls = ls_prev
        if mavg[i] < ss_prev and ss > ss_prev:
            ss = ss_prev
        d_prev = direction[i - 1] if i > 0 else 1
        if d_prev == -1 and mavg[i] > ss_prev:
            d = 1
        elif d_prev == 1 and mavg[i] < ls_prev:
            d = -1
        else:
            d = d_prev
        mt = ls if d == 1 else ss
        if mavg[i] > mt:
            ott_raw[i] = mt * (200 + percent) / 200
        else:
            ott_raw[i] = mt * (200 - percent) / 200
        long_stop[i] = ls
        short_stop[i] = ss
        direction[i] = d

    return ott_raw, direction


def var_func(data: pd.Series, length: int) -> pd.Series:
    """
    Anıl Özekşi'nin VAR (VIDYA) hareketli ortalaması.
    Pine: f_var(data, u1) / Var_Func(src, length)

    a = 9 (CMO penceresi sabit)
    h = 2 / (length + 1)   alpha
    vidya[i] = g*h*(data[i] - vidya[i-1]) + vidya[i-1]
    burada g = |CMO_9| ∈ [0,1]
    """
    if length == 1:
        return data.copy()

    # Pine: b = data>data[1] ? data-data[1] : 0  (ilk bar'da data[1] NaN -> b[0]=0)
    # pandas data.diff() ilk değeri NaN bırakır; Pine ile uyumlu olması için 0'a doldur.
    diff = data.diff().fillna(0)
    up = diff.clip(lower=0)
    down = (-diff).clip(lower=0)
    # Pine: math.sum(b, 9) — ilk 8 bar NA. min_periods default = window.
    sum_up = up.rolling(9).sum()
    sum_down = down.rolling(9).sum()
    denom = sum_up + sum_down
    # Pine: nz((d-e)/(d+e)) — NaN ve 0/0 -> 0
    with np.errstate(divide="ignore", invalid="ignore"):
        cmo_raw = (sum_up - sum_down) / denom
    cmo = np.where(np.isfinite(cmo_raw) & (denom != 0), cmo_raw, 0.0)
    abs_cmo = np.abs(cmo)

    alpha = 2.0 / (length + 1)
    init_sma = data.rolling(length, min_periods=length).mean()

    data_arr = data.to_numpy(dtype=float)
    init_arr = init_sma.to_numpy(dtype=float)
    abs_cmo_arr = np.asarray(abs_cmo, dtype=float)
    out = _var_loop(data_arr, init_arr, abs_cmo_arr, alpha)

    return pd.Series(out, index=data.index, name=f"VAR{length}")


def ott(source: pd.Series, length: int, percent: float, shift: int = 2) -> dict:
    """
    Anıl Özekşi OTT (Optimized Trend Tracker).
    Pine: OTT(source, length, percent) -> nz(OTT[2])

    Dönüş: dict
       'mavg'    -> destek çizgisi (VAR)
       'ott_raw' -> ham OTT (shift yok)
       'ott'     -> görsel OTT (shift bar kadar geciktirilmiş — Pine ile uyumlu)
       'dir'     -> +1 yukarı trend / -1 aşağı trend
    """
    mavg = var_func(source, length)
    mavg_arr = mavg.to_numpy(dtype=float)
    ott_raw, direction = _ott_loop(mavg_arr, float(percent))
    ott_raw_s = pd.Series(ott_raw, index=source.index)
    return {
        "mavg": mavg,
        "ott_raw": ott_raw_s,
        "ott": ott_raw_s.shift(shift),
        "dir": pd.Series(direction, index=source.index),
    }


def tott(source: pd.Series, length: int, percent: float, coeff: float, shift: int = 2) -> dict:
    """
    Twin OTT — OTT'nin ±coeff ile band oluşturulmuş hali.
    Pine TOTT.txt mantığı:
       OTTup = OTT * (1 + coeff)
       OTTdn = OTT * (1 - coeff)
       plot(nz(OTTup[2])) / plot(nz(OTTdn[2]))
    """
    o = ott(source, length, percent, shift=0)
    ott_raw = o["ott_raw"]
    ottup_raw = ott_raw * (1 + coeff)
    ottdn_raw = ott_raw * (1 - coeff)
    return {
        "mavg": o["mavg"],
        "ott": ott_raw.shift(shift),
        "ottup": ottup_raw.shift(shift),
        "ottdn": ottdn_raw.shift(shift),
    }


def rott(close: pd.Series, x1: int = 30, x2: int = 1000, percent: float = 7.0, shift: int = 2) -> dict:
    """
    Relative OTT — Pine ROTT.txt formu.
    perfect_ma2 = 2 * f_var(close, X2)
    ott_line    = OTT(perfect_ma2, X1, percent)

    'perfect_ma2 > ott_line' yukarı trend (BUY),
    'perfect_ma2 < ott_line' aşağı trend (SELL) — pozisyon açmayı engeller.
    """
    perfect_ma2 = 2 * var_func(close, x2)
    o = ott(perfect_ma2, x1, percent, shift=shift)
    return {
        "perfect_ma2": perfect_ma2,
        "ott": o["ott"],
        "ott_raw": o["ott_raw"],
    }


def stoch_raw(close: pd.Series, high: pd.Series, low: pd.Series, period_k: int) -> pd.Series:
    """
    Pine ta.stoch / stoch karşılığı:
       100 * (close - lowest(low, n)) / (highest(high, n) - lowest(low, n))
    Pine: ta.lowest/ta.highest ilk period_k-1 bar NA döndürür.
    """
    ll = low.rolling(period_k).min()
    hh = high.rolling(period_k).max()
    rng = hh - ll
    with np.errstate(divide="ignore", invalid="ignore"):
        k = 100 * (close - ll) / rng
    return pd.Series(np.where(rng > 0, k, np.nan), index=close.index)


def sott(close: pd.Series, high: pd.Series, low: pd.Series,
         period_k: int = 500, smooth_k: int = 200,
         length: int = 2, percent: float = 0.5, shift: int = 2) -> dict:
    """
    Stochastic OTT — Pine SOTT.txt formu.
       raw_stoch = stoch(close, high, low, period_k)
       k         = Var_Func(raw_stoch, smooth_k)
       src       = k + 1000          (aralık kaydırma)
       OTT       = OTT(src, length=2, percent=0.5)

    Sinyal: src > nz(OTT[2]) -> stochastic yukarı trend.
    """
    raw = stoch_raw(close, high, low, period_k)
    k = var_func(raw, smooth_k)
    src = k + 1000
    o = ott(src, length, percent, shift=shift)
    return {
        "k": k,
        "src": src,
        "ott": o["ott"],
        "ott_raw": o["ott_raw"],
    }


def hott(high: pd.Series, n: int, percent: float = 0.5, shift: int = 0) -> pd.Series:
    """
    HOTT yaması — H > OTT(HHV(H, n/2), 2, percent) AND H > REF(HHV(H,n), -1).
    Bu fonksiyon ilk şartın OTT bileşenini döndürür.
    """
    hhv = high.rolling(max(int(n // 2), 1), min_periods=1).max()
    return ott(hhv, 2, percent, shift=shift)["ott_raw"]


def lott(low: pd.Series, n: int, percent: float = 0.5, shift: int = 0) -> pd.Series:
    """
    LOTT yaması — L < OTT(LLV(L, n/2), 2, percent) AND L < REF(LLV(L,n), -1).
    """
    llv = low.rolling(max(int(n // 2), 1), min_periods=1).min()
    return ott(llv, 2, percent, shift=shift)["ott_raw"]
