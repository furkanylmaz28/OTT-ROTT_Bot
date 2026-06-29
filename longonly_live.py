"""
longonly_live.py — KANITLANMIŞ sistemin (SuperTrend 10/3 long-only) CANLI takibi.

forward_validation.py (OTT sistemi) ile AYRI dosyalar kullanır — geçmiş karışmaz.
Mantık: SuperTrend yukarı + pozisyon yok → AÇ (long). SuperTrend aşağı + long → KAPAT (nakit).
Short YOK. Max 3 eş zamanlı pozisyon. Sadece BIST seansında işlem.

Dosyalar:
  lo_positions.json — açık pozisyonlar {sym: {entry_price, entry_ts, stop}}
  lo_trades.json    — kapanmış trade'ler [{sym, entry, exit, pnl_pct, ...}]
"""
from __future__ import annotations
import json, os, re
from datetime import datetime, timezone, timedelta

TR = timezone(timedelta(hours=3))
POS_FILE = "lo_positions.json"
TRADES_FILE = "lo_trades.json"
BREADTH_FILE = "lo_breadth.json"
try:
    import risk
    MAX_OPEN = risk.MAX_POSITIONS   # tek kaynak (risk.py = 6)
except Exception:
    MAX_OPEN = 6

# SADECE walk-forward'ı (H1, 10/3, %0.05 maliyet) GEÇEN 34 sembol işlenir.
# Geçemeyen 11 (ARCLK,BIMAS,GARAN,OYAKC,SAHOL,TCELL,TSKB,VESTL,DOAS,CIMSA,ULKER)
# OOS'ta para kaybettirdi → trade edilmez (Davey: sadece doğrulanmışı trade et).
VALIDATED = [s + ".IS" for s in (
    "AKBNK ASELS DOHOL ENJSA EKGYO ENKAI EREGL FROTO GUBRF HALKB ISCTR KCHOL "
    "KRDMD MGROS PETKM PGSUS SASA SISE SOKM TAVHL THYAO TOASO TKFEN TTKOM TUPRS "
    "VAKBN YKBNK AEFES HEKTS ODAS ASTOR AKSEN ALARK KONTR"
).split()]

# #6 KORELASYON/SEKTÖR KAPISI: aynı sektörden max 1 pozisyon (banka kümesi gibi
# korelasyonlu çöküşü önler). MTM testi: floating drawdown -35.6% → -30.2%, getiri bedeli yok.
SECTOR = {"AKBNK":"banka","HALKB":"banka","ISCTR":"banka","VAKBN":"banka","YKBNK":"banka",
 "KCHOL":"holding","ALARK":"holding","ENKAI":"holding","DOHOL":"holding",
 "ASELS":"savunma","ASTOR":"savunma","KONTR":"savunma","EREGL":"celik","KRDMD":"celik",
 "PETKM":"kimya","SASA":"kimya","GUBRF":"kimya","HEKTS":"kimya",
 "TUPRS":"enerji","ENJSA":"enerji","ODAS":"enerji","AKSEN":"enerji",
 "THYAO":"ulasim","PGSUS":"ulasim","TAVHL":"ulasim","FROTO":"oto","TOASO":"oto",
 "MGROS":"perakende","SOKM":"perakende","AEFES":"perakende",
 "TTKOM":"telekom","SISE":"cam","TKFEN":"insaat","EKGYO":"gyo"}

def _sector(sym):
    return SECTOR.get(sym.replace(".IS", ""), sym)


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def is_session_open(ts: datetime = None) -> bool:
    """BIST seansı açık mı? Hafta içi 09:30-18:10 TR."""
    dt = ts or datetime.now(TR)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TR)
    dt = dt.astimezone(TR)
    if dt.weekday() >= 5:
        return False
    mins = dt.hour * 60 + dt.minute
    return 9 * 60 + 30 <= mins <= 18 * 60 + 10


def record(sym: str, state: str, price: float, stop: float = None,
           ts: str = None, on_open=None, on_close=None, fresh: bool = True):
    """Durum makinesi. state ∈ {LONG, FLAT}. fresh=TAZE dönüş mü (geç trene binme).
       pozisyon yok + LONG + slot var → AÇ
       pozisyon var + FLAT           → KAPAT (nakit)
       pozisyon var + LONG           → tut, stop güncelle"""
    if not price or price <= 0:
        return
    ts = ts or datetime.now(TR).isoformat()
    if not is_session_open(datetime.fromisoformat(ts)):
        return

    positions = _load(POS_FILE, {})
    trades = _load(TRADES_FILE, [])
    cur = positions.get(sym)

    if cur is None:
        # SADECE taze dönüşte gir — olgun trende geç binme (MT5 EA ile tutarlı)
        # + #6: aynı sektörden açık pozisyon varsa GİRME (korelasyon riski)
        same_sector = any(_sector(k) == _sector(sym) for k in positions)
        if state == "LONG" and fresh and len(positions) < MAX_OPEN and not same_sector:
            positions[sym] = {"entry_price": price, "entry_ts": ts, "stop": stop}
            if on_open:
                try: on_open(sym, price, stop)
                except Exception: pass
    else:
        if state == "FLAT":
            pnl = (price - cur["entry_price"]) / cur["entry_price"]
            trades.append({
                "sym": sym, "side": "LONG",
                "entry_price": cur["entry_price"], "exit_price": price,
                "entry_ts": cur["entry_ts"], "exit_ts": ts,
                "pnl_pct": round(pnl * 100, 3),
            })
            del positions[sym]
            if on_close:
                try: on_close(sym, cur["entry_price"], price, round(pnl * 100, 2))
                except Exception: pass
        elif stop is not None:
            positions[sym]["stop"] = stop

    _save(POS_FILE, positions)
    _save(TRADES_FILE, trades)


# ---------------- istatistik (Canlı Performans tabı için) ----------------
def live_stats(sym: str, last_n: int = 30) -> dict:
    trades = _load(TRADES_FILE, [])
    st = sorted([t for t in trades if t["sym"] == sym], key=lambda t: t.get("exit_ts", ""))[-last_n:]
    n = len(st)
    if n == 0:
        return {"n": 0, "win_rate": 0, "pf": 0, "avg": 0, "total": 0}
    wins = [t["pnl_pct"] for t in st if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in st if t["pnl_pct"] <= 0]
    gw = sum(wins); gl = abs(sum(losses))
    pf = (gw / gl) if gl > 0 else (999 if gw > 0 else 0)
    return {"n": n, "win_rate": round(100 * len(wins) / n, 1), "pf": round(pf, 2),
            "avg": round(sum(t["pnl_pct"] for t in st) / n, 2),
            "total": round(sum(t["pnl_pct"] for t in st), 1)}


def all_live_stats(last_n: int = 30) -> dict:
    trades = _load(TRADES_FILE, [])
    return {s: live_stats(s, last_n) for s in set(t["sym"] for t in trades)}


def open_positions() -> dict:
    return _load(POS_FILE, {})


def get_trades(sym: str = None) -> list:
    trades = _load(TRADES_FILE, [])
    if sym:
        trades = [t for t in trades if t["sym"] == sym]
    return sorted(trades, key=lambda t: t.get("exit_ts", ""), reverse=True)


# ---------------- tarama (cron'dan çağrılır) ----------------
def _bist_symbols():
    try:
        txt = open("app.py", encoding="utf-8").read()
        m = re.search(r'^BIST = \[(.*?)\]', txt, re.S | re.M)
        return re.findall(r'"([^"]+)"', m.group(1))
    except Exception:
        return []


def scan_and_record(symbols=None, on_open=None, on_close=None) -> dict:
    """Tüm BIST sembollerini SuperTrend 10/3 ile tara, durumu kaydet.
       Döner: {açılan, kapanan, taranan} özeti."""
    if not is_session_open():
        return {"skipped": "seans kapalı"}
    import longonly_strategy as lo
    from data_source import fetch_futures
    syms = symbols or VALIDATED   # sadece WF'yi geçen 34 sembol
    before_open = len(open_positions())
    before_trades = len(_load(TRADES_FILE, []))
    scanned = 0
    bull = []; bear = []; fresh_bear = []   # piyasa genişliği
    for sym in syms:
        try:
            d = fetch_futures(sym, "1h", 1500)
            stt = lo.current_state(d)
            if not stt:
                continue
            scanned += 1
            nm = sym.replace(".IS", "")
            if stt["pozisyon"] == "LONG":
                bull.append(nm)
            else:
                bear.append(nm)
                if stt.get("bars", 99) <= 9:   # son ~1 günde bearish'e döndü
                    fresh_bear.append(nm)
            state = "LONG" if stt["pozisyon"] == "LONG" else "FLAT"
            # taze = SuperTrend son ~2 barda LONG'a döndü (olgun trende geç binme)
            fresh = stt.get("bars", 99) <= 2
            record(sym, state, stt["anlik"], stop=stt.get("cizgi"),
                   on_open=on_open, on_close=on_close, fresh=fresh)
        except Exception:
            continue
    tot = len(bull) + len(bear)
    if tot > 0:
        _save(BREADTH_FILE, {
            "ts": datetime.now(TR).isoformat(),
            "bull": len(bull), "bear": len(bear), "total": tot,
            "bull_pct": round(100 * len(bull) / tot, 0),
            "bull_syms": bull, "bear_syms": bear, "fresh_bear": fresh_bear,
        })
    return {"scanned": scanned,
            "opened": len(open_positions()) - before_open,
            "closed": len(_load(TRADES_FILE, [])) - before_trades,
            "bull_pct": round(100 * len(bull) / tot, 0) if tot else None}


def market_breadth() -> dict:
    """Son taramanın piyasa genişliği (Canlı Performans/Kanıtlanmış Sistem tabı)."""
    return _load(BREADTH_FILE, {})


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    print(scan_and_record())
