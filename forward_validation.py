"""
Forward-validation — CANLI performans takibi.

In-sample backtest rating'i (MÜKEMMEL vs) yanıltıcı olabilir (overfitting).
Bu modül botun GERÇEK ZAMANLI sinyallerini kaydeder, trade'leri yeniden kurar,
her sembolün CANLI PF/win rate'ini hesaplar.

Mantık (basit pozisyon durum makinesi):
  Gözlem: (sembol, durum, fiyat, zaman)   durum ∈ {LONG, SHORT, FLAT}
  FLAT → LONG  : long aç (giriş kaydet)
  LONG → FLAT  : long kapat → trade kaydet (pnl)
  LONG → SHORT : long kapat + short aç (flip)
  ...

Dosyalar:
  live_positions.json — açık pozisyonlar {sym: {side, entry_price, entry_ts}}
  live_trades.json    — kapanmış trade'ler [{sym, side, entry, exit, pnl_pct, ...}]

NOT: Taramalar günde birkaç kez olduğu için bu, gerçek trade dizisinin
ÖRNEKLENMİŞ yaklaşımıdır. İki tarama arasında açılıp kapanan trade kaçabilir.
Yine de in-sample rating'den çok daha gerçekçi bir canlı gösterge verir.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta

TR = timezone(timedelta(hours=3))
POS_FILE = "live_positions.json"
TRADES_FILE = "live_trades.json"


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


def is_session_open(sym: str, ts: str = None) -> bool:
    """Sembolün borsası açık mı? (profesyonel trader sadece seansta işlem açar)
    BIST (.IS): hafta içi 09:30-18:10 TR. NASDAQ/US: hafta içi 16:30-23:00 TR."""
    dt = datetime.fromisoformat(ts) if ts else datetime.now(TR)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TR)
    dt = dt.astimezone(TR)
    if dt.weekday() >= 5:   # Cumartesi/Pazar kapalı
        return False
    hm = dt.hour * 60 + dt.minute
    su = sym.upper()
    if su.endswith(".IS"):                     # BIST
        return 9 * 60 + 30 <= hm <= 18 * 60 + 10
    if su.endswith("-USD"):                    # crypto 7/24
        return True
    if su.endswith("=F") or su.endswith("=X"): # emtia (metal) + forex → hafta içi ~24h
        return True
    return 16 * 60 + 30 <= hm <= 23 * 60      # NASDAQ/US (TR saati)


def signal_direction(signal: str) -> str:
    """Sinyalin yön durumu: LONG / SHORT / FLAT."""
    if not signal:
        return "FLAT"
    if "ÇIK" in signal:
        return "FLAT"
    if "LONG" in signal and ("AÇ" in signal or "TUT" in signal):
        return "LONG"
    if "SHORT" in signal and ("AÇ" in signal or "TUT" in signal):
        return "SHORT"
    return "FLAT"   # BEKLE / belirsiz


def is_fresh_entry(signal: str) -> str | None:
    """TAZE giriş sinyali mi? 'LONG'/'SHORT' döner, değilse None.
    Profesyonel kural: sadece AÇ'ta gir, TUT'ta GİRME (geç trende atlama)."""
    if not signal:
        return None
    if "LONG" in signal and "AÇ" in signal:
        return "LONG"
    if "SHORT" in signal and "AÇ" in signal:
        return "SHORT"
    return None


def record_observation(sym: str, signal: str, price: float, ts: str = None,
                        stop: float = None, on_open=None, block_open=False):
    """Profesyonel trader durum makinesi.
      - Açık pozisyon YOKKEN: sadece TAZE AÇ sinyalinde gir (TUT'ta girme)
      - Açık pozisyon VARKEN: yön ters dönerse/FLAT olursa kapat
      - Seans kapalıysa hiç işlem yapma (BIST 09:30-18:10)
    on_open: yeni pozisyon açılınca çağrılacak callback (Telegram için).
    block_open: True ise YENİ pozisyon AÇMAZ (haber/olay karanlığı). Çıkış/trail
                yine işler — sadece yeni giriş engellenir."""
    if not signal or not price or price <= 0:
        return
    ts = ts or datetime.now(TR).isoformat()
    if not is_session_open(sym, ts):
        return  # seans kapalı → işlem yok (gece raporu pozisyon açmaz)

    direction = signal_direction(signal)   # LONG/SHORT/FLAT
    fresh = is_fresh_entry(signal)         # LONG/SHORT/None (taze AÇ)

    positions = _load(POS_FILE, {})
    trades = _load(TRADES_FILE, [])
    cur = positions.get(sym)

    def _close(side, ep, ets):
        pnl = (price - ep) / ep if side == "LONG" else (ep - price) / ep
        trades.append({
            "sym": sym, "side": side,
            "entry_price": ep, "exit_price": price,
            "entry_ts": ets, "exit_ts": ts,
            "pnl_pct": round(pnl * 100, 3),
        })

    def _open(side):
        positions[sym] = {"side": side, "entry_price": price,
                          "entry_ts": ts, "stop": stop}
        if on_open:
            try: on_open(sym, side, price, stop)
            except Exception: pass

    if cur is None:
        # Açık yok → SADECE taze AÇ'ta gir (blackout'ta açma)
        if fresh and not block_open:
            _open(fresh)
    else:
        side = cur["side"]
        if direction == side:
            # Aynı yön → tut, stop'u güncelle (trail)
            if stop is not None:
                positions[sym]["stop"] = stop
        elif direction == "FLAT":
            # ÇIK veya bekle → kapat (blackout çıkışı engellemez)
            _close(side, cur["entry_price"], cur["entry_ts"])
            del positions[sym]
        else:
            # Ters yön → kapat; taze AÇ ise yeni pozisyon aç (flip, blackout'ta açma)
            _close(side, cur["entry_price"], cur["entry_ts"])
            del positions[sym]
            if fresh and not block_open:
                _open(fresh)

    _save(POS_FILE, positions)
    _save(TRADES_FILE, trades)


def live_stats(sym: str, last_n: int = 30) -> dict:
    """Bir sembolün CANLI son N trade istatistiği."""
    trades = _load(TRADES_FILE, [])
    sym_trades = [t for t in trades if t["sym"] == sym]
    sym_trades = sorted(sym_trades, key=lambda t: t.get("exit_ts", ""))[-last_n:]
    n = len(sym_trades)
    if n == 0:
        return {"n": 0, "win_rate": 0, "pf": 0, "avg": 0, "total": 0}
    wins = [t["pnl_pct"] for t in sym_trades if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in sym_trades if t["pnl_pct"] <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999 if gross_win > 0 else 0)
    return {
        "n": n,
        "win_rate": round(100 * len(wins) / n, 1),
        "pf": round(pf, 2),
        "avg": round(sum(t["pnl_pct"] for t in sym_trades) / n, 2),
        "total": round(sum(t["pnl_pct"] for t in sym_trades), 1),
    }


def all_live_stats(last_n: int = 30) -> dict:
    """Tüm semboller için canlı istatistik {sym: stats}."""
    trades = _load(TRADES_FILE, [])
    syms = set(t["sym"] for t in trades)
    return {s: live_stats(s, last_n) for s in syms}


def open_positions() -> dict:
    """Şu an açık (takip edilen) pozisyonlar."""
    return _load(POS_FILE, {})


def get_trades(sym: str = None) -> list:
    """Kapanmış trade'leri döndür. sym verilirse sadece o sembol.
    En yeni kapanış üstte."""
    trades = _load(TRADES_FILE, [])
    if sym:
        trades = [t for t in trades if t["sym"] == sym]
    return sorted(trades, key=lambda t: t.get("exit_ts", ""), reverse=True)


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    stats = all_live_stats()
    print(f"Canlı takip edilen sembol: {len(stats)}")
    print(f"Açık pozisyon: {len(open_positions())}")
    print(f"\n{'Sembol':12s} {'N':>3} {'Win%':>6} {'PF':>6} {'Toplam%':>8}")
    print("-" * 40)
    for sym, s in sorted(stats.items(), key=lambda x: -x[1]["pf"]):
        if s["n"] > 0:
            print(f"{sym:12s} {s['n']:>3} {s['win_rate']:>6} {s['pf']:>6} {s['total']:>8}")
