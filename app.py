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
    for _key in ("TV_USERNAME", "TV_PASSWORD"):
        if _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
except Exception:
    pass

import signals_full as sig_full
from backtest import run_backtest
from data_source import fetch as ds_fetch


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
NASDAQ = [
    "AAPL","MSFT","AMZN","NVDA","GOOG","GOOGL","META","AVGO","TSLA","COST",
    "NFLX","AMD","PEP","ADBE","CSCO","TMUS","INTC","INTU","CMCSA","AMGN",
    "QCOM","TXN","HON","BKNG","AMAT","ISRG","GILD","ADP","MU","ADI",
    "MDLZ","SBUX","REGN","VRTX","LRCX","KLAC","PANW","SNPS","PYPL","CDNS",
    "MELI","MAR","ASML","ABNB","CRWD","ORLY","MNST","FTNT","NXPI","CHTR",
    "ADSK","KDP","ROP","AEP","PCAR","MRVL","KHC","FAST","ODFL","PAYX",
    "DDOG","CTSH","EXC","BIIB","AZN","FANG","ROST","IDXX","EA","CSGP",
    "ZS","GEHC","XEL","DXCM","BKR","ANSS","CTAS","DLTR","TEAM","WDAY",
    "MRNA","ON","VRSK","CCEP","CDW","GFS","MDB","SIRI","JD","ILMN",
    "LULU","WBA","ENPH","MTCH","FOXA","FOX","WBD","CEG","TTD","APP",
    "QQQ",  # endeks ETF de listede
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
def _load_per_sym():
    import os, json
    if not os.path.exists("per_symbol_params.json"):
        return {}
    with open("per_symbol_params.json") as f:
        return json.load(f)


def analyze_intraday(symbol, interval: str | None = None):
    """interval=None → kategoriye göre otomatik (CRYPTO=30m, diğer=1h)"""
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
# Sistem durumu için hızlı sayım
_iyi = 0; _uyumsuz = 0; _total = 0
try:
    import os, json
    if os.path.exists("per_symbol_params.json"):
        with open("per_symbol_params.json") as _f:
            _psy = json.load(_f)
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

tab_safe, tab_morning, tab_scan, tab_sim, tab_chart, tab_alt, tab_info = st.tabs([
    "🛡️  Güvenli Mod",
    "🎯  Bugünün Önerileri",
    "📡  Anlık Tarayıcı",
    "📌  Öneriler",
    "📊  Detay Grafik",
    "🧪  Alternatif Bot Portföyü",
    "📖  Bilgi",
])

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

    safe_col1, safe_col2, safe_col3 = st.columns([2, 2, 1])
    with safe_col1:
        safe_capital = st.number_input("💵 Sermaye ($)",
                                         100, 10000000, 1000, 100, key="safe_capital")
    with safe_col2:
        safe_pct = st.slider("📊 Pozisyon başına %",
                              2, 25, 10, key="safe_pct",
                              help="Sermayenin % kaçı bir pozisyona ayrılsın")
    with safe_col3:
        safe_lev = st.slider("⚖️ Kaldıraç", 1, 25, 5, key="safe_lev")

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
        # per_symbol_params dosyasının son güncellenme zamanı
        psy_path = "per_symbol_params.json"
        if os.path.exists(psy_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(psy_path))
            age_min = (datetime.now() - mtime).total_seconds() / 60
            age_str = f"{age_min:.0f} dk önce" if age_min < 60 else f"{age_min/60:.1f} saat önce"
            with open(psy_path) as f:
                psy_data = json.load(f)
            n_total = len(psy_data)
            rt_counts = {}
            for s, r in psy_data.items():
                if r.get("ok"):
                    rt_counts[r.get("rating","?")] = rt_counts.get(r.get("rating","?"),0)+1
            iyi_count = rt_counts.get("MÜKEMMEL",0) + rt_counts.get("İYİ",0) + rt_counts.get("ORTA",0)
            uyumsuz_count = rt_counts.get("UYUMSUZ", 0)

            cu1.metric("📁 Parametre dosyası", f"{age_str}", help="per_symbol_params.json güncellenme zamanı")
            cu2.metric("🎯 İşe yarayan sembol", f"{iyi_count}/{n_total}",
                        help="MÜKEMMEL + İYİ + ORTA rating sayısı")
            cu3.metric("❌ Uyumsuz", f"{uyumsuz_count}",
                        help="Sistem bu sembollerde zarar ediyor")
        else:
            cu1.warning("Henüz `per_symbol_params.json` yok")

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
    st.caption("Sabah ritüeli: sermayeni gir, sistem güçlü sinyalleri filtreler, pozisyon büyüklüklerini hesaplar.")

    # Sermaye ayarları
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        morning_capital = st.number_input("💵 Sermaye ($)",
                                            min_value=100, max_value=10000000,
                                            value=1000, step=100)
    with c2:
        pct_per_pos = st.slider("📊 Pozisyon başına %",
                                 min_value=2, max_value=25, value=10, step=1,
                                 help="Sermayenin yüzde kaçı bir pozisyona ayrılsın")
    with c3:
        max_positions = st.slider("🎯 Maksimum eşzamanlı pozisyon",
                                    min_value=1, max_value=15, value=5)
    with c4:
        morning_lev = st.slider("⚖️ Kaldıraç", 1, 25, 5)

    pos_size = morning_capital * pct_per_pos / 100

    # Per-symbol params var mı?
    import os, json
    has_per_sym = os.path.exists("per_symbol_params.json")
    if has_per_sym:
        with open("per_symbol_params.json") as f:
            per_sym = json.load(f)
        st.success(f"✓ Sembol bazlı optimum parametreler yüklü "
                   f"({len(per_sym)} sembol). Tarama her sembolün kendi parametresiyle yapılacak.")
    else:
        st.warning("Henüz `per_symbol_params.json` yok — generic parametre kullanılacak. "
                   "`per_symbol_optimize.py` çalıştırılınca bu tablo iyileşir.")
        per_sym = {}

    morning_cats = st.multiselect("Kategoriler (NASDAQ + BIST + ...)",
                                    ["NASDAQ", "BIST", "COMMODITY", "CRYPTO"],
                                    default=["NASDAQ", "BIST"], key="morning_cats")

    if st.button("🌅 Bugünün önerilerini hazırla", type="primary", use_container_width=True):
        symbols = []
        if "NASDAQ" in morning_cats: symbols += NASDAQ
        if "BIST" in morning_cats: symbols += BIST
        if "COMMODITY" in morning_cats: symbols += COMMODITY
        if "CRYPTO" in morning_cats: symbols += CRYPTO

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
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        categories = st.multiselect("Kategoriler",
                                     ["NASDAQ", "BIST", "COMMODITY", "CRYPTO"],
                                     default=["NASDAQ", "BIST", "COMMODITY"])
    with col2:
        only_signals = st.checkbox("Sadece AKTİF SİNYAL (AL/SAT)", value=False)
    with col3:
        only_top_rated = st.checkbox("Sadece 🏆 MÜKEMMEL + ⭐ İYİ", value=True,
                                       help="Düşük güvenli sembolleri gizle — terste kalma riski azalır")
    with col4:
        if st.button("🔄 Şimdi tara", type="primary"):
            st.cache_data.clear()

    symbols = []
    if "NASDAQ" in categories: symbols += NASDAQ
    if "BIST" in categories: symbols += BIST
    if "COMMODITY" in categories: symbols += COMMODITY
    if "CRYPTO" in categories: symbols += CRYPTO

    progress = st.progress(0, text=f"0/{len(symbols)}")
    rows = []
    for i, sym in enumerate(symbols):
        r = analyze_intraday(sym)
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
    st.caption("Şu an aktif sinyal veren semboller. Anlık fiyat, stop seviyesi, beklenen hedef ve potansiyel getiri.")

    with st.expander("ℹ️ Beklenen fiyat nasıl hesaplanıyor?"):
        st.markdown("""
        Sistem **trend takipçi** → kesin hedef fiyat yok, sistem çıkış sinyali verene kadar pozisyon tutulur.

        Tablodaki **Beklenen Hedef** profesyonel R:R 1:2 mantığıyla hesaplanır:
        - **Risk** = |Anlık Fiyat − Stop Seviyesi|
        - **Hedef** = Anlık Fiyat ± (2 × Risk)
        - LONG: hedef yukarıda  ·  SHORT: hedef aşağıda

        **Backtest Win** sütunu: bu sembolde sistem geçmişte ne sıklıkla kazanmış.
        Yüksek win + uygun R:R = beklenen kazanç.

        **NOT**: Hedef tahminidir, gerçek çıkış sistem sinyaline bağlı.
        """)

    pc1, pc2 = st.columns([2, 1])
    with pc1:
        prop_cats = st.multiselect("Kategoriler",
                                     ["NASDAQ", "BIST", "COMMODITY", "CRYPTO"],
                                     default=["NASDAQ", "BIST", "COMMODITY", "CRYPTO"],
                                     key="prop_cats")
    with pc2:
        prop_top_only = st.checkbox("Sadece 🏆 MÜKEMMEL + ⭐ İYİ",
                                      value=True, key="prop_top_only")

    if st.button("🔄 Önerileri yenile", type="primary", use_container_width=True):
        st.cache_data.clear()

    prop_symbols = []
    if "NASDAQ" in prop_cats: prop_symbols += NASDAQ
    if "BIST" in prop_cats: prop_symbols += BIST
    if "COMMODITY" in prop_cats: prop_symbols += COMMODITY
    if "CRYPTO" in prop_cats: prop_symbols += CRYPTO

    prop_prog = st.progress(0, text=f"0/{len(prop_symbols)}")
    prop_rows = []
    for i, sym in enumerate(prop_symbols):
        r = analyze_intraday(sym)
        if r:
            prop_rows.append(r)
        prop_prog.progress((i+1)/len(prop_symbols), text=f"{i+1}/{len(prop_symbols)} {sym}")
    prop_prog.empty()

    # Sadece YENİ sinyali olanları al (LONG AÇ veya SHORT AÇ)
    fresh = []
    for r in prop_rows:
        if "LONG AÇ" in r["Durum"] or "SHORT AÇ" in r["Durum"]:
            # Rating filtre
            if prop_top_only and not ("MÜKEMMEL" in r["Güven"] or "İYİ" in r["Güven"]):
                continue

            cur = r["Fiyat"]
            if "LONG" in r["Durum"]:
                yon = "🟢 LONG"
                stop = r["Tetik ↓"]
                if stop and cur:
                    risk = cur - stop
                    target = cur + 2 * risk  # 1:2 R:R
                    risk_pct = risk / cur * 100
                    pot_pct = 2 * risk_pct
                else:
                    target = risk_pct = pot_pct = None
            else:
                yon = "🔴 SHORT"
                stop = r["Tetik ↑"]
                if stop and cur:
                    risk = stop - cur
                    target = cur - 2 * risk
                    risk_pct = risk / cur * 100
                    pot_pct = 2 * risk_pct
                else:
                    target = risk_pct = pot_pct = None

            fresh.append({
                "Sembol": r["Sembol"],
                "Kategori": r["Kategori"],
                "Güven": r["Güven"],
                "Yön": yon,
                "Anlık Fiyat": cur,
                "Stop": stop,
                "Risk %": risk_pct,
                "Beklenen Hedef": target,
                "Potansiyel %": pot_pct,
                "BT Win %": r["BT Win %"],
                "BT Ret %": r["BT Getiri %"],
            })

    if not fresh:
        st.info("📭 Şu anda yeni sinyal yok. Tarama yapıldı, hiçbir sembolde **LONG AÇ** veya **SHORT AÇ** sinyali yok.\n\n"
                 "Yarın sabah veya birkaç saat sonra tekrar dene.")
    else:
        df_prop = pd.DataFrame(fresh)
        # Güven + potansiyel ile sırala
        guv_skor = {"🏆 MÜKEMMEL": 5, "⭐ İYİ": 4, "🟢 ORTA": 3,
                    "🟡 MARJINAL": 2, "⚠️ VERİ_AZ": 1, "❌ UYUMSUZ": 0}
        df_prop["_sc"] = df_prop["Güven"].map(guv_skor).fillna(0)
        df_prop = df_prop.sort_values(["_sc", "Potansiyel %"],
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
                "Beklenen Hedef": "{:.4f}",
                "Potansiyel %": "{:+.2f}%",
                "BT Win %": "{:.0f}%",
                "BT Ret %": "{:+.1f}%",
            }).background_gradient(subset=["BT Win %"], cmap="Greens")
              .background_gradient(subset=["Potansiyel %"], cmap="RdYlGn"),
            use_container_width=True, height=550,
        )

        st.markdown("""
        ### 📋 Nasıl kullanılır?

        **Örnek:** ASELS.IS · 🟢 LONG · Anlık 380 · Stop 372 · Hedef 396

        1. **Long pozisyon aç** broker'da (örn 380 fiyatından alış emri)
        2. **Stop-loss = Stop sütunu** (372) — bu seviyenin altına inerse OTOMATIK ÇIK
        3. Fiyat **396'ya yaklaşırsa** (Beklenen Hedef) → kâr al
        4. Veya **dashboard'daki "🟡 LONG ÇIK" sinyalini** bekle → kapat

        Aynı mantık SHORT için tersi.
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

        # ──── Sembol BACKTEST KARTI (per_symbol_params.json'dan)
        import os, json
        sym_data = None
        if os.path.exists("per_symbol_params.json"):
            with open("per_symbol_params.json") as f:
                psy = json.load(f)
            if chart_sym in psy and psy[chart_sym].get("ok"):
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

    import os, json
    bayes_path = "per_symbol_params_bayes.json"
    grid_path = "per_symbol_params.json"

    # Mevcut durumu kontrol et
    bayes_exists = os.path.exists(bayes_path)
    if bayes_exists:
        with open(bayes_path) as f: bayes_data = json.load(f)
        bayes_done = len(bayes_data)
    else:
        bayes_data = {}
        bayes_done = 0

    with open(grid_path) as f: grid_data = json.load(f)

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
        # Karşılaştırma tablosu
        st.markdown(f"### 📊 Karşılaştırma Tablosu ({bayes_done} sembol)")

        rows = []
        for sym, bayes_r in bayes_data.items():
            if not bayes_r.get("ok"):
                continue
            grid_r = grid_data.get(sym, {})
            bs = bayes_r["stats"]
            gs = grid_r.get("stats", {}) if grid_r.get("ok") else {}

            rows.append({
                "Sembol": sym,
                "Kategori": bayes_r.get("category", "?"),
                "Bayes Rating": bayes_r.get("rating", "?"),
                "Bayes Ret %": bs["return"] * 100,
                "Bayes PF": bs["pf"] if bs["pf"] else 999,
                "Bayes Win %": bs["win_rate"] * 100,
                "Grid Rating": grid_r.get("rating", "—"),
                "Grid Ret %": gs.get("return", 0) * 100 if gs else None,
                "Grid PF": gs.get("pf", 0) if gs and gs.get("pf") else None,
                "Fark %": (bs["return"] - gs.get("return", 0)) * 100 if gs else None,
            })

        if rows:
            df_alt = pd.DataFrame(rows)
            df_alt = df_alt.sort_values("Bayes Ret %", ascending=False).reset_index(drop=True)

            st.dataframe(
                df_alt.style.format({
                    "Bayes Ret %": "{:+.1f}%",
                    "Bayes PF": lambda v: ("∞" if v >= 900 else f"{v:.2f}") if v else "-",
                    "Bayes Win %": "{:.0f}%",
                    "Grid Ret %": lambda v: f"{v:+.1f}%" if pd.notna(v) else "-",
                    "Grid PF": lambda v: f"{v:.2f}" if pd.notna(v) else "-",
                    "Fark %": lambda v: f"{v:+.1f}%" if pd.notna(v) else "-",
                }).background_gradient(subset=["Fark %"], cmap="RdYlGn", vmin=-30, vmax=30),
                use_container_width=True, height=500,
            )

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

            if st.button("🔍 Şimdi tara (canlı veri çek)", type="primary",
                          use_container_width=True, key="bayes_scan_btn"):
                from data_source import best_interval_for as _bif
                live_rows = []
                live_prog = st.progress(0, text="başlatılıyor...")
                _ok_items = [(s, r) for s, r in bayes_data.items() if r.get("ok")]
                for idx, (sym, sym_data) in enumerate(_ok_items):
                    params = sym_data["params"].copy()
                    params.setdefault("rott_x1", 30)
                    params.setdefault("rott_x2", 1000)
                    params.setdefault("rott_percent", 7.0)
                    try:
                        df_live = fetch_yf(sym, interval=_bif(sym))
                        if df_live.empty or len(df_live) < 1500:
                            live_prog.progress((idx+1)/len(_ok_items))
                            continue
                        s_live = sig_full.build_signals_full(
                            df_live["close"], df_live["high"], df_live["low"], **params)
                        last_l = s_live.iloc[-1]
                        cur_l = float(df_live["close"].iloc[-1])
                        if last_l["cond_buy_long"]:        pos_l = "🟢 LONG AÇ"
                        elif last_l["cond_buy_short"]:     pos_l = "🔴 SHORT AÇ"
                        elif last_l["cond_exit_long"]:     pos_l = "🟡 LONG ÇIK"
                        elif last_l["cond_exit_short"]:    pos_l = "🟡 SHORT ÇIK"
                        elif last_l["major_up"] and last_l["zone_up"]:  pos_l = "🟢 LONG TUT"
                        elif last_l["major_dn"] and last_l["zone_dn"]:  pos_l = "🔴 SHORT TUT"
                        elif last_l["major_up"]:           pos_l = "⏳ LONG bekle"
                        elif last_l["major_dn"]:           pos_l = "⏳ SHORT bekle"
                        else:                              pos_l = "❓ Belirsiz"
                        tott_up_v = float(last_l["tott_up"]) if not pd.isna(last_l["tott_up"]) else None
                        tott_dn_v = float(last_l["tott_dn"]) if not pd.isna(last_l["tott_dn"]) else None
                        live_rows.append({
                            "Sembol": sym,
                            "Rating": sym_data.get("rating","?"),
                            "Durum": pos_l,
                            "Fiyat": cur_l,
                            "Stop ↑": tott_up_v,
                            "Stop ↓": tott_dn_v,
                            "Up %": (tott_up_v/cur_l - 1)*100 if tott_up_v else None,
                            "Dn %": (tott_dn_v/cur_l - 1)*100 if tott_dn_v else None,
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
                        "⏳ LONG bekle": 6, "⏳ SHORT bekle": 7, "❓ Belirsiz": 8,
                    }
                    df_live_show["_ord"] = df_live_show["Durum"].map(order_live).fillna(9)
                    df_live_show = df_live_show.sort_values(
                        ["_ord", "BT Ret %"], ascending=[True, False]
                    ).drop(columns="_ord").reset_index(drop=True)
                    fm1, fm2, fm3, fm4 = st.columns(4)
                    fm1.metric("🟢 LONG AÇ", int((df_live_show["Durum"]=="🟢 LONG AÇ").sum()))
                    fm2.metric("🔴 SHORT AÇ", int((df_live_show["Durum"]=="🔴 SHORT AÇ").sum()))
                    fm3.metric("🟡 ÇIK sinyali",
                                int(df_live_show["Durum"].str.contains("ÇIK", regex=False).sum()))
                    fm4.metric("Toplam", len(df_live_show))
                    st.dataframe(
                        df_live_show.style.format({
                            "Fiyat": "{:.4f}", "Stop ↑": "{:.4f}", "Stop ↓": "{:.4f}",
                            "Up %": "{:+.2f}%", "Dn %": "{:+.2f}%",
                            "BT Ret %": "{:+.1f}%",
                            "BT PF": lambda v: ("∞" if v >= 900 else f"{v:.2f}") if pd.notna(v) else "-",
                            "BT Win %": "{:.0f}%",
                        }).background_gradient(subset=["BT Ret %"], cmap="RdYlGn"),
                        use_container_width=True, height=500,
                    )
                    st.caption("Sıralama: önce **yeni AÇ sinyalleri**, sonra ÇIK, sonra TUT, sonra bekleyenler. "
                                "Stop ↑/↓ = pozisyon yönüne göre stop-loss seviyesi.")

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
