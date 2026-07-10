"""
pullback_live.py — Strong Pullback (trend-devam) sisteminin CANLI/forward takibi.

Neden cron YOK: Strong Pullback deterministik ve repaint-yok (teyitli barlarda karar).
Fiyat geçmişinden her an BİREBİR yeniden kurulur → SuperTrend gibi anlık-durum
kaydına muhtaç değil. Sekme açıldığında canlı hesaplanır (app tarafında cache'li).

Gerçek forward-test: GO_LIVE'dan (bugün) SONRA açılan işlemler "forward" sayılır;
öncekiler bağlam/backtest. Asıl güven forward satırındadır — haftalarca birikince.

Kural seti research_pullback3.py ile birebir (muhafazakâr, TP2, SL öncelikli):
  trend EMA34>EMA144+eğim & HTF EMA200 üstü → 20-bar kırılım → pullback EMA21-0.4ATR'ye
  LİMİT → yapısal stop [0.5-2.5]ATR → hedef 2R. Long-only. Sadece LİKİT semboller.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from datetime import datetime, timezone, timedelta
import numpy as np, pandas as pd

TR = timezone(timedelta(hours=3))
GO_LIVE = "2026-07-10"   # forward-test başlangıcı (bundan sonrası gerçek canlı)

# Yaşaması İÇİN sadece LİKİT isimler (edge maliyet 0.25R'de ölüyor → düşük sürtünme şart).
# Geçmiş performansa göre DEĞİL, likiditeye göre seçildi (winner cherry-pick = overfit).
PB_SYMS = [s + ".IS" for s in (
    "AKBNK GARAN ISCTR YKBNK VAKBN KCHOL SAHOL EREGL KRDMD TUPRS PETKM SASA "
    "ASELS SISE THYAO PGSUS TAVHL BIMAS TCELL FROTO TOASO ARCLK ENKAI SOKM"
).split()]

FAST, SLOW, PULL, SLOPE = 34, 144, 21, 5
BREAK_LB, MIN_WAIT, MAX_HUNT, MIN_BODY = 20, 2, 40, 0.20
ATR_LEN, DEPTH, SL_BUF, MAXR, MINR = 14, 0.40, 0.30, 2.5, 0.5
HTF_EMA, TPR = 200, 2.0
COST_R = 0.15   # net R hesabı için varsayılan maliyet (likit + limit giriş)


def _ema(x, n): return pd.Series(x).ewm(span=n, adjust=False).mean().values

def _atr(h, l, c, n=ATR_LEN):
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    a = np.full(len(c), np.nan)
    a[1:] = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values
    return a


def simulate(sym: str, period: str = "2y"):
    """Deterministik yeniden-kurulum. Döner: (closed_trades[list], open_pos|None).
       closed trade: {sym, entry_ts, exit_ts, entry, exit, stop, tp, R, result}
       open_pos:     {sym, entry_price, entry_ts, stop, tp, risk}"""
    import yfinance as yf
    d = yf.download(sym, period=period, interval="1h", progress=False, auto_adjust=True)
    if d is None or len(d) < 400:
        return [], None
    idx = d.index
    o, h, l, c = [d[x].astype(float).values.ravel() for x in ["Open", "High", "Low", "Close"]]
    n = len(c); A = _atr(h, l, c)
    ef, es, ep, eh = _ema(c, FAST), _ema(c, SLOW), _ema(c, PULL), _ema(c, HTF_EMA)
    trades = []; armed = False; armbar = 0; swing = np.nan; pos = None

    def _ts(i):
        t = idx[i]
        try: return pd.Timestamp(t).tz_localize(None).isoformat()
        except Exception: return pd.Timestamp(t).isoformat()

    for i in range(SLOW + SLOPE, n):
        if np.isnan(A[i]) or A[i] <= 0:
            continue
        if pos is not None:
            sl_hit = l[i] <= pos["stop"]; tp_hit = h[i] >= pos["tp"]
            done = None
            if sl_hit:      done = (-1.0, pos["stop"], "SL")   # aynı bar → SL öncelikli
            elif tp_hit:    done = (TPR, pos["tp"], "TP")
            if done:
                R, xpx, res = done
                trades.append({"sym": sym, "entry_ts": pos["entry_ts"], "exit_ts": _ts(i),
                               "entry": round(pos["entry_price"], 4), "exit": round(xpx, 4),
                               "stop": round(pos["stop"], 4), "tp": round(pos["tp"], 4),
                               "R": R, "result": res})
                pos = None
            if pos is not None:
                continue
        bull = ef[i] > es[i] and c[i] > es[i] and ef[i] > ef[i - SLOPE]
        hiB = np.max(h[i - BREAK_LB:i]) if i >= BREAK_LB else np.inf
        brk = bull and c[i] > hiB and c[i] > o[i] and abs(c[i] - o[i]) >= A[i] * MIN_BODY
        if brk and not armed:
            armed = True; armbar = i; swing = l[i]
        if armed:
            swing = min(swing, l[i]); age = i - armbar
            if age > MAX_HUNT or not bull:
                armed = False; continue
            limit = ep[i] - DEPTH * A[i]
            if age >= MIN_WAIT and l[i] <= limit and c[i] > eh[i]:
                ent = min(o[i], limit)
                risk = min(max(abs(ent - (swing - A[i] * SL_BUF)), A[i] * MINR), A[i] * MAXR)
                pos = {"sym": sym, "entry_price": ent, "entry_ts": _ts(i),
                       "stop": ent - risk, "tp": ent + risk * TPR, "risk": risk}
                armed = False
    return trades, pos


# ---------------- toplu (Canlı Performans → Pullback alt-sekmesi) ----------------
def all_results(period: str = "2y") -> dict:
    """Tüm likit sembolleri simüle et. Döner: {trades, open, per_sym}."""
    all_trades, open_pos, per_sym = [], {}, {}
    for sym in PB_SYMS:
        try:
            tr, op = simulate(sym, period)
        except Exception:
            continue
        all_trades += tr
        if op is not None:
            open_pos[sym] = op
        per_sym[sym.replace(".IS", "")] = [t["R"] for t in tr]
    all_trades.sort(key=lambda t: t.get("exit_ts", ""))
    return {"trades": all_trades, "open": open_pos, "per_sym": per_sym}


def _agg(trades: list) -> dict:
    """R listesinden istatistik: n, win%, ort R (net), toplam R, t-stat."""
    if not trades:
        return {"n": 0, "win": 0, "avgR": 0, "totR": 0, "t": 0}
    R = np.array([t["R"] for t in trades]); Rnet = R - COST_R
    n = len(R); t = Rnet.mean() / (Rnet.std(ddof=1) / np.sqrt(n)) if n > 1 else 0
    return {"n": n, "win": round(100 * (R > 0).mean(), 1),
            "avgR": round(Rnet.mean(), 3), "totR": round(Rnet.sum(), 1), "t": round(t, 2)}


def summary(period: str = "2y") -> dict:
    """UI için: forward (GO_LIVE sonrası) + tüm (backtest bağlamı) ayrı ayrı."""
    res = all_results(period)
    trades = res["trades"]
    fwd = [t for t in trades if t.get("entry_ts", "") >= GO_LIVE]
    return {"all": _agg(trades), "forward": _agg(fwd),
            "trades": trades, "forward_trades": fwd,
            "open": res["open"], "per_sym": res["per_sym"], "go_live": GO_LIVE}


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    s = summary()
    print(f"Semboller: {len(PB_SYMS)} likit")
    print(f"TÜM (bağlam):    {s['all']}")
    print(f"FORWARD (canlı): {s['forward']}   (başlangıç {s['go_live']})")
    print(f"Açık pozisyon:   {len(s['open'])}")
    for k, v in list(s["open"].items())[:8]:
        print(f"  {k}: giriş {v['entry_price']:.2f}  stop {v['stop']:.2f}  hedef {v['tp']:.2f}")
