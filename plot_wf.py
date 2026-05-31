"""
Walk-forward sonuçlarının görsel özeti — IS vs OOS karşılaştırması.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_wf(csv_path: str, save_path: str, title: str):
    df = pd.read_csv(csv_path)
    n = len(df)
    if n == 0:
        return
    x = np.arange(n)

    fig, axes = plt.subplots(2, 1, figsize=(14, 8),
                             gridspec_kw={"height_ratios": [2, 1]})

    # Üst: IS, OOS, BH bar grafiği
    ax = axes[0]
    width = 0.25
    is_vals = df["is_return"] * 100
    oos_vals = df["oos_return"] * 100
    bh_vals = df["bh_return"] * 100

    ax.bar(x - width, is_vals, width, label="In-Sample", color="#7aa6c2", alpha=0.85)
    ax.bar(x,         oos_vals, width, label="Out-of-Sample",
           color=["#2a8c4a" if v > 0 else "#c33a3a" for v in oos_vals], alpha=0.95)
    ax.bar(x + width, bh_vals, width, label="Buy & Hold", color="#bbb", alpha=0.65)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"P{i+1}" for i in range(n)])
    ax.set_ylabel("Return %")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    ax.set_title(title)

    # Alt: kümülatif OOS equity vs BH
    ax2 = axes[1]
    cum_oos = (1 + df["oos_return"]).cumprod() - 1
    cum_bh  = (1 + df["bh_return"]).cumprod() - 1
    ax2.plot(x, cum_oos * 100, "o-", color="#2a8c4a", label="Sistem OOS kümülatif", linewidth=2)
    ax2.plot(x, cum_bh * 100, "s--", color="#888", label="Buy & Hold kümülatif", linewidth=1.5)
    ax2.axhline(0, color="black", linewidth=0.7)
    ax2.set_xticks(x); ax2.set_xticklabels([f"P{i+1}" for i in range(n)])
    ax2.set_ylabel("Kümülatif Getiri %")
    ax2.set_xlabel("Pencere")
    ax2.legend(); ax2.grid(alpha=0.3)

    # ekstra metin
    pos = (df["oos_return"] > 0).sum()
    avg_oos = df["oos_return"].mean() * 100
    wf_eff = avg_oos / (df["is_return"].mean() * 100) if df["is_return"].mean() > 0 else 0
    total_oos = ((1 + df["oos_return"]).prod() - 1) * 100
    total_bh = ((1 + df["bh_return"]).prod() - 1) * 100
    info = (f"  Pozitif OOS: {pos}/{n} ({pos/n*100:.0f}%)   "
            f"WF eff: {wf_eff*100:.1f}%   "
            f"Toplam OOS: {total_oos:+.2f}%   "
            f"Buy & Hold: {total_bh:+.2f}%")
    ax2.text(0.5, -0.25, info, transform=ax2.transAxes, ha="center",
             fontsize=11, bbox=dict(boxstyle="round", facecolor="lightyellow"))

    plt.tight_layout()
    plt.savefig(save_path, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {save_path}")


if __name__ == "__main__":
    os.makedirs("plots_wf", exist_ok=True)
    plot_wf("wfseq_GOLD_M15.csv", "plots_wf/GOLD_M15_walkforward.png",
            "GOLD M15 — Walk-Forward (sıralı optimize ile)")
    plot_wf("wfseq_GOLD_M5.csv",  "plots_wf/GOLD_M5_walkforward.png",
            "GOLD M5 — Walk-Forward (sıralı optimize ile)")
