"""
Otomatik güncelleme daemon'u — sürekli arka planda çalışır.

Görevleri:
  1) Her gün 02:00'da TÜM sembolleri yeniden optimize et (per_symbol_optimize)
  2) Her saatte anlık fiyat snapshot al (intraday verileri tazele)
  3) Tüm aktivite log'unu auto_update.log'a yaz

Çalıştırmak için:
   cd C:\\Users\\furka\\Desktop\\ott_bot
   python auto_daemon.py

   (Veya Windows Task Scheduler ile sistem açılışında otomatik tetikle.)
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import os, time, subprocess, json
from datetime import datetime, timedelta


LOG = "auto_update.log"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_full_optimize():
    log("Tam optimize başlatılıyor (per_symbol_optimize.py)")
    try:
        result = subprocess.run(
            ["python", "-u", "per_symbol_optimize.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=2400  # 40 dk timeout
        )
        if result.returncode == 0:
            log("✓ Tam optimize başarılı")
        else:
            log(f"✗ Tam optimize hata: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        log("✗ Tam optimize timeout (40 dk geçti)")
    except Exception as e:
        log(f"✗ Hata: {e}")


def write_status():
    """Mevcut durumu auto_update_status.json'a yaz — dashboard bunu okuyabilir."""
    try:
        with open("per_symbol_params.json") as f:
            data = json.load(f)
        rating_counts = {}
        for sym, r in data.items():
            if r.get("ok"):
                rt = r.get("rating", "?")
                rating_counts[rt] = rating_counts.get(rt, 0) + 1

        status = {
            "last_update": datetime.now().isoformat(),
            "total_symbols": len(data),
            "rating_counts": rating_counts,
        }
        with open("auto_update_status.json", "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log(f"Status yazılamadı: {e}")


def main():
    log("=" * 60)
    log("Auto-update daemon başlatıldı")
    log(f"Sonraki tam optimize: PAZAR gece 02:00 (haftalık)")
    log("Manuel tetikleme için: trigger_optimize.flag dosyası oluştur")
    log("=" * 60)

    last_optimize_date = None
    TRIGGER_FILE = "trigger_optimize.flag"

    while True:
        now = datetime.now()

        # Manuel tetikleme dosyası varsa → hemen çalıştır
        if os.path.exists(TRIGGER_FILE):
            log("Manuel tetik dosyası bulundu — optimize başlatılıyor")
            os.remove(TRIGGER_FILE)
            run_full_optimize()
            write_status()
            last_optimize_date = now.date()
            continue

        # PAZAR (weekday=6) gece 02:00 — haftalık otomatik optimize
        if now.weekday() == 6 and now.hour == 2 and last_optimize_date != now.date():
            log(f"Pazar gece 02:00 — haftalık optimize tetikleniyor")
            run_full_optimize()
            write_status()
            last_optimize_date = now.date()

        # Status'u her saat güncelle
        if now.minute == 0 and now.second < 30:
            write_status()

        # 30 saniyede bir döngü
        time.sleep(30)


if __name__ == "__main__":
    main()
