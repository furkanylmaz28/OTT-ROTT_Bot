"""
reliability.py — "Güvenilir sembol" muhafazakâr kapısı (İlerleyen Algo Trading / ADIM A).

Felsefe: Bayes (serbest) neredeyse her şeye MÜKEMMEL diyor (overfit). Mold (eşli
kalıp) en dürüst/kısıtlı yöntem. Bir sembolü ancak MUHAFAZAKÂR yöntem onaylıyorsa
"güvenilir" sayarız → overfit yanılsamalarına güvenmeyi bırakırız.

Kapı:
  - mold verisi VARSA (BIST/CRYPTO/EMTIA): mold rating İYİ+ (MÜKEMMEL/İYİ/ORTA) olmalı
  - mold verisi YOKSA (NASDAQ 416): Grid İYİ+ (MÜKEMMEL/İYİ) — mevcut kapı
"""
from __future__ import annotations
import json, os

GOOD = {"MÜKEMMEL", "İYİ", "ORTA"}
GOOD_STRICT = {"MÜKEMMEL", "İYİ"}
_MOLD_FILE = "per_symbol_params_mold.json"
_mold_cache = None


def load_mold():
    global _mold_cache
    if _mold_cache is None:
        try:
            with open(_MOLD_FILE, encoding="utf-8") as f:
                _mold_cache = json.load(f)
        except Exception:
            _mold_cache = {}
    return _mold_cache


def mold_rating(sym):
    m = load_mold().get(sym, {})
    return m.get("rating") if m.get("ok") else None


def is_reliable(sym, grid=None):
    """Sembol muhafazakâr kapıdan geçer mi?
    grid: per_symbol_params.json dict (NASDAQ fallback için). None ise sadece mold."""
    mr = mold_rating(sym)
    if mr is not None:                       # mold verisi var → mold karar verir
        return mr in GOOD
    # mold yok (NASDAQ) → Grid İYİ+ fallback
    if grid is not None:
        g = grid.get(sym, {})
        if g.get("ok"):
            return g.get("rating") in GOOD_STRICT
    return False


def reliable_set(grid=None):
    """Mold'da güvenilir (İYİ+) tüm semboller."""
    return {s for s in load_mold() if is_reliable(s)}


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    rs = reliable_set()
    print(f"Mold güvenilir sembol: {len(rs)}")
    print(sorted(rs))
