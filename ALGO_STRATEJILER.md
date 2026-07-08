# Algoritmik Trading Mantıkları — Kapsamlı Katalog

> Notlar internet taraması (QuantInsti, Wikipedia, QuantStart, CFA, arXiv, AQR, DayTrading.com)
> + domain bilgisiyle derlendi. **⬅ işaretli satırlar: bu projede TEST ETTİK.**
> Durum kodları: ✅ retail'e uygun · ⚠️ zor/veri ister · ❌ altyapı/sermaye ister (bize kapalı)

---

## 1) TREND-TAKİP / MOMENTUM  (en büyük aile, CTA'ların temeli)
- **Hareketli ortalama kesişimi** (MA crossover) — fiyat/MA veya iki MA kesişimi ⬅ (OTT bu ailede, test edildi)
- **MACD** — iki EMA farkı + sinyal çizgisi ⬅ (RSI ile aynı sonuç beklenir)
- **Donchian kanal kırılımı** — N-gün en yüksek/düşük kırılınca → **Turtle Trading** (Richard Dennis, 1983) ✅
- **SuperTrend / OTT / TOTT** — ATR/VAR bantlı trailing trend ⬅ (senin sistemin, test edildi → t=−9)
- **ADX/DMI** — trend gücü filtresi ⬅ (filtre olarak elendi)
- **Time-series (mutlak) momentum** — kendi geçmiş getirisi >0 → long ⬅ (test: kriz sigortası, alfa değil)
- **Cross-sectional momentum** — hisseleri birbirine göre sırala, kazananı al ⬅ (test: OOS güçlü, full nötr)
- **Kalıntı/rezidüel momentum** — beta-nötr momentum ⬅ (test: OOS t=+3.1 ama survivorship şüpheli)
- **Dual momentum** (Gary Antonacci) — mutlak + göreli momentum birleşimi ✅
- **Kanal/breakout** (opening range, N-bar high) ✅
- Ünlü: **Turtle Traders**, Dunn Capital, **Man AHL**, Winton, CTA/managed futures endüstrisi

## 2) MEAN-REVERSION / KARŞI-TREND
- **RSI aşırı-alım/satım** — RSI<30 al, >70 sat ⬅ (test: drift-üstü NEGATİF, %44-46)
- **Bollinger Bands reversion** — banda değince tersine ⬅ (RSI ile aynı aile)
- **Grid trading** — kademeli al/sat, dalgada nakit ⬅ (BOTUMUZ — kanıtlanmış kaybeden)
- **Martingale / anti-martingale** — kayıpta katla (❌ iflas riski)
- **Ornstein-Uhlenbeck** — matematiksel ortalamaya dönüş modeli ⚠️
- **VWAP/gün-ortası reversion**, **gap fade** (açılış boşluğunu kapatma) ✅
- Not: BIST'te mean-reversion ailesi bizde **kanıtlanmış çöktü** (piyasa momentum-sürücülü)

## 3) İSTATİSTİKSEL ARBİTRAJ / PAIRS / GÖRELİ DEĞER
- **Pairs trading** — kointegre iki hisse ayrışınca yakınsamaya bahis (örn: KOÇ-SABANCI) ⚠️ ✅test-edilebilir
- **Cointegration/ECM**, **PCA/faktör-nötr stat-arb** — çok değişkenli ⚠️
- **Index/basket arbitrage**, **ETF arbitrage** (yaratım/itfa) ❌
- **Convergence arb** — LTCM'in yöntemi (1998'de patladı — ders!)
- Ünlü: **Morgan Stanley (Nunzio Tartaglia stat-arb grubu, 1980'ler)**, **Renaissance Medallion (Jim Simons)**, D.E. Shaw, Two Sigma

## 4) PİYASA YAPICILIĞI / LİKİDİTE SAĞLAMA
- **Bid-ask spread yakalama** — sürekli alış/satış kotasyonu ❌ (spread'i onlar toplar, biz öderiz)
- **Envanter yönetimi** — Avellaneda-Stoikov modeli ❌
- **Order-book imbalance** — emir defteri dengesizliği ❌ (hız ister)
- Ünlü: **Citadel Securities, Jane Street, Virtu, Jump, HRT** (piyasanın kazanan tarafı — bize kapalı)

## 5) YÜKSEK FREKANS (HFT) / MİKROYAPI / GECİKME
- **Latency arbitrage** — borsalar arası ms gecikme ❌ (colocation, FPGA ister)
- **Order-flow prediction**, **rebate/sub-penny arb** ❌
- Teknoloji: FPGA, co-location, kernel-bypass, ~nanosaniye ❌ (bize %100 kapalı)
- Ünlü: Virtu, Getco, Jump Trading

## 6) KLASİK ARBİTRAJ
- **Triangular FX arb** — 3 döviz çapraz kuru ⚠️
- **Cross-exchange arb** — crypto borsaları arası fiyat farkı ✅ (crypto'da mümkün, hız yarışı)
- **Cash-and-carry** — spot vs vadeli baz (funding rate) ✅ (crypto perp funding — gerçek!)
- **Covered interest parity**, **convertible bond arb**, **kapalı-uçlu fon iskonto** ⚠️
- Ünlü: **Ed Thorp** (convertible arb, Kelly criterion), LTCM

## 7) FAKTÖR YATIRIMI / SMART BETA  (akademik, uzun-vade)
- **Value** — ucuz (F/K, PD/DD düşük) al ⚠️ (temel veri geçmişi ister — bizde yok)
- **Momentum** — son 6-12 ay kazananı al ⬅ (test edildi, rejim-bağımlı)
- **Quality** — yüksek kârlılık/düşük borç ⚠️ (temel veri)
- **Low-volatility** — düşük-vol anomalisi ⬅ (test: piyasayı geçmedi)
- **Size** — küçük-cap primi ⚠️
- **Carry**, **Investment/Profitability** (Fama-French 5-faktör)
- Ünlü: **AQR (Cliff Asness)**, **Dimensional/DFA (Fama-French)**, BlackRock, MSCI

## 8) OLAY-BAZLI (EVENT-DRIVEN)
- **Merger/risk arbitrage** — hedef al, alıcıyı short (düşük vol, iyi Sharpe) ⚠️
- **PEAD (post-earnings drift)** — bilanço sürprizi sonrası sürüklenme ⚠️ (bilanço tarihi+tahmin verisi)
- **Index rebalancing** — endekse giren/çıkan hisse (BIST100 revizyonu!) ✅ **BIST'te denenebilir**
- **Buyback, spin-off, IPO, temettü, insider işlemleri takibi** ⚠️
- Ünlü: merger-arb masaları, aktivist fonlar

## 9) CARRY (taşıma) STRATEJİLERİ
- **FX carry** — yüksek faizli parayı al, düşük faizliyle fonla ✅ (TL carry — ama kur riski)
- **Bond/commodity carry**, **roll yield** ⚠️
- **Volatility carry** — opsiyon/vol satmak (prim topla) ⚠️ (kuyruk riski — LJM 2018'de patladı)
- Ünlü: currency carry trade (klasik)

## 10) VOLATİLİTE TİCARETİ
- **Vol arbitrage** — implied vs realized volatilite farkı ⚠️ (opsiyon ister)
- **Gamma scalping**, **dispersion**, **variance swap** ❌⚠️
- **VIX vade yapısı** — contango/backwardation ⚠️
- **Tail hedging** — Taleb/**Universa** (siyah kuğu koruması)
- Ünlü: Universa (kazanan tail-hedge), LJM (kaybeden vol-satış)

## 11) MAKİNE ÖĞRENMESİ / AI / ALT-DATA
- **Supervised** (getiri tahmini: LSTM, Transformer, XGBoost) ⚠️ (overfit tuzağı çok yüksek)
- **Reinforcement learning** (FinRL, PPO/DDPG) ⚠️
- **NLP/sentiment** (haber, Twitter, Reddit) ⚠️
- **Alternatif veri** — uydu görüntüsü, kredi kartı, web-scraping ❌ (pahalı)
- **LLM ajanları** (2025-26 trendi, FinRL-DeepSeek, agentic trading) ⚠️
- Ünlü: **Renaissance** (erken ML), **Two Sigma**, **Numerai** (crowdsource)
- ⚠️ UYARI: ML retail'de genelde **overfit** üretir — bizim curve-fit sorunumuzun steroidli hali

## 12) İCRA ALGORİTMALARI  (alfa değil, maliyet azaltma)
- **VWAP, TWAP, POV** (hacim yüzdesi), **Implementation Shortfall**
- **Iceberg/gizli emir**, **sniper/likidite-arayan**
- Not: Bunlar "nasıl al-sat" (execution), "ne al-sat" (alfa) değil

## 13) MEVSİMSELLİK / TAKVİM
- **Turn-of-month**, **day-of-week**, **Sell-in-May**, **Ocak etkisi**, tatil etkisi
- **Overnight vs intraday** getiri ayrışması ✅ (test-edilebilir, genelde zayıf/data-mining)

## 14) SENTIMENT / DAVRANIŞSAL / POZİSYONLAMA
- **Haber/sentiment skorlama**, **sosyal medya** (Reddit/Twitter)
- **Put-call ratio**, **COT raporları** (pozisyonlama), **fear-greed endeksi**
- **Google Trends** arama hacmi ⚠️

---

## ÜNLÜ İSİMLER & DERSLER
| Kişi/Fon | Katkı | Ders |
|---|---|---|
| **Jim Simons / Renaissance Medallion** | En efsanevi kantitatif fon (%39/yıl net, 30yıl) | ML + mikro-anomali + gizlilik; kopyalanamaz |
| **Ed Thorp** | Convertible arb, **Kelly criterion** (pozisyon boyutu) | Matematiksel kenar + risk yönetimi |
| **Richard Dennis / Turtles** | Trend-takip kuralları öğretilebilir | Basit kurallar + disiplin |
| **Cliff Asness / AQR** | Faktör yatırımı akademik→pratik | Value+Momentum+Quality, uzun-vade |
| **Ray Dalio / Bridgewater** | **Risk parity / All Weather** | Varlık dağılımı > sinyal |
| **LTCM (Merton, Scholes)** | Convergence arb, Nobel'li | **Kaldıraç + model körlüğü = iflas (1998)** |
| **Nassim Taleb / Universa** | Tail hedging | Nadir olaylara hazırlık |

---

## 🎯 BİZİM İÇİN DÜRÜST DEĞERLENDİRME (test sonuçlarımıza göre)
**Bize KAPALI (altyapı/sermaye/hız):** HFT, latency arb, market-making, order-book — 4,5 numara.
**Test ETTİK, ÇALIŞMADI:** trend/OTT, mean-reversion/grid, RSI, momentum (rejim-bağımlı), low-vol, macro.
**Veri EKSİK (temiz test edilemez):** value/quality (temel veri geçmişi), event-driven/PEAD (bilanço takvimi), alt-data.
**Retail'de GERÇEKTEN denenebilir + henüz bakmadığımız:**
- ✅ **Pairs trading** (KOÇ-SABANCI gibi kointegre BIST çiftleri) — göreli değer, market-neutral
- ✅ **Endeks rebalancing** (BIST100'e giren/çıkan hisse — takvim belli, olay-bazlı)
- ✅ **Crypto funding/cash-carry** (perp funding rate — gerçek, mekanik)
- ✅ **Kelly criterion** — pozisyon boyutlandırma (edge bulunursa uygulama katmanı)
- ⚠️ **Risk parity / varlık dağılımı** — "sinyal değil dağılım" felsefesi (Dalio)

**EN DÜRÜST SONUÇ:** Kazanan yöntemlerin çoğu ya (a) hız/sermaye/altyapı (HFT, MM), ya (b) veri
(faktör, event, alt-data), ya (c) kurumsal ölçek ister. Retail + ücretsiz veri + BIST'te
kanıtlanmış edge dar: **pairs, event-driven (endeks), crypto-funding** henüz bakılmadı;
gerisi ya kapalı ya test edilip elendi.
