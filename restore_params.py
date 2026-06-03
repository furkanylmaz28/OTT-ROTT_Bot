"""
Eski parametrelere geri dön — Quarterly optimize sonrası sistem bozulduysa.

Kullanım:
  python restore_params.py              → mevcut yedekleri listele
  python restore_params.py 2026-06-03   → bu tarihteki yedeği geri yükle

Sonra:
  git add per_symbol_params*.json
  git commit -m "rollback: 2026-06-03 parametrelerine dön"
  git push
"""
from __future__ import annotations
import sys
import os
import shutil
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BACKUP_DIR = Path("backups")
TARGETS = {
    "per_symbol_params.json":       "per_symbol_params_{stamp}.json",
    "per_symbol_params_bayes.json": "per_symbol_params_bayes_{stamp}.json",
}


def list_backups():
    """Mevcut yedekleri tarih sırasına göre listele."""
    if not BACKUP_DIR.exists():
        print("✗ backups/ klasörü yok. Henüz hiç yedek alınmamış.")
        return []
    files = sorted(BACKUP_DIR.glob("per_symbol_params_*.json"))
    # Tarihleri çıkar
    stamps = set()
    for f in files:
        # per_symbol_params_2026-06-03.json veya
        # per_symbol_params_bayes_2026-06-03.json
        name = f.stem  # per_symbol_params_2026-06-03
        parts = name.split("_")
        # son parça tarih olmalı (YYYY-MM-DD)
        if parts and len(parts[-1]) == 10 and parts[-1].count("-") == 2:
            stamps.add(parts[-1])
    return sorted(stamps, reverse=True)


def restore(stamp):
    """Belirtilen tarihteki yedekleri geri yükle."""
    restored = []
    failed = []
    for target, template in TARGETS.items():
        src = BACKUP_DIR / template.format(stamp=stamp)
        if not src.exists():
            failed.append((target, src))
            continue
        # Önce mevcutu emergency_backup'a kopyala
        if Path(target).exists():
            emergency = Path(target).with_suffix(f".pre-rollback-{stamp}.json")
            shutil.copy2(target, emergency)
            print(f"  ⚠️ Mevcut {target} → {emergency} olarak yedeklendi")
        shutil.copy2(src, target)
        restored.append((target, src))
        print(f"  ✓ {target} ← {src}")
    return restored, failed


def main():
    if len(sys.argv) == 1:
        # Listele
        print("📂 Mevcut parametre yedekleri (en yenisi üstte):\n")
        stamps = list_backups()
        if not stamps:
            print("  (hiç yedek yok)")
            return 0
        for s in stamps:
            print(f"  • {s}")
        print(f"\nGeri yüklemek için:")
        print(f"  python restore_params.py {stamps[0]}")
        return 0

    stamp = sys.argv[1]
    print(f"🔄 Geri yükleniyor: {stamp}\n")
    restored, failed = restore(stamp)
    print()
    if restored:
        print(f"✓ {len(restored)} dosya geri yüklendi")
    if failed:
        print(f"✗ {len(failed)} dosya yedek bulunamadı:")
        for t, src in failed:
            print(f"   {t}: {src} yok")
    if restored:
        print("\nŞimdi push et:")
        print("  git add per_symbol_params*.json")
        print(f"  git commit -m 'rollback: {stamp} parametrelerine dön'")
        print("  git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
