"""
Unified veri kaynağı — TradingView (tvDatafeed) öncelikli, fallback yfinance.

Kullanım:
   from data_source import fetch
   df = fetch("NVDA", interval="5m", n_bars=10000)

TradingView login için .env dosyasına şu satırları ekle:
   TV_USERNAME=your_tradingview_username
   TV_PASSWORD=your_tradingview_password

Login yoksa anonim modda çalışır (5000 bar limit).
"""
from __future__ import annotations
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── TradingView setup
_tv_client = None
_tv_login_attempted = False

def _get_tv():
    global _tv_client, _tv_login_attempted
    if _tv_client is not None:
        return _tv_client
    if _tv_login_attempted:
        return None
    _tv_login_attempted = True
    try:
        from tvDatafeed import TvDatafeed
        user = os.getenv("TV_USERNAME")
        pwd = os.getenv("TV_PASSWORD")
        if user and pwd:
            _tv_client = TvDatafeed(username=user, password=pwd)
            print(f"  [data_source] TradingView LOGIN modunda ({user})")
        else:
            _tv_client = TvDatafeed()
            print("  [data_source] TradingView anonim modda (5000 bar limit)")
    except Exception as e:
        print(f"  [data_source] tvDatafeed kurulamadı: {e}")
        _tv_client = None
    return _tv_client


# ── tvDatafeed interval map
_TV_INTERVAL = {
    "1m": "in_1_minute", "3m": "in_3_minute", "5m": "in_5_minute",
    "15m": "in_15_minute", "30m": "in_30_minute", "45m": "in_45_minute",
    "1h": "in_1_hour", "2h": "in_2_hour", "3h": "in_3_hour",
    "4h": "in_4_hour", "1d": "in_daily", "1w": "in_weekly", "1mo": "in_monthly",
}


def category_of(symbol: str) -> str:
    """Sembolün kategorisini döndür: BIST / CRYPTO / FOREX / COMMODITY / INDEX / NASDAQ"""
    s = symbol.upper()
    if s.endswith(".IS"): return "BIST"
    if s.endswith("-USD"): return "CRYPTO"
    if s.endswith("=X"): return "FOREX"
    if s.endswith("=F"): return "COMMODITY"
    if s.startswith("^"): return "INDEX"
    return "NASDAQ"


def best_interval_for(symbol: str) -> str:
    """
    Kategoriye göre 'profesyonel kullanım' için en uygun timeframe.
    Mantık: 5000 bar civarında **en az 4-6 ay geçmiş** olmalı, **yeterli trade** üretmeli.
    """
    cat = category_of(symbol)
    # Crypto 7/24: 30dk = ~3.5 ay yeterli, daha aktif trade
    if cat == "CRYPTO": return "30m"
    # BIST: günde 9 saat = az bar/gün, H1 zaten çok geriye gider
    if cat == "BIST": return "1h"
    # Hisse, forex, commodity, index: H1 ideal
    return "1h"


# ── Sembol → (exchange, tv_symbol) çözücüsü
def _resolve_tv_symbol(symbol: str) -> tuple[str, str] | None:
    """yfinance sembolünü TradingView'a çevir."""
    s = symbol.upper()

    # BIST — .IS uzantısı
    if s.endswith(".IS"):
        return ("BIST", s[:-3])

    # Crypto — -USD uzantısı
    if s.endswith("-USD"):
        coin = s[:-4]
        # TradingView'da USDT pair daha iyi (Binance)
        if coin in {"BTC","ETH","BNB","SOL","XRP","ADA","DOGE","TRX","AVAX","DOT",
                     "LINK","MATIC","LTC","BCH","UNI","ATOM","ETC","NEAR","ALGO","FIL",
                     "APT","ARB","OP","SUI","INJ","HBAR","IMX","RNDR","TIA","SEI"}:
            return ("BINANCE", f"{coin}USDT")
        return ("CRYPTO", f"{coin}USD")

    # Forex — =X uzantısı
    if s.endswith("=X"):
        pair = s[:-2]  # EURUSD=X → EURUSD
        return ("OANDA", pair)

    # Futures — =F uzantısı (GC=F = Gold, SI=F = Silver vs)
    if s.endswith("=F"):
        m = {"GC=F":"XAUUSD", "SI=F":"XAGUSD", "CL=F":"USOIL",
              "NG=F":"NATGASUSD", "HG=F":"COPPERUSD"}
        if symbol in m:
            return ("OANDA", m[symbol])

    # Index ^ — örn ^GSPC → SPX
    if s.startswith("^"):
        m = {"^GSPC":"SPX", "^IXIC":"NDX", "^DJI":"DJI",
              "^N225":"NI225", "^GDAXI":"DAX", "^FTSE":"UKX"}
        if symbol in m:
            return ("INDEX", m[symbol])

    # Default — NASDAQ varsay
    return ("NASDAQ", s)


# ── Ana fetch fonksiyonu
def fetch(symbol: str, interval: str = "5m", n_bars: int = 5000) -> pd.DataFrame:
    """
    Verilen sembolün OHLC verisini döndür (DataFrame: open, high, low, close).
    Önce TradingView'dan dener; başarısız olursa yfinance fallback.

    Args:
        symbol: yfinance formatında (NVDA, ASELS.IS, BTC-USD, EURUSD=X, GC=F, ^GSPC)
        interval: '1m','3m','5m','15m','30m','1h','4h','1d'
        n_bars: kaç bar (anonim mode max ~5000)

    Returns:
        DataFrame with columns: open, high, low, close (index = datetime)
        Empty DataFrame if no data.
    """
    # 1) TradingView dene
    tv = _get_tv()
    if tv is not None:
        resolved = _resolve_tv_symbol(symbol)
        if resolved:
            exch, tv_sym = resolved
            try:
                from tvDatafeed import Interval
                tv_interval = getattr(Interval, _TV_INTERVAL.get(interval, "in_5_minute"))
                df = tv.get_hist(symbol=tv_sym, exchange=exch,
                                  interval=tv_interval, n_bars=n_bars)
                if df is not None and not df.empty:
                    # Multi-exchange ise birden çok exchange dene
                    df = df.rename(columns=str.lower)
                    keep = [c for c in ["open","high","low","close","volume"] if c in df.columns]
                    return df[keep]
            except Exception:
                pass  # Sessizce yfinance'a düş

    # 2) yfinance fallback — TradingView başarısız oldu, YEDEK devrede.
    #    Her kullanımı işaretle (TV ne sıklıkta çöküyor + kötü veri kontrolü).
    #    yfinance BIST'te gecikmeli/boşluklu → BIST'te bu uyarıyı ciddiye al.
    _bist = symbol.upper().endswith(".IS")
    print(f"  ⚠️ [data_source] yfinance YEDEK kullanılıyor → {symbol} "
          f"({'BIST — gecikmeli/boşluklu olabilir!' if _bist else 'TV çöktü'})")
    # Yedek kullanımını dosyaya da yaz (sayım/izleme için)
    try:
        from datetime import datetime, timezone, timedelta
        _tr = datetime.now(timezone(timedelta(hours=3))).isoformat()
        with open("yfinance_fallback.log", "a", encoding="utf-8") as _lf:
            _lf.write(f"{_tr}\t{symbol}\t{interval}\n")
    except Exception:
        pass

    try:
        import yfinance as yf
        # yfinance 4h sunmaz → 60m çekip 4 saate resample edilir (yanlış TF bug fix).
        yf_int = {"5m":"5m", "15m":"15m", "30m":"30m", "1h":"60m",
                  "4h":"60m", "1d":"1d"}.get(interval, "5m")
        period = "60d" if interval in ("1m","3m","5m","15m","30m") else "2y"
        df = yf.download(symbol, period=period, interval=yf_int,
                          auto_adjust=False, progress=False, threads=False)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.rename(columns=str.lower)
        keep = [c for c in ["open","high","low","close","volume"] if c in df.columns]
        df = df[keep].dropna()
        # 4h istendiyse 60m veriyi 4 saate topla (yoksa 1h veriyi 4h sanardı)
        if interval == "4h" and not df.empty:
            agg = {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
            agg = {k:v for k,v in agg.items() if k in df.columns}
            df = df.resample("4h").agg(agg).dropna()
        return df
    except Exception:
        return pd.DataFrame()


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    print("\n=== TEST ===")
    for sym, interval in [
        ("NVDA", "5m"),
        ("ASELS.IS", "5m"),
        ("BTC-USD", "5m"),
        ("EURUSD=X", "15m"),
        ("GC=F", "15m"),
    ]:
        df = fetch(sym, interval, n_bars=5000)
        if df.empty:
            print(f"  {sym:<12} {interval}: VERİ YOK")
        else:
            print(f"  {sym:<12} {interval}: {len(df):>5} bar  {df.index[0]} → {df.index[-1]}")
