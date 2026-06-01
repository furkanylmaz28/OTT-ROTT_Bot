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
    """GCM sembollerini kategorize et.

    GCM kuralı:
      '#' ile başlayan = CFD hisse (US + EU + UK + Asya borsaları)
      6 harfli (USD/EUR/GBP/JPY/CHF/AUD/CAD/NZD/TRY): forex paritesi
      GOLD/SILVER/PLATINUM/COPPER vb: emtia
      ENDEKS'ler (NASDAQ, S&P, FTSE) — # ile veya .IDX
      Geri kalan: OTHER
    """
    cats = {
        "STOCK_US": [],         # Bilinen US (NVDA, AAPL, AMD vs)
        "STOCK_EU_UK": [],      # Avrupa borsa eki (.L, .DE, .PA, .AS vs)
        "STOCK_OTHER": [],      # Diğer # ile başlayan CFD'ler
        "INDEX": [],            # NASDAQ, FTSE, NIKKEI, DAX
        "COMMODITY": [],        # GOLD, SILVER, OIL, COFFEE
        "FOREX": [],            # 6 harfli pariteler
        "BOND": [],             # T-NOTES, T-BOND
        "OTHER": [],
    }
    # Hisse kategorisi için bilinen US ticker'lar (5 karakter veya daha kısa)
    # Geri kalanlar — #+uzun isim → STOCK_OTHER
    EU_SUFFIX = (".L", ".DE", ".PA", ".AS", ".MC", ".BR", ".MI")
    INDEX_KW = ("NASDAQ", "FTSE", "NIKKEI", "DAX", "DJ", "HSI", "VIX",
                 "S&P", "SPX", "IBEX", "CAC", "RUSS", "DOLLAR_IND")
    COMM_KW  = ("GOLD", "SILVER", "PLATINUM", "PALLADIUM", "COPPER", "ALUMIN",
                 "BRENT", "WTI", "OIL", "GAS", "GASOLINE", "HEATING",
                 "COFFEE", "COCOA", "SUGAR", "CORN", "WHEAT", "COTTON", "SOYBEAN")
    BOND_KW  = ("T-NOTES", "T-BOND", "BUND")

    for sym in symbols:
        s = sym.upper().lstrip("#")

        # ÖNCE: Forex paritesi (6 harf, tam eşleşme) — diğer keyword kontrollerinden ÖNCE
        if not sym.startswith("#") and len(s) == 6 and s.isalpha():
            cats["FOREX"].append(sym); continue
        # Bonds
        if any(k in s for k in BOND_KW):
            cats["BOND"].append(sym); continue
        # Endeksler — sadece # ile başlayan VEYA tam-keyword eşleşme
        if sym.startswith("#") and any(k in s for k in INDEX_KW):
            cats["INDEX"].append(sym); continue
        # Emtialar — # ile başlamayan emtialar (GOLD, SILVER vs)
        # # ile başlayan #LASVEGAS, #PACIFICGAS gibi hisseleri yakalamamak için
        if not sym.startswith("#") and any(k in s for k in COMM_KW):
            cats["COMMODITY"].append(sym); continue
        # Hisseler — # ile başlayanlar
        if sym.startswith("#"):
            if any(s.endswith(suf) for suf in EU_SUFFIX):
                cats["STOCK_EU_UK"].append(sym)
            elif len(s) <= 5 and s.isalpha():
                cats["STOCK_US"].append(sym)
            else:
                cats["STOCK_OTHER"].append(sym)
            continue
        # Geri kalan
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
