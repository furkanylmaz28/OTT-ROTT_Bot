"""
OTT BOT DASHBOARD — Streamlit uygulaması

Çalıştırmak için:
   cd C:\\Users\\furka\\Desktop\\ott_bot
   streamlit run app.py

Açılır: http://localhost:8501
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")

import time
import os
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
from streamlit_lightweight_charts import renderLightweightCharts

# Streamlit Cloud secrets.toml → environment variable yükle
# (data_source.py .env'in yerine env okuyor; Cloud'da .env yok, secrets var)
try:
    for _key in ("TV_USERNAME", "TV_PASSWORD",
                  "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
except Exception:
    pass

# Background scheduler — Telegram bildirim 7/24 (Streamlit Cloud içinde çalışır)
# UptimeRobot ile app uyumaz, scheduler her 10 dk'da bir notify_scheduled.main() çağırır
try:
    from streamlit_scheduler import start_scheduler
    start_scheduler()
except Exception as _e:
    pass

import signals_full as sig_full
from backtest import run_backtest
import ott_tott_confirm as otc   # OTT+TOTT sıralı teyit (Kokpit/scan/scalp ortak kullanır)
from data_source import fetch as ds_fetch
try:
    from data_source import fetch_futures as ds_fetch_futures
except ImportError:
    # Eski/cache'lenmiş data_source modülüne karşı güvenli düşüş → futures özelliği
    # devre dışı kalır ama dashboard çökmez (spot çalışmaya devam eder).
    def ds_fetch_futures(*_a, **_k):
        import pandas as _pd
        return _pd.DataFrame()


def bars_to_duration(bars: float, interval: str, category: str = "") -> str:
    """Bar sayısını insan-okunabilir süreye çevir.
    Hisse/BIST için işgünü 7-8 saat, crypto 7/24."""
    if not bars or bars <= 0:
        return "—"
    # Bar süresi (saat cinsinden)
    bar_h = {"1m":1/60, "5m":5/60, "15m":0.25, "30m":0.5,
             "1h":1.0, "4h":4.0, "1d":24.0}.get(interval, 1.0)
    total_h = bars * bar_h
    if category == "CRYPTO":
        # 7/24
        days = total_h / 24
        if days < 1: return f"{total_h:.1f} sa"
        if days < 7: return f"{days:.1f} gün"
        return f"{days/7:.1f} hafta"
    # Hisse/Forex — işgünü (7 saat)
    workdays = total_h / 7
    if workdays < 1: return f"{total_h:.1f} sa"
    if workdays < 7: return f"{workdays:.1f} işgünü"
    if workdays < 30: return f"{workdays/5:.1f} hafta"
    return f"{workdays/22:.1f} ay"


st.set_page_config(
    page_title="OTT Bot Dashboard",
    page_icon="static/favicon.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── PWA — manifest + iOS/Android meta tag'lerini parent document'a enjekte et
import streamlit.components.v1 as components
components.html("""
<script>
(function() {
    const head = parent.document.head;
    if (!head) return;
    if (head.querySelector('link[rel="manifest"]')) return;
    const adds = [
        ['link', {rel:'manifest', href:'./app/static/manifest.json'}],
        ['link', {rel:'apple-touch-icon', sizes:'192x192', href:'./app/static/icon-192.png'}],
        ['link', {rel:'apple-touch-icon', sizes:'512x512', href:'./app/static/icon-512.png'}],
        ['link', {rel:'icon', sizes:'192x192', href:'./app/static/icon-192.png'}],
        ['meta', {name:'theme-color', content:'#26a69a'}],
        ['meta', {name:'apple-mobile-web-app-capable', content:'yes'}],
        ['meta', {name:'apple-mobile-web-app-status-bar-style', content:'black-translucent'}],
        ['meta', {name:'apple-mobile-web-app-title', content:'OTT Bot'}],
        ['meta', {name:'mobile-web-app-capable', content:'yes'}],
    ];
    for (const [tag, attrs] of adds) {
        const el = parent.document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
        head.appendChild(el);
    }
    // Service Worker kaydı (PWA + push)
    if ('serviceWorker' in parent.navigator) {
        parent.navigator.serviceWorker.register('/app/static/service-worker.js')
            .then(reg => console.log('[OTT] Service Worker kayıtlı'))
            .catch(err => console.log('[OTT] SW kayıt hatası:', err));
    }
})();
</script>
""", height=0)

# ──────────────────────────────────────────────────────────────────
#  CUSTOM CSS — TradingView tarzı tema
# ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Genel tema */
    .stApp {
        background: linear-gradient(180deg, #0d1117 0%, #131722 100%);
    }

    /* Ana başlık alanı */
    .main-header {
        background: linear-gradient(135deg, #1a1f2e 0%, #232938 100%);
        padding: 24px 28px;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 1px solid #2a2e39;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .main-header h1 {
        margin: 0;
        font-size: 32px;
        font-weight: 700;
        background: linear-gradient(90deg, #26a69a 0%, #2962ff 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .main-header .subtitle {
        color: #888;
        margin-top: 4px;
        font-size: 14px;
    }
    .main-header .badge {
        display: inline-block;
        padding: 4px 10px;
        background: #26a69a22;
        color: #26a69a;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 8px;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: #1a1f2e;
        padding: 4px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 500;
        transition: all 0.2s;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #232938;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2962ff 0%, #1e88e5 100%) !important;
        color: white !important;
    }

    /* Metric kartları */
    [data-testid="stMetric"] {
        background: #1a1f2e;
        padding: 14px;
        border-radius: 8px;
        border: 1px solid #2a2e39;
        transition: all 0.2s;
    }
    [data-testid="stMetric"]:hover {
        border-color: #2962ff;
        transform: translateY(-1px);
    }
    [data-testid="stMetricLabel"] {
        color: #888 !important;
        font-size: 12px !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    [data-testid="stMetricValue"] {
        font-size: 24px !important;
        font-weight: 700 !important;
        color: #d1d4dc !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 13px !important;
    }

    /* Butonlar */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s;
        border: 1px solid transparent;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #2962ff 0%, #1e88e5 100%);
        border: none;
    }
    .stButton button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(41,98,255,0.4);
    }

    /* Dataframe styling */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #2a2e39;
    }

    /* Slider */
    .stSlider [data-baseweb="slider"] {
        margin-top: 8px;
    }

    /* Expander */
    .streamlit-expanderHeader {
        background: #1a1f2e !important;
        border-radius: 8px !important;
        font-weight: 600;
    }

    /* Info / Warning / Error / Success boxes */
    .stAlert {
        border-radius: 8px;
        border-left-width: 4px;
    }

    /* Number input + selectbox */
    .stNumberInput input, .stSelectbox > div > div {
        background: #1a1f2e !important;
        border-color: #2a2e39 !important;
        border-radius: 6px !important;
    }

    /* Footer alanı */
    .footer-bar {
        margin-top: 40px;
        padding: 16px;
        text-align: center;
        color: #666;
        font-size: 12px;
        border-top: 1px solid #2a2e39;
    }

    /* Loading spinner overrides */
    .stSpinner > div {
        border-top-color: #2962ff !important;
    }

    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, #26a69a 0%, #2962ff 100%);
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: #131722; }
    ::-webkit-scrollbar-thumb { background: #2a2e39; border-radius: 5px; }
    ::-webkit-scrollbar-thumb:hover { background: #485158; }

    /* Section divider */
    hr { border-color: #2a2e39 !important; }

    /* Hide streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)

# ── Sembol evreni — tam NASDAQ 100 + genişletilmiş BIST
# NASDAQ kategorisi = GCM Forex'te işlem gören hisseler (Türkiye'den erişilebilir CFD'ler)
# Forex/emtia/endeks/bond hariç. STOCK_US + STOCK_OTHER + STOCK_EU_UK birleşimi.
def _load_gcm_stocks():
    """gcm_symbols.json + gcm_to_yf_map.json'dan sadece hisseleri çek (yfinance ticker)."""
    try:
        import json
        with open("gcm_symbols.json", encoding="utf-8") as f:
            cats = json.load(f).get("categorized", {})
        with open("gcm_to_yf_map.json", encoding="utf-8") as f:
            mp = json.load(f)["mapping"]
        stock_keys = (cats.get("STOCK_US", []) +
                       cats.get("STOCK_OTHER", []) +
                       cats.get("STOCK_EU_UK", []))
        tickers = [mp[s] for s in stock_keys if s in mp]
        return sorted(set(tickers))
    except Exception:
        return None


_gcm_stocks = _load_gcm_stocks()
NASDAQ = _gcm_stocks if _gcm_stocks else [
    # Fallback (gcm_symbols.json yoksa)
    "AAPL","MSFT","AMZN","NVDA","GOOG","GOOGL","META","AVGO","TSLA","COST",
    "NFLX","AMD","PEP","ADBE","CSCO","INTC","INTU","CMCSA","AMGN",
    "QCOM","TXN","HON","BKNG","AMAT","ISRG","GILD","ADP","MU","ADI",
    "MDLZ","SBUX","REGN","VRTX","LRCX","KLAC","PANW","SNPS","PYPL","CDNS",
]
BIST = [
    # VIOP'ta vadeli işlem gören 45 hisse (kullanıcı doğruladı — gerçek işlem evreni)
    "AKBNK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","DOHOL.IS","ENJSA.IS",
    "EKGYO.IS","ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","GUBRF.IS",
    "HALKB.IS","ISCTR.IS","KCHOL.IS","KRDMD.IS","MGROS.IS","OYAKC.IS",
    "PETKM.IS","PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TOASO.IS","TKFEN.IS","TSKB.IS",
    "TTKOM.IS","TUPRS.IS","VAKBN.IS","VESTL.IS","YKBNK.IS","AEFES.IS",
    "HEKTS.IS","ODAS.IS","ASTOR.IS","AKSEN.IS","ALARK.IS","KONTR.IS",
    "DOAS.IS","CIMSA.IS","ULKER.IS",
]
COMMODITY = ["GC=F", "SI=F"]
# Emtia + Forex (GCM Forex enstrümanları) — ayrı sekme
EMTIA_FX = ["GC=F", "SI=F", "PA=F", "EURUSD=X", "GBPUSD=X"]
EMTIA_FX_ADI = {"GC=F": "GOLD (Altın)", "SI=F": "Silver (Gümüş)",
                "PA=F": "Palladium", "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD"}

# GCM Forex'te CFD olarak işlem gören US hisseler (yfinance formatında)
# Kaynak: extract_gcm_symbols.py + gcm_ticker_map.py (MT4 history klasöründen gerçek)
# 424 GCM sembolünün %99.1'i mapped → 420 ticker
def _load_gcm_set():
    """gcm_to_yf_map.json varsa oradan oku, yoksa fallback (50 popüler)."""
    try:
        import json
        with open("gcm_to_yf_map.json", encoding="utf-8") as f:
            d = json.load(f)
        return set(d["mapping"].values())
    except Exception:
        # Fallback — JSON yoksa
        return {
            "AAPL", "MSFT", "AMZN", "GOOG", "GOOGL", "META", "NVDA", "TSLA",
            "AMD", "INTC", "NFLX", "ADBE", "ORCL", "CSCO", "PYPL", "IBM",
            "JPM", "BAC", "WFC", "C", "GS", "MS", "V", "MA",
            "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY",
            "WMT", "COST", "KO", "PEP", "MCD", "SBUX", "NKE",
            "DIS", "T", "VZ", "CMCSA",
            "BA", "GE", "F", "GM", "CAT", "MMM",
            "XOM", "CVX", "HD", "PG",
            "RIOT", "COIN", "PLTR", "GME", "AMC",
        }


GCM_NASDAQ = _load_gcm_set()

CRYPTO = [
    # Top market cap
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "TRX-USD", "AVAX-USD", "DOT-USD",
    # Mid cap layer-1 / DeFi
    "LINK-USD", "MATIC-USD", "LTC-USD", "BCH-USD", "UNI-USD",
    "ATOM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD", "FIL-USD",
    # Yeni nesil / L2
    "APT-USD", "ARB-USD", "OP-USD", "SUI-USD", "INJ-USD",
    "HBAR-USD", "IMX-USD", "RNDR-USD", "TIA-USD", "SEI-USD",
]

PARAMS = dict(
    trend_length=20, trend_percent=8.0, minor_percent=4.0,
    tott_percent=1.0, tott_coeff=0.0004,
    sott_period_k=300, sott_smooth_k=200, sott_percent=0.2,
    gate_length=10, gate_percent=0.4, gate_shift=0,
    rott_x1=30, rott_x2=1000, rott_percent=7.0,
)


@st.cache_data(ttl=300)  # 5 dk cache
def fetch_yf(symbol, period="60d", interval="5m", n_bars=5000):
    """
    TradingView (varsayılan) veya yfinance fallback. data_source.fetch sarmalayıcısı.
    Eski isim 'fetch_yf' geriye uyumluluk için tutuldu.
    """
    df = ds_fetch(symbol, interval=interval, n_bars=n_bars)
    if df.empty: return df
    keep = [c for c in ["open","high","low","close"] if c in df.columns]
    return df[keep].dropna()


@st.cache_data(ttl=120, show_spinner=False)
def fetch_fut_cached(symbol, interval="15m", n_bars=2000):
    """Önbellekli futures fetch (120 sn). Tarama/Kokpit hızı için: tekrar tarama
    cache'ten anında gelir. n_bars=2000 → OTT(40)+TOTT için fazlasıyla yeter,
    5000'den ~2.5x hızlı. BIST değilse spot'a düşer."""
    if symbol.upper().endswith(".IS"):
        d = ds_fetch_futures(symbol, interval=interval, n_bars=n_bars)
        if d is not None and not d.empty:
            return d
    return fetch_yf(symbol, interval=interval, n_bars=n_bars)


@st.cache_data(ttl=45, show_spinner=False)  # 45 sn — açık pozisyon canlı fiyatı için
def live_price(symbol):
    """Sadece son (anlık) fiyat — hafif ve taze (45 sn cache).
    Açık pozisyon yüzen P&L'i için; tam sinyal hesabı yapmaz."""
    from data_source import best_interval_for
    try:
        df = ds_fetch(symbol, interval=best_interval_for(symbol), n_bars=60)
        if df.empty: return None
        return float(df["close"].iloc[-1])
    except Exception:
        return None


# Per-symbol params cache (uygulama başlangıcında okunur, hızlı erişim)
@st.cache_data(ttl=60)
@st.cache_data(ttl=3600, show_spinner=False)
def _load_per_sym():
    """Grid (FY) optimize JSON — 1 saat cache."""
    import os, json
    if not os.path.exists("per_symbol_params.json"):
        return {}
    with open("per_symbol_params.json") as f:
        return json.load(f)


@st.cache_data(ttl=3600, show_spinner=False)
def _load_bayes_sym():
    """Bayes optimize JSON — 1 saat cache."""
    import os, json
    if not os.path.exists("per_symbol_params_bayes.json"):
        return {}
    with open("per_symbol_params_bayes.json") as f:
        return json.load(f)


def _is_uyumsuz(sym):
    """Kullanıcı 'her şey gözüksün' dedi → hiçbir sembol gizlenmez.
    Rating filtresi kaldırıldı; asıl değerlendirme Canlı Performans'ta yapılır."""
    return False


def _is_shown(sym):
    return True


def _sup_res(df, n=120):
    """Anlık destek/direnç — son n barın en düşük/en yüksek değeri (faktüel seviye,
    tahmin değil). Direnç = yakın zirve, Destek = yakın dip."""
    try:
        if df is None or df.empty:
            return None, None
        w = df.tail(n)
        lo = float(w["low"].min()) if "low" in w else float(w["close"].min())
        hi = float(w["high"].max()) if "high" in w else float(w["close"].max())
        return lo, hi
    except Exception:
        return None, None


def analyze_intraday(symbol, interval: str | None = None, warn_threshold_pct: float = 1.0):
    """interval=None → kategoriye göre otomatik (CRYPTO=30m, diğer=1h)
    warn_threshold_pct: 'ÇIK YAKIN' uyarısı eşiği (%) — fiyat trail stop'a bu kadar yakınsa uyar.
    Sabit %1.0 (slider kaldırıldı)."""
    if interval is None:
        from data_source import best_interval_for
        interval = best_interval_for(symbol)
    df = fetch_yf(symbol, interval=interval)
    if df.empty or len(df) < 1500:
        return None
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **PARAMS)
    # Sinyal = son KAPANMIŞ bar (iloc[-2]). iloc[-1] piyasa açıkken oluşan/eksik mum,
    # backtest kapanmış bar varsayar → tutarlılık için -2. Fiyat ise canlı (-1).
    last = s.iloc[-2] if len(s) >= 2 else s.iloc[-1]
    cur = float(df["close"].iloc[-1])

    if last["cond_buy_long"]:        pos = "🟢 LONG AÇ"
    elif last["cond_buy_short"]:     pos = "🔴 SHORT AÇ"
    elif last["cond_exit_long"]:     pos = "🟡 LONG'tan ÇIK"
    elif last["cond_exit_short"]:    pos = "🟡 SHORT'tan ÇIK"
    elif last["major_up"] and last["zone_up"]:  pos = "🟢 LONG'ta TUT"
    elif last["major_dn"] and last["zone_dn"]:  pos = "🔴 SHORT'ta TUT"
    elif last["major_up"]:           pos = "⏳ LONG bekle"
    elif last["major_dn"]:           pos = "⏳ SHORT bekle"
    else:                            pos = "❓ Belirsiz"

    # ── Erken ÇIK uyarısı: mum kapanışı beklenmeden,
    #    fiyat trail stop'a (karşı TOTT tetiği) yaklaştığında uyar.
    #    warn_threshold_pct parametresinden geçer (dashboard slider ile ayarlanır).
    if "LONG'ta TUT" in pos and not pd.isna(last["tott_dn"]):
        # LONG: trail stop = TOTT_dn (aşağıda). Fiyat ne kadar yakın?
        dist_pct = (cur / float(last["tott_dn"]) - 1) * 100
        if 0 < dist_pct < warn_threshold_pct:
            pos = f"{pos}  ⚠️ ÇIK YAKIN ({dist_pct:.2f}%)"
    elif "SHORT'ta TUT" in pos and not pd.isna(last["tott_up"]):
        # SHORT: trail stop = TOTT_up (yukarıda). Fiyat ne kadar yakın?
        dist_pct = (float(last["tott_up"]) / cur - 1) * 100
        if 0 < dist_pct < warn_threshold_pct:
            pos = f"{pos}  ⚠️ ÇIK YAKIN ({dist_pct:.2f}%)"

    # ── Güvenilirlik (per_symbol_params.json'dan)
    psy = _load_per_sym()
    bt = psy.get(symbol)
    if bt and bt.get("ok"):
        rt = bt.get("rating", "?")
        stx = bt["stats"]
        guven_emoji = {
            "MÜKEMMEL": "🏆", "İYİ": "⭐", "ORTA": "🟢",
            "MARJINAL": "🟡", "VERİ_AZ": "⚠️", "UYUMSUZ": "❌",
        }.get(rt, "❓")
        guven_label = f"{guven_emoji} {rt}"
        guven_score = {
            "MÜKEMMEL": 100, "İYİ": 80, "ORTA": 60,
            "MARJINAL": 40, "VERİ_AZ": 25, "UYUMSUZ": 0,
        }.get(rt, 0)
        bt_ret = stx["return"] * 100
        bt_pf = stx["pf"] if stx["pf"] else 999
        bt_win = stx["win_rate"] * 100
        bt_n = stx["n_trades"]
    else:
        guven_label = "❓ Bilinmiyor"
        guven_score = 0
        bt_ret = bt_pf = bt_win = None
        bt_n = 0

    from data_source import category_of as _cat
    _dest, _diren = _sup_res(df)   # anlık destek/direnç (son 120 bar)
    return {
        "Sembol": symbol,
        "Kategori": _cat(symbol),
        "Güven": guven_label,
        "_GuvenSkor": guven_score,
        "Durum": pos,
        "Fiyat": cur,
        "Direnç": _diren,
        "Destek": _dest,
        "Trend OTT": float(last["trend_ott"]) if not pd.isna(last["trend_ott"]) else None,
        "Tetik ↑": float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None,
        "Tetik ↓": float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None,
        "Up %": (float(last["tott_up"])/cur - 1)*100 if not pd.isna(last["tott_up"]) else None,
        "Dn %": (float(last["tott_dn"])/cur - 1)*100 if not pd.isna(last["tott_dn"]) else None,
        "BT Getiri %": bt_ret,
        "BT PF": bt_pf,
        "BT Win %": bt_win,
        "BT Trade": bt_n,
        "_df": df, "_signals": s,
    }


def analyze_backtest(symbol, days=30, leverage=10):
    df = fetch_yf(symbol, "60d", "5m")
    if df.empty or len(df) < 2000: return None
    s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **PARAMS)
    res = run_backtest(
        df[["open","high","low","close"]],
        s["cond_buy_long"], s["cond_exit_long"],
        s["cond_buy_short"], s["cond_exit_short"],
    )
    cutoff = df.index[-1] - pd.Timedelta(days=days)
    trades = [t for t in res.trades if t.exit_price is not None and t.exit_time >= cutoff]
    eq = 1000  # 1000$ baz
    margin_call = False
    for t in trades:
        lev_pnl = t.pnl_pct * leverage
        if lev_pnl <= -1.0:
            margin_call = True; eq = 0; break
        eq *= (1 + lev_pnl)
    return {
        "Sembol": symbol,
        "Trade": len(trades),
        "Final": eq,
        "Getiri %": (eq/1000 - 1)*100,
        "Margin Call": margin_call,
        "Trades": trades,
    }


# ──────────────────────────────────────────────────────────────────
#  HEADER — Custom design
# ──────────────────────────────────────────────────────────────────
# Sistem durumu için hızlı sayım (cache'li yükleme)
_iyi = 0; _uyumsuz = 0; _total = 0
try:
    _psy = _load_per_sym()
    if _psy:
        _total = len(_psy)
        for _s, _r in _psy.items():
            if _r.get("ok"):
                _rt = _r.get("rating", "?")
                if _rt in ("MÜKEMMEL", "İYİ", "ORTA"):
                    _iyi += 1
                elif _rt == "UYUMSUZ":
                    _uyumsuz += 1
except Exception:
    pass

st.markdown(f"""
<div class="main-header">
    <h1>📊 OTT Bot Dashboard</h1>
    <div class="subtitle">
        <b>OTT-ailesi</b> · TOTT + SOTT + HOTT/LOTT + ROTT
    </div>
    <div style="margin-top:14px;">
        <span class="badge">📡 {_total} sembol</span>
        <span class="badge" style="background:#26a69a22;color:#26a69a;">★ {_iyi} işe yarayan</span>
        <span class="badge" style="background:#ef535022;color:#ef5350;">✗ {_uyumsuz} uyumsuz</span>
        <span class="badge" style="background:#2962ff22;color:#2962ff;">🤖 Auto-update AÇIK</span>
    </div>
</div>
""", unsafe_allow_html=True)

(tab_kokpit, tab_kanit, tab_portfolio, tab_tarayici,
 tab_emtia, tab_crypto, tab_otttott, tab_scalp, tab_live, tab_info) = st.tabs([
    "🎯  Kokpit",
    "🏆  Kanıtlanmış Sistem",
    "💼  Portföyüm",
    "🔎  Tarayıcı",
    "🥇  Emtia/Forex",
    "🪙  Crypto (4h)",
    "🔗  OTT+TOTT Teyit",
    "⚡  Aktif/Scalp (15m)",
    "✅  Canlı Performans",
    "📖  Bilgi",
])
# 3 tarama sekmesi tek "Tarayıcı" altında alt-sekme (sadeleştirme). Aşağıdaki
# `with tab_consensus/tab_scan/tab_sim:` blokları artık burada nested render olur.
tab_consensus, tab_scan, tab_sim, tab_heat = tab_tarayici.tabs([
    "🤝  Konsensüs", "📡  Anlık Tarayıcı", "📌  Öneriler", "🗺️  Isı Haritası",
])

# ──────────────────────────────────────────────────────────────────
#  TAB: KANITLANMIŞ SİSTEM — M60 long-only + nakit (SuperTrend)
#  Walk-forward (8/8 OOS+) + Monte Carlo (medyan +247%) ile DOĞRULANDI.
# ──────────────────────────────────────────────────────────────────
with tab_kanit:
    import longonly_strategy as lo
    st.subheader("🏆 Kanıtlanmış Sistem — M60 Long-only + Nakit")
    st.caption("Walk-forward (8/8 OOS pozitif, drawdown al-tut'tan düşük) + Monte Carlo "
               "(medyan +247%, iflas %10.6) ile **doğrulanan** tek sistem. SuperTrend, **short YOK**.")

    with st.expander("📋 Kurallar — okumadan işlem açma", expanded=False):
        st.markdown(
            "- **LONG:** SuperTrend (M60) yukarı → futures'ta long aç / tut.\n"
            "- **NAKİT:** yön aşağı dönerse → **pozisyonu kapat, nakitte bekle** (short açma).\n"
            "- **Kaldıraç:** efektif **max 2×** — toplam notional ≤ 2× hesap. **1:7 = %72 iflas riski.**\n"
            "  - 50K hesap → toplam pozisyon ≤ ~100K notional (≈10K teminat).\n"
            "- **Stop:** SuperTrend çizgisi doğal takip-stopu; ayrıca sıkı stop **koyma** (edge'i keser).\n"
            "- **Ay sonu:** VIOP kontratı biter — çık ya da gelecek vadeye roll et.\n"
            "- **Short:** rejim-kapılı bile test edildi, değer katmadı → kapalı. Ayı piyasası kanıtlanırsa açılır."
        )

    if st.button("🔍 BIST'i tara (kanıtlanmış sistem)", key="kanit_scan", type="primary"):
        rows = []
        prog = st.progress(0.0)
        bist_syms = [s for s in BIST]
        for i, sym in enumerate(bist_syms):
            prog.progress((i + 1) / len(bist_syms))
            try:
                df = fetch_fut_cached(sym, "1h", n_bars=1500)
                stt = lo.current_state(df)
                if not stt:
                    continue
                _dt = stt.get("donus_tarih")
                rows.append({
                    "Sembol": sym.replace(".IS", ""),
                    "Durum": stt["pozisyon"],
                    "Tazelik": stt.get("tazelik", ""),
                    "Sinyal Tarihi": _dt.strftime("%d %b %H:%M") if _dt is not None else "-",
                    "Sinyal Fiyatı": round(stt["donus_fiyat"], 2) if stt.get("donus_fiyat") else None,
                    "Fiyat": round(stt["anlik"], 2),
                    "Sinyalden %": round((stt["anlik"] / stt["donus_fiyat"] - 1) * 100, 1)
                                    if stt.get("donus_fiyat") else None,
                    "Stop (SuperT)": round(stt["cizgi"], 2),
                    "Tampon %": round(stt["tampon"], 1) if stt["tampon"] is not None else None,
                    "Bar": stt["bars"],
                })
            except Exception:
                continue
        prog.empty()
        if rows:
            import pandas as _pd
            dfr = _pd.DataFrame(rows)
            longs = dfr[dfr["Durum"] == "LONG"].sort_values("Bar")
            cash = dfr[dfr["Durum"] == "NAKİT"]
            st.session_state["kanit_longs"] = longs
            st.session_state["kanit_cash"] = cash

    if "kanit_longs" in st.session_state:
        longs = st.session_state["kanit_longs"]; cash = st.session_state["kanit_cash"]
        c1, c2 = st.columns(2)
        c1.metric("🟢 LONG (tutulan/alınabilir)", len(longs))
        c2.metric("⚪ NAKİT (uzak dur)", len(cash))
        st.markdown("#### 🟢 LONG sembolleri — sistem yukarı diyor (en taze en üstte)")
        st.caption("🟢 TAZE (~1 gün) = trene yeni bin · 🟡 yeni (1-3 gün) · 🔴 olgun = trene GEÇ kaldın, dikkat. "
                   "'Sinyalden %' = sinyal gününden bu yana ne kadar kaçırdın (büyükse geç kaldın).")
        st.dataframe(longs, use_container_width=True, hide_index=True)
        with st.expander(f"⚪ NAKİT sembolleri ({len(cash)}) — sistem aşağı, girme"):
            st.dataframe(cash, use_container_width=True, hide_index=True)
    else:
        st.info("Yukarıdaki butona bas → BIST'i kanıtlanmış sistemle tarar, LONG ve NAKİT sembollerini ayırır.")


# ──────────────────────────────────────────────────────────────────
#  TAB: KOKPİT — açık pozisyon + izleme listesi, canlı yön + çıkış seviyesi
# ──────────────────────────────────────────────────────────────────
with tab_kokpit:
    st.subheader("🎯 Kokpit — Canlı Yön + Çıkış Seviyesi")
    st.caption("Açık pozisyon ve izleme sembollerinin **güncel OTT+TOTT yönü ve çıkış çizgisi** tek ekranda. "
                "Seviyeler her barla kayar; burada hep tazesi gösterilir. (BIST → futures, Pine param)")


    # Otomatik yenileme
    _kc1, _kc2 = st.columns([1, 3])
    with _kc1:
        _k_auto = st.toggle("🔄 Otomatik yenile", value=False, key="kokpit_auto")
    with _kc2:
        _k_sec = st.select_slider("Aralık (sn)", options=[30, 60, 120, 300], value=60,
                                   key="kokpit_sec", disabled=not _k_auto)
    if _k_auto:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=_k_sec * 1000, key="kokpit_tick")
        except Exception:
            pass

    _k_tf = st.radio("Zaman dilimi", ["15m", "1h"], horizontal=True, key="kokpit_tf",
                      help="Çıkış seviyesi bu TF'in OTT/TOTT'undan hesaplanır")

    # İzleme listesi: açık pozisyonlar + kullanıcının seçtikleri
    try:
        import forward_validation as _fv
        _open_syms = list(_fv.open_positions().keys())
    except Exception:
        _open_syms = []
    _bist_opts = [s for s in BIST]
    # Kalıcı favoriler — favorites.json'dan yükle (yoksa varsayılan çekirdek)
    import os as _os2, json as _json2
    _FAV_FILE = "favorites.json"
    try:
        _favs = _json2.load(open(_FAV_FILE, encoding="utf-8")) if _os2.path.exists(_FAV_FILE) else []
    except Exception:
        _favs = []
    _def_watch = _favs if _favs else [s for s in ["AKBNK.IS", "GARAN.IS", "ASELS.IS", "THYAO.IS"] if s in _bist_opts]
    _watch = st.multiselect("İzleme listesi (favoriler)", _bist_opts,
                             default=sorted(set(_def_watch) | set(s for s in _open_syms if s.endswith(".IS"))),
                             key="kokpit_watch")
    if st.button("💾 Bu listeyi favori olarak kaydet", key="kokpit_savefav"):
        try:
            _json2.dump(_watch, open(_FAV_FILE, "w", encoding="utf-8"), ensure_ascii=False)
            st.success(f"{len(_watch)} sembol favorilere kaydedildi — bir dahaki açılışta hazır.")
        except Exception as _e:
            st.error(f"Kaydedilemedi: {_e}")

    _kgrid = _load_per_sym()   # futures-optimize params (botun kullandığı)
    from data_source import best_interval_for as _kbif

    def _kokpit_row(sym, tf):
        """Canlı yön + çıkış — BOT ile AYNI: full sistem (signals_full) + optimize param.
        Botun gerçek interval'i (BIST=1h) kullanılır ki dashboard = botun yaptığı."""
        p = _kgrid.get(sym, {}).get("params")
        if not p:
            return None  # optimize param yok (örn TKFEN) → atla
        d = fetch_fut_cached(sym, _kbif(sym), 2000)
        if d is None or d.empty or len(d) < 300:
            return None
        p = {**p}
        p.setdefault("rott_x1", 30); p.setdefault("rott_x2", 1000); p.setdefault("rott_percent", 7.0)
        s = sig_full.build_signals_full(d["close"], d["high"], d["low"], **p)
        last = s.iloc[-2] if len(s) >= 2 else s.iloc[-1]   # son KAPANMIŞ bar
        cur = float(d["close"].iloc[-1])
        # GERÇEK pozisyon — sinyal akışından (backtest mantığı): AÇ→pozisyon, ÇIK→flat.
        # major_up/dn TEK BAŞINA pozisyon DEĞİL (sadece eğilim/BEKLE) → yanlış SHORT'u önler.
        bl = s["cond_buy_long"].values; xl = s["cond_exit_long"].values
        bs = s["cond_buy_short"].values; xs = s["cond_exit_short"].values
        pos = 0
        for i in range(len(s) - 1):   # sadece KAPANMIŞ barlar (oluşan bar hariç)
            if bl[i]: pos = 1
            elif bs[i]: pos = -1
            elif pos == 1 and xl[i]: pos = 0
            elif pos == -1 and xs[i]: pos = 0
        yon = "LONG" if pos == 1 else ("SHORT" if pos == -1 else None)
        tup = float(last["tott_up"]); tdn = float(last["tott_dn"]); ott = float(last["trend_ott"])
        # Çıkış/stop = botun stopu: LONG→TOTT alt, SHORT→TOTT üst
        cikis = tdn if yon == "LONG" else (tup if yon == "SHORT" else ott)
        if yon == "LONG":
            tampon = (cur / cikis - 1) * 100
        elif yon == "SHORT":
            tampon = (cikis / cur - 1) * 100
        else:
            tampon = None
        return {
            "Sembol": sym.replace(".IS", "1!") if sym.endswith(".IS") else sym,
            "Yön": "🟢 LONG" if yon == "LONG" else ("🔴 SHORT" if yon == "SHORT" else "—"),
            "Anlık": cur,
            "Çıkış (stop)": cikis,
            "Tampon %": round(tampon, 1) if tampon is not None else None,
            "TOTT alt": tdn, "TOTT üst": tup, "OTT": ott,
        }

    if not _watch:
        st.info("👆 İzlemek istediğin sembolleri seç (açık pozisyonların otomatik eklenir).")
    else:
        rows = []; _errs = []
        prog = st.progress(0, text="0")
        for i, sym in enumerate(_watch):
            try:
                rr = _kokpit_row(sym, _k_tf)
                if rr:
                    rows.append(rr)
                else:
                    _errs.append(f"{sym}: veri boş/yetersiz")
            except Exception as _e:
                _errs.append(f"{sym}: {type(_e).__name__}: {_e}")
            prog.progress((i+1)/len(_watch), text=f"{i+1}/{len(_watch)} {sym}")
        prog.empty()
        if rows:
            dfk = pd.DataFrame(rows)
            st.dataframe(
                dfk.style.format({
                    "Anlık": "{:.2f}", "Çıkış (stop)": "{:.2f}", "Tampon %": "{:+.1f}%",
                    "TOTT alt": "{:.2f}", "TOTT üst": "{:.2f}", "OTT": "{:.2f}",
                }).background_gradient(subset=["Tampon %"], cmap="RdYlGn", vmin=-3, vmax=8),
                use_container_width=True, hide_index=True,
                column_config={
                    "Çıkış (stop)": st.column_config.NumberColumn("Çıkış / Stop",
                        help="Botun gerçek stopu: LONG→TOTT alt, SHORT→TOTT üst. Kapanış bunu kırarsa çıkış."),
                    "Tampon %": st.column_config.NumberColumn("Tampon %",
                        help="Fiyatın stop'a uzaklığı. Küçük=çıkışa yakın, büyük=rahat"),
                })
            now_tr = pd.Timestamp.now(tz="Europe/Istanbul")
            st.caption(f"⏱️ {now_tr:%d/%m %H:%M:%S} TR · **Tam sistem (bot ile aynı)**, "
                        f"{_kbif('AKBNK.IS')} · futures + optimize param. Çıkış/stop = botun gerçek seviyesi "
                        "(Konsensüs 'Stop' ile aynı). Kapanış stop'u kırarsa çıkış.")
        else:
            st.warning("Veri çekilemedi.")
            # Kendi kendine teşhis: TV login durumu + ilk gerçek hata
            import os as _os
            _tvuser = _os.getenv("TV_USERNAME")
            try:
                import data_source as _ds
                _tv_ok = _ds._get_tv() is not None
            except Exception:
                _tv_ok = False
            st.caption(f"🔎 Teşhis — TV_USERNAME secret: {'✅ var' if _tvuser else '❌ YOK'} · "
                        f"tvDatafeed bağlantısı: {'✅' if _tv_ok else '❌'}")
            if _errs:
                with st.expander("Hata detayları"):
                    for _e in _errs[:10]:
                        st.text(_e)

    # ── KENDİ grafiğimiz (futures veri + OTT/TOTT bantları + sinyaller) — gerçekten çalışır
    st.markdown("#### 📈 Grafik (OTT+TOTT)")
    _chart_opts = _watch if _watch else _def_watch
    if _chart_opts:
        _csym = st.selectbox("Grafik sembolü", _chart_opts, key="kokpit_chart_sym")
        # Grafik bakmak için en iyi/bedava yer TradingView'in kendisi → tek tık link
        _tv_full = f"BIST:{_csym[:-3]}1!" if _csym.endswith(".IS") else _csym
        _tv_url = f"https://tr.tradingview.com/chart/?symbol={_tv_full.replace(':', '%3A')}"
        st.link_button("🔗 TradingView'da aç (canlı, tam grafik)", _tv_url, use_container_width=True)

        _pp = _kgrid.get(_csym, {}).get("params")
        _dch = fetch_fut_cached(_csym, _kbif(_csym), 2000) if _pp else None
        if not _pp:
            st.warning("Bu sembolün optimize parametresi yok (örn TKFEN).")
        elif _dch is None or _dch.empty or len(_dch) < 300:
            st.warning("Grafik verisi çekilemedi.")
        else:
            import numpy as _np
            _pp = {**_pp}; _pp.setdefault("rott_x1", 30); _pp.setdefault("rott_x2", 1000); _pp.setdefault("rott_percent", 7.0)
            _sf = sig_full.build_signals_full(_dch["close"], _dch["high"], _dch["low"], **_pp)
            _v = _sf.tail(200).reset_index(drop=True)
            _o = _dch.tail(200).reset_index(drop=True)
            _dts = _dch.tail(200).index
            _x = list(range(len(_o)))     # BİTİŞİK bar (boşluk yok)
            import plotly.graph_objects as _go
            fig = _go.Figure()
            _mav = _v["mavg"].values; _ottl = _v["trend_ott"].values
            _up = _mav >= _ottl
            # TOTT bulutu: MAvg–OTT arası, yeşil(yukarı)/kırmızı(aşağı)
            _gtop = _np.where(_up, _mav, _np.nan); _gbot = _np.where(_up, _ottl, _np.nan)
            _rtop = _np.where(~_up, _ottl, _np.nan); _rbot = _np.where(~_up, _mav, _np.nan)
            fig.add_trace(_go.Scatter(x=_x, y=_gbot, line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(_go.Scatter(x=_x, y=_gtop, fill="tonexty", fillcolor="rgba(38,166,154,0.22)",
                line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(_go.Scatter(x=_x, y=_rbot, line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(_go.Scatter(x=_x, y=_rtop, fill="tonexty", fillcolor="rgba(239,83,80,0.20)",
                line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(_go.Candlestick(x=_x, open=_o["open"], high=_o["high"],
                low=_o["low"], close=_o["close"], name="Fiyat",
                increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))
            fig.add_trace(_go.Scatter(x=_x, y=_v["mavg"], name="MAvg", line=dict(color="#26c6da", width=1.5)))
            fig.add_trace(_go.Scatter(x=_x, y=_v["trend_ott"], name="OTT", line=dict(color="#f5a623", width=1.6)))
            fig.add_trace(_go.Scatter(x=_x, y=_v["tott_up"], name="TOTT üst", line=dict(color="#ab47bc", width=1, dash="dot")))
            fig.add_trace(_go.Scatter(x=_x, y=_v["tott_dn"], name="TOTT alt", line=dict(color="#ab47bc", width=1, dash="dot")))
            # GERÇEK sistem sinyalleri: AL/SAT (cond_buy) + ÇIK (cond_exit)
            for _i in range(len(_v)):
                _row = _v.iloc[_i]
                if _row["cond_buy_long"]:
                    fig.add_trace(_go.Scatter(x=[_i], y=[_o["low"].iloc[_i]*0.99], mode="markers+text",
                        text=["AL"], textposition="bottom center", textfont=dict(size=10, color="#26a69a"),
                        marker=dict(symbol="triangle-up", size=13, color="#26a69a"), showlegend=False, hoverinfo="skip"))
                elif _row["cond_buy_short"]:
                    fig.add_trace(_go.Scatter(x=[_i], y=[_o["high"].iloc[_i]*1.01], mode="markers+text",
                        text=["SAT"], textposition="top center", textfont=dict(size=10, color="#ef5350"),
                        marker=dict(symbol="triangle-down", size=13, color="#ef5350"), showlegend=False, hoverinfo="skip"))
                elif _row["cond_exit_long"] or _row["cond_exit_short"]:
                    fig.add_trace(_go.Scatter(x=[_i], y=[_o["close"].iloc[_i]], mode="markers",
                        marker=dict(symbol="circle-open", size=9, color="#ffa726", line=dict(width=1.5)),
                        showlegend=False, hoverinfo="skip"))
            _step = max(1, len(_x)//8)
            _tickv = _x[::_step]; _tickt = [f"{_dts[j]:%d/%m %H:%M}" for j in _tickv]
            _ttl = _csym.replace(".IS", "1! (futures)") if _csym.endswith(".IS") else _csym
            fig.update_layout(height=560, title=f"{_ttl} · {_kbif(_csym)} · TAM SİSTEM",
                xaxis_rangeslider_visible=False, paper_bgcolor="#131722",
                plot_bgcolor="#131722", font=dict(color="#d1d4dc"),
                legend=dict(orientation="h", y=1.02, x=0))
            fig.update_xaxes(gridcolor="#2a2e39", tickvals=_tickv, ticktext=_tickt)
            fig.update_yaxes(gridcolor="#2a2e39")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📈 **Tam optimize sistem** (botun gerçek stratejisi, sembole özel param) — "
                        "tablo ile AYNI sistem. ▲AL ▼SAT (gerçek giriş), ○ çıkış. Sarı=OTT, mor=TOTT bandı. "
                        "TradingView linki (üstte) sadece görsel; karar bu sistemle.")

    # ── EKONOMİK TAKVİM (faiz/enflasyon/önemli olaylar) — haber günü farkındalığı
    with st.expander("📅 Ekonomik Takvim (TR + US + EU)", expanded=False):
        import streamlit.components.v1 as _comp
        _comp.html("""
        <div class="tradingview-widget-container">
          <div class="tradingview-widget-container__widget"></div>
          <script type="text/javascript"
            src="https://s3.tradingview.com/external-embedding/embed-widget-events.js" async>
          {"colorTheme":"dark","isTransparent":true,"locale":"tr",
           "countryFilter":"tr,us,eu","importanceFilter":"0,1","width":"100%","height":480}
          </script>
        </div>
        """, height=500)
        st.caption("⚠️ Yüksek önemli olay (faiz/enflasyon) gününde yeni pozisyon açarken dikkat — "
                    "gap/şok riski yüksek. Sistem zaten olay gününü bilir ama göz kararı da fayda.")


# ──────────────────────────────────────────────────────────────────
#  TAB: PORTFÖYÜM — kişisel pozisyon takibi
# ──────────────────────────────────────────────────────────────────
with tab_portfolio:
    st.subheader("💼 Portföyüm — Açık Pozisyonlarım")
    st.caption("Alım/satımlarını buraya işle. Bot her seferinde **anlık fiyat + bot sinyali + P&L** hesaplar.")

    PORTFOLIO_FILE = "portfolio.csv"
    PORT_COLS = ["Sembol", "Yön", "Giriş Tarihi", "Giriş Fiyatı", "Miktar",
                  "Stop Loss", "Take Profit", "Komisyon %", "Notlar", "Durum",
                  "Kapanış Tarihi", "Kapanış Fiyatı"]

    # Session state'te tut (Streamlit Cloud'da geçici, lokal'de CSV ile senkron)
    if "portfolio" not in st.session_state:
        try:
            st.session_state.portfolio = pd.read_csv(PORTFOLIO_FILE)
        except Exception:
            st.session_state.portfolio = pd.DataFrame(columns=PORT_COLS)

    # ── YENİ POZİSYON FORMU
    with st.expander("➕ Yeni pozisyon ekle", expanded=False):
        from datetime import datetime as _dt, date as _date
        # NASDAQ + BIST + COMMODITY + CRYPTO + GCM Forex (416 ticker)
        all_syms_full = sorted(set(NASDAQ + BIST + COMMODITY + CRYPTO + list(GCM_NASDAQ)))

        # Sembolün indikatör değerlerini çek (5 dk cache)
        # — TOTT_up + TOTT_dn = senin Pine indikatöründen tetik seviyeleri
        # — Stop = LONG için TOTT_dn, SHORT için TOTT_up (trail stop)
        @st.cache_data(ttl=300, show_spinner=False)
        def _sym_levels(sym):
            try:
                r = analyze_intraday(sym)
                if r:
                    return {
                        "price": r["Fiyat"],
                        "tott_up": r["Tetik ↑"],   # SHORT trail stop
                        "tott_dn": r["Tetik ↓"],   # LONG trail stop
                        "trend_ott": r["Trend OTT"],
                    }
            except Exception:
                pass
            return None

        # Sembol veya Yön değiştiğinde Giriş Fiyatı + Stop'u indikatörden doldur
        def _on_sym_change():
            sym = st.session_state["p_sym"]
            yon = st.session_state.get("p_yon", "LONG")
            lvl = _sym_levels(sym)
            if not lvl:
                return
            if lvl["price"] and lvl["price"] > 0:
                st.session_state["p_price"] = round(lvl["price"], 4)
            # Stop = TOTT karşı tetik (indikatörden — trail stop seviyesi)
            stop_val = lvl["tott_dn"] if yon == "LONG" else lvl["tott_up"]
            if stop_val and stop_val > 0:
                st.session_state["p_sl"] = round(stop_val, 4)
            # TP yok — sistem trend takipçi, sabit hedef indikatörden çıkmıyor

        # İlk açılışta default sembol için fiyat + stop'u indikatörden çek
        if "p_sym_initialized" not in st.session_state:
            initial_sym = all_syms_full[0] if all_syms_full else None
            if initial_sym:
                st.session_state["p_sym"] = initial_sym
                st.session_state.setdefault("p_yon", "LONG")
                lvl0 = _sym_levels(initial_sym)
                if lvl0:
                    st.session_state.setdefault("p_price", round(lvl0["price"], 4))
                    # LONG default → stop = TOTT_dn
                    sl0 = lvl0["tott_dn"]
                    st.session_state.setdefault("p_sl",
                                                  round(sl0, 4) if sl0 and sl0 > 0 else 0.0)
                else:
                    st.session_state.setdefault("p_price", 0.0)
                    st.session_state.setdefault("p_sl", 0.0)
                # TP boş — indikatörden çıkmıyor, sistem ÇIK sinyalini bekle
                st.session_state.setdefault("p_tp", 0.0)
            st.session_state["p_sym_initialized"] = True

        fp1, fp2, fp3 = st.columns(3)
        with fp1:
            new_sym = st.selectbox("Sembol", all_syms_full, key="p_sym",
                                     on_change=_on_sym_change,
                                     help="Sembol seçince Giriş Fiyatı (anlık) + "
                                            "Stop (TOTT karşı tetik) otomatik dolar.")
            new_yon = st.radio("Yön", ["LONG", "SHORT"], horizontal=True, key="p_yon",
                                 on_change=_on_sym_change,
                                 help="LONG → Stop=TOTT_dn  ·  SHORT → Stop=TOTT_up")
        with fp2:
            new_date = st.date_input("Giriş Tarihi", _date.today(), key="p_date")
            new_price = st.number_input("Giriş Fiyatı", min_value=0.0,
                                          step=0.01, format="%.4f", key="p_price",
                                          help="Sembol değişince anlık fiyat otomatik gelir.")
            new_qty = st.number_input("Miktar (lot/adet)", min_value=0.0, value=1.0,
                                        step=0.01, format="%.4f", key="p_qty")
        with fp3:
            new_sl = st.number_input("Stop Loss", min_value=0.0,
                                       step=0.01, format="%.4f", key="p_sl",
                                       help="Broker'a koyacağın koruyucu stop. "
                                            "Sistem indikatöründen çıkmaz, sen belirle (0 = yok).")
            new_tp = st.number_input("Take Profit", min_value=0.0,
                                       step=0.01, format="%.4f", key="p_tp",
                                       help="Sistem trend takipçi, sabit TP yok. "
                                            "0 bırakırsan sadece bot ÇIK sinyalini bekle.")
            new_comm = st.number_input("Komisyon %", min_value=0.0, value=0.05,
                                         step=0.01, format="%.3f", key="p_comm")
        new_notes = st.text_input("Notlar (opsiyonel)", key="p_notes")

        if st.button("✓ Pozisyonu ekle", type="primary", key="p_add"):
            new_row = pd.DataFrame([{
                "Sembol": new_sym, "Yön": new_yon,
                "Giriş Tarihi": new_date.isoformat(),
                "Giriş Fiyatı": new_price, "Miktar": new_qty,
                "Stop Loss": new_sl, "Take Profit": new_tp,
                "Komisyon %": new_comm, "Notlar": new_notes,
                "Durum": "Açık",
                "Kapanış Tarihi": "", "Kapanış Fiyatı": 0.0,
            }])
            st.session_state.portfolio = pd.concat(
                [st.session_state.portfolio, new_row], ignore_index=True)
            try:
                st.session_state.portfolio.to_csv(PORTFOLIO_FILE, index=False)
            except Exception:
                pass
            st.success(f"✓ {new_sym} {new_yon} pozisyonu eklendi")
            st.rerun()

    # ── GOOGLE SHEETS senkron
    try:
        from gsheets_storage import is_available as _gs_avail, \
                                    load_portfolio_sheets as _gs_load, \
                                    save_portfolio_sheets as _gs_save
        gs_active = _gs_avail()
    except Exception:
        gs_active = False
        _gs_load = _gs_save = None

    if gs_active:
        gs_c1, gs_c2, gs_c3 = st.columns([1, 1, 2])
        with gs_c1:
            if st.button("☁️ Google Sheets'ten yükle", use_container_width=True):
                gs_data = _gs_load()
                if gs_data is not None and len(gs_data) > 0:
                    st.session_state.portfolio = gs_data
                    try:
                        gs_data.to_csv(PORTFOLIO_FILE, index=False)
                    except Exception:
                        pass
                    st.success(f"✓ {len(gs_data)} pozisyon yüklendi")
                    st.rerun()
                else:
                    st.info("Google Sheets'te kayıt yok")
        with gs_c2:
            if st.button("☁️ Google Sheets'e kaydet", use_container_width=True):
                if _gs_save(st.session_state.portfolio):
                    st.success("✓ Google Sheets'e kaydedildi (kalıcı)")
                else:
                    try:
                        from gsheets_storage import get_last_error
                        err = get_last_error()
                    except Exception:
                        err = "bilinmeyen hata"
                    st.error(f"Kaydetme başarısız: {err}")
        with gs_c3:
            st.success("🟢 Google Sheets aktif — veri kalıcı")
    else:
        st.caption("💡 **Tip:** `gsheets_credentials.json` ekleyerek Google Sheets'le kalıcı kayıt yapabilirsin. Detay: `gsheets_storage.py`")

    # ── CSV İNDİR / YÜKLE
    fpc1, fpc2, fpc3 = st.columns([1, 1, 2])
    with fpc1:
        if len(st.session_state.portfolio) > 0:
            csv_data = st.session_state.portfolio.to_csv(index=False).encode("utf-8")
            st.download_button("📥 CSV indir", csv_data,
                                  file_name="portfolio.csv", mime="text/csv",
                                  use_container_width=True)
    with fpc2:
        up_csv = st.file_uploader("📤 CSV yükle", type="csv",
                                     key="p_upload", label_visibility="collapsed")
        if up_csv:
            try:
                st.session_state.portfolio = pd.read_csv(up_csv)
                try:
                    st.session_state.portfolio.to_csv(PORTFOLIO_FILE, index=False)
                except Exception:
                    pass
                st.success("CSV yüklendi")
            except Exception as e:
                st.error(f"Hata: {e}")
    with fpc3:
        if st.button("🗑️ Tüm pozisyonları sil", key="p_clear"):
            st.session_state.portfolio = pd.DataFrame(columns=PORT_COLS)
            try:
                pd.DataFrame(columns=PORT_COLS).to_csv(PORTFOLIO_FILE, index=False)
            except Exception:
                pass
            st.rerun()

    st.markdown("---")

    # ── AÇIK POZİSYONLAR + CANLI HESAPLAMA
    port_df = st.session_state.portfolio.copy()
    if len(port_df) == 0:
        st.info("📭 Henüz pozisyon yok. Yukarıdaki **➕ Yeni pozisyon ekle** ile başla.")
    else:
        open_df = port_df[port_df["Durum"] == "Açık"].reset_index()  # 'index' = orijinal indeks
        closed_df = port_df[port_df["Durum"] == "Kapalı"]

        st.markdown(f"### 📂 Açık Pozisyonlar ({len(open_df)})")

        if len(open_df) == 0:
            st.info("Şu an açık pozisyon yok.")
        else:
            # Her açık pozisyon için canlı fiyat + bot sinyali çek
            from data_source import best_interval_for as _bif2
            from data_source import category_of as _cat2
            _psy = _load_per_sym() or {}

            live_rows = []
            with st.spinner("Canlı fiyatlar çekiliyor..."):
                for _, row in open_df.iterrows():
                    sym = row["Sembol"]
                    try:
                        df_l = fetch_yf(sym, interval=_bif2(sym))
                        if df_l.empty:
                            cur_p = float(row["Giriş Fiyatı"])
                            bot_sig = "veri yok"
                        else:
                            cur_p = float(df_l["close"].iloc[-1])
                            # Bot sinyali
                            sd = _psy.get(sym, {})
                            if sd.get("ok"):
                                p_ = sd["params"].copy()
                                p_.setdefault("rott_x1", 30)
                                p_.setdefault("rott_x2", 1000)
                                p_.setdefault("rott_percent", 7.0)
                                s_ = sig_full.build_signals_full(
                                    df_l["close"], df_l["high"], df_l["low"], **p_)
                                lst = s_.iloc[-2] if len(s_) >= 2 else s_.iloc[-1]  # kapanmış bar
                                # Pozisyon yönüne göre bağlamlı sinyal
                                if row["Yön"] == "LONG":
                                    # LONG pozisyondaysa → LONG perspektifi
                                    if lst["cond_exit_long"]:
                                        bot_sig = "🔴 LONG ÇIK — kapat!"
                                    elif lst["major_up"] and lst["zone_up"]:
                                        bot_sig = "🟢 LONG TUT — devam"
                                    elif lst["major_dn"]:
                                        bot_sig = "⚠️ Trend AŞAĞIYA döndü"
                                    elif lst["major_up"]:
                                        bot_sig = "🟡 LONG zayıf — izle"
                                    else:
                                        bot_sig = "❓ belirsiz"
                                else:  # SHORT
                                    if lst["cond_exit_short"]:
                                        bot_sig = "🔴 SHORT ÇIK — kapat!"
                                    elif lst["major_dn"] and lst["zone_dn"]:
                                        bot_sig = "🟢 SHORT TUT — devam"
                                    elif lst["major_up"]:
                                        bot_sig = "⚠️ Trend YUKARIYA döndü"
                                    elif lst["major_dn"]:
                                        bot_sig = "🟡 SHORT zayıf — izle"
                                    else:
                                        bot_sig = "❓ belirsiz"
                            else:
                                bot_sig = "optimize yok"
                    except Exception:
                        cur_p = float(row["Giriş Fiyatı"])
                        bot_sig = "hata"

                    entry = float(row["Giriş Fiyatı"])
                    qty = float(row["Miktar"])
                    comm_pct = float(row["Komisyon %"]) / 100
                    sl = float(row["Stop Loss"]) if row["Stop Loss"] else 0
                    tp = float(row["Take Profit"]) if row["Take Profit"] else 0

                    # P&L hesabı
                    if row["Yön"] == "LONG":
                        pnl_pct = (cur_p - entry) / entry * 100 - 2 * comm_pct * 100
                        pnl_usd = (cur_p - entry) * qty - (cur_p + entry) * qty * comm_pct
                    else:  # SHORT
                        pnl_pct = (entry - cur_p) / entry * 100 - 2 * comm_pct * 100
                        pnl_usd = (entry - cur_p) * qty - (cur_p + entry) * qty * comm_pct

                    # Stop / TP'ye yakınlık
                    sl_dist = ((cur_p - sl) / cur_p * 100) if sl and row["Yön"]=="LONG" else \
                              ((sl - cur_p) / cur_p * 100) if sl else None
                    tp_dist = ((tp - cur_p) / cur_p * 100) if tp and row["Yön"]=="LONG" else \
                              ((cur_p - tp) / cur_p * 100) if tp else None

                    # Uyarı bayrakları
                    flag = ""
                    if row["Yön"] == "LONG":
                        if sl and cur_p <= sl: flag = "⚠️ STOP altında!"
                        elif tp and cur_p >= tp: flag = "✅ TP'ye ulaştı!"
                    else:
                        if sl and cur_p >= sl: flag = "⚠️ STOP üstünde!"
                        elif tp and cur_p <= tp: flag = "✅ TP'ye ulaştı!"

                    # Bot trail-stop yakınlığı (TOTT karşı tetik) — sabit %1.0
                    warn_thr_port = 1.0
                    if sd.get("ok") and not flag:  # SL/TP uyarısı yoksa
                        try:
                            if row["Yön"] == "LONG" and not pd.isna(lst["tott_dn"]):
                                dpct = (cur_p / float(lst["tott_dn"]) - 1) * 100
                                if 0 < dpct < warn_thr_port:
                                    flag = f"⚠️ ÇIK YAKIN ({dpct:.2f}%)"
                            elif row["Yön"] == "SHORT" and not pd.isna(lst["tott_up"]):
                                dpct = (float(lst["tott_up"]) / cur_p - 1) * 100
                                if 0 < dpct < warn_thr_port:
                                    flag = f"⚠️ ÇIK YAKIN ({dpct:.2f}%)"
                        except Exception:
                            pass

                    live_rows.append({
                        "Sembol": sym, "Yön": row["Yön"],
                        "Giriş": entry, "Anlık": cur_p,
                        "Miktar": qty,
                        "PnL %": pnl_pct, "PnL $": pnl_usd,
                        "SL": sl if sl else None,
                        "SL %": sl_dist,
                        "TP": tp if tp else None,
                        "TP %": tp_dist,
                        "Bot Sinyali": bot_sig,
                        "Uyarı": flag,
                        "_idx": row["index"],   # orijinal df indeksi
                    })

            df_open = pd.DataFrame(live_rows)

            # ── Özet metric'ler
            sm1, sm2, sm3, sm4, sm5 = st.columns(5)
            sm1.metric("Açık pozisyon", len(df_open))
            sm2.metric("Toplam PnL", f"${df_open['PnL $'].sum():+,.2f}")
            n_winners = (df_open["PnL $"] > 0).sum()
            n_losers = (df_open["PnL $"] <= 0).sum()
            sm3.metric("Kazanan", int(n_winners))
            sm4.metric("Kaybeden", int(n_losers))
            n_alerts = (df_open["Uyarı"] != "").sum()
            sm5.metric("⚠️ Uyarı", int(n_alerts),
                        help="Stop'a takıldı veya TP'ye ulaştı")

            # ── Tablo
            show_open = df_open.drop(columns="_idx").copy()
            st.dataframe(
                show_open.style.format({
                    "Giriş": "{:.4f}", "Anlık": "{:.4f}",
                    "Miktar": "{:.4f}",
                    "PnL %": "{:+.2f}%", "PnL $": "${:+,.2f}",
                    "SL": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                    "SL %": lambda v: f"{v:+.2f}%" if pd.notna(v) else "-",
                    "TP": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                    "TP %": lambda v: f"{v:+.2f}%" if pd.notna(v) else "-",
                }).background_gradient(subset=["PnL %"], cmap="RdYlGn",
                                        vmin=-10, vmax=10),
                use_container_width=True, height=400,
            )

            # ── POZİSYON KAPATMA
            st.markdown("### ✂️ Pozisyon kapat")
            cc_col1, cc_col2 = st.columns([3, 1])
            with cc_col1:
                close_labels = [f"{r['Sembol']} {r['Yön']} (giriş {r['Giriş']:.4f}, anlık {r['Anlık']:.4f})"
                                 for r in live_rows]
                close_idx = st.selectbox("Kapatılacak pozisyon",
                                            range(len(close_labels)),
                                            format_func=lambda i: close_labels[i],
                                            key="p_close_select")
            with cc_col2:
                if st.button("✗ Kapat", key="p_close_btn", use_container_width=True):
                    orig_idx = live_rows[close_idx]["_idx"]
                    cur_p_close = live_rows[close_idx]["Anlık"]
                    st.session_state.portfolio.loc[orig_idx, "Durum"] = "Kapalı"
                    st.session_state.portfolio.loc[orig_idx, "Kapanış Tarihi"] = _dt.now().date().isoformat()
                    st.session_state.portfolio.loc[orig_idx, "Kapanış Fiyatı"] = cur_p_close
                    try:
                        st.session_state.portfolio.to_csv(PORTFOLIO_FILE, index=False)
                    except Exception:
                        pass
                    st.success(f"✓ Kapatıldı: {live_rows[close_idx]['Sembol']} @ {cur_p_close:.4f}")
                    st.rerun()

        # ── KAPANMIŞ POZİSYONLAR
        if len(closed_df) > 0:
            with st.expander(f"📁 Kapanmış Pozisyonlar ({len(closed_df)})"):
                # P&L hesabı
                cl_rows = []
                for _, row in closed_df.iterrows():
                    entry = float(row["Giriş Fiyatı"])
                    exit_p = float(row["Kapanış Fiyatı"])
                    qty = float(row["Miktar"])
                    comm_pct = float(row["Komisyon %"]) / 100
                    if row["Yön"] == "LONG":
                        pnl_pct = (exit_p - entry) / entry * 100 - 2 * comm_pct * 100
                        pnl_usd = (exit_p - entry) * qty - (exit_p + entry) * qty * comm_pct
                    else:
                        pnl_pct = (entry - exit_p) / entry * 100 - 2 * comm_pct * 100
                        pnl_usd = (entry - exit_p) * qty - (exit_p + entry) * qty * comm_pct
                    cl_rows.append({
                        "Sembol": row["Sembol"], "Yön": row["Yön"],
                        "Giriş Tarihi": row["Giriş Tarihi"],
                        "Kapanış Tarihi": row["Kapanış Tarihi"],
                        "Giriş": entry, "Kapanış": exit_p,
                        "Miktar": qty,
                        "PnL %": pnl_pct, "PnL $": pnl_usd,
                    })
                df_cl = pd.DataFrame(cl_rows)
                # Özet
                tot_pnl = df_cl["PnL $"].sum()
                n_win = (df_cl["PnL $"] > 0).sum()
                win_rate = n_win / len(df_cl) * 100 if len(df_cl) else 0
                cl_sm1, cl_sm2, cl_sm3 = st.columns(3)
                cl_sm1.metric("Toplam realize PnL", f"${tot_pnl:+,.2f}")
                cl_sm2.metric("Kazanan", f"{n_win}/{len(df_cl)}")
                cl_sm3.metric("Win Rate", f"{win_rate:.0f}%")
                st.dataframe(
                    df_cl.style.format({
                        "Giriş":"{:.4f}", "Kapanış":"{:.4f}", "Miktar":"{:.4f}",
                        "PnL %":"{:+.2f}%", "PnL $":"${:+,.2f}",
                    }).background_gradient(subset=["PnL %"], cmap="RdYlGn"),
                    use_container_width=True, height=300,
                )

                # ── EQUITY CURVE + DRAWDOWN
                if len(df_cl) >= 2:
                    st.markdown("### 📊 Equity Curve + Drawdown")
                    df_curve = df_cl.copy()
                    df_curve["Kapanış Tarihi"] = pd.to_datetime(df_curve["Kapanış Tarihi"])
                    df_curve = df_curve.sort_values("Kapanış Tarihi").reset_index(drop=True)
                    df_curve["Kümülatif PnL $"] = df_curve["PnL $"].cumsum()

                    initial_balance = st.number_input(
                        "Başlangıç bakiyesi ($)", min_value=0.0, value=1000.0,
                        step=100.0, key="p_initial_bal",
                        help="Equity hesabı için başlangıç sermayesi"
                    )
                    df_curve["Hesap Bakiyesi"] = initial_balance + df_curve["Kümülatif PnL $"]
                    df_curve["Peak"] = df_curve["Hesap Bakiyesi"].cummax()
                    df_curve["Drawdown $"] = df_curve["Hesap Bakiyesi"] - df_curve["Peak"]
                    df_curve["Drawdown %"] = df_curve["Drawdown $"] / df_curve["Peak"] * 100

                    import plotly.graph_objects as _go
                    from plotly.subplots import make_subplots as _msp
                    fig_eq = _msp(
                        rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.65, 0.35],
                        vertical_spacing=0.08,
                        subplot_titles=("Hesap Bakiyesi", "Drawdown %"),
                    )
                    # Equity
                    fig_eq.add_trace(_go.Scatter(
                        x=df_curve["Kapanış Tarihi"],
                        y=df_curve["Hesap Bakiyesi"],
                        mode="lines+markers", name="Equity",
                        line=dict(color="#26a69a", width=2.5),
                        marker=dict(size=6),
                    ), row=1, col=1)
                    fig_eq.add_trace(_go.Scatter(
                        x=df_curve["Kapanış Tarihi"],
                        y=df_curve["Peak"],
                        mode="lines", name="Peak", line=dict(color="#888", dash="dot"),
                    ), row=1, col=1)
                    fig_eq.add_hline(y=initial_balance, line_color="#444",
                                       line_dash="dash", row=1, col=1)
                    # Drawdown
                    fig_eq.add_trace(_go.Scatter(
                        x=df_curve["Kapanış Tarihi"],
                        y=df_curve["Drawdown %"],
                        mode="lines", name="DD",
                        line=dict(color="#ef5350"),
                        fill="tozeroy", fillcolor="rgba(239,83,80,0.3)",
                    ), row=2, col=1)
                    fig_eq.update_layout(
                        height=550, showlegend=False,
                        paper_bgcolor="#131722", plot_bgcolor="#131722",
                        font=dict(color="#d1d4dc"),
                    )
                    fig_eq.update_xaxes(gridcolor="#2a2e39")
                    fig_eq.update_yaxes(gridcolor="#2a2e39")
                    st.plotly_chart(fig_eq, use_container_width=True)

                    # Metric bar — özet
                    eq_c1, eq_c2, eq_c3, eq_c4 = st.columns(4)
                    total_ret = (df_curve["Hesap Bakiyesi"].iloc[-1] / initial_balance - 1) * 100
                    eq_c1.metric("Toplam Getiri", f"{total_ret:+.2f}%")
                    eq_c2.metric("Final Bakiye",
                                  f"${df_curve['Hesap Bakiyesi'].iloc[-1]:,.2f}")
                    eq_c3.metric("Max DD %",
                                  f"{df_curve['Drawdown %'].min():.2f}%")
                    eq_c4.metric("Max DD $",
                                  f"${df_curve['Drawdown $'].min():,.2f}")

# ──────────────────────────────────────────────────────────────────
#  TAB: KONSENSÜS MOD — FY Bot + Bayes Bot mikslemesi
# ──────────────────────────────────────────────────────────────────
with tab_consensus:
    st.subheader("🤝 Konsensüs Mod — İki bot aynı yönde derse")
    st.caption("**En güvenilir sinyal yöntemi.** FY Bot (grid) + Bayes Bot (TPE) aynı yönü gösterirse işlem yap. Tartışmalıysa atla.")

    with st.expander("ℹ️ Konsensüs mantığı"):
        st.markdown("""
        **Ensemble yöntemi:** İki bağımsız bot aynı yönde sinyal verirse **olasılık × 2**, yanlış olma şansı dramatik düşer.

        | İki bot | Aksiyon |
        |---|---|
        | 🟢 LONG AÇ + 🟢 LONG AÇ | **GÜÇLÜ LONG aç** ⭐⭐⭐ |
        | 🔴 SHORT AÇ + 🔴 SHORT AÇ | **GÜÇLÜ SHORT aç** ⭐⭐⭐ |
        | 🟡 ÇIK + 🟡 ÇIK | **Hemen kapat** |
        | LONG + SHORT (çelişki) | **HİÇ İŞLEM YAPMA** ❌ |
        | Tek bot AÇ derse | **Bekle** — tartışmalı |

        **Beklenen sonuç:**
        - Win rate **%75-85'e çıkar**
        - Trade sayısı **yarıya düşer**
        - Drawdown küçülür
        - "Terste kalmama" hedefine en yakın yapı

        **Risk-weighted pozisyon:**
        - Konsensüs sinyali → sermayenin **%10-15**'ine büyük pozisyon
        - Tek bot sinyali → atla veya çok küçük (%2)
        """)

    # Sabit varsayılanlar (UI kaldırıldı — sermaye/poz/kaldıraç/GCM filtresi yok)
    cons_capital  = 1000      # $ — pozisyon büyüklüğü hesabı için referans
    cons_pos_pct  = 10        # %
    cons_lev      = 5         # x
    cons_only_gcm = False     # tüm semboller dahil
    warn_thr_cons = 1.0       # ÇIK YAKIN eşiği %

    st.markdown("### 🚀 Konsensüs taraması")
    st.caption("İki bot da var olan sembolleri tarayıp konsensüs sinyallerini liste.")
    cons_btn_col1, cons_btn_col2 = st.columns(2)
    with cons_btn_col1:
        run_cons_bist = st.button("🇹🇷 BIST Konsensüs", type="primary",
                                     use_container_width=True, key="cons_bist_btn")
    with cons_btn_col2:
        run_cons_nasdaq = st.button("🇺🇸 NASDAQ Konsensüs", type="primary",
                                       use_container_width=True, key="cons_nasdaq_btn")
    run_cons = run_cons_bist or run_cons_nasdaq
    cons_category = "BIST" if run_cons_bist else ("NASDAQ" if run_cons_nasdaq else None)

    # Bayes ve Grid dataset'ler
    import os as _os, json as _json
    if not _os.path.exists("per_symbol_params_bayes.json"):
        st.warning("⚠️ Bayes verisi yok. Alternatif Bot Portföyü'nde Bayesian arama çalıştır.")
    elif run_cons:
        _bayes = _load_bayes_sym()
        _grid  = _load_per_sym()
        from data_source import best_interval_for as _bif
        from data_source import category_of as _cat

        # Hem grid hem bayes'te olan sembolleri tara
        common_syms = [s for s in _bayes
                        if _bayes[s].get("ok") and _grid.get(s, {}).get("ok")
                        and _grid[s].get("rating") != "UYUMSUZ"]  # UYUMSUZ gizle
        # Kategoriye göre filtre — SADECE tanımlı listeler (JSON'daki eski semboller değil)
        if cons_category == "BIST":
            _bist_set = set(BIST)  # 45 VIOP hissesi
            common_syms = [s for s in common_syms if s in _bist_set]
        elif cons_category == "NASDAQ":
            # Sadece GCM Forex MetaTrader'da olan hisseler
            common_syms = [s for s in common_syms if s in GCM_NASDAQ]

        cons_prog = st.progress(0, text=f"0/{len(common_syms)}")
        cons_rows = []

        def _lbl(last_):
            if last_["cond_buy_long"]:        return "LONG_AÇ"
            if last_["cond_buy_short"]:       return "SHORT_AÇ"
            if last_["cond_exit_long"]:       return "LONG_ÇIK"
            if last_["cond_exit_short"]:      return "SHORT_ÇIK"
            if last_["major_up"] and last_["zone_up"]:  return "LONG_TUT"
            if last_["major_dn"] and last_["zone_dn"]:  return "SHORT_TUT"
            if last_["major_up"]:              return "LONG_BEKLE"
            if last_["major_dn"]:              return "SHORT_BEKLE"
            return "BELIRSIZ"

        def _walk_side(s):
            """GERÇEK pozisyon (Kokpit ile AYNI yöntem): AÇ→gir, ÇIK→çık. LONG/SHORT/FLAT."""
            bl = s["cond_buy_long"].values; xl = s["cond_exit_long"].values
            bs = s["cond_buy_short"].values; xs = s["cond_exit_short"].values
            pos = 0
            for i in range(len(s) - 1):   # sadece kapanmış barlar
                if bl[i]: pos = 1
                elif bs[i]: pos = -1
                elif pos == 1 and xl[i]: pos = 0
                elif pos == -1 and xs[i]: pos = 0
            return "LONG" if pos == 1 else ("SHORT" if pos == -1 else "FLAT")

        for idx, sym in enumerate(common_syms):
            try:
                # BIST'te FUTURES (işlem yaptığın, Kokpit ile aynı) → fiyat/S-R/sinyal tutarlı
                df_l = (fetch_fut_cached(sym, _bif(sym), 2000) if sym.upper().endswith(".IS")
                        else fetch_yf(sym, interval=_bif(sym)))
                if df_l.empty or len(df_l) < 1500:
                    cons_prog.progress((idx+1)/len(common_syms))
                    continue
                gp = _grid[sym]["params"].copy()
                bp = _bayes[sym]["params"].copy()
                for p_ in (gp, bp):
                    p_.setdefault("rott_x1", 30)
                    p_.setdefault("rott_x2", 1000)
                    p_.setdefault("rott_percent", 7.0)
                sg = sig_full.build_signals_full(df_l["close"], df_l["high"], df_l["low"], **gp)
                sb = sig_full.build_signals_full(df_l["close"], df_l["high"], df_l["low"], **bp)
                # Son KAPANMIŞ bar (iloc[-2]) — oluşan mum sinyal kaymasını önler
                _ix = -2 if len(sg) >= 2 else -1
                cur = float(df_l["close"].iloc[-1])
                # GERÇEK pozisyon (Kokpit ile AYNI yöntem — tutarlılık için kök çözüm)
                gpos = _walk_side(sg); bpos = _walk_side(sb)
                _gl = sg.iloc[_ix]; _bl_ = sb.iloc[_ix]
                gfresh = "LONG" if _gl["cond_buy_long"] else ("SHORT" if _gl["cond_buy_short"] else None)
                bfresh = "LONG" if _bl_["cond_buy_long"] else ("SHORT" if _bl_["cond_buy_short"] else None)

                # Konsensüs türü — GERÇEK pozisyona göre (taze giriş > tutma > yok)
                if gfresh == "LONG" and bfresh == "LONG":
                    cons_type = "🟢🟢 GÜÇLÜ LONG (taze giriş)"; side = "LONG"; consensus = True
                elif gfresh == "SHORT" and bfresh == "SHORT":
                    cons_type = "🔴🔴 GÜÇLÜ SHORT (taze giriş)"; side = "SHORT"; consensus = True
                elif gpos == "LONG" and bpos == "LONG":
                    cons_type = "🟢 LONG (iki bot pozisyonda)"; side = "LONG"; consensus = True
                elif gpos == "SHORT" and bpos == "SHORT":
                    cons_type = "🔴 SHORT (iki bot pozisyonda)"; side = "SHORT"; consensus = True
                elif gpos == "FLAT" and bpos == "FLAT":
                    cons_type = "⚪ Pozisyon yok"; side = None; consensus = False
                else:
                    cons_type = "⏳ botlar ayrı düşüyor"; side = None; consensus = False

                # Stop bandı GRID'den (sg) — Kokpit + bot grid params kullanıyor → tutarlı.
                tott_up_v = float(sg.iloc[_ix]["tott_up"]) if not pd.isna(sg.iloc[_ix]["tott_up"]) else None
                tott_dn_v = float(sg.iloc[_ix]["tott_dn"]) if not pd.isna(sg.iloc[_ix]["tott_dn"]) else None
                # Stop seçimi yöne göre (TOTT karşı tetik = trail stop)
                stop = tott_dn_v if side == "LONG" else (tott_up_v if side == "SHORT" else None)
                risk_pct = (abs(cur - stop) / cur * 100) if stop else None

                # ÇIK YAKIN uyarısı — açık pozisyonda trail stop yakınlığı
                if side == "LONG" and tott_dn_v:
                    dist_pct = (cur / tott_dn_v - 1) * 100
                    if 0 < dist_pct < warn_thr_cons:
                        cons_type = f"{cons_type}  ⚠️ ÇIK YAKIN ({dist_pct:.2f}%)"
                elif side == "SHORT" and tott_up_v:
                    dist_pct = (tott_up_v / cur - 1) * 100
                    if 0 < dist_pct < warn_thr_cons:
                        cons_type = f"{cons_type}  ⚠️ ÇIK YAKIN ({dist_pct:.2f}%)"

                # Pozisyon büyüklüğü — konsensüs varsa daha büyük
                pos_size = cons_capital * (cons_pos_pct / 100) if consensus and side and side != "EXIT" else 0
                max_risk = (pos_size * cons_lev * risk_pct / 100) if pos_size and risk_pct else 0

                # FY ve Bayes rating
                fy_rt = _grid[sym].get("rating", "?")
                bs_rt = _bayes[sym].get("rating", "?")

                # ── OTT+TOTT sıralı teyit. BIST'te FUTURES (işlem yapılan, TradingView ile
                #    aynı) baz alınır; futures yoksa spot'a düşer.
                try:
                    import ott_tott_confirm as _otc
                    _src = df_l   # varsayılan spot
                    if sym.upper().endswith(".IS"):
                        _df_fut = ds_fetch_futures(sym, interval="15m")
                        if _df_fut is not None and not _df_fut.empty and len(_df_fut) > 200:
                            _src = _df_fut
                    _rr = _otc.compute(_src["close"], _otc.TV_LENGTH, _otc.TV_PERCENT, _otc.TV_COEFF)
                    _cf = _rr[_rr["confirm"].notna()]
                    if len(_cf):
                        _d = _cf["confirm"].iloc[-1]
                        _p = float(_cf["close"].iloc[-1])
                        ot_teyit = (f"🟢 LONG · {_cf.index[-1]:%d/%m %H:%M} · {_p:.2f}" if _d == "LONG"
                                    else f"🔴 SHORT · {_cf.index[-1]:%d/%m %H:%M} · {_p:.2f}")
                    else:
                        ot_teyit = "—"
                except Exception:
                    ot_teyit = "—"

                _cd, _cr = _sup_res(df_l)   # anlık destek/direnç
                cons_rows.append({
                    "Sembol": sym,
                    "Kategori": _cat(sym),
                    "OTT+TOTT Teyit": ot_teyit,
                    "FY Bot": (f"{gpos} (taze)" if gfresh else gpos),
                    "Bayes Bot": (f"{bpos} (taze)" if bfresh else bpos),
                    "Konsensüs": cons_type,
                    "Fiyat": cur,
                    "Direnç": _cr,
                    "Destek": _cd,
                    "Stop": stop,
                    "Risk %": risk_pct,
                    "Pozisyon $": pos_size,
                    "Adet": (pos_size / cur) if pos_size and cur else 0,
                    "Max Risk $": max_risk,
                    "FY Rating": fy_rt,
                    "Bayes Rating": bs_rt,
                    "_strong": consensus,
                })
            except Exception:
                pass
            cons_prog.progress((idx+1)/len(common_syms), text=f"{idx+1}/{len(common_syms)} {sym}")
        cons_prog.empty()

        if not cons_rows:
            st.warning("Veri çekilemedi.")
        else:
            df_cons = pd.DataFrame(cons_rows)
            # Sadece konsensüs olanları ayır
            strong = df_cons[df_cons["_strong"] == True].drop(columns="_strong").reset_index(drop=True)
            weak   = df_cons[df_cons["_strong"] == False].drop(columns="_strong").reset_index(drop=True)

            # Özet metric'leri — taze AÇ konsensüsler + TUT konsensüsler + çelişki
            sm1, sm2, sm3, sm4, sm5 = st.columns(5)
            sm1.metric("🟢🟢 GÜÇLÜ LONG (AÇ)",
                        int((strong["Konsensüs"]=="🟢🟢 GÜÇLÜ LONG").sum()))
            sm2.metric("🔴🔴 GÜÇLÜ SHORT (AÇ)",
                        int((strong["Konsensüs"]=="🔴🔴 GÜÇLÜ SHORT").sum()))
            sm3.metric("🟡🟡 HEMEN KAPAT",
                        int((strong["Konsensüs"]=="🟡🟡 HEMEN KAPAT").sum()))
            tut_count = int(strong["Konsensüs"].str.contains("TUT").sum())
            sm4.metric("🟢🔴 TUT (konsensüs)", tut_count,
                        help="İki bot da aynı yönde TUT diyor — pozisyon zaten varsa koru")
            sm5.metric("Tartışmalı / Çelişki", len(weak))

            if len(strong) > 0:
                st.markdown("### ⭐ KONSENSÜS SİNYALLER (yüksek olasılık)")
                show_cols_s = ["Sembol","Kategori","OTT+TOTT Teyit","Konsensüs","Fiyat",
                                "Direnç","Destek","Stop",
                                "Risk %","Pozisyon $","Adet","Max Risk $",
                                "FY Rating","Bayes Rating"]
                st.dataframe(
                    strong[show_cols_s].style.format({
                        "Fiyat":"{:.4f}", "Stop":"{:.4f}",
                        "Direnç": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                        "Destek": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                        "Risk %":"{:.2f}%",
                        "Pozisyon $":"${:.0f}", "Adet":"{:.4f}", "Max Risk $":"${:.0f}",
                    }).background_gradient(subset=["Risk %"], cmap="RdYlGn_r"),
                    use_container_width=True, height=300,
                )
                # Toplam risk
                tot_inv = strong["Pozisyon $"].sum()
                tot_risk = strong["Max Risk $"].sum()
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("Toplam yatırım", f"${tot_inv:,.0f}")
                rc2.metric("Toplam max risk", f"${tot_risk:,.0f}",
                            f"{tot_risk/cons_capital*100:.1f}% sermaye")
                rc3.metric("Sermayenin %", f"{tot_inv/cons_capital*100:.0f}%")
            else:
                st.info("📭 Şu an konsensüs sinyali yok. İki bot anlaşmıyor — risk almama.")

            if len(weak) > 0:
                with st.expander(f"📋 Konsensüs olmayan / tartışmalı ({len(weak)})"):
                    show_cols_w = ["Sembol","Kategori","FY Bot","Bayes Bot","Konsensüs",
                                    "Fiyat","FY Rating","Bayes Rating"]
                    st.dataframe(
                        weak[show_cols_w].style.format({"Fiyat":"{:.4f}"}),
                        use_container_width=True, height=300,
                    )
                    st.caption("Bu sembollerde **iki bot farklı görüş**. Risk yüksek, atla.")
with tab_scan:
    st.subheader("📡 Anlık Sinyal Tarayıcı")
    _src_info = []
    if os.getenv("TV_USERNAME"):
        _src_info.append(f"TradingView (login: `{os.getenv('TV_USERNAME')}`)")
    else:
        _src_info.append("TradingView (anonim mod)")
    _src_info.append("yfinance fallback")
    st.caption("Veri kaynağı: " + " · ".join(_src_info) + " — "
                "**adaptif timeframe**: BIST/NASDAQ → H1, CRYPTO → 30dk.")

    with st.expander("ℹ️ Sütunlar ne anlama gelir? (legend)"):
        st.markdown("""
        ### Durum sütunu

        | Durum | Anlam | Sen ne yapmalısın? |
        |---|---|---|
        | 🟢 **LONG AÇ** | YENİ AL sinyali bu bar oluştu | **Şimdi long pozisyon aç** (taze sinyal) |
        | 🔴 **SHORT AÇ** | YENİ AÇIĞA SAT sinyali oluştu | **Şimdi short pozisyon aç** (taze sinyal) |
        | 🟡 **LONG'tan ÇIK** | Sistem long pozisyondan çıkış sinyali verdi | Açık LONG pozisyonun varsa **KAPAT** |
        | 🟡 **SHORT'tan ÇIK** | Sistem short pozisyondan çıkış sinyali verdi | Açık SHORT pozisyonun varsa **KAPAT** |
        | 🟢 **LONG'ta TUT** | Sistem zaten long pozisyonda (önceki barda açıldı) | Henüz girmediysen geç kaldın — küçük poz dene ya da atla |
        | 🔴 **SHORT'ta TUT** | Sistem zaten short pozisyonda | Aynı şekilde — geç kalmış olabilirsin |
        | ⏳ **LONG bekle** | Ana trend yukarı ama henüz tetik yok | Hiçbir şey yapma, izlemeye devam |
        | ⏳ **SHORT bekle** | Ana trend aşağı ama henüz tetik yok | Bekle |
        | ❓ **Belirsiz** | Ana trend belli değil (warmup veya yatay) | Bu sembolden uzak dur |

        ### Güven sütunu — sembolün sisteme uygunluğu (60 gün backtest)

        | Güven | Şart | Anlam |
        |---|---|---|
        | 🏆 **MÜKEMMEL** | ret > 30%, PF ≥ 2.0 | Sistem bu sembolde **ideal** çalışıyor. Tam güven. |
        | ⭐ **İYİ** | ret > 15%, PF ≥ 1.5 | Güvenilir edge var |
        | 🟢 **ORTA** | ret > 5%, PF ≥ 1.2 | Küçük edge — dikkatli |
        | 🟡 **MARJINAL** | ret > 0% | Belirsiz, çok küçük pozisyon |
        | ⚠️ **VERİ_AZ** | <5 trade | İstatistiksel olarak anlamlı değil |
        | ❌ **UYUMSUZ** | ret < 0% | Sistem bu sembolde **zarar etti** → girme |
        | ❓ **Bilinmiyor** | optimize edilmedi | Henüz değerlendirilmedi |

        ### BT istatistik sütunları

        - **BT Getiri %** = 60 günlük backtest getirisi (sembol-özel optimum parametre ile)
        - **BT PF** = Profit Factor (kar / zarar oranı). ≥ 2 mükemmel, ≥ 1.5 iyi, < 1 sistem zarar etti
        - **BT Win %** = kazanan trade oranı
        - **BT Trade** = backtest'te oluşan toplam işlem sayısı

        > **Pratik karar:** Aynı sinyali veren iki sembol varsa, **Güven yüksek olana** öncelik ver.
        > 🏆 MÜKEMMEL + 🟢 LONG AÇ = en güçlü kombinasyon.
        > ❌ UYUMSUZ + 🟢 LONG AÇ = **bahis yapma**, sistem bu sembolde çalışmıyor.

        > **Filtre kısa-yolu:** "Sadece AKTİF SİNYAL" kutusunu işaretle → sadece **LONG AÇ / SHORT AÇ / ÇIK** sinyalleri kalır.
        """)
    col1, col2 = st.columns(2)
    with col1:
        only_signals = st.checkbox("Sadece AKTİF SİNYAL (AL/SAT)", value=False)
    with col2:
        only_top_rated = st.checkbox("Sadece 🏆 MÜKEMMEL + ⭐ İYİ", value=True,
                                       help="Düşük güvenli sembolleri gizle — terste kalma riski azalır")

    # Erken ÇIK uyarı eşiği — sabit %1.0
    warn_thr_scan = 1.0

    # BIST / NASDAQ ayrı butonlar
    sc_btn1, sc_btn2 = st.columns(2)
    with sc_btn1:
        run_scan_bist = st.button(f"🇹🇷 BIST tara ({len(BIST)} sembol)",
                                     type="primary", use_container_width=True,
                                     key="scan_bist_btn")
    with sc_btn2:
        run_scan_nasdaq = st.button(f"🇺🇸 NASDAQ tara ({len(NASDAQ)} sembol)",
                                       type="primary", use_container_width=True,
                                       key="scan_nasdaq_btn")
    run_scan = run_scan_bist or run_scan_nasdaq

    # Hangi kategori tarandı? (UYUMSUZ semboller filtrelenir)
    if run_scan_bist:
        symbols = [s for s in BIST if not _is_uyumsuz(s)]
    elif run_scan_nasdaq:
        symbols = [s for s in NASDAQ if not _is_uyumsuz(s)]
    else:
        symbols = []

    rows = []
    if not run_scan:
        st.warning("👆 **🔄 Şimdi tara** butonuna bas. Tarama 1-5 dk sürer.\n\n"
                    "📲 Otomatik bildirim için Telegram'a bak — "
                    "BIST 10:30/12:30/15:30/17:30, NASDAQ 17:00/19:00/21:00/23:00 TR.")
    else:
        st.cache_data.clear()
        progress = st.progress(0, text=f"0/{len(symbols)}")
        for i, sym in enumerate(symbols):
            r = analyze_intraday(sym, warn_threshold_pct=warn_thr_scan)
            if r:
                r2 = {k:v for k,v in r.items() if not k.startswith("_")}
                rows.append(r2)
            progress.progress((i+1)/len(symbols), text=f"{i+1}/{len(symbols)} — {sym}")
        progress.empty()

    if rows:
        df_scan = pd.DataFrame(rows)
        if only_signals:
            df_scan = df_scan[df_scan["Durum"].str.contains("AÇ|ÇIK", regex=True)]
        if only_top_rated:
            df_scan = df_scan[df_scan["Güven"].str.contains("MÜKEMMEL|İYİ", regex=True)]

        # Sıralama: önce yeni sinyaller, sonra çıkışlar, sonra açık tut, sonra bekleyenler
        # — aynı seviyede güven skoruna göre sırala
        order = {
            "🟢 LONG AÇ": 0, "🔴 SHORT AÇ": 1,
            "🟡 LONG'tan ÇIK": 2, "🟡 SHORT'tan ÇIK": 3,
            "🟢 LONG'ta TUT": 4, "🔴 SHORT'ta TUT": 5,
            "⏳ LONG bekle": 6, "⏳ SHORT bekle": 7, "❓ Belirsiz": 8,
        }
        df_scan["_ord"] = df_scan["Durum"].map(order).fillna(9)
        sort_cols = ["_ord"]
        sort_asc = [True]
        if "_GuvenSkor" in df_scan.columns:
            sort_cols.append("_GuvenSkor")
            sort_asc.append(False)
        df_scan = df_scan.sort_values(sort_cols, ascending=sort_asc).reset_index(drop=True)

        # Gösterim kolonları (underscore'la başlayanları çıkar)
        show_cols = [c for c in df_scan.columns if not c.startswith("_")]
        # İdeal sıralama
        col_order = ["Sembol", "Kategori", "Güven", "Durum", "Fiyat",
                      "Direnç", "Destek",
                      "Trend OTT", "Tetik ↑", "Up %", "Tetik ↓", "Dn %",
                      "BT Getiri %", "BT PF", "BT Win %", "BT Trade"]
        show_cols = [c for c in col_order if c in show_cols]

        st.dataframe(
            df_scan[show_cols].style.format({
                "Fiyat": "{:.4f}",
                "Direnç": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                "Destek": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                "Trend OTT": "{:.4f}",
                "Tetik ↑": "{:.4f}",
                "Tetik ↓": "{:.4f}",
                "Up %": "{:+.2f}%",
                "Dn %": "{:+.2f}%",
                "BT Getiri %": lambda v: f"{v:+.1f}%" if pd.notna(v) else "-",
                "BT PF": lambda v: ("∞" if v >= 900 else f"{v:.2f}") if pd.notna(v) else "-",
                "BT Win %": lambda v: f"{v:.0f}%" if pd.notna(v) else "-",
                "BT Trade": lambda v: f"{int(v)}" if pd.notna(v) else "-",
            }).background_gradient(subset=["BT Getiri %"], cmap="RdYlGn",
                                    vmin=-30, vmax=80),
            use_container_width=True, height=600,
        )

        st.info(f"🎯 **{len(df_scan)}** sembol gösteriliyor. "
                f"Güven sütunu = backtest rating'i (60 gün, sembol-özel optimize edilmiş). "
                f"BT Getiri = 60 günlük backtest getirisi.")

        st.markdown("### Özet")
        col_a, col_b, col_c, col_d, col_e = st.columns(5)
        col_a.metric("Toplam", len(df_scan))
        col_b.metric("🟢 LONG AÇ",
                     len(df_scan[df_scan["Durum"]=="🟢 LONG AÇ"]),
                     help="Yeni LONG sinyali — şimdi aç")
        col_c.metric("🔴 SHORT AÇ",
                     len(df_scan[df_scan["Durum"]=="🔴 SHORT AÇ"]),
                     help="Yeni SHORT sinyali — şimdi aç")
        col_d.metric("🟡 ÇIK sinyali",
                     len(df_scan[df_scan["Durum"].str.contains("ÇIK", regex=False)]),
                     help="Açık pozisyonu kapatma sinyali")
        col_e.metric("Açık (tut)",
                     len(df_scan[df_scan["Durum"].str.contains("TUT", regex=False)]),
                     help="Sistem zaten içinde olan pozisyonlar")

# ──────────────────────────────────────────────────────────────────
#  TAB 2: PORTFÖY SİMÜLASYONU
# ──────────────────────────────────────────────────────────────────
with tab_sim:
    st.subheader("📌 Anlık Fırsatlar — Bot Önerileri")
    st.caption("Şu an AÇ sinyali veren semboller. Stop = TOTT karşı tetik (trailing). Çıkış sistem sinyaline bağlı.")

    with st.expander("ℹ️ Sistem mantığı"):
        st.markdown("""
        Bu bot **trend takipçi**: sabit hedef yok, **trail stop** mantığıyla çalışır.

        - **Giriş**: TOTT tetik kapısı kırılınca (cond_buy_long/short)
        - **Stop**: karşı yöndeki TOTT tetiği (her bar kayar — trail)
        - **Çıkış**: trend ters döndüğünde sistem ÇIK sinyali verir
          - LONG ÇIK: bölge aşağı (zone_dn) + major aşağı
          - SHORT ÇIK: bölge yukarı (zone_up) + major yukarı

        Tablodaki **Stop** seviyesi = TOTT'un anlık değeri. Mum kapanışında güncellenir.

        **NOT**: Hedef sütunu kaldırıldı — indikatörden çıkmıyor, sistem ÇIK sinyalini bekle.
        """)

    prop_top_only = st.checkbox("Sadece 🏆 MÜKEMMEL + ⭐ İYİ",
                                   value=True, key="prop_top_only")

    # BIST / NASDAQ ayrı butonlar
    pc_btn1, pc_btn2 = st.columns(2)
    with pc_btn1:
        run_prop_bist = st.button(f"🇹🇷 BIST öneriler ({len(BIST)} sembol)",
                                     type="primary", use_container_width=True,
                                     key="prop_bist_btn")
    with pc_btn2:
        run_prop_nasdaq = st.button(f"🇺🇸 NASDAQ öneriler ({len(NASDAQ)} sembol)",
                                       type="primary", use_container_width=True,
                                       key="prop_nasdaq_btn")
    run_prop = run_prop_bist or run_prop_nasdaq

    if run_prop_bist:
        prop_symbols = [s for s in BIST if not _is_uyumsuz(s)]
    elif run_prop_nasdaq:
        prop_symbols = [s for s in NASDAQ if not _is_uyumsuz(s)]
    else:
        prop_symbols = []

    if not run_prop:
        st.warning("👆 Yukarıdaki **🔄 Önerileri tara** butonuna bas. "
                    "Tarama sembol sayısına bağlı olarak 1-5 dk sürer.\n\n"
                    "📲 Otomatik bildirim için Telegram'a bak — "
                    "BIST için 10:10/12:10/15:10/17:10 TR, "
                    "NASDAQ için 16:40/18:40/20:40/22:40 TR.")
        prop_rows = []
    else:
        st.cache_data.clear()
        prop_prog = st.progress(0, text=f"0/{len(prop_symbols)}")
        prop_rows = []
        for i, sym in enumerate(prop_symbols):
            r = analyze_intraday(sym)
            if r:
                prop_rows.append(r)
            prop_prog.progress((i+1)/len(prop_symbols), text=f"{i+1}/{len(prop_symbols)} {sym}")
        prop_prog.empty()

    # Sadece YENİ sinyali olanları al (LONG AÇ veya SHORT AÇ) — sadece tarama yapıldıysa
    fresh = []
    if not run_prop:
        prop_rows = []
    for r in prop_rows:
        if "LONG AÇ" in r["Durum"] or "SHORT AÇ" in r["Durum"]:
            # Rating filtre
            if prop_top_only and not ("MÜKEMMEL" in r["Güven"] or "İYİ" in r["Güven"]):
                continue

            cur = r["Fiyat"]
            if "LONG" in r["Durum"]:
                yon = "🟢 LONG"
                stop = r["Tetik ↓"]
                risk_pct = ((cur - stop) / cur * 100) if (stop and cur) else None
            else:
                yon = "🔴 SHORT"
                stop = r["Tetik ↑"]
                risk_pct = ((stop - cur) / cur * 100) if (stop and cur) else None

            fresh.append({
                "Sembol": r["Sembol"],
                "Kategori": r["Kategori"],
                "Güven": r["Güven"],
                "Yön": yon,
                "Anlık Fiyat": cur,
                "Direnç": r.get("Direnç"),
                "Destek": r.get("Destek"),
                "Stop": stop,
                "Risk %": risk_pct,
                "BT Win %": r["BT Win %"],
                "BT Ret %": r["BT Getiri %"],
            })

    if run_prop and not fresh:
        st.info("📭 Şu anda yeni sinyal yok. Tarama yapıldı, hiçbir sembolde **LONG AÇ** veya **SHORT AÇ** sinyali yok.\n\n"
                 "Yarın sabah veya birkaç saat sonra tekrar dene.")
    elif not run_prop:
        pass  # buton basılmadı, info yukarıda gösterildi

    else:
        df_prop = pd.DataFrame(fresh)
        # Güven + BT Win % ile sırala (R:R 1:2 kaldırıldı, hedef yok)
        guv_skor = {"🏆 MÜKEMMEL": 5, "⭐ İYİ": 4, "🟢 ORTA": 3,
                    "🟡 MARJINAL": 2, "⚠️ VERİ_AZ": 1, "❌ UYUMSUZ": 0}
        df_prop["_sc"] = df_prop["Güven"].map(guv_skor).fillna(0)
        df_prop = df_prop.sort_values(["_sc", "BT Win %"],
                                        ascending=[False, False]).drop(columns="_sc").reset_index(drop=True)

        # Özet
        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("🟢 LONG sinyali", (df_prop["Yön"]=="🟢 LONG").sum())
        sm2.metric("🔴 SHORT sinyali", (df_prop["Yön"]=="🔴 SHORT").sum())
        sm3.metric("Toplam fırsat", len(df_prop))

        st.dataframe(
            df_prop.style.format({
                "Anlık Fiyat": "{:.4f}",
                "Stop": "{:.4f}",
                "Risk %": "{:.2f}%",
                "BT Win %": "{:.0f}%",
                "BT Ret %": "{:+.1f}%",
            }).background_gradient(subset=["BT Win %"], cmap="Greens"),
            use_container_width=True, height=550,
        )

        st.markdown("""
        ### 📋 Nasıl kullanılır?

        **Örnek:** ASELS.IS · 🟢 LONG · Anlık 380 · Stop 372

        1. **Long pozisyon aç** broker'da (örn 380 fiyatından alış emri)
        2. **Stop-loss = Stop sütunu** (372) — bu seviyenin altına inerse OTOMATIK ÇIK
        3. Pozisyonu **dashboard'daki "🟡 LONG ÇIK" sinyali gelene kadar tut**
        4. Stop sürekli kayar (trail) — her bar yeniden çekilir, takip et

        Aynı mantık SHORT için tersi. **Hedef yok**, sistem sinyalini bekle.
        """)

# ──────────────────────────────────────────────────────────────────
#  TAB 3: SEMBOL GRAFİK (TradingView-style lightweight-charts)
# ──────────────────────────────────────────────────────────────────
if False:  # 📊 Detay Grafik kaldırıldı (sadeleştirme) — Kokpit'te grafik+TV linki var. Kod tarihçe için duruyor.
    st.subheader("📈 Sembol Detay — TradingView Tarzı Grafik")

    csym1, csym2, csym3 = st.columns([3, 1, 1])
    with csym1:
        all_syms = NASDAQ + BIST + COMMODITY + CRYPTO
        chart_sym = st.selectbox("Sembol", all_syms,
                                  index=all_syms.index("NVDA") if "NVDA" in all_syms else 0)
    with csym2:
        chart_days = st.selectbox("Süre", [3, 7, 14, 30], index=1,
                                    format_func=lambda x: f"{x} gün")
    with csym3:
        chart_show_signals = st.checkbox("Sinyal okları", value=True)

    r = analyze_intraday(chart_sym)
    if r is None:
        st.error(f"{chart_sym} için veri çekilemedi. Birkaç saniye sonra tekrar dene veya başka sembol seç.")
    else:
        df = r["_df"]
        s = r["_signals"]
        cutoff = df.index[-1] - pd.Timedelta(days=chart_days)
        dff = df[df.index >= cutoff]
        sf = s[s.index >= cutoff]

        # ──── Sembol BACKTEST KARTI (cache'li)
        sym_data = None
        psy = _load_per_sym()
        if psy and chart_sym in psy and psy[chart_sym].get("ok"):
            sym_data = psy[chart_sym]

        if sym_data:
            rt = sym_data.get("rating", "?")
            stx = sym_data["stats"]
            # Rating rengi
            rating_color = {
                "MÜKEMMEL": "#26a69a", "İYİ": "#66bb6a",
                "ORTA": "#ffa726", "MARJINAL": "#ffca28",
                "VERİ_AZ": "#90a4ae", "UYUMSUZ": "#ef5350",
            }.get(rt, "#888")
            rating_emoji = {
                "MÜKEMMEL": "🏆", "İYİ": "⭐", "ORTA": "🟢",
                "MARJINAL": "🟡", "VERİ_AZ": "⚠️", "UYUMSUZ": "❌",
            }.get(rt, "❓")

            st.markdown(f"""
            <div style="background:{rating_color}22; border-left:5px solid {rating_color};
                        padding:12px 16px; margin-bottom:10px; border-radius:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-size:24px; font-weight:bold; color:{rating_color};">
                            {rating_emoji} {rt}
                        </span>
                        <span style="opacity:0.7; margin-left:10px;">
                            ({sym_data.get('bars', 0):,} bar, 60 gün 5-dk backtest)
                        </span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Backtest metrikleri
            bm1, bm2, bm3, bm4, bm5, bm6 = st.columns(6)
            bm1.metric("60g Getiri", f"{stx['return']*100:+.1f}%")
            pf_str = "∞" if stx['pf'] is None else f"{stx['pf']:.2f}"
            bm2.metric("Profit Factor", pf_str)
            bm3.metric("Max DD", f"{stx['max_dd']*100:+.1f}%")
            bm4.metric("Trade", f"{stx['n_trades']}")
            bm5.metric("Win Rate", f"{stx['win_rate']*100:.0f}%")
            bm6.metric("Sharpe", f"{stx['sharpe']:.2f}")

            # Parametreler (collapsible)
            with st.expander(f"⚙️ {chart_sym} için optimum parametreler"):
                params = sym_data["params"]
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.markdown("**Trend**")
                    st.write(f"- length: `{params['trend_length']}`")
                    st.write(f"- percent: `{params['trend_percent']}`")
                    st.write(f"- minor: `{params['minor_percent']}`")
                with pc2:
                    st.markdown("**Bölge (TOTT + SOTT)**")
                    st.write(f"- tott %: `{params['tott_percent']}`")
                    st.write(f"- tott coeff: `{params['tott_coeff']}`")
                    st.write(f"- sott K: `{params['sott_period_k']}`")
                    st.write(f"- sott smooth: `{params['sott_smooth_k']}`")
                    st.write(f"- sott %: `{params['sott_percent']}`")
                with pc3:
                    st.markdown("**Kapı + ROTT**")
                    st.write(f"- gate length: `{params['gate_length']}`")
                    st.write(f"- gate %: `{params['gate_percent']}`")
                    st.write(f"- gate shift: `{params['gate_shift']}`")
                    st.write(f"- rott x1: `{params['rott_x1']}`")
                    st.write(f"- rott x2: `{params['rott_x2']}`")
                    st.write(f"- rott %: `{params['rott_percent']}`")
        else:
            st.warning(f"⚠️ **{chart_sym}** için sembol-özel optimum parametre yok. "
                       f"Grafik generic parametrelerle çiziliyor. "
                       f"Tam sonuç için `per_symbol_optimize.py` çalıştır.")

        st.markdown("---")

        # Anlık fiyat ve tetik metrikleri
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Fiyat", f"{r['Fiyat']:.4f}")
        m2.metric("Durum", r['Durum'].replace("🟢","").replace("🔴","").replace("🟡","").strip())
        if r["Trend OTT"]:
            m3.metric("Trend OTT", f"{r['Trend OTT']:.4f}",
                      f"{(r['Trend OTT']/r['Fiyat']-1)*100:+.2f}%")
        if r["Tetik ↑"]:
            m4.metric("Tetik ↑", f"{r['Tetik ↑']:.4f}",
                      f"{r['Up %']:+.2f}%")
        if r["Tetik ↓"]:
            m5.metric("Tetik ↓", f"{r['Tetik ↓']:.4f}",
                      f"{r['Dn %']:+.2f}%")

        # Veriyi lightweight-charts formatına çevir
        def to_unix(idx):
            return int(idx.timestamp())

        candles = [
            {"time": to_unix(t), "open": float(o), "high": float(h),
             "low": float(l), "close": float(c)}
            for t,o,h,l,c in zip(dff.index, dff["open"], dff["high"],
                                  dff["low"], dff["close"])
        ]
        def line_data(series, idx):
            return [{"time": to_unix(t), "value": float(v)}
                    for t, v in zip(idx, series) if not pd.isna(v)]

        trend_ott_line = line_data(sf["trend_ott"], sf.index)
        tott_up_line = line_data(sf["tott_up"], sf.index)
        tott_dn_line = line_data(sf["tott_dn"], sf.index)

        # Sinyal markerları
        markers = []
        if chart_show_signals:
            buy_long = sf[sf["cond_buy_long"]]
            buy_short = sf[sf["cond_buy_short"]]
            exit_long = sf[sf["cond_exit_long"]]
            exit_short = sf[sf["cond_exit_short"]]
            for t in buy_long.index:
                markers.append({"time": to_unix(t), "position": "belowBar",
                                "color": "#26a69a", "shape": "arrowUp", "text": "AL"})
            for t in buy_short.index:
                markers.append({"time": to_unix(t), "position": "aboveBar",
                                "color": "#ef5350", "shape": "arrowDown", "text": "SAT"})
            for t in exit_long.index:
                markers.append({"time": to_unix(t), "position": "aboveBar",
                                "color": "#ffa726", "shape": "circle", "text": "ÇIK"})
            for t in exit_short.index:
                markers.append({"time": to_unix(t), "position": "belowBar",
                                "color": "#ffa726", "shape": "circle", "text": "KAPAT"})
            markers.sort(key=lambda x: x["time"])

        # SOTT alt grafik için veri
        sott_src_line = line_data(sf["sott_src"], sf.index)
        sott_ott_line = line_data(sf["sott_ott"], sf.index)

        # ──── Lightweight Charts konfigürasyonu (TradingView dark)
        chart_options_main = {
            "height": 500,
            "layout": {
                "background": {"type": "solid", "color": "#131722"},
                "textColor": "#d1d4dc",
            },
            "grid": {
                "vertLines": {"color": "#2a2e39"},
                "horzLines": {"color": "#2a2e39"},
            },
            "crosshair": {"mode": 1},
            "rightPriceScale": {"borderColor": "#485158"},
            "timeScale": {
                "borderColor": "#485158",
                "timeVisible": True,
                "secondsVisible": False,
            },
        }
        chart_options_sub = {
            "height": 200,
            "layout": {
                "background": {"type": "solid", "color": "#131722"},
                "textColor": "#d1d4dc",
            },
            "grid": {
                "vertLines": {"color": "#2a2e39"},
                "horzLines": {"color": "#2a2e39"},
            },
            "rightPriceScale": {"borderColor": "#485158"},
            "timeScale": {
                "borderColor": "#485158",
                "timeVisible": True,
                "secondsVisible": False,
            },
        }

        # Series listesi — ana panel
        main_series = [
            {"type": "Candlestick", "data": candles,
             "options": {
                 "upColor": "#26a69a", "downColor": "#ef5350",
                 "borderUpColor": "#26a69a", "borderDownColor": "#ef5350",
                 "wickUpColor": "#26a69a", "wickDownColor": "#ef5350",
             },
             "markers": markers if chart_show_signals else [],
            },
            {"type": "Line", "data": trend_ott_line,
             "options": {"color": "#aa00ff", "lineWidth": 2, "title": "Trend OTT"}},
            {"type": "Line", "data": tott_up_line,
             "options": {"color": "#26a69a", "lineWidth": 1, "lineStyle": 2,
                         "title": "TOTT ↑"}},
            {"type": "Line", "data": tott_dn_line,
             "options": {"color": "#ef5350", "lineWidth": 1, "lineStyle": 2,
                         "title": "TOTT ↓"}},
        ]

        # SOTT alt panel
        sub_series = [
            {"type": "Line", "data": sott_src_line,
             "options": {"color": "#2196f3", "lineWidth": 2, "title": "SOTT K"}},
            {"type": "Line", "data": sott_ott_line,
             "options": {"color": "#e040fb", "lineWidth": 2, "title": "SOTT OTT"}},
        ]

        renderLightweightCharts(
            [
                {"chart": chart_options_main, "series": main_series},
                {"chart": chart_options_sub, "series": sub_series},
            ],
            key=f"chart_{chart_sym}_{chart_days}"
        )

        st.caption(f"📊 **{chart_sym}** — son {chart_days} gün, 5-dk bar. "
                   f"Mor çizgi: Trend OTT. Yeşil/Kırmızı kesik: TOTT bantları. "
                   f"Yeşil↑/Kırmızı↓ ok: AL/SAT sinyali. Turuncu daire: çıkış. "
                   f"Alt panel: SOTT (mavi K, mor OTT).")


# ── ISI HARİTASI (Tarayıcı alt-sekmesi) — tüm BIST renk renk, % değişim + OTT yönü
with tab_heat:
    st.subheader("🗺️ BIST Isı Haritası")
    st.caption("Tüm tahta tek ekranda: kutu rengi = günlük % değişim (yeşil↑/kırmızı↓), "
                "etiket = OTT+TOTT yönü (🟢/🔴). Matriks heatmap mantığı, futures verisiyle.")
    _ht_tf = st.radio("Zaman dilimi", ["1h", "15m"], horizontal=True, key="heat_tf")
    if st.button("🗺️ Isı haritasını oluştur", type="primary", use_container_width=True, key="heat_btn"):
        _hl = [s for s in BIST if not _is_uyumsuz(s)]
        prog = st.progress(0, text="0"); hrows = []
        for i, sym in enumerate(_hl):
            try:
                d = fetch_fut_cached(sym, _ht_tf, 2000)
                if d is None or d.empty or len(d) < 300:
                    continue
                cur = float(d["close"].iloc[-1])
                # günlük % değişim: bugünün ilk barına göre (seans içi); yoksa son güne göre
                _today = d[d.index.normalize() == d.index[-1].normalize()]
                base = float(_today["open"].iloc[0]) if len(_today) else float(d["close"].iloc[-2])
                chg = (cur / base - 1) * 100 if base else 0.0
                r = otc.compute(d["close"], otc.TV_LENGTH, otc.TV_PERCENT, otc.TV_COEFF)
                cs = otc.confirmed_signals(r)
                yon = cs["yon"].iloc[-1] if len(cs) else None
                hrows.append({"sym": sym[:-3], "chg": round(chg, 2), "yon": yon, "cur": cur})
            except Exception:
                pass
            prog.progress((i+1)/len(_hl), text=f"{i+1}/{len(_hl)} {sym}")
        prog.empty()
        if hrows:
            import plotly.graph_objects as _go
            labels = [f"{h['sym']}<br>{h['chg']:+.1f}%<br>{'🟢' if h['yon']=='LONG' else ('🔴' if h['yon']=='SHORT' else '—')}"
                      for h in hrows]
            fig = _go.Figure(_go.Treemap(
                labels=labels, parents=[""]*len(hrows),
                values=[1]*len(hrows),
                marker=dict(colors=[h["chg"] for h in hrows], colorscale="RdYlGn",
                            cmid=0, cmin=-6, cmax=6, line=dict(width=1, color="#131722")),
                textfont=dict(size=14), hoverinfo="label",
            ))
            fig.update_layout(height=600, margin=dict(t=10, l=0, r=0, b=0),
                paper_bgcolor="#131722", font=dict(color="#fff"))
            st.plotly_chart(fig, use_container_width=True)
            nL = sum(1 for h in hrows if h["yon"] == "LONG"); nS = sum(1 for h in hrows if h["yon"] == "SHORT")
            up = sum(1 for h in hrows if h["chg"] > 0)
            st.caption(f"{len(hrows)} hisse · 🟢 OTT LONG: {nL} · 🔴 SHORT: {nS} · "
                        f"günlük artıda: {up}/{len(hrows)}. Renk=% değişim, etiket=OTT+TOTT yönü.")
        else:
            st.warning("Veri çekilemedi.")


with tab_emtia:
    st.subheader("🥇 Emtia / Forex — GCM Forex enstrümanları")
    st.caption("GOLD · Silver · Palladium · EUR/USD · GBP/USD. "
                "Metaller trend yapar (sistem çalışır), forex yatay (zayıf sinyal).")

    with st.expander("ℹ️ Beklenti"):
        st.markdown("""
        | Sembol | Sistem uyumu |
        |---|---|
        | 🥇 GOLD / Silver / Palladium | ✅ Trend takipçi → çalışır (backtest İYİ/MÜKEMMEL) |
        | 💱 EUR/USD · GBP/USD | ⚠️ Mean-reverting (yatay) → zayıf sinyal, edge düşük |

        Forex majorleri trend yapmaz, OTT trend takipçi → forex'te az/sahte sinyal.
        Metaller asıl odak. Bunlar **GCM Forex**'te işlem görür (VIOP değil).
        """)

    if st.button("🔄 Emtia/Forex tara", type="primary", use_container_width=True,
                  key="emtia_scan"):
        st.cache_data.clear()
        em_prog = st.progress(0, text="0/5")
        em_rows = []
        for i, sym in enumerate(EMTIA_FX):
            r = analyze_intraday(sym)
            if r:
                cur = r["Fiyat"]
                durum = r["Durum"]
                if "LONG" in durum:
                    stop = r["Tetik ↓"]
                elif "SHORT" in durum:
                    stop = r["Tetik ↑"]
                else:
                    stop = None
                em_rows.append({
                    "Sembol": EMTIA_FX_ADI.get(sym, sym),
                    "Güven": r["Güven"],
                    "Durum": durum,
                    "Fiyat": cur,
                    "Direnç": r.get("Direnç"),
                    "Destek": r.get("Destek"),
                    "Stop (TOTT)": stop,
                    "BT Getiri %": r["BT Getiri %"],
                    "BT PF": r["BT PF"],
                    "BT Win %": r["BT Win %"],
                })
            em_prog.progress((i+1)/len(EMTIA_FX), text=f"{i+1}/5 {sym}")
        em_prog.empty()

        if em_rows:
            df_em = pd.DataFrame(em_rows)
            st.dataframe(
                df_em.style.format({
                    "Fiyat": "{:.4f}",
                    "Direnç": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                    "Destek": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                    "Stop (TOTT)": lambda v: f"{v:.4f}" if pd.notna(v) else "-",
                    "BT Getiri %": lambda v: f"{v:+.1f}%" if pd.notna(v) else "-",
                    "BT PF": lambda v: ("∞" if v >= 900 else f"{v:.2f}") if pd.notna(v) else "-",
                    "BT Win %": lambda v: f"{v:.0f}%" if pd.notna(v) else "-",
                }),
                use_container_width=True, height=250,
            )
            st.caption("⚠️ BT (backtest) rakamları in-sample (iyimser). "
                        "Forex satırları zayıf — metallere odaklan. "
                        "Gerçek kanıt için Canlı Performans sekmesini bekle.")
        else:
            st.warning("Veri çekilemedi.")
    else:
        st.info("👆 **Emtia/Forex tara** butonuna bas. 5 sembol, ~30 sn.")


# ──────────────────────────────────────────────────────────────────
#  TAB: CRYPTO (4h) — sadece güvenilir / trade edilebilir coinler
# ──────────────────────────────────────────────────────────────────
with tab_crypto:
    st.subheader("🪙 Crypto — 4 saatlik (4h) timeframe")
    st.caption("Crypto'da 30dk çok gürültülü → **4h** büyük trendleri yakalar. "
                "Burada **sadece güvenilir (trade edilebilir) coinler** listelenir; "
                "Grid'e göre UYUMSUZ/zayıf coinler gizlenir.")

    # Güvenilir coin = Grid rating İYİ/MÜKEMMEL/ORTA. Bayes uyumu ayrıca işaretlenir.
    _grid = _load_per_sym()
    _bayes = _load_bayes_sym()
    _GOOD = {"MÜKEMMEL", "İYİ", "ORTA"}

    reliable = []
    for sym in CRYPTO:
        g = _grid.get(sym)
        if not (g and g.get("ok")):
            continue
        grt = g.get("rating", "?")
        if grt not in _GOOD:
            continue  # UYUMSUZ / MARJINAL / VERİ_AZ → gizle
        b = _bayes.get(sym)
        brt = b.get("rating", "?") if (b and b.get("ok")) else "?"
        # Konsensüs: hem Grid hem Bayes iyi → güçlü; sadece Grid → orta güven
        consensus = "🤝 Güçlü" if brt in _GOOD else "👍 Grid"
        reliable.append((sym, grt, brt, consensus))

    if not reliable:
        st.warning("Henüz güvenilir coin yok. 4h optimize sonuçları yüklenince burada görünecek. "
                    "(Arka planda 4h optimize çalışıyor olabilir.)")
    else:
        st.success(f"**{len(reliable)} güvenilir coin** (Grid İYİ/MÜKEMMEL/ORTA) — "
                    f"toplam {len(CRYPTO)} coin tarandı, gerisi gizlendi.")

        with st.expander("ℹ️ Neden bunlar?"):
            st.markdown("""
            - **🤝 Güçlü** = Grid (FY) **ve** Bayes ikisi de bu coin'i iyi buluyor → konsensüs var.
            - **👍 Grid** = sadece Grid iyi buluyor (Bayes katılmıyor) → daha temkinli ol.
            - Timeframe **4h** sabit (crypto 7/24, 30dk gürültüsü elendi).
            - ⚠️ BT (backtest) rakamları **in-sample** (iyimser). Gerçek kanıt → Canlı Performans.
            """)

        if st.button("🔄 Güvenilir coinleri tara (4h)", type="primary",
                      use_container_width=True, key="crypto_scan"):
            st.cache_data.clear()
            cr_prog = st.progress(0, text=f"0/{len(reliable)}")
            cr_rows = []
            for i, (sym, grt, brt, cons) in enumerate(reliable):
                r = analyze_intraday(sym)  # interval=None → 4h (best_interval_for)
                if r:
                    durum = r["Durum"]
                    if "LONG" in durum:
                        stop = r["Tetik ↓"]
                    elif "SHORT" in durum:
                        stop = r["Tetik ↑"]
                    else:
                        stop = None
                    cr_rows.append({
                        "Coin": sym.replace("-USD", ""),
                        "Konsensüs": cons,
                        "Güven": r["Güven"],
                        "Durum": durum,
                        "Fiyat": r["Fiyat"],
                        "Direnç": r.get("Direnç"),
                        "Destek": r.get("Destek"),
                        "Stop (TOTT)": stop,
                        "BT Getiri %": r["BT Getiri %"],
                        "BT PF": r["BT PF"],
                        "BT Win %": r["BT Win %"],
                    })
                cr_prog.progress((i+1)/len(reliable), text=f"{i+1}/{len(reliable)} {sym}")
            cr_prog.empty()

            if cr_rows:
                df_cr = pd.DataFrame(cr_rows)
                # Sinyali olanlar üstte (AÇ > TUT > bekle)
                _order = {"🟢": 0, "🔴": 0, "🟡": 1}
                df_cr["_o"] = df_cr["Durum"].str[0].map(lambda c: _order.get(c, 2))
                df_cr = df_cr.sort_values(["_o", "Konsensüs"]).drop(columns="_o")
                st.dataframe(
                    df_cr.style.format({
                        "Fiyat": lambda v: f"{v:,.4f}" if pd.notna(v) else "-",
                        "Direnç": lambda v: f"{v:,.4f}" if pd.notna(v) else "-",
                        "Destek": lambda v: f"{v:,.4f}" if pd.notna(v) else "-",
                        "Stop (TOTT)": lambda v: f"{v:,.4f}" if pd.notna(v) else "-",
                        "BT Getiri %": lambda v: f"{v:+.0f}%" if pd.notna(v) else "-",
                        "BT PF": lambda v: ("∞" if v >= 900 else f"{v:.1f}") if pd.notna(v) else "-",
                        "BT Win %": lambda v: f"{v:.0f}%" if pd.notna(v) else "-",
                    }),
                    use_container_width=True, height=min(60 + 36*len(df_cr), 600),
                )
                st.caption("⚠️ 4h sinyaller daha **seyrek** ama daha kaliteli. "
                            "Mum 4 saatte bir kapanır → sinyaller yavaş ama gürültüsüz.")
            else:
                st.warning("Veri çekilemedi.")
        else:
            st.info(f"👆 **Güvenilir coinleri tara** butonuna bas. "
                    f"{len(reliable)} coin × 4h, ~{len(reliable)*6}sn.")


# ──────────────────────────────────────────────────────────────────
#  TAB: OTT + TOTT TEYİT — sıralı teyit (OTT sinyali → peşinde aynı yön TOTT)
# ──────────────────────────────────────────────────────────────────
with tab_otttott:
    st.subheader("🔗 OTT + TOTT Sıralı Teyit")
    st.caption("Sadece OTT ve TOTT. Kural: OTT bir sinyal verir → **hemen peşindeki "
                "TOTT AYNI yönde** onaylarsa sinyal geçerli. OTT ters dönerse (long→short) "
                "araya giren ters TOTT teyidi **sayılmaz**. Aynı formül/timeframe (H1).")

    import ott_tott_confirm as otc

    _allsyms = sorted(set(BIST + list(GCM_NASDAQ) + CRYPTO + COMMODITY + EMTIA_FX))
    _grid_ot = _load_per_sym()

    # ── Timeframe seçici (sadece bu OTT+TOTT görünümü için; ana sistem H1 kalır)
    ot_tf = st.radio("Zaman dilimi", ["15m", "1h"], horizontal=True, key="otc_tf",
                      format_func=lambda x: "M15 (15 dk)" if x == "15m" else "H1 (saatlik)")

    # ── TÜM BIST taraması (M15/H1 OTT+TOTT — her hissenin güncel yönü)
    with st.expander("📋 Tüm BIST OTT+TOTT taraması", expanded=True):
        _cc1, _cc2 = st.columns(2)
        with _cc1:
            _scan_spot = st.checkbox("Spot karşılaştırma da göster (yavaşlatır)", value=False, key="otc_scan_spot")
        with _cc2:
            _scan_fresh = st.checkbox("Taze veri (önbelleği temizle)", value=False, key="otc_scan_fresh",
                                       help="Kapalıyken son 2 dk'lık önbellekten gelir → çok hızlı")
        if st.button(f"🔄 Tüm BIST'i tara ({ot_tf})", type="primary",
                      use_container_width=True, key="otc_bist_scan"):
            if _scan_fresh:
                st.cache_data.clear()
            bist_list = [s for s in BIST if not _is_uyumsuz(s)]
            prog = st.progress(0, text="0")
            scan_rows = []
            def _last_sig(close):
                """Sıralı OTT+TOTT son sinyali: (yön, tz'siz tarih, fiyat, toplam sinyal) | None."""
                rr = otc.compute(close, otc.TV_LENGTH, otc.TV_PERCENT, otc.TV_COEFF)
                cfx = rr[rr["confirm"].notna()]
                if not len(cfx):
                    return None
                ld = cfx["confirm"].iloc[-1]; lt = cfx.index[-1]
                _ts = pd.Timestamp(lt)
                if _ts.tz is not None:
                    _ts = _ts.tz_localize(None)
                return (ld, _ts, float(cfx["close"].iloc[-1]), len(cfx))

            for i, sym in enumerate(bist_list):
                try:
                    # FUTURES (işlem yapılan) — birincil, önbellekli + 2000 bar (hızlı)
                    df_f = fetch_fut_cached(sym, ot_tf, 2000)
                    df_s = fetch_yf(sym, interval=ot_tf, n_bars=2000) if _scan_spot else None   # SPOT opsiyonel
                    fut = _last_sig(df_f["close"]) if (df_f is not None and not df_f.empty and len(df_f) > 200) else None
                    spt = _last_sig(df_s["close"]) if (df_s is not None and not df_s.empty and len(df_s) > 200) else None
                    if fut is None and spt is None:
                        continue
                    # Anlık fiyat: futures öncelik
                    curx = float(df_f["close"].iloc[-1]) if (df_f is not None and not df_f.empty) else \
                           (float(df_s["close"].iloc[-1]) if not df_s.empty else None)
                    row = {"Sembol": sym}
                    if fut:
                        fl, ft, fp, fn = fut
                        pl = (curx/fp-1)*100 if fl == "LONG" else (fp/curx-1)*100
                        row.update({
                            "Futures Yön": "🟢 LONG" if fl == "LONG" else "🔴 SHORT",
                            "Futures Tarih": ft, "Futures Fiyat": fp,
                            "Futures Sinyalden %": round(pl, 1) if curx else None,
                            "Yön değişimi": fn,
                        })
                    else:
                        row.update({"Futures Yön": "—", "Futures Tarih": pd.NaT,
                                     "Futures Fiyat": None, "Futures Sinyalden %": None, "Yön değişimi": None})
                    if spt:
                        sl, st_, sp, sn = spt
                        row.update({"Spot Yön": "🟢 LONG" if sl == "LONG" else "🔴 SHORT",
                                     "Spot Tarih": st_})
                    else:
                        row.update({"Spot Yön": "—", "Spot Tarih": pd.NaT})
                    row["Anlık"] = curx
                    scan_rows.append(row)
                except Exception:
                    pass
                prog.progress((i+1)/len(bist_list), text=f"{i+1}/{len(bist_list)} {sym}")
            prog.empty()
            if scan_rows:
                df_sc = pd.DataFrame(scan_rows).sort_values("Futures Yön").reset_index(drop=True)
                nL = (df_sc["Futures Yön"] == "🟢 LONG").sum()
                nS = (df_sc["Futures Yön"] == "🔴 SHORT").sum()
                # Futures vs Spot yön uyuşmazlığı (dikkat çekici)
                _uy = ((df_sc["Futures Yön"] != df_sc["Spot Yön"]) &
                        (df_sc["Spot Yön"] != "—") & (df_sc["Futures Yön"] != "—")).sum()
                c1, c2, c3 = st.columns(3)
                c1.metric("🟢 Futures LONG", int(nL)); c2.metric("🔴 Futures SHORT", int(nS))
                c3.metric("⚠️ Fut≠Spot", int(_uy), help="Futures ile spot yönü farklı olan hisse sayısı")
                df_show = df_sc[["Sembol", "Futures Yön", "Futures Tarih", "Futures Fiyat",
                                  "Anlık", "Futures Sinyalden %", "Spot Yön", "Spot Tarih",
                                  "Yön değişimi"]]
                st.dataframe(
                    df_show.style.format({
                        "Futures Fiyat": "{:.2f}", "Anlık": "{:.2f}",
                        "Futures Sinyalden %": "{:+.1f}%",
                    }).background_gradient(subset=["Futures Sinyalden %"], cmap="RdYlGn", vmin=-8, vmax=8),
                    use_container_width=True, height=560, hide_index=True,
                    column_config={
                        "Futures Yön": st.column_config.TextColumn("Futures Yön", help="VIOP futures (işlem yaptığın)"),
                        "Futures Tarih": st.column_config.DatetimeColumn(
                            "Futures Tarih", format="DD/MM HH:mm",
                            help="Futures OTT+TOTT teyit anı (TradingView ile aynı)"),
                        "Spot Yön": st.column_config.TextColumn("Spot Yön", help="Spot (.IS) — karşılaştırma"),
                        "Spot Tarih": st.column_config.DatetimeColumn(
                            "Spot Tarih", format="DD/MM HH:mm", help="Spot teyit anı"),
                        "Yön değişimi": st.column_config.NumberColumn(
                            "Yön değişimi",
                            help="Futures'ta kaç kez yön değişti. Yüksek=çalkantılı, düşük=trendli"),
                    })
                st.caption(f"{ot_tf} OTT+TOTT sıralı teyit — **Futures = işlem yaptığın, TradingView ile aynı.** "
                            "Spot karşılaştırma için. 📅 Tarihe tıkla → kronolojik sıra. "
                            "⚠️ Fut≠Spot olanlarda futures'ı baz al (gerçek işlem orada).")
            else:
                st.warning("Veri çekilemedi.")

    st.markdown("### 🔍 Tek sembol detayı")
    # Varsayılan: güvenilir çekirdekten ASELS
    _def = "ASELS.IS" if "ASELS.IS" in _allsyms else _allsyms[0]
    ot_sym = st.selectbox("Sembol", _allsyms, index=_allsyms.index(_def), key="otc_sym")

    if st.button("🔗 OTT+TOTT teyit sinyallerini getir", type="primary",
                  use_container_width=True, key="otc_btn"):

        def _otc_render(df_src, baslik, anahtar):
            """Bir veri kaynağı (futures/spot) için sıralı OTT+TOTT teyit görünümü."""
            if df_src is None or df_src.empty or len(df_src) < 300:
                st.warning(f"{baslik}: veri çekilemedi.")
                return
            r = otc.compute(df_src["close"], otc.TV_LENGTH, otc.TV_PERCENT, otc.TV_COEFF)
            cs = otc.confirmed_signals(r)
            cur_price = float(df_src["close"].iloc[-1])
            cur_dir = cs["yon"].iloc[-1] if len(cs) else None
            last = cs.iloc[-1] if len(cs) else None
            m1, m2, m3 = st.columns(3)
            m1.metric("Güncel yön", "🟢 LONG" if cur_dir == "LONG" else ("🔴 SHORT" if cur_dir == "SHORT" else "—"))
            if last is not None:
                m2.metric("Son sinyal", f"{last.name:%d/%m %H:%M}", f"@ {last['price']:.2f}")
            m3.metric("Anlık fiyat", f"{cur_price:.2f}",
                      f"{(cur_price/last['price']-1)*100:+.1f}%" if last is not None else None)
            prices = cs["price"].tolist()
            sonuc = []
            for k in range(len(cs)):
                nxt = prices[k+1] if k+1 < len(prices) else cur_price
                e = prices[k]; yon = cs["yon"].iloc[k]
                sonuc.append(round((nxt - e)/e*100 if yon == "LONG" else (e - nxt)/e*100, 1))
            cs2 = cs.copy(); cs2["sonuc"] = sonuc
            show = cs2.tail(30).iloc[::-1].copy()
            show["Tarih"] = [f"{i:%d/%m/%Y %H:%M}" for i in show.index]
            show["Yön"] = show["yon"].map({"LONG": "🟢 LONG", "SHORT": "🔴 SHORT"})
            st.dataframe(
                show[["Tarih", "Yön", "price", "sonuc"]].rename(
                    columns={"price": "Fiyat", "sonuc": "Sonraki sinyale dek %"}).style.format(
                    {"Fiyat": "{:.2f}", "Sonraki sinyale dek %": "{:+.1f}%"}).background_gradient(
                    subset=["Sonraki sinyale dek %"], cmap="RdYlGn", vmin=-8, vmax=8),
                use_container_width=True, height=420, hide_index=True, key=f"otc_tbl_{anahtar}")
            wins = sum(1 for x in sonuc if x > 0)
            st.caption(f"📊 {len(cs)} sinyal · kazanan {wins}/{len(cs)} "
                        f"(%{100*wins/max(len(cs),1):.0f}) · toplam {sum(sonuc):+.0f}%")

        _is_bist = ot_sym.upper().endswith(".IS")
        with st.spinner(f"{ot_sym} OTT+TOTT hesaplanıyor ({ot_tf})..."):
            df_spot = fetch_yf(ot_sym, interval=ot_tf)
            df_fut = ds_fetch_futures(ot_sym, interval=ot_tf) if _is_bist else None

        st.caption("✅ Sıralı teyit (OTT sinyali → peşinde TOTT onayı) + Pine param "
                    "(L=40 %=1 coeff=0.001). ⚠️ SADECE OTT+TOTT (rejim/SOTT/HOTT/ROTT yok).")

        if _is_bist and df_fut is not None and not df_fut.empty:
            base = ot_sym[:-3]
            tab_f, tab_s = st.tabs([f"🎯 FUTURES ({base}1!) — işlem yaptığın", f"📈 SPOT ({ot_sym})"])
            with tab_f:
                st.info("Bu, TradingView'da gördüğün ve VIOP'ta işlem yaptığın futures kontratı. "
                        "Grafiğinle birebir aynı sinyal saati.")
                _otc_render(df_fut, "Futures", "fut")
            with tab_s:
                st.caption("Spot fiyat (.IS). Choppy bölgede futures'tan birkaç bar farklı olabilir.")
                _otc_render(df_spot, "Spot", "spot")
        else:
            _otc_render(df_spot, "Spot", "spot")
    else:
        st.info("👆 Sembol seç + butona bas. BIST hisselerinde **Futures** (işlem yaptığın, "
                "TradingView grafiğinle aynı) ve **Spot** sekmeleri ayrı gösterilir.")


# ──────────────────────────────────────────────────────────────────
#  TAB: AKTİF/SCALP (15m) — kısa parametreli yüksek frekans, OOS-doğrulanmış
# ──────────────────────────────────────────────────────────────────
with tab_scalp:
    st.subheader("⚡ Aktif/Scalp — 15m, sık sinyal")
    st.caption("Kısa parametreli OTT+TOTT (15m futures). Ana swing sisteminden AYRI bir mod: "
                "daha sık işlem, daha ince edge. Maliyete duyarlı.")
    with st.expander("⚠️ Bu sekmeyi kullanmadan önce OKU", expanded=False):
        st.markdown("""
        - **Gerçek scalp (5m) DEĞİL** — test 5m'de edge'in öldüğünü gösterdi. Bu 15m, kısa param.
        - Semboller **train/test (OOS) ayrımıyla** seçildi: parametre verinin %70'inde optimize,
          %30'unda (görülmemiş) doğrulandı. Sadece OOS'ta edge'i tutanlar burada.
        - **Edge ince** (PF ~1.2-2). Ana sistemden (PF ~2.8) zayıf ama çok daha sık.
        - **Maliyet kritik:** %0.05 tek yön varsayımıyla kârlı. Komisyonun yüksekse edge buharlaşır.
        - **Garanti değil:** 45 sembol × 60 param denendi; OOS geçişlerin bir kısmı şans olabilir.
          Canlı sonucu izle, körü körüne güvenme. Stop yok — strateji kendi sinyaliyle çıkar.
        """)
    try:
        import json as _json, os as _os
        _scalp = _json.load(open("per_symbol_scalp_15m.json", encoding="utf-8")) if _os.path.exists("per_symbol_scalp_15m.json") else {}
    except Exception:
        _scalp = {}

    if not _scalp:
        st.warning("Scalp optimize verisi yok. `python optimize_scalp_15m.py` çalıştır.")
    else:
        _rate = st.radio("Hangi semboller?", ["İYİ", "İYİ + ORTA", "Hepsi"], horizontal=True, key="scalp_rate")
        _allow = {"İYİ"} if _rate == "İYİ" else ({"İYİ", "ORTA"} if _rate == "İYİ + ORTA" else None)
        _syms = [s for s in _scalp if (_allow is None or _scalp[s].get("rating") in _allow)]
        st.caption(f"{len(_syms)} sembol · OOS-doğrulanmış · 15m futures")

        if st.button(f"⚡ Scalp sinyallerini tara ({len(_syms)} sembol)", type="primary",
                      use_container_width=True, key="scalp_scan"):
            rows = []; prog = st.progress(0, text="0")
            for i, sym in enumerate(_syms):
                try:
                    p = _scalp[sym]["params"]
                    d = fetch_fut_cached(sym, "15m", 2000)
                    if d is not None and not d.empty and len(d) > 200:
                        rr = otc.compute(d["close"], p["trend_length"], p["trend_percent"], p["tott_coeff"])
                        cfx = rr[rr["confirm"].notna()]
                        if len(cfx):
                            ld = cfx["confirm"].iloc[-1]; lt = cfx.index[-1]; lpr = float(cfx["close"].iloc[-1])
                            curx = float(d["close"].iloc[-1])
                            pl = (curx/lpr-1)*100 if ld == "LONG" else (lpr/curx-1)*100
                            _ts = pd.Timestamp(lt)
                            if _ts.tz is not None: _ts = _ts.tz_localize(None)
                            rows.append({
                                "Sembol": sym, "Yön": "🟢 LONG" if ld == "LONG" else "🔴 SHORT",
                                "Sinyal Tarihi": _ts, "Sinyal Fiyatı": lpr, "Anlık": curx,
                                "Sinyalden %": round(pl, 1),
                                "OOS PF": _scalp[sym]["oos_pf"], "Rating": _scalp[sym]["rating"],
                                "Param": f"L{p['trend_length']}/%{p['trend_percent']:.0f}/{p['tott_coeff']}",
                            })
                except Exception:
                    pass
                prog.progress((i+1)/len(_syms), text=f"{i+1}/{len(_syms)} {sym}")
            prog.empty()
            if rows:
                dfx = pd.DataFrame(rows).sort_values(["Yön", "Sinyal Tarihi"], ascending=[True, False]).reset_index(drop=True)
                nL = (dfx["Yön"] == "🟢 LONG").sum(); nS = (dfx["Yön"] == "🔴 SHORT").sum()
                c1, c2 = st.columns(2); c1.metric("🟢 LONG", int(nL)); c2.metric("🔴 SHORT", int(nS))
                st.dataframe(
                    dfx.style.format({"Sinyal Fiyatı": "{:.2f}", "Anlık": "{:.2f}",
                                       "Sinyalden %": "{:+.1f}%", "OOS PF": "{:.2f}"})
                       .background_gradient(subset=["Sinyalden %"], cmap="RdYlGn", vmin=-5, vmax=5),
                    use_container_width=True, height=560, hide_index=True,
                    column_config={
                        "Sinyal Tarihi": st.column_config.DatetimeColumn("Sinyal Tarihi", format="DD/MM HH:mm",
                            help="15m OTT+TOTT teyit anı (kısa param)"),
                        "OOS PF": st.column_config.NumberColumn("OOS PF", help="Out-of-sample profit factor (yüksek=güvenilir)"),
                    })
                st.caption("⚡ 15m kısa-param OTT+TOTT · semboller OOS-doğrulanmış · maliyet %0.05 varsayımı. "
                            "📅 Tarihe tıkla → kronolojik. Stop yok; ters sinyalde çık.")
            else:
                st.warning("Veri çekilemedi.")


with tab_live:
    st.subheader("✅ Canlı Performans — Forward Validation")
    st.caption("Backtest rating'i (MÜKEMMEL) geçmişe bakar, overfit olabilir. "
                "Bu sekme botun **gerçek zamanlı sinyallerinin canlı sonucunu** gösterir. "
                "Asıl güven göstergesi budur.")

    # ── Otomatik yenileme — tıklamadan veriyi tazele
    _ar1, _ar2 = st.columns([1, 3])
    with _ar1:
        auto_refresh = st.toggle("🔄 Otomatik yenile", value=False, key="live_autorefresh",
                                  help="Açıkken sayfa periyodik kendini yeniler, "
                                       "sen tıklamadan canlı veri güncellenir.")
    with _ar2:
        refresh_sec = st.select_slider("Aralık (sn)", options=[30, 60, 120, 300],
                                        value=60, key="live_refresh_sec",
                                        disabled=not auto_refresh)
    if auto_refresh:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=refresh_sec * 1000, key="live_ar_tick")
            st.caption(f"⏱️ Her {refresh_sec} sn'de otomatik yenileniyor "
                        f"(son: {pd.Timestamp.now(tz='Europe/Istanbul'):%H:%M:%S}).")
        except Exception:
            st.caption("⚠️ Otomatik yenileme bileşeni yüklenemedi (deploy sonrası aktif olur).")

    with st.expander("ℹ️ Bu nasıl çalışır?"):
        st.markdown("""
        - Bot her tarama'da (GitHub Actions, saatte birkaç kez) her sembolün **anlık durumunu** kaydeder
        - LONG AÇ → giriş, LONG ÇIK → çıkış olarak **trade'leri yeniden kurar**
        - Her sembolün **canlı PF / win rate**'ini biriktirir
        - **MÜKEMMEL rating yerine** buradaki gerçek sonuca güven

        ⚠️ **Veri birikmesi 2-4 hafta sürer.** Sembol başına ≥5 trade olunca anlamlı olur.
        Henüz az trade varsa rakamlar güvenilmez — sabırlı ol.

        🎯 **Hedef:** Canlı PF > 1.2-1.5 kalan semboller = gerçekten çalışan sistem.
        """)

    try:
        import forward_validation as fv
        live_all = fv.all_live_stats(last_n=30)
        open_pos = fv.open_positions()
    except Exception as e:
        live_all = {}
        open_pos = {}
        st.error(f"Forward-validation modülü yüklenemedi: {e}")

    # ── Kategori filtresi (BIST / NASDAQ / CRYPTO / EMTIA) — #61 + Crypto + Emtia
    live_cat = st.radio("Piyasa", ["🇹🇷 BIST", "🇺🇸 NASDAQ", "🪙 Crypto", "🥇 Emtia/Forex"],
                         horizontal=True, key="live_cat")
    _bist_set = set(BIST)
    _crypto_set = set(CRYPTO)
    _emtia_set = set(EMTIA_FX)
    def _in_cat(sym):
        if live_cat == "🇹🇷 BIST":
            return sym in _bist_set
        elif live_cat == "🇺🇸 NASDAQ":
            return sym in GCM_NASDAQ
        elif live_cat == "🪙 Crypto":
            return sym in _crypto_set
        else:  # Emtia/Forex
            return sym in _emtia_set

    # Sadece trade'i olan + seçili kategorideki semboller
    live_rows = []
    for sym, s in live_all.items():
        if s["n"] > 0 and _in_cat(sym):
            live_rows.append({
                "Sembol": sym,
                "Canlı Trade": s["n"],
                "Canlı Win %": s["win_rate"],
                "Canlı PF": s["pf"],
                "Ort. Trade %": s["avg"],
                "Toplam %": s["total"],
            })
    # Açık pozisyonları da kategoriye göre filtrele
    open_pos = {k: v for k, v in open_pos.items() if _in_cat(k)}

    # ── AÇIK POZİSYONLAR — HER ZAMAN göster (kapanmış işlem olmasa da)
    #    Bot girdi, işlem DEVAM EDİYOR. Telegram'a "açıldı" bildirimi gelen
    #    pozisyonlar burada görünür (önceden else bloğunda gizliydi → bug).
    st.markdown(f"### 📂 Açık Pozisyonlar ({len(open_pos)}) — bot girdi, devam ediyor")
    st.caption("Bot bu pozisyonları açtı, henüz kapatmadı. 🛑 Stop = TOTT trail "
                "(bot sabit TP koymaz — trend takipçi, ÇIK sinyaline kadar tutar).")
    if not open_pos:
        st.write("Şu an bu kategoride açık pozisyon yok.")
    else:
        # Anlık fiyat HER ZAMAN gösterilir (giriş yanında). live_price 45 sn cache'li
        # → tekrar render'larda hızlı. "Fiyatı tazele" cache'i temizler.
        if st.button("🔄 Fiyatı tazele (cache temizle)", key="live_price_refresh"):
            live_price.clear()
        op_rows = []
        with st.spinner(f"{len(open_pos)} pozisyonun anlık fiyatı çekiliyor…"):
            for s, v in open_pos.items():
                cp = None
                try:
                    cp = live_price(s)   # hafif, 45 sn cache → anlık fiyat
                except Exception:
                    pass
                row = {
                    "Sembol": s,
                    "Yön": "🟢 LONG" if v["side"] == "LONG" else "🔴 SHORT",
                    "Giriş": v["entry_price"],
                    "Anlık Fiyat": cp,
                    "Yüzen P&L %": None,
                    "Stop (TOTT)": v.get("stop"),
                    "Stop'a %": None,
                    "Açılış": v.get("entry_ts", "")[:16].replace("T", " "),
                }
                if cp:
                    if v["side"] == "LONG":
                        row["Yüzen P&L %"] = round((cp - v["entry_price"]) / v["entry_price"] * 100, 2)
                    else:
                        row["Yüzen P&L %"] = round((v["entry_price"] - cp) / v["entry_price"] * 100, 2)
                    stp = v.get("stop")
                    if stp:
                        if v["side"] == "LONG":
                            row["Stop'a %"] = round((cp / stp - 1) * 100, 2)
                        else:
                            row["Stop'a %"] = round((stp / cp - 1) * 100, 2)
                op_rows.append(row)
        df_op = pd.DataFrame(op_rows)
        styler = df_op.style.format({
            "Giriş": "{:.4f}",
            "Anlık Fiyat": lambda x: f"{x:.4f}" if pd.notna(x) else "-",
            "Yüzen P&L %": lambda x: f"{x:+.2f}%" if pd.notna(x) else "-",
            "Stop (TOTT)": lambda x: f"{x:.4f}" if pd.notna(x) else "-",
            "Stop'a %": lambda x: f"{x:+.2f}%" if pd.notna(x) else "-",
        }).background_gradient(subset=["Yüzen P&L %"], cmap="RdYlGn", vmin=-5, vmax=5)
        st.dataframe(styler, use_container_width=True, height=400)
        st.caption(f"💹 Anlık fiyatlar (≤45 sn taze) — "
                    f"son: {pd.Timestamp.now(tz='Europe/Istanbul'):%H:%M:%S}. "
                    "Sürekli akış için üstte **🔄 Otomatik yenile**'yi aç.")

    st.markdown("---")
    if not live_rows:
        st.info("📊 Henüz **kapanmış** işlem yok (açık pozisyonlar yukarıda görünür).\n\n"
                "Kapanmış trade istatistikleri (PF/win rate) ilk pozisyonlar "
                "kapandıkça **birkaç gün–hafta** içinde birikecek.")
    else:
        df_live = pd.DataFrame(live_rows).sort_values("Canlı PF", ascending=False).reset_index(drop=True)

        # Min trade filtresi
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            min_n = st.slider("Min canlı trade sayısı", 1, 20, 5, key="live_min_n",
                               help="Bu kadar trade'i olmayan semboller gizlenir (anlamsız)")
        with fcol2:
            min_pf = st.slider("Min canlı PF", 0.0, 3.0, 1.2, 0.1, key="live_min_pf",
                                help="Bu PF'in altındaki semboller gizlenir")

        df_show = df_live[(df_live["Canlı Trade"] >= min_n) & (df_live["Canlı PF"] >= min_pf)]

        m1, m2, m3 = st.columns(3)
        m1.metric("Takip edilen sembol", len(df_live))
        m2.metric(f"Filtreyi geçen (PF≥{min_pf})", len(df_show))
        m3.metric("Açık pozisyon", len(open_pos))

        if len(df_show) > 0:
            st.markdown(f"### 🏆 Canlı KANITLANMIŞ semboller (PF≥{min_pf}, ≥{min_n} trade)")
            st.dataframe(
                df_show.style.format({
                    "Canlı Win %": "{:.0f}%",
                    "Canlı PF": lambda v: "∞" if v >= 900 else f"{v:.2f}",
                    "Ort. Trade %": "{:+.2f}%",
                    "Toplam %": "{:+.1f}%",
                }).background_gradient(subset=["Canlı PF"], cmap="Greens", vmin=0, vmax=3),
                use_container_width=True, height=400,
            )
            st.success("Bu semboller **canlıda gerçekten** çalışıyor — backtest'e değil, "
                        "gerçek sonuca dayanıyor. Trade için en güvenilir liste.")
        else:
            st.warning(f"Henüz PF≥{min_pf} + {min_n}+ trade kriterini geçen sembol yok. "
                        "Veri birikmeye devam ediyor.")

        with st.expander("📋 Tüm takip edilen semboller (ham)"):
            st.dataframe(
                df_live.style.format({
                    "Canlı Win %": "{:.0f}%",
                    "Canlı PF": lambda v: "∞" if v >= 900 else f"{v:.2f}",
                    "Ort. Trade %": "{:+.2f}%",
                    "Toplam %": "{:+.1f}%",
                }),
                use_container_width=True, height=400,
            )

        # ── İŞLEM DETAYI — botun gerçek al/sat hareketleri
        st.markdown("---")
        st.markdown("### 🔍 İşlem Detayı — botun gerçek al/sat hareketleri")
        st.caption("Bot neyi, ne zaman, hangi fiyattan açtı/kapattı. Her satır bir trade.")

        try:
            all_trades = fv.get_trades()
        except Exception:
            all_trades = []

        if not all_trades:
            st.info("Henüz kapanmış işlem yok.")
        else:
            # Sembol filtresi
            syms_with_trades = sorted(set(t["sym"] for t in all_trades))
            sel_sym = st.selectbox(
                "Sembol seç (hepsi için boş bırak)",
                ["— Tümü —"] + syms_with_trades, key="live_trade_sym")

            trades_show = all_trades if sel_sym == "— Tümü —" \
                else [t for t in all_trades if t["sym"] == sel_sym]

            # Detay tablo
            det_rows = []
            for t in trades_show:
                det_rows.append({
                    "Sembol": t["sym"],
                    "Yön": "🟢 LONG" if t["side"] == "LONG" else "🔴 SHORT",
                    "Açılış Fiyat": t["entry_price"],
                    "Açılış Zamanı": t.get("entry_ts", "")[:16].replace("T", " "),
                    "Kapanış Fiyat": t["exit_price"],
                    "Kapanış Zamanı": t.get("exit_ts", "")[:16].replace("T", " "),
                    "Sonuç %": t["pnl_pct"],
                })
            df_det = pd.DataFrame(det_rows)

            # Özet
            dm1, dm2, dm3 = st.columns(3)
            dm1.metric("İşlem sayısı", len(df_det))
            if len(df_det) > 0:
                dm2.metric("Kazanan", f"{(df_det['Sonuç %'] > 0).sum()}/{len(df_det)}")
                dm3.metric("Toplam %", f"{df_det['Sonuç %'].sum():+.1f}%")

            st.dataframe(
                df_det.style.format({
                    "Açılış Fiyat": "{:.4f}",
                    "Kapanış Fiyat": "{:.4f}",
                    "Sonuç %": "{:+.2f}%",
                }).background_gradient(subset=["Sonuç %"], cmap="RdYlGn", vmin=-5, vmax=5),
                use_container_width=True, height=500,
            )


with tab_info:
    st.subheader("Sistem hakkında")
    st.markdown("""
    ### Kaynak
    - **Sistem:** OTT-ailesi (TOTT + SOTT + HOTT/LOTT + ROTT)
    - **Pine kaynak kodları:** OTT.txt, TOTT.txt, ROTT.txt, SOTT.txt (kullanıcı tarafından sağlandı)
    - **Kombinasyon mantığı:** .docx örneklerinden çıkarıldı (.docx 2 ve 3)

    ### Doğruluk
    - VAR ve OTT port'u Pine-referans implementation ile **birebir** uyumlu (birim testlerle kanıtlandı, `test_unit.py`).

    ### Performans (backtest)
    - **GOLD M15:** 29 ayda **+117.78%**, PF 4.41, Max DD -9.01%, Win %62.7
    - **GOLD M5:** 11 ayda **+46.53%**, PF 3.04, Max DD -9.44%
    - **Forex (GBPUSD/EURGBP):** Sistem **çalışmıyor** (mean-reverting) — kullanma

    ### Walk-forward
    - **GOLD M15:** 10 pencereden 8'i pozitif OOS (%80 tutarlılık)
    - Beklenen yıllık getiri: **+%15-%25 kaldıraçsız**

    ### MT4 Deployment
    - `OTT_GOLD_EA.mq4` MetaTrader 4 Expert Advisor
    - `DEPLOY.txt` kurulum talimatı
    - Risk yönetimi dahil: Daily loss %3, Max DD %15

    ### Klasör
    `C:\\Users\\furka\\Desktop\\ott_bot\\`

    ### Önemli Uyarı ⚠️
    Bu dashboard **sinyal gösterici**dir. Otomatik emir vermez.
    - Tarama → sinyal görme
    - Manuel emir → GCM MT4 veya broker'da
    - Backtest sonuçları geçmişin tekrarı garanti etmez
    """)

    st.markdown("---")
    st.markdown("### 📊 Sembol Kalite Paneli (Bayes backtest istatistikleri)")
    st.caption("Bayes optimize sonucu — her sembolün backtest performansı. "
                "Tablo sıralanabilir, filtreleyebilirsin.")

    _bayes_data = _load_bayes_sym()
    _grid_data  = _load_per_sym()
    if not _bayes_data and not _grid_data:
        st.warning("Optimize verisi yok.")
    else:
        # Tüm sembolleri topla, en iyi rating + en iyi PF
        RT_SCORE = {"MÜKEMMEL": 5, "İYİ": 4, "ORTA": 3,
                     "MARJINAL": 2, "VERİ_AZ": 1, "UYUMSUZ": 0}
        from data_source import category_of as _cat_q
        all_rows = []
        # Sadece tanımlı listeler (JSON'daki eski/artık sembolleri gösterme)
        _defined = set(BIST) | set(GCM_NASDAQ) | set(CRYPTO) | set(COMMODITY)
        all_syms = set(list(_bayes_data.keys()) + list(_grid_data.keys()))
        for sym in all_syms:
            if sym not in _defined:   # tanımlı listede değil → JSON artığı, atla
                continue
            if _is_uyumsuz(sym):   # Grid UYUMSUZ → gösterme
                continue
            # Bayes önceliği
            src = _bayes_data.get(sym) if _bayes_data.get(sym, {}).get("ok") else _grid_data.get(sym)
            if not src or not src.get("ok"):
                continue
            stats = src.get("stats", {})
            rating = src.get("rating", "?")
            all_rows.append({
                "Sembol":   sym,
                "Kategori": _cat_q(sym),
                "GCM":      "✓" if sym in GCM_NASDAQ else "",
                "Rating":   rating,
                "_RtScore": RT_SCORE.get(rating, 0),
                "Win %":    (stats.get("win_rate") or 0) * 100,
                "PF":       (999 if stats.get("pf") is None else stats.get("pf")),
                "Getiri %": (stats.get("return") or 0) * 100,
                "Trade":    int(stats.get("n_trades") or 0),
                "Max DD %": (stats.get("max_dd") or 0) * 100,
            })

        if all_rows:
            qdf = pd.DataFrame(all_rows)
            qdf = qdf.sort_values(["_RtScore", "PF"], ascending=[False, False])

            # Filtre satırı
            qcol1, qcol2, qcol3 = st.columns(3)
            with qcol1:
                _catopts = sorted(qdf["Kategori"].unique())
                qcat = st.multiselect("Kategori", _catopts,
                                        default=[c for c in ["BIST", "NASDAQ"] if c in _catopts] or _catopts,
                                        key="q_cat")
            with qcol2:
                qrt  = st.multiselect("Rating",
                                        ["MÜKEMMEL","İYİ","ORTA","MARJINAL","VERİ_AZ","UYUMSUZ"],
                                        default=["MÜKEMMEL","İYİ","ORTA"], key="q_rt")
            with qcol3:
                qgcm = st.checkbox("Sadece GCM Forex'te olanlar", value=False, key="q_gcm")

            qfiltered = qdf[qdf["Kategori"].isin(qcat) & qdf["Rating"].isin(qrt)]
            if qgcm:
                qfiltered = qfiltered[qfiltered["GCM"] == "✓"]

            # Özet metric
            qm1, qm2, qm3, qm4 = st.columns(4)
            qm1.metric("Sembol", len(qfiltered))
            if len(qfiltered) > 0:
                qm2.metric("Ortalama Win %", f"{qfiltered['Win %'].mean():.0f}%")
                qm3.metric("Ortalama PF",
                            f"{qfiltered[qfiltered['PF'] < 900]['PF'].mean():.2f}")
                qm4.metric("Ortalama Getiri %",
                            f"{qfiltered['Getiri %'].mean():+.1f}%")

            # Tablo
            qshow = qfiltered.drop(columns="_RtScore").reset_index(drop=True)
            st.dataframe(
                qshow.style.format({
                    "Win %": "{:.0f}%",
                    "PF": lambda v: "∞" if v >= 900 else f"{v:.2f}",
                    "Getiri %": "{:+.1f}%",
                    "Max DD %": "{:.1f}%",
                }).background_gradient(subset=["Getiri %"], cmap="RdYlGn", vmin=-30, vmax=100)
                  .background_gradient(subset=["PF"], cmap="Greens", vmin=0, vmax=5),
                use_container_width=True, height=550,
            )

# ──────────────────────────────────────────────────────────────────
#  FOOTER
# ──────────────────────────────────────────────────────────────────
from datetime import datetime as _dt
st.markdown(f"""
<div class="footer-bar">
    <span style="color:#888;">OTT Bot Dashboard</span>
    <span style="margin:0 12px; color:#444;">•</span>
    <span style="color:#26a69a;">●</span> Auto-update aktif
    <span style="margin:0 12px; color:#444;">•</span>
    <span style="color:#888;">{_dt.now().strftime("%Y-%m-%d %H:%M")}</span>
    <span style="margin:0 12px; color:#444;">•</span>
    <span style="color:#666;">OTT-family · Python port · Streamlit</span>
</div>
""", unsafe_allow_html=True)
