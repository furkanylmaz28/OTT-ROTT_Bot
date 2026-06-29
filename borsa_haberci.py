"""
borsa_haberci.py — "Borsa Habercisi" ajanı.
  1) KAP bildirimleri (şirket bazlı)              → get_news()
  2) Dünya + Türkiye makro haberleri (RSS)        → get_macro_news()
  3) Haber → 45 BIST hissesine ETKİ analizi       → analyze_impact()

KARAR/SİNYAL ÜRETMEZ — bağlam/istihbarat verir. Savunmacı: kaynağa ulaşılamazsa
çökmez. Cron (GitHub Actions) ortamında tam internet olduğu için orada çalışır.
"""
from __future__ import annotations
import re, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

TR = timezone(timedelta(hours=3))
_HDR = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/xml, */*"}
KAP_URL = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"

# Dünya + Türkiye finans RSS kaynakları (başlık çekilir)
RSS_FEEDS = [
    ("Dünya", "http://feeds.bbci.co.uk/news/business/rss.xml"),
    ("Dünya", "https://www.investing.com/rss/news_25.rss"),       # economy
    ("Dünya", "https://www.investing.com/rss/news_1.rss"),        # markets
    ("TR",    "https://www.bloomberght.com/rss"),
    ("TR",    "https://www.investing.com/rss/news_285.rss"),      # Türkiye
]

# ───────── Haber → BIST hisse ETKİ haritası ─────────
# (anahtar kelimeler, [(hisse, yön, sebep)])  yön: "+" olumlu / "-" olumsuz / "±" belirsiz
IMPACT_RULES = [
    (["brent", "ham petrol", "petrol fiyat", "crude", "opec", "varil", "oil price"],
     [("TUPRS", "+", "rafinaj marjı"), ("THYAO", "-", "yakıt maliyeti"),
      ("PGSUS", "-", "yakıt maliyeti")]),
    (["faiz", "tcmb", "merkez bankas", "ppk", "interest rate", "policy rate", "fed", "powell", "ecb"],
     [("BANKA", "±", "faiz marjı / kredi talebi"), ("EKGYO", "±", "konut faizi"),
      ("EMLAK", "±", "finansman maliyeti")]),
    (["dolar", "kur ", "tl ", "lira", "döviz", "usdtry", "devalüasyon"],
     [("IHRACATCI", "+", "döviz geliri"), ("EREGL", "+", "ihracat"), ("SASA", "+", "ihracat"),
      ("FROTO", "+", "ihracat"), ("ITHALATCI", "-", "maliyet artışı")]),
    (["altın", "ons altın", "gold"], [("PIYASA", "±", "güvenli liman talebi")]),
    (["savunma", "defense", "siha", "insansız", "milli muharip", "nato"],
     [("ASELS", "+", "savunma talebi")]),
    (["enflasyon", "tüfe", "cpi", "inflation"],
     [("PERAKENDE", "±", "fiyatlama gücü"), ("BIMAS", "±", "talep/marj"), ("MGROS", "±", "talep/marj")]),
    (["çelik", "steel", "demir cevheri", "iron ore"],
     [("EREGL", "+", "çelik fiyatı"), ("KRDMD", "+", "çelik fiyatı")]),
    (["doğalgaz", "natural gas", "elektrik fiyat", "enerji fiyat", "spot piyasa"],
     [("AKSEN", "±", "enerji marjı"), ("ENJSA", "±", "enerji"), ("ODAS", "±", "enerji")]),
    (["turizm", "turist", "tourism", "yolcu sayıs", "havalimanı"],
     [("THYAO", "+", "yolcu"), ("PGSUS", "+", "yolcu"), ("TAVHL", "+", "yolcu trafiği")]),
    (["otomotiv", "araç satış", "automotive", "taşıt kredisi"],
     [("FROTO", "+", "otomotiv talebi"), ("TOASO", "+", "otomotiv talebi"), ("DOAS", "+", "araç satışı")]),
    (["gübre", "fertilizer", "tarım", "buğday"], [("GUBRF", "+", "gübre talebi")]),
    (["beyaz eşya", "dayanıklı tüketim", "ihracat teşvik"],
     [("ARCLK", "+", "beyaz eşya"), ("VESTL", "+", "beyaz eşya")]),
    (["telekom", "5g", "tarife", "abonelik"], [("TTKOM", "+", "ARPU"), ("TCELL", "+", "ARPU")]),
    (["çimento", "inşaat", "konut", "kentsel dönüşüm", "müteahhit"],
     [("CIMSA", "+", "çimento talebi"), ("TKFEN", "+", "inşaat"), ("ENKAI", "+", "taahhüt"),
      ("EKGYO", "+", "konut")]),
    (["içecek", "bira", "gıda fiyat"], [("AEFES", "±", "içecek talebi"), ("ULKER", "±", "gıda")]),
    (["resesyon", "durgunluk", "kriz", "recession", "jeopolitik", "savaş", "tarife", "gümrük"],
     [("PIYASA", "-", "risk iştahı düşer")]),
    (["büyüme", "gdp", "gsyih", "teşvik paketi", "yatırım"], [("PIYASA", "+", "risk iştahı artar")]),
]

# Sektör grubu → 45 hissedeki gerçek semboller
_GROUPS = {
    "BANKA": ["AKBNK", "HALKB", "ISCTR", "VAKBN", "YKBNK", "GARAN", "TSKB"],
    "IHRACATCI": ["EREGL", "SASA", "FROTO", "TOASO", "KRDMD", "ARCLK", "VESTL"],
    "ITHALATCI": ["DOAS", "BIMAS", "MGROS"],
    "PERAKENDE": ["BIMAS", "MGROS", "SOKM", "ULKER"],
    "EMLAK": ["EKGYO"], "PIYASA": [], "ITHAL": [],
}


def _expand(code, universe):
    """Sektör grubunu/sembolü 45'lik evrene göre çöz."""
    if code in _GROUPS:
        return [s for s in _GROUPS[code] if not universe or s in universe]
    return [code] if (not universe or code in universe) else []


def get_macro_news(limit=40):
    """Dünya + Türkiye finans başlıkları (RSS). [{"bolge","title"}]. Çökmez."""
    out = []
    for bolge, url in RSS_FEEDS:
        try:
            r = requests.get(url, headers=_HDR, timeout=12)
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                t = item.findtext("title") or ""
                if t.strip():
                    out.append({"bolge": bolge, "title": t.strip()})
        except Exception:
            continue
    return out[:limit]


def analyze_impact(headlines, universe=None):
    """Başlıkları tara, etkilenen hisseleri yön+sebep ile döndür.
    [{"title","bolge","etkiler":[(hisse,yön,sebep)]}]. Sadece eşleşenler."""
    res = []
    for h in headlines:
        title = h["title"]; low = title.lower()
        hits = {}
        for keys, impacts in IMPACT_RULES:
            if any(k in low for k in keys):
                for code, yon, sebep in impacts:
                    for sym in _expand(code, universe) or ([code] if code in ("PIYASA",) else []):
                        hits.setdefault(sym, (yon, sebep))
                    if code == "PIYASA":
                        hits.setdefault("PİYASA", (impacts[0][1], impacts[0][2]))
        if hits:
            res.append({"title": title, "bolge": h.get("bolge", ""),
                        "etkiler": [(s, y, sb) for s, (y, sb) in list(hits.items())[:6]]})
    return res[:12]


def get_news(hours: int = 24, symbols: set | None = None) -> list:
    """KAP bildirimleri (şirket bazlı). Çökmez."""
    today = datetime.now(TR).date()
    body = {"fromDate": (today - timedelta(days=2)).isoformat(), "toDate": today.isoformat(),
            "year": "", "prd": "", "term": "", "ruleType": "", "bdkReview": "", "disclosureClass": "",
            "index": "", "market": "", "isLate": "", "subjectList": [], "mkkMemberOidList": [],
            "inactiveMkkMemberOidList": [], "bdkMemberOidList": [], "mainSector": "", "sector": "",
            "subSector": "", "memberType": "IGS", "fromSrc": "N", "srcCategory": "", "discIndex": []}
    try:
        data = requests.post(KAP_URL, json=body,
                             headers={**_HDR, "Content-Type": "application/json"}, timeout=25).json()
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    cutoff = datetime.now(TR) - timedelta(hours=hours)
    syms_up = {s.upper() for s in symbols} if symbols else None
    out = []
    for it in data:
        b = it.get("basic", it) if isinstance(it, dict) else {}
        codes = (b.get("stockCodes") or "").replace(" ", "")
        title = (b.get("title") or b.get("disclosureType") or "")[:90]
        code_list = [c for c in codes.split(",") if c]
        if syms_up and not any(c in syms_up for c in code_list):
            continue
        ts = b.get("publishDate") or ""
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "")).replace(tzinfo=TR)
            if dt < cutoff: continue
            tstr = dt.strftime("%H:%M")
        except Exception:
            tstr = str(ts)[:16]
        out.append({"sym": ", ".join(code_list) or b.get("companyName", "")[:20],
                    "title": title, "time": tstr})
    return out[:25]


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    UNI = set(("AKBNK ASELS DOHOL ENJSA EKGYO ENKAI EREGL FROTO GUBRF HALKB ISCTR KCHOL "
               "KRDMD MGROS PETKM PGSUS SASA SISE SOKM TAVHL THYAO TOASO TKFEN TTKOM TUPRS "
               "VAKBN YKBNK AEFES HEKTS ODAS ASTOR AKSEN ALARK KONTR ARCLK BIMAS GARAN OYAKC "
               "SAHOL TCELL TSKB VESTL DOAS CIMSA ULKER").split())
    mn = get_macro_news()
    print(f"Makro başlık: {len(mn)}")
    imp = analyze_impact(mn, UNI)
    print(f"BIST'e etkili: {len(imp)}\n")
    for x in imp[:8]:
        et = " · ".join(f"{s}{y}({sb})" for s, y, sb in x["etkiler"])
        print(f"[{x['bolge']}] {x['title'][:70]}\n   → {et}\n")
    if not mn:
        print("(RSS erişilemedi — cron ortamında çalışır)")
