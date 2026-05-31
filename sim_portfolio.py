"""
PORTFÖY SİMÜLASYONU — son 30 günde Nasdaq + BIST hisselerinde sistem
hangi AL/SAT sinyallerini verirdi ve 1:10 kaldıraçla ne kâr/zarar ederdi?

Yöntem:
   - Her sembol için yfinance'tan son 60 gün 5-dakikalık veri çek
   - signals_full ile tam sistem çalıştır
   - Backtest motorunda kapanmış trade'leri al, son 30 güne filtrele
   - Her trade için pnl_pct × 10 (kaldıraç)
   - Sembol bazlı + portföy toplam kâr/zarar

Sermaye varsayımı: Her sembol için bağımsız 10.000$ hesap.
Toplam portföy: 30 sembol × 10K = 300K (her sembolün performansı net).
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import time
import pandas as pd
import yfinance as yf

import signals_full as sig_full
from backtest import run_backtest


# Sembol evreni
NASDAQ = ["QQQ", "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
          "AMD", "NFLX", "AVGO", "ORCL", "CSCO", "ADBE", "INTC", "PYPL"]
BIST   = ["AKBNK.IS", "ASELS.IS", "GARAN.IS", "KCHOL.IS", "THYAO.IS",
          "TUPRS.IS", "BIMAS.IS", "FROTO.IS", "SAHOL.IS", "TCELL.IS",
          "YKBNK.IS", "ARCLK.IS", "EREGL.IS", "ISCTR.IS", "SISE.IS"]

PARAMS = dict(
    trend_length=20, trend_percent=8.0, minor_percent=4.0,
    tott_percent=1.0, tott_coeff=0.0004,
    sott_period_k=300, sott_smooth_k=200, sott_percent=0.2,
    gate_length=10, gate_percent=0.4, gate_shift=0,
    rott_x1=30, rott_x2=1000, rott_percent=7.0,
)

INITIAL = 10000
LEVERAGE = 10


def fetch_5m(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="5m",
                         auto_adjust=False, progress=False, threads=False)
    except Exception:
        return pd.DataFrame()
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.lower)[["open","high","low","close"]].dropna()
    return df


def analyze(symbol, category):
    df = fetch_5m(symbol)
    if df.empty or len(df) < 2000:
        return None

    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **PARAMS)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )

    cutoff = df.index[-1] - pd.Timedelta(days=30)
    # Son 30 gün içinde kapanmış olanlar
    trades = [t for t in res.trades
              if t.exit_price is not None and t.exit_time >= cutoff]

    # Kaldıraçlı simülasyon
    eq = INITIAL
    peak = INITIAL
    max_dd = 0
    margin_call = False
    bar_pnls = []
    for t in trades:
        lev_pnl = t.pnl_pct * LEVERAGE
        if lev_pnl <= -1.0:
            margin_call = True
            eq = 0
            bar_pnls.append({"trade": t, "lev_pnl": -1.0, "eq_after": 0})
            break
        eq *= (1 + lev_pnl)
        if eq > peak: peak = eq
        dd = (eq/peak - 1)
        if dd < max_dd: max_dd = dd
        bar_pnls.append({"trade": t, "lev_pnl": lev_pnl, "eq_after": eq})

    # Açık pozisyon kontrolü (henüz kapanmamış son trade)
    open_trade = None
    for t in reversed(res.trades):
        if t.exit_price is None and t.entry_time >= cutoff:
            open_trade = t; break

    return {
        "symbol": symbol, "category": category,
        "n_trades": len(trades),
        "trades": bar_pnls,
        "final_equity": eq,
        "return_pct": (eq/INITIAL - 1) * 100,
        "max_dd": max_dd * 100,
        "margin_call": margin_call,
        "open_trade": open_trade,
    }


def main():
    print(f"\n  Veri çekiliyor — Nasdaq ({len(NASDAQ)}) + BIST ({len(BIST)})")
    print(f"  Kaldıraç: 1:{LEVERAGE}  |  Sermaye/sembol: {INITIAL:,}$  |  Süre: son 30 gün\n")

    results = []
    for sym in NASDAQ + BIST:
        category = "NASDAQ" if sym in NASDAQ else "BIST"
        print(f"  {sym:12s} ...", end=" ", flush=True)
        try:
            r = analyze(sym, category)
            if r is None:
                print("veri yok"); continue
            mc = " ✗MARGIN-CALL" if r["margin_call"] else ""
            print(f"trade={r['n_trades']:>2d}  kaldıraçlı ret={r['return_pct']:+7.2f}%{mc}")
            results.append(r)
        except Exception as e:
            print(f"hata: {e}")

    # Detay tabloları
    for cat in ["NASDAQ", "BIST"]:
        print("\n" + "═"*100)
        print(f"  {cat} — sembol bazlı sonuç (1:{LEVERAGE} kaldıraçlı, {INITIAL:,}$ başlangıç)")
        print("═"*100)
        cat_results = [r for r in results if r["category"] == cat]
        cat_results.sort(key=lambda x: -x["return_pct"])
        print(f"  {'Sembol':<12} {'Trade':>5} {'Final':>10} {'Getiri':>10} {'Max DD':>9} {'Durum'}")
        print("  " + "─"*70)
        for r in cat_results:
            mc = "MARGIN CALL ✗" if r["margin_call"] else "OK"
            print(f"  {r['symbol']:<12} {r['n_trades']:>5d} {r['final_equity']:>10,.0f} "
                  f"{r['return_pct']:+9.2f}% {r['max_dd']:8.2f}% {mc}")
        # Kategori toplam (her sembol bağımsız hesap kabulü)
        total_invested = len(cat_results) * INITIAL
        total_final = sum(r["final_equity"] for r in cat_results)
        cat_ret = (total_final / total_invested - 1) * 100 if total_invested else 0
        print("  " + "─"*70)
        print(f"  TOPLAM ({len(cat_results)} sembol, {total_invested:,}$ yatırım): "
              f"{total_final:,.0f}$  ({cat_ret:+.2f}%)")

    # Genel toplam
    print("\n" + "═"*100)
    print("  GENEL PORTFÖY ÖZETİ")
    print("═"*100)
    total_inv = len(results) * INITIAL
    total_fin = sum(r["final_equity"] for r in results)
    total_ret = (total_fin / total_inv - 1) * 100 if total_inv else 0
    margin_calls = sum(1 for r in results if r["margin_call"])
    profit_syms = sum(1 for r in results if r["return_pct"] > 0)
    loss_syms = sum(1 for r in results if r["return_pct"] <= 0)
    print(f"  Toplam yatırım : {total_inv:,}$  ({len(results)} sembol × {INITIAL:,}$)")
    print(f"  Toplam final   : {total_fin:,.0f}$")
    print(f"  Toplam getiri  : {total_ret:+.2f}%")
    print(f"  Kazanan sembol : {profit_syms}")
    print(f"  Kaybeden sembol: {loss_syms}")
    print(f"  Margin call    : {margin_calls}")

    # En karlı 5 ve en zararlı 5
    results.sort(key=lambda x: -x["return_pct"])
    print(f"\n  ★ En kazandıran 5:")
    for r in results[:5]:
        print(f"     {r['symbol']:<10} {r['category']:8s}  "
              f"{r['return_pct']:+8.2f}%  ({r['n_trades']} trade)")
    print(f"\n  ✗ En kaybettiren 5:")
    for r in results[-5:]:
        mc = " MARGIN-CALL" if r["margin_call"] else ""
        print(f"     {r['symbol']:<10} {r['category']:8s}  "
              f"{r['return_pct']:+8.2f}%  ({r['n_trades']} trade){mc}")

    # En kazandıran sembolün trade detayı
    if results:
        best = results[0]
        if best["n_trades"] > 0:
            print(f"\n  📋 En karlı sembol detayı: {best['symbol']} ({best['category']})")
            print(f"     Toplam: {best['return_pct']:+.2f}% ({best['n_trades']} trade)")
            for b in best["trades"]:
                t = b["trade"]
                gross = t.pnl_pct * 100
                lev = b["lev_pnl"] * 100
                print(f"       {t.side.upper():<5}  "
                      f"{t.entry_time.strftime('%m-%d %H:%M')} @ {t.entry_price:.2f}  →  "
                      f"{t.exit_time.strftime('%m-%d %H:%M')} @ {t.exit_price:.2f}  "
                      f"PnL: {gross:+5.2f}%  (×{LEVERAGE} = {lev:+6.2f}%)  "
                      f"Eq: {b['eq_after']:,.0f}$")

    # Tüm trade'leri CSV
    all_trades = []
    for r in results:
        for b in r["trades"]:
            t = b["trade"]
            all_trades.append({
                "symbol": r["symbol"], "category": r["category"],
                "side": t.side,
                "entry_time": t.entry_time, "entry_price": t.entry_price,
                "exit_time": t.exit_time, "exit_price": t.exit_price,
                "pnl_pct": t.pnl_pct * 100,
                "leveraged_pnl_pct": b["lev_pnl"] * 100,
            })
    pd.DataFrame(all_trades).to_csv("portfolio_trades.csv", index=False)
    print(f"\n  Tüm trade'ler CSV: portfolio_trades.csv")


if __name__ == "__main__":
    main()
