"""
borsa_mudur.py — "Borsa Müdürü" ajanı. Ekibin (Algo Trader + Grafik Takipçisi +
Haberci) çıktılarını TEK rapora toplar ve Telegram'a gönderir. KARAR VERMEZ —
istihbaratı sentezler, kararı insana bırakır.

Akıllı kadans: cron her 10 dk çağırır; müdür sadece KAYDA DEĞER bir şey değişince
(yeni işlem/sinyal/haber/breadth) rapor atar (≥20 dk arayla). Ayrıca 4 saatte bir
"hayatta" sinyali. Böylece günde 48 spam yerine sadece önemli güncellemeler gelir.

Kullanım:
    python borsa_mudur.py          # rapor üret + (değişiklik varsa) gönder
    python borsa_mudur.py --dry    # sadece ekrana
    python borsa_mudur.py --force  # değişiklik olmasa da gönder
    python borsa_mudur.py --cron   # cron modu (akıllı kadans + state)
"""
from __future__ import annotations
import sys, os, json, hashlib
from datetime import datetime, timezone, timedelta
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
# Ayrı process olarak koşar → .env'i KENDİSİ yüklemeli (yoksa Telegram token'ı
# os.getenv'de None döner, rapor sessizce gönderilemez).
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception: pass

TR = timezone(timedelta(hours=3))
STATE_FILE = "borsa_mudur_state.json"
VERDICT_N = 100


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default


def _stats(trades):
    pn = [t.get("pnl_pct", 0) for t in trades] if isinstance(trades, list) else []
    n = len(pn)
    if not n: return {"n": 0, "wr": 0, "pf": 0, "tot": 0}
    w = [p for p in pn if p > 0]; l = [p for p in pn if p <= 0]
    gw, gl = sum(w), abs(sum(l))
    pf = (gw / gl) if gl > 0 else (999 if gw > 0 else 0)
    return {"n": n, "wr": round(100 * len(w) / n, 1), "pf": round(pf, 2), "tot": round(sum(pn), 1)}


UNIVERSE = set(("AKBNK ASELS DOHOL ENJSA EKGYO ENKAI EREGL FROTO GUBRF HALKB ISCTR KCHOL "
                "KRDMD MGROS PETKM PGSUS SASA SISE SOKM TAVHL THYAO TOASO TKFEN TTKOM TUPRS "
                "VAKBN YKBNK AEFES HEKTS ODAS ASTOR AKSEN ALARK KONTR ARCLK BIMAS GARAN OYAKC "
                "SAHOL TCELL TSKB VESTL DOAS CIMSA ULKER").split())


def gather():
    """Ekip çıktılarını topla."""
    lo_pos = _load("lo_positions.json", {})
    cg_pos = _load("cg_positions.json", {})
    lo_tr = _load("lo_trades.json", [])
    cg_tr = _load("cg_trades.json", [])
    breadth = _load("lo_breadth.json", {})
    news, impact = [], []
    try:
        import borsa_haberci as hb
        watch = set(k.replace(".IS", "") for k in lo_pos) | set(breadth.get("bull_syms", [])[:20])
        news = hb.get_news(hours=24, symbols=watch or None)
        impact = hb.analyze_impact(hb.get_macro_news(), UNIVERSE)   # dünya/TR haber → 45 hisse etkisi
    except Exception:
        pass
    return {
        "lo_pos": lo_pos, "cg_pos": cg_pos,
        "lo": _stats(lo_tr), "cg": _stats(cg_tr),
        "breadth": breadth, "news": news, "impact": impact,
    }


def signature(g):
    """Değişiklik tespiti için durum imzası (yeni işlem/poz/haber/breadth)."""
    bp = round(g["breadth"].get("bull_pct", -1) / 10)   # 10'luk kova
    key = (
        sorted(g["lo_pos"].keys()),
        sum(len(v) for v in g["cg_pos"].values()) if isinstance(g["cg_pos"], dict) else 0,
        g["lo"]["n"], g["cg"]["n"], bp, len(g["news"]), len(g.get("impact", [])),
    )
    return hashlib.md5(str(key).encode()).hexdigest()[:12]


def build_report(g):
    now = datetime.now(TR)
    L = [f"🧑‍💼 *BORSA MÜDÜRÜ* — {now:%d.%m %H:%M}", ""]
    # Piyasa (Grafik Takipçisi + breadth)
    bp = g["breadth"].get("bull_pct")
    if bp is not None:
        mood = "🟢 güçlü" if bp >= 50 else ("🟡 nötr" if bp >= 35 else "🔴 ZAYIF")
        L.append(f"🌡️ *Piyasa:* bull %{bp:.0f} {mood}")
        fb = g["breadth"].get("fresh_bear", [])
        if fb: L.append(f"   ⚠️ taze ayıya dönen: {', '.join(fb[:6])}")
    # Algo Trader (açık pozisyonlar)
    lo_n = len(g["lo_pos"]); cg_n = sum(len(v) for v in g["cg_pos"].values()) if isinstance(g["cg_pos"], dict) else 0
    L.append(f"🤖 *Algo Trader:* BIST {lo_n} açık ({', '.join(k.replace('.IS','') for k in list(g['lo_pos'])[:6]) or '—'}) · Crypto {cg_n} birim")
    # Performans
    L.append(f"📊 *Performans:* BIST PF {g['lo']['pf']} ({g['lo']['n']} işlem) · Crypto PF {g['cg']['pf']} ({g['cg']['tot']:+}%, {g['cg']['n']} işlem)")
    # Haberci — KAP
    if g["news"]:
        L.append(f"📰 *KAP:* {len(g['news'])} bildirim")
        for n in g["news"][:4]:
            L.append(f"   • {n['time']} {n['sym']}: {n['title'][:50]}")
    # Haberci — Dünya/TR makro haber → BIST etkisi
    if g.get("impact"):
        L.append("🌍 *Dünya/TR Haber → BIST Etkisi:*")
        for x in g["impact"][:4]:
            pos = [s for s, y, _ in x["etkiler"] if y == "+"]
            neg = [s for s, y, _ in x["etkiler"] if y == "-"]
            amb = [s for s, y, _ in x["etkiler"] if y == "±"]
            et = ""
            if pos: et += f"  🟢 {', '.join(pos[:4])}"
            if neg: et += f"  🔴 {', '.join(neg[:4])}"
            if amb: et += f"  🟡 {', '.join(amb[:3])}"
            L.append(f"   • {x['title'][:58]}\n     →{et}")
    if not g["news"] and not g.get("impact"):
        L.append("📰 *Haberci:* yeni haber/etki yok")
    # 🎯 BIST Öneri — kanıtlanmış sistemin (SuperTrend long-only) sinyali. SHORT YOK.
    bull = g["breadth"].get("bull_syms", [])
    posset = {k.replace(".IS", "") for k in g["lo_pos"]}
    aday = [s for s in bull if s not in posset]
    fbear = g["breadth"].get("fresh_bear", [])
    if bull or aday or fbear:
        L.append("🎯 *BIST Öneri* (Algo Trader · long-only):")
        if posset: L.append(f"   📂 Pozisyonda LONG: {', '.join(sorted(posset)[:8])}")
        if aday:   L.append(f"   ✨ LONG aday (sinyal var, girilmemiş): {', '.join(aday[:8])}")
        if fbear:  L.append(f"   ⚪ NAKİT'e dön / kaçın: {', '.join(fbear[:8])}")
        L.append("   ⛔ Short YOK — BIST'te short yapısal kaybettirir (kanıtlı); çıkış=nakit")
    # Yargı sayacı
    tot_n = g["lo"]["n"] + g["cg"]["n"]
    pct = min(100, round(100 * tot_n / VERDICT_N))
    L.append(f"🎯 *Yargı:* {tot_n}/{VERDICT_N} (%{pct}) — {'✅ yeterli' if tot_n>=VERDICT_N else f'{VERDICT_N-tot_n} işlem daha'}")
    L.append("")
    L.append("_Müdür istihbarat sentezler; kararı SEN verirsin._")
    return "\n".join(L)


def _send(msg):
    try:
        from notifications import send_telegram
        ok = send_telegram(msg)
        print("[Telegram:", "gönderildi ✅" if ok else "gönderilemedi ❌", "]")
        return ok
    except Exception as e:
        print(f"[Telegram hata: {e}]"); return False


def main():
    g = gather()
    report = build_report(g)
    print(report)
    if "--dry" in sys.argv:
        print("\n[--dry]"); return
    if "--force" in sys.argv:
        _send(report); return
    if "--cron" in sys.argv:
        now = datetime.now(TR)
        st = _load(STATE_FILE, {})
        sig = signature(g)
        last_ts = st.get("ts"); last_sig = st.get("sig")
        # son gönderimden bu yana dakika
        mins = 999
        if last_ts:
            try: mins = (now - datetime.fromisoformat(last_ts)).total_seconds() / 60
            except Exception: pass
        changed = (sig != last_sig)
        # SADECE TR 09:30–18:30 arası raporla (BIST seansı); dışında sus
        nowmin = now.hour * 60 + now.minute
        in_window = (9 * 60 + 30) <= nowmin <= (18 * 60 + 30)
        # gönder: pencere içinde + DÜZENLİ ~30 dk VEYA değişiklikte ≥8 dk
        if in_window and (mins >= 28 or (changed and mins >= 8)):
            if _send(report):
                json.dump({"ts": now.isoformat(), "sig": sig}, open(STATE_FILE, "w"))
        elif not in_window:
            print(f"[cron: pencere dışı (TR {now:%H:%M}) — 09:30-18:30 arası raporlar]")
        else:
            print(f"[cron: gönderilmedi — son gönderimden {mins:.0f}dk (30 dk bekleniyor)]")
        return
    _send(report)


if __name__ == "__main__":
    main()
