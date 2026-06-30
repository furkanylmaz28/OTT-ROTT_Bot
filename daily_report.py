"""
daily_report.py — Günlük konsolide performans raporu (Telegram).

Tüm canlı tracker'ları (BIST long-only + Crypto Grid) tek raporda toplar:
  bugünkü işlemler, kümülatif PF / kazanan%, 100-işlem yargı sayacı, zarar freni durumu.

Kullanım:
    python daily_report.py          # hesapla + Telegram'a gönder
    python daily_report.py --dry    # sadece ekrana yaz (gönderme)
Cron'a günde 1 kez bağlanır (örn TR 18:30).
"""
from __future__ import annotations
import sys, os, json
from datetime import datetime, timezone, timedelta
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
# Ayrı process olarak koşar → .env'i KENDİSİ yüklemeli (Telegram token os.getenv).
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception: pass

TR = timezone(timedelta(hours=3))
VERDICT_N = 100   # bu kadar işlemde dürüst yargı


def _load(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return []


def _stats(trades, key="pnl_pct"):
    pn = [t.get(key, 0) for t in trades]
    n = len(pn)
    if n == 0: return {"n": 0, "wr": 0, "pf": 0, "tot": 0}
    w = [p for p in pn if p > 0]; l = [p for p in pn if p <= 0]
    gw = sum(w); gl = abs(sum(l))
    pf = (gw / gl) if gl > 0 else (999 if gw > 0 else 0)
    return {"n": n, "wr": round(100*len(w)/n, 1), "pf": round(pf, 2), "tot": round(sum(pn), 1)}


def _today_count(trades, tskey):
    bugun = datetime.now(TR).date().isoformat()
    return sum(1 for t in trades if str(t.get(tskey, ""))[:10] == bugun)


def build_report() -> str:
    bist = _load("lo_trades.json")
    cg   = _load("cg_trades.json")
    sb, sc = _stats(bist), _stats(cg)
    tb = _today_count(bist, "exit_ts"); tc = _today_count(cg, "exit_ts")
    toplam_n = sb["n"] + sc["n"]

    L = [f"📊 *GÜNLÜK RAPOR* — {datetime.now(TR):%d.%m.%Y %H:%M}", ""]
    L.append(f"*BIST (long-only):* {sb['n']} işlem · kazanan %{sb['wr']} · PF {sb['pf']} · toplam {sb['tot']:+}%")
    L.append(f"   bugün: {tb} işlem")
    L.append(f"*Crypto Grid:* {sc['n']} işlem · kazanan %{sc['wr']} · PF {sc['pf']} · toplam {sc['tot']:+}%")
    L.append(f"   bugün: {tc} işlem")
    L.append("")
    # 100-işlem yargı sayacı
    pct = min(100, round(100 * toplam_n / VERDICT_N))
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    L.append(f"*Yargı sayacı:* {toplam_n}/{VERDICT_N}  {bar} %{pct}")
    if toplam_n < VERDICT_N:
        L.append(f"   → {VERDICT_N - toplam_n} işlem daha, sonra dürüst karar (gerçek para?)")
    else:
        # yeterli örneklem → ön-değerlendirme
        cg_ok = sc["pf"] >= 1.5 and sc["tot"] > 0
        L.append(f"   → ✅ örneklem yeterli. Crypto PF {sc['pf']} {'≥1.5 → küçük gerçek para düşünülebilir' if cg_ok else '<1.5 → edge zayıf, BEKLE'}")
    L.append("")
    L.append("_Hatırlatma: küçük örneklemde panik yok; karar veriyle, 100 işlemde._")
    return "\n".join(L)


STATE_FILE = "daily_report_state.json"


def _send(rapor):
    try:
        from notifications import send_telegram
        ok = send_telegram(rapor)
        print("\n[Telegram:", "gönderildi ✅" if ok else "gönderilemedi ❌", "]")
        return ok
    except Exception as e:
        print(f"\n[Telegram hatası: {e}]"); return False


def main():
    rapor = build_report()
    print(rapor)
    if "--dry" in sys.argv:
        print("\n[--dry: gönderilmedi]"); return
    if "--cron" in sys.argv:
        # cron her 10dk çağırır; sadece TR 18:30+ ve bugün gönderilmediyse gönder
        now = datetime.now(TR)
        if now.hour < 18 or (now.hour == 18 and now.minute < 30):
            print("\n[cron: henüz vakti değil (TR 18:30 bekleniyor)]"); return
        try: last = json.load(open(STATE_FILE, encoding="utf-8")).get("last")
        except Exception: last = None
        if last == now.date().isoformat():
            print("\n[cron: bugün zaten gönderildi]"); return
        if _send(rapor):
            json.dump({"last": now.date().isoformat()}, open(STATE_FILE, "w"))
        return
    _send(rapor)


if __name__ == "__main__":
    main()
