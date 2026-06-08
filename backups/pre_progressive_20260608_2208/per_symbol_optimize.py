"""
BIST 30 + NASDAQ 30 için sembol bazlı sıralı optimize.
Her sembolün KENDİ en iyi parametrelerini bul.

yfinance üzerinden 60 günlük 5-dk veri kullanılır (intraday).
Sonuç: per_symbol_params.json — sembol başına optimum parametreler + backtest istatistikleri.

Toplam compute tahminim: ~21 dakika (60 sembol × ~21 sn).
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import json, time
from itertools import product
import numpy as np
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from data_source import fetch as ds_fetch


BIST30 = [
    # VIOP'ta vadeli işlem gören 45 hisse (kullanıcı doğruladı — gerçek işlem evreni)
    "AKBNK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","DOHOL.IS","ENJSA.IS",
    "EKGYO.IS","ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","GUBRF.IS",
    "HALKB.IS","ISCTR.IS","KCHOL.IS","KRDMD.IS","MGROS.IS","OYAKC.IS",
    "PETKM.IS","PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TOASO.IS","TKFEN.IS","TSKB.IS",
    "TTKOM.IS","TUPRS.IS","VAKBN.IS","VESTL.IS","YKBNK.IS","AEFES.IS",
    "HEKTS.IS","ODAS.IS","ASTOR.IS","AKSEN.IS","ALARK.IS","KONTR.IS",
    "DOAS.IS","CIMSA.IS","ULKER.IS",
]
def _load_gcm_stocks():
    """GCM Forex'teki hisseleri (US + EU/UK) yfinance ticker olarak çek."""
    try:
        with open("gcm_symbols.json", encoding="utf-8") as f:
            cats = json.load(f).get("categorized", {})
        with open("gcm_to_yf_map.json", encoding="utf-8") as f:
            mp = json.load(f)["mapping"]
        stock_keys = (cats.get("STOCK_US", []) +
                       cats.get("STOCK_OTHER", []) +
                       cats.get("STOCK_EU_UK", []))
        return sorted(set(mp[s] for s in stock_keys if s in mp))
    except Exception:
        return None

_gcm_stocks = _load_gcm_stocks()
NASDAQ100 = _gcm_stocks if _gcm_stocks else [
    # Fallback — gcm_symbols.json yoksa eski NASDAQ-100
    "AAPL","MSFT","AMZN","NVDA","GOOG","GOOGL","META","AVGO","TSLA","COST",
    "NFLX","AMD","PEP","ADBE","CSCO","TMUS","INTC","INTU","CMCSA","AMGN",
    "QCOM","TXN","HON","BKNG","AMAT","ISRG","GILD","ADP","MU","ADI",
    "MDLZ","SBUX","REGN","VRTX","LRCX","KLAC","PANW","SNPS","PYPL","CDNS",
]
CRYPTO30 = [
    "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD",
    "ADA-USD","DOGE-USD","TRX-USD","AVAX-USD","DOT-USD",
    "LINK-USD","MATIC-USD","LTC-USD","BCH-USD","UNI-USD",
    "ATOM-USD","ETC-USD","NEAR-USD","ALGO-USD","FIL-USD",
    "APT-USD","ARB-USD","OP-USD","SUI-USD","INJ-USD",
    "HBAR-USD","IMX-USD","RNDR-USD","TIA-USD","SEI-USD",
]
# Emtia + Forex (GCM Forex enstrümanları)
EMTIA_FX = [
    "GC=F",       # GOLD
    "SI=F",       # Silver
    "PA=F",       # Palladium
    "EURUSD=X",   # EURUSD
    "GBPUSD=X",   # GBPUSD
]


def fetch(symbol, interval: str | None = None, n_bars: int = 5000):
    """
    TradingView (login varsa) / yfinance fallback.
    interval=None ise kategoriye göre adaptif seçer:
      - CRYPTO: 30dk (7/24 işliyor, H1'de yetersiz trade)
      - BIST/NASDAQ/FOREX/COMMODITY/INDEX: H1 (~7-10 ay geçmiş)
    """
    from data_source import best_interval_for
    if interval is None:
        interval = best_interval_for(symbol)
    df = ds_fetch(symbol, interval=interval, n_bars=n_bars)
    if df.empty: return df
    keep = [c for c in ["open","high","low","close"] if c in df.columns]
    return df[keep].dropna()


def score(stats, min_trades=3):
    """Esnek skor: en iyi parametre seti her zaman bulunur. Rating sonradan verilir."""
    n = stats["n_trades"]
    pf = stats["profit_factor"]
    dd = abs(stats["max_drawdown"])
    ret = stats["total_return"]
    if n < min_trades: return -1e9
    if not np.isfinite(pf): pf = 5.0
    # Negatif return de sıralanır (en az kötü kazanır)
    if ret <= 0:
        return ret / (1 + dd)
    return ret * max(pf, 0.5) / (1 + dd)


def rating(stats):
    """Sembolün sisteme uygunluğunu derecele."""
    ret = stats["total_return"]
    pf = stats["profit_factor"] if np.isfinite(stats["profit_factor"]) else 5.0
    dd = abs(stats["max_drawdown"])
    n = stats["n_trades"]
    if n < 5: return "VERİ_AZ"
    if ret > 0.30 and pf >= 2.0 and dd < 0.25: return "MÜKEMMEL"
    if ret > 0.15 and pf >= 1.5 and dd < 0.30: return "İYİ"
    if ret > 0.05 and pf >= 1.2: return "ORTA"
    if ret > 0: return "MARJINAL"
    return "UYUMSUZ"


def evaluate(df, p):
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **p)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    # Ortalama trade süresi (bar cinsinden)
    closed = [t for t in res.trades if t.exit_price is not None]
    avg_bars = sum(t.bars_held for t in closed) / len(closed) if closed else 0
    stats = res.stats
    stats["avg_trade_bars"] = avg_bars
    return stats


def optimize_symbol(symbol):
    df = fetch(symbol)
    if df.empty or len(df) < 2000:
        return None

    base = dict(
        trend_length=30, trend_percent=7.0, minor_percent=3.5,
        tott_percent=0.8, tott_coeff=0.0008,
        sott_period_k=500, sott_smooth_k=200, sott_percent=0.3,
        gate_length=20, gate_percent=0.5, gate_shift=0,
        rott_x1=30, rott_x2=1000, rott_percent=7.0,
    )

    # Aşama 1 — Trend
    best, best_sc = base.copy(), -1e9
    for tl, tp, mp in product([20,30,35], [5.0,7.0,8.0], [3.0,3.5,4.0]):
        p = {**base, "trend_length": tl, "trend_percent": tp, "minor_percent": mp}
        st = evaluate(df, p); sc = score(st)
        if sc > best_sc: best_sc, best = sc, p.copy()
    if best_sc <= -1e9:
        return {"symbol": symbol, "ok": False, "reason": "n_trades < 5 her durumda"}
    base = best

    # Aşama 2 — Bölge
    best_sc = -1e9
    for tp, tc, pk, sp in product([0.6,0.8,1.0], [0.0004,0.0006,0.0008],
                                    [200,300,500], [0.2,0.3,0.4]):
        p = {**base, "tott_percent": tp, "tott_coeff": tc,
             "sott_period_k": pk, "sott_percent": sp}
        st = evaluate(df, p); sc = score(st)
        if sc > best_sc: best_sc, best = sc, p.copy()
    base = best

    # Aşama 3 — Kapı
    best_sc = -1e9
    for gl, gp, gs in product([10,16,22,28], [0.4,0.5,0.6], [0,2]):
        p = {**base, "gate_length": gl, "gate_percent": gp, "gate_shift": gs}
        st = evaluate(df, p); sc = score(st)
        if sc > best_sc: best_sc, best = sc, p.copy()

    from data_source import best_interval_for, category_of
    final = evaluate(df, best)
    rt = rating(final)
    return {
        "symbol": symbol, "ok": True, "bars": len(df),
        "rating": rt,
        "interval": best_interval_for(symbol),
        "category": category_of(symbol),
        "params": best,
        "stats": {
            "return": final["total_return"],
            "pf": final["profit_factor"] if np.isfinite(final["profit_factor"]) else None,
            "sharpe": final["sharpe"],
            "max_dd": final["max_drawdown"],
            "n_trades": final["n_trades"],
            "win_rate": final["win_rate"],
            "avg_trade_bars": final.get("avg_trade_bars", 0),
        },
    }


def main():
    symbols = BIST30 + NASDAQ100 + CRYPTO30 + EMTIA_FX
    print(f"Toplam {len(symbols)} sembol (BIST + NASDAQ + CRYPTO + EMTIA_FX) — sembol başına ~15sn → tahmini {len(symbols)*15/60:.0f} dakika")
    print()
    results = {}
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        ts = time.time()
        try:
            r = optimize_symbol(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)}
        dt = time.time() - ts

        if r and r.get("ok"):
            s = r["stats"]
            results[sym] = r
            pf_str = f"{s['pf']:.2f}" if s["pf"] else "∞"
            rt = r.get("rating", "?")
            print(f"[{i:2d}/{len(symbols)}] {sym:<12} {rt:<10} "
                  f"ret={s['return']*100:+7.1f}% PF={pf_str:>5} "
                  f"DD={s['max_dd']*100:+6.1f}% n={s['n_trades']:3d} "
                  f"win={s['win_rate']*100:.0f}%  ({dt:.0f}sn)")
        else:
            reason = r["reason"] if r else "veri yok"
            print(f"[{i:2d}/{len(symbols)}] {sym:<12} ✗ {reason}  ({dt:.0f}sn)")

        # Her 5 sembolde bir ara kayıt
        if i % 5 == 0:
            with open("per_symbol_params.json", "w") as f:
                json.dump(results, f, indent=2, default=str)

    elapsed = time.time() - t0
    print(f"\n  Toplam süre: {elapsed/60:.1f} dakika")
    print(f"  Başarılı: {len(results)}/{len(symbols)}")

    with open("per_symbol_params.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Sonuçlar: per_symbol_params.json")


if __name__ == "__main__":
    main()
