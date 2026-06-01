"""
GCM MT4 history klasöründen sembol listesini çıkar.

MT4'te Market Watch panelinden "Show All" deyip History Center'dan
istediğin sembolleri açtıysan, o sembollerin .hst dosyaları
%APPDATA%\\MetaQuotes\\Terminal\\<ID>\\history\\GCM-Demo\\ klasöründedir.

Bu script o klasörü tarayıp benzersiz sembol listesini üretir.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import re
from pathlib import Path
import json


def list_gcm_symbols(server: str = "GCM-Demo") -> dict[str, list[str]]:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "MetaQuotes" / "Terminal"
    # Terminal ID klasörlerini bul (32 hex char)
    terminals = [t for t in base.iterdir()
                 if len(t.name) == 32 and all(c in "0123456789ABCDEFabcdef" for c in t.name)]

    all_symbols = {}
    for t in terminals:
        hist = t / "history" / server
        if not hist.is_dir():
            continue
        for hst in hist.glob("*.hst"):
            # Dosya adı örn: AAPL60.hst, #NASDAQ1001.hst, GOLD5.hst
            name = hst.stem  # AAPL60, #NASDAQ1001
            # Sonundaki rakamları sıyır → sembol kodu kalır
            m = re.match(r"(.+?)(\d+)$", name)
            if m:
                sym = m.group(1)
            else:
                sym = name
            sym = sym.strip()
            if sym not in all_symbols:
                all_symbols[sym] = []
            all_symbols[sym].append(name)

    return all_symbols


def categorize_gcm(symbols: list[str]) -> dict[str, list[str]]:
    """GCM sembollerini kategorize et."""
    cats = {
        "STOCK_US": [],     # US hisseler (AAPL, NVDA, vb)
        "STOCK_BIST": [],   # BIST hisseler (eğer GCM'de varsa)
        "INDEX": [],        # NAS100, US30, SPX vs.
        "COMMODITY": [],    # GOLD, SILVER, OIL vs.
        "FOREX": [],        # EURUSD, GBPUSD vs.
        "CRYPTO": [],       # BTC, ETH (varsa)
        "OTHER": [],
    }
    for sym in symbols:
        s = sym.upper().lstrip("#")
        # Forex paireri 6 karakter, harf
        if len(s) == 6 and s.isalpha():
            cats["FOREX"].append(sym)
        elif s in {"GOLD", "SILVER", "NGAS", "USOIL", "UKOIL", "XAUUSD", "XAGUSD",
                    "COPPER", "PLATINUM", "PALLADIUM"}:
            cats["COMMODITY"].append(sym)
        elif s in {"NASDAQ100", "SPX500", "US30", "DAX30", "FTSE100", "NIKKEI",
                    "NAS100", "DJ30", "GER40", "NK225"}:
            cats["INDEX"].append(sym)
        elif s.endswith(".IS") or s.endswith("E"):  # BIST genelde .E veya .IS
            cats["STOCK_BIST"].append(sym)
        elif "BTC" in s or "ETH" in s or "USDT" in s:
            cats["CRYPTO"].append(sym)
        elif len(s) <= 5 and s.isalpha():
            cats["STOCK_US"].append(sym)
        else:
            cats["OTHER"].append(sym)
    return cats


def main():
    print("GCM-Demo history klasörü taranıyor...\n")
    syms = list_gcm_symbols("GCM-Demo")
    print(f"Toplam {len(syms)} benzersiz sembol bulundu.\n")

    sorted_syms = sorted(syms.keys())
    cats = categorize_gcm(sorted_syms)

    print("=" * 60)
    for cat, items in cats.items():
        if not items: continue
        print(f"\n{cat} ({len(items)} sembol):")
        # Sırala ve 5'erli grupla
        items = sorted(items)
        for i in range(0, len(items), 8):
            print("  " + "  ".join(f"{s:<12}" for s in items[i:i+8]))

    # JSON'a yaz
    with open("gcm_symbols.json", "w", encoding="utf-8") as f:
        json.dump({"raw": sorted_syms, "categorized": cats}, f, indent=2)
    print(f"\n  ✓ gcm_symbols.json yazıldı")

    # Python set olarak app.py'da kullanmaya hazır kod
    us_stocks = sorted(cats["STOCK_US"])
    print(f"\n# app.py için (US hisseler):")
    print("GCM_NASDAQ = {")
    for i in range(0, len(us_stocks), 8):
        line = ", ".join(f'"{s}"' for s in us_stocks[i:i+8])
        print(f'    {line},')
    print("}")


if __name__ == "__main__":
    main()
