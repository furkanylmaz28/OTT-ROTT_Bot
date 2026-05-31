"""
MT4 .hst (history) binary dosyası okuyucu — build 510+ (yeni format, 60 byte/bar).

Format referansı:
  Header (148 byte):
    int32   version       (4)
    char    copyright[64] (64)
    char    symbol[12]    (12)
    int32   period        (4)   timeframe
    int32   digits        (4)   ondalık hane
    int32   timesign      (4)   oluşturulma zamanı
    int32   last_sync     (4)
    int32   unused[13]    (52)

  Bar (60 byte):
    int64   ctm          (8)   Unix epoch saniye
    double  open         (8)
    double  high         (8)
    double  low          (8)
    double  close        (8)
    uint64  volume       (8)
    int32   spread       (4)
    uint64  real_volume  (8)
"""

from __future__ import annotations
import os
import struct
from pathlib import Path
from typing import Iterator
import pandas as pd


HEADER_FMT = "<i64s12siiii52s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)        # 148
BAR_FMT = "<q4dQiQ"
BAR_SIZE = struct.calcsize(BAR_FMT)              # 60

TF_MAP = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1",
          240: "H4", 1440: "D1", 10080: "W1", 43200: "MN1"}


def read_hst(path: str | Path) -> pd.DataFrame:
    """
    Bir .hst dosyasını okuyup OHLCV DataFrame döndürür (UTC index).
    """
    path = Path(path)
    data = path.read_bytes()
    if len(data) < HEADER_SIZE:
        raise ValueError(f"{path}: dosya çok küçük ({len(data)} byte)")

    version, copyright_, symbol, period, digits, timesign, last_sync, _ = \
        struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    symbol = symbol.split(b"\x00", 1)[0].decode("latin-1", errors="ignore")

    body = data[HEADER_SIZE:]
    n_bars, rem = divmod(len(body), BAR_SIZE)
    if rem != 0:
        # bazı broker'lar son barı yarım yazabilir; uyarı yerine sessizce kes
        body = body[:n_bars * BAR_SIZE]

    rows = []
    for i in range(n_bars):
        ctm, o, h, l, c, vol, spread, rvol = \
            struct.unpack(BAR_FMT, body[i * BAR_SIZE:(i + 1) * BAR_SIZE])
        rows.append((ctm, o, h, l, c, vol))

    df = pd.DataFrame(rows, columns=["ctm", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["ctm"], unit="s", utc=True)
    df = df.set_index("time").drop(columns="ctm")
    df.attrs["symbol"] = symbol
    df.attrs["period"] = period
    df.attrs["digits"] = digits
    df.attrs["tf"] = TF_MAP.get(period, f"M{period}")
    return df


def find_history(server: str, terminal_root: str | None = None) -> Path:
    """
    GCM-Demo gibi bir server adı verince history klasörünün yolunu döndürür.
    """
    if terminal_root is None:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA env yok")
        base = Path(appdata) / "MetaQuotes" / "Terminal"
        for t in base.iterdir():
            if len(t.name) == 32 and all(c in "0123456789ABCDEFabcdef" for c in t.name):
                p = t / "history" / server
                if p.is_dir():
                    return p
        raise FileNotFoundError(f"server={server} için history klasörü bulunamadı")
    return Path(terminal_root) / "history" / server


def load_symbol(server: str, symbol: str, tf: int = 5) -> pd.DataFrame:
    """
    Sembol + timeframe ile .hst dosyasını yükle.
    Örn: load_symbol('GCM-Demo', 'GOLD', 5) -> 5-dakikalık altın.
    """
    hist_dir = find_history(server)
    filename = f"{symbol}{tf}.hst"
    path = hist_dir / filename
    if not path.exists():
        # alternatif: # prefix'i deneme
        alt = hist_dir / f"#{symbol}{tf}.hst"
        if alt.exists():
            path = alt
        else:
            raise FileNotFoundError(f"{path} bulunamadı")
    return read_hst(path)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    df = load_symbol("GCM-Demo", "GOLD", 5)
    print(f"Symbol  : {df.attrs['symbol']}")
    print(f"TF      : {df.attrs['tf']} (period={df.attrs['period']})")
    print(f"Digits  : {df.attrs['digits']}")
    print(f"Bars    : {len(df)}")
    print(f"İlk bar : {df.index[0]}")
    print(f"Son bar : {df.index[-1]}")
    print(df.head(3))
    print("...")
    print(df.tail(3))
