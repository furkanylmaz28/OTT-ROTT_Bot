"""
equivalence.py — İlerleyen Algo Trading: frekans-eşli parametre KALIPLARI.

Eğitimin felsefesi: parametreleri SERBEST aramak (her kombinasyonu deneyip en
yüksek getiriyi seçmek) = overfit/yanılsama. Antidot: OTT periyodu ile Stochastic
periyodunu AYNI FREKANSTA eşle (fast/medium/slow birlikte hareket etsin), sadece
bu eşli az sayıda kalıbı test et.

NOT: Eğitimdeki sayılar (20-60, 0.6-1.5, 200-800) 1-DAKİKALIK grafik içindir.
Bizim sistem H1 → yöntem aynı, sınırlar H1'e uyarlanmış (trend_percent vb. çalışan
H1 değerlerinde sabit; FREKANS parametreleri — trend_length ↔ sott periyotları —
eşli kalıplarda hareket eder).

Kalıplar (eğitimdeki 500/200 mantığı):
  - 500 (dengeli piyasa): yavaş/orta, stochastic ilk parametresi büyük
  - 200 (dengesiz/sert) : hızlı, stochastic ilk parametresi küçük
"""
from __future__ import annotations

# H1 için sabit taban (frekans dışı parametreler — çalışan değerler)
BASE = dict(
    trend_percent=7.0, minor_percent=3.5,
    tott_percent=0.8, tott_coeff=0.0004,
    sott_percent=0.3,
    gate_length=20, gate_percent=0.5, gate_shift=0,
    rott_x1=30, rott_x2=1000, rott_percent=7.0,
)

# ── Frekans-eşli KALIPLAR ─────────────────────────────────────────
# Her kalıp: (trend_length, sott_period_k, sott_smooth_k) AYNI frekansta eşli.
# trend_length küçük=hızlı, büyük=yavaş. sott periyotları da paralel.
MOLDS_500 = [   # dengeli piyasa — yavaş/orta, büyük stochastic ilk param
    {"name": "500-bal",  "trend_length": 40, "sott_period_k": 500, "sott_smooth_k": 200},
    {"name": "500-fast", "trend_length": 30, "sott_period_k": 500, "sott_smooth_k": 300},
]
MOLDS_200 = [   # dengesiz/sert piyasa — hızlı, küçük stochastic ilk param
    {"name": "200-fast", "trend_length": 20, "sott_period_k": 200, "sott_smooth_k": 400},
    {"name": "200-med",  "trend_length": 30, "sott_period_k": 300, "sott_smooth_k": 300},
]

# trend_percent (ana trend OTT %) için H1'de küçük varyasyon (frekans değil, hassasiyet)
TREND_PCT_OPTS = [6.0, 7.0, 8.0]


def all_molds():
    """Tüm kalıpları (500 + 200), trend_percent varyasyonlarıyla döndür.
    Toplam = (2+2) × 3 = 12 eşli kombinasyon (serbest grid'in yüzlercesi yerine)."""
    out = []
    for m in (MOLDS_500 + MOLDS_200):
        for tp in TREND_PCT_OPTS:
            p = dict(BASE)
            p.update({k: v for k, v in m.items() if k != "name"})
            p["trend_percent"] = tp
            out.append({"mold": m["name"], "kalip": "500" if m["name"].startswith("500") else "200",
                        "params": p})
    return out


def free_grid():
    """KIYAS için: serbest (eşli OLMAYAN) grid — eğitimin 'yapma' dediği yöntem.
    trend_length × sott_period_k × sott_smooth_k bağımsız → çok kombinasyon."""
    out = []
    for tl in (20, 30, 40):
        for pk in (200, 500, 800):
            for sk in (100, 200, 300):
                for tp in TREND_PCT_OPTS:
                    p = dict(BASE)
                    p.update(trend_length=tl, sott_period_k=pk, sott_smooth_k=sk, trend_percent=tp)
                    out.append({"params": p})
    return out
