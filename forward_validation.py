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


def signal_to_state(signal: str) -> str | None:
    """Sinyal etiketinden pozisyon durumu çıkar.
    LONG AÇ/TUT → LONG, SHORT AÇ/TUT → SHORT, ÇIK → FLAT, diğer → None (gözlem yok)."""
    if not signal:
        return None
    if "ÇIK" in signal:
        return "FLAT"
    if "LONG" in signal and ("AÇ" in signal or "TUT" in signal):
        return "LONG"
    if "SHORT" in signal and ("AÇ" in signal or "TUT" in signal):
        return "SHORT"
    return None


def record_observation(sym: str, state: str | None, price: float, ts: str = None):
    """Bir sembolün anlık durumunu işle, durum makinesini güncelle.
    state: 'LONG' / 'SHORT' / 'FLAT' / None (None → gözlem atlanır)."""
    if state is None or not price or price <= 0:
        return
    ts = ts or datetime.now(TR).isoformat()

    positions = _load(POS_FILE, {})
    trades = _load(TRADES_FILE, [])

    cur = positions.get(sym)  # {side, entry_price, entry_ts} veya None

    def _close(side, entry_price, entry_ts):
        if side == "LONG":
            pnl = (price - entry_price) / entry_price
        else:  # SHORT
            pnl = (entry_price - price) / entry_price
        trades.append({
            "sym": sym, "side": side,
            "entry_price": entry_price, "exit_price": price,
            "entry_ts": entry_ts, "exit_ts": ts,
            "pnl_pct": round(pnl * 100, 3),
        })

    if cur is None:
        # Açık pozisyon yok
        if state in ("LONG", "SHORT"):
            positions[sym] = {"side": state, "entry_price": price, "entry_ts": ts}
    else:
        side = cur["side"]
        if state == side:
            pass  # aynı yön → tut, değişiklik yok
        elif state == "FLAT":
            _close(side, cur["entry_price"], cur["entry_ts"])
            del positions[sym]
        else:
            # Ters yön → flip (kapat + yeni aç)
            _close(side, cur["entry_price"], cur["entry_ts"])
            positions[sym] = {"side": state, "entry_price": price, "entry_ts": ts}

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
