"""
GÜVENLİ MOD — terste kalmamak için katı filtreler.

Bir sembolün "güvenilir" sayılması için ŞU şartları AYNI ANDA sağlamalı:
  1. backtest rating MÜKEMMEL
  2. profit factor ≥ 3.0
  3. win rate ≥ 60%
  4. trade sayısı ≥ 8
  5. (varsa multi-timeframe doğrulama — H1 yön + 5dk/15dk sinyal aynı tarafta)

Kullanım:
    from safe_mode import filter_safe, recheck_recent_form, get_safe_recommendations
"""
from __future__ import annotations
import os, json
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from data_source import fetch as ds_fetch


SAFE_CRITERIA = {
    "rating_in": ["MÜKEMMEL"],
    "min_pf": 3.0,
    "min_win_rate": 0.60,
    "min_trades": 8,
    "max_drawdown": -0.20,
    "recent_form_must_positive": True,
}


def load_params():
    if not os.path.exists("per_symbol_params.json"):
        return {}
    with open("per_symbol_params.json") as f:
        return json.load(f)


def is_safe_symbol(symbol: str, sym_data: dict, criteria: dict = None) -> tuple[bool, str]:
    """Bir sembol güvenli mi? Karar + nedeni döndürür."""
    c = criteria or SAFE_CRITERIA
    if not sym_data or not sym_data.get("ok"):
        return False, "optimize edilmemiş"
    rt = sym_data.get("rating", "?")
    if rt not in c["rating_in"]:
        return False, f"rating ({rt}) yetersiz"
    s = sym_data["stats"]
    pf = s["pf"] or 999
    if pf < c["min_pf"]:
        return False, f"PF ({pf:.2f}) < {c['min_pf']}"
    if s["win_rate"] < c["min_win_rate"]:
        return False, f"win rate ({s['win_rate']*100:.0f}%) < {c['min_win_rate']*100:.0f}%"
    if s["n_trades"] < c["min_trades"]:
        return False, f"az trade ({s['n_trades']}) < {c['min_trades']}"
    if s["max_dd"] < c["max_drawdown"]:
        return False, f"DD ({s['max_dd']*100:.1f}%) çok kötü"
    return True, "GEÇTİ"


def recheck_recent_form(symbol: str, params: dict, days: int = 7,
                         interval: str = "1h") -> dict:
    """Son N gün backtest çalıştır — pozitif mi kontrol et."""
    df = ds_fetch(symbol, interval=interval, n_bars=2000)
    if df.empty or len(df) < 500:
        return {"ok": False, "reason": "veri az"}
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(df[["open","high","low","close"]],
                       s["cond_buy_long"], s["cond_exit_long"],
                       s["cond_buy_short"], s["cond_exit_short"])
    cutoff = df.index[-1] - pd.Timedelta(days=days)
    eq = res.equity[res.equity.index >= cutoff]
    if len(eq) < 2:
        return {"ok": False, "reason": "dilim az"}
    ret = (eq.iloc[-1] / eq.iloc[0]) - 1
    return {"ok": True, "return": ret, "positive": ret > 0}


def get_current_signal(symbol: str, params: dict, interval: str = "1h") -> dict:
    """Şu anki sembolün durumu."""
    df = ds_fetch(symbol, interval=interval, n_bars=2000)
    if df.empty or len(df) < 500:
        return {"ok": False}
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    last = s.iloc[-1]
    cur = float(df["close"].iloc[-1])

    if last["cond_buy_long"]:        sig = "LONG_AÇ"
    elif last["cond_buy_short"]:     sig = "SHORT_AÇ"
    elif last["cond_exit_long"]:     sig = "LONG_ÇIK"
    elif last["cond_exit_short"]:    sig = "SHORT_ÇIK"
    elif last["major_up"] and last["zone_up"]:  sig = "LONG_TUT"
    elif last["major_dn"] and last["zone_dn"]:  sig = "SHORT_TUT"
    elif last["major_up"]:           sig = "LONG_BEKLE"
    elif last["major_dn"]:           sig = "SHORT_BEKLE"
    else:                            sig = "BELİRSİZ"

    return {
        "ok": True, "signal": sig,
        "price": cur,
        "major_up": bool(last["major_up"]),
        "major_dn": bool(last["major_dn"]),
        "zone_up": bool(last["zone_up"]),
        "zone_dn": bool(last["zone_dn"]),
        "stop_long": float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None,
        "stop_short": float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None,
    }


def mtf_confirm(symbol: str, params: dict) -> dict:
    """
    Multi-Timeframe onayı:
      - H1 yön (yukarı / aşağı)
      - 15dk YENİ sinyal aynı yönde olmalı
    İkisi aynı yöndeyse 'güçlü onay', değilse 'yok'.
    """
    h1 = get_current_signal(symbol, params, interval="1h")
    m15 = get_current_signal(symbol, params, interval="15m")
    if not h1.get("ok") or not m15.get("ok"):
        return {"confirmed": False, "reason": "veri yok"}

    if h1["major_up"] and m15["signal"] == "LONG_AÇ":
        return {"confirmed": True, "direction": "LONG", "reason": "H1 yukarı + 15dk LONG AÇ"}
    if h1["major_dn"] and m15["signal"] == "SHORT_AÇ":
        return {"confirmed": True, "direction": "SHORT", "reason": "H1 aşağı + 15dk SHORT AÇ"}
    if h1["major_up"] and h1["signal"] == "LONG_AÇ":
        return {"confirmed": True, "direction": "LONG", "reason": "H1'de yeni LONG sinyali (kendi onayı)"}
    if h1["major_dn"] and h1["signal"] == "SHORT_AÇ":
        return {"confirmed": True, "direction": "SHORT", "reason": "H1'de yeni SHORT sinyali (kendi onayı)"}

    return {"confirmed": False, "reason": f"H1={'↑' if h1['major_up'] else '↓' if h1['major_dn'] else '-'} 15dk_sinyal={m15['signal']}"}


def get_safe_recommendations(criteria: dict = None) -> list[dict]:
    """
    Güvenli sembolleri çıkar — backtest filtre + multi-timeframe onay.
    Sadece "şimdi aksiyon alınabilir" sembolleri döndürür.
    """
    psy = load_params()
    out = []
    for sym, sym_data in psy.items():
        ok, reason = is_safe_symbol(sym, sym_data, criteria)
        if not ok:
            continue
        params = sym_data["params"]
        # MTF onay
        mtf = mtf_confirm(sym, params)
        if not mtf.get("confirmed"):
            continue
        # Recent form
        rf = recheck_recent_form(sym, params, days=7)
        if rf.get("ok") and not rf.get("positive", True):
            continue
        # Anlık durum
        cur = get_current_signal(sym, params, interval="1h")
        out.append({
            "Sembol": sym,
            "Yön": mtf["direction"],
            "Onay": mtf["reason"],
            "Fiyat": cur.get("price"),
            "Stop": cur.get("stop_long" if mtf["direction"]=="LONG" else "stop_short"),
            "BT Getiri %": sym_data["stats"]["return"] * 100,
            "BT PF": sym_data["stats"]["pf"],
            "BT Win %": sym_data["stats"]["win_rate"] * 100,
            "BT Trade": sym_data["stats"]["n_trades"],
            "Recent 7g": rf.get("return", 0) * 100 if rf.get("ok") else None,
        })
    return out


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    recs = get_safe_recommendations()
    print(f"\n🛡️ GÜVENLİ MOD — {len(recs)} sembol uygun\n")
    for r in recs:
        print(f"  {r['Sembol']:<10} {r['Yön']:<6} fiyat={r['Fiyat']:.4f}  "
              f"stop={r['Stop']:.4f if r['Stop'] else 0}  "
              f"BT={r['BT Getiri %']:+.1f}% PF={r['BT PF']:.2f}  "
              f"win={r['BT Win %']:.0f}%  ({r['Onay']})")
