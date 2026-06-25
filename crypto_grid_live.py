"""
crypto_grid_live.py — Crypto GRID canlı takibi (kanıtlanmış: WF 10/10, MC kaybetme %0).

BIST/long-only'den AYRI dosyalar. 7/24 (seans kontrolü yok). Grid mantığı:
  - Yatay (ER<0.30): fiyat AL seviyesine (-2/-4/-6%) inince birim al;
    +%1.5'te TRAILING aktif, peak'in %0.5 altına inince sat (kazananı koştur).
  - Trend (ER≥0.30): açık birimleri kapat.
Her coin'de birden çok birim olabilir (3 seviye).

Dosyalar:
  cg_positions.json — açık grid birimleri {coin: {level_idx: {e:entry, a:active, p:peak}}}
  cg_trades.json    — kapanmış birim trade'leri [{coin, entry, exit, pnl_pct, ...}]
"""
from __future__ import annotations
import json, os, re
from datetime import datetime, timezone, timedelta

TR = timezone(timedelta(hours=3))
POS_FILE = "cg_positions.json"
TRADES_FILE = "cg_trades.json"
LEVELS = [-0.02, -0.04, -0.06]   # merkez (SMA20) altı AL seviyeleri
TAKE = 0.015                     # +%1.5'te TRAILING aktifleş (satmaz, kayan stop başlar)
TRAIL = 0.005                    # peak'in %0.5 altına inince sat (kazananı koştur)
COST = 0.0005                    # yön başı


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


def _coins():
    try:
        txt = open("app.py", encoding="utf-8").read()
        m = re.search(r'^CRYPTO = \[(.*?)\]', txt, re.S | re.M)
        return re.findall(r'"([^"]+)"', m.group(1))
    except Exception:
        return []


def _stats_list(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0, "pf": 0, "avg": 0, "total": 0}
    wins = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    gw = sum(wins); gl = abs(sum(losses))
    pf = (gw / gl) if gl > 0 else (999 if gw > 0 else 0)
    return {"n": n, "win_rate": round(100 * len(wins) / n, 1), "pf": round(pf, 2),
            "avg": round(sum(t["pnl_pct"] for t in trades) / n, 2),
            "total": round(sum(t["pnl_pct"] for t in trades), 1)}


def overall_stats() -> dict:
    return _stats_list(_load(TRADES_FILE, []))


def per_coin_stats() -> dict:
    trades = _load(TRADES_FILE, [])
    out = {}
    for c in set(t["coin"] for t in trades):
        out[c] = _stats_list([t for t in trades if t["coin"] == c])
    return out


def open_units() -> dict:
    return _load(POS_FILE, {})


def get_trades(last_n: int = 50) -> list:
    return sorted(_load(TRADES_FILE, []), key=lambda t: t.get("exit_ts", ""), reverse=True)[:last_n]


def scan_and_record(on_open=None, on_close=None) -> dict:
    """Tüm coinleri 4h grid ile tara, birim al/sat kaydet. 7/24."""
    import grid_strategy as g
    from data_source import fetch as ds_fetch
    coins = _coins()
    positions = _load(POS_FILE, {})
    trades = _load(TRADES_FILE, [])
    ts = datetime.now(TR).isoformat()
    opened = closed = scanned = 0

    def _close(coin, k, entry, exit_price, reason):
        nonlocal closed
        pnl = (exit_price / entry - 1) - 2 * COST   # trailing/trend: market çıkış
        trades.append({"coin": coin, "level": k, "entry_price": entry,
                       "exit_price": round(exit_price, 6), "pnl_pct": round(pnl * 100, 3),
                       "exit_ts": ts, "reason": reason})
        closed += 1
        if on_close:
            try: on_close(coin, round(pnl * 100, 2), reason)
            except Exception: pass

    for sym in coins:
        try:
            d = ds_fetch(sym, interval="4h", n_bars=600)
            stt = g.current_state(d)
            if not stt:
                continue
            scanned += 1
            coin = sym.replace("-USD", "")
            price = stt["anlik"]
            held = positions.get(coin, {})
            if stt["yatay"]:
                # 1) TRAILING: +%1.5'te aktifleş, peak'in %0.5 altına inince sat
                for k in list(held.keys()):
                    u = held[k]
                    if not u.get("a") and price >= u["e"] * (1 + TAKE):
                        u["a"] = True; u["p"] = price           # trailing aktif
                    if u.get("a"):
                        u["p"] = max(u["p"], price)
                        if price <= u["p"] * (1 - TRAIL):
                            _close(coin, k, u["e"], price, "trail")
                            del held[k]
                # 2) al: fiyat seviyeye indi + o seviye boş
                for k, lv in enumerate(stt["seviyeler"]):
                    if str(k) not in held and price <= lv:
                        held[str(k)] = {"e": price, "a": False, "p": price}; opened += 1
                        if on_open:
                            try: on_open(coin, k + 1, price)
                            except Exception: pass
            else:
                # trend → açık birimleri kapat
                for k in list(held.keys()):
                    _close(coin, k, held[k]["e"], price, "trend")
                    del held[k]
            if held:
                positions[coin] = held
            elif coin in positions:
                del positions[coin]
        except Exception:
            continue

    _save(POS_FILE, positions)
    _save(TRADES_FILE, trades)
    return {"scanned": scanned, "opened": opened, "closed": closed,
            "open_units": sum(len(v) for v in positions.values())}


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    print(scan_and_record())
