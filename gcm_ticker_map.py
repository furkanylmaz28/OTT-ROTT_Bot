"""
GCM Forex sembol kodlarını yfinance / TradingView ticker'larına çevir.

GCM'de sembol kodları:
  - #NVDA, #TSLA, #AMD  → kısa ticker, # at
  - #APPLE, #GOOGLE     → uzun isim, manuel mapping (STOCK_NAME_MAP)
  - #AAL.L, #SAP.DE     → EU/UK borsa, suffix koru
  - GOLD, SILVER         → emtia, doğrudan
  - EURUSD, USDJPY       → forex paritesi, doğrudan

yfinance formatı:
  - US hisseler: NVDA, AAPL, GOOGL (sade)
  - EU/UK:       AAL.L, SAP.DE, ASML.AS (suffix korunur)
  - Emtia:       GC=F (gold futures), SI=F (silver futures)
  - Forex:       EURUSD=X, USDJPY=X
"""
from __future__ import annotations
import json
import re

# ── Uzun isim → ticker manuel mapping
# GCM'deki #APPLE gibi uzun isimleri gerçek yfinance ticker'larına eşle
STOCK_NAME_MAP = {
    # Tech mega-cap
    "#APPLE":       "AAPL",
    "#MICROSOFT":   "MSFT",
    "#GOOGLE":      "GOOGL",
    "#AMAZON":      "AMZN",
    "#FACEBOOK":    "META",
    "#ALIBABA":     "BABA",
    "#ORACLE":      "ORCL",
    "#SALESFORCE":  "CRM",
    "#PAYPAL":      "PYPL",
    "#BROADCOM":    "AVGO",
    "#QUALCOMM":    "QCOM",
    "#TAIWANSM":    "TSM",
    "#SHOPIFY":     "SHOP",
    "#SPOTIFY":     "SPOT",
    "#REDDIT":      "RDDT",
    "#PINTEREST":   "PINS",
    "#SNAPCHAT":    "SNAP",
    "#PALANTIR":    "PLTR",
    "#PALOALTO":    "PANW",
    "#ZSCALER":     "ZS",
    "#WORKDAY":     "WDAY",
    "#SERVICENOW":  "NOW",
    "#SNOWFLAKE":   "SNOW",
    "#DROPBOX":     "DBX",
    "#UPSTART":     "UPST",
    "#ROBINHOOD":   "HOOD",
    "#SQUARE":      "SQ",
    "#TRADEDESK":   "TTD",
    "#DOORDASH":    "DASH",
    "#AIRBNB":      "ABNB",
    "#UBER":        "UBER",  # zaten kısa, ama # de var
    "#ZOOM":        "ZM",
    "#FAIRISAAC":   "FICO",
    "#AKAMAI":      "AKAM",
    "#AUTODESK":    "ADSK",
    "#CADENCE":     "CDNS",
    "#SYNOPSYS":    "SNPS",
    "#ADOBE":       "ADBE",
    "#INTUIT":      "INTU",
    "#ANALOGDEV":   "ADI",
    "#APPLIEDMAT":  "AMAT",
    "#LAMRESEARC":  "LRCX",
    "#MICRON":      "MU",
    "#WESTDIGITA":  "WDC",
    "#SEAGATE":     "STX",
    "#SKYWORKS":    "SWKS",
    "#TWILIO":      "TWLO",
    "#VERTEX":      "VRTX",
    "#GEVERNOVA":   "GEV",
    "#ILLUMINA":    "ILMN",
    "#PROGRESSIV":  "PGR",
    "#ROBLOX":      "RBLX",
    "#FIRSTSOLAR":  "FSLR",
    "#MICROVIS":    "MVIS",

    # Finans
    "#JP_MORGAN":   "JPM",
    "#MORGAN_STA":  "MS",
    "#WELLSFARGO":  "WFC",
    "#CITIGROUP":   "C",
    "#BERKSHIRE":   "BRK-B",
    "#BLACKROCK":   "BLK",
    "#BLACKSTONE":  "BX",
    "#GOLDMAN_S":   "GS",  # zaten #GS var, # at olur ama olsun
    "#MASTERCARD":  "MA",
    "#VISA":        "V",
    "#CAPITALONE":  "COF",
    "#SPGLOBAL":    "SPGI",
    "#REUTERS":     "TRI",

    # Sağlık + ilaç
    "#UTDHEALTH":   "UNH",
    "#JOHNSONJ":    "JNJ",
    "#JNJ":         "JNJ",
    "#PFIZER":      "PFE",
    "#MERCK":       "MRK",
    "#ABBVIE":      "ABBV",
    "#ABBOTT":      "ABT",
    "#LILLY":       "LLY",
    "#ELILILLY":    "LLY",
    "#BRISTOLMYE":  "BMY",
    "#MODERNA":     "MRNA",
    "#NOVAVAX":     "NVAX",
    "#BIONTECH":    "BNTX",
    "#GILEAD":      "GILD",
    "#REGENERON":   "REGN",
    "#NOVONORDIS":  "NVO",
    "#HUMANA":      "HUM",
    "#CARDINAL":    "CAH",
    "#MCKESSON":    "MCK",
    "#CENTENE":     "CNC",
    "#ELEVANCE":    "ELV",
    "#THERMOFISH":  "TMO",
    "#ESTEELAUD":   "EL",

    # Tüketim
    "#WAL_MART":    "WMT",
    "#WALMART":     "WMT",
    "#HOMEDEPOT":   "HD",
    "#COSTCO":      "COST",
    "#MCDONALDS":   "MCD",
    "#STARBUCKS":   "SBUX",
    "#NIKE":        "NKE",
    "#DISNEY":      "DIS",
    "#NETFLIX":     "NFLX",
    "#COCA-COLA":   "KO",
    "#PEPSICO":     "PEP",
    "#MONDELEZ":    "MDLZ",
    "#GENERALMIL":  "GIS",
    "#KIMBERLYC":   "KMB",
    "#COLGATE":     "CL",
    "#PHILIPMRS":   "PM",
    "#ALTRIA":      "MO",
    "#IMPERIAL":    "IMBBY",
    "#TARGET":      "TGT",
    "#LULULEMON":   "LULU",
    "#RALPHLAURE":  "RL",
    "#TJX":         "TJX",
    "#BESTBUY":     "BBY",
    "#WAYFAIR":     "W",
    "#CHIPOTLE":    "CMG",
    "#DOMINOS":     "DPZ",
    "#DRPEPPER":    "KDP",
    "#MONSTER":     "MNST",
    "#HEINTZ":      "KHC",
    "#CONBRANDS":   "CAG",
    "#ETSY":        "ETSY",
    "#BEYONDMEAT":  "BYND",
    "#FERRARI":     "RACE",
    "#TOYOTA":      "TM",
    "#HONDA":       "HMC",

    # Sanayi + Enerji
    "#BOEING":      "BA",
    "#LOCKHEEDM":   "LMT",
    "#GDYNAMICS":   "GD",
    "#GE":          "GE",
    "#CATERPILLAR": "CAT",
    "#DEERE":       "DE",
    "#3M":          "MMM",
    "#UNIONPAC":    "UNP",
    "#CANADARAIL":  "CNI",
    "#CHEVRON":     "CVX",
    "#EXXONMOBIL":  "XOM",
    "#CONOCOPHI":   "COP",
    "#SCHLUMBERG":  "SLB",
    "#KINDERMORG":  "KMI",
    "#ENBRIDGE":    "ENB",
    "#DUKEENERGY":  "DUK",
    "#SOUTHERN":    "SO",
    "#SOUTHERNCO":  "SO",
    "#NEXTERA":     "NEE",
    "#DOMINION":    "D",
    "#PACIFICGAS":  "PCG",
    "#SEMPRA":      "SRE",
    "#FREEPORT":    "FCX",
    "#NEWMONT":     "NEM",
    "#BARRICK":     "GOLD",  # Barrick Gold — dikkat: GCM'de "GOLD" sembolü emtia
    "#CAMECO":      "CCJ",
    "#BHPGROUP":    "BHP",
    "#TOURMALINE":  "TOU.TO",
    "#CANADIANSO":  "CNQ",
    "#COUCHETARD":  "ATD.TO",
    "#ROYALBANK":   "RY",
    "#TORDOMBANK":  "TD",
    "#SUNLIFE":     "SLF",
    "#MACQUARIE":   "MQG.AX",
    "#QANTAS":      "QAN.AX",

    # Diğer
    "#BOOKING":     "BKNG",
    "#EXPEDIA":     "EXPE",
    "#MARRIOTT":    "MAR",
    "#HILTON":      "HLT",
    "#LASVEGAS":    "LVS",
    "#ROYAL_CARB":  "RCL",
    "#DRHORTON":    "DHI",
    "#LENNAR":      "LEN",
    "#PULTEGROUP":  "PHM",
    "#PROLOGIS":    "PLD",
    "#PUBLICSTOR":  "PSA",
    "#REALTY":      "O",
    "#WELLTOWER":   "WELL",
    "#EQUINIX":     "EQIX",
    "#MARSH_N_MC":  "MMC",
    "#PROGRESSIV":  "PGR",
    "#GROUPON":     "GRPN",
    "#ZILLOW":      "Z",
    "#LEMONADE":    "LMND",
    "#UPSTART":     "UPST",
    "#CINTAS":      "CTAS",
    "#COPART":      "CPRT",
    "#ROSS":        "ROST",
    "#SYSCO":       "SYY",
    "#EXELON":      "EXC",
    "#XEL":         "XEL",
    "#AEP":         "AEP",
    "#CRONOS":      "CRON",
    "#AURORA":      "ACB",
    "#CANNATRES":   "CRON",
    "#TLRY":        "TLRY",
    "#SUNRUN":      "RUN",
    "#PLUG":        "PLUG",
    "#CHARGEPT":    "CHPT",
    "#RIVIAN":      "RIVN",
    "#LUCID":       "LCID",
    "#NIO":         "NIO",
    "#XPENG":       "XPEV",
    "#BAIDU":       "BIDU",
    "#JDCOM":       "JD",
    "#PDD":         "PDD",
    "#WEIBO":       "WB",
    "#TENCENT":     "TCEHY",
    "#HEPSIBURAD":  "HEPS",
    "#NTDOY":       "NTDOY",
    "#TEVA":        "TEVA",
    "#VRX":         "BHC",
    "#AMERICANTO":  "AAL",
    "#AMERICAN_E":  "AEP",
    "#AMERICAN_A":  "AAL",
    "#ANALOGDEV":   "ADI",
    "#ARCHERDM":    "ADM",
    "#AT&T":        "T",
    "#VERIZON":     "VZ",
    "#COMCAST":     "CMCSA",
    "#FORD":        "F",
    "#GM":          "GM",
    "#TESLA":       "TSLA",
    "#VIRGING":     "SPCE",
    "#MORGAN_STA":  "MS",
    "#NEXTERA":     "NEE",

    # Endeksler (CFD)
    "#NASDAQ":      "^IXIC",
    "#S&P":         "^GSPC",
    "#DJ":          "^DJI",
    "#DJ_EUR":      "^STOXX50E",
    "#DAX":         "^GDAXI",
    "#FTSE":        "^FTSE",
    "#FTSEMIB":     "FTSEMIB.MI",
    "#NIKKEI":      "^N225",
    "#HSI":         "^HSI",
    "#CAC":         "^FCHI",
    "#IBEX":        "^IBEX",
    "#RUSS":        "^RUT",
    "#VIX":         "^VIX",
    "#DOLLAR_IND":  "DX-Y.NYB",

    # Emtia
    "GOLD":         "GC=F",
    "SILVER":       "SI=F",
    "PALLADIUM":    "PA=F",
    "PLATINUM":     "PL=F",
    "COPPER":       "HG=F",
    "BRENT_OIL":    "BZ=F",
    "CrudeOIL":     "CL=F",
    "NATURAL_GAS":  "NG=F",
    "HEATING_OIL":  "HO=F",
    "GASOLINE":     "RB=F",
    "WHEAT":        "ZW=F",
    "CORN":         "ZC=F",
    "SOYBEAN":      "ZS=F",
    "COFFEE":       "KC=F",
    "COCOA":        "CC=F",
    "SUGAR#":       "SB=F",
    "COTTON#":      "CT=F",
    "ALUMINUM":     "ALI=F",

    # Bond
    "10Y_T-NOTES":  "^TNX",
    "30Y_T-BOND":   "^TYX",
    "5Y_T-NOTES":   "^FVX",

    # Kalan 7
    "#BROOKFIELD":  "BAM",
    "#DUPONT":      "DD",
    "#ENTERPRISE":  "EPD",
    "#LIFECO":      "GWO.TO",
    "#METLIFE":     "MET",
    "#ZOETIS":      "ZTS",
    "#GENERICHOL":  None,    # Generic Holding bilinmiyor, atla

    # GOLDEUR, GOLDTRY, TRYBASK yfinance'da yok — None bırak
}


def gcm_to_yf(gcm_sym: str) -> str | None:
    """GCM sembolünü yfinance ticker'ına çevir. None → eşleştirme yok."""
    s = gcm_sym.strip()
    # 1) Manuel mapping (None değer de "bilinmiyor" sayılır)
    if s in STOCK_NAME_MAP:
        v = STOCK_NAME_MAP[s]
        return v if v else None
    # 2) # ile başlayan kısa US ticker → # at
    if s.startswith("#"):
        body = s[1:]
        # 5 karakter veya daha kısa, sadece harf → US ticker
        if len(body) <= 5 and body.replace("&", "").replace("-", "").isalpha():
            return body
        # EU/UK suffix → # at, suffix koru
        for suf in (".L", ".DE", ".PA", ".AS", ".MC", ".BR", ".MI", ".TO", ".AX"):
            if body.endswith(suf):
                return body
        # Bilinmiyor
        return None
    # 3) Forex paritesi (6 harf) → yfinance EURUSD=X
    if len(s) == 6 and s.isalpha():
        return f"{s}=X"
    # 4) Mapping yok
    return None


def stats() -> dict:
    """gcm_symbols.json'a göre mapping kapsamını raporla."""
    try:
        with open("gcm_symbols.json", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"error": "gcm_symbols.json yok — extract_gcm_symbols.py çalıştır"}

    raw = data.get("raw", [])
    mapped = {}
    unmapped = []
    for s in raw:
        yf = gcm_to_yf(s)
        if yf:
            mapped[s] = yf
        else:
            unmapped.append(s)
    return {
        "total": len(raw),
        "mapped": len(mapped),
        "unmapped": len(unmapped),
        "coverage_pct": round(100 * len(mapped) / max(len(raw), 1), 1),
        "unmapped_list": unmapped,
        "mapping": mapped,
    }


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    s = stats()
    if "error" in s:
        print(s["error"]); sys.exit(1)
    print(f"GCM mapping kapsamı: {s['mapped']}/{s['total']} = %{s['coverage_pct']}")
    print(f"Eşleşmeyen: {s['unmapped']} sembol")
    if s["unmapped"]:
        print("\nİlk 20 eşleşmeyen sembol:")
        for u in s["unmapped_list"][:20]:
            print(f"  {u}")

    # mapping json kaydı
    with open("gcm_to_yf_map.json", "w", encoding="utf-8") as f:
        json.dump({
            "mapping": s["mapping"],
            "unmapped": s["unmapped"],
            "stats": {k: v for k, v in s.items() if k not in ("mapping", "unmapped_list")},
        }, f, indent=2, ensure_ascii=False)
    print(f"\n✓ gcm_to_yf_map.json kaydedildi")
