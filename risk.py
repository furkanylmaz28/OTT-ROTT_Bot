"""
risk.py — Risk yönetimi modülü. SİNYAL ÜRETMEZ; sadece "ne kadar al" ve "ne zaman dur".

Sinyal katmanından (longonly_strategy / grid_strategy) bağımsız. Getiri/DD testiyle
"elenmez" çünkü işi getiri artırmak değil — pozisyon boyutu + tail riski yönetmek.

Kullanım:
    import risk
    qty = risk.position_size(account=60000, entry=100.0, stop=96.0)   # %1 risk
    halt, sebep = risk.loss_brake(today_pct=-2.3, week_pct=-1.0)      # günlük limit aşıldı mı
    if risk.can_open(open_n=3, halted=halt): ...
"""
from __future__ import annotations

# ── Ayarlar (config) ──
ACCOUNT_RISK    = 0.01    # işlem başı hesabın %1'i risk
MAX_POSITIONS   = 6       # aynı anda en fazla pozisyon
MAX_LEVERAGE    = 2.0     # toplam notional ≤ hesap × bu (1:7 = iflas)
MAX_DAILY_LOSS  = 0.02    # günlük -%2 → o gün dur
MAX_WEEKLY_LOSS = 0.05    # haftalık -%5 → hafta sonuna kadar dur


def position_size(account: float, entry: float, stop: float,
                  risk_pct: float = ACCOUNT_RISK, max_lev: float = MAX_LEVERAGE) -> dict:
    """ATR/stop-bazlı pozisyon boyutu. Risk = (giriş - stop) × adet = hesap × risk_pct.
    Long varsayar (stop < giriş). Kaldıraç tavanı uygulanır.
    Döner: dict(adet, notional, risk_tutari, kaldirac, uyari)."""
    if entry <= 0 or stop <= 0 or stop >= entry:
        return {"adet": 0, "notional": 0.0, "risk_tutari": 0.0, "kaldirac": 0.0,
                "uyari": "geçersiz giriş/stop (stop < giriş olmalı)"}
    risk_tutari = account * risk_pct
    per_unit = entry - stop                      # birim başı risk (stop mesafesi)
    adet = risk_tutari / per_unit
    notional = adet * entry
    uyari = ""
    cap = account * max_lev
    if notional > cap:                           # kaldıraç tavanını aşma
        adet = cap / entry; notional = cap
        uyari = f"kaldıraç tavanı: pozisyon {max_lev}×'e kısıldı (stop çok uzak)"
    return {"adet": round(adet, 4), "notional": round(notional, 2),
            "risk_tutari": round(risk_tutari, 2),
            "kaldirac": round(notional / account, 2), "uyari": uyari}


def loss_brake(today_pct: float, week_pct: float) -> tuple[bool, str]:
    """Günlük/haftalık zarar limiti aşıldı mı? today_pct/week_pct = yüzde (örn -2.3).
    Döner: (dur_mu, sebep)."""
    if today_pct <= -MAX_DAILY_LOSS * 100:
        return True, f"🛑 GÜNLÜK zarar limiti aşıldı ({today_pct:+.1f}% ≤ -{MAX_DAILY_LOSS*100:.0f}%) — bugün yeni işlem YOK"
    if week_pct <= -MAX_WEEKLY_LOSS * 100:
        return True, f"🛑 HAFTALIK zarar limiti aşıldı ({week_pct:+.1f}% ≤ -{MAX_WEEKLY_LOSS*100:.0f}%) — hafta sonuna kadar dur"
    return False, ""


def can_open(open_n: int, halted: bool = False) -> bool:
    """Yeni pozisyon açılabilir mi? (limit dolmamış + zarar freni kapalı)"""
    return (not halted) and open_n < MAX_POSITIONS


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    print("risk.py kendi-testi\n" + "=" * 50)
    # 60.000₺ hesap, giriş 100, stop 96 (4% stop mesafesi)
    r = position_size(60000, 100.0, 96.0)
    print(f"60.000₺ · giriş 100 · stop 96 (%4 uzak):")
    print(f"   → {r['adet']} adet · notional {r['notional']:,.0f}₺ · risk {r['risk_tutari']:,.0f}₺ · {r['kaldirac']}× {r['uyari']}")
    # stop çok yakın → büyük pozisyon → kaldıraç tavanı devreye girer
    r2 = position_size(60000, 100.0, 99.5)
    print(f"60.000₺ · giriş 100 · stop 99.5 (%0.5 uzak, çok yakın):")
    print(f"   → {r2['adet']} adet · notional {r2['notional']:,.0f}₺ · {r2['kaldirac']}× · {r2['uyari']}")
    # zarar freni
    print("\nZarar freni:")
    for t, w in [(-1.0, -1.0), (-2.5, -1.0), (-0.5, -5.2)]:
        h, s = loss_brake(t, w)
        print(f"   günlük {t:+.1f}% haftalık {w:+.1f}% → {'DUR: '+s if h else '✅ devam'}")
    print(f"\ncan_open(3 açık, fren yok): {can_open(3, False)}")
    print(f"can_open(6 açık, fren yok): {can_open(6, False)}  (limit dolu)")
    print(f"can_open(2 açık, fren açık): {can_open(2, True)}  (zarar freni)")
