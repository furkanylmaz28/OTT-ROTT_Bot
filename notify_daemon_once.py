"""
notify_daemon_once.py — tek seferlik konsensüs taraması.

GitHub Actions saatte 1 çalıştırır:
  1. Tüm sembolleri Grid (FY) + Bayes ile tara
  2. Konsensüs sinyallerini (LONG AÇ / SHORT AÇ / ÇIK) topla
  3. notify_state.json ile karşılaştır → sadece YENİ olanları Telegram'a gönder
  4. State'i güncelle ve commit/push (workflow yapar)

Lokal test:
  python notify_daemon_once.py
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# notify_daemon'dan ortak fonksiyonları kullan
from notify_daemon import scan_consensus, load_state, save_state, format_message
from notifications import notify, is_configured


def main():
    cfg = is_configured()
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Tek tarama başladı")
    print(f"  Telegram: {'✓' if cfg['telegram'] else '✗'}  "
          f"Email: {'✓' if cfg['email'] else '✗'}")
    if not any(cfg.values()):
        print("✗ Hiç bildirim kanalı yapılandırılmamış. Çıkılıyor.")
        sys.exit(0)

    try:
        fresh = scan_consensus()
        print(f"  Konsensüs sinyali bulunan: {len(fresh)}")

        state = load_state()
        new = [s for s in fresh
               if state.get(s["sym"]) != f"{s['kind']}_{s['fy']}"]
        # State güncelle (yeni olanlar dahil hepsini kaydet)
        for s in fresh:
            state[s["sym"]] = f"{s['kind']}_{s['fy']}"
        # Süpürme: artık fresh olmayan sembolleri state'ten temizle (opsiyonel — keep)
        save_state(state)

        if new:
            msg_html = format_message(new)
            msg_plain = (msg_html.replace("<b>", "").replace("</b>", "")
                                  .replace("<i>", "").replace("</i>", ""))
            r = notify("OTT Bot — Yeni Sinyal", msg_html, msg_plain)
            print(f"  {len(new)} YENİ sinyal → Telegram:{r['telegram']} Email:{r['email']}")
            for s in new:
                print(f"    • {s['sym']}: {s['fy']}  (Bayes: {s.get('bayes')})")
        else:
            print(f"  Yeni sinyal yok ({len(fresh)} aktif sinyal değişmedi)")
    except Exception as e:
        import traceback
        print(f"  HATA: {e}")
        traceback.print_exc()
        # Workflow yine de devam etsin (exit 0)
    print(f"[{datetime.now():%H:%M}] Tarama bitti")


if __name__ == "__main__":
    main()
