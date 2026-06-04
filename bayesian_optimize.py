"""
Bayesian parametre arama — optuna ile.

Grid search'ten farkı:
- TPE (Tree Parzen Estimator) ile akıllı arama
- "İyi bölgeleri" yoğun, kötü bölgeleri seyrek dener
- Continuous parametreler (sadece discrete değil)
- Daha geniş arama uzayı
- Erken durdurma (pruning) ile kötü trial'lar atlanır

Tahmini süre: 200 trial × 151 sembol × ~0.15s = ~75 dakika
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import os
import json
import time
import optuna
import numpy as np
import pandas as pd

import signals_full as sig_full
from backtest import run_backtest
from data_source import fetch as ds_fetch, best_interval_for, category_of
from per_symbol_optimize import BIST30, NASDAQ100, CRYPTO30, rating

# Optuna log seviyesini azalt (her trial'ı yazdırmasın)
optuna.logging.set_verbosity(optuna.logging.WARNING)

N_TRIALS = 200       # Sembol başına trial sayısı
TIMEOUT = 180        # Sembol başına max saniye (yine de cap)
MIN_BARS = 1500
MIN_TRADES = 5


def fetch(symbol):
    interval = best_interval_for(symbol)
    df = ds_fetch(symbol, interval=interval, n_bars=5000)
    if df.empty: return df
    keep = [c for c in ["open","high","low","close"] if c in df.columns]
    return df[keep].dropna()


def evaluate(df, params):
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    return res.stats


def objective(trial, df):
    """
    Optuna trial — parametre öner, backtest, skor döndür.
    Skor = return × win_rate^1.5 × log(PF+1) / sqrt(1+|DD|)
       (yüksek win rate ve PF'yi ödüllendirir)
    """
    # Geniş parametre uzayı
    p = dict(
        trend_length=trial.suggest_int("trend_length", 10, 35),
        trend_percent=trial.suggest_float("trend_percent", 3.0, 12.0, step=0.5),
        minor_percent=trial.suggest_float("minor_percent", 2.0, 6.0, step=0.5),
        tott_percent=trial.suggest_float("tott_percent", 0.3, 1.5, step=0.1),
        tott_coeff=trial.suggest_float("tott_coeff", 0.0002, 0.002, log=True),
        sott_period_k=trial.suggest_int("sott_period_k", 50, 600, step=50),
        sott_smooth_k=trial.suggest_int("sott_smooth_k", 50, 300, step=50),
        sott_percent=trial.suggest_float("sott_percent", 0.1, 0.6, step=0.1),
        gate_length=trial.suggest_int("gate_length", 8, 32, step=2),
        gate_percent=trial.suggest_float("gate_percent", 0.3, 0.8, step=0.1),
        gate_shift=trial.suggest_categorical("gate_shift", [0, 2]),
        rott_x1=trial.suggest_int("rott_x1", 20, 50, step=5),
        rott_x2=trial.suggest_int("rott_x2", 200, 1500, step=100),
        rott_percent=trial.suggest_float("rott_percent", 4.0, 10.0, step=0.5),
    )

    try:
        st = evaluate(df, p)
    except Exception:
        return -1e9

    n = st["n_trades"]
    if n < MIN_TRADES:
        # Düşük trade sayısına ceza
        return -100 + n  # Optuna minimize/maximize için sıralanabilir

    ret = st["total_return"]
    pf = st["profit_factor"] if np.isfinite(st["profit_factor"]) else 10.0
    pf = min(pf, 10.0)  # cap
    win = st["win_rate"]
    dd = abs(st["max_drawdown"])

    # Çok katmanlı skor — win rate ve PF'yi ödüllendir
    if ret <= 0:
        return ret  # negatif sıralanır
    score = ret * (win ** 1.5) * np.log(pf + 1) / np.sqrt(1 + dd)
    return score


def optimize_symbol(symbol, n_trials=N_TRIALS, timeout=TIMEOUT):
    df = fetch(symbol)
    if df.empty or len(df) < MIN_BARS:
        return None

    sampler = optuna.samplers.TPESampler(seed=42, n_startup_trials=20)
    study = optuna.create_study(direction="maximize", sampler=sampler,
                                  pruner=optuna.pruners.MedianPruner(n_warmup_steps=30))
    study.optimize(lambda t: objective(t, df),
                    n_trials=n_trials, timeout=timeout, show_progress_bar=False,
                    catch=(Exception,))

    if not study.best_trial or study.best_value < 0:
        return {"symbol": symbol, "ok": False, "reason": "kötü skor"}

    best_params = study.best_params
    # Categorical değerler için cast
    if "gate_shift" in best_params:
        best_params["gate_shift"] = int(best_params["gate_shift"])

    final_stats = evaluate(df, best_params)
    return {
        "symbol": symbol, "ok": True, "bars": len(df),
        "rating": rating(final_stats),
        "interval": best_interval_for(symbol),
        "category": category_of(symbol),
        "params": best_params,
        "n_trials": len(study.trials),
        "best_score": study.best_value,
        "stats": {
            "return": final_stats["total_return"],
            "pf": final_stats["profit_factor"] if np.isfinite(final_stats["profit_factor"]) else None,
            "sharpe": final_stats["sharpe"],
            "max_dd": final_stats["max_drawdown"],
            "n_trades": final_stats["n_trades"],
            "win_rate": final_stats["win_rate"],
        },
    }


OUTPUT_FILE = "per_symbol_params_bayes.json"
COMPARE_AGAINST = "per_symbol_params.json"


def main():
    # Mevcut grid search sonuçlarını referans olarak yükle (karşılaştırma için)
    try:
        with open(COMPARE_AGAINST) as f:
            grid_results = json.load(f)
    except FileNotFoundError:
        grid_results = {}

    # Bayesian sonuçlarını ayrı dosyaya yaz (sistem dokunulmaz)
    try:
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)
    except FileNotFoundError:
        existing = {}

    symbols = BIST30 + NASDAQ100 + CRYPTO30
    print(f"Bayesian arama — {len(symbols)} sembol × {N_TRIALS} trial")
    print(f"Çıktı: {OUTPUT_FILE} (mevcut {COMPARE_AGAINST} dokunulmaz)")
    print(f"Tahmini süre: {len(symbols) * 30 / 60:.0f}-{len(symbols) * 80 / 60:.0f} dakika\n")

    improved = 0
    same = 0
    failed = 0
    t0 = time.time()

    for i, sym in enumerate(symbols, 1):
        ts = time.time()
        try:
            r = optimize_symbol(sym)
        except Exception as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)[:80]}
        dt = time.time() - ts

        if not r or not r.get("ok"):
            failed += 1
            reason = r.get("reason", "?") if r else "veri yok"
            print(f"[{i:3d}/{len(symbols)}] {sym:<12} ✗ {reason}  ({dt:.0f}sn)")
            continue

        new_score = r["best_score"]
        new_s = r["stats"]
        new_ret = new_s["return"] * 100
        new_win = new_s["win_rate"] * 100
        new_rt = r["rating"]

        # Mevcut grid sonucu ile karşılaştır (sadece raporlama için)
        grid_old = grid_results.get(sym, {})
        grid_ret = grid_old.get("stats", {}).get("return", -999) * 100 if grid_old.get("ok") else -999
        grid_rt = grid_old.get("rating", "—")

        # Bayesian sonucunu her durumda kaydet (ayrı dosya)
        existing[sym] = r
        if new_ret > grid_ret:
            improved += 1
            marker = "★ GRİD'TEN İYİ"
        else:
            same += 1
            marker = " "

        pf_str = f"{new_s['pf']:.2f}" if new_s["pf"] else "∞"
        print(f"[{i:3d}/{len(symbols)}] {sym:<12} {new_rt:<10} "
              f"ret={new_ret:+6.1f}% PF={pf_str:>5} win={new_win:.0f}% n={new_s['n_trades']:3d}  "
              f"(grid:{grid_ret:+5.1f}% {grid_rt}) {marker} ({dt:.0f}sn)")

        # Her 10 sembolde ara kayıt (Bayesian'a özel dosya)
        if i % 10 == 0:
            with open(OUTPUT_FILE, "w") as f:
                json.dump(existing, f, indent=2, default=str)
            elapsed = time.time() - t0
            eta = elapsed / i * (len(symbols) - i)
            print(f"  ── kaydedildi → {OUTPUT_FILE} · {improved} grid'ten iyi · ETA {eta/60:.0f}dk ──\n")

    # Final kayıt
    with open(OUTPUT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  Toplam süre  : {elapsed/60:.1f} dakika")
    print(f"  İyileşen     : {improved}/{len(symbols)}")
    print(f"  Aynı/azalan  : {same}")
    print(f"  Başarısız    : {failed}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
