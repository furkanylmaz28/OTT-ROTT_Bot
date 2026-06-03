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
from data_source import fetch as ds_fetch


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
    "AKBNK.IS","ARCLK.IS","ASELS.IS","ASTOR.IS","BIMAS.IS","EKGYO.IS",
    "ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","HALKB.IS","ISCTR.IS",
    "KCHOL.IS","KOZAA.IS","KOZAL.IS","MGROS.IS","ODAS.IS","PETKM.IS",
    "PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SKBNK.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TOASO.IS","TTKOM.IS","TUPRS.IS",
    "VAKBN.IS","VESTL.IS","YKBNK.IS",
]
COMMODITY = ["GC=F", "SI=F"]

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
    last = s.iloc[-1]
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
    return {
        "Sembol": symbol,
        "Kategori": _cat(symbol),
        "Güven": guven_label,
        "_GuvenSkor": guven_score,
        "Durum": pos,
        "Fiyat": cur,
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
        Anıl Özekşi <b>OTT-ailesi</b> · TOTT + SOTT + HOTT/LOTT + ROTT
    </div>
    <div style="margin-top:14px;">
        <span class="badge">📡 {_total} sembol</span>
        <span class="badge" style="background:#26a69a22;color:#26a69a;">★ {_iyi} işe yarayan</span>
        <span class="badge" style="background:#ef535022;color:#ef5350;">✗ {_uyumsuz} uyumsuz</span>
        <span class="badge" style="background:#2962ff22;color:#2962ff;">🤖 Auto-update AÇIK</span>
    </div>
</div>
""", unsafe_allow_html=True)

(tab_portfolio, tab_consensus, tab_safe, tab_morning, tab_scan,
 tab_sim, tab_chart, tab_alt, tab_info) = st.tabs([
    "💼  Portföyüm",
    "🤝  Konsensüs Mod",
    "🛡️  Güvenli Mod",
    "🎯  Bugünün Önerileri",
    "📡  Anlık Tarayıcı",
    "📌  Öneriler",
    "📊  Detay Grafik",
    "🧪  Alternatif Bot Portföyü",
    "📖  Bilgi",
])

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
                                lst = s_.iloc[-1]
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
                        if _bayes[s].get("ok") and _grid.get(s, {}).get("ok")]
        # Kategoriye göre filtre (BIST veya NASDAQ butonuna basıldı)
        if cons_category == "BIST":
            common_syms = [s for s in common_syms if s.upper().endswith(".IS")]
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

        for idx, sym in enumerate(common_syms):
            try:
                df_l = fetch_yf(sym, interval=_bif(sym))
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
                lg = _lbl(sg.iloc[-1])
                lb = _lbl(sb.iloc[-1])
                cur = float(df_l["close"].iloc[-1])

                # Konsensüs türü
                if lg == "LONG_AÇ" and lb == "LONG_AÇ":
                    cons_type = "🟢🟢 GÜÇLÜ LONG"
                    side = "LONG"; consensus = True
                elif lg == "SHORT_AÇ" and lb == "SHORT_AÇ":
                    cons_type = "🔴🔴 GÜÇLÜ SHORT"
                    side = "SHORT"; consensus = True
                elif "ÇIK" in lg and "ÇIK" in lb and lg == lb:
                    cons_type = "🟡🟡 HEMEN KAPAT"
                    side = "EXIT"; consensus = True
                elif lg == "LONG_TUT" and lb == "LONG_TUT":
                    cons_type = "🟢 LONG TUT (konsensüs)"
                    side = "LONG"; consensus = True   # iki bot da TUT diyor — konsensüs
                elif lg == "SHORT_TUT" and lb == "SHORT_TUT":
                    cons_type = "🔴 SHORT TUT (konsensüs)"
                    side = "SHORT"; consensus = True
                elif (lg == "LONG_AÇ") != (lb == "LONG_AÇ") or \
                      (lg == "SHORT_AÇ") != (lb == "SHORT_AÇ"):
                    cons_type = "❌ ÇELİŞKİ — ATLA"
                    side = None; consensus = False
                else:
                    cons_type = "⏳ tartışmalı / bekle"
                    side = None; consensus = False

                tott_up_v = float(sb.iloc[-1]["tott_up"]) if not pd.isna(sb.iloc[-1]["tott_up"]) else None
                tott_dn_v = float(sb.iloc[-1]["tott_dn"]) if not pd.isna(sb.iloc[-1]["tott_dn"]) else None
                # Stop seçimi yöne göre (TOTT karşı tetik = trail stop)
                stop = tott_dn_v if side == "LONG" else (tott_up_v if side == "SHORT" else None)
                risk_pct = (abs(cur - stop) / cur * 100) if stop else None

                # ÇIK YAKIN uyarısı — TUT pozisyonlarında trail stop yakınlığı
                if side == "LONG" and "TUT" in cons_type and tott_dn_v:
                    dist_pct = (cur / tott_dn_v - 1) * 100
                    if 0 < dist_pct < warn_thr_cons:
                        cons_type = f"{cons_type}  ⚠️ ÇIK YAKIN ({dist_pct:.2f}%)"
                elif side == "SHORT" and "TUT" in cons_type and tott_up_v:
                    dist_pct = (tott_up_v / cur - 1) * 100
                    if 0 < dist_pct < warn_thr_cons:
                        cons_type = f"{cons_type}  ⚠️ ÇIK YAKIN ({dist_pct:.2f}%)"

                # Pozisyon büyüklüğü — konsensüs varsa daha büyük
                pos_size = cons_capital * (cons_pos_pct / 100) if consensus and side and side != "EXIT" else 0
                max_risk = (pos_size * cons_lev * risk_pct / 100) if pos_size and risk_pct else 0

                # FY ve Bayes rating
                fy_rt = _grid[sym].get("rating", "?")
                bs_rt = _bayes[sym].get("rating", "?")

                cons_rows.append({
                    "Sembol": sym,
                    "Kategori": _cat(sym),
                    "GCM": "✓" if sym in GCM_NASDAQ else "",
                    "FY Bot": lg.replace("_", " "),
                    "Bayes Bot": lb.replace("_", " "),
                    "Konsensüs": cons_type,
                    "Fiyat": cur,
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
                show_cols_s = ["Sembol","Kategori","GCM","Konsensüs","Fiyat","Stop",
                                "Risk %","Pozisyon $","Adet","Max Risk $",
                                "FY Rating","Bayes Rating"]
                st.dataframe(
                    strong[show_cols_s].style.format({
                        "Fiyat":"{:.4f}", "Stop":"{:.4f}",
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

# ──────────────────────────────────────────────────────────────────
#  TAB 0: GÜVENLİ MOD — "terste kalmamak için" katı filtre
# ──────────────────────────────────────────────────────────────────
with tab_safe:
    st.subheader("🛡️ Güvenli Mod — Yalnız Yüksek-Olasılık Pozisyonlar")
    st.caption("Hiçbir trade'de terste kalmamak için çok katı filtreler. Az sinyal, ama güvenilir.")

    with st.expander("ℹ️ Güvenli Mod kuralları"):
        st.markdown("""
        Bir sembol güvenli mod'da çıkması için **TÜM** şu şartları sağlamalı:

        | # | Kriter | Eşik |
        |---|---|---|
        | 1 | Rating | 🏆 **MÜKEMMEL** (sadece) |
        | 2 | Profit Factor | ≥ **3.0** |
        | 3 | Win Rate | ≥ **%60** |
        | 4 | Trade sayısı | ≥ **8** (örneklem yeterli) |
        | 5 | Max Drawdown | ≥ **-20%** (kötü değil) |
        | 6 | Multi-timeframe onayı | H1 yönü + 15dk sinyali **aynı yönde** |
        | 7 | Son 7 gün | sistem o sembolde **pozitif** olmalı |

        **Sonuç:** Günde 0-3 sinyal beklenir. Sıfır olabilir — o gün hiçbir şey yapma.
        Çıkanlar **yüksek olasılıkla** kar getirir (geçmiş performansa göre).

        ⚠️ Hiçbir sistem %100 garanti vermez. Sıkı stop-loss + lot kontrolü mutlaka.
        """)

    # Sabit varsayılanlar (UI kaldırıldı — yalnız sinyaller önemli)
    safe_capital = 1000
    safe_pct     = 10
    safe_lev     = 5

    if st.button("🛡️ Güvenli sinyalleri çıkar", type="primary", use_container_width=True):
        from safe_mode import get_safe_recommendations
        with st.spinner("Multi-timeframe onayı + recent form kontrolü yapılıyor..."):
            recs = get_safe_recommendations()

        if not recs:
            st.warning("🚫 Şu anda güvenli mod kriterlerini geçen sembol yok. "
                       "Bu **iyi haber** — kötü sinyale para yatırmıyorsun. "
                       "Bir kaç saat sonra tekrar dene.")
        else:
            st.success(f"✅ **{len(recs)}** sembol güvenli mod'dan geçti. Hepsi multi-timeframe onaylı.")

            df_safe = pd.DataFrame(recs)
            df_safe["Pozisyon $"] = safe_capital * safe_pct / 100
            df_safe["Max Risk $"] = df_safe.apply(
                lambda r: abs(r["Fiyat"] - r["Stop"]) / r["Fiyat"] * r["Pozisyon $"] * safe_lev
                if r["Stop"] else 0, axis=1)

            show_cols = ["Sembol","Yön","Fiyat","Stop","Pozisyon $","Max Risk $",
                          "BT Getiri %","BT PF","BT Win %","BT Trade","Recent 7g","Onay"]
            st.dataframe(
                df_safe[show_cols].style.format({
                    "Fiyat": "{:.4f}", "Stop": "{:.4f}",
                    "Pozisyon $": "${:.0f}", "Max Risk $": "${:.0f}",
                    "BT Getiri %": "{:+.1f}%", "BT PF": "{:.2f}",
                    "BT Win %": "{:.0f}%", "Recent 7g": "{:+.2f}%",
                }).background_gradient(subset=["BT PF"], cmap="Greens"),
                use_container_width=True, height=400,
            )

            tot_inv = df_safe["Pozisyon $"].sum()
            tot_risk = df_safe["Max Risk $"].sum()
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Toplam yatırım", f"${tot_inv:,.0f}",
                        f"sermayenin {safe_pct * len(recs)}%'i")
            sc2.metric("Toplam max risk", f"${tot_risk:,.0f}",
                        f"{tot_risk/safe_capital*100:.1f}% sermaye")
            sc3.metric("Sinyal sayısı", len(recs))

            st.markdown("---")
            st.markdown(f"""
            ### 📋 İş akışı

            1. Her sembol için **{safe_pct}% pozisyon** aç (${safe_capital * safe_pct / 100:.0f})
            2. **Stop-loss = Stop sütunu** (mutlaka koy!)
            3. Sinyal yönünde gir, sistem çıkış sinyali verene kadar tut
            4. Asla stop'u **gevşetme**. Kayıp = öğrenme parası, hesabı korumak öncelikli.
            """)

# ──────────────────────────────────────────────────────────────────
#  TAB 0: SABAH RİTÜELİ — Bugünün Önerileri
# ──────────────────────────────────────────────────────────────────
with tab_morning:
    # ── Veri yenileme durumu kutusu (üstte)
    import os, json
    from datetime import datetime
    status_box = st.container()
    with status_box:
        cu1, cu2, cu3, cu4 = st.columns([2, 2, 2, 1])
        # Hem Grid hem Bayes optimize verisini topla — en iyi rating'i göster (cache'li)
        psy_path  = "per_symbol_params.json"
        bayes_path = "per_symbol_params_bayes.json"
        psy_data   = _load_per_sym()   if os.path.exists(psy_path) else {}
        bayes_data = _load_bayes_sym() if os.path.exists(bayes_path) else {}

        # Dosya yaşı (en yeni olanı al)
        mtimes = [os.path.getmtime(p) for p in (psy_path, bayes_path) if os.path.exists(p)]
        if mtimes:
            mtime = datetime.fromtimestamp(max(mtimes))
            age_min = (datetime.now() - mtime).total_seconds() / 60
            age_str = f"{age_min:.0f} dk önce" if age_min < 60 else \
                       (f"{age_min/60:.1f} saat önce" if age_min < 1440 else
                        f"{age_min/1440:.1f} gün önce")
        else:
            age_str = "yok"

        # Her sembol için EN İYİ rating (Grid veya Bayes'ten yüksek olanı)
        RT_ORDER = {"MÜKEMMEL": 5, "İYİ": 4, "ORTA": 3,
                     "MARJINAL": 2, "VERİ_AZ": 1, "UYUMSUZ": 0}
        best_rt = {}
        for src in (psy_data, bayes_data):
            for sym, r in src.items():
                if not r.get("ok"): continue
                rt = r.get("rating", "?")
                if rt in RT_ORDER:
                    if sym not in best_rt or RT_ORDER[rt] > RT_ORDER[best_rt[sym]]:
                        best_rt[sym] = rt

        n_total      = len(best_rt)
        iyi_count    = sum(1 for r in best_rt.values()
                            if r in ("MÜKEMMEL", "İYİ", "ORTA"))
        uyumsuz_count = sum(1 for r in best_rt.values() if r == "UYUMSUZ")

        cu1.metric("📁 Parametre dosyası", f"{age_str}",
                    help="Grid + Bayes JSON son güncellenme zamanı")
        cu2.metric("🎯 İşe yarayan sembol", f"{iyi_count}/{n_total}",
                    help="MÜKEMMEL + İYİ + ORTA rating sayısı (Grid + Bayes en iyisi)")
        cu3.metric("❌ Uyumsuz", f"{uyumsuz_count}",
                    help="Sistem bu sembollerde zarar ediyor")

        with cu4:
            if st.button("🔄 Cache temizle", help="Fiyat cache'lerini temizle (anlık veri yenile)"):
                st.cache_data.clear()
                st.success("Cache temizlendi!")
                st.rerun()
            if st.button("🔁 Parametreleri yenile",
                          help="Tüm sembolleri yeniden optimize et (~30dk). "
                                "Auto-daemon haftalık (Pazar 02:00) çalışır; "
                                "büyük piyasa olayında manuel tetikleyebilirsin."):
                # Daemon'a tetik dosyası bırak
                with open("trigger_optimize.flag", "w") as _f:
                    _f.write(datetime.now().isoformat())
                st.success("✓ Tetik gönderildi. Daemon en çok 30 sn içinde optimize'ı başlatır. "
                            "İlerlemeyi `auto_update.log` dosyasından izleyebilirsin.")

    st.markdown("---")

    st.subheader("🌅 Bugünün Pozisyon Önerileri")
    st.caption("Sabah ritüeli: sistem güçlü sinyalleri filtreler, top-5 pozisyon önerir.")

    # Sabit varsayılanlar (UI kaldırıldı)
    morning_capital = 1000
    pct_per_pos     = 10
    max_positions   = 5
    morning_lev     = 5
    pos_size        = morning_capital * pct_per_pos / 100

    # Per-symbol params var mı? (cache'li)
    import os
    has_per_sym = os.path.exists("per_symbol_params.json")
    if has_per_sym:
        per_sym = _load_per_sym()
        st.success(f"✓ Sembol bazlı optimum parametreler yüklü "
                   f"({len(per_sym)} sembol). Tarama her sembolün kendi parametresiyle yapılacak.")
    else:
        st.warning("Henüz `per_symbol_params.json` yok — generic parametre kullanılacak. "
                   "`per_symbol_optimize.py` çalıştırılınca bu tablo iyileşir.")
        per_sym = {}

    # BIST / NASDAQ ayrı butonlar
    mb1, mb2 = st.columns(2)
    with mb1:
        run_morning_bist = st.button(f"🇹🇷 BIST önerileri ({len(BIST)} sembol)",
                                        type="primary", use_container_width=True,
                                        key="morning_bist_btn")
    with mb2:
        run_morning_nasdaq = st.button(f"🇺🇸 NASDAQ önerileri ({len(NASDAQ)} sembol)",
                                          type="primary", use_container_width=True,
                                          key="morning_nasdaq_btn")
    _run_morning = run_morning_bist or run_morning_nasdaq

    if _run_morning:
        if run_morning_bist:
            symbols = list(BIST)
        else:
            symbols = list(NASDAQ)

        prog = st.progress(0, text="taranıyor...")
        candidates = []

        for i, sym in enumerate(symbols):
            df = fetch_yf(sym, "60d", "5m")
            if df.empty or len(df) < 2000:
                prog.progress((i+1)/len(symbols))
                continue

            # Sembolün kendi optimum parametresi (varsa)
            if sym in per_sym and per_sym[sym].get("ok"):
                params = per_sym[sym]["params"]
                bt_score = per_sym[sym]["stats"]["return"]
                bt_pf = per_sym[sym]["stats"]["pf"] or 5.0
            else:
                params = PARAMS
                bt_score = 0
                bt_pf = 1.0

            try:
                s = sig_full.build_signals_full(df["close"], df["high"], df["low"], **params)
            except Exception:
                prog.progress((i+1)/len(symbols))
                continue

            last = s.iloc[-1]
            cur = float(df["close"].iloc[-1])

            # Sinyal var mı?
            signal_type = None
            if last.get("cond_buy_long", False):    signal_type = "🟢 LONG AÇ"
            elif last.get("cond_buy_short", False): signal_type = "🔴 SHORT AÇ"
            # Açık pozisyon takibi de göster
            elif last.get("major_up", False) and last.get("zone_up", False):  signal_type = "🟢 LONG TUT"
            elif last.get("major_dn", False) and last.get("zone_dn", False):  signal_type = "🔴 SHORT TUT"

            if signal_type is None:
                prog.progress((i+1)/len(symbols))
                continue

            # Tetik seviyeleri (stop loss + target)
            tott_up = float(last["tott_up"]) if not pd.isna(last["tott_up"]) else None
            tott_dn = float(last["tott_dn"]) if not pd.isna(last["tott_dn"]) else None

            if signal_type and "LONG" in signal_type:
                # Long pozisyon — stop = tott_dn
                stop = tott_dn
                risk_pct = (cur - stop) / cur * 100 if stop else None
            elif signal_type and "SHORT" in signal_type:
                # Short pozisyon — stop = tott_up
                stop = tott_up
                risk_pct = (stop - cur) / cur * 100 if stop else None
            else:
                stop = None
                risk_pct = None

            # Skor (önceliklendirme): backtest performansı + sinyal türü
            score_val = bt_score * (bt_pf if bt_pf else 1.0)
            if signal_type and "AÇ" in signal_type:  # YENİ sinyal öncelikli (LONG AÇ / SHORT AÇ)
                score_val *= 1.5

            candidates.append({
                "Sembol": sym,
                "Kategori": "NASDAQ" if sym in NASDAQ else ("BIST" if sym in BIST else "OTHER"),
                "Sinyal": signal_type,
                "Fiyat": cur,
                "Stop": stop,
                "Risk %": risk_pct,
                "BT Getiri %": bt_score * 100 if bt_score else 0,
                "BT PF": bt_pf if bt_pf else 0,
                "Skor": score_val,
                "Param": "kendi" if sym in per_sym and per_sym[sym].get("ok") else "generic",
            })
            prog.progress((i+1)/len(symbols), text=f"{i+1}/{len(symbols)} — {sym}")

        prog.empty()

        if not candidates:
            st.warning("Şu anda hiçbir sembolde aktif sinyal yok. Daha sonra tekrar dene.")
        else:
            df_c = pd.DataFrame(candidates)
            df_c = df_c.sort_values("Skor", ascending=False).reset_index(drop=True)

            # En iyi N'i seç
            top_picks = df_c.head(max_positions).copy()
            top_picks["Pozisyon $"] = pos_size
            top_picks["Tahmini risk $"] = top_picks["Pozisyon $"] * morning_lev * top_picks["Risk %"].abs() / 100

            st.markdown(f"### 🎯 Bugünün önerilen pozisyonları (top {max_positions})")
            st.dataframe(
                top_picks[["Sembol","Kategori","Sinyal","Fiyat","Stop","Risk %",
                            "Pozisyon $","Tahmini risk $","BT Getiri %","BT PF","Param"]].style.format({
                    "Fiyat":"{:.4f}", "Stop":"{:.4f}", "Risk %":"{:+.2f}%",
                    "Pozisyon $":"${:.0f}", "Tahmini risk $":"${:.0f}",
                    "BT Getiri %":"{:+.1f}%", "BT PF":"{:.2f}",
                }).background_gradient(subset=["BT Getiri %"], cmap="RdYlGn"),
                use_container_width=True, height=400,
            )

            # Toplam risk
            total_risk = top_picks["Tahmini risk $"].sum()
            risk_pct_of_capital = total_risk / morning_capital * 100
            colA, colB, colC = st.columns(3)
            colA.metric("Toplam yatırım", f"${(pos_size * len(top_picks)):,.0f}",
                        f"sermayenin {pct_per_pos * len(top_picks)}%'i")
            colB.metric("Toplam max risk (kaldıraçlı)", f"${total_risk:,.0f}",
                        f"{risk_pct_of_capital:.1f}% sermaye")
            colC.metric("Önerilen pozisyon adedi", f"{len(top_picks)}")

            # Risk uyarısı
            if risk_pct_of_capital > 30:
                st.error(f"⚠️ Toplam risk sermayenin %{risk_pct_of_capital:.0f}'i — çok yüksek! "
                         f"Kaldıracı düşür veya pozisyon başı %'yi azalt.")
            elif risk_pct_of_capital > 15:
                st.warning(f"Toplam risk %{risk_pct_of_capital:.0f}. Makul ama dikkatli izle.")
            else:
                st.success(f"✓ Toplam risk %{risk_pct_of_capital:.0f}. Konservatif seviye.")

            # Talimat
            st.markdown("---")
            st.markdown("### 📋 Bugünün İş Akışı")
            st.markdown(f"""
            1. **MT4 / GCM platformunda** yukarıdaki sembollerden uygun olanlara emir gir
            2. Her sembol için **stop-loss = Stop sütunu** ($) — bu seviye geçilirse çık
            3. Sistemin **otomatik çıkış sinyali** geldiğinde de mutlaka pozisyonu kapat (TOTT/SOTT yön değişimi)
            4. Tüm pozisyonları **${pos_size:,.0f}'lık** açtığından emin ol — sermaye yönetimi kritik
            5. Akşam veya yarın sabah dashboard'u tekrar aç, yeni durumu gör
            """)

            # CSV indirme
            csv = top_picks.to_csv(index=False).encode("utf-8")
            st.download_button("📥 CSV indir", csv, "morning_picks.csv", "text/csv")

# ──────────────────────────────────────────────────────────────────
#  TAB 1: TARAYICI
# ──────────────────────────────────────────────────────────────────
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

    # Hangi kategori tarandı?
    if run_scan_bist:
        symbols = list(BIST)
    elif run_scan_nasdaq:
        symbols = list(NASDAQ)
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
                      "Trend OTT", "Tetik ↑", "Up %", "Tetik ↓", "Dn %",
                      "BT Getiri %", "BT PF", "BT Win %", "BT Trade"]
        show_cols = [c for c in col_order if c in show_cols]

        st.dataframe(
            df_scan[show_cols].style.format({
                "Fiyat": "{:.4f}",
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
        prop_symbols = list(BIST)
    elif run_prop_nasdaq:
        prop_symbols = list(NASDAQ)
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
with tab_chart:
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

# ──────────────────────────────────────────────────────────────────
#  TAB 5: BİLGİ
# ──────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────
#  TAB: ALTERNATİF BOT PORTFÖYÜ — Bayesian parametre arama
# ──────────────────────────────────────────────────────────────────
with tab_alt:
    st.subheader("🧪 Alternatif Bot Portföyü — Bayesian Parametre Arama")
    st.caption("Mevcut sistem dokunulmaz. Bu sekme **deneysel**: optuna ile akıllı parametre araması, sonuçlar ayrı dosyada (`per_symbol_params_bayes.json`).")

    with st.expander("ℹ️ Bayesian arama nedir? Grid'den farkı ne?"):
        st.markdown("""
        **Grid search** (mevcut sistem):
        - Önceden belirlenmiş parametre değerleri × kombinasyonu
        - Örnek: trend_length ∈ {20, 30, 40} → 3 değer
        - Sembol başına ~140 kombinasyon
        - **Sınırlı arama uzayı**: belki en iyi parametre 25'tir ama grid bilmez

        **Bayesian search** (TPE — Tree Parzen Estimator, optuna):
        - Sürekli aralık: trend_length ∈ [10, 60] herhangi bir tamsayı
        - İlk 20 trial **rastgele örnek** → uzayı tanı
        - Sonraki 180 trial **iyi bölgelerde yoğun** → fine-tune
        - Sembol başına 200 trial × 14 parametre = **akıllı arama**
        - 3-5x daha iyi parametre bulma olasılığı

        **Aşağıdaki tablo karşılaştırma:**
        - Grid: mevcut `per_symbol_params.json`
        - Bayes: yeni `per_symbol_params_bayes.json`
        """)

    import os
    bayes_path = "per_symbol_params_bayes.json"
    grid_path = "per_symbol_params.json"

    # Mevcut durumu kontrol et (cache'li)
    bayes_exists = os.path.exists(bayes_path)
    bayes_data = _load_bayes_sym() if bayes_exists else {}
    bayes_done = len(bayes_data)
    grid_data  = _load_per_sym()

    # Status bar
    bcol1, bcol2, bcol3 = st.columns(3)
    bcol1.metric("Grid sonucu", f"{len(grid_data)} sembol", help="Mevcut çalışan sistem")
    bcol2.metric("Bayesian sonucu", f"{bayes_done} sembol",
                  help="Bayesian arama tamamlanan sembol sayısı")
    if bayes_done > 0:
        improved = sum(1 for s, r in bayes_data.items()
                        if r.get("ok") and grid_data.get(s, {}).get("stats", {}).get("return", -999)
                        < r["stats"]["return"])
        bcol3.metric("Grid'ten iyi", f"{improved}/{bayes_done}",
                      help="Bayesian'ın grid'i geçtiği sembol sayısı")

    st.markdown("---")

    # Tetik butonu
    tcol1, tcol2 = st.columns([2, 1])
    with tcol1:
        st.markdown("### 🚀 Bayesian aramayı tetikle")
        st.caption("**Süre: ~60-90 dakika** (151 sembol × 200 trial). Bot çalışmaz, sadece optimize.")
    with tcol2:
        if st.button("⚗️ Bayesian'ı çalıştır", type="primary", use_container_width=True):
            from datetime import datetime
            with open("trigger_bayesian.flag", "w") as f:
                f.write(datetime.now().isoformat())
            st.success("✓ Tetik gönderildi. Auto-daemon başlatacak. İlerlemeyi `auto_update.log` dosyasında izleyebilirsin.")
            st.info("Yerel olarak çalıştırmak istersen Git Bash'te:\n```\ncd /c/Users/furka/Desktop/ott_bot\npython bayesian_optimize.py\n```")

    st.markdown("---")

    if bayes_done == 0:
        st.warning("📭 Henüz Bayesian sonucu yok. Yukarıdaki butona basıp çalıştır.")
    else:
        # Filtre — sadece GCM Forex'te işlem görenler
        st.markdown(f"### 📊 Karşılaştırma Tablosu ({bayes_done} sembol)")
        only_gcm = st.checkbox("📍 Sadece GCM Forex'te işlem görenler (NASDAQ CFD)",
                                value=False, key="alt_only_gcm",
                                help=f"GCM Forex'te yaygın işlem gören {len(GCM_NASDAQ)} NASDAQ hissesi listede mevcut")

        rows = []
        for sym, bayes_r in bayes_data.items():
            if not bayes_r.get("ok"):
                continue
            grid_r = grid_data.get(sym, {})
            bs = bayes_r["stats"]
            gs = grid_r.get("stats", {}) if grid_r.get("ok") else {}
            in_gcm = sym in GCM_NASDAQ

            if only_gcm and not in_gcm:
                continue

            rows.append({
                "Sembol": sym,
                "Kategori": bayes_r.get("category", "?"),
                "GCM": "✓" if in_gcm else "",
                "Bayes Bot": bayes_r.get("rating", "?"),
                "Bayes Ret %": bs["return"] * 100,
                "Bayes PF": bs["pf"] if bs["pf"] else 999,
                "Bayes Win %": bs["win_rate"] * 100,
                "FY Bot": grid_r.get("rating", "—"),
                "FY Ret %": gs.get("return", 0) * 100 if gs else None,
                "FY PF": gs.get("pf", 0) if gs and gs.get("pf") else None,
                "Fark %": (bs["return"] - gs.get("return", 0)) * 100 if gs else None,
            })

        if rows:
            df_alt = pd.DataFrame(rows)
            df_alt = df_alt.sort_values("Bayes Ret %", ascending=False).reset_index(drop=True)

            # Üst metrik bar — GCM sayısı vs toplam
            gcm_count = (df_alt["GCM"] == "✓").sum()
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Toplam", len(df_alt))
            mc2.metric("📍 GCM'de var", int(gcm_count))
            mc3.metric("📍 GCM dışı", len(df_alt) - int(gcm_count))

            st.dataframe(
                df_alt.style.format({
                    "Bayes Ret %": "{:+.1f}%",
                    "Bayes PF": lambda v: ("∞" if v >= 900 else f"{v:.2f}") if v else "-",
                    "Bayes Win %": "{:.0f}%",
                    "FY Ret %": lambda v: f"{v:+.1f}%" if pd.notna(v) else "-",
                    "FY PF": lambda v: f"{v:.2f}" if pd.notna(v) else "-",
                    "Fark %": lambda v: f"{v:+.1f}%" if pd.notna(v) else "-",
                }).background_gradient(subset=["Fark %"], cmap="RdYlGn", vmin=-30, vmax=30),
                use_container_width=True, height=500,
            )
            st.caption("**FY Bot** = ana sistem (grid search · `per_symbol_params.json`).  "
                        "**Bayes Bot** = alternatif (TPE arama · `per_symbol_params_bayes.json`). "
                        "**GCM** = sembol GCM Forex'te CFD olarak işlem görüyor mu.")

            # Rating dağılımı karşılaştırma
            st.markdown("### 🏆 Rating dağılımı")
            rc1, rc2 = st.columns(2)
            with rc1:
                st.markdown("**Bayesian sonucu:**")
                bayes_rt = {}
                for s, r in bayes_data.items():
                    if r.get("ok"):
                        rt = r.get("rating", "?")
                        bayes_rt[rt] = bayes_rt.get(rt, 0) + 1
                for rt in ["MÜKEMMEL", "İYİ", "ORTA", "MARJINAL", "VERİ_AZ", "UYUMSUZ"]:
                    n = bayes_rt.get(rt, 0)
                    if n > 0:
                        st.write(f"{rt}: **{n}**")
            with rc2:
                st.markdown("**Grid sonucu (referans):**")
                grid_rt = {}
                for s, r in grid_data.items():
                    if r.get("ok"):
                        rt = r.get("rating", "?")
                        grid_rt[rt] = grid_rt.get(rt, 0) + 1
                for rt in ["MÜKEMMEL", "İYİ", "ORTA", "MARJINAL", "VERİ_AZ", "UYUMSUZ"]:
                    n = grid_rt.get(rt, 0)
                    if n > 0:
                        st.write(f"{rt}: **{n}**")

            # Sembol özelinde detay
            st.markdown("### 🔍 Sembol detayı")
            sel = st.selectbox("Sembol seç", df_alt["Sembol"].tolist(), key="alt_sym")
            if sel and sel in bayes_data:
                bd = bayes_data[sel]
                gd = grid_data.get(sel, {})

                dc1, dc2 = st.columns(2)
                with dc1:
                    st.markdown(f"#### 🧪 Bayesian — {bd.get('rating','?')}")
                    bsr = bd["stats"]
                    st.write(f"- Return: **{bsr['return']*100:+.2f}%**")
                    st.write(f"- PF: **{bsr['pf']:.2f}**" if bsr["pf"] else "- PF: ∞")
                    st.write(f"- Win Rate: **{bsr['win_rate']*100:.0f}%**")
                    st.write(f"- Max DD: {bsr['max_dd']*100:.2f}%")
                    st.write(f"- Trade: {bsr['n_trades']}")
                    st.write(f"- Trial sayısı: {bd.get('n_trials', '?')}")
                with dc2:
                    if gd.get("ok"):
                        st.markdown(f"#### 📐 Grid — {gd.get('rating','?')}")
                        gsr = gd["stats"]
                        st.write(f"- Return: **{gsr['return']*100:+.2f}%**")
                        st.write(f"- PF: **{gsr['pf']:.2f}**" if gsr.get("pf") else "- PF: ∞")
                        st.write(f"- Win Rate: **{gsr['win_rate']*100:.0f}%**")
                        st.write(f"- Max DD: {gsr['max_dd']*100:.2f}%")
                        st.write(f"- Trade: {gsr['n_trades']}")

                with st.expander("⚙️ Bayesian parametreleri"):
                    st.json(bd["params"])

            # ──── Anlık sinyal tarama (Bayesian parametreleriyle)
            st.markdown("---")
            st.markdown("### 📡 Bayesian parametreleriyle ANLIK sinyaller (LONG / SHORT)")
            st.caption("Her sembol kendi Bayesian parametre setini kullanır. Canlı fiyatla **şu anki yön**ü gösterir.")

            if st.button("🔍 Şimdi tara (FY Bot + Bayes Bot)", type="primary",
                          use_container_width=True, key="bayes_scan_btn"):
                from data_source import best_interval_for as _bif
                from data_source import category_of as _cat
                live_rows = []
                live_prog = st.progress(0, text="başlatılıyor...")
                _ok_items = [(s, r) for s, r in bayes_data.items() if r.get("ok")]

                def _signal_label(last_):
                    if last_["cond_buy_long"]:        return "🟢 LONG AÇ"
                    if last_["cond_buy_short"]:       return "🔴 SHORT AÇ"
                    if last_["cond_exit_long"]:       return "🟡 LONG ÇIK"
                    if last_["cond_exit_short"]:      return "🟡 SHORT ÇIK"
                    if last_["major_up"] and last_["zone_up"]:  return "🟢 LONG TUT"
                    if last_["major_dn"] and last_["zone_dn"]:  return "🔴 SHORT TUT"
                    if last_["major_up"]:              return "⏳ LONG bekle"
                    if last_["major_dn"]:              return "⏳ SHORT bekle"
                    return "❓"

                for idx, (sym, sym_data) in enumerate(_ok_items):
                    bayes_params = sym_data["params"].copy()
                    bayes_params.setdefault("rott_x1", 30)
                    bayes_params.setdefault("rott_x2", 1000)
                    bayes_params.setdefault("rott_percent", 7.0)
                    grid_entry = grid_data.get(sym, {})
                    grid_params = grid_entry["params"].copy() if grid_entry.get("ok") else None
                    if grid_params:
                        grid_params.setdefault("rott_x1", 30)
                        grid_params.setdefault("rott_x2", 1000)
                        grid_params.setdefault("rott_percent", 7.0)
                    try:
                        df_live = fetch_yf(sym, interval=_bif(sym))
                        if df_live.empty or len(df_live) < 1500:
                            live_prog.progress((idx+1)/len(_ok_items))
                            continue
                        # Bayes Bot sinyali
                        s_bayes = sig_full.build_signals_full(
                            df_live["close"], df_live["high"], df_live["low"], **bayes_params)
                        last_b = s_bayes.iloc[-1]
                        cur_l = float(df_live["close"].iloc[-1])
                        bayes_sig = _signal_label(last_b)

                        # FY Bot (grid) sinyali
                        if grid_params:
                            s_grid = sig_full.build_signals_full(
                                df_live["close"], df_live["high"], df_live["low"], **grid_params)
                            fy_sig = _signal_label(s_grid.iloc[-1])
                        else:
                            fy_sig = "—"

                        tott_up_v = float(last_b["tott_up"]) if not pd.isna(last_b["tott_up"]) else None
                        tott_dn_v = float(last_b["tott_dn"]) if not pd.isna(last_b["tott_dn"]) else None
                        live_rows.append({
                            "Sembol": sym,
                            "Kategori": _cat(sym),
                            "GCM": "✓" if sym in GCM_NASDAQ else "",
                            "Rating": sym_data.get("rating","?"),
                            "FY Bot": fy_sig,
                            "Bayes Bot": bayes_sig,
                            "Fiyat": cur_l,
                            "Stop ↑": tott_up_v,
                            "Stop ↓": tott_dn_v,
                            "BT Ret %": sym_data["stats"]["return"]*100,
                            "BT PF": sym_data["stats"]["pf"] if sym_data["stats"]["pf"] else 999,
                            "BT Win %": sym_data["stats"]["win_rate"]*100,
                        })
                    except Exception:
                        pass
                    live_prog.progress((idx+1)/len(_ok_items), text=f"{idx+1}/{len(_ok_items)} {sym}")
                live_prog.empty()

                if not live_rows:
                    st.warning("Anlık veri çekilemedi.")
                else:
                    df_live_show = pd.DataFrame(live_rows)
                    order_live = {
                        "🟢 LONG AÇ": 0, "🔴 SHORT AÇ": 1,
                        "🟡 LONG ÇIK": 2, "🟡 SHORT ÇIK": 3,
                        "🟢 LONG TUT": 4, "🔴 SHORT TUT": 5,
                        "⏳ LONG bekle": 6, "⏳ SHORT bekle": 7, "❓": 8, "—": 9,
                    }
                    # Bayes durumuna göre sırala
                    df_live_show["_ord"] = df_live_show["Bayes Bot"].map(order_live).fillna(9)
                    df_live_show = df_live_show.sort_values(
                        ["_ord", "BT Ret %"], ascending=[True, False]
                    ).drop(columns="_ord").reset_index(drop=True)

                    fm1, fm2, fm3, fm4 = st.columns(4)
                    bayes_long = int((df_live_show["Bayes Bot"]=="🟢 LONG AÇ").sum())
                    bayes_short = int((df_live_show["Bayes Bot"]=="🔴 SHORT AÇ").sum())
                    fy_long = int((df_live_show["FY Bot"]=="🟢 LONG AÇ").sum())
                    fy_short = int((df_live_show["FY Bot"]=="🔴 SHORT AÇ").sum())
                    fm1.metric("🤖 FY Bot AÇ", fy_long + fy_short,
                                f"L:{fy_long} · S:{fy_short}")
                    fm2.metric("🧪 Bayes Bot AÇ", bayes_long + bayes_short,
                                f"L:{bayes_long} · S:{bayes_short}")
                    # Konsensüs — iki bot aynı yönü diyenler
                    consensus = int(((df_live_show["FY Bot"].str.contains("LONG AÇ", regex=False)) &
                                     (df_live_show["Bayes Bot"].str.contains("LONG AÇ", regex=False))).sum() +
                                    ((df_live_show["FY Bot"].str.contains("SHORT AÇ", regex=False)) &
                                     (df_live_show["Bayes Bot"].str.contains("SHORT AÇ", regex=False))).sum())
                    fm3.metric("🤝 İki bot aynı", consensus,
                                help="İki bot aynı yönde sinyal verirse en güvenli")
                    fm4.metric("Toplam", len(df_live_show))

                    st.dataframe(
                        df_live_show.style.format({
                            "Fiyat": "{:.4f}", "Stop ↑": "{:.4f}", "Stop ↓": "{:.4f}",
                            "BT Ret %": "{:+.1f}%",
                            "BT PF": lambda v: ("∞" if v >= 900 else f"{v:.2f}") if pd.notna(v) else "-",
                            "BT Win %": "{:.0f}%",
                        }).background_gradient(subset=["BT Ret %"], cmap="RdYlGn"),
                        use_container_width=True, height=500,
                    )
                    st.caption(
                        "**FY Bot** = ana sistem (grid) sinyali · **Bayes Bot** = alternatif sinyal.  "
                        "**İkisi aynı yöne deyince** en güçlü işaret. "
                        "**GCM** ✓ = sembol GCM Forex'te CFD olarak işlem görüyor (Türkiye'den erişilebilir).")

            st.markdown("---")
            st.markdown("### 🎯 Bu parametreleri **canlı kullanmaya hazır mı**?")
            st.markdown("""
            Alternatif Bot Portföyü **deneysel**. Mevcut ana sistemi etkilemiyor.
            Eğer Bayesian sonuçları sürekli daha iyi çıkarsa ileride **ana sistem buraya geçirilebilir**.
            Şimdilik karşılaştırma ve test için.
            """)

with tab_info:
    st.subheader("Sistem hakkında")
    st.markdown("""
    ### Kaynak
    - **Sistem:** Anıl Özekşi OTT-ailesi (TOTT + SOTT + HOTT/LOTT + ROTT)
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
        all_syms = set(list(_bayes_data.keys()) + list(_grid_data.keys()))
        for sym in all_syms:
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
                "PF":       (stats.get("pf") or 0),
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
                qcat = st.multiselect("Kategori",
                                        sorted(qdf["Kategori"].unique()),
                                        default=["BIST", "NASDAQ"], key="q_cat")
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
    <span style="color:#666;">Anıl Özekşi OTT-family · Python port · Streamlit</span>
</div>
""", unsafe_allow_html=True)
