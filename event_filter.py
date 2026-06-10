"""
event_filter.py — Haber/olay "karanlık penceresi" (event blackout).

AMAÇ: Planlı yüksek-etkili olaylardan hemen önce/sonra YENİ pozisyon AÇMA.
Formüle/indikatöre DOKUNMAZ. Sadece "şu an girme" der (gap stop riskini azaltır).
Açık pozisyonlara ve ÇIKIŞ sinyallerine müdahale ETMEZ.

İki kaynak:
  1. Bilanço (earnings) — yfinance takviminden, sembol bazlı (±win_days gün).
  2. Makro olaylar — events_blackout.json (kullanıcı düzenler) + TÜİK enflasyon
     (her ayın ilk iş günü, otomatik). Tüm BIST'e uygulanır.

Tahmin YOK: olayın yönünü bilmeyiz, sadece o pencerede yeni risk almayız.
"""
from __future__ import annotations
import json, os
from datetime import datetime, date, timedelta, timezone

TR = timezone(timedelta(hours=3))
_EARN_CACHE = "earnings_cache.json"
_MACRO_FILE = "events_blackout.json"   # {"dates": ["2026-06-26", ...], "note": "..."}
_CACHE_TTL_DAYS = 7


def _today_tr() -> date:
    return datetime.now(TR).date()


# ── Bilanço tarihleri (yfinance) — haftalık cache ────────────────────
def _load_earn_cache() -> dict:
    if not os.path.exists(_EARN_CACHE):
        return {}
    try:
        with open(_EARN_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_earn_cache(d: dict):
    try:
        with open(_EARN_CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def next_earnings_date(sym: str) -> date | None:
    """Sembolün bir sonraki bilanço tarihi (yfinance). Haftalık cache'li."""
    cache = _load_earn_cache()
    rec = cache.get(sym)
    today = _today_tr()
    if rec:
        try:
            fetched = date.fromisoformat(rec["fetched"])
            if (today - fetched).days < _CACHE_TTL_DAYS:
                return date.fromisoformat(rec["date"]) if rec.get("date") else None
        except Exception:
            pass
    # Taze çek
    ed = None
    try:
        import yfinance as yf
        cal = yf.Ticker(sym).calendar or {}
        raw = cal.get("Earnings Date")
        if isinstance(raw, (list, tuple)) and raw:
            raw = raw[0]
        if hasattr(raw, "date"):
            ed = raw.date()
        elif isinstance(raw, date):
            ed = raw
    except Exception:
        ed = None
    cache[sym] = {"fetched": today.isoformat(),
                  "date": ed.isoformat() if ed else None}
    _save_earn_cache(cache)
    return ed


def is_earnings_blackout(sym: str, ts: str | None = None, win_days: int = 1) -> bool:
    """Sembol bilanço gününe ±win_days içindeyse True."""
    d = (datetime.fromisoformat(ts).astimezone(TR).date() if ts else _today_tr())
    ed = next_earnings_date(sym)
    if not ed:
        return False
    return abs((ed - d).days) <= win_days


# ── Makro olaylar (BIST geneli) ──────────────────────────────────────
def _load_macro_dates() -> set[date]:
    out = set()
    # TÜİK enflasyon: her ayın ilk iş günü (Pzt-Cuma)
    today = _today_tr()
    for mo in (today.month, today.month % 12 + 1):
        yr = today.year + (1 if mo < today.month else 0)
        d = date(yr, mo, 1)
        while d.weekday() >= 5:   # hafta sonuysa ilk iş gününe kaydır
            d += timedelta(days=1)
        out.add(d)
    # Kullanıcı listesi (TCMB PPK faiz vb.) — events_blackout.json
    if os.path.exists(_MACRO_FILE):
        try:
            with open(_MACRO_FILE, encoding="utf-8") as f:
                for s in json.load(f).get("dates", []):
                    out.add(date.fromisoformat(s))
        except Exception:
            pass
    return out


def is_macro_blackout(ts: str | None = None, win_days: int = 0) -> bool:
    """BIST geneli makro olay (TÜİK enflasyon / TCMB faiz) gününde mi?"""
    d = (datetime.fromisoformat(ts).astimezone(TR).date() if ts else _today_tr())
    for md in _load_macro_dates():
        if abs((md - d).days) <= win_days:
            return True
    return False


def _last_business_day(y: int, m: int) -> date:
    import calendar
    d = date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5:      # Cmt/Paz → geri kaydır
        d -= timedelta(days=1)
    return d


def viop_expiry(ref: date | None = None) -> date:
    """Önümüzdeki VIOP vade tarihi = ayın SON İŞ GÜNÜ (tek-hisse vadeli standart).
    Bu ayın expiry'si geçtiyse gelecek ayınkini döndürür."""
    ref = ref or _today_tr()
    exp = _last_business_day(ref.year, ref.month)
    if ref > exp:                # bu ayın vadesi geçti → gelecek ay
        ny, nm = (ref.year + (1 if ref.month == 12 else 0),
                  1 if ref.month == 12 else ref.month + 1)
        exp = _last_business_day(ny, nm)
    return exp


def is_viop_near_expiry(sym: str, ts: str | None = None, biz_days: int = 5) -> bool:
    """BIST/.IS (VIOP'ta vadeli işlem) — vadeye son `biz_days` iş günü kala True.
    Koşacak yeri olmayan pozisyon açma (ay sonu zorla kapanır)."""
    if not sym.upper().endswith(".IS"):
        return False
    d = (datetime.fromisoformat(ts).astimezone(TR).date() if ts else _today_tr())
    exp = viop_expiry(d)
    # vadeye kaç İŞ günü kaldı
    biz = 0; cur = d
    while cur < exp:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            biz += 1
    return 0 <= biz <= biz_days


def is_event_blackout(sym: str, ts: str | None = None) -> tuple[bool, str]:
    """Yeni pozisyon açmamalı mıyız? (True, sebep) döner.
    BIST (.IS): bilanço + makro + VIOP vade-sonu. Diğer: sadece bilanço."""
    su = sym.upper()
    if is_earnings_blackout(sym, ts, win_days=1):
        return True, "bilanço"
    if su.endswith(".IS"):
        if is_macro_blackout(ts, win_days=0):
            return True, "makro (TÜİK/TCMB)"
        if is_viop_near_expiry(sym, ts, biz_days=5):
            return True, "VIOP vade-sonu (roll/koşacak yer yok)"
    return False, ""


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    print("Makro blackout günleri:", sorted(_load_macro_dates()))
    for t in ["GARAN.IS", "ASELS.IS", "THYAO.IS", "ARCLK.IS"]:
        ed = next_earnings_date(t)
        bo, why = is_event_blackout(t)
        print(f"  {t:10s} bilanço={ed}  blackout={bo} {why}")
