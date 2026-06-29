"""
borsa_haberci.py — "Borsa Habercisi" ajanı. KAP bildirimlerini çeker, izlenen
sembollere dair son haberleri döndürür. SİNYAL ÜRETMEZ — sadece bağlam/istihbarat.

Savunmacı: KAP'a ulaşılamazsa çökmez, boş liste döner. Cron (GitHub Actions)
ortamında tam internet olduğu için orada çalışır.

Kullanım:
    import borsa_haberci as hb
    items = hb.get_news(hours=24, symbols={"GARAN","THYAO",...})
    # [{"sym","title","time","url"}, ...]
"""
from __future__ import annotations
import requests
from datetime import datetime, timedelta, timezone

TR = timezone(timedelta(hours=3))
KAP_URL = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
_HDR = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get_news(hours: int = 24, symbols: set | None = None) -> list:
    """Son `hours` saatteki KAP bildirimleri. symbols verilirse o sembollere filtre.
    Çökmez — hata/erişimsizlikte []."""
    today = datetime.now(TR).date()
    body = {
        "fromDate": (today - timedelta(days=2)).isoformat(),
        "toDate": today.isoformat(),
        "year": "", "prd": "", "term": "", "ruleType": "", "bdkReview": "",
        "disclosureClass": "", "index": "", "market": "", "isLate": "",
        "subjectList": [], "mkkMemberOidList": [], "inactiveMkkMemberOidList": [],
        "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "",
        "memberType": "IGS", "fromSrc": "N", "srcCategory": "", "discIndex": [],
    }
    try:
        r = requests.post(KAP_URL, json=body, headers=_HDR, timeout=25)
        data = r.json()
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
        title = b.get("title") or b.get("disclosureType") or ""
        oid = it.get("disclosureIndex") or b.get("disclosureIndex") or ""
        # zaman
        ts = b.get("publishDate") or b.get("kapTitle") or ""
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "")).replace(tzinfo=TR)
            if dt < cutoff:
                continue
            tstr = dt.strftime("%H:%M")
        except Exception:
            tstr = str(ts)[:16]
        code_list = [c for c in codes.split(",") if c]
        if syms_up and not any(c in syms_up for c in code_list):
            continue
        out.append({
            "sym": ", ".join(code_list) if code_list else (b.get("companyName", "")[:20]),
            "title": title[:90],
            "time": tstr,
            "url": f"https://www.kap.org.tr/tr/Bildirim/{oid}" if oid else "",
        })
    return out[:25]


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    news = get_news(hours=48)
    print(f"KAP bildirim: {len(news)}")
    for n in news[:10]:
        print(f"  {n['time']} · {n['sym']:14s} · {n['title']}")
    if not news:
        print("  (KAP erişilemedi ya da bildirim yok — cron ortamında tekrar denenecek)")
