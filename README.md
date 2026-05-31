# OTT Bot Dashboard

Anıl Özekşi'nin OTT-family (TOTT + SOTT + HOTT/LOTT + ROTT) algoritmik
sinyal sistemini Python'a port edip otomatize eden dashboard.

## Live demo
🔗 (Streamlit Cloud URL'i kurulumdan sonra burada)

## Özellikler

- 🎯 **Sabah Ritüeli** — sermayeni gir, sistem bugünün en güçlü
  pozisyonlarını filtreler, stop-loss seviyeleriyle birlikte verir
- 🛡️ **Güvenli Mod** — sadece "MÜKEMMEL + Multi-timeframe + Recent form
  pozitif" sembolleri gösterir. Terste kalma riskini minimize eder
- 📡 **Anlık Tarayıcı** — 151 sembol için canlı durum tablosu
- 📊 **Detay Grafik** — TradingView tarzı candle + OTT + sinyaller
- 💼 **Portföy Simülasyonu** — geçmiş kaldıraçlı simülasyon
- 🤖 **Auto-update** — her Pazar gece GitHub Actions ile parametre yenileme

## Kapsanan piyasalar (151 sembol)

- **NASDAQ 100** (100 hisse) → H1 timeframe
- **BIST 30** (32 hisse) → H1 timeframe
- **Crypto** (30 coin) → 30-dakika timeframe

## Sistem mimarisi

```
┌─────────────────────────────────────────────────────────┐
│  TradingView (veri)                                     │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────▼────────┐         ┌──────────────────┐
        │  data_source.py │◄────────│  per_symbol_     │
        │  fetch()        │         │  optimize.py     │
        └────────┬────────┘         │  (haftalık)      │
                 │                  └────────┬─────────┘
                 │                           ▼
        ┌────────▼─────────────────────────────────────┐
        │  indicators.py (numba JIT — Pine doğru port) │
        │  signals_full.py (kombinasyon mantığı)       │
        │  backtest.py (event-driven)                  │
        └────────┬─────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │  app.py         │
        │  (Streamlit)    │
        └─────────────────┘
```

## Dosya rehberi

| Dosya | Görev |
|---|---|
| `app.py` | Streamlit dashboard (anasayfa) |
| `indicators.py` | VAR, OTT, TOTT, ROTT, SOTT, HOTT/LOTT (Pine port) |
| `signals_full.py` | Tam sistem sinyal mantığı |
| `backtest.py` | Custom backtest motoru |
| `data_source.py` | TradingView / yfinance unified veri |
| `per_symbol_optimize.py` | Sembol bazlı sıralı optimize |
| `safe_mode.py` | Güvenli Mod filtreleri |
| `auto_daemon.py` | Lokal cron (Cloud'da yerine GitHub Actions) |
| `.github/workflows/weekly_optimize.yml` | Haftalık otomatik optimize |

## Kurulum (lokal)

```bash
pip install -r requirements.txt
cp .env.example .env
# .env içine TV_USERNAME, TV_PASSWORD yaz
streamlit run app.py
```

## Cloud deployment

`CLOUD_DEPLOY.txt` dosyasındaki adımları takip et.

## Lisans / Atıf

Anıl Özekşi'nin OTT-family sistemi:
- Pine kaynaklar: Kivanç Özbilgiç (@kivancozbilgic, TradingView)
- Sistem tasarımı: Anıl Özekşi (@Anil_Ozeksi)
- Python port: bu repo
