"""
Google Sheets entegrasyonu — portföy verisini kalıcı tutar.

Kurulum (1 kez):
  1. https://console.cloud.google.com → yeni proje aç
  2. APIs & Services → "Google Sheets API" enable
  3. APIs & Services → Credentials → Create Credentials → Service Account
     - Service Account JSON anahtarını indir
  4. JSON'ı bu klasöre koy: gsheets_credentials.json
  5. .gitignore'a ekle: gsheets_credentials.json
  6. Google Sheets'te yeni bir sayfa oluştur: "OTT Bot Portfolio"
  7. JSON içindeki email'i (xxx@xxx.iam.gserviceaccount.com) sayfaya
     Düzenleyici olarak paylaş

  Streamlit Cloud için secrets.toml:
    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    ... (JSON içeriğini buraya kopyala)

Kullanım:
  from gsheets_storage import load_portfolio_sheets, save_portfolio_sheets
  df = load_portfolio_sheets()
  save_portfolio_sheets(df)
"""
from __future__ import annotations
import os
import json
import pandas as pd

SHEET_NAME = "OTT Bot Portfolio"
WORKSHEET = "portfolio"

_gc_cache = None


def _get_client():
    """gspread istemcisini lazy initialize."""
    global _gc_cache
    if _gc_cache is not None:
        return _gc_cache
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None

    creds_data = None
    # 1) Streamlit Cloud secrets
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            creds_data = dict(st.secrets["gcp_service_account"])
    except Exception:
        pass
    # 2) Lokal JSON dosyası
    if not creds_data and os.path.exists("gsheets_credentials.json"):
        with open("gsheets_credentials.json") as f:
            creds_data = json.load(f)
    if not creds_data:
        return None

    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    _gc_cache = gspread.authorize(creds)
    return _gc_cache


def _get_sheet():
    gc = _get_client()
    if gc is None:
        return None
    try:
        sheet = gc.open(SHEET_NAME).worksheet(WORKSHEET)
    except Exception:
        try:
            sheet = gc.open(SHEET_NAME).add_worksheet(WORKSHEET, rows=1000, cols=20)
        except Exception:
            return None
    return sheet


def load_portfolio_sheets() -> pd.DataFrame | None:
    """Google Sheets'ten portföy yükle. None → bağlantı yok / boş."""
    sheet = _get_sheet()
    if sheet is None:
        return None
    try:
        rows = sheet.get_all_records()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
    except Exception:
        return None


_last_error = None


def get_last_error() -> str | None:
    return _last_error


def save_portfolio_sheets(df: pd.DataFrame) -> bool:
    """Portföyü Google Sheets'e yaz. True → başarılı."""
    global _last_error
    _last_error = None
    sheet = _get_sheet()
    if sheet is None:
        _last_error = "Bağlantı yok (credentials veya Sheets bulunamadı)"
        return False
    try:
        sheet.clear()
        if len(df) == 0:
            return True
        header = list(df.columns)
        values = df.fillna("").astype(str).values.tolist()
        # gspread 6.x: keyword args zorunlu
        try:
            sheet.update(values=[header] + values, range_name="A1")
        except TypeError:
            # Eski gspread fallback
            sheet.update("A1", [header] + values)
        return True
    except Exception as e:
        _last_error = f"{type(e).__name__}: {str(e)[:300]}"
        return False


def is_available() -> bool:
    """Google Sheets bağlantısı aktif mi?"""
    return _get_sheet() is not None


if __name__ == "__main__":
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    print("Google Sheets bağlantı testi:")
    if is_available():
        print("  ✓ bağlantı aktif")
        df = load_portfolio_sheets()
        print(f"  Yüklü {len(df) if df is not None else 0} satır")
    else:
        print("  ✗ Bağlantı yok")
        print("  → gsheets_credentials.json yok veya yapılandırma eksik")
        print("  → Detaylı kurulum: gsheets_storage.py dosyasının başındaki yorumu oku")
